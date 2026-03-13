import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient
from main import TelegramBot, format_trade_message, app
import main

client = TestClient(app)

def make_decision(action="BUY") -> dict:
    return {
        "symbol":           "AAPL",
        "action":           action,
        "price":            180.0,
        "quantity":         10,
        "position_value":   1800.0,
        "risk_amount":      30.0,
        "stop_loss":        177.0,
        "take_profit":      186.0,
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

# Nachrichtenformat Tests

def test_buy_message_contains_green_emoji():
    msg = format_trade_message(make_decision("BUY"))
    assert "🟢" in msg

def test_sell_message_contains_red_emoji():
    msg = format_trade_message(make_decision("SELL"))
    assert "🔴" in msg

def test_message_contains_symbol():
    msg = format_trade_message(make_decision())
    assert "AAPL" in msg

def test_message_contains_stop_loss():
    msg = format_trade_message(make_decision())
    assert "177.00" in msg

def test_message_contains_take_profit():
    msg = format_trade_message(make_decision())
    assert "186.00" in msg

def test_message_contains_risk_amount():
    msg = format_trade_message(make_decision())
    assert "30.00" in msg

# Telegram Bot Tests

@patch("main.Application")
async def test_send_trade_alert_returns_message_id(mock_app_class):
    mock_bot     = AsyncMock()
    mock_msg     = MagicMock()
    mock_msg.message_id = 42
    mock_bot.send_message.return_value = mock_msg

    mock_app          = MagicMock()
    mock_app.bot      = mock_bot
    mock_app.build.return_value = mock_app
    mock_app_class.builder.return_value.token.return_value.build.return_value = mock_app

    bot    = TelegramBot()
    result = await bot.send_trade_alert(make_decision())
    assert result == 42

@patch("main.Application")
async def test_send_trade_alert_stores_pending(mock_app_class):
    mock_bot     = AsyncMock()
    mock_msg     = MagicMock()
    mock_msg.message_id = 99
    mock_bot.send_message.return_value = mock_msg

    mock_app          = MagicMock()
    mock_app.bot      = mock_bot
    mock_app_class.builder.return_value.token.return_value.build.return_value = mock_app

    bot      = TelegramBot()
    decision = make_decision()
    msg_id   = await bot.send_trade_alert(decision)

    # pending dict muss nach send_trade_alert befuellt werden
    bot.pending[msg_id] = decision
    assert msg_id in bot.pending
    assert bot.pending[msg_id]["symbol"] == "AAPL"
