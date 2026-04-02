from unittest.mock import MagicMock

from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.ui.app import MainWindow


class FakeBridge:
	def __init__(self, engine, **kwargs):
		self.engine = engine
		self.kwargs = kwargs
		self.runner = MagicMock()
		self.runner.adapter = None
		self.runner.loop = None
		self.runner.is_connected = False
		self.setup_called = False
		self.shutdown_called = False

	def setup(self) -> None:
		self.setup_called = True

	def shutdown(self) -> None:
		self.shutdown_called = True


def test_bridge_shutdown_unsubscribes_engine_events(monkeypatch):
	engine = Engine()
	bridge = Bridge(engine)
	monkeypatch.setattr(bridge.runner, "run_in_thread", lambda: MagicMock())
	monkeypatch.setattr("threading.Thread.start", lambda self: None)

	bridge.setup()

	assert len(engine.session_started.callbacks) == 1
	assert len(engine.session_stopped.callbacks) == 1
	assert len(engine.connector_status_changed.callbacks) == 1

	bridge.shutdown()

	assert len(engine.session_started.callbacks) == 0
	assert len(engine.session_stopped.callbacks) == 0
	assert len(engine.connector_status_changed.callbacks) == 0


def test_save_config_restarts_bridge_with_updated_settings(monkeypatch, qtbot):
	monkeypatch.setattr("chargeghost_evse.ui.app.Bridge", FakeBridge)
	window = MainWindow()
	qtbot.addWidget(window)
	window.config.save = MagicMock()

	old_bridge = window.bridge
	window.simulator.settings_panel.input_url.setText("ws://example.test/ocpp")
	window.simulator.settings_panel.input_ocpp_id.setText("CP_RESTART")
	window.simulator.settings_panel.combo_ocpp_version.setCurrentText("OCPP 2.0.1")

	window.simulator.settings_panel._on_save_config()

	assert window.config.save.called
	assert old_bridge.shutdown_called is True
	assert window.bridge is not old_bridge
	assert window.bridge.setup_called is True
	assert window.bridge.kwargs["url"] == "ws://example.test/ocpp"
	assert window.bridge.kwargs["charge_point_id"] == "CP_RESTART"
	assert window.bridge.kwargs["ocpp_version"] == "2.0.1"
	assert window.simulator.bridge is window.bridge
	assert window.manual.bridge is window.bridge
	assert window.simulator_controller.bridge is window.bridge
	assert window._config_restart_pending is True


def test_reconnect_uses_explicit_success_message_after_config_restart(monkeypatch, qtbot):
	monkeypatch.setattr("chargeghost_evse.ui.app.Bridge", FakeBridge)
	window = MainWindow()
	qtbot.addWidget(window)
	window.show_toast = MagicMock()
	window.log_message = MagicMock()
	window._config_restart_pending = True

	window.on_connection_status_changed(True)

	window.show_toast.assert_called_once_with(
		"Reconnected to Central System with new settings", "success"
	)
	window.log_message.assert_called_once_with(
		"[green]Config:[/green] Reconnected to Central System with new settings."
	)
	assert window._config_restart_pending is False


def test_save_config_updates_engine_battery_capacity(monkeypatch, qtbot):
	monkeypatch.setattr("chargeghost_evse.ui.app.Bridge", FakeBridge)
	window = MainWindow()
	qtbot.addWidget(window)
	window.config.save = MagicMock()

	window.simulator.settings_panel.input_battery_capacity.setValue(100.0)
	window.simulator.settings_panel._on_save_config()

	assert window.config.ev_battery_capacity == 100.0
	assert window.engine.ev_battery_capacity == 100000.0
