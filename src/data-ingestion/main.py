import json
import os
import signal
import sys
import threading
from datetime import datetime, timezone

import structlog
import uvicorn
from alpaca.data.live import StockDataStream
from alpaca.data.models import Bar, Trade
from confluent_kafka import Producer, KafkaException
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Konfiguration

load_dotenv()

ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
KAFKA_BOOTSTRAP   = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
SYMBOLS           = os.getenv("SYMBOLS", "AAPL,MSFT,GOOGL,AMZN,NVDA").split(",")

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

# Kafka Producer

def create_kafka_producer() -> Producer:
    config = {
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "client.id":         "data-ingestion-service",
        "acks":              "all",
        "retries":           5,
        "linger.ms":         100,
    }
    return Producer(config)

def delivery_report(err, msg):
    """Callback: Wird aufgerufen wenn Kafka die Nachricht bestaetigt oder ablehnt."""
    if err:
        log.error("kafka_delivery_failed",
                  topic=msg.topic(),
                  error=str(err))
    else:
        log.debug("kafka_delivery_success",
                  topic=msg.topic(),
                  partition=msg.partition(),
                  offset=msg.offset())

# Data Ingestion Service

class DataIngestionService:
    def __init__(self):
        self.producer    = create_kafka_producer()
        self.stream      = StockDataStream(ALPACA_API_KEY, ALPACA_SECRET_KEY)
        self.tick_count  = 0

    def _publish(self, topic: str, key: str, data: dict):
        """Schreibt einen Datenpunkt nach Kafka."""
        try:
            self.producer.produce(
                topic=topic,
                key=key.encode("utf-8"),
                value=json.dumps(data).encode("utf-8"),
                callback=delivery_report,
            )
            self.producer.poll(0)
        except KafkaException as e:
            log.error("kafka_publish_failed", topic=topic, error=str(e))

    async def handle_trade(self, trade: Trade):
        """Empfaengt einen Trade-Tick von Alpaca und schreibt ihn nach Kafka."""
        data = {
            "symbol":           trade.symbol,
            "price":            float(trade.price),
            "size":             float(trade.size),
            "exchange":         trade.exchange,
            "valid_time":       trade.timestamp.isoformat(),
            "transaction_time": datetime.now(timezone.utc).isoformat(),
        }
        self._publish(topic="market_ticks", key=trade.symbol, data=data)

        self.tick_count += 1
        if self.tick_count % 100 == 0:
            log.info("ticks_processed", count=self.tick_count)

    async def handle_bar(self, bar: Bar):
        """Empfaengt eine 1-Minuten-Bar von Alpaca."""
        data = {
            "symbol":           bar.symbol,
            "open":             float(bar.open),
            "high":             float(bar.high),
            "low":              float(bar.low),
            "close":            float(bar.close),
            "volume":           float(bar.volume),
            "vwap":             float(bar.vwap) if bar.vwap else None,
            "valid_time":       bar.timestamp.isoformat(),
            "transaction_time": datetime.now(timezone.utc).isoformat(),
        }
        self._publish(topic="market_bars", key=bar.symbol, data=data)

    def start(self):
        """Startet den WebSocket Stream und abonniert alle Symbole."""
        global is_ready

        log.info("service_starting", symbols=SYMBOLS, kafka=KAFKA_BOOTSTRAP)

        self.stream.subscribe_trades(self.handle_trade, *SYMBOLS)
        self.stream.subscribe_bars(self.handle_bar, *SYMBOLS)

        is_ready = True
        log.info("service_ready", symbols=SYMBOLS)

        self.stream.run()

    def stop(self):
        """Graceful Shutdown: Flush alle ausstehenden Kafka-Nachrichten."""
        global is_ready
        log.info("service_stopping")
        is_ready = False
        self.stream.stop()
        self.producer.flush(timeout=10)
        log.info("service_stopped")

# Entry Point

def main():
    service = DataIngestionService()

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
