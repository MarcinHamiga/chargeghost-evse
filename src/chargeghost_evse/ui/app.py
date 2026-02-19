import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
	QApplication,
	QFrame,
	QHBoxLayout,
	QLabel,
	QLineEdit,
	QMainWindow,
	QPushButton,
	QStackedWidget,
	QStatusBar,
	QTabWidget,
	QVBoxLayout,
	QWidget,
)

from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.ui.bridge import QtSignalBridge
from chargeghost_evse.ui.widgets.collapsible_log import CollapsibleLogPanel
from chargeghost_evse.ui.widgets.log_panel import LogPanel
from chargeghost_evse.ui.widgets.session_dashboard import SessionDashboard
from chargeghost_evse.ui.widgets.settings_panel import SettingsPanel
from chargeghost_evse.util.config import ConnectorConfig, SimulationConfig


def get_resource_path(relative_path: str) -> Path:
	if getattr(sys, "frozen", False):
		base_path = Path(sys._MEIPASS)  # type: ignore[attr-defined]
		return base_path / "chargeghost_evse" / "ui" / relative_path
	else:
		base_path = Path(__file__).parent
		return base_path / relative_path


STYLES_PATH = get_resource_path("styles/e_mobility.qss")


class ClickableModeCard(QFrame):
	def __init__(self, callback, parent=None):
		super().__init__(parent)
		self._callback = callback

	def mousePressEvent(self, event) -> None:
		if event.button() == Qt.MouseButton.LeftButton:
			self._callback()
		super().mousePressEvent(event)


class ModeSelectWidget(QWidget):
	def __init__(self, main_window: "MainWindow"):
		super().__init__()
		self.main_window = main_window
		layout = QVBoxLayout(self)
		layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
		layout.setSpacing(40)
		layout.setContentsMargins(40, 40, 40, 40)

		header_container = QVBoxLayout()
		header_container.setSpacing(10)

		title = QLabel("ChargeGhost EVSE")
		title.setObjectName("mainTitle")
		title.setAlignment(Qt.AlignmentFlag.AlignCenter)
		header_container.addWidget(title)

		subtitle = QLabel("Electric Vehicle Supply Equipment Simulator")
		subtitle.setObjectName("mainSubtitle")
		subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
		header_container.addWidget(subtitle)

		layout.addLayout(header_container)

		mode_container = QVBoxLayout()
		mode_container.setSpacing(24)

		mode_label = QLabel("Select Simulation Mode")
		mode_label.setObjectName("modeSelectLabel")
		mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
		mode_container.addWidget(mode_label)

		btn_row = QHBoxLayout()
		btn_row.setSpacing(20)
		btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

		sim_card = self._create_mode_card(
			title="Simulator Mode",
			description="Full autonomous simulation with OCPP integration",
			button_text="Launch Simulator",
			button_property="primary",
			callback=lambda: self.main_window.switch_to_mode("simulator"),
		)
		btn_row.addWidget(sim_card)

		manual_card = self._create_mode_card(
			title="Manual Mode",
			description="Raw OCPP message control and protocol debugging",
			button_text="Launch Manual",
			button_property="",
			callback=lambda: self.main_window.switch_to_mode("manual"),
		)
		btn_row.addWidget(manual_card)

		mode_container.addLayout(btn_row)
		layout.addLayout(mode_container)
		layout.addStretch()

		self.log_panel = LogPanel()
		self.log_panel.setMinimumHeight(100)
		self.log_panel.setMaximumHeight(140)
		layout.addWidget(self.log_panel)

	def _create_mode_card(
		self,
		title: str,
		description: str,
		button_text: str,
		button_property: str,
		callback,
	) -> ClickableModeCard:
		card = ClickableModeCard(callback)
		card.setProperty("modeCard", True)
		card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		card.setFixedSize(280, 200)
		card.setCursor(Qt.CursorShape.PointingHandCursor)

		card_layout = QVBoxLayout(card)
		card_layout.setContentsMargins(24, 24, 24, 24)
		card_layout.setSpacing(16)

		title_label = QLabel(title)
		title_label.setObjectName("modeCardTitle")
		title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
		card_layout.addWidget(title_label)

		btn = QPushButton(button_text)
		btn.setObjectName("modeLaunchBtn")
		if button_property:
			btn.setProperty(button_property, True)
		btn.setMinimumHeight(44)
		btn.clicked.connect(callback)
		card_layout.addWidget(btn)

		desc_label = QLabel(description)
		desc_label.setObjectName("modeCardDesc")
		desc_label.setWordWrap(True)
		desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
		card_layout.addWidget(desc_label)

		return card


class SimulatorWidget(QWidget):
	def __init__(self, main_window: "MainWindow"):
		super().__init__()
		self.main_window = main_window
		self.config = main_window.config
		self.engine = self.main_window.engine
		self.bridge = self.main_window.bridge
		self._selected_connector_id: int = 1
		self._transaction_counter: int = 0

		self._setup_ui()

	def _setup_ui(self) -> None:
		main_layout = QVBoxLayout(self)
		main_layout.setSpacing(0)
		main_layout.setContentsMargins(0, 0, 0, 0)

		self.tabs = QTabWidget()
		self.tabs.setObjectName("mainTabs")
		main_layout.addWidget(self.tabs)

		dashboard_tab = QWidget()
		dashboard_layout = QVBoxLayout(dashboard_tab)
		dashboard_layout.setSpacing(0)
		dashboard_layout.setContentsMargins(0, 0, 0, 0)

		self.dashboard = SessionDashboard()
		self.dashboard.connector_selected.connect(self._on_connector_selected)
		self.dashboard.plug_in_clicked.connect(self.action_plug_in)
		self.dashboard.unplug_clicked.connect(self.action_unplug)
		self.dashboard.start_charging_clicked.connect(self.action_start_charging)
		self.dashboard.stop_charging_clicked.connect(self.action_stop_charging)
		self.dashboard.apply_id_tag_clicked.connect(self.action_apply_id_tag)
		dashboard_layout.addWidget(self.dashboard, 1)

		self.log_panel = CollapsibleLogPanel()
		self.log_panel.log_mode_toggled.connect(self.action_toggle_log_mode)
		dashboard_layout.addWidget(self.log_panel)

		self.tabs.addTab(dashboard_tab, "Dashboard")

		settings_tab = QWidget()
		settings_layout = QVBoxLayout(settings_tab)
		settings_layout.setSpacing(0)
		settings_layout.setContentsMargins(0, 0, 0, 0)

		self.settings_panel = SettingsPanel()
		self.settings_panel.set_engine(self.engine)
		self.settings_panel.set_config(self.config)
		self.settings_panel.set_connector_callbacks(
			on_apply=self._on_connector_apply,
			on_remove=self._on_connector_remove,
			on_add=self._on_connector_add,
		)
		self.settings_panel.save_config_clicked.connect(self.action_save_config)
		settings_layout.addWidget(self.settings_panel)

		settings_log = CollapsibleLogPanel()
		settings_log.log_mode_toggled.connect(self.action_toggle_log_mode)
		self._settings_log_panel = settings_log
		settings_layout.addWidget(settings_log)

		self.tabs.addTab(settings_tab, "Settings")

	def _on_connector_selected(self, connector_id: int) -> None:
		self._selected_connector_id = connector_id

	def _get_selected_connector(self):
		return self.engine.get_connector(self._selected_connector_id)

	def _ensure_valid_selection(self) -> None:
		if self.engine.get_connector(self._selected_connector_id) is None:
			if self.engine.connectors:
				self._selected_connector_id = self.engine.connectors[0].id
				self.dashboard.set_selected_connector(self._selected_connector_id)

	def update_ui(self) -> None:
		self._ensure_valid_selection()
		self.dashboard.update_from_engine(self.engine)

	def action_plug_in(self) -> None:
		for conn in self.engine.connectors:
			if conn.is_plugged_in and conn.id != self._selected_connector_id:
				self.engine.unplug(conn.id)
				self.log_panel.log_message(
					f"[yellow]UI:[/yellow] Auto-unplugged Connector {conn.id}"
				)
				self._settings_log_panel.log_message(
					f"[yellow]UI:[/yellow] Auto-unplugged Connector {conn.id}"
				)

		self.engine.plug_in(self._selected_connector_id)
		msg = f"[green]UI:[/green] Plugged In to Connector {self._selected_connector_id}"
		self.log_panel.log_message(msg)
		self._settings_log_panel.log_message(msg)

	def action_unplug(self) -> None:
		self.engine.unplug(self._selected_connector_id)
		msg = f"[yellow]UI:[/yellow] Unplugged from Connector {self._selected_connector_id}"
		self.log_panel.log_message(msg)
		self._settings_log_panel.log_message(msg)

	def action_start_charging(self) -> None:
		self._transaction_counter += 1
		temp_tx_id = self._transaction_counter
		self.engine.start_session(
			connector_id=self._selected_connector_id, transaction_id=temp_tx_id
		)
		msg = f"[green]UI:[/green] Started charging session on Connector {self._selected_connector_id}"
		self.log_panel.log_message(msg)
		self._settings_log_panel.log_message(msg)

	def action_stop_charging(self) -> None:
		self.engine.stop_session()
		msg = "[red]UI:[/red] Stopped charging session"
		self.log_panel.log_message(msg)
		self._settings_log_panel.log_message(msg)

	def action_apply_id_tag(self, id_tag: str) -> None:
		conn = self._get_selected_connector()
		if conn:
			conn.id_tag = id_tag
			msg = f"[green]UI:[/green] ID Tag set to: {id_tag} on Connector {self._selected_connector_id}"
			self.log_panel.log_message(msg)
			self._settings_log_panel.log_message(msg)

	def action_save_config(self) -> None:
		url = self.settings_panel.get_url()
		if url:
			try:
				parsed = urlparse(url)
				if parsed.scheme not in ("ws", "wss"):
					self._show_error("URL must start with ws:// or wss://")
					return
				if not parsed.netloc:
					self._show_error("Invalid URL format")
					return
			except Exception:
				self._show_error("Invalid URL format")
				return

		self.config.connectors = [
			ConnectorConfig(voltage=c.voltage, current=c.current, phase=c.phase)
			for c in self.engine.connectors
		]
		self.config.num_connectors = len(self.engine.connectors)
		self.config.save()
		msg = "[green]Config:[/green] Configuration saved."
		self.log_panel.log_message(msg)
		self._settings_log_panel.log_message(msg)

	def _show_error(self, message: str) -> None:
		msg = f"[red]Config:[/red] {message}"
		self.log_panel.log_message(msg)
		self._settings_log_panel.log_message(msg)

	def _on_connector_apply(
		self, connector_id: int, voltage: float, current: float, phase: int
	) -> None:
		error = self.engine.update_connector(connector_id, voltage, current, phase)
		if error:
			self._show_error(f"Connector: {error}")
		else:
			msg = (
				f"[green]Connector {connector_id}:[/green] Updated to "
				f"{voltage}V, {current}A, {phase}Ph"
			)
			self.log_panel.log_message(msg)
			self._settings_log_panel.log_message(msg)
			self._save_connector_config()

	def _save_connector_config(self) -> None:
		self.config.connectors = [
			ConnectorConfig(voltage=c.voltage, current=c.current, phase=c.phase)
			for c in self.engine.connectors
		]
		self.config.num_connectors = len(self.engine.connectors)
		self.config.save()

	def _on_connector_remove(self, connector_id: int) -> None:
		if len(self.engine.connectors) <= 1:
			self._show_error("Cannot remove the last connector")
			return

		if self.engine.session and self.engine.session.connector_id == connector_id:
			self._show_error("Cannot remove connector with active session")
			return

		self.engine.remove_connector(connector_id)
		self.settings_panel.rebuild_connector_cards()
		self._ensure_valid_selection()
		msg = f"[yellow]Connector:[/yellow] Removed connector {connector_id}"
		self.log_panel.log_message(msg)
		self._settings_log_panel.log_message(msg)
		self._save_connector_config()

	def _on_connector_add(self) -> None:
		connector = self.engine.add_connector()
		self.settings_panel.rebuild_connector_cards()
		self._selected_connector_id = connector.id
		self.dashboard.set_selected_connector(connector.id)
		msg = f"[green]Connector:[/green] Added connector {connector.id}"
		self.log_panel.log_message(msg)
		self._settings_log_panel.log_message(msg)
		self._save_connector_config()

	def action_toggle_log_mode(self, is_detailed: bool) -> None:
		self.main_window.signal_bridge.log_mode = "verbose" if is_detailed else "compact"

	def log_message(self, message: str) -> None:
		self.log_panel.log_message(message)
		self._settings_log_panel.log_message(message)


class ManualWidget(QWidget):
	def __init__(self, main_window: "MainWindow"):
		super().__init__()
		self.main_window = main_window
		self.config = SimulationConfig.load()
		self.engine = self.main_window.engine
		self.bridge = self.main_window.bridge
		self._setup_ui()

	def _setup_ui(self) -> None:
		layout = QHBoxLayout(self)
		layout.setSpacing(16)
		layout.setContentsMargins(16, 16, 16, 16)

		controls = QVBoxLayout()
		controls.setSpacing(12)
		layout.addLayout(controls, 3)

		controls_title = QLabel("Manual OCPP Controls")
		controls_title.setObjectName("sectionHeader")
		controls.addWidget(controls_title)

		basic_group = QFrame()
		basic_group.setProperty("controlGroup", True)
		basic_group.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		basic_layout = QVBoxLayout(basic_group)
		basic_layout.setSpacing(8)
		basic_layout.setContentsMargins(12, 12, 12, 12)

		self.btn_boot = QPushButton("BootNotification")
		self.btn_boot.setMinimumHeight(40)
		self.btn_boot.clicked.connect(self.action_boot)
		basic_layout.addWidget(self.btn_boot)

		self.btn_heartbeat = QPushButton("Heartbeat")
		self.btn_heartbeat.setMinimumHeight(40)
		self.btn_heartbeat.clicked.connect(self.action_heartbeat)
		basic_layout.addWidget(self.btn_heartbeat)

		self.btn_status = QPushButton("StatusNotification")
		self.btn_status.setMinimumHeight(40)
		self.btn_status.clicked.connect(self.action_status)
		basic_layout.addWidget(self.btn_status)
		controls.addWidget(basic_group)

		tx_group = QFrame()
		tx_group.setProperty("controlGroup", True)
		tx_group.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		tx_layout = QVBoxLayout(tx_group)
		tx_layout.setSpacing(8)
		tx_layout.setContentsMargins(12, 12, 12, 12)

		tx_title = QLabel("Transaction Control")
		tx_title.setObjectName("groupTitle")
		tx_layout.addWidget(tx_title)

		start_row = QHBoxLayout()
		self.btn_start = QPushButton("Start")
		self.btn_start.setProperty("success", True)
		self.btn_start.setMinimumHeight(40)
		self.btn_start.clicked.connect(self.action_start)
		self.input_tag = QLineEdit()
		self.input_tag.setPlaceholderText("ID Tag")
		start_row.addWidget(self.btn_start, 1)
		start_row.addWidget(self.input_tag, 2)
		tx_layout.addLayout(start_row)

		stop_row = QHBoxLayout()
		self.btn_stop = QPushButton("Stop")
		self.btn_stop.setProperty("danger", True)
		self.btn_stop.setMinimumHeight(40)
		self.btn_stop.clicked.connect(self.action_stop)
		self.input_tx_id = QLineEdit()
		self.input_tx_id.setPlaceholderText("TX ID")
		stop_row.addWidget(self.btn_stop, 1)
		stop_row.addWidget(self.input_tx_id, 2)
		tx_layout.addLayout(stop_row)
		controls.addWidget(tx_group)

		controls.addStretch()

		right_panel = QVBoxLayout()
		right_panel.setSpacing(8)
		layout.addLayout(right_panel, 7)

		self.log_panel = LogPanel()

		log_header = QHBoxLayout()
		log_title = QLabel("Activity Log")
		log_title.setObjectName("sectionHeader")
		log_header.addWidget(log_title)
		log_header.addStretch()

		self.btn_clear_logs = QPushButton("Clear")
		self.btn_clear_logs.setMinimumHeight(24)
		self.btn_clear_logs.clicked.connect(self.log_panel.clear)
		log_header.addWidget(self.btn_clear_logs)

		self.btn_log_mode = QPushButton("Detailed")
		self.btn_log_mode.setObjectName("btn_log_mode")
		self.btn_log_mode.setCheckable(True)
		self.btn_log_mode.setMinimumHeight(24)
		self.btn_log_mode.clicked.connect(self.action_toggle_log_mode)
		log_header.addWidget(self.btn_log_mode)
		right_panel.addLayout(log_header)

		right_panel.addWidget(self.log_panel)

	def action_toggle_log_mode(self) -> None:
		is_detailed = self.btn_log_mode.isChecked()
		if is_detailed:
			self.main_window.signal_bridge.log_mode = "verbose"
			self.btn_log_mode.setText("Compact")
		else:
			self.main_window.signal_bridge.log_mode = "compact"
			self.btn_log_mode.setText("Detailed")

	def action_boot(self) -> None:
		adapter = self.bridge.runner.adapter
		loop = self.bridge.runner.loop
		if adapter and loop:
			asyncio.run_coroutine_threadsafe(adapter.send_boot_notification(), loop)

	def action_heartbeat(self) -> None:
		adapter = self.bridge.runner.adapter
		loop = self.bridge.runner.loop
		if adapter and loop:
			asyncio.run_coroutine_threadsafe(adapter.send_heartbeat(), loop)

	def action_start(self) -> None:
		adapter = self.bridge.runner.adapter
		loop = self.bridge.runner.loop
		if adapter and loop:
			id_tag = self.input_tag.text() or "MANUAL_TAG"
			asyncio.run_coroutine_threadsafe(
				adapter.send_start_transaction(
					connector_id=1,
					id_tag=id_tag,
					meter_start=0,
					timestamp=datetime.now(timezone.utc).isoformat(),
				),
				loop,
			)

	def action_stop(self) -> None:
		adapter = self.bridge.runner.adapter
		loop = self.bridge.runner.loop
		if adapter and loop:
			tx_id_text = self.input_tx_id.text().strip()
			if tx_id_text:
				try:
					transaction_id = int(tx_id_text)
				except ValueError:
					self.log_panel.log_message("[red]UI:[/red] Invalid Transaction ID")
					return
			elif self.engine.session:
				transaction_id = self.engine.session.transaction_id
			else:
				transaction_id = 1

			meter_stop = (
				int(self.engine.energy_meter.get_meter_reading())
				if self.engine.energy_meter
				else 0
			)

			asyncio.run_coroutine_threadsafe(
				adapter.send_stop_transaction(
					meter_stop=meter_stop,
					timestamp=datetime.now(timezone.utc).isoformat(),
					transaction_id=transaction_id,
				),
				loop,
			)

	def action_status(self) -> None:
		adapter = self.bridge.runner.adapter
		loop = self.bridge.runner.loop
		if adapter and loop:
			asyncio.run_coroutine_threadsafe(
				adapter.send_status_notification(
					connector_id=1, error_code="NoError", status="Available"
				),
				loop,
			)

	def log_message(self, message: str) -> None:
		self.log_panel.log_message(message)


class MainWindow(QMainWindow):
	_accumulator: float = 0.0
	_last_tick_time: float = 0.0
	_status_check_counter: int = 0

	def __init__(self):
		super().__init__()
		self.setWindowTitle("ChargeGhost EVSE")
		self.setMinimumSize(800, 500)
		self.resize(1100, 700)

		self.config = SimulationConfig.load()
		self.engine = Engine()
		for connector_config in self.config.connectors:
			self.engine.add_connector(
				voltage=connector_config.voltage,
				current=connector_config.current,
				phase=connector_config.phase,
			)

		self.bridge = Bridge(
			self.engine,
			url=self.config.connection_url,
			charge_point_id=self.config.ocpp_id,
			password=self.config.ocpp_password,
			skip_tls_verify=self.config.skip_tls_verify,
			charge_point_model=self.config.charge_point_model,
			charge_point_vendor=self.config.charge_point_vendor,
		)
		self.bridge.setup()

		self.signal_bridge = QtSignalBridge(self.engine, self.bridge)
		self.signal_bridge.log_received.connect(self.on_log_received)
		self.signal_bridge.connection_status_changed.connect(
			self.on_connection_status_changed
		)

		self.stack = QStackedWidget()
		self.setCentralWidget(self.stack)

		self.mode_select = ModeSelectWidget(self)
		self.simulator = SimulatorWidget(self)
		self.manual = ManualWidget(self)

		self.stack.addWidget(self.mode_select)
		self.stack.addWidget(self.simulator)
		self.stack.addWidget(self.manual)

		self.stack.setCurrentWidget(self.mode_select)

		self.status_bar = QStatusBar()
		self.setStatusBar(self.status_bar)

		self._connection_indicator = QLabel("Disconnected")
		self._connection_indicator.setObjectName("connection_indicator")
		self._connection_indicator.setProperty("connected", False)
		self._connection_indicator.setAttribute(
			Qt.WidgetAttribute.WA_StyledBackground, True
		)
		self.status_bar.addPermanentWidget(self._connection_indicator)

		self._last_tick_time = time.monotonic()
		self.timer = QTimer()
		self.timer.timeout.connect(self.simulate_step)
		self.timer.start(100)

	def switch_to_mode(self, mode: str) -> None:
		if mode == "simulator":
			self.stack.setCurrentWidget(self.simulator)
		elif mode == "manual":
			self.stack.setCurrentWidget(self.manual)

	def simulate_step(self) -> None:
		current_time = time.monotonic()
		delta = current_time - self._last_tick_time
		self._last_tick_time = current_time
		self._accumulator += delta

		while self._accumulator >= 0.1:
			self.engine.simulate()
			self._accumulator -= 0.1

		self._status_check_counter += 1
		if self._status_check_counter >= 10:
			self._status_check_counter = 0
			self.signal_bridge.check_connection_status()

		if self.stack.currentWidget() == self.simulator:
			self.simulator.update_ui()

	@Slot(str, str, bool)
	def on_log_received(self, source: str, message: str, is_important: bool) -> None:
		if self.signal_bridge.log_mode == "compact" and not is_important:
			return

		source_colors = {
			"Engine": "yellow",
			"OCPP": "blue",
		}
		color = source_colors.get(source, "white")
		formatted_message = f"[{color}]{source}:[/] {message}"

		self.mode_select.log_panel.log_message(formatted_message)
		self.simulator.log_message(formatted_message)
		self.manual.log_message(formatted_message)

	@Slot(bool)
	def on_connection_status_changed(self, connected: bool) -> None:
		if connected:
			self._connection_indicator.setText("Connected")
			self._connection_indicator.setProperty("connected", True)
		else:
			self._connection_indicator.setText("Disconnected")
			self._connection_indicator.setProperty("connected", False)
		self._connection_indicator.style().unpolish(self._connection_indicator)
		self._connection_indicator.style().polish(self._connection_indicator)

	def closeEvent(self, event) -> None:
		self.config.connectors = [
			ConnectorConfig(voltage=c.voltage, current=c.current, phase=c.phase)
			for c in self.engine.connectors
		]
		self.config.num_connectors = len(self.engine.connectors)
		self.config.save()
		self.bridge.shutdown()
		event.accept()


def main() -> None:
	app = QApplication(sys.argv)

	if STYLES_PATH.exists():
		with open(STYLES_PATH, "r", encoding="utf-8") as f:
			app.setStyleSheet(f.read())

	window = MainWindow()
	window.show()
	sys.exit(app.exec())


if __name__ == "__main__":
	main()
