import json
import os
import signal
import sys
import threading
from datetime import datetime, timezone
from collections import defaultdict

import structlog
import uvicorn
from confluent_kafka import Consumer, Producer
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Konfiguration

load_dotenv()

KAFKA_BOOTSTRAP    = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_GROUP_ID     = os.getenv("KAFKA_GROUP_ID", "signal-aggregator-group")
SIGNAL_TTL_SECONDS = int(os.getenv("SIGNAL_TTL_SECONDS", "60"))  # Signal verfaellt nach 60 Sekunden

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


# Signal Cache

class SignalCache:
    """
    Speichert das zuletzt empfangene Signal pro Symbol und Typ.
    Signale verfallen nach SIGNAL_TTL_SECONDS.
    """
    def __init__(self):
        self._indicator: dict[str, dict]  = {}
        self._sentiment: dict[str, dict]  = {}

    def store_indicator(self, symbol: str, data: dict):
        self._indicator[symbol] = {
            **data,
            "_received_at": datetime.now(timezone.utc).isoformat(),
        }

    def store_sentiment(self, symbol: str, data: dict):
        self._sentiment[symbol] = {
            **data,
            "_received_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_pair(self, symbol: str) -> tuple[dict | None, dict | None]:
        """Gibt (indicator, sentiment) zurueck wenn beide vorhanden und nicht verfallen."""
        indicator = self._indicator.get(symbol)
        sentiment = self._sentiment.get(symbol)

        if indicator and self._is_expired(indicator):
            del self._indicator[symbol]
            indicator = None

        if sentiment and self._is_expired(sentiment):
            del self._sentiment[symbol]
            sentiment = None

        return indicator, sentiment

    def clear(self, symbol: str):
        """Loescht beide Signale nach erfolgreicher Aggregation."""
        self._indicator.pop(symbol, None)
        self._sentiment.pop(symbol, None)

    def _is_expired(self, data: dict) -> bool:
        received_at = datetime.fromisoformat(data["_received_at"])
        age = (datetime.now(timezone.utc) - received_at).total_seconds()
        return age > SIGNAL_TTL_SECONDS


# Signal Aggregator

class SignalAggregator:
    def __init__(self):
        self.cache = SignalCache()

    def aggregate(self, symbol: str) -> dict | None:
        """
        Aggregiert Indikator- und Sentiment-Signal.
        Gibt ein Trade-Signal zurueck wenn beide uebereinstimmen, sonst None.
        """
        indicator, sentiment = self.cache.get_pair(symbol)

        if not indicator or not sentiment:
            return None

        ind_signal  = indicator.get("signal")         # BUY / SELL / HOLD
        sent_signal = sentiment.get("sentiment_signal")  # BUY / SELL / HOLD
        sent_score  = float(sentiment.get("sentiment_score", 0.0))

        # Beide Signale muessen uebereinstimmen
        if ind_signal != sent_signal:
            log.info("signals_disagree",
                     symbol=symbol,
                     indicator=ind_signal,
                     sentiment=sent_signal)
            return None

        # HOLD Signale werden nicht weitergeleitet
        if ind_signal == "HOLD":
            return None

        # ATR aus Indikator-Daten extrahieren
        atr = float(indicator.get("atr", {}).get("value", 1.0))

        # Aktuellen Preis aus VWAP schaetzen (praeziser Preis kommt vom Tick)
        price = float(indicator.get("vwap", {}).get("value", 0.0))

        if price <= 0:
            log.error("invalid_price", symbol=symbol, price=price)
            return None

        result = {
            "symbol":           symbol,
            "action":           ind_signal,
            "price":            price,
            "atr":              atr,
            "indicator_signal": ind_signal,
            "sentiment_signal": sent_signal,
            "sentiment_score":  sent_score,
            "valid_time":       indicator.get("valid_time", ""),
            "transaction_time": datetime.now(timezone.utc).isoformat(),
        }

        log.info("signal_aggregated",
                 symbol=symbol,
                 action=ind_signal,
                 sentiment_score=sent_score,
                 atr=atr)

        # Cache leeren damit das gleiche Signal nicht doppelt gesendet wird
        self.cache.clear(symbol)

        return result


# Signal Aggregator Service

class SignalAggregatorService:
    def __init__(self):
        self.aggregator = SignalAggregator()
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
        # Beide Topics gleichzeitig subscriben
        self.consumer.subscribe(["indicator_results", "sentiment_results"])
        is_ready = True
        log.info("service_ready", topics=["indicator_results", "sentiment_results"])

        while self.running:
            msg = self.consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                log.error("kafka_error", error=str(msg.error()))
                continue

            try:
                topic  = msg.topic()
                data   = json.loads(msg.value().decode("utf-8"))
                symbol = data.get("symbol")

                if not symbol:
                    continue

                if topic == "indicator_results":
                    self.aggregator.cache.store_indicator(symbol, data)
                elif topic == "sentiment_results":
                    self.aggregator.cache.store_sentiment(symbol, data)

                # Aggregation versuchen
                result = self.aggregator.aggregate(symbol)

                if result:
                    self.producer.produce(
                        topic="trade_signals",
                        key=symbol.encode("utf-8"),
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
    service = SignalAggregatorService()

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
