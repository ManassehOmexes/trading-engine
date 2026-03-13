import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import RiskCalculator, TradeSignal, app
import main

client = TestClient(app)

def make_signal(action="BUY",
                indicator_signal="BUY",
                sentiment_signal="BUY",
                sentiment_score=0.6,
                price=180.0,
                atr=1.5) -> TradeSignal:
    return TradeSignal(
        symbol="AAPL",
        action=action,
        price=price,
        atr=atr,
        indicator_signal=indicator_signal,
        sentiment_signal=sentiment_signal,
        sentiment_score=sentiment_score,
        valid_time="2026-03-10T09:30:00+00:00",
    )

# Health Check Tests

def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200

def test_ready_returns_503_when_not_ready():
    main.is_ready = False
    response = client.get("/ready")
    assert response.status_code == 503

# Kelly Criterion Tests

def test_half_kelly_is_positive_with_valid_inputs():
    calc   = RiskCalculator()
    result = calc._half_kelly(win_rate=0.55, win_loss_ratio=1.5)
    assert result > 0

def test_half_kelly_is_zero_when_no_edge():
    calc   = RiskCalculator()
    result = calc._half_kelly(win_rate=0.3, win_loss_ratio=1.0)
    assert result == 0.0

def test_half_kelly_does_not_exceed_max_position():
    calc   = RiskCalculator()
    kelly  = calc._half_kelly(win_rate=0.9, win_loss_ratio=5.0)
    import main
    assert min(kelly, main.MAX_POSITION_PCT) <= main.MAX_POSITION_PCT

# Stop-Loss Tests

def test_stop_loss_is_below_entry_for_buy():
    calc   = RiskCalculator()
    signal = make_signal(action="BUY", price=180.0, atr=1.5)
    stop   = calc._calculate_stop_loss(signal)
    assert stop < signal.price

def test_stop_loss_is_above_entry_for_sell():
    calc   = RiskCalculator()
    signal = make_signal(action="SELL",
                         indicator_signal="SELL",
                         sentiment_signal="SELL",
                         sentiment_score=-0.6,
                         price=180.0,
                         atr=1.5)
    stop   = calc._calculate_stop_loss(signal)
    assert stop > signal.price

def test_stop_loss_distance_equals_atr_times_multiplier():
    calc      = RiskCalculator()
    signal    = make_signal(price=180.0, atr=2.0)
    stop      = calc._calculate_stop_loss(signal)
    import main
    expected  = round(180.0 - (2.0 * main.ATR_MULTIPLIER), 4)
    assert stop == expected

# Signal Agreement Tests

def test_rejects_when_indicator_and_sentiment_disagree():
    calc   = RiskCalculator()
    signal = make_signal(action="BUY",
                         indicator_signal="BUY",
                         sentiment_signal="SELL",
                         sentiment_score=-0.5)
    result = calc.evaluate(signal)
    assert result.approved is False

def test_rejects_when_sentiment_score_too_low():
    calc   = RiskCalculator()
    signal = make_signal(action="BUY",
                         indicator_signal="BUY",
                         sentiment_signal="BUY",
                         sentiment_score=0.1)  # Unter 0.3
    result = calc.evaluate(signal)
    assert result.approved is False

# Approval Tests

def test_approves_valid_buy_signal():
    calc   = RiskCalculator()
    signal = make_signal()
    result = calc.evaluate(signal)
    assert result.approved is True
    assert result.quantity > 0
    assert result.stop_loss < signal.price
    assert result.take_profit > signal.price

def test_take_profit_is_2x_risk():
    calc       = RiskCalculator()
    signal     = make_signal(price=180.0, atr=1.5)
    result     = calc.evaluate(signal)
    risk       = result.price - result.stop_loss
    reward     = result.take_profit - result.price
    assert round(reward / risk, 1) == 2.0

def test_position_value_does_not_exceed_portfolio_limit():
    calc   = RiskCalculator()
    signal = make_signal(price=180.0, atr=0.1)  # Kleiner ATR = grosse Position
    result = calc.evaluate(signal)
    import main
    assert result.position_value <= main.TOTAL_CAPITAL * main.MAX_PORTFOLIO_RISK
