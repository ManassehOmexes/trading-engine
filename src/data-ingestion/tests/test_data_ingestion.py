import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from main import DataIngestionService, delivery_report, app

import main

# pytest-asyncio Konfiguration
pytestmark = pytest.mark.asyncio

client = TestClient(app)

# Health Check Tests

def test_health_endpoint_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_ready_endpoint_returns_503_when_not_ready():
    main.is_ready = False
    response = client.get("/ready")
    assert response.status_code == 503

def test_ready_endpoint_returns_200_when_ready():
    main.is_ready = True
    response = client.get("/ready")
    assert response.status_code == 200
    main.is_ready = False


# Delivery Report Tests

def test_delivery_report_logs_error_on_failure():
    mock_msg = MagicMock()
    mock_msg.topic.return_value = "market_ticks"
    with patch("main.log") as mock_log:
        delivery_report(err="some error", msg=mock_msg)
        mock_log.error.assert_called_once()

def test_delivery_report_logs_debug_on_success():
    mock_msg = MagicMock()
    mock_msg.topic.return_value = "market_ticks"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 42
    with patch("main.log") as mock_log:
        delivery_report(err=None, msg=mock_msg)
        mock_log.debug.assert_called_once()


# Data Ingestion Service Tests

@patch("main.Producer")
@patch("main.StockDataStream")
def test_service_initializes_correctly(mock_stream, mock_producer):
    service = DataIngestionService()
    assert service.tick_count == 0
    mock_producer.assert_called_once()
    mock_stream.assert_called_once()

@patch("main.Producer")
@patch("main.StockDataStream")
async def test_handle_trade_publishes_to_kafka(mock_stream, mock_producer):
    service = DataIngestionService()

    mock_trade = MagicMock()
    mock_trade.symbol = "AAPL"
    mock_trade.price = 182.50
    mock_trade.size = 100
    mock_trade.exchange = "NYSE"
    mock_trade.timestamp = datetime(2026, 3, 10, 9, 30, 0, tzinfo=timezone.utc)

    with patch.object(service, "_publish") as mock_publish:
        await service.handle_trade(mock_trade)
        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        assert call_args.kwargs["topic"] == "market_ticks"
        assert call_args.kwargs["key"] == "AAPL"

@patch("main.Producer")
@patch("main.StockDataStream")
async def test_handle_trade_includes_bitemporal_timestamps(mock_stream, mock_producer):
    service = DataIngestionService()

    mock_trade = MagicMock()
    mock_trade.symbol = "AAPL"
    mock_trade.price = 182.50
    mock_trade.size = 100
    mock_trade.exchange = "NYSE"
    mock_trade.timestamp = datetime(2026, 3, 10, 9, 30, 0, tzinfo=timezone.utc)

    published_data = {}

    def capture_publish(topic, key, data):
        published_data.update(data)

    with patch.object(service, "_publish", side_effect=capture_publish):
        await service.handle_trade(mock_trade)

    assert "valid_time" in published_data
    assert "transaction_time" in published_data
    assert published_data["valid_time"] == "2026-03-10T09:30:00+00:00"

@patch("main.Producer")
@patch("main.StockDataStream")
async def test_handle_bar_publishes_to_correct_topic(mock_stream, mock_producer):
    service = DataIngestionService()

    mock_bar = MagicMock()
    mock_bar.symbol = "MSFT"
    mock_bar.open = 380.0
    mock_bar.high = 382.0
    mock_bar.low = 379.5
    mock_bar.close = 381.0
    mock_bar.volume = 5000
    mock_bar.vwap = 380.5
    mock_bar.timestamp = datetime(2026, 3, 10, 9, 31, 0, tzinfo=timezone.utc)

    with patch.object(service, "_publish") as mock_publish:
        await service.handle_bar(mock_bar)
        call_args = mock_publish.call_args
        assert call_args.kwargs["topic"] == "market_bars"
        assert call_args.kwargs["key"] == "MSFT"

@patch("main.Producer")
@patch("main.StockDataStream")
def test_tick_counter_increments(mock_stream, mock_producer):
    service = DataIngestionService()
    assert service.tick_count == 0
