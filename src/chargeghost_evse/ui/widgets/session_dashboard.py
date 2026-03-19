"""
Session Dashboard Widget Module.

This module provides the main charging session dashboard for the ChargeGhost
EVSE simulator. It includes real-time telemetry visualization, session metrics,
connector selection, and charging controls.

Classes:
    TelemetryChart: Real-time power telemetry line chart.
    MetricCard: Display card for a single metric value.
    ContextChip: Compact label+value chip for the context rail.
    IdTagInput: ID tag input field with recent tags dropdown.
    SessionDashboard: Main dashboard widget combining all components.

Example:
    >>> from chargeghost_evse.ui.widgets.session_dashboard import SessionDashboard
    >>>
    >>> dashboard = SessionDashboard()
    >>> dashboard.start_charging_clicked.connect(self._start_session)
"""

import time
from typing import TYPE_CHECKING, Optional

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
	QComboBox,
	QFrame,
	QHBoxLayout,
	QLabel,
	QLineEdit,
	QProgressBar,
	QPushButton,
	QVBoxLayout,
	QWidget,
)

from chargeghost_evse.ui.styles import colors

from chargeghost_evse.engine.connector import ConnectorState

if TYPE_CHECKING:
	from chargeghost_evse.engine.engine import Engine


class TelemetryChart(QFrame):
	def __init__(self, parent: Optional[QWidget] = None):
		super().__init__(parent)
		self.setObjectName("telemetryChartFrame")
		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		self.setMinimumHeight(200)

		self._window_seconds = 60.0
		self._max_points = 600
		self._power_data: list[QPointF] = []
		self._current_data: list[QPointF] = []
		self._start_time = time.monotonic()

		self._setup_ui()

	def _setup_ui(self) -> None:
		"""
		Build and configure the chart UI components.
		"""
		layout = QVBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)

		# Create chart with transparent background
		self.chart = QChart()
		self.chart.setBackgroundVisible(False)
		self.chart.layout().setContentsMargins(0, 0, 0, 0)
		self.chart.legend().hide()

		# Power line series (cyan color)
		self.series_power = QLineSeries()
		power_pen = QPen(QColor(colors.ACCENT_TEAL))
		power_pen.setWidth(2)
		self.series_power.setPen(power_pen)
		self.chart.addSeries(self.series_power)

		# X-axis: Time in seconds
		self.axis_x = QValueAxis()
		self.axis_x.setRange(0, self._window_seconds)
		self.axis_x.setLabelFormat("%.0f s")
		self.axis_x.setTitleText("Session time (s)")
		self.axis_x.setGridLineVisible(True)
		self.axis_x.setGridLineColor(QColor(colors.BORDER_DEFAULT))
		self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
		self.series_power.attachAxis(self.axis_x)

		# Y-axis: Power in kW
		self.axis_y = QValueAxis()
		self.axis_y.setRange(0, 25)  # 22kW is common max
		self.axis_y.setLabelFormat("%.1f kW")
		self.axis_y.setTitleText("Power (kW)")
		self.axis_y.setGridLineVisible(True)
		self.axis_y.setGridLineColor(QColor(colors.BORDER_DEFAULT))
		self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)
		self.series_power.attachAxis(self.axis_y)

		# Chart view with antialiasing
		self.chart_view = QChartView(self.chart)
		self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
		self.chart_view.setBackgroundRole(self.backgroundRole())
		layout.addWidget(self.chart_view)

	def add_point(self, power_kw: float) -> None:
		current_time = time.monotonic() - self._start_time
		self._power_data.append(QPointF(current_time, power_kw))

		# Keep only data within the window (e.g. last 60 seconds)
		while self._power_data and (current_time - self._power_data[0].x() > self._window_seconds):
			self._power_data.pop(0)

		if len(self._power_data) > self._max_points:
			self._power_data = self._power_data[-self._max_points:]

		self.series_power.replace(self._power_data)

		# Update X axis range for rolling effect
		if current_time > self._window_seconds:
			self.axis_x.setRange(current_time - self._window_seconds, current_time)
		else:
			self.axis_x.setRange(0, self._window_seconds)

		# Auto-scale Y axis
		max_power = max((p.y() for p in self._power_data), default=25)
		if max_power > self.axis_y.max():
			self.axis_y.setRange(0, max_power * 1.2)
		elif max_power < self.axis_y.max() * 0.4 and self.axis_y.max() > 25:
			# Scale down if power drops significantly and we are above default max
			self.axis_y.setRange(0, max(25, max_power * 1.5))

	def clear(self) -> None:
		self._power_data.clear()
		self.series_power.clear()
		self.axis_x.setRange(0, self._window_seconds)
		self.axis_y.setRange(0, 25)


class MetricCard(QFrame):
	"""
	Display card for a single metric value.

	Shows a title, value, and optional unit in a styled card format.
	Used for displaying session metrics like energy, power, voltage.

	Attributes:
		_title_label: Label showing the metric title.
		_value_label: Label showing the metric value.
		_unit_label: Optional label showing the unit.

	Example:
		>>> card = MetricCard("Energy", "kWh")
		>>> card.set_value("45.2")
		>>> card.clear()  # Shows "--"
	"""

	def __init__(
		self, title: str, unit: str = "", parent: Optional[QWidget] = None
	) -> None:
		"""
		Initialize the metric card.

		Args:
			title: The metric title/label.
			unit: Optional unit suffix to display.
			parent: Optional parent widget.
		"""
		super().__init__(parent)
		self.setObjectName("metricCard")
		self.setProperty("card", True)
		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

		layout = QVBoxLayout(self)
		layout.setSpacing(0)
		layout.setContentsMargins(10, 6, 10, 6)

		# Title label
		self._title_label = QLabel(title)
		self._title_label.setObjectName("metricTitle")
		layout.addWidget(self._title_label)

		# Value layout with optional unit
		value_layout = QHBoxLayout()
		value_layout.setSpacing(4)
		value_layout.setAlignment(
			Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
		)

		self._value_label = QLabel("--")
		self._value_label.setObjectName("metricValue")
		value_layout.addWidget(self._value_label)

		if unit:
			self._unit_label = QLabel(unit)
			self._unit_label.setObjectName("metricUnit")
			value_layout.addWidget(
				self._unit_label, alignment=Qt.AlignmentFlag.AlignBottom
			)

		value_layout.addStretch()
		layout.addLayout(value_layout)

	def set_value(self, value: str) -> None:
		"""
		Set the metric value.

		Args:
			value: The value string to display.
		"""
		self._value_label.setText(value)

	def clear(self) -> None:
		"""
		Clear the metric value (shows "--").
		"""
		self._value_label.setText("--")


class IdTagInput(QWidget):
	"""
	ID tag input widget with recent tags dropdown.

	Provides a text input for entering RFID tags with a dropdown
	for quickly selecting recently used tags.

	Signals:
		tag_applied: Emitted when user applies a tag.
			Parameters: tag (str)
		recent_tags_changed: Emitted when recent tags list changes.

	Example:
		>>> input_widget = IdTagInput()
		>>> input_widget.set_recent_tags(["RFID-001", "RFID-002"])
		>>> input_widget.tag_applied.connect(self._on_tag_applied)
	"""

	tag_applied = Signal(str)
	recent_tags_changed = Signal()

	def __init__(self, parent: Optional[QWidget] = None, button_text: str = "Apply") -> None:
		"""
		Initialize the ID tag input.

		Args:
			parent: Optional parent widget.
			button_text: Text for the action button.
		"""
		super().__init__(parent)
		self._recent_tags: list[str] = []
		self._button_text = button_text
		self._setup_ui()

	def _setup_ui(self) -> None:
		"""
		Build the UI with label, recent tags, and input field in a more vertical-friendly layout.
		"""
		layout = QVBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(8)

		header = QHBoxLayout()
		id_tag_label = QLabel("ID Tag")
		id_tag_label.setObjectName("idTagLabel")
		header.addWidget(id_tag_label)
		header.addStretch()

		# Recent tags dropdown (hidden when empty)
		self._recent_combo = QComboBox()
		self._recent_combo.setObjectName("recentTagsCombo")
		self._recent_combo.setPlaceholderText("Recent tags...")
		self._recent_combo.setMinimumWidth(100)
		self._recent_combo.currentTextChanged.connect(self._on_recent_selected)
		self._recent_combo.hide()
		header.addWidget(self._recent_combo)
		layout.addLayout(header)

		input_row = QHBoxLayout()
		input_row.setSpacing(8)

		# Text input
		self._input = QLineEdit()
		self._input.setPlaceholderText("Enter RFID tag")
		self._input.returnPressed.connect(self._on_apply)
		input_row.addWidget(self._input, 1)

		# Apply button
		self._apply_btn = QPushButton(self._button_text)
		self._apply_btn.setObjectName("btnApplyTag")
		self._apply_btn.clicked.connect(self._on_apply)
		self._apply_btn.setMinimumHeight(32)
		input_row.addWidget(self._apply_btn)

		layout.addLayout(input_row)

	def _on_recent_selected(self, tag: str) -> None:
		"""
		Handle selection from recent tags dropdown.

		Args:
			tag: The selected tag.
		"""
		if tag:
			self._input.setText(tag)

	def _on_apply(self) -> None:
		"""
		Handle apply button click or Enter key.
		"""
		tag = self._input.text().strip()
		if tag:
			self.tag_applied.emit(tag)

	def set_recent_tags(self, tags: list[str]) -> None:
		"""
		Set the list of recent tags for the dropdown.

		Args:
			tags: List of recent tag strings (max 10).
		"""
		self._recent_tags = tags[:10]
		self._recent_combo.clear()
		if self._recent_tags:
			self._recent_combo.addItems(self._recent_tags)
			self._recent_combo.show()
		else:
			self._recent_combo.hide()

	def set_applied_tag(self, tag: Optional[str]) -> None:
		"""
		Set the currently applied tag to display as ghost text (placeholder).

		Args:
			tag: The tag string currently applied to the connector.
		"""
		if tag:
			self._input.setPlaceholderText(f"Active: {tag}")
		else:
			self._input.setPlaceholderText("Enter RFID tag")

	def get_tag(self) -> str:
		"""
		Get the current tag text.

		Returns:
			Current text in the input field.
		"""
		return self._input.text().strip()

	def set_tag(self, tag: str) -> None:
		"""
		Set the tag text in the input field.

		Args:
			tag: The tag string to set.
		"""
		self._input.setText(tag)

	def set_enabled(self, enabled: bool) -> None:
		self._input.setEnabled(enabled)
		self._recent_combo.setEnabled(enabled)
		self._apply_btn.setEnabled(enabled)


def _compute_effective_power_kw(engine: "Engine", connector_id: int) -> float:
	"""Return delivered power in kW, honouring smart charging limits. 0 when not charging."""
	conn = engine.get_connector(connector_id)
	if conn is None or not engine.energy_meter.is_charging:
		return 0.0
	session = engine.session
	if session is None or session.connector_id != connector_id:
		return 0.0
	effective_current = conn.current
	if engine.get_limit is not None:
		limit = engine.get_limit(session.connector_id, session.transaction_id)
		if limit is not None and limit >= 0:
			effective_current = min(conn.current, limit)
	return (conn.voltage * effective_current * conn.phase) / 1000.0


class ContextChip(QFrame):
	"""Compact label+value chip for the context rail."""

	def __init__(self, label: str, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)
		self.setObjectName("contextChip")
		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

		layout = QVBoxLayout(self)
		layout.setContentsMargins(8, 4, 8, 4)
		layout.setSpacing(1)

		self._label = QLabel(label)
		self._label.setObjectName("contextChipLabel")
		layout.addWidget(self._label)

		self._value = QLabel("--")
		self._value.setObjectName("contextChipValue")
		layout.addWidget(self._value)

	def set_value(self, value: str) -> None:
		self._value.setText(value)

	def clear(self) -> None:
		self._value.setText("--")


class SessionDashboard(QWidget):
	"""
	Main charging session dashboard widget.

	Combines all session-related UI components into a single dashboard:
	- Primary metrics (energy, power, duration, SoC)
	- Real-time telemetry chart
	- Charging progress bar
	- Context chips (transaction ID, voltage, current, meter, phases)
	- ID tag input
	- Action buttons (Plug/Unplug/Charge/Suspend)

	Signals:
		plug_in_clicked: Emitted when plug in button is clicked.
		unplug_clicked: Emitted when unplug button is clicked.
		start_charging_clicked: Emitted when start charging is clicked.
		stop_charging_clicked: Emitted when stop charging is clicked.
		apply_id_tag_clicked: Emitted when ID tag is applied.

	Example:
		>>> dashboard = SessionDashboard()
		>>> dashboard.start_charging_clicked.connect(engine.start_session)
		>>> dashboard.update_from_engine(engine)  # Update display
	"""

	plug_in_clicked = Signal()
	unplug_clicked = Signal()
	start_charging_clicked = Signal()
	stop_charging_clicked = Signal()
	suspend_ev_clicked = Signal()
	resume_charging_clicked = Signal()
	apply_id_tag_clicked = Signal(str)

	def __init__(self, parent: Optional[QWidget] = None) -> None:
		"""
		Initialize the session dashboard.

		Args:
			parent: Optional parent widget.
		"""
		super().__init__(parent)
		self._selected_connector_id: int = 1
		self._setup_ui()

	def _setup_ui(self) -> None:
		main_layout = QHBoxLayout(self)
		main_layout.setSpacing(0)
		main_layout.setContentsMargins(0, 0, 0, 0)

		# ── Left: Controls panel ─────────────────────────────────────────────
		controls_panel = QWidget()
		controls_panel.setObjectName("dashControlsPanel")
		controls_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		controls_panel.setMinimumWidth(180)
		controls_panel.setMaximumWidth(280)
		controls_layout = QVBoxLayout(controls_panel)
		controls_layout.setContentsMargins(12, 12, 12, 12)
		controls_layout.setSpacing(12)

		# Session state badge
		self._state_badge = QFrame()
		self._state_badge.setObjectName("sessionStateBadge")
		self._state_badge.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		self._state_badge.setProperty("state", "idle")
		badge_layout = QHBoxLayout(self._state_badge)
		badge_layout.setContentsMargins(8, 6, 8, 6)
		badge_layout.setSpacing(6)
		self._state_name = QLabel("Idle")
		self._state_name.setObjectName("sessionStateName")
		self._state_sub = QLabel("Connector 1")
		self._state_sub.setObjectName("sessionStateSub")
		badge_layout.addWidget(self._state_name)
		badge_layout.addStretch()
		badge_layout.addWidget(self._state_sub)
		controls_layout.addWidget(self._state_badge)

		# Actions section
		actions_label = QLabel("ACTIONS")
		actions_label.setObjectName("dashSectionLabel")
		controls_layout.addWidget(actions_label)

		self.btn_plug = QPushButton("Plug In")
		self.btn_plug.setObjectName("btnPlug")
		self.btn_plug.setProperty("primary", True)
		self.btn_plug.setMinimumHeight(36)
		self.btn_plug.clicked.connect(self.plug_in_clicked)
		controls_layout.addWidget(self.btn_plug)

		self.btn_start_charge = QPushButton("Start Charging")
		self.btn_start_charge.setObjectName("btnStartCharge")
		self.btn_start_charge.setProperty("success", True)
		self.btn_start_charge.setMinimumHeight(36)
		self.btn_start_charge.clicked.connect(self.start_charging_clicked)
		controls_layout.addWidget(self.btn_start_charge)

		stop_unplug_row = QHBoxLayout()
		stop_unplug_row.setSpacing(6)
		self.btn_stop_charge = QPushButton("Stop")
		self.btn_stop_charge.setObjectName("btnStopCharge")
		self.btn_stop_charge.setProperty("warning", True)
		self.btn_stop_charge.setMinimumHeight(36)
		self.btn_stop_charge.clicked.connect(self.stop_charging_clicked)
		stop_unplug_row.addWidget(self.btn_stop_charge)
		self.btn_unplug = QPushButton("Unplug")
		self.btn_unplug.setObjectName("btnUnplug")
		self.btn_unplug.setProperty("danger", True)
		self.btn_unplug.setMinimumHeight(36)
		self.btn_unplug.clicked.connect(self.unplug_clicked)
		stop_unplug_row.addWidget(self.btn_unplug)
		controls_layout.addLayout(stop_unplug_row)

		self.btn_suspend_ev = QPushButton("Suspend EV")
		self.btn_suspend_ev.setObjectName("btnSuspendEV")
		self.btn_suspend_ev.setMinimumHeight(36)
		self.btn_suspend_ev.clicked.connect(self._on_suspend_ev_clicked)
		controls_layout.addWidget(self.btn_suspend_ev)

		# ID tag section
		id_label = QLabel("ID TAG")
		id_label.setObjectName("dashSectionLabel")
		controls_layout.addWidget(id_label)

		self.id_tag_input = IdTagInput()
		self.id_tag_input.tag_applied.connect(self._on_apply_id_tag)
		controls_layout.addWidget(self.id_tag_input)

		# Effective limit
		limit_row = QHBoxLayout()
		limit_lbl = QLabel("Effective Limit")
		limit_lbl.setObjectName("dashLimitLabel")
		limit_row.addWidget(limit_lbl)
		limit_row.addStretch()
		self._context_limit_value = QLabel("No limit")
		self._context_limit_value.setObjectName("contextLimitValue")
		limit_row.addWidget(self._context_limit_value)
		controls_layout.addLayout(limit_row)

		controls_layout.addStretch()
		main_layout.addWidget(controls_panel)

		# Vertical separator
		sep = QFrame()
		sep.setFrameShape(QFrame.Shape.VLine)
		sep.setObjectName("dashVertSep")
		main_layout.addWidget(sep)

		# ── Right: Data panel ────────────────────────────────────────────────
		data_panel = QWidget()
		data_panel.setObjectName("dashDataPanel")
		data_layout = QVBoxLayout(data_panel)
		data_layout.setContentsMargins(12, 12, 12, 12)
		data_layout.setSpacing(10)

		# Metric row (4 cards)
		metric_row = QHBoxLayout()
		metric_row.setSpacing(8)
		self.metric_power = MetricCard("Power", "kW")
		self.metric_soc = MetricCard("State of Charge", "%")
		self.metric_duration = MetricCard("Duration")
		self.metric_energy = MetricCard("Energy Charged", "Wh")
		for card in (self.metric_power, self.metric_soc, self.metric_duration, self.metric_energy):
			metric_row.addWidget(card)
		data_layout.addLayout(metric_row)

		# Telemetry chart (fills remaining vertical space)
		telemetry_panel = QFrame()
		telemetry_panel.setObjectName("telemetryPanel")
		telemetry_panel.setProperty("card", True)
		telemetry_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		telemetry_layout = QVBoxLayout(telemetry_panel)
		telemetry_layout.setContentsMargins(12, 8, 12, 8)
		telemetry_layout.setSpacing(4)
		telemetry_title = QLabel("Live Power Telemetry — 60 s rolling")
		telemetry_title.setObjectName("telemetryTitle")
		telemetry_layout.addWidget(telemetry_title)
		self.telemetry_chart = TelemetryChart()
		telemetry_layout.addWidget(self.telemetry_chart, 1)
		data_layout.addWidget(telemetry_panel, 1)

		# Charging progress row
		progress_row = QHBoxLayout()
		progress_row.setSpacing(8)
		progress_lbl = QLabel("Charging progress")
		progress_lbl.setObjectName("socTitle")
		progress_row.addWidget(progress_lbl)
		self.soc_progress = QProgressBar()
		self.soc_progress.setMinimumHeight(6)
		self.soc_progress.setMaximumHeight(6)
		self.soc_progress.setTextVisible(False)
		self.soc_progress.setValue(0)
		progress_row.addWidget(self.soc_progress, 1)
		self._soc_percent_label = QLabel("0%")
		self._soc_percent_label.setObjectName("socPercent")
		progress_row.addWidget(self._soc_percent_label)
		data_layout.addLayout(progress_row)

		# Context rail (5 chips)
		context_row = QHBoxLayout()
		context_row.setSpacing(6)
		self.chip_tx_id = ContextChip("Transaction")
		self.chip_voltage = ContextChip("Voltage")
		self.chip_current = ContextChip("Current")
		self.chip_meter = ContextChip("Total Meter")
		self.chip_phases = ContextChip("Phases")
		for chip in (
			self.chip_tx_id,
			self.chip_voltage,
			self.chip_current,
			self.chip_meter,
			self.chip_phases,
		):
			context_row.addWidget(chip)
		data_layout.addLayout(context_row)

		main_layout.addWidget(data_panel, 1)

	def _format_duration(self, start_time: float) -> str:
		duration = time.time() - start_time
		total_secs = int(duration)
		hours = total_secs // 3600
		minutes = (total_secs % 3600) // 60
		seconds = total_secs % 60
		if hours > 0:
			return f"{hours}:{minutes:02d}:{seconds:02d}"
		return f"{minutes}:{seconds:02d}"

	def _on_apply_id_tag(self, tag: str) -> None:
		"""
		Handle ID tag application.

		Args:
			tag: The applied tag string.
		"""
		self.apply_id_tag_clicked.emit(tag)

	def get_selected_connector_id(self) -> int:
		"""
		Get the currently selected connector ID.

		Returns:
			The selected connector ID.
		"""
		return self._selected_connector_id

	def set_selected_connector(self, connector_id: int) -> None:
		"""
		Set the selected connector.

		Args:
			connector_id: The connector ID to select.
		"""
		if self._selected_connector_id != connector_id:
			self.telemetry_chart.clear()
		self._selected_connector_id = connector_id

	def set_recent_tags(self, tags: list[str]) -> None:
		"""
		Set the list of recent ID tags.

		Args:
			tags: List of recent tag strings.
		"""
		self.id_tag_input.set_recent_tags(tags)

	def record_telemetry(self, engine: "Engine") -> None:
		"""Record a telemetry data point. Called every simulation tick."""
		power_kw = _compute_effective_power_kw(engine, self._selected_connector_id)
		self.telemetry_chart.add_point(power_kw)

	def update_from_engine(self, engine: "Engine") -> None:
		"""
		Update the dashboard display from the engine state.

		Refreshes all metrics, chart, and button states based on
		the current engine and session state.

		Args:
			engine: The Engine instance to read state from.
		"""
		conn = engine.get_connector(self._selected_connector_id)
		if not conn:
			return

		# Button states
		self.btn_plug.setEnabled(not conn.is_plugged_in)
		self.btn_unplug.setEnabled(conn.is_plugged_in)
		self.id_tag_input.set_applied_tag(conn.id_tag)

		power_kw = _compute_effective_power_kw(engine, self._selected_connector_id)
		self.metric_power.set_value(f"{power_kw:.2f}")

		session = engine.session
		if session and session.connector_id == self._selected_connector_id:
			self.metric_energy.set_value(f"{session.energy_charged:.1f}")
			self.metric_soc.set_value(f"{session.state_of_charge:.1f}")
			duration_str = self._format_duration(session.start_time)
			self.metric_duration.set_value(duration_str)
			self.soc_progress.setValue(int(session.state_of_charge))
			self._soc_percent_label.setText(f"{session.state_of_charge:.0f}%")
			self.btn_start_charge.setEnabled(False)
			self.btn_stop_charge.setEnabled(True)

			state_name = conn.status.value
			self._state_name.setText(state_name)
			self._state_badge.setProperty("state", "charging")

			if conn.status == ConnectorState.SUSPENDED_EV:
				self.btn_suspend_ev.setText("Resume Charging")
				self.btn_suspend_ev.setEnabled(True)
			elif conn.status == ConnectorState.CHARGING:
				self.btn_suspend_ev.setText("Suspend EV")
				self.btn_suspend_ev.setEnabled(True)
			else:
				self.btn_suspend_ev.setText("Suspend EV")
				self.btn_suspend_ev.setEnabled(False)
		else:
			self.metric_energy.clear()
			self.metric_soc.clear()
			self.metric_duration.clear()
			self.soc_progress.setValue(0)
			self._soc_percent_label.setText("0%")
			self.btn_start_charge.setEnabled(conn.is_plugged_in)
			self.btn_stop_charge.setEnabled(False)
			self.btn_suspend_ev.setText("Suspend EV")
			self.btn_suspend_ev.setEnabled(False)

			if conn.is_plugged_in:
				self._state_name.setText("Plugged")
				self._state_badge.setProperty("state", "plugged")
			else:
				self._state_name.setText("Idle")
				self._state_badge.setProperty("state", "idle")

		self._state_sub.setText(f"Connector {self._selected_connector_id}")
		self._state_badge.style().unpolish(self._state_badge)
		self._state_badge.style().polish(self._state_badge)

		# Context chips
		selected_tx_id = (
			session.transaction_id
			if session and session.connector_id == self._selected_connector_id
			else None
		)
		self.chip_tx_id.set_value(f"#{selected_tx_id}" if selected_tx_id else "--")
		self.chip_voltage.set_value(f"{conn.voltage:.0f} V")
		self.chip_current.set_value(f"{conn.current:.0f} A")
		self.chip_meter.set_value(f"{engine.energy_meter.get_meter_reading():.1f} Wh")
		self.chip_phases.set_value(f"{conn.phase}Φ")

		# Effective limit display
		effective_limit: Optional[float] = None
		if session and session.connector_id == self._selected_connector_id:
			if engine.get_limit is not None:
				effective_limit = engine.get_limit(session.connector_id, session.transaction_id)
		if effective_limit is None or effective_limit < 0:
			self._context_limit_value.setText("No limit")
			self._context_limit_value.setProperty("limited", False)
		else:
			self._context_limit_value.setText(f"{effective_limit:.1f} A")
			self._context_limit_value.setProperty("limited", effective_limit < conn.current)
		self._context_limit_value.style().unpolish(self._context_limit_value)
		self._context_limit_value.style().polish(self._context_limit_value)

	def _on_suspend_ev_clicked(self) -> None:
		"""
		Handle suspend/resume toggle button click.

		Emits the appropriate signal based on the current button label.
		"""
		if self.btn_suspend_ev.text() == "Resume Charging":
			self.resume_charging_clicked.emit()
		else:
			self.suspend_ev_clicked.emit()

	def set_id_tag(self, tag: str) -> None:
		"""
		Set the ID tag in the input field.

		Args:
			tag: The tag string to set.
		"""
		self.id_tag_input.set_tag(tag)
