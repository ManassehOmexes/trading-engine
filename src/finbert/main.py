import json
import os
import signal
import sys
import threading
from datetime import datetime, timezone

import structlog
import uvicorn
from confluent_kafka import Consumer, KafkaException
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from transformers import pipeline

# Konfiguration

load_dotenv()

KAFKA_BOOTSTRAP   = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_GROUP_ID    = os.getenv("KAFKA_GROUP_ID", "finbert-consumer-group")
CLICKHOUSE_HOST   = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT   = int(os.getenv("CLICKHOUSE_PORT", "8123"))
MODEL_NAME        = os.getenv("MODEL_NAME", "ProsusAI/finbert")
SENTIMENT_THRESHOLD = float(os.getenv("SENTIMENT_THRESHOLD", "0.3"))

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

# FinBERT Sentiment Analyser

class SentimentAnalyser:
    def __init__(self):
        log.info("model_loading", model=MODEL_NAME)
        self.pipe = pipeline(
            task="text-classification",
            model=MODEL_NAME,
            top_k=None,   # Gibt alle drei Label-Scores zurueck
        )
        log.info("model_loaded", model=MODEL_NAME)

    def analyse(self, text: str) -> dict:
        """
        Gibt einen Score zwischen -1.0 und +1.0 zurueck.
        Score = P(positive) - P(negative)
        """
        results = self.pipe(text[:512])  # FinBERT max 512 Tokens

        scores = {item["label"]: item["score"] for item in results[0]}

        score = scores.get("positive", 0.0) - scores.get("negative", 0.0)

        return {
            "score":    round(score, 4),
            "positive": round(scores.get("positive", 0.0), 4),
            "negative": round(scores.get("negative", 0.0), 4),
            "neutral":  round(scores.get("neutral",  0.0), 4),
            "signal":   self._to_signal(score),
        }

    def _to_signal(self, score: float) -> str:
        """Konvertiert Score in ein handelbares Signal."""
        if score >= SENTIMENT_THRESHOLD:
            return "BUY"
        if score <= -SENTIMENT_THRESHOLD:
            return "SELL"
        return "HOLD"

# FinBERT Service

class FinBERTService:
    def __init__(self):
        self.analyser       = SentimentAnalyser()
        self.consumer       = self._create_consumer()
        self.processed      = 0
        self.running        = True

    def _create_consumer(self) -> Consumer:
        return Consumer({
            "bootstrap.servers":  KAFKA_BOOTSTRAP,
            "group.id":           KAFKA_GROUP_ID,
            "auto.offset.reset":  "earliest",
            "enable.auto.commit": True,
        })

    def _process_news(self, message: dict) -> dict:
        """Analysiert einen News-Artikel und gibt das Ergebnis zurueck."""
        text      = message.get("headline", "") + " " + message.get("summary", "")
        symbol    = message.get("symbol", "UNKNOWN")
        sentiment = self.analyser.analyse(text)

        result = {
            "symbol":           symbol,
            "headline":         message.get("headline", ""),
            "sentiment_score":  sentiment["score"],
            "sentiment_signal": sentiment["signal"],
            "positive":         sentiment["positive"],
            "negative":         sentiment["negative"],
            "neutral":          sentiment["neutral"],
            "valid_time":       message.get("published_at", ""),
            "transaction_time": datetime.now(timezone.utc).isoformat(),
            "model":            MODEL_NAME,
        }

        log.info("sentiment_analysed",
                 symbol=symbol,
                 score=sentiment["score"],
                 signal=sentiment["signal"])

        return result

    def start(self):
        global is_ready
        self.consumer.subscribe(["news_stream"])
        is_ready = True
        log.info("service_ready", topic="news_stream")

        while self.running:
            msg = self.consumer.poll(timeout=1.0)

            if msg is None:
                continue

            if msg.error():
                log.error("kafka_consumer_error", error=str(msg.error()))
                continue

            try:
                data   = json.loads(msg.value().decode("utf-8"))
                result = self._process_news(data)

                self.processed += 1
                if self.processed % 10 == 0:
                    log.info("news_processed", count=self.processed)

            except Exception as e:
                log.error("processing_failed", error=str(e))

    def stop(self):
        global is_ready
        log.info("service_stopping")
        self.running = False
        is_ready     = False
        self.consumer.close()
        log.info("service_stopped")

# Entry Point

def main():
    service = FinBERTService()

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
