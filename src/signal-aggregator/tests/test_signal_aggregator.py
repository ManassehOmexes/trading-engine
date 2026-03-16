import pytest
import time
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import SignalAggregator, SignalCache, app
import main

client = TestClient(app)

def make_indicator(symbol="AAPL", signal="BUY", price=180.0, atr=1.5) -> dict:
    return {
        "symbol":  symbol,
        "signal":  signal,
        "atr":     {"value": atr},
        "vwap":    {"value": price},
        "valid_time": "2026-03-10T09:30:00+00:00",
    }

def make_sentiment(symbol="AAPL", signal="BUY", score=0.6) -> dict:
    return {
        "symbol":           symbol,
        "sentiment_signal": signal,
        "sentiment_score":  score,
    }

# Health Check Tests

def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200

def test_ready_returns_503_when_not_ready():
    main.is_ready = False
    response = client.get("/ready")
    assert response.status_code == 503

# Signal Cache Tests

def test_cache_stores_and_retrieves_indicator():
    cache = SignalCache()
    cache.store_indicator("AAPL", make_indicator())
    ind, sent = cache.get_pair("AAPL")
    assert ind is not None
    assert sent is None

def test_cache_stores_and_retrieves_both():
    cache = SignalCache()
    cache.store_indicator("AAPL", make_indicator())
    cache.store_sentiment("AAPL", make_sentiment())
    ind, sent = cache.get_pair("AAPL")
    assert ind is not None
    assert sent is not None

def test_cache_clear_removes_both():
    cache = SignalCache()
    cache.store_indicator("AAPL", make_indicator())
    cache.store_sentiment("AAPL", make_sentiment())
    cache.clear("AAPL")
    ind, sent = cache.get_pair("AAPL")
    assert ind is None
    assert sent is None

def test_cache_expiry():
    with patch("main.SIGNAL_TTL_SECONDS", 0):
        cache = SignalCache()
        cache.store_indicator("AAPL", make_indicator())
        time.sleep(0.01)
        ind, _ = cache.get_pair("AAPL")
        assert ind is None

# Aggregation Tests

def test_returns_none_when_only_indicator_present():
    agg = SignalAggregator()
    agg.cache.store_indicator("AAPL", make_indicator())
    result = agg.aggregate("AAPL")
    assert result is None

def test_returns_none_when_only_sentiment_present():
    agg = SignalAggregator()
    agg.cache.store_sentiment("AAPL", make_sentiment())
    result = agg.aggregate("AAPL")
    assert result is None

def test_returns_none_when_signals_disagree():
    agg = SignalAggregator()
    agg.cache.store_indicator("AAPL", make_indicator(signal="BUY"))
    agg.cache.store_sentiment("AAPL", make_sentiment(signal="SELL", score=-0.6))
    result = agg.aggregate("AAPL")
    assert result is None

def test_returns_none_when_both_hold():
    agg = SignalAggregator()
    agg.cache.store_indicator("AAPL", make_indicator(signal="HOLD"))
    agg.cache.store_sentiment("AAPL", make_sentiment(signal="HOLD", score=0.1))
    result = agg.aggregate("AAPL")
    assert result is None

def test_aggregates_matching_buy_signals():
    agg = SignalAggregator()
    agg.cache.store_indicator("AAPL", make_indicator(signal="BUY"))
    agg.cache.store_sentiment("AAPL", make_sentiment(signal="BUY", score=0.6))
    result = agg.aggregate("AAPL")
    assert result is not None
    assert result["action"] == "BUY"
    assert result["symbol"] == "AAPL"

def test_aggregates_matching_sell_signals():
    agg = SignalAggregator()
    agg.cache.store_indicator("AAPL", make_indicator(signal="SELL", price=180.0))
    agg.cache.store_sentiment("AAPL", make_sentiment(signal="SELL", score=-0.6))
    result = agg.aggregate("AAPL")
    assert result is not None
    assert result["action"] == "SELL"

def test_cache_cleared_after_aggregation():
    agg = SignalAggregator()
    agg.cache.store_indicator("AAPL", make_indicator(signal="BUY"))
    agg.cache.store_sentiment("AAPL", make_sentiment(signal="BUY"))
    agg.aggregate("AAPL")
    ind, sent = agg.cache.get_pair("AAPL")
    assert ind is None
    assert sent is None

def test_result_has_bitemporal_timestamps():
    agg = SignalAggregator()
    agg.cache.store_indicator("AAPL", make_indicator(signal="BUY"))
    agg.cache.store_sentiment("AAPL", make_sentiment(signal="BUY"))
    result = agg.aggregate("AAPL")
    assert "valid_time" in result
    assert "transaction_time" in result
