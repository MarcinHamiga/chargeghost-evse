import time
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
	QFrame,
	QGridLayout,
	QHBoxLayout,
	QLabel,
	QLineEdit,
	QProgressBar,
	QPushButton,
	QVBoxLayout,
	QWidget,
)

from chargeghost_evse.ui.widgets.connector_strip import ConnectorStrip

if TYPE_CHECKING:
	from chargeghost_evse.engine.engine import Engine


class MetricCard(QFrame):
	def __init__(self, title: str, unit: str = "", parent: Optional[QWidget] = None):
		super().__init__(parent)
		self.setObjectName("metricCard")
		self.setProperty("card", True)
		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

		layout = QVBoxLayout(self)
		layout.setSpacing(4)
		layout.setContentsMargins(16, 12, 16, 12)

		self._title_label = QLabel(title)
		self._title_label.setObjectName("metricTitle")
		layout.addWidget(self._title_label)

		value_layout = QHBoxLayout()
		value_layout.setSpacing(4)

		self._value_label = QLabel("--")
		self._value_label.setObjectName("metricValue")
		value_layout.addWidget(self._value_label)

		if unit:
			self._unit_label = QLabel(unit)
			self._unit_label.setObjectName("metricUnit")
			value_layout.addWidget(self._unit_label, alignment=Qt.AlignmentFlag.AlignBottom)

		value_layout.addStretch()
		layout.addLayout(value_layout)

	def set_value(self, value: str) -> None:
		self._value_label.setText(value)

	def clear(self) -> None:
		self._value_label.setText("--")


class CollapsibleDetails(QWidget):
	toggled = Signal(bool)

	def __init__(self, parent: Optional[QWidget] = None):
		super().__init__(parent)
		self._is_expanded = False
		self._setup_ui()

	def _setup_ui(self) -> None:
		layout = QVBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)

		self._toggle_btn = QPushButton("▶ Details")
		self._toggle_btn.setObjectName("toggleDetailsBtn")
		self._toggle_btn.setProperty("flat", True)
		self._toggle_btn.clicked.connect(self._toggle)
		layout.addWidget(self._toggle_btn)

		self._content = QWidget()
		self._content.setObjectName("detailsContent")
		content_layout = QGridLayout(self._content)
		content_layout.setSpacing(12)
		content_layout.setContentsMargins(8, 8, 8, 8)

		self.metric_tx_id = MetricCard("Transaction ID")
		self.metric_voltage = MetricCard("Voltage", "V")
		self.metric_current = MetricCard("Current", "A")
		self.metric_meter = MetricCard("Total Meter", "Wh")

		content_layout.addWidget(self.metric_tx_id, 0, 0)
		content_layout.addWidget(self.metric_voltage, 0, 1)
		content_layout.addWidget(self.metric_current, 1, 0)
		content_layout.addWidget(self.metric_meter, 1, 1)

		self._content.hide()
		layout.addWidget(self._content)

	def _toggle(self) -> None:
		self._is_expanded = not self._is_expanded
		if self._is_expanded:
			self._toggle_btn.setText("▼ Details")
			self._content.show()
		else:
			self._toggle_btn.setText("▶ Details")
			self._content.hide()
		self.toggled.emit(self._is_expanded)

	def is_expanded(self) -> bool:
		return self._is_expanded

	def update_metrics(
		self,
		tx_id: Optional[int],
		voltage: float,
		current: float,
		meter: float,
	) -> None:
		self.metric_tx_id.set_value(str(tx_id) if tx_id else "--")
		self.metric_voltage.set_value(f"{voltage:.1f}")
		self.metric_current.set_value(f"{current:.1f}")
		self.metric_meter.set_value(f"{meter:.1f}")

	def clear(self) -> None:
		for metric in [self.metric_tx_id, self.metric_voltage, self.metric_current, self.metric_meter]:
			metric.clear()


class SessionDashboard(QWidget):
	connector_selected = Signal(int)
	plug_in_clicked = Signal()
	unplug_clicked = Signal()
	start_charging_clicked = Signal()
	stop_charging_clicked = Signal()
	apply_id_tag_clicked = Signal(str)

	def __init__(self, parent: Optional[QWidget] = None):
		super().__init__(parent)
		self._selected_connector_id: int = 1
		self._setup_ui()

	def _setup_ui(self) -> None:
		layout = QVBoxLayout(self)
		layout.setSpacing(16)
		layout.setContentsMargins(16, 16, 16, 16)

		self.connector_strip = ConnectorStrip()
		self.connector_strip.connector_selected.connect(self._on_connector_selected)
		layout.addWidget(self.connector_strip)

		primary_metrics = QGridLayout()
		primary_metrics.setSpacing(12)

		self.metric_energy = MetricCard("Energy Charged", "Wh")
		self.metric_power = MetricCard("Current Power", "kW")
		self.metric_duration = MetricCard("Duration", "s")
		self.metric_soc = MetricCard("State of Charge", "%")

		primary_metrics.addWidget(self.metric_energy, 0, 0)
		primary_metrics.addWidget(self.metric_power, 0, 1)
		primary_metrics.addWidget(self.metric_duration, 1, 0)
		primary_metrics.addWidget(self.metric_soc, 1, 1)
		layout.addLayout(primary_metrics)

		soc_section = QFrame()
		soc_section.setObjectName("socSection")
		soc_layout = QVBoxLayout(soc_section)
		soc_layout.setContentsMargins(12, 12, 12, 12)
		soc_layout.setSpacing(8)

		soc_header = QHBoxLayout()
		soc_title = QLabel("Charging Progress")
		soc_title.setObjectName("socTitle")
		soc_header.addWidget(soc_title)

		self._soc_percent_label = QLabel("0%")
		self._soc_percent_label.setObjectName("socPercent")
		soc_header.addStretch()
		soc_header.addWidget(self._soc_percent_label)
		soc_layout.addLayout(soc_header)

		self.soc_progress = QProgressBar()
		self.soc_progress.setMinimumHeight(8)
		self.soc_progress.setTextVisible(False)
		self.soc_progress.setValue(0)
		soc_layout.addWidget(self.soc_progress)

		layout.addWidget(soc_section)

		self.details = CollapsibleDetails()
		layout.addWidget(self.details)

		id_tag_section = QFrame()
		id_tag_section.setObjectName("idTagSection")
		id_tag_layout = QHBoxLayout(id_tag_section)
		id_tag_layout.setContentsMargins(12, 8, 12, 8)
		id_tag_layout.setSpacing(12)

		id_tag_label = QLabel("ID Tag")
		id_tag_label.setObjectName("idTagLabel")
		id_tag_layout.addWidget(id_tag_label)

		self.input_id_tag = QLineEdit()
		self.input_id_tag.setPlaceholderText("Enter RFID tag (e.g., RFID-001)")
		self.input_id_tag.returnPressed.connect(self._on_apply_id_tag)
		id_tag_layout.addWidget(self.input_id_tag, 1)

		self.btn_apply_tag = QPushButton("Apply")
		self.btn_apply_tag.setObjectName("btnApplyTag")
		self.btn_apply_tag.clicked.connect(self._on_apply_id_tag)
		id_tag_layout.addWidget(self.btn_apply_tag)

		layout.addWidget(id_tag_section)

		actions = QHBoxLayout()
		actions.setSpacing(12)

		self.btn_plug = QPushButton("Plug In")
		self.btn_plug.setObjectName("btnPlug")
		self.btn_plug.setProperty("primary", True)
		self.btn_plug.setMinimumHeight(48)
		self.btn_plug.clicked.connect(self.plug_in_clicked)
		actions.addWidget(self.btn_plug, 1)

		self.btn_charge = QPushButton("Start Charging")
		self.btn_charge.setObjectName("btnCharge")
		self.btn_charge.setProperty("success", True)
		self.btn_charge.setMinimumHeight(48)
		self.btn_charge.clicked.connect(self._on_charge_clicked)
		actions.addWidget(self.btn_charge, 1)

		self.btn_unplug = QPushButton("Unplug")
		self.btn_unplug.setObjectName("btnUnplug")
		self.btn_unplug.setProperty("danger", True)
		self.btn_unplug.setMinimumHeight(48)
		self.btn_unplug.clicked.connect(self.unplug_clicked)
		actions.addWidget(self.btn_unplug, 1)

		layout.addLayout(actions)
		layout.addStretch()

	def _on_connector_selected(self, connector_id: int) -> None:
		self._selected_connector_id = connector_id
		self.connector_selected.emit(connector_id)

	def _on_charge_clicked(self) -> None:
		if self.btn_charge.text().startswith("Start"):
			self.start_charging_clicked.emit()
		else:
			self.stop_charging_clicked.emit()

	def _on_apply_id_tag(self) -> None:
		tag = self.input_id_tag.text().strip()
		if tag:
			self.apply_id_tag_clicked.emit(tag)

	def get_selected_connector_id(self) -> int:
		return self._selected_connector_id

	def set_selected_connector(self, connector_id: int) -> None:
		self._selected_connector_id = connector_id
		self.connector_strip.set_selected_connector(connector_id)

	def update_from_engine(self, engine: "Engine") -> None:
		self.connector_strip.update_connectors(engine)

		conn = engine.get_connector(self._selected_connector_id)
		if not conn:
			return

		self.btn_plug.setEnabled(not conn.is_plugged_in)
		self.btn_unplug.setEnabled(conn.is_plugged_in)
		self.btn_charge.setEnabled(conn.is_plugged_in)

		power_kw = (conn.voltage * conn.current * conn.phase) / 1000.0
		self.metric_power.set_value(f"{power_kw:.2f}")

		session = engine.session
		if session and session.connector_id == self._selected_connector_id:
			self.metric_energy.set_value(f"{session.energy_charged:.1f}")
			self.metric_soc.set_value(f"{session.state_of_charge:.1f}")
			duration = time.monotonic() - session.start_time
			self.metric_duration.set_value(f"{duration:.0f}")
			self.soc_progress.setValue(int(session.state_of_charge))
			self._soc_percent_label.setText(f"{session.state_of_charge:.0f}%")

			self.btn_charge.setText("Stop Charging")
			self.btn_charge.setProperty("success", False)
			self.btn_charge.setProperty("danger", True)
		else:
			self.metric_energy.clear()
			self.metric_soc.clear()
			self.metric_duration.clear()
			self.soc_progress.setValue(0)
			self._soc_percent_label.setText("0%")

			self.btn_charge.setText("Start Charging")
			self.btn_charge.setProperty("success", True)
			self.btn_charge.setProperty("danger", False)

		self._refresh_widget_style(self.btn_charge)

		self.details.update_metrics(
			tx_id=session.transaction_id if session else None,
			voltage=conn.voltage,
			current=conn.current,
			meter=engine.energy_meter.get_meter_reading(),
		)

	def _refresh_widget_style(self, widget: QWidget) -> None:
		widget.style().unpolish(widget)
		widget.style().polish(widget)

	def set_id_tag(self, tag: str) -> None:
		self.input_id_tag.setText(tag)
