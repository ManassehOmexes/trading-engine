import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from main import OrderExecutor, app
import main

client = TestClient(app)

def make_decision(action="BUY", quantity=10, price=180.0) -> dict:
    return {
        "symbol":           "AAPL",
        "action":           action,
        "price":            price,
        "quantity":         quantity,
        "stop_loss":        177.0,
        "take_profit":      186.0,
        "position_value":   1800.0,
        "risk_amount":      30.0,
        "valid_time":       "2026-03-10T09:30:00+00:00",
        "transaction_time": "2026-03-10T09:30:01+00:00",
    }

# Health Check Tests

def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200

def test_ready_returns_503_when_not_ready():
    main.is_ready = False
    response = client.get("/ready")
    assert response.status_code == 503

# Order Executor Tests

@patch("main.TradingClient")
def test_buy_order_is_submitted(mock_client_class):
    mock_order        = MagicMock()
    mock_order.id     = "test-order-123"
    mock_client       = MagicMock()
    mock_client.submit_order.return_value = mock_order
    mock_client_class.return_value        = mock_client

    executor = OrderExecutor()
    result   = executor.execute(make_decision(action="BUY"))

    assert result["status"]  == "submitted"
    assert result["order_id"] == "test-order-123"
    assert result["action"]  == "BUY"
    mock_client.submit_order.assert_called_once()

@patch("main.TradingClient")
def test_sell_order_is_submitted(mock_client_class):
    mock_order        = MagicMock()
    mock_order.id     = "test-order-456"
    mock_client       = MagicMock()
    mock_client.submit_order.return_value = mock_order
    mock_client_class.return_value        = mock_client

    executor = OrderExecutor()
    result   = executor.execute(make_decision(action="SELL"))

    assert result["status"] == "submitted"
    assert result["action"] == "SELL"

@patch("main.TradingClient")
def test_failed_order_returns_failed_status(mock_client_class):
    mock_client = MagicMock()
    mock_client.submit_order.side_effect = Exception("Insufficient buying power")
    mock_client_class.return_value       = mock_client

    executor = OrderExecutor()
    result   = executor.execute(make_decision())

    assert result["status"] == "failed"
    assert result["order_id"] is None
    assert "Insufficient buying power" in result["error"]

@patch("main.TradingClient")
def test_result_includes_stop_loss_and_take_profit(mock_client_class):
    mock_order        = MagicMock()
    mock_order.id     = "test-order-789"
    mock_client       = MagicMock()
    mock_client.submit_order.return_value = mock_order
    mock_client_class.return_value        = mock_client

    executor = OrderExecutor()
    decision = make_decision()
    result   = executor.execute(decision)

    assert result["stop_loss"]   == decision["stop_loss"]
    assert result["take_profit"] == decision["take_profit"]

@patch("main.TradingClient")
def test_result_has_transaction_time(mock_client_class):
    mock_order        = MagicMock()
    mock_order.id     = "test-order-999"
    mock_client       = MagicMock()
    mock_client.submit_order.return_value = mock_order
    mock_client_class.return_value        = mock_client

    executor = OrderExecutor()
    result   = executor.execute(make_decision())

    assert "transaction_time" in result

@patch("main.TradingClient")
def test_paper_trading_is_enabled_by_default(mock_client_class):
    OrderExecutor()
    call_kwargs = mock_client_class.call_args.kwargs
    assert call_kwargs["paper"] is True
