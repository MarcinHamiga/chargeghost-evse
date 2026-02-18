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
    QGridLayout,
    QGroupBox,
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
    QFrame,
    QProgressBar,
)

from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.ui.bridge import QtSignalBridge
from chargeghost_evse.ui.widgets.connector_panel import ConnectorPanel
from chargeghost_evse.ui.widgets.log_panel import LogPanel
from chargeghost_evse.ui.widgets.status_panel import StatusPanel
from chargeghost_evse.util.config import ConnectorConfig, SimulationConfig

STYLES_PATH = Path(__file__).parent / "styles" / "e_mobility.qss"


class MetricCard(QFrame):
    def __init__(self, title: str, unit: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setProperty("card", True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(160)
        self.setMinimumHeight(80)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(12, 12, 12, 12)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600; text-transform: uppercase;")
        layout.addWidget(self.title_label)

        value_layout = QHBoxLayout()
        self.value_label = QLabel("--")
        self.value_label.setObjectName("metricValue")
        self.value_label.setStyleSheet("color: #1EAD98; font-size: 18px; font-weight: 700; font-family: 'JetBrains Mono', monospace;")
        value_layout.addWidget(self.value_label)

        if unit:
            self.unit_label = QLabel(unit)
            self.unit_label.setStyleSheet("color: #6e7681; font-size: 12px; font-weight: 500; margin-bottom: -4px;")
            value_layout.addWidget(self.unit_label, alignment=Qt.AlignmentFlag.AlignBottom)
        
        value_layout.addStretch()
        layout.addLayout(value_layout)

    def set_value(self, value: str):
        self.value_label.setText(value)


class ModeSelectWidget(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(40)
        layout.setContentsMargins(40, 40, 40, 40)

        header_container = QVBoxLayout()
        header_container.setSpacing(10)

        title = QLabel("⚡ ChargeGhost EVSE")
        title.setObjectName("mainTitle")
        title.setStyleSheet("font-size: 42px; font-weight: 800; color: #1EAD98; margin-bottom: 0px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_container.addWidget(title)

        subtitle = QLabel("Electric Vehicle Supply Equipment Simulator")
        subtitle.setObjectName("mainSubtitle")
        subtitle.setStyleSheet("font-size: 16px; color: #8b949e; font-weight: 400;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_container.addWidget(subtitle)
        
        layout.addLayout(header_container)

        mode_container = QVBoxLayout()
        mode_container.setSpacing(24)
        
        mode_label = QLabel("Select Simulation Mode")
        mode_label.setStyleSheet("color: #e6edf3; font-size: 14px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px;")
        mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mode_container.addWidget(mode_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(20)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sim_card = QFrame()
        sim_card.setProperty("card", True)
        sim_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sim_card.setFixedSize(280, 200)
        sim_layout = QVBoxLayout(sim_card)
        sim_layout.setContentsMargins(24, 24, 24, 24)
        sim_layout.setSpacing(16)
        
        sim_icon = QLabel("🔌")
        sim_icon.setStyleSheet("font-size: 48px;")
        sim_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sim_layout.addWidget(sim_icon)

        sim_btn = QPushButton("Simulator Mode")
        sim_btn.setObjectName("sim_btn")
        sim_btn.setProperty("primary", True)
        sim_btn.setMinimumHeight(44)
        sim_btn.clicked.connect(lambda: self.main_window.switch_to_mode("simulator"))
        sim_layout.addWidget(sim_btn)
        
        sim_desc = QLabel("Full autonomous simulation with OCPP integration")
        sim_desc.setWordWrap(True)
        sim_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sim_desc.setStyleSheet("color: #8b949e; font-size: 12px;")
        sim_layout.addWidget(sim_desc)
        
        btn_row.addWidget(sim_card)

        manual_card = QFrame()
        manual_card.setProperty("card", True)
        manual_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        manual_card.setFixedSize(280, 200)
        manual_layout = QVBoxLayout(manual_card)
        manual_layout.setContentsMargins(24, 24, 24, 24)
        manual_layout.setSpacing(16)

        manual_icon = QLabel("🔧")
        manual_icon.setStyleSheet("font-size: 48px;")
        manual_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        manual_layout.addWidget(manual_icon)

        manual_btn = QPushButton("Manual Mode")
        manual_btn.setObjectName("manual_btn")
        manual_btn.setMinimumHeight(44)
        manual_btn.clicked.connect(lambda: self.main_window.switch_to_mode("manual"))
        manual_layout.addWidget(manual_btn)

        manual_desc = QLabel("Raw OCPP message control and protocol debugging")
        manual_desc.setWordWrap(True)
        manual_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        manual_desc.setStyleSheet("color: #8b949e; font-size: 12px;")
        manual_layout.addWidget(manual_desc)

        btn_row.addWidget(manual_card)
        mode_container.addLayout(btn_row)
        
        layout.addLayout(mode_container)
        layout.addStretch()

        self.log_panel = LogPanel()
        self.log_panel.setMinimumHeight(100)
        self.log_panel.setMaximumHeight(140)
        layout.addWidget(self.log_panel)


class SimulatorWidget(QWidget):
    _transaction_counter: int = 0

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.config = SimulationConfig.load()
        self.engine = self.main_window.engine
        self.bridge = self.main_window.bridge
        self._selected_connector_id: int = 1

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

        # -- CONTROLS TAB --
        controls_tab = QWidget()
        controls_layout = QVBoxLayout(controls_tab)
        controls_layout.setSpacing(12)
        controls_layout.setContentsMargins(12, 12, 12, 12)

        self.btn_plug = QPushButton("🔌  Plug In")
        self.btn_plug.setObjectName("btn_plug")
        self.btn_plug.setProperty("primary", True)
        self.btn_plug.setMinimumHeight(44)
        self.btn_plug.clicked.connect(self.action_plug_in)
        controls_layout.addWidget(self.btn_plug)

        self.btn_swipe = QPushButton("💳  Start Charging")
        self.btn_swipe.setObjectName("btn_swipe")
        self.btn_swipe.setProperty("success", True)
        self.btn_swipe.setMinimumHeight(44)
        self.btn_swipe.clicked.connect(self.action_swipe_card)
        controls_layout.addWidget(self.btn_swipe)

        self.btn_unplug = QPushButton("⏏  Unplug")
        self.btn_unplug.setObjectName("btn_unplug")
        self.btn_unplug.setProperty("danger", True)
        self.btn_unplug.setMinimumHeight(44)
        self.btn_unplug.clicked.connect(self.action_unplug)
        controls_layout.addWidget(self.btn_unplug)

        self.status_panel = StatusPanel()
        self.status_panel.on_connector_selected.connect(self._on_connector_panel_select)
        controls_layout.addWidget(self.status_panel)
        controls_layout.addStretch()

        self.tabs.addTab(controls_tab, "Controls")

        # -- CONNECTORS TAB --
        connectors_tab = QWidget()
        connectors_layout = QVBoxLayout(connectors_tab)
        connectors_layout.setSpacing(8)
        connectors_layout.setContentsMargins(8, 8, 8, 8)

        self.connector_panel = ConnectorPanel()
        self.connector_panel.set_engine(self.engine)
        self.connector_panel.set_callbacks(
            on_apply=self._on_connector_apply,
            on_remove=self._on_connector_remove,
            on_add=self._on_connector_add,
        )
        connectors_layout.addWidget(self.connector_panel)

        self.tabs.addTab(connectors_tab, "Connectors")

        # -- CONFIG TAB --
        config_tab = QWidget()
        config_scroll = QScrollArea()
        config_scroll.setWidgetResizable(True)
        config_content = QWidget()
        config_layout = QVBoxLayout(config_content)
        config_layout.setSpacing(16)
        config_layout.setContentsMargins(12, 12, 12, 12)

        # Connection Group
        conn_group = QGroupBox("Connection Settings")
        conn_form = QFormLayout(conn_group)
        conn_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        
        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("ws://example.com/ocpp")
        self.input_url.setText(self.config.connection_url)
        conn_form.addRow("URL:", self.input_url)

        self.input_ocpp_id = QLineEdit()
        self.input_ocpp_id.setPlaceholderText("CP-001")
        self.input_ocpp_id.setText(self.config.ocpp_id)
        conn_form.addRow("OCPP ID:", self.input_ocpp_id)

        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.setPlaceholderText("Optional")
        self.input_password.setText(self.config.ocpp_password)
        conn_form.addRow("Password:", self.input_password)
        
        self.checkbox_skip_tls = QCheckBox("Skip TLS Verification")
        self.checkbox_skip_tls.setChecked(self.config.skip_tls_verify)
        conn_form.addRow(self.checkbox_skip_tls)
        config_layout.addWidget(conn_group)

        # Identity Group
        ident_group = QGroupBox("Station Identity")
        ident_form = QFormLayout(ident_group)
        
        self.input_model = QLineEdit()
        self.input_model.setPlaceholderText("ChargeGhostV1")
        self.input_model.setText(self.config.charge_point_model)
        ident_form.addRow("Model:", self.input_model)

        self.input_vendor = QLineEdit()
        self.input_vendor.setPlaceholderText("ChargeGhost")
        self.input_vendor.setText(self.config.charge_point_vendor)
        ident_form.addRow("Vendor:", self.input_vendor)
        config_layout.addWidget(ident_group)

        self.btn_save_config = QPushButton("💾  Save Configuration")
        self.btn_save_config.setObjectName("btn_save_config")
        self.btn_save_config.setProperty("primary", True)
        self.btn_save_config.setMinimumHeight(40)
        self.btn_save_config.clicked.connect(self.action_save_config)
        config_layout.addWidget(self.btn_save_config)

        config_layout.addStretch()
        config_scroll.setWidget(config_content)
        config_tab_layout = QVBoxLayout(config_tab)
        config_tab_layout.setContentsMargins(0, 0, 0, 0)
        config_tab_layout.addWidget(config_scroll)
        self.tabs.addTab(config_tab, "Config")

        # -- SESSION TAB (DASHBOARD) --
        session_tab = QWidget()
        session_layout = QVBoxLayout(session_tab)
        session_layout.setSpacing(16)
        session_layout.setContentsMargins(12, 12, 12, 12)

        # ID Tag Section
        tag_container = QFrame()
        tag_container.setProperty("card", True)
        tag_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        tag_layout = QHBoxLayout(tag_container)
        tag_layout.setContentsMargins(12, 8, 12, 8)
        tag_layout.addWidget(QLabel("👤 ID Tag:"))
        self.input_id_tag = QLineEdit()
        self.input_id_tag.setPlaceholderText("Enter tag (e.g. RFID-001)")
        tag_layout.addWidget(self.input_id_tag)
        self.btn_apply_id_tag = QPushButton("Apply")
        self.btn_apply_id_tag.clicked.connect(self.action_apply_id_tag)
        tag_layout.addWidget(self.btn_apply_id_tag)
        session_layout.addWidget(tag_container)

        # Dashboard Grid
        dash_scroll = QScrollArea()
        dash_scroll.setWidgetResizable(True)
        dash_content = QWidget()
        dash_layout = QVBoxLayout(dash_content)
        dash_layout.setSpacing(16)
        
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(12)
        
        self.metric_tx_id = MetricCard("Transaction ID")
        self.metric_energy = MetricCard("Energy Charged", "Wh")
        self.metric_soc = MetricCard("State of Charge", "%")
        self.metric_duration = MetricCard("Session Duration", "s")
        self.metric_voltage = MetricCard("Voltage", "V")
        self.metric_current = MetricCard("Current", "A")
        self.metric_power = MetricCard("Current Power", "kW")
        self.metric_meter = MetricCard("Total Meter", "Wh")

        metrics_grid.addWidget(self.metric_tx_id, 0, 0)
        metrics_grid.addWidget(self.metric_duration, 0, 1)
        metrics_grid.addWidget(self.metric_energy, 1, 0)
        metrics_grid.addWidget(self.metric_soc, 1, 1)
        metrics_grid.addWidget(self.metric_power, 2, 0)
        metrics_grid.addWidget(self.metric_meter, 2, 1)
        metrics_grid.addWidget(self.metric_voltage, 3, 0)
        metrics_grid.addWidget(self.metric_current, 3, 1)
        
        dash_layout.addLayout(metrics_grid)

        # SoC Progress Bar
        soc_group = QGroupBox("State of Charge")
        soc_group_layout = QVBoxLayout(soc_group)
        self.session_progress = QProgressBar()
        self.session_progress.setMinimumHeight(24)
        soc_group_layout.addWidget(self.session_progress)
        dash_layout.addWidget(soc_group)

        dash_layout.addStretch()
        dash_scroll.setWidget(dash_content)
        session_layout.addWidget(dash_scroll)
        
        self.tabs.addTab(session_tab, "Session")

        # -- LOG PANEL (RIGHT) --
        right_panel = QVBoxLayout()
        right_panel.setSpacing(8)
        main_layout.addLayout(right_panel, 7)

        log_header = QHBoxLayout()
        log_title = QLabel("📋 Activity Log")
        log_title.setObjectName("sectionHeader")
        log_header.addWidget(log_title)
        log_header.addStretch()

        self.btn_clear_logs = QPushButton("Clear")
        self.btn_clear_logs.setMinimumHeight(24)
        self.btn_clear_logs.clicked.connect(lambda: self.log_panel.clear())
        log_header.addWidget(self.btn_clear_logs)

        self.btn_log_mode = QPushButton("Detailed")
        self.btn_log_mode.setObjectName("btn_log_mode")
        self.btn_log_mode.setCheckable(True)
        self.btn_log_mode.setMinimumHeight(24)
        self.btn_log_mode.clicked.connect(self.action_toggle_log_mode)
        log_header.addWidget(self.btn_log_mode)
        right_panel.addLayout(log_header)

        self.log_panel = LogPanel()
        right_panel.addWidget(self.log_panel)

    def _on_connector_panel_select(self, connector_id: int) -> None:
        self._selected_connector_id = connector_id
        self.status_panel.set_selected_connector(connector_id)

    def _get_selected_connector(self):
        return self.engine.get_connector(self._selected_connector_id)

    def _ensure_valid_selection(self) -> None:
        if self.engine.get_connector(self._selected_connector_id) is None:
            if self.engine.connectors:
                self._selected_connector_id = self.engine.connectors[0].id

    def update_ui(self):
        self._ensure_valid_selection()
        self.status_panel.set_selected_connector(self._selected_connector_id)
        self.status_panel.update_status(self.engine)
        self._update_session_details()

        conn = self._get_selected_connector()
        if conn:
            self.btn_plug.setEnabled(not conn.is_plugged_in)
            self.btn_unplug.setEnabled(conn.is_plugged_in)
            self.btn_swipe.setEnabled(conn.is_plugged_in)
            
            if self.engine.session:
                self.btn_swipe.setText("⏹  Stop Charging")
                self.btn_swipe.setProperty("danger", True)
                self.btn_swipe.setProperty("success", False)
            else:
                self.btn_swipe.setText("💳  Start Charging")
                self.btn_swipe.setProperty("success", True)
                self.btn_swipe.setProperty("danger", False)
            
            # Refresh style to apply danger/success properties
            self.btn_swipe.style().unpolish(self.btn_swipe)
            self.btn_swipe.style().polish(self.btn_swipe)

    def _update_session_details(self):
        conn = self._get_selected_connector()
        if conn:
            self.metric_voltage.set_value(f"{conn.voltage:.1f}")
            self.metric_current.set_value(f"{conn.current:.1f}")
            power_kw = (conn.voltage * conn.current * conn.phase) / 1000.0
            self.metric_power.set_value(f"{power_kw:.2f}")
        else:
            self.metric_voltage.set_value("--")
            self.metric_current.set_value("--")
            self.metric_power.set_value("--")

        session = self.engine.session
        if session:
            self.metric_tx_id.set_value(str(session.transaction_id))
            self.metric_energy.set_value(f"{session.energy_charged:.2f}")
            self.metric_soc.set_value(f"{session.state_of_charge:.1f}")
            duration = time.monotonic() - session.start_time
            self.metric_duration.set_value(f"{duration:.0f}")
            self.session_progress.setValue(int(session.state_of_charge))
        else:
            self.metric_tx_id.set_value("--")
            self.metric_energy.set_value("--")
            self.metric_soc.set_value("--")
            self.metric_duration.set_value("--")
            self.session_progress.setValue(0)

        meter = self.engine.energy_meter
        self.metric_meter.set_value(f"{meter.get_meter_reading():.1f}")

    def action_plug_in(self):
        # Unplug any currently plugged-in connectors first
        for conn in self.engine.connectors:
            if conn.is_plugged_in and conn.id != self._selected_connector_id:
                self.engine.unplug(conn.id)
                self.log_panel.log_message(
                    f"[yellow]UI:[/yellow] Auto-unplugged Connector {conn.id}"
                )

        self.engine.plug_in(self._selected_connector_id)
        self.log_panel.log_message(
            f"[green]UI:[/green] Plugged In to Connector {self._selected_connector_id}"
        )

    def action_unplug(self):
        self.engine.unplug(self._selected_connector_id)
        self.log_panel.log_message(
            f"[yellow]UI:[/yellow] Unplugged from Connector {self._selected_connector_id}"
        )

    def action_swipe_card(self):
        if not self.engine.session:
            SimulatorWidget._transaction_counter += 1
            temp_tx_id = SimulatorWidget._transaction_counter
            self.engine.start_session(
                connector_id=self._selected_connector_id, transaction_id=temp_tx_id
            )
            self.log_panel.log_message(
                f"[green]UI:[/green] Swiped Card - Requesting Start Session on Connector {self._selected_connector_id}"
            )
        else:
            self.engine.stop_session()
            self.log_panel.log_message(
                "[red]UI:[/red] Swiped Card - Requesting Stop Session"
            )

    def action_apply_id_tag(self):
        id_tag = self.input_id_tag.text().strip()
        conn = self._get_selected_connector()
        if id_tag and conn:
            conn.id_tag = id_tag
            self.log_panel.log_message(
                f"[green]UI:[/green] ID Tag set to: {id_tag} on Connector {self._selected_connector_id}"
            )
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
        self.config.skip_tls_verify = self.checkbox_skip_tls.isChecked()
        self.config.connectors = [
            ConnectorConfig(voltage=c.voltage, current=c.current, phase=c.phase)
            for c in self.engine.connectors
        ]
        self.config.num_connectors = len(self.engine.connectors)
        self.config.save()
        self.log_panel.log_message("[green]Config:[/green] Configuration saved.")

    def _on_connector_apply(
        self, connector_id: int, voltage: float, current: float, phase: int
    ) -> None:
        error = self.engine.update_connector(connector_id, voltage, current, phase)
        if error:
            self.log_panel.log_message(f"[red]Connector:[/red] {error}")
        else:
            self.log_panel.log_message(
                f"[green]Connector {connector_id}:[/green] Updated to "
                f"{voltage}V, {current}A, {phase}Ph"
            )
            self._save_connector_config()

    def _save_connector_config(self) -> None:
        """Persist current connector configuration to disk."""
        self.config.connectors = [
            ConnectorConfig(voltage=c.voltage, current=c.current, phase=c.phase)
            for c in self.engine.connectors
        ]
        self.config.num_connectors = len(self.engine.connectors)
        self.config.save()

    def _on_connector_remove(self, connector_id: int) -> None:
        if len(self.engine.connectors) <= 1:
            self.log_panel.log_message(
                "[red]Connector:[/red] Cannot remove the last connector"
            )
            return

        if self.engine.session and self.engine.session.connector_id == connector_id:
            self.log_panel.log_message(
                "[red]Connector:[/red] Cannot remove connector with active session"
            )
            return

        self.engine.remove_connector(connector_id)
        self.connector_panel.rebuild_cards()
        self._ensure_valid_selection()
        self.log_panel.log_message(
            f"[yellow]Connector:[/yellow] Removed connector {connector_id}"
        )
        self._save_connector_config()

    def _on_connector_add(self) -> None:
        connector = self.engine.add_connector()
        self.connector_panel.rebuild_cards()
        self._selected_connector_id = connector.id
        self.log_panel.log_message(
            f"[green]Connector:[/green] Added connector {connector.id}"
        )
        self._save_connector_config()

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

        # Basic Messages Group
        basic_group = QGroupBox("Lifecycle Messages")
        basic_layout = QVBoxLayout(basic_group)
        
        self.btn_boot = QPushButton("📤  BootNotification")
        self.btn_boot.setMinimumHeight(40)
        self.btn_boot.clicked.connect(self.action_boot)
        basic_layout.addWidget(self.btn_boot)

        self.btn_heartbeat = QPushButton("💓  Heartbeat")
        self.btn_heartbeat.setMinimumHeight(40)
        self.btn_heartbeat.clicked.connect(self.action_heartbeat)
        basic_layout.addWidget(self.btn_heartbeat)
        
        self.btn_status = QPushButton("📡  StatusNotification")
        self.btn_status.setMinimumHeight(40)
        self.btn_status.clicked.connect(self.action_status)
        basic_layout.addWidget(self.btn_status)
        controls.addWidget(basic_group)

        # Transaction Group
        tx_group = QGroupBox("Transaction Control")
        tx_layout = QVBoxLayout(tx_group)

        start_row = QHBoxLayout()
        self.btn_start = QPushButton("▶️  Start")
        self.btn_start.setProperty("success", True)
        self.btn_start.setMinimumHeight(40)
        self.btn_start.clicked.connect(self.action_start)
        self.input_tag = QLineEdit()
        self.input_tag.setPlaceholderText("ID Tag")
        start_row.addWidget(self.btn_start, 1)
        start_row.addWidget(self.input_tag, 2)
        tx_layout.addLayout(start_row)

        stop_row = QHBoxLayout()
        self.btn_stop = QPushButton("⏹️  Stop")
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

        log_header = QHBoxLayout()
        log_title = QLabel("📋 Activity Log")
        log_title.setObjectName("sectionHeader")
        log_header.addWidget(log_title)
        log_header.addStretch()

        self.btn_clear_logs = QPushButton("Clear")
        self.btn_clear_logs.setMinimumHeight(24)
        self.btn_clear_logs.clicked.connect(lambda: self.log_panel.clear())
        log_header.addWidget(self.btn_clear_logs)

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
        # Save connector configuration before closing
        self.config.connectors = [
            ConnectorConfig(voltage=c.voltage, current=c.current, phase=c.phase)
            for c in self.engine.connectors
        ]
        self.config.num_connectors = len(self.engine.connectors)
        self.config.save()
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
