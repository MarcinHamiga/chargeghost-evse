from typing import TYPE_CHECKING, Callable, Optional, cast, Literal
from urllib.parse import urlparse

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from chargeghost_evse.ui.widgets.connector_panel import ConnectorPanel

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
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("settingsScroll")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(20)
        content_layout.setContentsMargins(0, 0, 8, 0)

        connection_group = QGroupBox("Connection Settings")
        conn_form = QFormLayout(connection_group)
        conn_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        conn_form.setSpacing(12)

        self.input_url = ValidatedLineEdit("ws://example.com/ocpp")
        self.input_url.set_validator(validate_url)
        conn_form.addRow("WebSocket URL:", self.input_url)

        self.input_ocpp_id = QLineEdit()
        self.input_ocpp_id.setPlaceholderText("CP-001")
        conn_form.addRow("OCPP ID:", self.input_ocpp_id)

        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.setPlaceholderText("Optional")
        conn_form.addRow("Password:", self.input_password)

        self.checkbox_skip_tls = QCheckBox("Skip TLS Verification")
        conn_form.addRow(self.checkbox_skip_tls)

        self.combo_ocpp_version = QComboBox()
        self.combo_ocpp_version.addItems(["OCPP 1.6J", "OCPP 2.0.1"])
        conn_form.addRow("OCPP Version:", self.combo_ocpp_version)

        content_layout.addWidget(connection_group)

        identity_group = QGroupBox("Station Identity")
        ident_form = QFormLayout(identity_group)
        ident_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        ident_form.setSpacing(12)

        self.input_vendor = QLineEdit()
        self.input_vendor.setPlaceholderText("ChargeGhost")
        ident_form.addRow("Vendor:", self.input_vendor)

        self.input_model = QLineEdit()
        self.input_model.setPlaceholderText("ChargeGhostV1")
        ident_form.addRow("Model:", self.input_model)

        content_layout.addWidget(identity_group)

        simulation_group = QGroupBox("Simulation Mode")
        sim_form = QFormLayout(simulation_group)
        sim_form.setSpacing(12)

        self.checkbox_multi_evse = QCheckBox(
            "Each connector operates as an independent EVSE"
        )
        self.checkbox_multi_evse.setToolTip(
            "When enabled, each connector can run a separate charging session "
            "simultaneously. When disabled, only one session can be active at a time."
        )
        sim_form.addRow(self.checkbox_multi_evse)

        content_layout.addWidget(simulation_group)

        connectors_group = QGroupBox("Connector Management")
        conn_group_layout = QVBoxLayout(connectors_group)
        conn_group_layout.setContentsMargins(8, 16, 8, 8)
        conn_group_layout.setSpacing(8)

        self.connector_panel = ConnectorPanel()
        conn_group_layout.addWidget(self.connector_panel)

        content_layout.addWidget(connectors_group)

        self.btn_save = QPushButton("Save Configuration")
        self.btn_save.setObjectName("btnSaveConfig")
        self.btn_save.setProperty("primary", True)
        self.btn_save.setMinimumHeight(44)
        self.btn_save.clicked.connect(self._on_save_config)
        content_layout.addWidget(self.btn_save)

        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

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
