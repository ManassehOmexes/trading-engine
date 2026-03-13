import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from main import SentimentAnalyser, FinBERTService, app

import main

client = TestClient(app)

# Health Check Tests

def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200

def test_ready_returns_503_when_not_ready():
    main.is_ready = False
    response = client.get("/ready")
    assert response.status_code == 503

def test_ready_returns_200_when_ready():
    main.is_ready = True
    response = client.get("/ready")
    assert response.status_code == 200
    main.is_ready = False

# Sentiment Score Tests

@patch("main.pipeline")
def test_positive_news_returns_buy_signal(mock_pipeline):
    mock_pipeline.return_value = lambda text, **kwargs: [[
        {"label": "positive", "score": 0.85},
        {"label": "negative", "score": 0.05},
        {"label": "neutral",  "score": 0.10},
    ]]
    analyser = SentimentAnalyser()
    result   = analyser.analyse("Apple reports record earnings")
    assert result["signal"] == "BUY"
    assert result["score"] > 0.3

@patch("main.pipeline")
def test_negative_news_returns_sell_signal(mock_pipeline):
    mock_pipeline.return_value = lambda text, **kwargs: [[
        {"label": "positive", "score": 0.05},
        {"label": "negative", "score": 0.85},
        {"label": "neutral",  "score": 0.10},
    ]]
    analyser = SentimentAnalyser()
    result   = analyser.analyse("Fed raises rates unexpectedly")
    assert result["signal"] == "SELL"
    assert result["score"] < -0.3

@patch("main.pipeline")
def test_neutral_news_returns_hold_signal(mock_pipeline):
    mock_pipeline.return_value = lambda text, **kwargs: [[
        {"label": "positive", "score": 0.20},
        {"label": "negative", "score": 0.15},
        {"label": "neutral",  "score": 0.65},
    ]]
    analyser = SentimentAnalyser()
    result   = analyser.analyse("Company releases quarterly report")
    assert result["signal"] == "HOLD"
    assert -0.3 <= result["score"] <= 0.3

@patch("main.pipeline")
def test_score_range_is_between_minus_one_and_plus_one(mock_pipeline):
    mock_pipeline.return_value = lambda text, **kwargs: [[
        {"label": "positive", "score": 1.0},
        {"label": "negative", "score": 0.0},
        {"label": "neutral",  "score": 0.0},
    ]]
    analyser = SentimentAnalyser()
    result   = analyser.analyse("Extremely positive news")
    assert -1.0 <= result["score"] <= 1.0

@patch("main.pipeline")
def test_score_calculation_is_positive_minus_negative(mock_pipeline):
    mock_pipeline.return_value = lambda text, **kwargs: [[
        {"label": "positive", "score": 0.7},
        {"label": "negative", "score": 0.2},
        {"label": "neutral",  "score": 0.1},
    ]]
    analyser = SentimentAnalyser()
    result   = analyser.analyse("Some news text")
    expected = round(0.7 - 0.2, 4)
    assert result["score"] == expected

@patch("main.pipeline")
def test_process_news_includes_bitemporal_timestamps(mock_pipeline):
    mock_pipeline.return_value = lambda text, **kwargs: [[
        {"label": "positive", "score": 0.6},
        {"label": "negative", "score": 0.2},
        {"label": "neutral",  "score": 0.2},
    ]]
    with patch("main.Consumer"):
        service = FinBERTService()

    message = {
        "symbol":       "AAPL",
        "headline":     "Apple reports strong quarter",
        "summary":      "Revenue beats expectations",
        "published_at": "2026-03-10T09:30:00+00:00",
    }

    result = service._process_news(message)
    assert "valid_time" in result
    assert "transaction_time" in result
    assert result["symbol"] == "AAPL"
    assert result["valid_time"] == "2026-03-10T09:30:00+00:00"
