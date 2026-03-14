"""
Session Dashboard Widget Module.

This module provides the main charging session dashboard for the ChargeGhost
EVSE simulator. It includes real-time telemetry visualization, session metrics,
connector selection, and charging controls.

Classes:
    TelemetryChart: Real-time power telemetry line chart.
    MetricCard: Display card for a single metric value.
    CollapsibleDetails: Expandable details panel with additional metrics.
    IdTagInput: ID tag input field with recent tags dropdown.
    SessionDashboard: Main dashboard widget combining all components.

Example:
    >>> from chargeghost_evse.ui.widgets.session_dashboard import SessionDashboard
    >>> 
    >>> dashboard = SessionDashboard()
    >>> dashboard.connector_selected.connect(self._on_connector_selected)
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
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chargeghost_evse.ui.styles import colors
from chargeghost_evse.ui.widgets.connector_strip import ConnectorStrip

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


class CollapsibleDetails(QWidget):
    """
    Expandable details panel with additional session metrics.

    Provides a toggle button to show/hide detailed metrics like
    transaction ID, voltage, current, and meter reading.

    Signals:
        toggled: Emitted when expanded/collapsed.
            Parameters: is_expanded (bool)

    Attributes:
        metric_tx_id: Transaction ID metric card.
        metric_voltage: Voltage metric card.
        metric_current: Current metric card.
        metric_meter: Total meter metric card.
    """

    toggled = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the collapsible details panel.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._is_expanded = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """
        Build the UI with toggle button and metric cards.
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._toggle_btn = QPushButton("Show Details")
        self._toggle_btn.setObjectName("toggleDetailsBtn")
        self._toggle_btn.setProperty("flat", True)
        self._toggle_btn.clicked.connect(self._toggle)
        layout.addWidget(self._toggle_btn)

        # Content container (initially hidden)
        self._content = QWidget()
        self._content.setObjectName("detailsContent")
        content_layout = QGridLayout(self._content)
        content_layout.setSpacing(12)
        content_layout.setContentsMargins(8, 8, 8, 8)

        # Metric cards in 2x2 grid
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
        """
        Toggle the expanded state.
        """
        self._is_expanded = not self._is_expanded
        self._toggle_btn.setText(
            "Hide Details" if self._is_expanded else "Show Details"
        )
        if self._is_expanded:
            self._content.show()
        else:
            self._content.hide()
        self.toggled.emit(self._is_expanded)

    def is_expanded(self) -> bool:
        """
        Check if the details panel is expanded.

        Returns:
            True if expanded, False if collapsed.
        """
        return self._is_expanded

    def update_metrics(
        self,
        tx_id: Optional[int],
        voltage: float,
        current: float,
        meter: float,
    ) -> None:
        """
        Update all metric values.

        Args:
            tx_id: Transaction ID, or None if no active transaction.
            voltage: Voltage in volts.
            current: Current in amperes.
            meter: Meter reading in Watt-hours.
        """
        self.metric_tx_id.set_value(str(tx_id) if tx_id else "--")
        self.metric_voltage.set_value(f"{voltage:.1f}")
        self.metric_current.set_value(f"{current:.1f}")
        self.metric_meter.set_value(f"{meter:.1f}")

    def clear(self) -> None:
        """
        Clear all metric values.
        """
        for metric in [
            self.metric_tx_id,
            self.metric_voltage,
            self.metric_current,
            self.metric_meter,
        ]:
            metric.clear()


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


class SessionDashboard(QWidget):
    """
    Main charging session dashboard widget.

    Combines all session-related UI components into a single dashboard:
    - Connector strip for selection
    - Primary metrics (energy, power, duration, SoC)
    - Real-time telemetry chart
    - Charging progress bar
    - Collapsible details panel
    - ID tag input
    - Action buttons (Plug/Unplug/Charge)

    Signals:
        connector_selected: Emitted when a connector is selected.
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

    connector_selected = Signal(int)
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
        """
        Build the complete dashboard UI with a status-first layout.
        """
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(16, 16, 16, 16)

        self.connector_strip = ConnectorStrip()
        self.connector_strip.connector_selected.connect(self._on_connector_selected)
        main_layout.addWidget(self.connector_strip)

        self._hero_frame = QFrame()
        self._hero_frame.setObjectName("sessionHero")
        self._hero_frame.setProperty("card", True)
        self._hero_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        hero_layout = QVBoxLayout(self._hero_frame)
        hero_layout.setSpacing(12)
        hero_layout.setContentsMargins(16, 16, 16, 16)

        hero_header = QHBoxLayout()
        hero_header.setSpacing(12)

        hero_identity = QVBoxLayout()
        hero_identity.setSpacing(4)

        hero_title = QLabel("Active Session")
        hero_title.setObjectName("sectionHeader")
        hero_identity.addWidget(hero_title)

        self._hero_connector_value = QLabel("Connector 1")
        self._hero_connector_value.setObjectName("heroConnectorValue")
        hero_identity.addWidget(self._hero_connector_value)

        self._hero_state_value = QLabel("Idle")
        self._hero_state_value.setObjectName("heroStateValue")
        hero_identity.addWidget(self._hero_state_value)

        hero_header.addLayout(hero_identity)
        hero_header.addStretch()
        hero_layout.addLayout(hero_header)

        self._hero_metrics_frame = QFrame()
        self._hero_metrics_frame.setObjectName("sessionHeroMetrics")
        hero_metrics_layout = QGridLayout(self._hero_metrics_frame)
        hero_metrics_layout.setContentsMargins(0, 0, 0, 0)
        hero_metrics_layout.setHorizontalSpacing(12)
        hero_metrics_layout.setVerticalSpacing(8)

        self._hero_power_value = QLabel("0.00 kW")
        self._hero_power_value.setObjectName("heroPrimaryValue")
        self._hero_soc_value = QLabel("0.0%")
        self._hero_soc_value.setObjectName("heroPrimaryValue")
        self._hero_duration_value = QLabel("--")
        self._hero_duration_value.setObjectName("heroPrimaryValue")

        hero_metrics_layout.addWidget(QLabel("Power"), 0, 0)
        hero_metrics_layout.addWidget(QLabel("State of Charge"), 0, 1)
        hero_metrics_layout.addWidget(QLabel("Duration"), 0, 2)
        hero_metrics_layout.addWidget(self._hero_power_value, 1, 0)
        hero_metrics_layout.addWidget(self._hero_soc_value, 1, 1)
        hero_metrics_layout.addWidget(self._hero_duration_value, 1, 2)
        hero_layout.addWidget(self._hero_metrics_frame)

        self._hero_actions_frame = QFrame()
        self._hero_actions_frame.setObjectName("sessionHeroActions")
        hero_actions_layout = QGridLayout(self._hero_actions_frame)
        hero_actions_layout.setContentsMargins(0, 0, 0, 0)
        hero_actions_layout.setSpacing(8)

        self.btn_plug = QPushButton("Plug In")
        self.btn_plug.setObjectName("btnPlug")
        self.btn_plug.setProperty("primary", True)
        self.btn_plug.setMinimumHeight(40)
        self.btn_plug.clicked.connect(self.plug_in_clicked)
        hero_actions_layout.addWidget(self.btn_plug, 0, 0)

        self.btn_unplug = QPushButton("Unplug")
        self.btn_unplug.setObjectName("btnUnplug")
        self.btn_unplug.setProperty("danger", True)
        self.btn_unplug.setMinimumHeight(40)
        self.btn_unplug.clicked.connect(self.unplug_clicked)
        hero_actions_layout.addWidget(self.btn_unplug, 0, 1)

        self.btn_start_charge = QPushButton("Start Charging")
        self.btn_start_charge.setObjectName("btnStartCharge")
        self.btn_start_charge.setProperty("success", True)
        self.btn_start_charge.setMinimumHeight(40)
        self.btn_start_charge.clicked.connect(self.start_charging_clicked)
        hero_actions_layout.addWidget(self.btn_start_charge, 1, 0)

        self.btn_stop_charge = QPushButton("Stop Charging")
        self.btn_stop_charge.setObjectName("btnStopCharge")
        self.btn_stop_charge.setProperty("danger", True)
        self.btn_stop_charge.setMinimumHeight(40)
        self.btn_stop_charge.clicked.connect(self.stop_charging_clicked)
        hero_actions_layout.addWidget(self.btn_stop_charge, 1, 1)

        self.btn_suspend_ev = QPushButton("Suspend EV")
        self.btn_suspend_ev.setObjectName("btnSuspendEV")
        self.btn_suspend_ev.setMinimumHeight(40)
        self.btn_suspend_ev.clicked.connect(self._on_suspend_ev_clicked)
        hero_actions_layout.addWidget(self.btn_suspend_ev, 2, 0, 1, 2)

        hero_layout.addWidget(self._hero_actions_frame)

        self._hero_context_frame = QFrame()
        self._hero_context_frame.setObjectName("sessionHeroContext")
        hero_context_layout = QHBoxLayout(self._hero_context_frame)
        hero_context_layout.setContentsMargins(0, 0, 0, 0)
        hero_context_layout.setSpacing(12)

        self.id_tag_input = IdTagInput()
        self.id_tag_input.tag_applied.connect(self._on_apply_id_tag)
        hero_context_layout.addWidget(self.id_tag_input, 1)

        limit_summary = QFrame()
        limit_summary.setObjectName("heroLimitSummary")
        limit_layout = QVBoxLayout(limit_summary)
        limit_layout.setContentsMargins(12, 8, 12, 8)
        limit_layout.setSpacing(2)

        limit_title = QLabel("Effective Limit")
        limit_title.setObjectName("idTagLabel")
        limit_layout.addWidget(limit_title)

        self._context_limit_value = QLabel("No limit")
        self._context_limit_value.setObjectName("contextLimitValue")
        limit_layout.addWidget(self._context_limit_value)

        hero_context_layout.addWidget(limit_summary)
        hero_layout.addWidget(self._hero_context_frame)
        main_layout.addWidget(self._hero_frame)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)
        main_layout.addLayout(content_layout, 1)

        left_panel = QVBoxLayout()
        left_panel.setSpacing(16)
        content_layout.addLayout(left_panel, 7)

        telemetry_panel = QFrame()
        telemetry_panel.setObjectName("telemetryPanel")
        telemetry_panel.setProperty("card", True)
        telemetry_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        telemetry_layout = QVBoxLayout(telemetry_panel)
        telemetry_layout.setContentsMargins(12, 12, 12, 12)
        telemetry_layout.setSpacing(8)

        telemetry_title = QLabel("Live Power Telemetry")
        telemetry_title.setObjectName("telemetryTitle")
        telemetry_layout.addWidget(telemetry_title)

        telemetry_subtitle = QLabel("Rolling 60-second delivered power view")
        telemetry_subtitle.setObjectName("telemetrySubtitle")
        telemetry_layout.addWidget(telemetry_subtitle)

        self.telemetry_chart = TelemetryChart()
        telemetry_layout.addWidget(self.telemetry_chart, 1)
        left_panel.addWidget(telemetry_panel, 1)

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
        self.soc_progress.setMinimumHeight(12)
        self.soc_progress.setTextVisible(False)
        self.soc_progress.setValue(0)
        soc_layout.addWidget(self.soc_progress)
        left_panel.addWidget(soc_section)

        right_panel = QVBoxLayout()
        right_panel.setSpacing(16)
        content_layout.addLayout(right_panel, 3)

        primary_metrics = QGridLayout()
        primary_metrics.setSpacing(8)
        primary_metrics.setContentsMargins(0, 0, 0, 0)

        self.metric_energy = MetricCard("Energy Charged", "Wh")
        self.metric_power = MetricCard("Current Power", "kW")
        self.metric_duration = MetricCard("Duration")
        self.metric_soc = MetricCard("State of Charge", "%")

        primary_metrics.addWidget(self.metric_energy, 0, 0)
        primary_metrics.addWidget(self.metric_power, 0, 1)
        primary_metrics.addWidget(self.metric_duration, 1, 0)
        primary_metrics.addWidget(self.metric_soc, 1, 1)
        right_panel.addLayout(primary_metrics)

        right_panel.addStretch()

        self._context_rail = QFrame()
        self._context_rail.setObjectName("sessionContextRail")
        self._context_rail.setProperty("card", True)
        self._context_rail.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        context_layout = QGridLayout(self._context_rail)
        context_layout.setContentsMargins(12, 12, 12, 12)
        context_layout.setSpacing(8)

        self.metric_tx_id = MetricCard("Transaction ID")
        self.metric_tx_id.setObjectName("contextMetricTx")
        context_layout.addWidget(self.metric_tx_id, 0, 0)

        self.metric_voltage = MetricCard("Voltage", "V")
        self.metric_voltage.setObjectName("contextMetricVoltage")
        context_layout.addWidget(self.metric_voltage, 0, 1)

        self.metric_current = MetricCard("Current", "A")
        self.metric_current.setObjectName("contextMetricCurrent")
        context_layout.addWidget(self.metric_current, 0, 2)

        self.metric_meter = MetricCard("Total Meter", "Wh")
        self.metric_meter.setObjectName("contextMetricMeter")
        context_layout.addWidget(self.metric_meter, 0, 3)

        main_layout.addWidget(self._context_rail)

    def _format_duration(self, start_time: float) -> str:
        duration = time.time() - start_time
        total_secs = int(duration)
        hours = total_secs // 3600
        minutes = (total_secs % 3600) // 60
        seconds = total_secs % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def _on_connector_selected(self, connector_id: int) -> None:
        """
        Handle connector selection from the strip.

        Args:
            connector_id: The selected connector ID.
        """
        self._selected_connector_id = connector_id
        self.connector_selected.emit(connector_id)

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
        self.connector_strip.set_selected_connector(connector_id)

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
        self.connector_strip.update_connectors(engine)

        conn = engine.get_connector(self._selected_connector_id)
        if not conn:
            return

        # Update button states based on plug status
        self.btn_plug.setEnabled(not conn.is_plugged_in)
        self.btn_unplug.setEnabled(conn.is_plugged_in)

        # Update ID tag placeholder
        self.id_tag_input.set_applied_tag(conn.id_tag)

        power_kw = _compute_effective_power_kw(engine, self._selected_connector_id)
        self.metric_power.set_value(f"{power_kw:.2f}")
        self._hero_connector_value.setText(f"Connector {self._selected_connector_id}")
        self._hero_power_value.setText(f"{power_kw:.2f} kW")

        # Update session-specific metrics if active
        session = engine.session
        if session and session.connector_id == self._selected_connector_id:
            self.metric_energy.set_value(f"{session.energy_charged:.1f}")
            self.metric_soc.set_value(f"{session.state_of_charge:.1f}")
            duration_str = self._format_duration(session.start_time)
            self.metric_duration.set_value(duration_str)
            self.soc_progress.setValue(int(session.state_of_charge))
            self._soc_percent_label.setText(f"{session.state_of_charge:.0f}%")
            self._hero_state_value.setText(conn.status.value)
            self._hero_soc_value.setText(f"{session.state_of_charge:.1f}%")
            self._hero_duration_value.setText(duration_str)
            self._hero_frame.setProperty("sessionState", "charging")

            self.btn_start_charge.setEnabled(False)
            self.btn_stop_charge.setEnabled(True)

            # Suspend/Resume toggle
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
            # No active session - clear metrics
            self.metric_energy.clear()
            self.metric_soc.clear()
            self.metric_duration.clear()
            self.soc_progress.setValue(0)
            self._soc_percent_label.setText("0%")
            idle_state = "plugged" if conn.is_plugged_in else "idle"
            self._hero_state_value.setText("Plugged In" if conn.is_plugged_in else "Idle")
            self._hero_soc_value.setText("0.0%")
            self._hero_duration_value.setText("--")
            self._hero_frame.setProperty("sessionState", idle_state)

            self.btn_start_charge.setEnabled(conn.is_plugged_in)
            self.btn_stop_charge.setEnabled(False)
            self.btn_suspend_ev.setText("Suspend EV")
            self.btn_suspend_ev.setEnabled(False)

        selected_tx_id = (
            session.transaction_id
            if session and session.connector_id == self._selected_connector_id
            else None
        )
        effective_limit: Optional[float] = None
        if session and session.connector_id == self._selected_connector_id:
            if engine.get_limit is not None:
                effective_limit = engine.get_limit(
                    session.connector_id, session.transaction_id
                )
        self.metric_tx_id.set_value(str(selected_tx_id) if selected_tx_id else "--")
        self.metric_voltage.set_value(f"{conn.voltage:.1f}")
        self.metric_current.set_value(f"{conn.current:.1f}")
        self.metric_meter.set_value(f"{engine.energy_meter.get_meter_reading():.1f}")
        if effective_limit is None or effective_limit < 0:
            self._context_limit_value.setText("No limit")
            self._context_limit_value.setProperty("limited", False)
        else:
            self._context_limit_value.setText(f"{effective_limit:.1f}A")
            self._context_limit_value.setProperty("limited", effective_limit < conn.current)
        self._hero_frame.style().unpolish(self._hero_frame)
        self._hero_frame.style().polish(self._hero_frame)
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
