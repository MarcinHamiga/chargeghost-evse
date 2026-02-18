import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.ui.bridge import QtSignalBridge
from chargeghost_evse.ui.widgets.log_panel import LogPanel
from chargeghost_evse.ui.widgets.status_panel import StatusPanel
from chargeghost_evse.util.config import SimulationConfig

STYLES_PATH = Path(__file__).parent / "styles" / "e_mobility.qss"


class ModeSelectWidget(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 40, 40, 40)

        title = QLabel("⚡ ChargeGhost EVSE")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Electric Vehicle Supply Equipment Simulator")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        mode_label = QLabel("Select Mode")
        mode_label.setObjectName("sectionHeader")
        mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(mode_label)

        btn_container = QVBoxLayout()
        btn_container.setSpacing(12)

        sim_btn = QPushButton("🔌  Simulator Mode")
        sim_btn.setObjectName("sim_btn")
        sim_btn.setProperty("primary", True)
        sim_btn.setMinimumWidth(240)
        sim_btn.setMinimumHeight(48)
        sim_btn.clicked.connect(lambda: self.main_window.switch_to_mode("simulator"))
        btn_container.addWidget(sim_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        manual_btn = QPushButton("🔧  Manual Mode")
        manual_btn.setObjectName("manual_btn")
        manual_btn.setMinimumWidth(240)
        manual_btn.setMinimumHeight(48)
        manual_btn.clicked.connect(lambda: self.main_window.switch_to_mode("manual"))
        btn_container.addWidget(manual_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addLayout(btn_container)

        self.log_panel = LogPanel()
        self.log_panel.setMinimumHeight(120)
        self.log_panel.setMaximumHeight(180)
        layout.addWidget(self.log_panel, stretch=1)


class SimulatorWidget(QWidget):
    """
    Simulator mode widget for ChargeGhost EVSE.

    Note: This implementation currently supports single-connector operation.
    While the engine supports multiple connectors, the UI controls and session
    details display operate on connector 0 (the first connector). Future
    versions may add multi-connector support with connector selection.
    """

    _transaction_counter: int = 0

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.config = SimulationConfig.load()
        self.engine = self.main_window.engine
        self.bridge = self.main_window.bridge

        self.setup_ui()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(16, 16, 16, 16)

        left_panel = QVBoxLayout()
        left_panel.setSpacing(12)
        main_layout.addLayout(left_panel, 3)

        controls_title = QLabel("⚡ Controls")
        controls_title.setObjectName("sectionHeader")
        left_panel.addWidget(controls_title, alignment=Qt.AlignmentFlag.AlignLeft)

        self.tabs = QTabWidget()
        left_panel.addWidget(self.tabs)

        controls_tab = QWidget()
        controls_layout = QVBoxLayout(controls_tab)
        controls_layout.setSpacing(12)

        self.btn_plug = QPushButton("🔌  Plug In")
        self.btn_plug.setObjectName("btn_plug")
        self.btn_plug.setProperty("primary", True)
        self.btn_plug.setMinimumHeight(40)
        self.btn_plug.clicked.connect(self.action_plug_in)
        controls_layout.addWidget(self.btn_plug)

        self.btn_swipe = QPushButton("💳  Swipe Card")
        self.btn_swipe.setObjectName("btn_swipe")
        self.btn_swipe.setProperty("success", True)
        self.btn_swipe.setMinimumHeight(40)
        self.btn_swipe.clicked.connect(self.action_swipe_card)
        controls_layout.addWidget(self.btn_swipe)

        self.btn_unplug = QPushButton("⚡  Unplug")
        self.btn_unplug.setObjectName("btn_unplug")
        self.btn_unplug.setProperty("danger", True)
        self.btn_unplug.setMinimumHeight(40)
        self.btn_unplug.clicked.connect(self.action_unplug)
        controls_layout.addWidget(self.btn_unplug)

        self.status_panel = StatusPanel()
        controls_layout.addWidget(self.status_panel)

        self.tabs.addTab(controls_tab, "Controls")

        config_tab = QWidget()
        config_layout = QFormLayout(config_tab)
        config_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        config_layout.setSpacing(12)
        config_layout.setContentsMargins(8, 16, 8, 8)

        self.input_url = QLineEdit()
        self.input_url.setMinimumWidth(200)
        self.input_url.setPlaceholderText("ws://example.com/ocpp")
        self.input_url.setText(self.config.connection_url)
        config_layout.addRow("Connection URL:", self.input_url)

        self.input_ocpp_id = QLineEdit()
        self.input_ocpp_id.setMinimumWidth(200)
        self.input_ocpp_id.setPlaceholderText("CP-001")
        self.input_ocpp_id.setText(self.config.ocpp_id)
        config_layout.addRow("OCPP ID:", self.input_ocpp_id)

        self.input_password = QLineEdit()
        self.input_password.setMinimumWidth(200)
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.setPlaceholderText("Optional")
        self.input_password.setText(self.config.ocpp_password)
        config_layout.addRow("OCPP Password:", self.input_password)

        self.input_model = QLineEdit()
        self.input_model.setMinimumWidth(200)
        self.input_model.setPlaceholderText("ChargeGhostV1")
        self.input_model.setText(self.config.charge_point_model)
        config_layout.addRow("Model:", self.input_model)

        self.input_vendor = QLineEdit()
        self.input_vendor.setMinimumWidth(200)
        self.input_vendor.setPlaceholderText("ChargeGhost")
        self.input_vendor.setText(self.config.charge_point_vendor)
        config_layout.addRow("Vendor:", self.input_vendor)

        self.input_connectors = QLineEdit()
        self.input_connectors.setMinimumWidth(200)
        self.input_connectors.setPlaceholderText("1")
        self.input_connectors.setText(str(self.config.num_connectors))
        config_layout.addRow("Connectors:", self.input_connectors)

        self.checkbox_skip_tls = QCheckBox("Skip TLS Verification")
        self.checkbox_skip_tls.setChecked(self.config.skip_tls_verify)
        config_layout.addRow(self.checkbox_skip_tls)

        self.btn_save_config = QPushButton("💾  Save Configuration")
        self.btn_save_config.setObjectName("btn_save_config")
        self.btn_save_config.setProperty("primary", True)
        self.btn_save_config.setMinimumHeight(36)
        self.btn_save_config.clicked.connect(self.action_save_config)
        config_layout.addRow(self.btn_save_config)

        self.tabs.addTab(config_tab, "Config")

        session_tab = QWidget()
        session_scroll = QScrollArea()
        session_scroll.setWidgetResizable(True)
        session_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        session_content = QWidget()
        session_layout = QVBoxLayout(session_content)
        session_layout.setSpacing(8)
        session_layout.setContentsMargins(8, 8, 8, 8)

        id_tag_header = QLabel("ID Tag")
        id_tag_header.setObjectName("sectionHeader")
        session_layout.addWidget(id_tag_header)

        self.input_id_tag = QLineEdit()
        self.input_id_tag.setPlaceholderText("Enter ID Tag")
        session_layout.addWidget(self.input_id_tag)

        self.btn_apply_id_tag = QPushButton("Apply ID Tag")
        self.btn_apply_id_tag.setMinimumHeight(32)
        self.btn_apply_id_tag.clicked.connect(self.action_apply_id_tag)
        session_layout.addWidget(self.btn_apply_id_tag)

        conn_header = QLabel("🔌 Connector")
        conn_header.setObjectName("sectionHeader")
        session_layout.addWidget(conn_header)

        self.lbl_conn_status = QLabel("Status: --")
        self.lbl_conn_status.setObjectName("sessionLabel")
        session_layout.addWidget(self.lbl_conn_status)

        self.lbl_conn_plugged = QLabel("Plugged: --")
        self.lbl_conn_plugged.setObjectName("sessionLabel")
        session_layout.addWidget(self.lbl_conn_plugged)

        self.lbl_conn_voltage = QLabel("Voltage: -- V")
        self.lbl_conn_voltage.setObjectName("sessionLabel")
        session_layout.addWidget(self.lbl_conn_voltage)

        self.lbl_conn_current = QLabel("Current: -- A")
        self.lbl_conn_current.setObjectName("sessionLabel")
        session_layout.addWidget(self.lbl_conn_current)

        self.lbl_conn_phase = QLabel("Phase: --")
        self.lbl_conn_phase.setObjectName("sessionLabel")
        session_layout.addWidget(self.lbl_conn_phase)

        session_header = QLabel("⚡ Session")
        session_header.setObjectName("sectionHeader")
        session_layout.addWidget(session_header)

        self.lbl_session_tx_id = QLabel("Transaction ID: --")
        self.lbl_session_tx_id.setObjectName("sessionLabel")
        session_layout.addWidget(self.lbl_session_tx_id)

        self.lbl_session_conn_id = QLabel("Connector ID: --")
        self.lbl_session_conn_id.setObjectName("sessionLabel")
        session_layout.addWidget(self.lbl_session_conn_id)

        self.lbl_session_id_tag = QLabel("ID Tag: --")
        self.lbl_session_id_tag.setObjectName("sessionLabel")
        session_layout.addWidget(self.lbl_session_id_tag)

        self.lbl_session_energy = QLabel("Energy Charged: -- Wh")
        self.lbl_session_energy.setObjectName("sessionLabel")
        session_layout.addWidget(self.lbl_session_energy)

        self.lbl_session_soc = QLabel("State of Charge: --%")
        self.lbl_session_soc.setObjectName("sessionLabel")
        session_layout.addWidget(self.lbl_session_soc)

        self.lbl_session_max = QLabel("Max Energy: -- Wh")
        self.lbl_session_max.setObjectName("sessionLabel")
        session_layout.addWidget(self.lbl_session_max)

        self.lbl_session_duration = QLabel("Duration: --")
        self.lbl_session_duration.setObjectName("sessionLabel")
        session_layout.addWidget(self.lbl_session_duration)

        meter_header = QLabel("📊 Energy Meter")
        meter_header.setObjectName("sectionHeader")
        session_layout.addWidget(meter_header)

        self.lbl_meter_reading = QLabel("Reading: -- Wh")
        self.lbl_meter_reading.setObjectName("sessionLabel")
        session_layout.addWidget(self.lbl_meter_reading)

        self.lbl_meter_charging = QLabel("Charging: --")
        self.lbl_meter_charging.setObjectName("sessionLabel")
        session_layout.addWidget(self.lbl_meter_charging)

        session_layout.addStretch()
        session_scroll.setWidget(session_content)
        session_tab_layout = QVBoxLayout(session_tab)
        session_tab_layout.setContentsMargins(0, 0, 0, 0)
        session_tab_layout.addWidget(session_scroll)

        self.tabs.addTab(session_tab, "Session")

        right_panel = QVBoxLayout()
        right_panel.setSpacing(8)
        main_layout.addLayout(right_panel, 7)

        log_header = QHBoxLayout()
        log_title = QLabel("📋 Activity Log")
        log_title.setObjectName("sectionHeader")
        log_header.addWidget(log_title)
        log_header.addStretch()

        self.btn_log_mode = QPushButton("Detailed")
        self.btn_log_mode.setObjectName("btn_log_mode")
        self.btn_log_mode.setCheckable(True)
        self.btn_log_mode.setMinimumHeight(24)
        self.btn_log_mode.clicked.connect(self.action_toggle_log_mode)
        log_header.addWidget(self.btn_log_mode)
        right_panel.addLayout(log_header)

        self.log_panel = LogPanel()
        right_panel.addWidget(self.log_panel)

    def update_ui(self):
        self.status_panel.update_status(self.engine)
        self._update_session_details()

        if self.engine.connectors:
            conn = self.engine.connectors[0]
            self.btn_plug.setEnabled(not conn.is_plugged_in)
            self.btn_unplug.setEnabled(conn.is_plugged_in)
            self.btn_swipe.setEnabled(conn.is_plugged_in)

    def _update_session_details(self):
        if self.engine.connectors:
            conn = self.engine.connectors[0]
            self.lbl_conn_status.setText(f"Status: {conn.status.value}")
            self.lbl_conn_plugged.setText(
                f"Plugged: {'Yes' if conn.is_plugged_in else 'No'}"
            )
            self.lbl_conn_voltage.setText(f"Voltage: {conn.voltage:.1f} V")
            self.lbl_conn_current.setText(f"Current: {conn.current:.1f} A")
            self.lbl_conn_phase.setText(f"Phase: {conn.phase}")

        session = self.engine.session
        if session:
            self.lbl_session_tx_id.setText(f"Transaction ID: {session.transaction_id}")
            self.lbl_session_conn_id.setText(f"Connector ID: {session.connector_id}")
            self.lbl_session_id_tag.setText(f"ID Tag: {session.id_tag or '--'}")
            self.lbl_session_energy.setText(
                f"Energy Charged: {session.energy_charged:.3f} Wh"
            )
            self.lbl_session_soc.setText(
                f"State of Charge: {session.state_of_charge:.2f}%"
            )
            self.lbl_session_max.setText(f"Max Energy: {session.max_energy:.3f} Wh")
            duration = time.monotonic() - session.start_time
            self.lbl_session_duration.setText(f"Duration: {duration:.1f} s")
        else:
            self.lbl_session_tx_id.setText("Transaction ID: --")
            self.lbl_session_conn_id.setText("Connector ID: --")
            self.lbl_session_id_tag.setText("ID Tag: --")
            self.lbl_session_energy.setText("Energy Charged: -- Wh")
            self.lbl_session_soc.setText("State of Charge: --%")
            self.lbl_session_max.setText("Max Energy: -- Wh")
            self.lbl_session_duration.setText("Duration: --")

        meter = self.engine.energy_meter
        self.lbl_meter_reading.setText(f"Reading: {meter.get_meter_reading():.3f} Wh")
        self.lbl_meter_charging.setText(
            f"Charging: {'Yes' if meter.is_charging else 'No'}"
        )

    def action_plug_in(self):
        self.engine.plug_in(0)
        self.log_panel.log_message("[green]UI:[/green] Plugged In")

    def action_unplug(self):
        self.engine.unplug(0)
        self.log_panel.log_message("[yellow]UI:[/yellow] Unplugged")

    def action_swipe_card(self):
        if not self.engine.session:
            SimulatorWidget._transaction_counter += 1
            temp_tx_id = SimulatorWidget._transaction_counter
            self.engine.start_session(connector_id=0, transaction_id=temp_tx_id)
            self.log_panel.log_message(
                "[green]UI:[/green] Swiped Card - Requesting Start Session"
            )
        else:
            self.engine.stop_session()
            self.log_panel.log_message(
                "[red]UI:[/red] Swiped Card - Requesting Stop Session"
            )

    def action_apply_id_tag(self):
        id_tag = self.input_id_tag.text().strip()
        if id_tag and self.engine.connectors:
            self.engine.connectors[0].id_tag = id_tag
            self.log_panel.log_message(f"[green]UI:[/green] ID Tag set to: {id_tag}")
        elif not id_tag:
            self.log_panel.log_message("[yellow]UI:[/yellow] Please enter an ID Tag")

    def action_save_config(self):
        url = self.input_url.text().strip()
        if url:
            try:
                parsed = urlparse(url)
                if parsed.scheme not in ("ws", "wss"):
                    self.log_panel.log_message(
                        "[red]Config:[/red] URL must start with ws:// or wss://"
                    )
                    return
                if not parsed.netloc:
                    self.log_panel.log_message("[red]Config:[/red] Invalid URL format")
                    return
            except Exception:
                self.log_panel.log_message("[red]Config:[/red] Invalid URL format")
                return

        self.config.connection_url = url
        self.config.ocpp_id = self.input_ocpp_id.text()
        self.config.ocpp_password = self.input_password.text()
        self.config.charge_point_model = self.input_model.text() or "ChargeGhostV1"
        self.config.charge_point_vendor = self.input_vendor.text() or "ChargeGhost"
        try:
            num_connectors = int(self.input_connectors.text() or "1")
            if num_connectors < 1:
                self.log_panel.log_message(
                    "[red]Config:[/red] Connectors must be at least 1"
                )
                return
            self.config.num_connectors = num_connectors
        except ValueError:
            self.log_panel.log_message(
                "[red]Config:[/red] Invalid number of connectors"
            )
            return
        self.config.skip_tls_verify = self.checkbox_skip_tls.isChecked()
        self.config.save()
        self.log_panel.log_message("[green]Config:[/green] Configuration saved.")

    def action_toggle_log_mode(self):
        is_detailed = self.btn_log_mode.isChecked()
        if is_detailed:
            self.main_window.signal_bridge.log_mode = "verbose"
            self.btn_log_mode.setText("Compact")
        else:
            self.main_window.signal_bridge.log_mode = "compact"
            self.btn_log_mode.setText("Detailed")


class ManualWidget(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.config = SimulationConfig.load()
        self.engine = self.main_window.engine
        self.bridge = self.main_window.bridge
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        controls = QVBoxLayout()
        controls.setSpacing(12)
        layout.addLayout(controls, 3)

        controls_title = QLabel("🔧 Manual OCPP Controls")
        controls_title.setObjectName("sectionHeader")
        controls.addWidget(controls_title)

        self.btn_boot = QPushButton("📤  BootNotification")
        self.btn_boot.setMinimumHeight(40)
        self.btn_boot.clicked.connect(self.action_boot)
        controls.addWidget(self.btn_boot)

        self.btn_heartbeat = QPushButton("💓  Heartbeat")
        self.btn_heartbeat.setMinimumHeight(40)
        self.btn_heartbeat.clicked.connect(self.action_heartbeat)
        controls.addWidget(self.btn_heartbeat)

        start_row = QHBoxLayout()
        start_row.setSpacing(8)
        self.btn_start = QPushButton("▶️  Start")
        self.btn_start.setProperty("success", True)
        self.btn_start.setMinimumHeight(40)
        self.btn_start.clicked.connect(self.action_start)
        self.input_tag = QLineEdit()
        self.input_tag.setPlaceholderText("ID Tag")
        start_row.addWidget(self.btn_start)
        start_row.addWidget(self.input_tag)
        controls.addLayout(start_row)

        stop_row = QHBoxLayout()
        stop_row.setSpacing(8)
        self.btn_stop = QPushButton("⏹️  Stop")
        self.btn_stop.setProperty("danger", True)
        self.btn_stop.setMinimumHeight(40)
        self.btn_stop.clicked.connect(self.action_stop)
        self.input_tx_id = QLineEdit()
        self.input_tx_id.setPlaceholderText("Transaction ID")
        stop_row.addWidget(self.btn_stop)
        stop_row.addWidget(self.input_tx_id)
        controls.addLayout(stop_row)

        self.btn_status = QPushButton("📡  StatusNotification")
        self.btn_status.setMinimumHeight(40)
        self.btn_status.clicked.connect(self.action_status)
        controls.addWidget(self.btn_status)

        controls.addStretch()

        right_panel = QVBoxLayout()
        right_panel.setSpacing(8)
        layout.addLayout(right_panel, 7)

        log_header = QHBoxLayout()
        log_title = QLabel("📋 Activity Log")
        log_title.setObjectName("sectionHeader")
        log_header.addWidget(log_title)
        log_header.addStretch()

        self.btn_log_mode = QPushButton("Detailed")
        self.btn_log_mode.setObjectName("btn_log_mode")
        self.btn_log_mode.setCheckable(True)
        self.btn_log_mode.setMinimumHeight(24)
        self.btn_log_mode.clicked.connect(self.action_toggle_log_mode)
        log_header.addWidget(self.btn_log_mode)
        right_panel.addLayout(log_header)

        self.log_panel = LogPanel()
        right_panel.addWidget(self.log_panel)

    def action_toggle_log_mode(self):
        is_detailed = self.btn_log_mode.isChecked()
        if is_detailed:
            self.main_window.signal_bridge.log_mode = "verbose"
            self.btn_log_mode.setText("Compact")
        else:
            self.main_window.signal_bridge.log_mode = "compact"
            self.btn_log_mode.setText("Detailed")

    def action_boot(self):
        adapter = self.bridge.runner.adapter
        loop = self.bridge.runner.loop
        if adapter and loop:
            asyncio.run_coroutine_threadsafe(adapter.send_boot_notification(), loop)

    def action_heartbeat(self):
        adapter = self.bridge.runner.adapter
        loop = self.bridge.runner.loop
        if adapter and loop:
            asyncio.run_coroutine_threadsafe(adapter.send_heartbeat(), loop)

    def action_start(self):
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

    def action_stop(self):
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

    def action_status(self):
        adapter = self.bridge.runner.adapter
        loop = self.bridge.runner.loop
        if adapter and loop:
            asyncio.run_coroutine_threadsafe(
                adapter.send_status_notification(
                    connector_id=1, error_code="NoError", status="Available"
                ),
                loop,
            )


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
        for _ in range(self.config.num_connectors):
            self.engine.add_connector()

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

        self._connection_indicator = QLabel("● Disconnected")
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

    def switch_to_mode(self, mode):
        if mode == "simulator":
            self.stack.setCurrentWidget(self.simulator)
        elif mode == "manual":
            self.stack.setCurrentWidget(self.manual)

    def simulate_step(self):
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
    def on_log_received(self, source, message, is_important):
        if self.signal_bridge.log_mode == "compact" and not is_important:
            return

        source_colors = {
            "Engine": "yellow",
            "OCPP": "blue",
        }
        color = source_colors.get(source, "white")
        formatted_message = f"[{color}]{source}:[/] {message}"

        self.mode_select.log_panel.log_message(formatted_message)
        self.simulator.log_panel.log_message(formatted_message)
        self.manual.log_panel.log_message(formatted_message)

    @Slot(bool)
    def on_connection_status_changed(self, connected: bool):
        if connected:
            self._connection_indicator.setText("● Connected")
            self._connection_indicator.setProperty("connected", True)
        else:
            self._connection_indicator.setText("● Disconnected")
            self._connection_indicator.setProperty("connected", False)
        self._connection_indicator.style().unpolish(self._connection_indicator)
        self._connection_indicator.style().polish(self._connection_indicator)

    def closeEvent(self, event):
        self.bridge.shutdown()
        event.accept()


def main():
    app = QApplication(sys.argv)

    if STYLES_PATH.exists():
        with open(STYLES_PATH, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
