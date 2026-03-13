import json
import os
import signal
import sys
import threading
import asyncio
from datetime import datetime, timezone

import structlog
import uvicorn
from confluent_kafka import Consumer, Producer
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

# Konfiguration

load_dotenv()

TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID", "")
KAFKA_BOOTSTRAP   = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_GROUP_ID    = os.getenv("KAFKA_GROUP_ID", "telegram-bot-group")
APPROVE_TIMEOUT   = int(os.getenv("APPROVE_TIMEOUT_SECONDS", "300"))  # 5 Minuten

# Structured Logging

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger()

# Health Check API

app = FastAPI()
is_ready = False

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def ready():
    if is_ready:
        return JSONResponse(status_code=200, content={"status": "ready"})
    return JSONResponse(status_code=503, content={"status": "not ready"})


# Nachrichtenformat

def format_trade_message(decision: dict) -> str:
    """Formatiert einen Trade als lesbare Telegram-Nachricht."""
    action  = decision["action"]
    symbol  = decision["symbol"]
    emoji   = "🟢" if action == "BUY" else "🔴"

    return (
        f"{emoji} *TRADE SIGNAL: {action} {symbol}*\n"
        f"\n"
        f"💰 Preis:        `{decision['price']:.2f} USD`\n"
        f"📦 Menge:        `{decision['quantity']} Aktien`\n"
        f"💵 Positionswert: `{decision['position_value']:.2f} USD`\n"
        f"⚠️ Risiko:       `{decision['risk_amount']:.2f} USD`\n"
        f"\n"
        f"🛑 Stop-Loss:    `{decision['stop_loss']:.2f} USD`\n"
        f"🎯 Take-Profit:  `{decision['take_profit']:.2f} USD`\n"
        f"\n"
        f"🕐 Signal-Zeit:  `{decision['valid_time']}`\n"
    )


# Telegram Bot

class TelegramBot:
    def __init__(self):
        self.application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )
        # Speichert ausstehende Entscheidungen: message_id -> decision
        self.pending: dict[int, dict] = {}

        self.application.add_handler(
            CallbackQueryHandler(self.handle_callback)
        )

    async def send_trade_alert(self, decision: dict) -> int:
        """
        Sendet eine Trade-Nachricht mit Approve/Reject Buttons.
        Gibt die message_id zurueck.
        """
        text    = format_trade_message(decision)
        symbol  = decision["symbol"]
        action  = decision["action"]

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve:{symbol}:{action}"),
                InlineKeyboardButton("❌ Reject",  callback_data=f"reject:{symbol}:{action}"),
            ]
        ])

        msg = await self.application.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

        log.info("trade_alert_sent",
                 symbol=symbol,
                 action=action,
                 message_id=msg.message_id)

        return msg.message_id

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Empfaengt Approve/Reject Klick vom Benutzer.
        """
        query   = update.callback_query
        data    = query.data  # z.B. "approve:AAPL:BUY"
        parts   = data.split(":")
        action  = parts[0]   # approve oder reject
        symbol  = parts[1]
        side    = parts[2]

        await query.answer()

        msg_id  = query.message.message_id
        decision = self.pending.pop(msg_id, None)

        if action == "approve" and decision:
            await query.edit_message_text(
                f"✅ *{side} {symbol} genehmigt.* Order wird ausgefuehrt.",
                parse_mode="Markdown",
            )
            log.info("trade_approved_by_user", symbol=symbol, action=side)
            return decision

        else:
            await query.edit_message_text(
                f"❌ *{side} {symbol} abgelehnt.*",
                parse_mode="Markdown",
            )
            log.info("trade_rejected_by_user", symbol=symbol, action=side)
            return None

    async def start(self):
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        log.info("telegram_bot_started")

    async def stop(self):
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        log.info("telegram_bot_stopped")


# Telegram Bot Service

class TelegramBotService:
    def __init__(self):
        self.bot      = TelegramBot()
        self.consumer = self._create_consumer()
        self.producer = self._create_producer()
        self.running  = True
        self.loop     = asyncio.new_event_loop()

    def _create_consumer(self) -> Consumer:
        return Consumer({
            "bootstrap.servers":  KAFKA_BOOTSTRAP,
            "group.id":           KAFKA_GROUP_ID,
            "auto.offset.reset":  "earliest",
            "enable.auto.commit": True,
        })

    def _create_producer(self) -> Producer:
        return Producer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "acks":              "all",
        })

    def _publish_approved(self, decision: dict):
        """Leitet genehmigte Trades an den Order Executor weiter."""
        self.producer.produce(
            topic="approved_trades",
            key=decision["symbol"].encode("utf-8"),
            value=json.dumps(decision).encode("utf-8"),
        )
        self.producer.poll(0)

    def start(self):
        global is_ready

        # Bot in separatem Event Loop starten
        threading.Thread(
            target=self.loop.run_forever,
            daemon=True,
        ).start()

        asyncio.run_coroutine_threadsafe(self.bot.start(), self.loop)

        self.consumer.subscribe(["risk_approved_trades"])
        is_ready = True
        log.info("service_ready", topic="risk_approved_trades")

        while self.running:
            msg = self.consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                log.error("kafka_error", error=str(msg.error()))
                continue
            try:
                decision = json.loads(msg.value().decode("utf-8"))

                # Alert senden und message_id speichern
                future   = asyncio.run_coroutine_threadsafe(
                    self.bot.send_trade_alert(decision),
                    self.loop,
                )
                msg_id   = future.result(timeout=10)
                self.bot.pending[msg_id] = decision

                log.info("waiting_for_approval",
                         symbol=decision["symbol"],
                         message_id=msg_id)

            except Exception as e:
                log.error("processing_failed", error=str(e))

    def stop(self):
        global is_ready
        self.running = False
        is_ready     = False
        self.consumer.close()
        self.producer.flush(timeout=10)
        asyncio.run_coroutine_threadsafe(self.bot.stop(), self.loop)
        log.info("service_stopped")


# Entry Point

def main():
    service = TelegramBotService()

    def handle_sigterm(signum, frame):
        log.info("sigterm_received")
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    health_thread = threading.Thread(
        target=lambda: uvicorn.run(app, host="0.0.0.0", port=8080, log_level="error"),
        daemon=True,
    )
    health_thread.start()
    service.start()

if __name__ == "__main__":
    main()
