import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

from chargeghost_evse.bridge.message_queue import InMemoryBackend, MessageQueue
from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter


def _make_adapter(**overrides) -> V201Adapter:
    mock_conn = MagicMock()
    mock_conn.recv = AsyncMock()
    mock_conn.send = AsyncMock()
    kwargs = {
        "id": "CP_1",
        "connection": mock_conn,
        "command_queue": MagicMock(),
        "charge_point_model": "ChargeGhostV2",
        "charge_point_vendor": "ChargeGhost",
    }
    kwargs.update(overrides)
    return V201Adapter(**kwargs)


class TestGetTransactionStatusAcceptedMessagesWaiting:
    def test_messages_waiting_true_when_queue_has_messages(self):
        adapter = _make_adapter()
        adapter.call = MagicMock()
        tx_id = adapter.transaction_manager.begin_transaction(1)

        queue = MessageQueue(backend=InMemoryBackend())
        queue.enqueue("TransactionEventEnded", {"transaction_id": tx_id})
        adapter.message_queue = queue

        result = asyncio.run(adapter.on_get_transaction_status(transaction_id=tx_id))

        assert result.messages_in_queue is True
        assert result.ongoing_indicator is True


class TestGetTransactionStatusAcceptedNoMessages:
    def test_messages_waiting_false_when_queue_empty(self):
        adapter = _make_adapter()
        adapter.call = MagicMock()
        tx_id = adapter.transaction_manager.begin_transaction(1)

        queue = MessageQueue(backend=InMemoryBackend())
        adapter.message_queue = queue

        result = asyncio.run(adapter.on_get_transaction_status(transaction_id=tx_id))

        assert result.messages_in_queue is False
        assert result.ongoing_indicator is True


class TestGetTransactionStatusNotFound:
    def test_unknown_transaction_id(self):
        adapter = _make_adapter()
        adapter.call = MagicMock()

        queue = MessageQueue(backend=InMemoryBackend())
        adapter.message_queue = queue

        result = asyncio.run(
            adapter.on_get_transaction_status(transaction_id="nonexistent-tx")
        )

        assert result.messages_in_queue is False


class TestGetTransactionStatusNoQueue:
    def test_no_message_queue_returns_false(self):
        adapter = _make_adapter()
        adapter.call = MagicMock()
        tx_id = adapter.transaction_manager.begin_transaction(1)

        adapter.message_queue = None

        result = asyncio.run(adapter.on_get_transaction_status(transaction_id=tx_id))

        assert result.messages_in_queue is False
        assert result.ongoing_indicator is True


class TestGetTransactionStatusNoTransactionId:
    def test_no_transaction_id_with_active_transactions(self):
        adapter = _make_adapter()
        adapter.call = MagicMock()
        adapter.transaction_manager.begin_transaction(1)

        queue = MessageQueue(backend=InMemoryBackend())
        queue.enqueue("TransactionEventEnded", {"transaction_id": "tx1"})
        adapter.message_queue = queue

        result = asyncio.run(adapter.on_get_transaction_status())

        assert result.messages_in_queue is True
        assert result.ongoing_indicator is True

    def test_no_transaction_id_with_no_active_transactions(self):
        adapter = _make_adapter()
        adapter.call = MagicMock()

        queue = MessageQueue(backend=InMemoryBackend())
        adapter.message_queue = queue

        result = asyncio.run(adapter.on_get_transaction_status())

        assert result.messages_in_queue is False
        assert result.ongoing_indicator is None


class TestGetTransactionStatusLogging:
    def test_logs_warning_for_unknown_transaction(self, caplog):
        adapter = _make_adapter()
        adapter.call = MagicMock()
        adapter.message_queue = None

        with caplog.at_level(logging.WARNING, logger="chargeghost.ocpp"):
            asyncio.run(adapter.on_get_transaction_status(transaction_id="unknown"))

        assert any("unknown transaction" in r.message for r in caplog.records)

    def test_logs_request(self, caplog):
        adapter = _make_adapter()
        adapter.call = MagicMock()
        tx_id = adapter.transaction_manager.begin_transaction(1)
        adapter.message_queue = None

        with caplog.at_level(logging.INFO, logger="chargeghost.ocpp"):
            asyncio.run(adapter.on_get_transaction_status(transaction_id=tx_id))

        assert any("GetTransactionStatus" in r.message for r in caplog.records)
