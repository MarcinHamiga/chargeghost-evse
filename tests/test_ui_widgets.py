from __future__ import annotations

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QFrame
from PySide6.QtWidgets import QMainWindow

from chargeghost_evse.ui.app import MainWindow
from chargeghost_evse.ui.app import ManualWidget
from chargeghost_evse.ui.app import ModeSelectWidget
from chargeghost_evse.ui.app import ToastManager
from chargeghost_evse.ui.widgets import session_dashboard
from chargeghost_evse.ui.widgets.connector_strip import ConnectorIndicator
from chargeghost_evse.ui.widgets.session_dashboard import TelemetryChart


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


def test_telemetry_chart_restarts_from_window_start(monkeypatch) -> None:
	_app()
	monotonic_values = iter([0.0, 65.0, 65.0])
	monkeypatch.setattr(
		session_dashboard.time, "monotonic", lambda: next(monotonic_values)
	)
	chart = TelemetryChart()

	chart.add_point(11.5)

	assert len(chart._power_data) == 1
	assert chart._power_data[0].x() == 0.0
	assert chart.axis_x.min() == 0
	assert chart.axis_x.max() == 60


def test_connector_indicator_clears_charging_stylesheet() -> None:
	_app()
	indicator = ConnectorIndicator(1)

	indicator.update_status(status="Charging", is_plugged=True, soc=55.0)
	indicator.set_pulse_opacity(0.7)
	assert "charging='true'" in indicator.styleSheet()

	indicator.update_status(status="Available", is_plugged=False)

	assert indicator.property("charging") is False
	assert indicator.styleSheet() == ""


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
	runner = _DummyRunner()


class _DummySignalBridge:
	log_mode = "compact"


class _DummySettings:
	log_mode = "compact"


class _DummyMainWithDeps(QMainWindow):
	def __init__(self) -> None:
		super().__init__()
		from chargeghost_evse.engine.engine import Engine

		self.engine = Engine()
		self.bridge = _DummyBridge()
		self.signal_bridge = _DummySignalBridge()
		self.app_settings = _DummySettings()


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
