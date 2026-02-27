import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QTimer, Slot, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.ocpp_adapter.config_keys import ConfigurationKeyManager
from chargeghost_evse.ui.bridge import QtSignalBridge
from chargeghost_evse.ui.styles import colors
from chargeghost_evse.ui.widgets.app_settings import AppSettings
from chargeghost_evse.ui.widgets.charging_profiles_panel import ChargingProfilesPanel
from chargeghost_evse.ui.widgets.collapsible_log import CollapsibleLogPanel
from chargeghost_evse.ui.widgets.config_keys_panel import ConfigKeysPanel
from chargeghost_evse.ui.widgets.icons import get_icon
from chargeghost_evse.ui.widgets.log_panel import LogPanel
from chargeghost_evse.ui.widgets.session_dashboard import SessionDashboard
from chargeghost_evse.ui.widgets.settings_panel import SettingsPanel
from chargeghost_evse.ui.widgets.toast import ToastNotification, ToastType
from chargeghost_evse.ui.widgets.update_dialog import UpdateDialog, UpdateStatusChip
from chargeghost_evse.util.config import ConnectorConfig, LogMode, SimulationConfig
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
        self, message: str, toast_type: ToastType = "info"
    ) -> ToastNotification:
        toast = ToastNotification(message, toast_type)
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

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self._sidebar = QWidget()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(self._sidebar)
        sidebar_layout.setContentsMargins(8, 16, 8, 16)
        sidebar_layout.setSpacing(8)

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

        sidebar_layout.addStretch()

        main_layout.addWidget(self._sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("contentStack")
        main_layout.addWidget(self.stack, 1)

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

        self.stack.addWidget(dashboard_tab)

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

        profiles_tab = QWidget()
        profiles_layout = QVBoxLayout(profiles_tab)
        profiles_layout.setSpacing(0)
        profiles_layout.setContentsMargins(0, 0, 0, 0)

        self.profiles_panel = ChargingProfilesPanel()
        profiles_layout.addWidget(self.profiles_panel)

        self.stack.addWidget(profiles_tab)

    def _create_nav_btn(self, text: str, icon_name: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("sidebarNavBtn")
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
        btn.setIcon(get_icon(icon_name, colors.TEXT_SECONDARY))
        btn.setIconSize(QSize(16, 16))
        btn.setMinimumHeight(40)
        btn.setMaximumHeight(40)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _on_nav_clicked(self, index: int) -> None:
        target_widget = self.stack.widget(index)
        if self.stack.currentWidget() == target_widget or target_widget is None:
            return

        # Update icons to reflect active state
        self._btn_dashboard.setIcon(
            get_icon(
                "dashboard", colors.ACCENT_TEAL if index == 0 else colors.TEXT_SECONDARY
            )
        )
        self._btn_settings.setIcon(
            get_icon(
                "settings", colors.ACCENT_TEAL if index == 1 else colors.TEXT_SECONDARY
            )
        )
        self._btn_ocpp_keys.setIcon(
            get_icon("key", colors.ACCENT_TEAL if index == 2 else colors.TEXT_SECONDARY)
        )
        self._btn_profiles.setIcon(
            get_icon("sliders", colors.ACCENT_TEAL if index == 3 else colors.TEXT_SECONDARY)
        )

        # Fade animation
        effect = QGraphicsOpacityEffect(target_widget)
        target_widget.setGraphicsEffect(effect)

        self.stack.setCurrentIndex(index)

        self._anim = QPropertyAnimation(effect, b"opacity")
        self._anim.setDuration(200)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._anim.finished.connect(lambda: self._clear_graphics_effect(target_widget))
        self._anim.start()

    def _clear_graphics_effect(self, widget: QWidget) -> None:
        widget.setGraphicsEffect(None)  # type: ignore[arg-type]

    def _on_connector_selected(self, connector_id: int) -> None:
        self._selected_connector_id = connector_id
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
        self.dashboard.update_from_engine(self.engine)
        # Throttle profiles panel updates (10 ticks × 100 ms timer ≈ 1 s).
        self._profiles_tick_counter += 1
        if self._profiles_tick_counter >= 10:
            self._profiles_tick_counter = 0
            self.profiles_panel.update_from_engine(self.engine, self.bridge)

    def action_plug_in(self) -> None:
        self.engine.plug_in(self._selected_connector_id)
        self.main_window.log_message(
            f"[green]UI:[/green] Plugged In to Connector {self._selected_connector_id}"
        )

    def action_unplug(self) -> None:
        self.engine.unplug(self._selected_connector_id)
        self.main_window.log_message(
            f"[yellow]UI:[/yellow] Unplugged from Connector {self._selected_connector_id}"
        )

    def action_start_charging(self) -> None:
        self._transaction_counter += 1
        temp_tx_id = self._transaction_counter
        self.engine.start_session(
            connector_id=self._selected_connector_id, transaction_id=temp_tx_id
        )
        self.main_window.log_message(
            f"[green]UI:[/green] Started charging session on Connector {self._selected_connector_id}"
        )

    def action_stop_charging(self) -> None:
        self.engine.stop_session()
        self.main_window.log_message("[red]UI:[/red] Stopped charging session")

    def action_apply_id_tag(self, id_tag: str) -> None:
        conn = self._get_selected_connector()
        if conn:
            conn.id_tag = id_tag
            self.main_window.app_settings.add_recent_tag(id_tag)
            self.main_window.log_message(
                f"[green]UI:[/green] ID Tag set to: {id_tag} on Connector {self._selected_connector_id}"
            )
            self.dashboard.set_recent_tags(self.main_window.app_settings.recent_tags)

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
        self.main_window.log_message("[green]Config:[/green] Configuration saved.")
        self.main_window.show_toast("Configuration saved", "success")

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
        self.settings_panel.rebuild_connector_cards()
        self._ensure_valid_selection()
        self.main_window.log_message(
            f"[yellow]Connector:[/yellow] Removed connector {connector_id}"
        )
        self._save_connector_config()
        # Keep the cross-sibling call for now — Task 19 will fix it with a signal
        self.main_window.manual.update_connector_range()

    def _on_connector_add(self) -> None:
        connector = self.engine.add_connector()
        self.settings_panel.rebuild_connector_cards()
        self._selected_connector_id = connector.id
        self.dashboard.set_selected_connector(connector.id)
        self.main_window.manual.update_connector_range()
        self.main_window.log_message(
            f"[green]Connector:[/green] Added connector {connector.id}"
        )
        self._save_connector_config()

    def action_toggle_log_mode(self, is_detailed: bool) -> None:
        self.main_window.signal_bridge.log_mode = (
            "verbose" if is_detailed else "compact"
        )
        self.main_window.app_settings.log_mode = "verbose" if is_detailed else "compact"

    def load_ocpp_config_keys(self) -> None:
        adapter = self.bridge.runner.adapter
        if adapter:
            self.config_keys_panel.set_keys(adapter.config_manager.get_all_keys())

    def _on_ocpp_key_changed(self, key_name: str, new_value: str) -> None:
        adapter = self.bridge.runner.adapter
        if adapter:
            adapter.config_manager.set_key(key_name, new_value)
            self.main_window.log_message(
                f"[green]Config:[/green] OCPP key '{key_name}' set to '{new_value}'"
            )


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
        self.btn_clear_logs.setObjectName("btnClearLog")
        self.btn_clear_logs.setMinimumHeight(24)
        self.btn_clear_logs.clicked.connect(self.log_panel.clear)
        log_header.addWidget(self.btn_clear_logs)

        self.btn_log_mode = QPushButton("Detailed")
        self.btn_log_mode.setObjectName("btnLogMode")
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
            self.main_window.app_settings.log_mode = "verbose"
            self.btn_log_mode.setText("Compact")
        else:
            self.main_window.signal_bridge.log_mode = "compact"
            self.main_window.app_settings.log_mode = "compact"
            self.btn_log_mode.setText("Detailed")

    def update_connector_range(self) -> None:
        """Sync the connector spinner's upper bound to the current connector count."""
        self.input_connector_id.setRange(1, max(len(self.engine.connectors), 1))

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
                    connector_id=self.input_connector_id.value(),
                    error_code="NoError",
                    status="Available",
                ),
                loop,
            )

    def log_message(self, message: str) -> None:
        self.log_panel.log_message(message)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._accumulator: float = 0.0
        self._last_tick_time: float = 0.0
        self._status_check_counter: int = 0

        self.app_settings = AppSettings()

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
        self.signal_bridge.ocpp_config_key_changed.connect(
            self.on_ocpp_config_key_changed
        )
        self.signal_bridge.session_started.connect(self.on_session_started)

        self._setup_ui()
        self._setup_menu()
        self._setup_shortcuts()
        self._restore_ui_state()

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

    def _setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self._nav_header = QWidget()
        self._nav_header.setObjectName("navHeader")
        self._nav_header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._nav_header.setFixedHeight(48)
        self._nav_header.hide()

        nav_layout = QHBoxLayout(self._nav_header)
        nav_layout.setContentsMargins(12, 0, 12, 0)
        nav_layout.setSpacing(8)

        self._btn_home = QToolButton()
        self._btn_home.setObjectName("btnHome")
        self._btn_home.setAutoRaise(True)
        self._btn_home.setFixedSize(36, 36)
        self._btn_home.setIcon(get_icon("home", colors.TEXT_SECONDARY))
        self._btn_home.clicked.connect(self._go_home)
        nav_layout.addWidget(self._btn_home)

        self._nav_title = QLabel("")
        self._nav_title.setObjectName("navTitle")
        nav_layout.addWidget(self._nav_title)
        nav_layout.addStretch()
        main_layout.addWidget(self._nav_header)

        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.setObjectName("mainSplitter")
        main_layout.addWidget(self._splitter, 1)

        self.stack = QStackedWidget()
        self._splitter.addWidget(self.stack)

        self._global_log_panel = CollapsibleLogPanel()
        self._global_log_panel.log_mode_toggled.connect(self._on_global_log_mode_toggle)
        if self.app_settings.log_mode == "verbose":
            self._global_log_panel.btn_log_mode.setChecked(True)
            self._global_log_panel.btn_log_mode.setText("Compact")
        self._global_log_panel.setVisible(False)
        self._splitter.addWidget(self._global_log_panel)

        self._splitter.setStretchFactor(0, 4)
        self._splitter.setStretchFactor(1, 1)

        self.toast_manager = ToastManager(self)

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

        self._btn_toggle_log = QPushButton("Logs")
        self._btn_toggle_log.setObjectName("btnToggleLog")
        self._btn_toggle_log.setProperty("flat", True)
        self._btn_toggle_log.setCheckable(True)
        self._btn_toggle_log.clicked.connect(self._toggle_global_log)
        self.status_bar.addPermanentWidget(self._btn_toggle_log)

    def _setup_shortcuts(self) -> None:
        shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        shortcut_save.activated.connect(self._shortcut_save)

        shortcut_log = QShortcut(QKeySequence("`"), self)
        shortcut_log.activated.connect(self._toggle_global_log)

        shortcut_f1 = QShortcut(QKeySequence("F1"), self)
        shortcut_f1.activated.connect(self._toggle_global_log)

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
            self._global_log_panel.expand()
            self._btn_toggle_log.setChecked(True)

        saved_log_mode = self.app_settings.log_mode
        self.signal_bridge.log_mode = (
            "verbose" if saved_log_mode == "verbose" else "compact"
        )

        saved_ui_mode = self.app_settings.last_mode
        if saved_ui_mode in ("simulator", "manual"):
            self.switch_to_mode(saved_ui_mode)

    def _go_home(self) -> None:
        if self.stack.currentWidget() != self.mode_select:
            self._fade_to_widget(self.mode_select)
            self._nav_header.hide()
            self._global_log_panel.setVisible(False)
            self._btn_toggle_log.setChecked(False)
            self.app_settings.last_mode = ""

    def switch_to_mode(self, mode: str) -> None:
        if mode == "simulator":
            self._fade_to_widget(self.simulator)
            self._nav_title.setText("Simulator Mode")
            self._nav_header.show()
            self._global_log_panel.setVisible(True)
            self.simulator.dashboard.set_recent_tags(self.app_settings.recent_tags)
        elif mode == "manual":
            self._fade_to_widget(self.manual)
            self._nav_title.setText("Manual Mode")
            self._nav_header.show()
            self._global_log_panel.setVisible(True)
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

    def _toggle_global_log(self) -> None:
        if self.stack.currentWidget() == self.mode_select:
            return

        is_checked = self._btn_toggle_log.isChecked()
        self._global_log_panel.setVisible(is_checked)
        self.app_settings.log_panel_expanded = is_checked

    def _on_global_log_mode_toggle(self, is_detailed: bool) -> None:
        mode: LogMode = "verbose" if is_detailed else "compact"
        self.signal_bridge.log_mode = mode
        self.app_settings.log_mode = mode
        self.manual.btn_log_mode.setChecked(is_detailed)
        self.manual.btn_log_mode.setText("Compact" if is_detailed else "Detailed")

    def _shortcut_save(self) -> None:
        if self.stack.currentWidget() == self.simulator:
            self.simulator.action_save_config()

    def show_toast(self, message: str, toast_type: ToastType = "info") -> None:
        self.toast_manager.show_toast(message, toast_type)

    def log_message(self, message: str) -> None:
        self._global_log_panel.log_message(message)
        if self.stack.currentWidget() == self.simulator:
            return
        elif self.stack.currentWidget() == self.manual:
            self.manual.log_message(message)

    def simulate_step(self) -> None:
        current_time = time.monotonic()
        delta = current_time - self._last_tick_time
        self._last_tick_time = current_time
        self._accumulator += delta

        while self._accumulator >= 0.1:
            self.engine.simulate(0.1)
            self._accumulator -= 0.1

        self._status_check_counter += 1
        if self._status_check_counter >= 10:
            self._status_check_counter = 0
            self.signal_bridge.check_connection_status()

        # Always record chart data so no samples are lost while on another panel.
        self.simulator.dashboard.record_telemetry(self.engine)

        if self.stack.currentWidget() == self.simulator:
            self.simulator.update_ui()

    @Slot(str, str, bool)
    def on_log_received(self, source: str, message: str, is_important: bool) -> None:
        if self.signal_bridge.log_mode == "compact" and not is_important:
            return

        tag_map = {
            "Engine": "engine",
            "OCPP": "ocpp",
            "UI": "ui",
        }
        tag = tag_map.get(source, "white")
        formatted_message = f"[{tag}]{source}:[/] {message}"

        if self.stack.currentWidget() == self.mode_select:
            pass
        else:
            self._global_log_panel.log_message(formatted_message)

        if self.stack.currentWidget() == self.manual:
            self.manual.log_message(formatted_message)

    @Slot(bool)
    def on_connection_status_changed(self, connected: bool) -> None:
        if connected:
            self._connection_indicator.setText("Connected")
            self._connection_indicator.setProperty("connected", True)
            adapter = self.bridge.runner.adapter
            if adapter:
                self.signal_bridge.subscribe_to_adapter(adapter)
                self.simulator.load_ocpp_config_keys()
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
        self.show_toast(f"Downloading update: {percent}%", "info")

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
        self.app_settings.log_panel_expanded = self._global_log_panel.is_expanded()

        self.config.connectors = [
            ConnectorConfig(voltage=c.voltage, current=c.current, phase=c.phase)
            for c in self.engine.connectors
        ]
        self.config.save()
        self.bridge.shutdown()
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
