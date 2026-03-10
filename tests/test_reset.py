import asyncio
import queue
import threading
from unittest.mock import AsyncMock, MagicMock

from ocpp.v16.enums import ResetStatus

from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.bridge.message_queue import InMemoryBackend, MessageQueue
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.ocpp_adapter.adapter import Adapter


def _make_bridge(engine: Engine) -> Bridge:
    bridge = Bridge(engine=engine, url="ws://localhost:3000/CP_1")
    bridge._message_queue = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
    bridge.engine.session_started.subscribe(bridge.on_engine_session_started)
    bridge.engine.session_stopped.subscribe(bridge.on_engine_session_stopped)
    bridge.engine.connector_status_changed.subscribe(bridge.on_connector_status_change)
    return bridge


def _run_loop_until_idle(loop: asyncio.AbstractEventLoop) -> None:
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    sentinel = asyncio.run_coroutine_threadsafe(asyncio.sleep(0), loop)
    sentinel.result(timeout=5)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2)


def test_on_reset_accepts_soft_and_enqueues_reset() -> None:
    command_queue: queue.Queue = queue.Queue()
    adapter = Adapter("test_id", MagicMock(), command_queue=command_queue)
    received_types: list[str] = []

    def on_reset_requested(reset_type: str) -> None:
        received_types.append(reset_type)

    adapter.on_reset_requested.subscribe(on_reset_requested)

    result = asyncio.run(adapter.on_reset(type="Soft"))

    assert result.status == ResetStatus.accepted
    assert command_queue.get_nowait() == {"action": "RESET", "type": "Soft"}
    assert received_types == ["Soft"]


def test_on_reset_accepts_hard_and_enqueues_reset() -> None:
    command_queue: queue.Queue = queue.Queue()
    adapter = Adapter("test_id", MagicMock(), command_queue=command_queue)

    result = asyncio.run(adapter.on_reset(type="Hard"))

    assert result.status == ResetStatus.accepted
    assert command_queue.get_nowait() == {"action": "RESET", "type": "Hard"}


def test_on_reset_rejects_unknown_reset_type() -> None:
    adapter = Adapter("test_id", MagicMock(), command_queue=queue.Queue())

    result = asyncio.run(adapter.on_reset(type="ColdBoot"))

    assert result.status == ResetStatus.rejected


def test_reset_command_stops_active_session_with_soft_reset_reason() -> None:
    engine = Engine()
    engine.add_connector()
    engine.plug_in(1)
    engine.start_session(connector_id=1, transaction_id=123)

    engine.command_queue.put({"action": "RESET", "type": "Soft"})
    engine._process_commands()

    assert engine.session is None
    assert engine.last_stopped_session is not None
    assert engine.last_stopped_session["reason"] == "SoftReset"


def test_reset_command_stops_active_session_with_hard_reset_reason() -> None:
    engine = Engine()
    engine.add_connector()
    engine.plug_in(1)
    engine.start_session(connector_id=1, transaction_id=123)

    engine.command_queue.put({"action": "RESET", "type": "Hard"})
    engine._process_commands()

    assert engine.session is None
    assert engine.last_stopped_session is not None
    assert engine.last_stopped_session["reason"] == "HardReset"


def test_reset_command_clears_pending_remote_starts() -> None:
    engine = Engine()
    engine.add_connector()
    engine.command_queue.put(
        {
            "action": "START",
            "connector_id": 1,
            "transaction_id": 123,
            "id_tag": "TEST",
            "timeout": 10,
        }
    )
    engine._process_commands()

    assert 1 in engine._pending_remote_starts

    engine.command_queue.put({"action": "RESET", "type": "Soft"})
    engine._process_commands()

    assert engine._pending_remote_starts == {}


def test_reset_without_active_session_sends_boot_notification() -> None:
    engine = Engine()
    engine.add_connector()
    bridge = _make_bridge(engine)
    adapter = MagicMock()
    adapter.send_boot_notification = AsyncMock()
    adapter.send_status_notification = AsyncMock()
    bridge.runner.adapter = adapter
    loop = asyncio.new_event_loop()
    bridge.runner.loop = loop

    bridge.on_reset_requested("Soft")
    _run_loop_until_idle(loop)

    adapter.send_boot_notification.assert_awaited_once()
    loop.close()


def test_reset_boots_after_stop_transaction_for_active_session() -> None:
    engine = Engine()
    engine.add_connector()
    bridge = _make_bridge(engine)

    call_order: list[str] = []

    async def send_stop_transaction(**kwargs):
        call_order.append("stop")
        return MagicMock(id_tag_info={"status": "Accepted"})

    async def send_boot_notification():
        call_order.append("boot")
        return MagicMock(status="Accepted", interval=300)

    adapter = MagicMock()
    adapter.send_stop_transaction = AsyncMock(side_effect=send_stop_transaction)
    adapter.send_boot_notification = AsyncMock(side_effect=send_boot_notification)
    adapter.send_status_notification = AsyncMock()

    bridge.engine.plug_in(1)
    bridge.engine.start_session(connector_id=1, transaction_id=77)

    bridge.runner.adapter = adapter
    loop = asyncio.new_event_loop()
    bridge.runner.loop = loop
    bridge.on_reset_requested("Soft")
    bridge.engine.command_queue.put({"action": "RESET", "type": "Soft"})
    bridge.engine._process_commands()
    _run_loop_until_idle(loop)

    assert call_order == ["stop", "boot"]
    loop.close()
