import json
import os
import signal
import sys
import threading
from datetime import datetime, timezone
from dataclasses import dataclass

import structlog
import uvicorn
from confluent_kafka import Consumer, Producer, KafkaException
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Konfiguration

load_dotenv()

KAFKA_BOOTSTRAP      = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_GROUP_ID       = os.getenv("KAFKA_GROUP_ID", "risk-manager-group")
MAX_POSITION_PCT     = float(os.getenv("MAX_POSITION_PCT", "0.05"))    # Max 5% des Kapitals pro Trade
MAX_PORTFOLIO_RISK   = float(os.getenv("MAX_PORTFOLIO_RISK", "0.20"))  # Max 20% des Kapitals insgesamt
ATR_MULTIPLIER       = float(os.getenv("ATR_MULTIPLIER", "2.0"))       # Stop-Loss = Preis - (ATR * 2)
DEFAULT_WIN_RATE     = float(os.getenv("DEFAULT_WIN_RATE", "0.55"))    # Angenommene Trefferquote
DEFAULT_WIN_LOSS     = float(os.getenv("DEFAULT_WIN_LOSS", "1.5"))     # Durchschnittlicher Gewinn/Verlust Ratio
TOTAL_CAPITAL        = float(os.getenv("TOTAL_CAPITAL", "10000.0"))    # Gesamtkapital in USD

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


# Risiko-Berechnung

@dataclass
class TradeSignal:
    symbol:           str
    action:           str    # BUY / SELL
    price:            float
    atr:              float
    indicator_signal: str
    sentiment_signal: str
    sentiment_score:  float
    valid_time:       str


@dataclass
class RiskDecision:
    approved:         bool
    symbol:           str
    action:           str
    price:            float
    quantity:         int
    stop_loss:        float
    take_profit:      float
    position_value:   float
    risk_amount:      float
    reason:           str
    valid_time:       str
    transaction_time: str


class RiskCalculator:

    def evaluate(self, signal: TradeSignal) -> RiskDecision:
        """
        Bewertet ein Handelssignal und gibt eine Risikoentscheidung zurück.
        """
        # Schritt 1: Signalstaerke pruefen
        if not self._signals_agree(signal):
            return self._reject(signal, "Indikatoren und Sentiment stimmen nicht ueberein")

        # Schritt 2: Stop-Loss berechnen
        stop_loss   = self._calculate_stop_loss(signal)
        risk_per_share = signal.price - stop_loss

        if risk_per_share <= 0:
            return self._reject(signal, "Ungueltige Stop-Loss Berechnung")

        # Schritt 3: Positionsgroesse via Half Kelly
        position_pct = self._half_kelly(DEFAULT_WIN_RATE, DEFAULT_WIN_LOSS)
        position_pct = min(position_pct, MAX_POSITION_PCT)

        # Schritt 4: Maximales Risikokapital berechnen
        max_risk_capital = TOTAL_CAPITAL * position_pct
        quantity         = int(max_risk_capital / risk_per_share)

        if quantity <= 0:
            return self._reject(signal, "Positionsgroesse zu klein")

        position_value = quantity * signal.price

        # Schritt 5: Portfolio-Risiko pruefen
        if position_value > TOTAL_CAPITAL * MAX_PORTFOLIO_RISK:
            quantity       = int((TOTAL_CAPITAL * MAX_PORTFOLIO_RISK) / signal.price)
            position_value = quantity * signal.price

        # Schritt 6: Take-Profit berechnen (Risk/Reward = 2:1)
        risk_amount  = quantity * risk_per_share
        take_profit  = round(signal.price + (risk_per_share * 2), 4)

        log.info("trade_approved",
                 symbol=signal.symbol,
                 action=signal.action,
                 quantity=quantity,
                 stop_loss=round(stop_loss, 4),
                 take_profit=take_profit,
                 risk_usd=round(risk_amount, 2))

        return RiskDecision(
            approved=True,
            symbol=signal.symbol,
            action=signal.action,
            price=signal.price,
            quantity=quantity,
            stop_loss=round(stop_loss, 4),
            take_profit=take_profit,
            position_value=round(position_value, 2),
            risk_amount=round(risk_amount, 2),
            reason="Alle Risikopruefungen bestanden",
            valid_time=signal.valid_time,
            transaction_time=datetime.now(timezone.utc).isoformat(),
        )

    def _signals_agree(self, signal: TradeSignal) -> bool:
        """
        Prueft ob Indikator-Signal und Sentiment-Signal uebereinstimmen.
        Beide muessen die gleiche Richtung signalisieren.
        """
        if signal.action == "BUY":
            return (signal.indicator_signal == "BUY"
                    and signal.sentiment_signal == "BUY"
                    and signal.sentiment_score >= 0.3)
        if signal.action == "SELL":
            return (signal.indicator_signal == "SELL"
                    and signal.sentiment_signal == "SELL"
                    and signal.sentiment_score <= -0.3)
        return False

    def _calculate_stop_loss(self, signal: TradeSignal) -> float:
        """
        ATR-basierter Stop-Loss.
        BUY:  Stop = Preis - (ATR * Multiplikator)
        SELL: Stop = Preis + (ATR * Multiplikator)
        """
        atr_distance = signal.atr * ATR_MULTIPLIER
        if signal.action == "BUY":
            return round(signal.price - atr_distance, 4)
        return round(signal.price + atr_distance, 4)

    def _half_kelly(self, win_rate: float, win_loss_ratio: float) -> float:
        """
        Half Kelly Criterion.
        Kelly% = (W * R - (1 - W)) / R
        Half Kelly = Kelly% * 0.5

        W = Trefferquote (z.B. 0.55)
        R = Gewinn/Verlust Ratio (z.B. 1.5)
        """
        kelly = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
        kelly = max(kelly, 0.0)   # Kein negativer Kelly
        return round(kelly * 0.5, 4)

    def _reject(self, signal: TradeSignal, reason: str) -> RiskDecision:
        log.info("trade_rejected", symbol=signal.symbol, reason=reason)
        return RiskDecision(
            approved=False,
            symbol=signal.symbol,
            action=signal.action,
            price=signal.price,
            quantity=0,
            stop_loss=0.0,
            take_profit=0.0,
            position_value=0.0,
            risk_amount=0.0,
            reason=reason,
            valid_time=signal.valid_time,
            transaction_time=datetime.now(timezone.utc).isoformat(),
        )


# Risk Manager Service

class RiskManagerService:
    def __init__(self):
        self.calculator = RiskCalculator()
        self.consumer   = self._create_consumer()
        self.producer   = self._create_producer()
        self.running    = True
        self.processed  = 0

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
            "retries":           5,
        })

    def start(self):
        global is_ready
        self.consumer.subscribe(["trade_signals"])
        is_ready = True
        log.info("service_ready", topic="trade_signals")

        while self.running:
            msg = self.consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                log.error("kafka_error", error=str(msg.error()))
                continue
            try:
                data   = json.loads(msg.value().decode("utf-8"))
                signal = TradeSignal(**data)
                decision = self.calculator.evaluate(signal)

                if decision.approved:
                    self._publish_decision(decision)

                self.processed += 1

            except Exception as e:
                log.error("processing_failed", error=str(e))

    def _publish_decision(self, decision: RiskDecision):
        payload = decision.__dict__
        self.producer.produce(
            topic="approved_trades",
            key=decision.symbol.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8"),
        )
        self.producer.poll(0)

    def stop(self):
        global is_ready
        self.running = False
        is_ready     = False
        self.consumer.close()
        self.producer.flush(timeout=10)
        log.info("service_stopped")


# Entry Point

def main():
    service = RiskManagerService()

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
