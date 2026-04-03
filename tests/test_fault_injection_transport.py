import asyncio
import logging
import threading
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chargeghost_evse.bridge.bridge import AsyncRunner, Bridge
from chargeghost_evse.bridge.message_queue import InMemoryBackend, MessageQueue
from chargeghost_evse.devtools.fault_manager import FaultManager
from chargeghost_evse.devtools.fault_models import FaultConfig


class _MockStatus:
    def __init__(self, value: str) -> None:
        self.value = value


class _MockConnector:
    def __init__(self, connector_id: int, status: str = "Available") -> None:
        self.id = connector_id
        self.voltage: float = 230.0
        self.phase: int = 1
        self.status = _MockStatus(status)


class _MockEngine:
    def __init__(self, connector_statuses: Optional[list[str]] = None) -> None:
        self.get_limit = None
        self.session = MagicMock(connector_id=1, transaction_id=99)
        self._sessions = {1: self.session}
        self._energy_meters = {
            1: MagicMock(get_meter_reading=MagicMock(return_value=12.34))
        }
        statuses = connector_statuses or ["Available"]
        self._connectors = [
            _MockConnector(index + 1, status=status)
            for index, status in enumerate(statuses)
        ]

    def get_connector(self, connector_id: int):
        for connector in self._connectors:
            if connector.id == connector_id:
                return connector
        return None

    def get_session(self, connector_id: int):
        return self._sessions.get(connector_id)

    def get_energy_meter(self, connector_id: int):
        return self._energy_meters.get(connector_id)

    @property
    def connectors(self):
        return self._connectors

    def set_connector_availability(
        self, connector_id: int, availability_type: str
    ) -> str:
        return "accepted"


class _MockAdapter:
    def __init__(self) -> None:
        self.get_connector_info = None
        self.get_connector_status = None
        self.get_meter_snapshot = None
        self.charging_profile_manager = None
        self.known_connector_ids = []
        self.set_connector_availability = None
        self.reserve_connector = None
        self.cancel_reservation = None
        self.send_status_notification = AsyncMock()
        self.send_meter_values = AsyncMock()
        self.send_heartbeat = AsyncMock()
        self.heartbeat_interval = 300
        self.registration_status = "Accepted"
        self.on_registration_accepted = MagicMock()
        self.on_registration_accepted.subscribe = MagicMock()
        self.on_reset_requested = MagicMock()
        self.on_reset_requested.subscribe = MagicMock()
        self.start = AsyncMock()
        self.send_boot_notification = AsyncMock()


class _MockRunner:
    def __init__(self) -> None:
        self.adapter = None
        self._connected = False
        self.loop = None
        self.logger = logging.getLogger("chargeghost.bridge")
        self._fault_manager = None

    @property
    def is_connected(self) -> bool:
        return self._connected and self.adapter is not None


class _AsyncCtxMgr:
    def __init__(self, ws: MagicMock) -> None:
        self._ws = ws

    async def __aenter__(self):
        return self._ws

    async def __aexit__(self, *args):
        pass


def _make_bridge(
    engine: _MockEngine,
    runner: _MockRunner,
    fault_manager: Optional[FaultManager] = None,
) -> Bridge:
    bridge = Bridge.__new__(Bridge)
    bridge.engine = engine
    bridge.runner = runner
    bridge._shutdown_event = threading.Event()
    bridge._message_queue = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
    bridge._fault_manager = fault_manager
    return bridge


@pytest.mark.asyncio
async def test_forced_disconnect_fault_marks_runner_disconnected():
    fm = FaultManager()
    fm.enable("forced_disconnect")

    runner = AsyncRunner(
        charge_point_id="CP_1",
        url="ws://localhost:3000",
        command_queue=MagicMock(),
        fault_manager=fm,
    )
    runner._shutdown_event = asyncio.Event()

    mock_adapter = _MockAdapter()
    runner._create_adapter = MagicMock(return_value=mock_adapter)

    async def set_shutdown():
        await asyncio.sleep(0.1)
        runner._shutdown_event.set()

    asyncio.create_task(set_shutdown())

    with patch("chargeghost_evse.bridge.bridge.websockets.connect") as mock_connect:
        mock_ws = MagicMock()
        mock_connect.return_value = _AsyncCtxMgr(mock_ws)
        await runner._run_adapter()

    assert not runner._connected
    assert not fm.is_active("forced_disconnect")
    mock_adapter.start.assert_not_called()


@pytest.mark.asyncio
async def test_reconnect_delay_fault_extends_backoff():
    fm = FaultManager()
    fm.enable(
        "delayed_reconnect",
        FaultConfig(
            fault_id="delayed_reconnect",
            parameters={"delay_seconds": 10},
        ),
    )

    runner = AsyncRunner(
        charge_point_id="CP_1",
        url="ws://localhost:3000",
        command_queue=MagicMock(),
        fault_manager=fm,
    )
    runner._shutdown_event = asyncio.Event()

    captured_timeouts: list[Optional[float]] = []

    async def capturing_wait_for(awaitable, timeout=None):
        captured_timeouts.append(timeout)
        runner._shutdown_event.set()
        try:
            await awaitable
        except asyncio.CancelledError:
            pass
        raise asyncio.TimeoutError()

    with patch.object(asyncio, "wait_for", side_effect=capturing_wait_for):
        with patch(
            "chargeghost_evse.bridge.bridge.websockets.connect",
            side_effect=ConnectionRefusedError,
        ):
            await runner._run_adapter()

    assert len(captured_timeouts) >= 1
    assert captured_timeouts[0] == 11


@pytest.mark.asyncio
async def test_drop_heartbeat_fault_skips_single_heartbeat():
    fm = FaultManager()
    fm.enable("dropped_heartbeat")

    runner = AsyncRunner(
        charge_point_id="CP_1",
        url="ws://localhost:3000",
        command_queue=MagicMock(),
        fault_manager=fm,
    )
    runner._connected = True
    runner._shutdown_event = asyncio.Event()

    mock_adapter = _MockAdapter()
    mock_adapter.heartbeat_interval = 0.05
    runner.adapter = mock_adapter

    async def stop():
        await asyncio.sleep(0.2)
        runner._shutdown_event.set()

    asyncio.create_task(stop())
    await runner._heartbeat_loop()

    assert not fm.is_active("dropped_heartbeat")
    mock_adapter.send_heartbeat.assert_called()


@pytest.mark.asyncio
async def test_meter_values_delay_fault_defers_send():
    fm = FaultManager()
    fm.enable(
        "delayed_response",
        FaultConfig(
            fault_id="delayed_response",
            parameters={"delay_seconds": 0.2},
        ),
    )

    engine = _MockEngine()
    runner = _MockRunner()
    bridge = _make_bridge(engine, runner, fault_manager=fm)

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    adapter = _MockAdapter()
    runner.adapter = adapter
    runner.loop = loop

    bridge._send_meter_value("Sample.Periodic")

    await asyncio.sleep(0.05)
    adapter.send_meter_values.assert_not_called()

    await asyncio.sleep(0.3)
    adapter.send_meter_values.assert_called_once()

    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2)
    loop.close()
