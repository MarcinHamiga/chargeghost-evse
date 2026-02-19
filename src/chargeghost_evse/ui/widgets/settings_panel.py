from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
	QCheckBox,
	QFormLayout,
	QGroupBox,
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


class SettingsPanel(QWidget):
	save_config_clicked = Signal()

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
		conn_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
		conn_form.setSpacing(12)

		self.input_url = QLineEdit()
		self.input_url.setPlaceholderText("ws://example.com/ocpp")
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

		content_layout.addWidget(connection_group)

		identity_group = QGroupBox("Station Identity")
		ident_form = QFormLayout(identity_group)
		ident_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
		ident_form.setSpacing(12)

		self.input_vendor = QLineEdit()
		self.input_vendor.setPlaceholderText("ChargeGhost")
		ident_form.addRow("Vendor:", self.input_vendor)

		self.input_model = QLineEdit()
		self.input_model.setPlaceholderText("ChargeGhostV1")
		ident_form.addRow("Model:", self.input_model)

		content_layout.addWidget(identity_group)

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

		self._config.connection_url = self.input_url.text().strip()
		self._config.ocpp_id = self.input_ocpp_id.text().strip()
		self._config.ocpp_password = self.input_password.text()
		self._config.charge_point_vendor = self.input_vendor.text().strip() or "ChargeGhost"
		self._config.charge_point_model = self.input_model.text().strip() or "ChargeGhostV1"
		self._config.skip_tls_verify = self.checkbox_skip_tls.isChecked()

		self.save_config_clicked.emit()

	def get_url(self) -> str:
		return self.input_url.text().strip()

	def rebuild_connector_cards(self) -> None:
		self.connector_panel.rebuild_cards()
