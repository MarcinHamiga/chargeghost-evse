from __future__ import annotations

from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QFrame
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QMainWindow

from chargeghost_evse.engine.connector import ConnectorState
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.ui.app import MainWindow
from chargeghost_evse.ui.app import ManualWidget
from chargeghost_evse.ui.app import ModeSelectWidget
from chargeghost_evse.ui.app import ToastManager
from chargeghost_evse.ui.widgets.config_keys_panel import ConfigKeysPanel
from chargeghost_evse.ui.widgets import session_dashboard
from chargeghost_evse.ui.widgets.connector_strip import ConnectorIndicator
from chargeghost_evse.ui.widgets.log_entry import CollapsibleLogEntry
from chargeghost_evse.ui.widgets.toast import ToastNotification
from chargeghost_evse.ui.widgets.session_dashboard import TelemetryChart
from chargeghost_evse.ocpp_adapter.config_keys import ConfigurationKeyManager


def _app() -> QApplication:
	app = QApplication.instance()
	if app is None:
		app = QApplication([])
	return app


def test_telemetry_chart_clear_resets_axes() -> None:
	_app()
	chart = TelemetryChart()

	chart.add_point(80.0)
	assert chart.axis_y.max() > 25

	chart.clear()

	assert chart.axis_x.min() == 0
	assert chart.axis_x.max() == 60
	assert chart.axis_y.min() == 0
	assert chart.axis_y.max() == 25


def test_telemetry_chart_stores_points_within_window(monkeypatch) -> None:
	_app()
	# Simulate: chart created at t=0, two points at t=20 and t=40.
	monotonic_values = iter([0.0, 20.0, 40.0])
	monkeypatch.setattr(
		session_dashboard.time, "monotonic", lambda: next(monotonic_values)
	)
	chart = TelemetryChart()  # _start_time = 0.0

	chart.add_point(11.5)  # elapsed = 20 s
	chart.add_point(5.0)   # elapsed = 40 s

	assert len(chart._power_data) == 2
	assert chart._power_data[0].x() == 20.0
	assert chart._power_data[1].x() == 40.0


def test_dashboard_exposes_named_telemetry_panel() -> None:
	_app()
	dashboard = session_dashboard.SessionDashboard()

	assert dashboard.findChild(QFrame, "telemetryPanel") is not None
	assert dashboard.findChild(QLabel, "telemetryTitle").text() == "Live Power Telemetry"


def test_dashboard_exposes_telemetry_panel_supporting_copy() -> None:
	_app()
	dashboard = session_dashboard.SessionDashboard()

	assert dashboard.findChild(QLabel, "telemetrySubtitle").text() == "Rolling 60-second delivered power view"


def test_connector_indicator_clears_charging_stylesheet() -> None:
	_app()
	indicator = ConnectorIndicator(1)

	indicator.update_status(status="Charging", is_plugged=True, soc=55.0)
	indicator.set_pulse_opacity(0.7)
	assert "charging='true'" in indicator.styleSheet()

	indicator.update_status(status="Available", is_plugged=False)

	assert indicator.property("charging") is False
	assert indicator.styleSheet() == ""


def test_connector_indicator_shows_hardware_summary() -> None:
	_app()
	engine = Engine()
	engine.add_connector(voltage=400.0, current=32.0, phase=3)
	strip = session_dashboard.ConnectorStrip()

	strip.update_connectors(engine)

	indicator = strip._indicators[0]
	assert indicator._hardware_label.text() == "400V · 32A · 3Ph"


def test_connector_strip_preserves_selected_connector_after_status_refresh() -> None:
	_app()
	engine = Engine()
	engine.add_connector()
	second = engine.add_connector(voltage=400.0, current=16.0, phase=3)
	strip = session_dashboard.ConnectorStrip()

	strip.update_connectors(engine)
	strip.set_selected_connector(second.id)
	engine.plug_in(second.id)
	strip.update_connectors(engine)

	assert strip.get_selected_connector_id() == second.id
	assert strip._indicators[1].property("selected") is True
	assert strip._indicators[0].property("selected") is False


def test_toast_manager_is_hidden_when_empty() -> None:
	app = _app()
	host = QMainWindow()
	manager = ToastManager(host)
	host.show()
	app.processEvents()
	assert manager.isHidden()

	toast = manager.show_toast("Saved", "success")
	app.processEvents()
	assert manager.isVisible()

	manager._remove_toast(toast)
	app.processEvents()
	assert manager.isHidden()


class _DummyMainWindow(QMainWindow):
	def switch_to_mode(self, mode: str) -> None:
		pass


class _DummyRunner:
	adapter = None
	loop = None


class _DummyBridge:
	def __init__(self) -> None:
		self.runner = _DummyRunner()


class _DummySignalBridge:
	log_mode = "compact"


class _DummySettings:
	log_mode = "compact"


class _DummyMainWithDeps(QMainWindow):
	def __init__(self) -> None:
		super().__init__()
		self.engine = Engine()
		self.bridge = _DummyBridge()
		self.signal_bridge = _DummySignalBridge()
		self.app_settings = _DummySettings()

	def _go_home(self) -> None:
		pass


def test_mode_cards_stay_within_viewport_on_narrow_width() -> None:
	app = _app()
	widget = ModeSelectWidget(_DummyMainWindow())
	widget.resize(520, 480)
	widget.show()
	app.processEvents()

	cards = [c for c in widget.findChildren(QFrame) if c.property("modeCard")]
	assert len(cards) == 2
	for card in cards:
		assert card.geometry().right() <= widget.rect().right()


def test_manual_widget_log_button_object_names_match_stylesheet() -> None:
	_app()
	widget = ManualWidget(_DummyMainWithDeps())
	assert widget.btn_clear_logs.objectName() == "btnClearLog"
	assert widget.btn_log_mode.objectName() == "btnLogMode"


def test_manual_widget_disables_actions_without_adapter() -> None:
	_app()
	widget = ManualWidget(_DummyMainWithDeps())

	assert not widget.btn_boot.isEnabled()
	assert not widget.btn_heartbeat.isEnabled()
	assert not widget.btn_status.isEnabled()
	assert not widget.btn_stop.isEnabled()
	assert not widget.id_tag_input._apply_btn.isEnabled()


def test_manual_widget_requires_transaction_context_to_stop() -> None:
	_app()
	main = _DummyMainWithDeps()
	main.bridge.runner.adapter = object()
	main.bridge.runner.loop = object()
	widget = ManualWidget(main)

	with patch("chargeghost_evse.ui.app.asyncio.run_coroutine_threadsafe") as mock_submit:
		widget.action_stop()

	assert not mock_submit.called


def test_main_window_log_message_does_not_duplicate_in_simulator_mode() -> None:
	class _Panel:
		def __init__(self) -> None:
			self.messages: list[str] = []

		def log_message(self, message: str) -> None:
			self.messages.append(message)

	class _ManualPanel:
		def __init__(self) -> None:
			self.messages: list[str] = []

		def log_message(self, message: str) -> None:
			self.messages.append(message)

	class _Stack:
		def __init__(self, current_widget: object) -> None:
			self._current_widget = current_widget

		def currentWidget(self) -> object:
			return self._current_widget

	window = MainWindow.__new__(MainWindow)
	window._global_log_panel = _Panel()
	window.manual = _ManualPanel()
	window.simulator = object()
	window.stack = _Stack(window.simulator)

	MainWindow.log_message(window, "hello")

	assert window._global_log_panel.messages == ["hello"]
	assert window.manual.messages == []


def test_main_window_log_message_does_not_duplicate_in_manual_mode() -> None:
	class _Panel:
		def __init__(self) -> None:
			self.messages: list[str] = []

		def log_message(self, message: str) -> None:
			self.messages.append(message)

	class _ManualPanel:
		def __init__(self) -> None:
			self.messages: list[str] = []

		def log_message(self, message: str) -> None:
			self.messages.append(message)

	class _Stack:
		def __init__(self, current_widget: object) -> None:
			self._current_widget = current_widget

		def currentWidget(self) -> object:
			return self._current_widget

	window = MainWindow.__new__(MainWindow)
	window._global_log_panel = _Panel()
	window.manual = _ManualPanel()
	window.simulator = object()
	window.stack = _Stack(window.manual)

	MainWindow.log_message(window, "hello")

	assert window._global_log_panel.messages == []
	assert window.manual.messages == ["hello"]


def test_dashboard_power_metric_uses_effective_delivered_power() -> None:
	_app()
	engine = Engine()
	connector = engine.add_connector(voltage=230.0, current=32.0, phase=1)
	engine.plug_in(connector.id)
	engine.get_limit = lambda connector_id, transaction_id: 16.0
	engine.start_session(connector.id, transaction_id=42)
	dashboard = session_dashboard.SessionDashboard()

	dashboard.update_from_engine(engine)

	assert dashboard.metric_power._value_label.text() == "3.68"


def test_dashboard_exposes_session_hero_sections() -> None:
	_app()
	dashboard = session_dashboard.SessionDashboard()

	assert dashboard.findChild(QFrame, "sessionHero") is not None
	assert dashboard.findChild(QFrame, "sessionContextRail") is not None
	assert dashboard.findChild(QFrame, "sessionHeroMetrics") is not None
	assert dashboard.findChild(QFrame, "sessionHeroActions") is not None


def test_dashboard_hero_shows_idle_state_when_no_session() -> None:
	_app()
	engine = Engine()
	engine.add_connector()
	dashboard = session_dashboard.SessionDashboard()

	dashboard.update_from_engine(engine)

	assert dashboard._hero_state_value.text() == "Idle"
	assert dashboard._hero_connector_value.text() == "Connector 1"
	assert dashboard.btn_start_charge.isEnabled() is False
	assert dashboard.btn_stop_charge.isEnabled() is False


def test_dashboard_hero_shows_live_session_state(monkeypatch) -> None:
	_app()
	engine = Engine()
	connector = engine.add_connector(voltage=230.0, current=32.0, phase=1)
	engine.plug_in(connector.id)
	engine.get_limit = lambda connector_id, transaction_id: 16.0
	engine.start_session(connector.id, transaction_id=99)
	assert engine.session is not None
	engine.session.start_time = 100.0
	monkeypatch.setattr(session_dashboard.time, "time", lambda: 160.0)
	dashboard = session_dashboard.SessionDashboard()

	dashboard.update_from_engine(engine)

	assert dashboard._hero_state_value.text() == "Charging"
	assert dashboard._hero_power_value.text() == "3.68 kW"
	assert dashboard._hero_soc_value.text() == "0.0%"
	assert dashboard._hero_duration_value.text() == "1:00"


def test_dashboard_context_metrics_are_always_visible() -> None:
	_app()
	dashboard = session_dashboard.SessionDashboard()

	assert dashboard.findChild(QFrame, "sessionContextRail") is not None
	assert dashboard.findChild(QFrame, "contextMetricTx") is not None
	assert dashboard.findChild(QFrame, "contextMetricVoltage") is not None
	assert dashboard.findChild(QFrame, "contextMetricCurrent") is not None
	assert dashboard.findChild(QFrame, "contextMetricMeter") is not None
	assert dashboard.findChild(QFrame, "toggleDetailsBtn") is None


def test_dashboard_embeds_id_tag_controls_in_hero_context() -> None:
	_app()
	dashboard = session_dashboard.SessionDashboard()

	assert dashboard.findChild(QFrame, "sessionHeroContext") is not None
	assert dashboard.findChild(QFrame, "idTagSection") is None
	assert dashboard.id_tag_input.parentWidget() is dashboard._hero_context_frame


def test_dashboard_hero_context_uses_inner_margins() -> None:
	_app()
	dashboard = session_dashboard.SessionDashboard()
	margins = dashboard._hero_context_frame.layout().contentsMargins()

	assert margins.left() == 16
	assert margins.top() == 12
	assert margins.right() == 16
	assert margins.bottom() == 12


def test_dashboard_context_shows_effective_limit_for_selected_connector() -> None:
	_app()
	engine = Engine()
	connector = engine.add_connector(voltage=230.0, current=32.0, phase=1)
	engine.plug_in(connector.id)
	engine.get_limit = lambda connector_id, transaction_id: 16.0
	engine.start_session(connector.id, transaction_id=7)
	dashboard = session_dashboard.SessionDashboard()

	dashboard.update_from_engine(engine)

	assert dashboard._context_limit_value.text() == "16.0A"


def test_dashboard_hero_exposes_idle_state_property_for_styling() -> None:
	_app()
	engine = Engine()
	engine.add_connector()
	dashboard = session_dashboard.SessionDashboard()

	dashboard.update_from_engine(engine)

	assert dashboard._hero_frame.property("sessionState") == "idle"


def test_dashboard_limit_summary_exposes_limited_property_for_styling() -> None:
	_app()
	engine = Engine()
	connector = engine.add_connector(voltage=230.0, current=32.0, phase=1)
	engine.plug_in(connector.id)
	engine.get_limit = lambda connector_id, transaction_id: 16.0
	engine.start_session(connector.id, transaction_id=3)
	dashboard = session_dashboard.SessionDashboard()

	dashboard.update_from_engine(engine)

	assert dashboard._context_limit_value.property("limited") is True


def test_dashboard_context_hides_transaction_for_other_connector() -> None:
	_app()
	engine = Engine()
	first = engine.add_connector()
	second = engine.add_connector()
	engine.plug_in(first.id)
	engine.start_session(first.id, transaction_id=99)
	dashboard = session_dashboard.SessionDashboard()
	dashboard.set_selected_connector(second.id)

	dashboard.update_from_engine(engine)

	assert dashboard.metric_tx_id._value_label.text() == "--"


def test_connector_indicator_preserves_meaningful_plugged_status() -> None:
	_app()
	indicator = ConnectorIndicator(1)

	indicator.update_status(status=ConnectorState.PREPARING.value, is_plugged=True)

	assert indicator._status_label.text() == ConnectorState.PREPARING.value


def test_config_keys_panel_requires_explicit_apply(qtbot) -> None:
	manager = ConfigurationKeyManager()
	manager.initialize_defaults()
	panel = ConfigKeysPanel()
	qtbot.addWidget(panel)
	panel.set_keys(manager.get_all_keys())

	emitted: list[tuple[str, str]] = []
	panel.key_changed.connect(lambda key, value: emitted.append((key, value)))

	line_edit = panel._key_inputs["HeartbeatInterval"]
	line_edit.setText("123")

	assert emitted == []

	apply_btn = panel._apply_buttons["HeartbeatInterval"]
	apply_btn.click()

	assert emitted == [("HeartbeatInterval", "123")]


def test_config_keys_panel_shows_empty_search_state(qtbot) -> None:
	manager = ConfigurationKeyManager()
	manager.initialize_defaults()
	panel = ConfigKeysPanel()
	qtbot.addWidget(panel)
	panel.set_keys(manager.get_all_keys())

	panel._search_input.setText("no-such-config-key")

	assert not panel._empty_search_state.isHidden()


def test_toast_manager_reuses_progress_toast() -> None:
	app = _app()
	host = QMainWindow()
	manager = ToastManager(host)
	host.show()
	app.processEvents()

	first = manager.show_toast("Downloading update: 10%", "info", toast_id="download")
	second = manager.show_toast("Downloading update: 20%", "info", toast_id="download")
	app.processEvents()

	assert first is second
	assert len(manager._toasts) == 1
	assert second.message_text() == "Downloading update: 20%"


def test_toast_notification_grows_for_multiline_messages() -> None:
	_app()
	toast = ToastNotification("Line one\nLine two\nLine three", "info")

	assert toast.minimumHeight() > 48

class TestCollapsibleLogEntry:
	def test_creates_with_summary(self, qtbot):
		entry = CollapsibleLogEntry(summary="TX BootNotification", detail='{"vendor": "CG"}')
		qtbot.addWidget(entry)
		assert entry._summary_label.text() is not None
		assert not entry._detail_label.isVisible()

	def test_click_toggles_detail(self, qtbot):
		entry = CollapsibleLogEntry(summary="TX BootNotification", detail='{"vendor": "CG"}')
		qtbot.addWidget(entry)
		assert not entry._detail_label.isVisible()
		entry._on_toggle()
		assert entry._detail_label.isVisible()
		entry._on_toggle()
		assert not entry._detail_label.isVisible()
