from __future__ import annotations

from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QComboBox
from PySide6.QtWidgets import QFrame
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QMainWindow
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QWidget

from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.devtools.fault_catalog import FAULT_CATALOG
from chargeghost_evse.devtools.fault_models import FaultState
from chargeghost_evse.devtools.timeline_store import TimelineStore
from chargeghost_evse.ui.app import MainWindow
from chargeghost_evse.ui.app import ManualWidget
from chargeghost_evse.ui.app import ModeSelectWidget
from chargeghost_evse.ui.app import ToastManager
from chargeghost_evse.ui.widgets.config_keys_panel import ConfigKeysPanel
from chargeghost_evse.ui.widgets import session_dashboard
from chargeghost_evse.ui.widgets.fault_injection_panel import FaultInjectionPanel
from chargeghost_evse.ui.widgets.log_entry import CollapsibleLogEntry
from chargeghost_evse.ui.widgets.ocpp_timeline_panel import OCPPTimelinePanel
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
	assert dashboard.findChild(QLabel, "telemetryTitle").text() == "Live Power Telemetry — 60 s rolling"


def test_dashboard_exposes_telemetry_panel_supporting_copy() -> None:
	_app()
	dashboard = session_dashboard.SessionDashboard()

	# The subtitle label was merged into the title in the two-column redesign.
	assert dashboard.findChild(QLabel, "telemetryTitle") is not None


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
	sidebar_expanded = False


class _DummyMainWithDeps(QMainWindow):
	def __init__(self) -> None:
		super().__init__()
		self.engine = Engine()
		self.bridge = _DummyBridge()
		self.signal_bridge = _DummySignalBridge()
		self.app_settings = _DummySettings()
		self.timeline_store = TimelineStore()

	def _go_home(self) -> None:
		pass

	def _on_log_mode_toggle(self, is_detailed: bool) -> None:
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


def test_manual_widget_has_log_side_panel() -> None:
	_app()
	widget = ManualWidget(_DummyMainWithDeps())
	assert hasattr(widget, "log_side_panel")
	from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel
	assert isinstance(widget.log_side_panel, LogSidePanel)


def test_timeline_panel_stacks_action_buttons_below_filters() -> None:
	app = _app()
	panel = OCPPTimelinePanel()
	panel.resize(340, 320)
	panel.show()
	app.processEvents()

	action_combo = panel.findChild(QComboBox, "timelineActionFilter")
	copy_btn = panel.findChild(QPushButton, "btnTimelineCopy")

	assert action_combo is not None
	assert copy_btn is not None
	action_bottom = action_combo.mapTo(panel, action_combo.rect().bottomLeft()).y()
	copy_top = copy_btn.mapTo(panel, copy_btn.rect().topLeft()).y()
	assert copy_top >= action_bottom


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
	class _LogSidePanel:
		def __init__(self) -> None:
			self.messages: list[str] = []

		def log_message(self, message: str) -> None:
			self.messages.append(message)

	class _SimulatorWidget:
		def __init__(self) -> None:
			self.log_side_panel = _LogSidePanel()

	class _ManualWidget:
		def __init__(self) -> None:
			self.log_side_panel = _LogSidePanel()

	class _Stack:
		def __init__(self, current_widget: object) -> None:
			self._current_widget = current_widget

		def currentWidget(self) -> object:
			return self._current_widget

	window = MainWindow.__new__(MainWindow)
	window.simulator = _SimulatorWidget()
	window.manual = _ManualWidget()
	window.stack = _Stack(window.simulator)

	MainWindow.log_message(window, "hello")

	assert window.simulator.log_side_panel.messages == ["hello"]
	assert window.manual.log_side_panel.messages == []


def test_main_window_log_message_does_not_duplicate_in_manual_mode() -> None:
	class _LogSidePanel:
		def __init__(self) -> None:
			self.messages: list[str] = []

		def log_message(self, message: str) -> None:
			self.messages.append(message)

	class _SimulatorWidget:
		def __init__(self) -> None:
			self.log_side_panel = _LogSidePanel()

	class _ManualWidget:
		def __init__(self) -> None:
			self.log_side_panel = _LogSidePanel()

	class _Stack:
		def __init__(self, current_widget: object) -> None:
			self._current_widget = current_widget

		def currentWidget(self) -> object:
			return self._current_widget

	window = MainWindow.__new__(MainWindow)
	window.simulator = _SimulatorWidget()
	window.manual = _ManualWidget()
	window.stack = _Stack(window.manual)

	MainWindow.log_message(window, "hello")

	assert window.simulator.log_side_panel.messages == []
	assert window.manual.log_side_panel.messages == ["hello"]


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

	# Two-column redesign: controls panel + data panel, no hero frame
	assert dashboard.findChild(QWidget, "dashControlsPanel") is not None
	assert dashboard.findChild(QWidget, "dashDataPanel") is not None
	assert dashboard.findChild(QFrame, "sessionStateBadge") is not None
	assert dashboard.findChild(QFrame, "telemetryPanel") is not None


def test_dashboard_hero_shows_idle_state_when_no_session() -> None:
	_app()
	engine = Engine()
	engine.add_connector()
	dashboard = session_dashboard.SessionDashboard()

	dashboard.update_from_engine(engine)

	assert dashboard._state_name.text() == "Idle"
	assert dashboard._state_sub.text() == "Connector 1"
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

	# Two-column redesign: state badge + metric cards replace hero labels
	assert dashboard._state_name.text() == "Charging"
	assert dashboard.metric_power._value_label.text() == "3.68"
	assert dashboard.metric_soc._value_label.text() == "0.0"
	assert dashboard.metric_duration._value_label.text() == "1:00"


def test_dashboard_context_metrics_are_always_visible() -> None:
	_app()
	dashboard = session_dashboard.SessionDashboard()

	# Two-column redesign: context chips replace context rail metric cards
	assert dashboard.chip_tx_id is not None
	assert dashboard.chip_voltage is not None
	assert dashboard.chip_current is not None
	assert dashboard.chip_meter is not None
	assert dashboard.chip_phases is not None
	assert dashboard.findChild(QFrame, "toggleDetailsBtn") is None


def test_dashboard_embeds_id_tag_controls_in_hero_context() -> None:
	_app()
	dashboard = session_dashboard.SessionDashboard()

	# Two-column redesign: id_tag_input lives in the controls panel
	assert dashboard.id_tag_input is not None
	assert dashboard.findChild(QFrame, "idTagSection") is None
	assert dashboard.findChild(QWidget, "dashControlsPanel") is not None


def test_dashboard_hero_context_uses_inner_margins() -> None:
	_app()
	dashboard = session_dashboard.SessionDashboard()

	# Two-column redesign: controls panel has 12px margins on all sides
	controls = dashboard.findChild(QWidget, "dashControlsPanel")
	assert controls is not None
	margins = controls.layout().contentsMargins()
	assert margins.left() == 12
	assert margins.top() == 12
	assert margins.right() == 12
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

	assert dashboard._context_limit_value.text() == "16.0 A"


def test_dashboard_hero_exposes_idle_state_property_for_styling() -> None:
	_app()
	engine = Engine()
	engine.add_connector()
	dashboard = session_dashboard.SessionDashboard()

	dashboard.update_from_engine(engine)

	# Two-column redesign: state badge replaces hero frame for state styling
	assert dashboard._state_badge.property("state") == "idle"


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

	assert dashboard.chip_tx_id._value.text() == "--"


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


def test_fault_panel_creates_cards_for_all_faults() -> None:
	_app()
	panel = FaultInjectionPanel()
	assert len(panel._cards) == len(FAULT_CATALOG)
	for fault_id in FAULT_CATALOG:
		assert fault_id in panel._cards
		assert panel.findChild(QFrame, f"fault_card_{fault_id}") is not None


def test_fault_panel_shows_active_fault_count() -> None:
	_app()
	panel = FaultInjectionPanel()
	states = [
		FaultState(fault_id="frozen_meter", enabled=True, trigger_count=5),
		FaultState(fault_id="meter_jump", enabled=True, trigger_count=1),
	]
	panel.set_fault_states(states)

	assert panel._toggle_buttons["frozen_meter"].text() == "Disable"
	assert panel._toggle_buttons["meter_jump"].text() == "Disable"
	assert panel._toggle_buttons["forced_disconnect"].text() == "Enable"
	assert panel._count_labels["frozen_meter"].text() == "5"
	assert not panel._count_labels["frozen_meter"].isHidden()
	assert panel._count_labels["meter_jump"].text() == "1"
	assert not panel._count_labels["meter_jump"].isHidden()
	assert panel._count_labels["forced_disconnect"].isHidden()


def test_fault_panel_clear_all_emits_signal() -> None:
	_app()
	panel = FaultInjectionPanel()
	emitted = []
	panel.clear_all_requested.connect(lambda: emitted.append(True))

	clear_btn = panel.findChild(QPushButton, "clearAllBtn")
	clear_btn.click()

	assert len(emitted) == 1


def test_fault_panel_toggle_emits_signal() -> None:
	_app()
	panel = FaultInjectionPanel()
	emitted = []
	panel.fault_toggled.connect(lambda fid, enabled: emitted.append((fid, enabled)))

	panel._toggle_buttons["frozen_meter"].click()

	assert len(emitted) == 1
	assert emitted[0] == ("frozen_meter", True)


def test_fault_panel_state_updates_do_not_disable_other_fault_buttons() -> None:
	_app()
	panel = FaultInjectionPanel()
	panel.set_fault_states([FaultState(fault_id="frozen_meter", enabled=True)])

	assert panel._cards["forced_disconnect"].isEnabled()
	assert panel._toggle_buttons["forced_disconnect"].isEnabled()

	panel.set_fault_states([])

	assert panel._cards["frozen_meter"].isEnabled()
	assert panel._toggle_buttons["frozen_meter"].isEnabled()
