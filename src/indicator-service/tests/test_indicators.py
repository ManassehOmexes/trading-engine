import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient
from main import IndicatorCalculator, app

import main

client = TestClient(app)

def make_bars(n: int = 50) -> list[dict]:
    np.random.seed(42)
    prices = 180.0 + np.cumsum(np.random.randn(n) * 0.5)
    base   = datetime(2026, 3, 10, 9, 0, 0, tzinfo=timezone.utc)
    bars   = []
    for i, price in enumerate(prices):
        bars.append({
            "symbol":           "AAPL",
            "open":             price - 0.1,
            "high":             price + 0.5,
            "low":              price - 0.5,
            "close":            price,
            "volume":           100000 + i * 1000,
            "vwap":             price,
            "valid_time":       (base + timedelta(minutes=i)).isoformat(),
            "transaction_time": (base + timedelta(minutes=i, seconds=1)).isoformat(),
        })
    return bars

# Health Check Tests

def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200

def test_ready_returns_503_when_not_ready():
    main.is_ready = False
    response = client.get("/ready")
    assert response.status_code == 503

# Indikator Tests

def test_returns_none_when_insufficient_bars():
    calc   = IndicatorCalculator()
    result = calc.calculate("AAPL", make_bars(10))
    assert result is None

def test_returns_result_with_sufficient_bars():
    calc   = IndicatorCalculator()
    result = calc.calculate("AAPL", make_bars(50))
    assert result is not None
    assert result["symbol"] == "AAPL"

def test_rsi_value_is_between_0_and_100():
    calc   = IndicatorCalculator()
    result = calc.calculate("AAPL", make_bars(50))
    assert 0 <= result["rsi"]["value"] <= 100

def test_rsi_signal_is_valid():
    calc   = IndicatorCalculator()
    result = calc.calculate("AAPL", make_bars(50))
    assert result["rsi"]["signal"] in ("OVERBOUGHT", "OVERSOLD", "NEUTRAL")

def test_macd_crossover_is_valid():
    calc   = IndicatorCalculator()
    result = calc.calculate("AAPL", make_bars(50))
    assert result["macd"]["crossover"] in (
        "BULLISH_CROSSOVER", "BEARISH_CROSSOVER", "BULLISH", "BEARISH"
    )

def test_bollinger_bands_signal_is_valid():
    calc   = IndicatorCalculator()
    result = calc.calculate("AAPL", make_bars(50))
    assert result["bollinger_bands"]["signal"] in (
        "ABOVE_UPPER", "BELOW_LOWER", "INSIDE"
    )

def test_vwap_signal_is_valid():
    calc   = IndicatorCalculator()
    result = calc.calculate("AAPL", make_bars(50))
    assert result["vwap"]["signal"] in ("ABOVE_VWAP", "BELOW_VWAP")

def test_atr_is_positive():
    calc   = IndicatorCalculator()
    result = calc.calculate("AAPL", make_bars(50))
    assert result["atr"]["value"] > 0
    assert result["atr"]["percent"] > 0

def test_pivot_points_structure():
    calc   = IndicatorCalculator()
    result = calc.calculate("AAPL", make_bars(50))
    pp     = result["pivot_points"]
    assert "pivot" in pp
    assert "r1" in pp and "r2" in pp
    assert "s1" in pp and "s2" in pp
    assert pp["r1"] > pp["pivot"] > pp["s1"]

def test_aggregate_signal_is_valid():
    calc   = IndicatorCalculator()
    result = calc.calculate("AAPL", make_bars(50))
    assert result["signal"] in ("BUY", "SELL", "HOLD")

def test_result_has_bitemporal_timestamps():
    calc   = IndicatorCalculator()
    result = calc.calculate("AAPL", make_bars(50))
    assert "valid_time" in result
    assert "transaction_time" in result
