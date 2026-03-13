import json
import os
import signal
import sys
import threading
from datetime import datetime, timezone
from collections import defaultdict

import pandas as pd
import pandas_ta as ta
import structlog
import uvicorn
from confluent_kafka import Consumer, KafkaException
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Konfiguration

load_dotenv()

KAFKA_BOOTSTRAP  = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_GROUP_ID   = os.getenv("KAFKA_GROUP_ID", "indicator-consumer-group")
RSI_PERIOD       = int(os.getenv("RSI_PERIOD", "14"))
MACD_FAST        = int(os.getenv("MACD_FAST", "12"))
MACD_SLOW        = int(os.getenv("MACD_SLOW", "26"))
MACD_SIGNAL      = int(os.getenv("MACD_SIGNAL", "9"))
BB_PERIOD        = int(os.getenv("BB_PERIOD", "20"))
BB_STD           = float(os.getenv("BB_STD", "2.0"))
MIN_BARS         = int(os.getenv("MIN_BARS", "30"))

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

# Indikator Berechnung

class IndicatorCalculator:
    def calculate(self, symbol: str, bars: list[dict]) -> dict | None:
        if len(bars) < MIN_BARS:
            return None

        df = pd.DataFrame(bars)
        df["close"]  = df["close"].astype(float)
        df["high"]   = df["high"].astype(float)
        df["low"]    = df["low"].astype(float)
        df["volume"] = df["volume"].astype(float)

        # DatetimeIndex wird von ta.vwap benoetigt
        df.index = pd.to_datetime(df["valid_time"], utc=True)

        rsi   = self._calculate_rsi(df)
        macd  = self._calculate_macd(df)
        bb    = self._calculate_bollinger_bands(df)
        vwap  = self._calculate_vwap(df)
        atr   = self._calculate_atr(df)
        pivot = self._calculate_pivot_points(df)

        return {
            "symbol":           symbol,
            "rsi":              rsi,
            "macd":             macd,
            "bollinger_bands":  bb,
            "vwap":             vwap,
            "atr":              atr,
            "pivot_points":     pivot,
            "signal":           self._aggregate_signal(rsi, macd, bb, vwap),
            "valid_time":       bars[-1]["valid_time"],
            "transaction_time": datetime.now(timezone.utc).isoformat(),
        }

    def _calculate_rsi(self, df: pd.DataFrame) -> dict:
        rsi_series = ta.rsi(df["close"], length=RSI_PERIOD)
        value = round(float(rsi_series.iloc[-1]), 2)

        if value > 70:
            signal = "OVERBOUGHT"
        elif value < 30:
            signal = "OVERSOLD"
        else:
            signal = "NEUTRAL"

        return {"value": value, "signal": signal}

    def _calculate_macd(self, df: pd.DataFrame) -> dict:
        macd_df = ta.macd(df["close"],
                          fast=MACD_FAST,
                          slow=MACD_SLOW,
                          signal=MACD_SIGNAL)

        # Spaltennamen: MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
        macd_col   = [c for c in macd_df.columns if c.startswith("MACD_")][0]
        hist_col   = [c for c in macd_df.columns if c.startswith("MACDh_")][0]
        signal_col = [c for c in macd_df.columns if c.startswith("MACDs_")][0]

        macd_val   = round(float(macd_df[macd_col].iloc[-1]), 4)
        hist_val   = round(float(macd_df[hist_col].iloc[-1]), 4)
        signal_val = round(float(macd_df[signal_col].iloc[-1]), 4)
        prev_hist  = round(float(macd_df[hist_col].iloc[-2]), 4)

        if hist_val > 0 and prev_hist <= 0:
            crossover = "BULLISH_CROSSOVER"
        elif hist_val < 0 and prev_hist >= 0:
            crossover = "BEARISH_CROSSOVER"
        elif hist_val > 0:
            crossover = "BULLISH"
        else:
            crossover = "BEARISH"

        return {
            "macd":      macd_val,
            "signal":    signal_val,
            "histogram": hist_val,
            "crossover": crossover,
        }

    def _calculate_bollinger_bands(self, df: pd.DataFrame) -> dict:
        bb_df = ta.bbands(df["close"], length=BB_PERIOD, std=BB_STD)

        upper_col = [c for c in bb_df.columns if c.startswith("BBU_")][0]
        mid_col   = [c for c in bb_df.columns if c.startswith("BBM_")][0]
        lower_col = [c for c in bb_df.columns if c.startswith("BBL_")][0]

        close = float(df["close"].iloc[-1])
        upper = round(float(bb_df[upper_col].iloc[-1]), 4)
        mid   = round(float(bb_df[mid_col].iloc[-1]), 4)
        lower = round(float(bb_df[lower_col].iloc[-1]), 4)
        width = round((upper - lower) / mid, 4)

        if close > upper:
            signal = "ABOVE_UPPER"
        elif close < lower:
            signal = "BELOW_LOWER"
        else:
            signal = "INSIDE"

        return {
            "upper":  upper,
            "middle": mid,
            "lower":  lower,
            "width":  width,
            "signal": signal,
        }

    def _calculate_vwap(self, df: pd.DataFrame) -> dict:
        vwap_series = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
        vwap_val    = round(float(vwap_series.iloc[-1]), 4)
        close       = float(df["close"].iloc[-1])
        deviation   = round((close - vwap_val) / vwap_val * 100, 4)

        return {
            "value":     vwap_val,
            "deviation": deviation,
            "signal":    "BELOW_VWAP" if close < vwap_val else "ABOVE_VWAP",
        }

    def _calculate_atr(self, df: pd.DataFrame) -> dict:
        atr_series = ta.atr(df["high"], df["low"], df["close"], length=14)
        value      = round(float(atr_series.iloc[-1]), 4)
        close      = float(df["close"].iloc[-1])
        pct        = round(value / close * 100, 4)

        return {"value": value, "percent": pct}

    def _calculate_pivot_points(self, df: pd.DataFrame) -> dict:
        prev  = df.iloc[-2]
        high  = float(prev["high"])
        low   = float(prev["low"])
        close = float(prev["close"])

        pivot = round((high + low + close) / 3, 4)
        r1    = round(2 * pivot - low, 4)
        r2    = round(pivot + (high - low), 4)
        s1    = round(2 * pivot - high, 4)
        s2    = round(pivot - (high - low), 4)

        return {"pivot": pivot, "r1": r1, "r2": r2, "s1": s1, "s2": s2}

    def _aggregate_signal(self, rsi: dict, macd: dict, bb: dict, vwap: dict) -> str:
        buy_votes  = 0
        sell_votes = 0

        if rsi["signal"] == "OVERSOLD":
            buy_votes += 1
        elif rsi["signal"] == "OVERBOUGHT":
            sell_votes += 1

        if macd["crossover"] in ("BULLISH_CROSSOVER", "BULLISH"):
            buy_votes += 1
        elif macd["crossover"] in ("BEARISH_CROSSOVER", "BEARISH"):
            sell_votes += 1

        if bb["signal"] == "BELOW_LOWER":
            buy_votes += 1
        elif bb["signal"] == "ABOVE_UPPER":
            sell_votes += 1

        if vwap["signal"] == "BELOW_VWAP":
            buy_votes += 1
        elif vwap["signal"] == "ABOVE_VWAP":
            sell_votes += 1

        if buy_votes >= 3:
            return "BUY"
        if sell_votes >= 3:
            return "SELL"
        return "HOLD"


# Indikator Service

class IndicatorService:
    def __init__(self):
        self.calculator = IndicatorCalculator()
        self.consumer   = self._create_consumer()
        self.bars       = defaultdict(list)
        self.running    = True
        self.processed  = 0

    def _create_consumer(self) -> Consumer:
        return Consumer({
            "bootstrap.servers":  KAFKA_BOOTSTRAP,
            "group.id":           KAFKA_GROUP_ID,
            "auto.offset.reset":  "earliest",
            "enable.auto.commit": True,
        })

    def start(self):
        global is_ready
        self.consumer.subscribe(["market_bars"])
        is_ready = True
        log.info("service_ready", topic="market_bars")

        while self.running:
            msg = self.consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                log.error("kafka_error", error=str(msg.error()))
                continue
            try:
                bar    = json.loads(msg.value().decode("utf-8"))
                symbol = bar["symbol"]
                self.bars[symbol].append(bar)
                if len(self.bars[symbol]) > 100:
                    self.bars[symbol] = self.bars[symbol][-100:]
                result = self.calculator.calculate(symbol, self.bars[symbol])
                if result:
                    log.info("indicators_calculated",
                             symbol=symbol,
                             rsi=result["rsi"]["value"],
                             signal=result["signal"])
                self.processed += 1
            except Exception as e:
                log.error("processing_failed", error=str(e))

    def stop(self):
        global is_ready
        self.running = False
        is_ready     = False
        self.consumer.close()
        log.info("service_stopped")


# Entry Point

def main():
    service = IndicatorService()

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
