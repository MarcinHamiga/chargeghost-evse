"""Tests for Bridge._inject_limit_getter and _on_adapter_registered behaviour."""

import asyncio
import logging
import threading
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, call


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
        self.send_notify_event = AsyncMock()
        self.send_transaction_event_updated = AsyncMock()


class _MockRunner:
    def __init__(self, ocpp_version: str = "1.6") -> None:
        self.adapter = None
        self._connected = False
        self.loop = None
        self.logger = logging.getLogger("chargeghost.bridge")
        self.ocpp_version = ocpp_version

    @property
    def is_connected(self) -> bool:
        return self._connected and self.adapter is not None


class _NullEvent:
    def emit(self, **kwargs) -> None:
        pass

    def subscribe(self, *args, **kwargs) -> None:
        pass


def _make_bridge(engine, runner):
    """Create a Bridge instance without triggering its real __init__."""
    from chargeghost_evse.bridge.bridge import Bridge
    from chargeghost_evse.bridge.message_queue import InMemoryBackend, MessageQueue

    bridge = Bridge.__new__(Bridge)
    bridge.engine = engine
    bridge.runner = runner
    bridge._shutdown_event = threading.Event()
    bridge._message_queue = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
    bridge.timeline_store = None
    bridge._adapter_unsubscribers: list = []
    return bridge


def _run_loop_until_idle(loop: asyncio.AbstractEventLoop) -> None:
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    sentinel = asyncio.run_coroutine_threadsafe(asyncio.sleep(0), loop)
    sentinel.result(timeout=5)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2)


class TestInjectLimitGetter:
    def test_injects_on_first_connection(self):
        engine = _MockEngine()
        runner = _MockRunner()
        bridge = _make_bridge(engine, runner)

        adapter = _MockAdapter()
        runner.adapter = adapter
        runner._connected = True

        bridge._inject_limit_getter()

        assert adapter.get_connector_info is not None
        assert adapter.get_connector_status is not None
        assert adapter.get_meter_snapshot is not None
        assert adapter.get_connector_status(0) == "Available"
        assert adapter.get_connector_status(1) == "Available"
        assert adapter.get_meter_snapshot(1) == (12.34, 99)
        assert engine.get_limit is not None

    def test_registration_sends_charge_point_status_before_connectors(self):
        engine = _MockEngine(["Available", "Preparing"])
        runner = _MockRunner()
        adapter = _MockAdapter()
        loop = asyncio.new_event_loop()
        bridge = _make_bridge(engine, runner)

        runner.adapter = adapter
        runner.loop = loop
        runner._connected = True

        bridge._on_adapter_registered()
        _run_loop_until_idle(loop)
        loop.close()

        assert adapter.send_status_notification.await_args_list == [
            call(connector_id=0, error_code="NoError", status="Preparing"),
            call(connector_id=1, error_code="NoError", status="Available"),
            call(connector_id=2, error_code="NoError", status="Preparing"),
        ]

    def test_reconnect_reinjects_callbacks_and_resends_initial_statuses(self):
        """Each accepted BootNotification should re-register callbacks and statuses."""
        engine = _MockEngine(["Available", "Faulted"])
        runner = _MockRunner()
        bridge = _make_bridge(engine, runner)

        loop1 = asyncio.new_event_loop()
        adapter1 = _MockAdapter()
        runner.adapter = adapter1
        runner.loop = loop1
        runner._connected = True
        bridge._on_adapter_registered()
        _run_loop_until_idle(loop1)
        loop1.close()

        assert adapter1.get_connector_info is not None
        assert adapter1.get_connector_status is not None
        assert adapter1.get_meter_snapshot is not None
        assert adapter1.send_status_notification.await_args_list == [
            call(connector_id=0, error_code="NoError", status="Faulted"),
            call(connector_id=1, error_code="NoError", status="Available"),
            call(connector_id=2, error_code="NoError", status="Faulted"),
        ]

        runner._connected = False
        runner.adapter = None
        runner.loop = None

        loop2 = asyncio.new_event_loop()
        adapter2 = _MockAdapter()
        runner.adapter = adapter2
        runner.loop = loop2
        runner._connected = True
        bridge._on_adapter_registered()
        _run_loop_until_idle(loop2)
        loop2.close()

        assert adapter2.get_connector_info is not None
        assert adapter2.get_connector_status is not None
        assert adapter2.get_meter_snapshot is not None
        assert adapter2.send_status_notification.await_args_list == [
            call(connector_id=0, error_code="NoError", status="Faulted"),
            call(connector_id=1, error_code="NoError", status="Available"),
            call(connector_id=2, error_code="NoError", status="Faulted"),
        ]

    def test_remove_limit_getter_clears_callbacks(self):
        engine = _MockEngine()
        runner = _MockRunner()
        bridge = _make_bridge(engine, runner)

        adapter = _MockAdapter()
        runner.adapter = adapter
        runner._connected = True

        bridge._inject_limit_getter()
        bridge._remove_limit_getter()

        assert adapter.get_connector_info is None
        assert adapter.get_connector_status is None
        assert adapter.get_meter_snapshot is None


class TestConnectorStatusRouting:
    def test_faulted_sends_notify_event_and_status_notification(self):
        from chargeghost_evse.engine.connector import ConnectorState

        engine = _MockEngine()
        runner = _MockRunner(ocpp_version="2.0.1")
        bridge = _make_bridge(engine, runner)
        adapter = _MockAdapter()
        loop = asyncio.new_event_loop()
        runner.adapter = adapter
        runner.loop = loop
        runner._connected = True

        bridge.on_connector_status_change(1, ConnectorState.FAULTED)
        _run_loop_until_idle(loop)
        loop.close()

        assert adapter.send_notify_event.called
        assert adapter.send_status_notification.called
        status_call = adapter.send_status_notification.call_args
        assert status_call is not None
        assert status_call.kwargs["status"] == "Faulted"
        assert status_call.kwargs["error_code"] == "Faulted"

    def test_v201_charging_state_during_transaction_sends_transaction_event_updated(
        self,
    ):
        from chargeghost_evse.engine.connector import ConnectorState

        engine = _MockEngine()
        engine.session = MagicMock(connector_id=1, transaction_id=99)
        engine._sessions = {1: engine.session}
        runner = _MockRunner(ocpp_version="2.0.1")
        bridge = _make_bridge(engine, runner)
        adapter = _MockAdapter()
        loop = asyncio.new_event_loop()
        runner.adapter = adapter
        runner.loop = loop
        runner._connected = True

        bridge.on_connector_status_change(1, ConnectorState.CHARGING)
        _run_loop_until_idle(loop)
        loop.close()

        assert adapter.send_transaction_event_updated.called
        tx_update_call = adapter.send_transaction_event_updated.call_args
        assert tx_update_call is not None
        assert tx_update_call.kwargs["charging_state"] == "Charging"

    def test_v201_suspended_ev_during_transaction_sends_transaction_event_updated(self):
        from chargeghost_evse.engine.connector import ConnectorState

        engine = _MockEngine()
        engine.session = MagicMock(connector_id=1, transaction_id=99)
        engine._sessions = {1: engine.session}
        runner = _MockRunner(ocpp_version="2.0.1")
        bridge = _make_bridge(engine, runner)
        adapter = _MockAdapter()
        loop = asyncio.new_event_loop()
        runner.adapter = adapter
        runner.loop = loop
        runner._connected = True

        bridge.on_connector_status_change(1, ConnectorState.SUSPENDED_EV)
        _run_loop_until_idle(loop)
        loop.close()

        assert adapter.send_transaction_event_updated.called
        tx_update_call = adapter.send_transaction_event_updated.call_args
        assert tx_update_call is not None
        assert tx_update_call.kwargs["charging_state"] == "SuspendedEV"

    def test_v16_charging_state_always_sends_status_notification(self):
        from chargeghost_evse.engine.connector import ConnectorState

        engine = _MockEngine()
        engine.session = MagicMock(connector_id=1, transaction_id=99)
        engine._sessions = {1: engine.session}
        runner = _MockRunner(ocpp_version="1.6")
        bridge = _make_bridge(engine, runner)
        adapter = _MockAdapter()
        loop = asyncio.new_event_loop()
        runner.adapter = adapter
        runner.loop = loop
        runner._connected = True

        bridge.on_connector_status_change(1, ConnectorState.CHARGING)
        _run_loop_until_idle(loop)
        loop.close()

        assert not adapter.send_transaction_event_updated.called
        assert adapter.send_status_notification.called

    def test_available_state_sends_status_notification(self):
        from chargeghost_evse.engine.connector import ConnectorState

        engine = _MockEngine()
        runner = _MockRunner(ocpp_version="2.0.1")
        bridge = _make_bridge(engine, runner)
        adapter = _MockAdapter()
        loop = asyncio.new_event_loop()
        runner.adapter = adapter
        runner.loop = loop
        runner._connected = True

        bridge.on_connector_status_change(1, ConnectorState.AVAILABLE)
        _run_loop_until_idle(loop)
        loop.close()

        assert adapter.send_status_notification.called
        assert not adapter.send_notify_event.called
        assert not adapter.send_transaction_event_updated.called

    def test_no_transaction_charging_state_sends_status_notification(self):
        from chargeghost_evse.engine.connector import ConnectorState

        engine = _MockEngine()
        engine.session = None
        engine._sessions = {}
        runner = _MockRunner(ocpp_version="2.0.1")
        bridge = _make_bridge(engine, runner)
        adapter = _MockAdapter()
        loop = asyncio.new_event_loop()
        runner.adapter = adapter
        runner.loop = loop
        runner._connected = True

        bridge.on_connector_status_change(1, ConnectorState.CHARGING)
        _run_loop_until_idle(loop)
        loop.close()

        assert adapter.send_status_notification.called
        assert not adapter.send_transaction_event_updated.called
