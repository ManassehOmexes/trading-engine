import json
import os
import signal
import sys
import threading
from datetime import datetime, timezone

import structlog
import uvicorn
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from confluent_kafka import Consumer, Producer
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Konfiguration

load_dotenv()

ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
KAFKA_BOOTSTRAP   = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_GROUP_ID    = os.getenv("KAFKA_GROUP_ID", "order-executor-group")
PAPER_TRADING     = os.getenv("PAPER_TRADING", "true").lower() == "true"
ORDER_TYPE        = os.getenv("ORDER_TYPE", "market")  # market oder limit

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


# Order Executor

class OrderExecutor:
    def __init__(self):
        self.client = TradingClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY,
            paper=PAPER_TRADING,
        )
        log.info("alpaca_connected", paper=PAPER_TRADING)

    def execute(self, decision: dict) -> dict:
        """
        Sendet einen genehmigten Trade an Alpaca.
        Gibt das Ergebnis als Dictionary zurueck.
        """
        symbol   = decision["symbol"]
        action   = decision["action"]
        quantity = decision["quantity"]
        price    = decision["price"]

        side = OrderSide.BUY if action == "BUY" else OrderSide.SELL

        try:
            if ORDER_TYPE == "limit":
                request = LimitOrderRequest(
                    symbol=symbol,
                    qty=quantity,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                    limit_price=round(price, 2),
                )
            else:
                request = MarketOrderRequest(
                    symbol=symbol,
                    qty=quantity,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                )

            order = self.client.submit_order(request)

            log.info("order_submitted",
                     symbol=symbol,
                     action=action,
                     quantity=quantity,
                     order_id=str(order.id),
                     order_type=ORDER_TYPE)

            return {
                "status":           "submitted",
                "order_id":         str(order.id),
                "symbol":           symbol,
                "action":           action,
                "quantity":         quantity,
                "order_type":       ORDER_TYPE,
                "stop_loss":        decision["stop_loss"],
                "take_profit":      decision["take_profit"],
                "valid_time":       decision["valid_time"],
                "transaction_time": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            log.error("order_failed",
                      symbol=symbol,
                      action=action,
                      error=str(e))
            return {
                "status":           "failed",
                "order_id":         None,
                "symbol":           symbol,
                "action":           action,
                "quantity":         quantity,
                "error":            str(e),
                "transaction_time": datetime.now(timezone.utc).isoformat(),
            }


# Order Executor Service

class OrderExecutorService:
    def __init__(self):
        self.executor  = OrderExecutor()
        self.consumer  = self._create_consumer()
        self.producer  = self._create_producer()
        self.running   = True
        self.processed = 0

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

    def start(self):
        global is_ready
        self.consumer.subscribe(["approved_trades"])
        is_ready = True
        log.info("service_ready", topic="approved_trades")

        while self.running:
            msg = self.consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                log.error("kafka_error", error=str(msg.error()))
                continue
            try:
                decision = json.loads(msg.value().decode("utf-8"))
                result   = self.executor.execute(decision)

                # Ergebnis fuer Audit-Trail nach Kafka
                self.producer.produce(
                    topic="order_results",
                    key=decision["symbol"].encode("utf-8"),
                    value=json.dumps(result).encode("utf-8"),
                )
                self.producer.poll(0)
                self.processed += 1

            except Exception as e:
                log.error("processing_failed", error=str(e))

    def stop(self):
        global is_ready
        self.running = False
        is_ready     = False
        self.consumer.close()
        self.producer.flush(timeout=10)
        log.info("service_stopped")


# Entry Point

def main():
    service = OrderExecutorService()

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
