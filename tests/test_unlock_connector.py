import asyncio
import queue
from unittest.mock import AsyncMock, MagicMock

from ocpp.v16.enums import UnlockStatus

from chargeghost_evse.ocpp_adapter.adapter import Adapter


def _make_adapter(command_queue: queue.Queue) -> Adapter:
    mock_conn = MagicMock()
    mock_conn.recv = AsyncMock()
    mock_conn.send = AsyncMock()
    return Adapter("CP_1", mock_conn, command_queue=command_queue)


def test_unlock_connector_targets_requested_connector_without_clearing_tx() -> None:
    command_queue: queue.Queue = queue.Queue()
    adapter = _make_adapter(command_queue)
    adapter.known_connector_ids = [1, 2]
    adapter.set_active_transaction(1, 101)
    adapter.set_active_transaction(2, 202)

    result = asyncio.run(adapter.on_unlock_connector(connector_id=2))

    assert result.status == UnlockStatus.unlocked
    command = command_queue.get_nowait()
    assert command == {
        "action": "STOP",
        "connector_id": 2,
        "transaction_id": 202,
        "reason": "UnlockCommand",
    }
    assert adapter.get_active_transaction_id(1) == 101
    assert adapter.get_active_transaction_id(2) == 202
