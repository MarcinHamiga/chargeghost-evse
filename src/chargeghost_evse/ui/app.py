import asyncio
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from ocpp.v16.enums import ConfigurationStatus
from PySide6.QtCore import (
    Qt,
    QTimer,
    Signal,
    Slot,
    QPropertyAnimation,
    QEasingCurve,
    QSize,
)
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.devtools.fault_manager import FaultManager
from chargeghost_evse.devtools.scenario_loader import ScenarioLoader, ScenarioLoadError
from chargeghost_evse.devtools.scenario_runner import ScenarioRunner
from chargeghost_evse.devtools.simulator_controller import SimulatorController
from chargeghost_evse.devtools.timeline_store import TimelineStore
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.ocpp_adapter.config_keys import ConfigurationKeyManager
from chargeghost_evse.ui.bridge import QtSignalBridge
from chargeghost_evse.ui.styles import colors
from chargeghost_evse.ui.widgets.app_settings import AppSettings
from chargeghost_evse.ui.widgets.charging_profiles_panel import ChargingProfilesPanel
from chargeghost_evse.ui.widgets.display_message_widget import DisplayMessageWidget
from chargeghost_evse.ui.widgets.config_keys_panel import ConfigKeysPanel
from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
from chargeghost_evse.ui.widgets.fault_injection_panel import FaultInjectionPanel
from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel
from chargeghost_evse.ui.widgets.icons import get_icon
from chargeghost_evse.ui.widgets.scenario_runner_panel import ScenarioRunnerPanel
from chargeghost_evse.ui.widgets.session_dashboard import (
    SessionDashboard,
    IdTagInput,
)
from chargeghost_evse.ui.widgets.settings_panel import SettingsPanel
from chargeghost_evse.ui.widgets.toast import ToastNotification, ToastType
from chargeghost_evse.ui.widgets.update_dialog import UpdateDialog, UpdateStatusChip
from chargeghost_evse.util.config import ConnectorConfig, LogMode, SimulationConfig
from chargeghost_evse.util.log_setup import LogBridgeHandler, setup_file_logging
from chargeghost_evse.util.update_controller import UpdateController
from chargeghost_evse import __version__


def get_resource_path(relative_path: str) -> Path:
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        return base_path / "chargeghost_evse" / "ui" / relative_path
    else:
        base_path = Path(__file__).parent
        return base_path / relative_path


STYLES_PATH = get_resource_path("styles/e_mobility.qss")


class ToastManager(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._toasts: list[ToastNotification] = []
        self._toast_ids: dict[str, ToastNotification] = {}
        self._setup_ui()
        self.hide()

    def _setup_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(8)
        self._layout.addStretch()

    def show_toast(
        self,
        message: str,
        toast_type: ToastType = "info",
        toast_id: Optional[str] = None,
    ) -> ToastNotification:
        if toast_id:
            existing = self._toast_ids.get(toast_id)
            if existing is not None:
                existing.update_message(message, toast_type)
                self.adjustSize()
                self.reposition()
                self.show()
                self.raise_()
                return existing

        toast = ToastNotification(message, toast_type)
        if toast_id:
            self._toast_ids[toast_id] = toast
        toast.closed.connect(lambda: self._remove_toast(toast))
        self._layout.insertWidget(self._layout.count() - 1, toast)
        self._toasts.append(toast)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        return toast

    def _remove_toast(self, toast: ToastNotification) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        for current_id, current_toast in list(self._toast_ids.items()):
            if current_toast is toast:
                del self._toast_ids[current_id]
        if self._toasts:
            self.adjustSize()
            self.reposition()
        else:
            self.hide()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return

        margin = 16
        x_pos = max(margin, parent.width() - self.width() - margin)
        y_pos = margin
        self.move(x_pos, y_pos)


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
    connector_range_changed = Signal(int, int)

    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_window = main_window
        self.config = main_window.config
        self.engine = self.main_window.engine
        self.bridge = self.main_window.bridge
        self._selected_connector_id: int = 1
        self._transaction_counter: int = 0
        self._config_manager = ConfigurationKeyManager()
        self._config_manager.initialize_defaults()

        self._profiles_tick_counter: int = 0
        self._setup_ui()
        self.log_side_panel.set_timeline_store(self.main_window.timeline_store)

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # ── Sidebar ──────────────────────────────────────────────────────────
        self._sidebar = QWidget()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._sidebar.setFixedWidth(48)
        sidebar_layout = QVBoxLayout(self._sidebar)
        sidebar_layout.setContentsMargins(6, 12, 6, 12)
        sidebar_layout.setSpacing(4)

        self._btn_dashboard = self._create_nav_btn("Dashboard", "dashboard")
        self._btn_dashboard.setChecked(True)
        self._btn_dashboard.clicked.connect(lambda: self._on_nav_clicked(0))
        sidebar_layout.addWidget(self._btn_dashboard)

        self._btn_settings = self._create_nav_btn("Settings", "settings")
        self._btn_settings.clicked.connect(lambda: self._on_nav_clicked(1))
        sidebar_layout.addWidget(self._btn_settings)

        self._btn_ocpp_keys = self._create_nav_btn("OCPP Keys", "key")
        self._btn_ocpp_keys.clicked.connect(lambda: self._on_nav_clicked(2))
        sidebar_layout.addWidget(self._btn_ocpp_keys)

        self._btn_profiles = self._create_nav_btn("Profiles", "sliders")
        self._btn_profiles.clicked.connect(lambda: self._on_nav_clicked(3))
        sidebar_layout.addWidget(self._btn_profiles)

        self._btn_scenarios = self._create_nav_btn("Scenarios", "play")
        self._btn_scenarios.clicked.connect(lambda: self._on_nav_clicked(4))
        sidebar_layout.addWidget(self._btn_scenarios)

        self._btn_faults = self._create_nav_btn("Faults", "alert_triangle")
        self._btn_faults.clicked.connect(lambda: self._on_nav_clicked(5))
        sidebar_layout.addWidget(self._btn_faults)

        # Map index → (button, icon_name) for icon colour updates on nav click
        self._nav_btns: list[tuple[QToolButton, str]] = [
            (self._btn_dashboard, "dashboard"),
            (self._btn_settings, "settings"),
            (self._btn_ocpp_keys, "key"),
            (self._btn_profiles, "sliders"),
            (self._btn_scenarios, "play"),
            (self._btn_faults, "alert_triangle"),
        ]

        sidebar_layout.addStretch()

        self._btn_home = self._create_nav_btn("Switch Mode", "home")
        self._btn_home.setAutoExclusive(False)
        self._btn_home.clicked.connect(self.main_window._go_home)
        sidebar_layout.addWidget(self._btn_home)

        main_layout.addWidget(self._sidebar)

        # ── Content column ───────────────────────────────────────────────────
        content_col = QWidget()
        content_col_layout = QVBoxLayout(content_col)
        content_col_layout.setSpacing(0)
        content_col_layout.setContentsMargins(0, 0, 0, 0)

        # Connector status bar (always visible)
        self.connector_bar = ConnectorStatusBar()
        self.connector_bar.connector_selected.connect(self._on_connector_bar_selected)
        content_col_layout.addWidget(self.connector_bar)

        # CSMS display message widget (V201, hidden when no messages)
        self.display_message_widget = DisplayMessageWidget()
        content_col_layout.addWidget(self.display_message_widget)

        # Content stack
        self.stack = QStackedWidget()
        self.stack.setObjectName("contentStack")
        content_col_layout.addWidget(self.stack, 1)

        # Build tabs
        self._build_dashboard_tab()
        self._build_settings_tab()
        self._build_ocpp_keys_tab()
        self._build_profiles_tab()
        self._build_scenarios_tab()
        self._build_faults_tab()

        main_layout.addWidget(content_col, 1)

        # ── Log side panel ───────────────────────────────────────────────────
        self.log_side_panel = LogSidePanel()
        self.log_side_panel.log_mode_toggled.connect(
            self.main_window._on_log_mode_toggle
        )
        main_layout.addWidget(self.log_side_panel)

    def _create_nav_btn(self, text: str, icon_name: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("sidebarNavBtn")
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
        btn.setText(text)
        btn.setIcon(get_icon(icon_name, colors.TEXT_SECONDARY))
        btn.setIconSize(QSize(18, 18))
        btn.setMinimumHeight(40)
        btn.setMaximumHeight(40)
        btn.setToolTip(text)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _build_dashboard_tab(self) -> None:
        dashboard_tab = QWidget()
        dashboard_layout = QVBoxLayout(dashboard_tab)
        dashboard_layout.setSpacing(0)
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        self.dashboard = SessionDashboard()
        self.dashboard.plug_in_clicked.connect(self.action_plug_in)
        self.dashboard.unplug_clicked.connect(self.action_unplug)
        self.dashboard.start_charging_clicked.connect(self.action_start_charging)
        self.dashboard.stop_charging_clicked.connect(self.action_stop_charging)
        self.dashboard.suspend_ev_clicked.connect(self.action_suspend_ev)
        self.dashboard.resume_charging_clicked.connect(self.action_resume_charging)
        self.dashboard.set_rfid_clicked.connect(self.action_set_rfid)
        self.dashboard.clear_rfid_clicked.connect(self.action_clear_rfid)
        self.dashboard.authorize_clicked.connect(self.action_authorize)
        dashboard_layout.addWidget(self.dashboard, 1)
        self.stack.addWidget(dashboard_tab)

    def _build_settings_tab(self) -> None:
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
        self.settings_panel.ocpp_key_changed.connect(self._on_ocpp_key_changed)
        settings_layout.addWidget(self.settings_panel)
        self.stack.addWidget(settings_tab)

    def _build_ocpp_keys_tab(self) -> None:
        ocpp_keys_tab = QWidget()
        ocpp_keys_layout = QVBoxLayout(ocpp_keys_tab)
        ocpp_keys_layout.setSpacing(16)
        ocpp_keys_layout.setContentsMargins(16, 16, 16, 16)
        ocpp_keys_title = QLabel("OCPP Configuration Keys")
        ocpp_keys_title.setObjectName("sectionHeader")
        ocpp_keys_layout.addWidget(ocpp_keys_title)
        self.config_keys_panel = ConfigKeysPanel()
        self.config_keys_panel.key_changed.connect(self._on_ocpp_key_changed)
        self.config_keys_panel.set_keys(self._config_manager.get_all_keys())
        ocpp_keys_layout.addWidget(self.config_keys_panel)
        self.stack.addWidget(ocpp_keys_tab)

    def _build_profiles_tab(self) -> None:
        profiles_tab = QWidget()
        profiles_layout = QVBoxLayout(profiles_tab)
        profiles_layout.setSpacing(0)
        profiles_layout.setContentsMargins(0, 0, 0, 0)
        self.profiles_panel = ChargingProfilesPanel()
        profiles_layout.addWidget(self.profiles_panel)
        self.stack.addWidget(profiles_tab)

    def _build_scenarios_tab(self) -> None:
        scenarios_tab = QWidget()
        scenarios_layout = QVBoxLayout(scenarios_tab)
        scenarios_layout.setSpacing(0)
        scenarios_layout.setContentsMargins(0, 0, 0, 0)
        self.scenario_runner_panel = ScenarioRunnerPanel()
        self.scenario_runner_panel.load_scenario_clicked.connect(self._on_load_scenario)
        self.scenario_runner_panel.start_run_clicked.connect(self._on_start_scenario)
        self.scenario_runner_panel.cancel_run_clicked.connect(self._on_cancel_scenario)
        scenarios_layout.addWidget(self.scenario_runner_panel)
        self.stack.addWidget(scenarios_tab)

    def _build_faults_tab(self) -> None:
        faults_tab = QWidget()
        faults_layout = QVBoxLayout(faults_tab)
        faults_layout.setSpacing(0)
        faults_layout.setContentsMargins(0, 0, 0, 0)
        self.fault_panel = FaultInjectionPanel()
        faults_layout.addWidget(self.fault_panel)
        self.stack.addWidget(faults_tab)

    def _on_nav_clicked(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, (btn, icon_name) in enumerate(self._nav_btns):
            color = colors.ACCENT_TEAL if i == index else colors.TEXT_SECONDARY
            btn.setIcon(get_icon(icon_name, color))

    def _clear_graphics_effect(self, widget: QWidget) -> None:
        widget.setGraphicsEffect(None)  # type: ignore[arg-type]

    def _on_connector_bar_selected(self, connector_id: int) -> None:
        self._selected_connector_id = connector_id
        self.dashboard.set_selected_connector(connector_id)
        self.main_window.app_settings.last_connector_id = connector_id

    def _get_selected_connector(self):
        return self.engine.get_connector(self._selected_connector_id)

    def _ensure_valid_selection(self) -> None:
        if self.engine.get_connector(self._selected_connector_id) is None:
            if self.engine.connectors:
                self._selected_connector_id = self.engine.connectors[0].id
                self.dashboard.set_selected_connector(self._selected_connector_id)

    def update_ui(self) -> None:
        self._ensure_valid_selection()
        # Update connector status bar pills
        engine = self.engine
        for conn in engine.connectors:
            session = engine.get_session(conn.id)
            soc = session.state_of_charge if session else None
            self.connector_bar.update_connector(conn.id, conn.status.value, soc)
        self.connector_bar.set_selected_connector(self._selected_connector_id)

        # Update live session stats in bar
        from chargeghost_evse.ui.widgets.session_dashboard import (
            _compute_effective_power_kw,
        )

        power_kw = _compute_effective_power_kw(engine, self._selected_connector_id)
        session = engine.get_session(self._selected_connector_id)
        if session:
            duration_str = self.dashboard._format_duration(session.start_time)
            self.connector_bar.update_session_stats(
                power_kw, session.state_of_charge, duration_str
            )
        else:
            self.connector_bar.hide_session_stats()

        self.dashboard.update_from_engine(engine)
        self._profiles_tick_counter += 1
        if self._profiles_tick_counter >= 10:
            self._profiles_tick_counter = 0
            self.profiles_panel.update_from_engine(engine, self.bridge)

    def action_plug_in(self) -> None:
        self.engine.plug_in(self._selected_connector_id)
        if self.main_window.timeline_store is not None:
            self.main_window.timeline_store.append(
                source="ui",
                direction="local",
                event_type="action",
                action="plug_in",
                connector_id=self._selected_connector_id,
                summary=f"UI: Plugged In to Connector {self._selected_connector_id}",
            )
        self.main_window.log_message(
            f"[green]UI:[/green] Plugged In to Connector {self._selected_connector_id}"
        )

    def action_unplug(self) -> None:
        self.engine.unplug(self._selected_connector_id)
        if self.main_window.timeline_store is not None:
            self.main_window.timeline_store.append(
                source="ui",
                direction="local",
                event_type="action",
                action="unplug",
                connector_id=self._selected_connector_id,
                summary=f"UI: Unplugged from Connector {self._selected_connector_id}",
            )
        self.main_window.log_message(
            f"[yellow]UI:[/yellow] Unplugged from Connector {self._selected_connector_id}"
        )

    def action_start_charging(self) -> None:
        self._transaction_counter += 1
        temp_tx_id = self._transaction_counter
        self.engine.start_session(
            connector_id=self._selected_connector_id, transaction_id=temp_tx_id
        )
        if self.main_window.timeline_store is not None:
            self.main_window.timeline_store.append(
                source="ui",
                direction="local",
                event_type="action",
                action="start_charging",
                connector_id=self._selected_connector_id,
                transaction_id=temp_tx_id,
                summary=f"UI: Started charging session on Connector {self._selected_connector_id}",
            )
        self.main_window.log_message(
            f"[green]UI:[/green] Started charging session on Connector {self._selected_connector_id}"
        )

    def action_stop_charging(self) -> None:
        self.engine.stop_session()
        if self.main_window.timeline_store is not None:
            self.main_window.timeline_store.append(
                source="ui",
                direction="local",
                event_type="action",
                action="stop_charging",
                summary="UI: Stopped charging session",
            )
        self.main_window.log_message("[red]UI:[/red] Stopped charging session")

    def action_suspend_ev(self) -> None:
        self.engine.suspend_ev(self._selected_connector_id)
        if self.main_window.timeline_store is not None:
            self.main_window.timeline_store.append(
                source="ui",
                direction="local",
                event_type="action",
                action="suspend_ev",
                connector_id=self._selected_connector_id,
                summary=f"UI: Suspended EV on Connector {self._selected_connector_id}",
            )
        self.main_window.log_message(
            f"[yellow]UI:[/yellow] Suspended EV on Connector {self._selected_connector_id}"
        )

    def action_resume_charging(self) -> None:
        self.engine.resume_charging(self._selected_connector_id)
        if self.main_window.timeline_store is not None:
            self.main_window.timeline_store.append(
                source="ui",
                direction="local",
                event_type="action",
                action="resume_charging",
                connector_id=self._selected_connector_id,
                summary=f"UI: Resumed charging on Connector {self._selected_connector_id}",
            )
        self.main_window.log_message(
            f"[green]UI:[/green] Resumed charging on Connector {self._selected_connector_id}"
        )

    def action_set_rfid(self, rfid_tag: str) -> None:
        self.config.rfid_tag = rfid_tag
        self.config.save()
        conn = self._get_selected_connector()
        if conn:
            conn.id_tag = rfid_tag
        self.main_window.app_settings.add_recent_tag(rfid_tag)
        self.main_window.update_recent_tags()
        self.main_window.log_message(
            f"[green]RFID:[/green] Persistent RFID set to: {rfid_tag}"
        )
        self.main_window.show_toast(f"RFID set: {rfid_tag}", "success")

    def action_clear_rfid(self) -> None:
        self.config.rfid_tag = None
        self.config.save()
        conn = self._get_selected_connector()
        if conn:
            conn.id_tag = None
        self.main_window.log_message("[yellow]RFID:[/yellow] Persistent RFID cleared")
        self.main_window.show_toast("RFID cleared", "info")

    def action_authorize(self, rfid_tag: str) -> None:
        self.bridge.send_authorize(rfid_tag)
        if self.main_window.timeline_store is not None:
            self.main_window.timeline_store.append(
                source="ui",
                direction="local",
                event_type="action",
                action="authorize",
                summary=f"UI: Sending Authorize with tag: {rfid_tag}",
            )
        self.main_window.log_message(
            f"[cyan]OCPP:[/cyan] Sending Authorize with tag: {rfid_tag}"
        )

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
        self.config.save()
        self.engine.set_battery_capacity(self.config.ev_battery_capacity)
        self.main_window.restart_bridge_connection()
        self.main_window.log_message(
            "[green]Config:[/green] Configuration saved and connection restarted."
        )
        self.main_window.show_toast(
            "Configuration saved; reconnecting to CSMS", "success"
        )

    def _show_error(self, message: str) -> None:
        self.main_window.log_message(f"[red]Config:[/red] {message}")
        self.main_window.show_toast(message, "error")

    def _on_connector_apply(
        self, connector_id: int, voltage: float, current: float, phase: int
    ) -> None:
        error = self.engine.update_connector(connector_id, voltage, current, phase)
        if error:
            self._show_error(f"Connector: {error}")
        else:
            self.main_window.log_message(
                f"[green]Connector {connector_id}:[/green] Updated to "
                f"{voltage}V, {current}A, {phase}Ph"
            )
            self._save_connector_config()

    def _save_connector_config(self) -> None:
        self.config.connectors = [
            ConnectorConfig(voltage=c.voltage, current=c.current, phase=c.phase)
            for c in self.engine.connectors
        ]
        self.config.save()

    def _on_connector_remove(self, connector_id: int) -> None:
        try:
            self.engine.remove_connector(connector_id)
        except ValueError as e:
            self._show_error(str(e))
            return
        self.connector_bar.remove_connector(connector_id)
        self.settings_panel.rebuild_connector_cards()
        self._ensure_valid_selection()
        self.main_window.log_message(
            f"[yellow]Connector:[/yellow] Removed connector {connector_id}"
        )
        self._save_connector_config()
        self.connector_range_changed.emit(1, max(len(self.engine.connectors), 1))

    def _on_connector_add(self) -> None:
        connector = self.engine.add_connector()
        self.settings_panel.rebuild_connector_cards()
        self._selected_connector_id = connector.id
        self.dashboard.set_selected_connector(connector.id)
        self.connector_range_changed.emit(1, max(len(self.engine.connectors), 1))
        self.main_window.log_message(
            f"[green]Connector:[/green] Added connector {connector.id}"
        )
        self._save_connector_config()

    def action_toggle_log_mode(self, is_detailed: bool) -> None:
        self.main_window.app_settings.log_mode = "deep" if is_detailed else "shallow"

    def load_ocpp_config_keys(self) -> None:
        adapter = self.bridge.runner.adapter
        if adapter:
            config_manager = getattr(adapter, "config_manager", None)
            if config_manager is not None:
                self.config_keys_panel.set_keys(config_manager.get_all_keys())

    def _on_ocpp_key_changed(self, key_name: str, new_value: str) -> None:
        adapter = self.bridge.runner.adapter
        if adapter:
            config_manager = getattr(adapter, "config_manager", None)
            if config_manager is not None:
                status = config_manager.set_key(key_name, new_value)
                if status == ConfigurationStatus.accepted:
                    self.main_window.log_message(
                        f"[green]Config:[/green] OCPP key '{key_name}' set to '{new_value}'"
                    )
                    self.main_window.show_toast(
                        f"Updated OCPP key: {key_name}", "success"
                    )
                else:
                    self.main_window.log_message(
                        f"[red]Config:[/red] Failed to update OCPP key '{key_name}' ({status.value})"
                    )
                    self.main_window.show_toast(
                        f"Failed to update OCPP key: {key_name}", "error"
                    )

    def _on_load_scenario(self) -> None:
        last_path = self.main_window.app_settings.last_scenario_path
        if last_path:
            default_dir = str(Path(last_path).parent)
        else:
            default_dir = str(Path.home())

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Scenario",
            default_dir,
            "JSON Files (*.json);;All Files (*)",
        )
        if not file_path:
            return

        try:
            scenario = ScenarioLoader.load(Path(file_path))
            self.main_window.app_settings.last_scenario_path = file_path
            self.scenario_runner_panel.set_scenario(scenario)
            self.scenario_runner_panel.set_scenario_path(file_path)
            self.main_window.log_message(
                f"[green]Scenario:[/green] Loaded '{scenario.name}'"
            )
        except ScenarioLoadError as e:
            self.main_window.show_toast(f"Failed to load scenario: {e}", "error")
            self.main_window.log_message(f"[red]Scenario:[/red] Load error: {e}")

    def _on_start_scenario(self) -> None:
        scenario = self.scenario_runner_panel._scenario
        if scenario is None:
            self.main_window.show_toast("No scenario loaded", "error")
            return

        runner = self.main_window.scenario_runner
        success = runner.start(scenario)
        if not success:
            self.main_window.show_toast("Failed to start scenario", "error")
            return

        self.main_window.log_message(
            f"[green]Scenario:[/green] Started '{scenario.name}'"
        )

    def _on_cancel_scenario(self) -> None:
        runner = self.main_window.scenario_runner
        runner.cancel()
        self.main_window.log_message("[yellow]Scenario:[/yellow] Cancelled")


class ManualWidget(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_window = main_window
        self.config = SimulationConfig.load()
        self.engine = self.main_window.engine
        self.bridge = self.main_window.bridge
        self._setup_ui()
        self.log_side_panel.set_timeline_store(self.main_window.timeline_store)
        self.refresh_connection_state()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # ── Sidebar ──────────────────────────────────────────────────────────
        self._sidebar = QWidget()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._sidebar.setFixedWidth(48)
        sidebar_layout = QVBoxLayout(self._sidebar)
        sidebar_layout.setContentsMargins(6, 12, 6, 12)
        sidebar_layout.setSpacing(4)

        self._btn_manual = self._create_nav_btn("Manual Controls", "terminal")
        self._btn_manual.setChecked(True)
        sidebar_layout.addWidget(self._btn_manual)
        sidebar_layout.addStretch()

        self._btn_home = self._create_nav_btn("Switch Mode", "home")
        self._btn_home.setAutoExclusive(False)
        self._btn_home.clicked.connect(self.main_window._go_home)
        sidebar_layout.addWidget(self._btn_home)

        main_layout.addWidget(self._sidebar)

        # ── Content ──────────────────────────────────────────────────────────
        content_widget = QWidget()
        layout = QHBoxLayout(content_widget)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)
        main_layout.addWidget(content_widget, 1)

        controls = QVBoxLayout()
        controls.setSpacing(12)
        layout.addLayout(controls, 3)

        controls_title = QLabel("Manual OCPP Controls")
        controls_title.setObjectName("sectionHeader")
        controls.addWidget(controls_title)

        connector_row = QHBoxLayout()
        connector_label = QLabel("Connector:")
        connector_row.addWidget(connector_label)
        self.input_connector_id = QSpinBox()
        connector_row.addWidget(self.input_connector_id)
        self.update_connector_range()
        connector_row.addStretch()
        controls.addLayout(connector_row)

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

        self.id_tag_input = IdTagInput(button_text="Start")
        self.id_tag_input.tag_applied.connect(self.action_start)
        tx_layout.addWidget(self.id_tag_input)

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

        # ── Log side panel ───────────────────────────────────────────────────
        self.log_side_panel = LogSidePanel()
        self.log_side_panel.log_mode_toggled.connect(
            self.main_window._on_log_mode_toggle
        )
        main_layout.addWidget(self.log_side_panel)

    def _create_nav_btn(self, text: str, icon_name: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("sidebarNavBtn")
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
        btn.setText(text)
        btn.setIcon(get_icon(icon_name, colors.TEXT_SECONDARY))
        btn.setIconSize(QSize(18, 18))
        btn.setMinimumHeight(40)
        btn.setMaximumHeight(40)
        btn.setToolTip(text)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def update_connector_range(
        self, min_id: int = 1, max_id: Optional[int] = None
    ) -> None:
        """Sync the connector spinner's upper bound to the current connector count."""
        if max_id is None:
            max_id = max(len(self.engine.connectors), 1)
        self.input_connector_id.setRange(min_id, max_id)

    def action_boot(self) -> None:
        adapter = self.bridge.runner.adapter
        loop = self.bridge.runner.loop
        if not adapter or not loop:
            self.log_side_panel.log_message(
                "[yellow]UI:[/yellow] Manual controls unavailable while disconnected"
            )
            return
        asyncio.run_coroutine_threadsafe(adapter.send_boot_notification(), loop)

    def action_heartbeat(self) -> None:
        adapter = self.bridge.runner.adapter
        loop = self.bridge.runner.loop
        if not adapter or not loop:
            self.log_side_panel.log_message(
                "[yellow]UI:[/yellow] Manual controls unavailable while disconnected"
            )
            return
        asyncio.run_coroutine_threadsafe(adapter.send_heartbeat(), loop)

    def action_start(self, tag: str = "") -> None:
        adapter = self.bridge.runner.adapter
        loop = self.bridge.runner.loop
        if not adapter or not loop:
            self.log_side_panel.log_message(
                "[yellow]UI:[/yellow] Manual controls unavailable while disconnected"
            )
            return
        id_tag = tag or self.id_tag_input.get_tag() or "MANUAL_TAG"
        self.main_window.app_settings.add_recent_tag(id_tag)
        self.main_window.update_recent_tags()

        asyncio.run_coroutine_threadsafe(
            adapter.send_start_transaction(
                connector_id=self.input_connector_id.value(),
                id_tag=id_tag,
                meter_start=0,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
            loop,
        )

    def action_stop(self) -> None:
        adapter = self.bridge.runner.adapter
        loop = self.bridge.runner.loop
        if not adapter or not loop:
            self.log_side_panel.log_message(
                "[yellow]UI:[/yellow] Manual controls unavailable while disconnected"
            )
            return

        tx_id_text = self.input_tx_id.text().strip()
        if tx_id_text:
            try:
                transaction_id = int(tx_id_text)
            except ValueError:
                self.log_side_panel.log_message("[red]UI:[/red] Invalid Transaction ID")
                return
        elif self.engine.session:
            transaction_id = self.engine.session.transaction_id
        else:
            self.log_side_panel.log_message(
                "[yellow]UI:[/yellow] Enter a Transaction ID or start a session first"
            )
            return

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
        if not adapter or not loop:
            self.log_side_panel.log_message(
                "[yellow]UI:[/yellow] Manual controls unavailable while disconnected"
            )
            return
        asyncio.run_coroutine_threadsafe(
            adapter.send_status_notification(
                connector_id=self.input_connector_id.value(),
                error_code="NoError",
                status="Available",
            ),
            loop,
        )

    def set_recent_tags(self, tags: list[str]) -> None:
        """Update recent tags in the manual controls panel."""
        self.id_tag_input.set_recent_tags(tags)

    def update_ui(self) -> None:
        """Update manual controls from current engine state."""
        self.refresh_connection_state()
        connector_id = self.input_connector_id.value()
        conn = self.engine.get_connector(connector_id)
        if conn:
            self.id_tag_input.set_applied_tag(conn.id_tag)

    def refresh_connection_state(self) -> None:
        has_connection = (
            self.bridge.runner.adapter is not None
            and self.bridge.runner.loop is not None
        )
        self.btn_boot.setEnabled(has_connection)
        self.btn_heartbeat.setEnabled(has_connection)
        self.btn_status.setEnabled(has_connection)
        self.btn_stop.setEnabled(has_connection)
        self.input_tx_id.setEnabled(has_connection)
        self.input_connector_id.setEnabled(has_connection)
        self.id_tag_input.set_enabled(has_connection)

    def log_message(self, message: str) -> None:
        self.log_side_panel.log_message(message)

    def log_record(self, record: logging.LogRecord) -> None:
        self.log_side_panel.log_record(record)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._accumulator: float = 0.0
        self._last_tick_time: float = 0.0
        self._status_check_counter: int = 0
        self._config_restart_pending = False

        self.app_settings = AppSettings()

        self.setWindowTitle("ChargeGhost EVSE")
        self.setMinimumSize(1280, 720)
        self.resize(1600, 900)

        self.config = SimulationConfig.load()
        self.engine = Engine(multi_evse_mode=self.config.multi_evse_mode)
        self.engine.set_battery_capacity(self.config.ev_battery_capacity)
        for connector_config in self.config.connectors:
            self.engine.add_connector(
                voltage=connector_config.voltage,
                current=connector_config.current,
                phase=connector_config.phase,
            )

        self.fault_manager = FaultManager()
        self.engine.set_fault_manager(self.fault_manager)

        self.bridge = self._create_bridge()
        self.bridge.setup()

        # Initialize timeline store and inject into bridge
        self.timeline_store = TimelineStore()
        self.bridge.timeline_store = self.timeline_store

        self.signal_bridge = QtSignalBridge(self.engine, self.bridge)
        self.signal_bridge.set_fault_manager(self.fault_manager)

        self.simulator_controller = SimulatorController(self.engine, self.bridge)
        self.scenario_runner = ScenarioRunner(self.simulator_controller)

        # Set up Python logging for chargeghost namespace
        cg_logger = logging.getLogger("chargeghost")
        cg_logger.setLevel(logging.DEBUG)

        # File handler: rotating JSON logs (attach before banner so it's captured)
        self._file_handler = setup_file_logging()
        cg_logger.addHandler(self._file_handler)

        # UI handler: bridge to Qt signal
        self._ui_handler = LogBridgeHandler(self.signal_bridge.log_record_received)
        self._ui_handler.setLevel(logging.DEBUG)
        cg_logger.addHandler(self._ui_handler)

        cg_logger.info("=== ChargeGhost session started ===")

        self.signal_bridge.log_record_received.connect(self.on_log_received)
        self.signal_bridge.connection_status_changed.connect(
            self.on_connection_status_changed
        )
        self.signal_bridge.ocpp_config_key_changed.connect(
            self.on_ocpp_config_key_changed
        )
        self.signal_bridge.session_started.connect(self.on_session_started)
        self.signal_bridge.display_message_received.connect(self._on_display_message)
        self.signal_bridge.cost_updated.connect(self._on_cost_updated)
        self.signal_bridge.event_notification.connect(self._on_event_notification)

        self._setup_ui()
        self._setup_menu()
        self._setup_shortcuts()
        self._restore_ui_state()

        self.simulator.fault_panel.fault_toggled.connect(self._on_fault_toggled)
        self.simulator.fault_panel.clear_all_requested.connect(
            self.fault_manager.clear_all
        )
        self.fault_manager.fault_changed.subscribe(self._on_fault_manager_changed)

        self._last_tick_time = time.monotonic()
        self.timer = QTimer()
        self.timer.timeout.connect(self.simulate_step)
        self.timer.start(100)

        # Initialize updater
        self._update_chip: Optional[UpdateStatusChip] = None
        self.update_controller = UpdateController(
            current_version=__version__, config=self.config, parent=self
        )
        self.update_controller.update_available.connect(self._on_update_available)
        self.update_controller.download_progress.connect(self._on_download_progress)
        self.update_controller.ready_to_restart.connect(self._on_ready_to_restart)
        self.update_controller.error_occurred.connect(
            lambda msg: self.show_toast(msg, "error")
        )
        QTimer.singleShot(1500, self.update_controller.start_check)

    def _create_bridge(self) -> Bridge:
        return Bridge(
            self.engine,
            url=self.config.connection_url,
            charge_point_id=self.config.ocpp_id,
            password=self.config.ocpp_password,
            skip_tls_verify=self.config.skip_tls_verify,
            charge_point_model=self.config.charge_point_model,
            charge_point_vendor=self.config.charge_point_vendor,
            persist_message_queue=self.config.persist_message_queue,
            get_rfid=lambda: self.config.rfid_tag,
            ocpp_version=self.config.ocpp_version,
        )

    def restart_bridge_connection(self) -> None:
        old_bridge = self.bridge
        old_bridge.shutdown()

        self._config_restart_pending = True
        self.bridge = self._create_bridge()
        self.bridge.setup()
        self.signal_bridge.set_bridge(self.bridge)
        self.simulator.bridge = self.bridge
        self.manual.bridge = self.bridge
        self.simulator_controller.bridge = self.bridge
        self.manual.refresh_connection_state()
        self._connection_indicator.setText("Reconnecting with new settings")
        self._connection_indicator.setProperty("connected", False)
        self._connection_indicator.style().unpolish(self._connection_indicator)
        self._connection_indicator.style().polish(self._connection_indicator)

    def update_recent_tags(self) -> None:
        """Centralized update of recent tags across all relevant UI widgets."""
        tags = self.app_settings.recent_tags
        self.simulator.dashboard.set_recent_tags(tags)
        self.manual.set_recent_tags(tags)

    def _setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)

        self.toast_manager = ToastManager(self)

        self.mode_select = ModeSelectWidget(self)
        self.simulator = SimulatorWidget(self)
        self.manual = ManualWidget(self)

        self.simulator.connector_range_changed.connect(
            self.manual.update_connector_range
        )

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

    def _setup_shortcuts(self) -> None:
        shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        shortcut_save.activated.connect(self._shortcut_save)

        shortcut_log = QShortcut(QKeySequence("`"), self)
        shortcut_log.activated.connect(self._toggle_active_log)

        shortcut_f1 = QShortcut(QKeySequence("F1"), self)
        shortcut_f1.activated.connect(self._toggle_active_log)

        shortcut_home = QShortcut(QKeySequence("Esc"), self)
        shortcut_home.activated.connect(self._go_home)

    def _setup_menu(self) -> None:
        """Setup the application menu bar."""
        menubar = self.menuBar()

        # Help menu
        help_menu = menubar.addMenu("Help")

        # Check for Updates action (only enabled in production builds)
        check_updates_action = help_menu.addAction("Check for Updates...")
        check_updates_action.triggered.connect(self._manual_update_check)

        # Disable in development mode
        if not getattr(sys, "frozen", False):
            check_updates_action.setEnabled(False)
            check_updates_action.setText("Check for Updates... (Disabled in Dev Mode)")

        help_menu.addSeparator()

        # About action
        about_action = help_menu.addAction("About ChargeGhost EVSE")
        about_action.triggered.connect(self._show_about_dialog)

    def _restore_ui_state(self) -> None:
        geometry = self.app_settings.window_geometry
        if geometry:
            self.restoreGeometry(geometry)

        self.simulator._selected_connector_id = self.app_settings.last_connector_id
        self.simulator.dashboard.set_selected_connector(
            self.app_settings.last_connector_id
        )

        if self.app_settings.log_panel_expanded:
            self.simulator.log_side_panel.toggle()

        if self.config.rfid_tag:
            self.simulator.dashboard.set_rfid(self.config.rfid_tag)

        saved_ui_mode = self.app_settings.last_mode
        if saved_ui_mode in ("simulator", "manual"):
            self.switch_to_mode(saved_ui_mode)

    def _go_home(self) -> None:
        if self.stack.currentWidget() != self.mode_select:
            self._fade_to_widget(self.mode_select)
            self.app_settings.last_mode = ""

    def switch_to_mode(self, mode: str) -> None:
        if mode == "simulator":
            self._fade_to_widget(self.simulator)
            self.update_recent_tags()
        elif mode == "manual":
            self._fade_to_widget(self.manual)
            self.update_recent_tags()
        self.app_settings.last_mode = mode

    def _fade_to_widget(self, widget: QWidget) -> None:
        if self.stack.currentWidget() == widget:
            return

        # Create opacity effect
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

        # Set target widget as current
        self.stack.setCurrentWidget(widget)

        # Animate opacity
        self._anim = QPropertyAnimation(effect, b"opacity")
        self._anim.setDuration(250)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.finished.connect(lambda: self._clear_graphics_effect(widget))
        self._anim.start()

    def _clear_graphics_effect(self, widget: QWidget) -> None:
        widget.setGraphicsEffect(None)  # type: ignore[arg-type]

    def _toggle_active_log(self) -> None:
        current = self.stack.currentWidget()
        if current is self.simulator:
            self.simulator.log_side_panel.toggle()
        elif current is self.manual:
            self.manual.log_side_panel.toggle()

    def _on_log_mode_toggle(self, is_detailed: bool) -> None:
        mode: LogMode = "deep" if is_detailed else "shallow"
        self.app_settings.log_mode = mode
        # Sync the other mode's log panel button state
        other = (
            self.manual
            if self.stack.currentWidget() == self.simulator
            else self.simulator
        )
        other.log_side_panel.set_log_mode(is_detailed)

    def _shortcut_save(self) -> None:
        if self.stack.currentWidget() == self.simulator:
            self.simulator.action_save_config()

    def show_toast(self, message: str, toast_type: ToastType = "info") -> None:
        self.toast_manager.show_toast(message, toast_type)

    def log_message(self, message: str) -> None:
        if self.stack.currentWidget() == self.simulator:
            self.simulator.log_side_panel.log_message(message)
        elif self.stack.currentWidget() == self.manual:
            self.manual.log_side_panel.log_message(message)

    def _on_fault_toggled(self, fault_id: str, enabled: bool) -> None:
        if enabled:
            self.fault_manager.enable(fault_id)
        else:
            self.fault_manager.disable(fault_id)

    def _on_fault_manager_changed(self, **kwargs) -> None:
        self.simulator.fault_panel.set_fault_states(
            self.fault_manager.get_active_summary()
        )

    def simulate_step(self) -> None:
        current_time = time.monotonic()
        delta = current_time - self._last_tick_time
        self._last_tick_time = current_time
        self._accumulator += delta

        while self._accumulator >= 0.1:
            self.engine.simulate(0.1)
            self.scenario_runner.tick(0.1)
            self._accumulator -= 0.1

        self._status_check_counter += 1
        if self._status_check_counter >= 10:
            self._status_check_counter = 0
            self.signal_bridge.check_connection_status()

        # Always record chart data so no samples are lost while on another panel.
        self.simulator.dashboard.record_telemetry(self.engine)

        # Update scenario runner panel if visible
        if self.stack.currentWidget() == self.simulator:
            self.simulator.update_ui()
        elif self.stack.currentWidget() == self.manual:
            self.manual.update_ui()

        # Update scenario runner panel state
        self._update_scenario_runner_panel()

    def _update_scenario_runner_panel(self) -> None:
        runner = self.scenario_runner
        panel = self.simulator.scenario_runner_panel

        panel.set_runner_state(runner.state, runner._current_step_index)

        if runner.state == runner.state.COMPLETED:
            panel.set_failure_message("")
            self.simulator.log_side_panel.log_message(
                "[green]Scenario:[/green] Completed successfully"
            )
        elif runner.state == runner.state.FAILED:
            msg = runner.report.failure_reason if runner.report else "Unknown error"
            panel.set_failure_message(msg)
            self.simulator.log_side_panel.log_message(
                f"[red]Scenario:[/red] Failed: {msg}"
            )
        elif runner.state == runner.state.CANCELLED:
            self.simulator.log_side_panel.log_message(
                "[yellow]Scenario:[/yellow] Cancelled"
            )

    @Slot(object)
    def on_log_received(self, record: object) -> None:
        if not isinstance(record, logging.LogRecord):
            return
        if self.app_settings.log_mode == "shallow" and record.levelno < logging.INFO:
            return
        if self.stack.currentWidget() == self.simulator:
            self.simulator.log_side_panel.log_record(record)
        elif self.stack.currentWidget() == self.manual:
            self.manual.log_side_panel.log_record(record)

    @Slot(bool)
    def on_connection_status_changed(self, connected: bool) -> None:
        self.manual.refresh_connection_state()
        if connected:
            self._connection_indicator.setText("Connected")
            self._connection_indicator.setProperty("connected", True)
            adapter = self.bridge.runner.adapter
            if adapter:
                self.signal_bridge.subscribe_to_adapter(adapter)
                self.simulator.load_ocpp_config_keys()
            if self._config_restart_pending:
                self._config_restart_pending = False
                self.log_message(
                    "[green]Config:[/green] Reconnected to Central System with new settings."
                )
                self.show_toast(
                    "Reconnected to Central System with new settings", "success"
                )
            else:
                self.show_toast("Connected to Central System", "success")
        else:
            self._connection_indicator.setText("Disconnected")
            self._connection_indicator.setProperty("connected", False)
            self.show_toast("Disconnected from Central System", "warning")
        self._connection_indicator.style().unpolish(self._connection_indicator)
        self._connection_indicator.style().polish(self._connection_indicator)

    @Slot(int)
    def on_session_started(self, connector_id: int) -> None:
        self.simulator.dashboard.telemetry_chart.clear()

    @Slot(str, str)
    def on_ocpp_config_key_changed(self, key_name: str, new_value: str) -> None:
        self.simulator.config_keys_panel.update_key(key_name, new_value)

    @Slot(object)
    def _on_display_message(self, data: object) -> None:
        if not isinstance(data, dict):
            return
        self.simulator.display_message_widget.update_message(
            data.get("action", ""), data.get("message", {})
        )

    @Slot(str, object)
    def _on_cost_updated(self, transaction_id: str, total_cost: object) -> None:
        if not total_cost:
            self.simulator.dashboard.clear_cost_display()
            return
        cost_parts: list[str] = []
        for cost in total_cost:
            kind = (
                cost.cost_kind.value
                if hasattr(cost, "cost_kind") and hasattr(cost.cost_kind, "value")
                else str(getattr(cost, "cost_kind", ""))
            )
            amount = getattr(cost, "amount", 0)
            multiplier = getattr(cost, "amount_multiplier", 0) or 0
            if multiplier != 0:
                amount = amount * (10**multiplier)
            cost_parts.append(f"{kind}: {amount:.2f}")
        self.simulator.dashboard.set_cost_display("; ".join(cost_parts))

    @Slot(str, str, int)
    def _on_event_notification(
        self, component: str, variable: str, severity: int
    ) -> None:
        self.log_message(
            f"[cyan]Event:[/cyan] {component}/{variable} (severity={severity})"
        )

    @Slot(str, str)
    def _on_update_available(self, tag_name: str, body: str) -> None:
        """Show update chip when a new version is available."""
        if self._update_chip:
            return
        self._update_chip = UpdateStatusChip(tag_name)
        self._update_chip.clicked.connect(
            lambda: self._show_update_dialog(tag_name, body)
        )
        status_bar = self.statusBar()
        if status_bar:
            status_bar.addPermanentWidget(self._update_chip)
            self._update_chip.show()

    def _show_update_dialog(self, tag_name: str, body: str) -> None:
        """Show update dialog to user."""
        dialog = UpdateDialog(__version__, tag_name, body, self)
        dialog.update_now_clicked.connect(self.update_controller.trigger_download)
        dialog.later_clicked.connect(lambda: None)
        dialog.ignore_clicked.connect(lambda: self._on_update_ignore(tag_name))
        dialog.exec()

    def _on_update_ignore(self, tag_name: str) -> None:
        """Handle 'Ignore This Version' click."""
        self.update_controller.ignore_version(tag_name)
        if self._update_chip:
            self.statusBar().removeWidget(self._update_chip)
            self._update_chip.deleteLater()
            self._update_chip = None

    @Slot(int)
    def _on_download_progress(self, percent: int) -> None:
        """Show download progress toast."""
        self.toast_manager.show_toast(
            f"Downloading update: {percent}%", "info", toast_id="update-download"
        )

    @Slot()
    def _on_ready_to_restart(self) -> None:
        """Shut down bridge and quit after handover script is launched."""
        self.bridge.shutdown()
        QApplication.quit()

    def _manual_update_check(self) -> None:
        """Handle manual update check from menu."""
        self.show_toast("Checking for updates...", "info")
        self.update_controller.start_check()

    def _show_about_dialog(self) -> None:
        """Show about dialog."""
        about_text = f"""
        <h2>ChargeGhost EVSE</h2>
        <p>Version: {__version__}</p>
        <p>A professional, Python-based Electric Vehicle Supply Equipment (EVSE) simulator 
        featuring a modern graphical user interface built with PySide6 (Qt).</p>
        <p><b>Features:</b></p>
        <ul>
        <li>OCPP 1.6 protocol support</li>
        <li>Cross-platform compatibility</li>
        <li>Real-time simulation dashboard</li>
        <li>Automatic updates</li>
        </ul>
        <p>© 2026 Marcin Hamiga</p>
        <p>License: AGPLv3</p>
        """

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("About ChargeGhost EVSE")
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setText(about_text)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.exec()

    def closeEvent(self, event) -> None:
        self.app_settings.window_geometry = self.saveGeometry()
        self.app_settings.log_panel_expanded = self.simulator.log_side_panel.is_open()

        self.config.connectors = [
            ConnectorConfig(voltage=c.voltage, current=c.current, phase=c.phase)
            for c in self.engine.connectors
        ]
        self.config.save()
        self.bridge.shutdown()
        cg_logger = logging.getLogger("chargeghost")
        cg_logger.removeHandler(self._file_handler)
        cg_logger.removeHandler(self._ui_handler)
        self._file_handler.close()
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "toast_manager"):
            self.toast_manager.reposition()


def main() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)

    if STYLES_PATH.exists():
        with open(STYLES_PATH, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
