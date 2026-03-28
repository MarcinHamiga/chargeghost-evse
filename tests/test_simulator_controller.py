from unittest.mock import MagicMock, AsyncMock

import pytest

from chargeghost_evse.devtools.simulator_controller import (
    ActionResult,
    SimulatorController,
)


class TestSimulatorController:
    def test_plug_in_calls_engine(self) -> None:
        engine = MagicMock()
        bridge = MagicMock()
        controller = SimulatorController(engine=engine, bridge=bridge)

        result = controller.plug_in(connector_id=1)

        engine.plug_in.assert_called_once_with(1)
        assert result.success is True
        assert "Plugged In" in result.message

    def test_unplug_calls_engine(self) -> None:
        engine = MagicMock()
        bridge = MagicMock()
        controller = SimulatorController(engine=engine, bridge=bridge)

        result = controller.unplug(connector_id=1)

        engine.unplug.assert_called_once_with(1)
        assert result.success is True
        assert "Unplugged" in result.message

    def test_start_charging_assigns_transaction_id(self) -> None:
        engine = MagicMock()
        engine.get_connector.return_value = MagicMock()
        bridge = MagicMock()
        controller = SimulatorController(engine=engine, bridge=bridge)

        result = controller.start_charging(connector_id=1)

        assert controller._transaction_counter == 1
        engine.start_session.assert_called_once()
        call_kwargs = engine.start_session.call_args[1]
        assert call_kwargs["transaction_id"] == 1
        assert result.success is True

    def test_start_charging_increments_counter(self) -> None:
        engine = MagicMock()
        engine.get_connector.return_value = MagicMock()
        bridge = MagicMock()
        controller = SimulatorController(engine=engine, bridge=bridge)

        controller.start_charging(connector_id=1)
        controller.start_charging(connector_id=1)

        assert controller._transaction_counter == 2

    def test_stop_charging_calls_engine(self) -> None:
        engine = MagicMock()
        bridge = MagicMock()
        controller = SimulatorController(engine=engine, bridge=bridge)

        result = controller.stop_charging()

        engine.stop_session.assert_called_once()
        assert result.success is True

    def test_suspend_ev_calls_engine(self) -> None:
        engine = MagicMock()
        bridge = MagicMock()
        controller = SimulatorController(engine=engine, bridge=bridge)

        result = controller.suspend_ev(connector_id=1)

        engine.suspend_ev.assert_called_once_with(1)
        assert result.success is True
        assert "Suspended" in result.message

    def test_resume_charging_calls_engine(self) -> None:
        engine = MagicMock()
        bridge = MagicMock()
        controller = SimulatorController(engine=engine, bridge=bridge)

        result = controller.resume_charging(connector_id=1)

        engine.resume_charging.assert_called_once_with(1)
        assert result.success is True
        assert "Resumed" in result.message

    def test_authorize_uses_bridge(self) -> None:
        engine = MagicMock()
        bridge = MagicMock()
        controller = SimulatorController(engine=engine, bridge=bridge)

        result = controller.authorize("TAG-123")

        bridge.send_authorize.assert_called_once_with("TAG-123")
        assert result.success is True
        assert "Authorize" in result.message

    def test_send_heartbeat_uses_bridge(self) -> None:
        engine = MagicMock()
        bridge = MagicMock()
        controller = SimulatorController(engine=engine, bridge=bridge)

        result = controller.send_heartbeat()

        bridge.send_heartbeat.assert_called_once()
        assert result.success is True

    def test_set_rfid_updates_connector(self) -> None:
        engine = MagicMock()
        bridge = MagicMock()
        mock_connector = MagicMock()
        engine.get_connector.return_value = mock_connector
        controller = SimulatorController(engine=engine, bridge=bridge)

        result = controller.set_rfid("TAG-456", connector_id=1)

        assert mock_connector.id_tag == "TAG-456"
        assert result.success is True
        assert "RFID" in result.message

    def test_clear_rfid_clears_connector(self) -> None:
        engine = MagicMock()
        bridge = MagicMock()
        mock_connector = MagicMock()
        mock_connector.id_tag = "OLD"
        engine.get_connector.return_value = mock_connector
        controller = SimulatorController(engine=engine, bridge=bridge)

        result = controller.clear_rfid(connector_id=1)

        assert mock_connector.id_tag is None
        assert result.success is True

    def test_connect_starts_bridge(self) -> None:
        engine = MagicMock()
        bridge = MagicMock()
        bridge.runner.is_connected = False
        controller = SimulatorController(engine=engine, bridge=bridge)

        result = controller.connect()

        bridge.setup.assert_called_once()
        assert result.success is True
        assert "Connect" in result.message

    def test_disconnect_shuts_down_bridge(self) -> None:
        engine = MagicMock()
        bridge = MagicMock()
        controller = SimulatorController(engine=engine, bridge=bridge)

        result = controller.disconnect()

        bridge.shutdown.assert_called_once()
        assert result.success is True
        assert "Disconnect" in result.message

    def test_action_unknown_returns_failure(self) -> None:
        engine = MagicMock()
        bridge = MagicMock()
        controller = SimulatorController(engine=engine, bridge=bridge)

        result = controller.execute_action("fly_to_the_moon", connector_id=1)

        assert result.success is False
        assert "Unknown action" in result.message

    def test_get_connector_returns_engine_connector(self) -> None:
        engine = MagicMock()
        bridge = MagicMock()
        mock_connector = MagicMock()
        engine.get_connector.return_value = mock_connector
        controller = SimulatorController(engine=engine, bridge=bridge)

        connector = controller.get_connector(1)

        assert connector is mock_connector
        engine.get_connector.assert_called_once_with(1)

    def test_get_session_returns_engine_session(self) -> None:
        engine = MagicMock()
        bridge = MagicMock()
        mock_session = MagicMock()
        engine.get_session.return_value = mock_session
        controller = SimulatorController(engine=engine, bridge=bridge)

        session = controller.get_session(1)

        assert session is mock_session
        engine.get_session.assert_called_once_with(1)

    def test_is_connected_delegates_to_bridge_runner(self) -> None:
        engine = MagicMock()
        bridge = MagicMock()
        bridge.runner.is_connected = True
        controller = SimulatorController(engine=engine, bridge=bridge)

        assert controller.is_connected is True

        bridge.runner.is_connected = False
        assert controller.is_connected is False
