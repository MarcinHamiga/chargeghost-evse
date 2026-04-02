from typing import TYPE_CHECKING, Callable, Optional, cast, Literal
from urllib.parse import urlparse

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from chargeghost_evse.ui.widgets.connector_panel import ConnectorPanel
from chargeghost_evse.util.config import (
    BATTERY_CAPACITY_DEFAULT,
    BATTERY_CAPACITY_MAX,
    BATTERY_CAPACITY_MIN,
)

if TYPE_CHECKING:
    from chargeghost_evse.engine.engine import Engine
    from chargeghost_evse.util.config import SimulationConfig


class ValidatedLineEdit(QWidget):
    validation_changed = Signal(bool)

    def __init__(self, placeholder: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._is_valid = True
        self._validator: Optional[Callable[[str], Optional[str]]] = None
        self._setup_ui(placeholder)

    def _setup_ui(self, placeholder: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._input = QLineEdit()
        self._input.setPlaceholderText(placeholder)
        self._input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._input)

        self._error_label = QLabel()
        self._error_label.setProperty("validationError", True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

    def set_validator(self, validator: Callable[[str], Optional[str]]) -> None:
        self._validator = validator

    def _on_text_changed(self, text: str) -> None:
        if self._validator:
            error = self._validator(text)
            if error:
                self._show_error(error)
            else:
                self._clear_error()

    def _show_error(self, message: str) -> None:
        self._is_valid = False
        self._input.setProperty("validationError", True)
        self._input.style().unpolish(self._input)
        self._input.style().polish(self._input)
        self._error_label.setText(message)
        self._error_label.show()
        self.validation_changed.emit(False)

    def _clear_error(self) -> None:
        self._is_valid = True
        self._input.setProperty("validationError", False)
        self._input.style().unpolish(self._input)
        self._input.style().polish(self._input)
        self._error_label.hide()
        self.validation_changed.emit(True)

    def text(self) -> str:
        return self._input.text()

    def setText(self, text: str) -> None:
        self._input.setText(text)

    def setEchoMode(self, mode: QLineEdit.EchoMode) -> None:
        self._input.setEchoMode(mode)

    def setPlaceholderText(self, text: str) -> None:
        self._input.setPlaceholderText(text)

    def is_valid(self) -> bool:
        return self._is_valid

    def setEnabled(self, enabled: bool) -> None:
        self._input.setEnabled(enabled)


def validate_url(text: str) -> Optional[str]:
    if not text:
        return None
    try:
        parsed = urlparse(text)
        if parsed.scheme not in ("ws", "wss"):
            return "URL must start with ws:// or wss://"
        if not parsed.netloc:
            return "Invalid URL format"
    except Exception:
        return "Invalid URL format"
    return None


class SettingsPanel(QWidget):
    save_config_clicked = Signal()
    ocpp_key_changed = Signal(str, str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._engine: Optional["Engine"] = None
        self._config: Optional["SimulationConfig"] = None
        self._on_connector_apply: Optional[Callable] = None
        self._on_connector_remove: Optional[Callable] = None
        self._on_connector_add: Optional[Callable] = None
        self._layout_mode: str = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("settingsPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("settingsScroll")

        self._body_content = QWidget()
        self._body_layout = QHBoxLayout(self._body_content)
        self._body_layout.setSpacing(16)
        self._body_layout.setContentsMargins(0, 0, 8, 0)

        self._rail = self._build_settings_rail()
        self._workspace = self._build_connector_workspace()

        self._body_layout.addWidget(self._rail)
        self._body_layout.addWidget(self._workspace, 1)

        scroll.setWidget(self._body_content)
        root.addWidget(scroll, 1)

        self._update_layout_mode()

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("settingsHeader")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        lay = QHBoxLayout(header)
        lay.setContentsMargins(0, 0, 0, 0)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title = QLabel("Settings")
        title.setObjectName("settingsHeaderTitle")
        text_col.addWidget(title)

        body = QLabel("Configure your EVSE connection, identity, and connectors.")
        body.setObjectName("settingsHeaderBody")
        text_col.addWidget(body)

        lay.addLayout(text_col, 1)

        save_bar = QFrame()
        save_bar.setObjectName("settingsSaveBar")
        save_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        save_lay = QHBoxLayout(save_bar)
        save_lay.setContentsMargins(0, 0, 0, 0)

        self.btn_save = QPushButton("Save Configuration")
        self.btn_save.setObjectName("btnSaveConfig")
        self.btn_save.setProperty("primary", True)
        self.btn_save.setMinimumHeight(44)
        self.btn_save.clicked.connect(self._on_save_config)
        save_lay.addWidget(self.btn_save)

        lay.addWidget(save_bar)
        return header

    def _build_settings_rail(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("settingsRail")
        lay = QVBoxLayout(rail)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(self._build_connection_card())
        lay.addWidget(self._build_identity_card())
        lay.addWidget(self._build_simulation_card())
        lay.addStretch()
        return rail

    def _make_card(self, title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("settingsCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(card)
        lay.setSpacing(8)
        lay.setContentsMargins(16, 16, 16, 16)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("settingsCardTitle")
        lay.addWidget(title_lbl)
        return card

    def _build_connection_card(self) -> QFrame:
        card = self._make_card("Connection")
        lay = cast(QVBoxLayout, card.layout())

        lay.addWidget(QLabel("WebSocket URL"))
        self.input_url = ValidatedLineEdit("ws://example.com/ocpp")
        self.input_url.set_validator(validate_url)
        lay.addWidget(self.input_url)

        row_id_pw = QHBoxLayout()
        row_id_pw.setSpacing(8)

        col_id = QVBoxLayout()
        col_id.setSpacing(2)
        col_id.addWidget(QLabel("OCPP ID"))
        self.input_ocpp_id = QLineEdit()
        self.input_ocpp_id.setPlaceholderText("CP-001")
        col_id.addWidget(self.input_ocpp_id)
        row_id_pw.addLayout(col_id)

        col_pw = QVBoxLayout()
        col_pw.setSpacing(2)
        col_pw.addWidget(QLabel("Password"))
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.setPlaceholderText("Optional")
        col_pw.addWidget(self.input_password)
        row_id_pw.addLayout(col_pw)

        lay.addLayout(row_id_pw)

        row_ver_tls = QHBoxLayout()
        row_ver_tls.setSpacing(8)

        col_ver = QVBoxLayout()
        col_ver.setSpacing(2)
        col_ver.addWidget(QLabel("OCPP Version"))
        self.combo_ocpp_version = QComboBox()
        self.combo_ocpp_version.addItems(["OCPP 1.6J", "OCPP 2.0.1"])
        col_ver.addWidget(self.combo_ocpp_version)
        row_ver_tls.addLayout(col_ver)

        self.checkbox_skip_tls = QCheckBox("Skip TLS Verification")
        row_ver_tls.addWidget(self.checkbox_skip_tls)
        row_ver_tls.addStretch()

        lay.addLayout(row_ver_tls)
        return card

    def _build_identity_card(self) -> QFrame:
        card = self._make_card("Station Identity")
        lay = cast(QVBoxLayout, card.layout())

        row = QHBoxLayout()
        row.setSpacing(8)

        col_v = QVBoxLayout()
        col_v.setSpacing(2)
        col_v.addWidget(QLabel("Vendor"))
        self.input_vendor = QLineEdit()
        self.input_vendor.setPlaceholderText("ChargeGhost")
        col_v.addWidget(self.input_vendor)
        row.addLayout(col_v)

        col_m = QVBoxLayout()
        col_m.setSpacing(2)
        col_m.addWidget(QLabel("Model"))
        self.input_model = QLineEdit()
        self.input_model.setPlaceholderText("ChargeGhostV1")
        col_m.addWidget(self.input_model)
        row.addLayout(col_m)

        lay.addLayout(row)
        return card

    def _build_simulation_card(self) -> QFrame:
        card = self._make_card("Simulation")
        lay = cast(QVBoxLayout, card.layout())

        self.checkbox_multi_evse = QCheckBox(
            "Each connector operates as an independent EVSE"
        )
        self.checkbox_multi_evse.setToolTip(
            "When enabled, each connector can run a separate charging "
            "session simultaneously. When disabled, only one session "
            "can be active at a time."
        )
        lay.addWidget(self.checkbox_multi_evse)

        capacity_row = QHBoxLayout()
        capacity_row.setSpacing(8)

        col_cap = QVBoxLayout()
        col_cap.setSpacing(2)
        col_cap.addWidget(QLabel("EV Battery Capacity"))
        self.input_battery_capacity = QDoubleSpinBox()
        self.input_battery_capacity.setRange(BATTERY_CAPACITY_MIN, BATTERY_CAPACITY_MAX)
        self.input_battery_capacity.setValue(BATTERY_CAPACITY_DEFAULT)
        self.input_battery_capacity.setSuffix(" kWh")
        self.input_battery_capacity.setDecimals(1)
        self.input_battery_capacity.setSingleStep(5.0)
        self.input_battery_capacity.setMinimumWidth(120)
        self.input_battery_capacity.setToolTip(
            "Sets the simulated EV battery capacity. Controls state-of-charge "
            "percentage calculation during charging sessions."
        )
        col_cap.addWidget(self.input_battery_capacity)
        capacity_row.addLayout(col_cap)
        capacity_row.addStretch()

        lay.addLayout(capacity_row)
        return card

    def _build_connector_workspace(self) -> QWidget:
        workspace = QWidget()
        workspace.setObjectName("settingsWorkspace")
        lay = QVBoxLayout(workspace)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        title = QLabel("Connector Management")
        title.setObjectName("settingsCardTitle")
        lay.addWidget(title)

        self.connector_panel = ConnectorPanel()
        lay.addWidget(self.connector_panel, 1)

        return workspace

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_layout_mode()

    def _update_layout_mode(self) -> None:
        mode = "split" if self.width() >= 1050 else "stacked"
        if mode != self._layout_mode:
            self._set_layout_mode(mode)

    def _set_layout_mode(self, mode: str) -> None:
        self._layout_mode = mode
        self.setProperty("layoutMode", mode)
        self.style().unpolish(self)
        self.style().polish(self)

        if mode == "stacked":
            self._body_layout.setDirection(QBoxLayout.Direction.TopToBottom)
        else:
            self._body_layout.setDirection(QBoxLayout.Direction.LeftToRight)

    def set_engine(self, engine: "Engine") -> None:
        self._engine = engine
        self.connector_panel.set_engine(engine)

    def set_config(self, config: "SimulationConfig") -> None:
        self._config = config
        self._populate_fields()

    def _populate_fields(self) -> None:
        if not self._config:
            return

        self.input_url.setText(self._config.connection_url)
        self.input_ocpp_id.setText(self._config.ocpp_id)
        self.input_password.setText(self._config.ocpp_password)
        self.input_vendor.setText(self._config.charge_point_vendor)
        self.input_model.setText(self._config.charge_point_model)
        self.checkbox_skip_tls.setChecked(self._config.skip_tls_verify)
        self.checkbox_multi_evse.setChecked(self._config.multi_evse_mode)
        self.input_battery_capacity.setValue(self._config.ev_battery_capacity)
        ocpp_version_map = {"1.6": "OCPP 1.6J", "2.0.1": "OCPP 2.0.1"}
        self.combo_ocpp_version.setCurrentText(
            ocpp_version_map.get(self._config.ocpp_version, "OCPP 1.6J")
        )

    def set_connector_callbacks(
        self,
        on_apply: Optional[Callable] = None,
        on_remove: Optional[Callable] = None,
        on_add: Optional[Callable] = None,
    ) -> None:
        self._on_connector_apply = on_apply
        self._on_connector_remove = on_remove
        self._on_connector_add = on_add
        self.connector_panel.set_callbacks(
            on_apply=on_apply,
            on_remove=on_remove,
            on_add=on_add,
        )

    def _on_save_config(self) -> None:
        if not self._config:
            return

        if not self.input_url.is_valid():
            return

        self._config.connection_url = self.input_url.text().strip()
        self._config.ocpp_id = self.input_ocpp_id.text().strip()
        self._config.ocpp_password = self.input_password.text()
        self._config.charge_point_vendor = (
            self.input_vendor.text().strip() or "ChargeGhost"
        )
        self._config.charge_point_model = (
            self.input_model.text().strip() or "ChargeGhostV1"
        )
        self._config.skip_tls_verify = self.checkbox_skip_tls.isChecked()
        self._config.multi_evse_mode = self.checkbox_multi_evse.isChecked()
        self._config.ev_battery_capacity = self.input_battery_capacity.value()
        ocpp_version_map = {"OCPP 1.6J": "1.6", "OCPP 2.0.1": "2.0.1"}
        self._config.ocpp_version = cast(
            "Literal['1.6', '2.0.1']",
            ocpp_version_map.get(self.combo_ocpp_version.currentText(), "1.6"),
        )

        self.save_config_clicked.emit()

    def get_url(self) -> str:
        return self.input_url.text().strip()

    def rebuild_connector_cards(self) -> None:
        self.connector_panel.rebuild_cards()
