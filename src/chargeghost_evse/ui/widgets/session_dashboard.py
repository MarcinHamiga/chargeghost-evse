import time
from collections import deque
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

if TYPE_CHECKING:
    from chargeghost_evse.engine.engine import Engine


class TelemetryChart(QFrame):
    # Must match the QTimer interval in app.py (100 ms → 10 Hz).
    # Used to derive _max_points and to debounce Y-axis downscaling.
    _SAMPLE_RATE_HZ: int = 10

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("telemetryChartFrame")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(200)

        self._window_seconds = 60.0
        # Safety cap: 2× the expected points per window so the deque never
        # silently drops samples when the timer fires slightly faster.
        _max_points = int(self._window_seconds * self._SAMPLE_RATE_HZ) * 2
        self._data: deque[QPointF] = deque(maxlen=_max_points)
        self._session_start: float = time.monotonic()
        self._running_max: float = 0.0
        # Ticks since the last full Y-axis downscale recalculation.
        self._downscale_counter: int = 0

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.chart = QChart()
        self.chart.setBackgroundVisible(False)
        self.chart.layout().setContentsMargins(0, 0, 0, 0)
        self.chart.legend().hide()

        self.series_power = QLineSeries()
        power_pen = QPen(QColor(colors.ACCENT_TEAL))
        power_pen.setWidth(2)
        self.series_power.setPen(power_pen)
        self.chart.addSeries(self.series_power)

        self.axis_x = QValueAxis()
        self.axis_x.setRange(0, self._window_seconds)
        self.axis_x.setLabelFormat("%.0f s")
        self.axis_x.setTitleText("Session time (s)")
        self.axis_x.setGridLineVisible(True)
        self.axis_x.setGridLineColor(QColor(colors.BORDER_DEFAULT))
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.series_power.attachAxis(self.axis_x)

        self.axis_y = QValueAxis()
        self.axis_y.setRange(0, 25)
        self.axis_y.setLabelFormat("%.1f kW")
        self.axis_y.setTitleText("Power (kW)")
        self.axis_y.setGridLineVisible(True)
        self.axis_y.setGridLineColor(QColor(colors.BORDER_DEFAULT))
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)
        self.series_power.attachAxis(self.axis_y)

        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setBackgroundRole(self.backgroundRole())
        layout.addWidget(self.chart_view)

    def record_point(self, power_kw: float) -> None:
        """Append a sample to the internal buffer. Does not touch Qt series."""
        elapsed = time.monotonic() - self._session_start
        self._data.append(QPointF(elapsed, power_kw))
        if power_kw > self._running_max:
            self._running_max = power_kw

    def refresh(self) -> None:
        """Sync buffered data to the visible chart. Call only from the main thread."""
        if not self._data:
            return

        latest_t = self._data[-1].x()
        x_min = max(0.0, latest_t - self._window_seconds)
        # Always show at least one full window width so early data isn't squashed.
        x_max = max(latest_t, self._window_seconds)

        # Build the visible slice without mutating the deque.
        visible: list[QPointF] = [p for p in self._data if p.x() >= x_min]
        self.series_power.replace(visible)
        self.axis_x.setRange(x_min, x_max)
        self._update_y_axis(self._data[-1].y(), x_min)

    def _update_y_axis(self, latest_power: float, x_min: float) -> None:
        # Upscale immediately when a new peak arrives.
        if latest_power > self.axis_y.max():
            self.axis_y.setRange(0, latest_power * 1.2)
            return

        # Downscale is expensive (O(n) scan) — only recalculate every ~5 s.
        self._downscale_counter += 1
        if self._downscale_counter < self._SAMPLE_RATE_HZ * 5:
            return
        self._downscale_counter = 0

        visible_max = max((p.y() for p in self._data if p.x() >= x_min), default=0.0)
        self._running_max = visible_max
        ceiling = self.axis_y.max()
        if visible_max < ceiling * 0.6 and ceiling > 25.0:
            self.axis_y.setRange(0, max(25.0, visible_max * 1.5))
        elif ceiling < 25.0:
            self.axis_y.setRange(0, 25.0)

    def clear(self) -> None:
        self._data.clear()
        self._session_start = time.monotonic()
        self._running_max = 0.0
        self._downscale_counter = 0
        self.series_power.clear()
        self.axis_x.setRange(0, self._window_seconds)
        self.axis_y.setRange(0, 25)


class MetricCard(QFrame):
    def __init__(self, title: str, unit: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setProperty("card", True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(12, 8, 12, 8)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("metricTitle")
        layout.addWidget(self._title_label)

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

        self._toggle_btn = QPushButton("Show Details")
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
        self._toggle_btn.setText(
            "Hide Details" if self._is_expanded else "Show Details"
        )
        if self._is_expanded:
            self._content.show()
        else:
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
        for metric in [
            self.metric_tx_id,
            self.metric_voltage,
            self.metric_current,
            self.metric_meter,
        ]:
            metric.clear()


class IdTagInput(QWidget):
    tag_applied = Signal(str)
    recent_tags_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._recent_tags: list[str] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        id_tag_label = QLabel("ID Tag")
        id_tag_label.setObjectName("idTagLabel")
        layout.addWidget(id_tag_label)

        self._recent_combo = QComboBox()
        self._recent_combo.setObjectName("recentTagsCombo")
        self._recent_combo.setPlaceholderText("Recent tags...")
        self._recent_combo.setMinimumWidth(100)
        self._recent_combo.currentTextChanged.connect(self._on_recent_selected)
        self._recent_combo.hide()
        layout.addWidget(self._recent_combo)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Enter RFID tag (e.g., RFID-001)")
        self._input.returnPressed.connect(self._on_apply)
        layout.addWidget(self._input, 1)

        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setObjectName("btnApplyTag")
        self._apply_btn.clicked.connect(self._on_apply)
        layout.addWidget(self._apply_btn)

    def _on_recent_selected(self, tag: str) -> None:
        if tag:
            self._input.setText(tag)

    def _on_apply(self) -> None:
        tag = self._input.text().strip()
        if tag:
            self.tag_applied.emit(tag)

    def set_recent_tags(self, tags: list[str]) -> None:
        self._recent_tags = tags[:10]
        self._recent_combo.clear()
        if self._recent_tags:
            self._recent_combo.addItems(self._recent_tags)
            self._recent_combo.show()
        else:
            self._recent_combo.hide()

    def get_tag(self) -> str:
        return self._input.text().strip()

    def set_tag(self, tag: str) -> None:
        self._input.setText(tag)


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
        primary_metrics.setSpacing(8)
        primary_metrics.setContentsMargins(0, 0, 0, 0)

        self.metric_energy = MetricCard("Energy Charged", "Wh")
        self.metric_power = MetricCard("Current Power", "kW")
        self.metric_duration = MetricCard("Duration")
        self.metric_soc = MetricCard("State of Charge", "%")

        primary_metrics.addWidget(self.metric_energy, 0, 0)
        primary_metrics.addWidget(self.metric_power, 0, 1)
        primary_metrics.addWidget(self.metric_duration, 0, 2)
        primary_metrics.addWidget(self.metric_soc, 0, 3)
        layout.addLayout(primary_metrics)

        self.telemetry_chart = TelemetryChart()
        layout.addWidget(self.telemetry_chart, 1)

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

        layout.addWidget(soc_section)

        self.details = CollapsibleDetails()
        layout.addWidget(self.details)

        id_tag_section = QFrame()
        id_tag_section.setObjectName("idTagSection")
        id_tag_layout = QHBoxLayout(id_tag_section)
        id_tag_layout.setContentsMargins(12, 8, 12, 8)
        id_tag_layout.setSpacing(12)

        self.id_tag_input = IdTagInput()
        self.id_tag_input.tag_applied.connect(self._on_apply_id_tag)
        id_tag_layout.addWidget(self.id_tag_input)

        layout.addWidget(id_tag_section)

        actions = QHBoxLayout()
        actions.setSpacing(12)

        self.btn_plug = QPushButton("Plug In")
        self.btn_plug.setObjectName("btnPlug")
        self.btn_plug.setProperty("primary", True)
        self.btn_plug.setMinimumHeight(48)
        self.btn_plug.clicked.connect(self.plug_in_clicked)
        actions.addWidget(self.btn_plug, 1)

        self.btn_start_charge = QPushButton("Start Charging")
        self.btn_start_charge.setObjectName("btnStartCharge")
        self.btn_start_charge.setProperty("success", True)
        self.btn_start_charge.setMinimumHeight(48)
        self.btn_start_charge.clicked.connect(self.start_charging_clicked)
        actions.addWidget(self.btn_start_charge, 1)

        self.btn_stop_charge = QPushButton("Stop Charging")
        self.btn_stop_charge.setObjectName("btnStopCharge")
        self.btn_stop_charge.setProperty("danger", True)
        self.btn_stop_charge.setMinimumHeight(48)
        self.btn_stop_charge.clicked.connect(self.stop_charging_clicked)
        actions.addWidget(self.btn_stop_charge, 1)

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

    def _on_apply_id_tag(self, tag: str) -> None:
        self.apply_id_tag_clicked.emit(tag)

    def get_selected_connector_id(self) -> int:
        return self._selected_connector_id

    def set_selected_connector(self, connector_id: int) -> None:
        if self._selected_connector_id != connector_id:
            self.telemetry_chart.clear()
        self._selected_connector_id = connector_id
        self.connector_strip.set_selected_connector(connector_id)

    def set_recent_tags(self, tags: list[str]) -> None:
        self.id_tag_input.set_recent_tags(tags)

    def update_from_engine(self, engine: "Engine") -> None:
        self.connector_strip.update_connectors(engine)

        conn = engine.get_connector(self._selected_connector_id)
        if not conn:
            return

        self.btn_plug.setEnabled(not conn.is_plugged_in)
        self.btn_unplug.setEnabled(conn.is_plugged_in)

        power_kw = _compute_effective_power_kw(engine, self._selected_connector_id)
        self.metric_power.set_value(f"{power_kw:.2f}")
        self.telemetry_chart.refresh()

        session = engine.session
        if session and session.connector_id == self._selected_connector_id:
            self.metric_energy.set_value(f"{session.energy_charged:.1f}")
            self.metric_soc.set_value(f"{session.state_of_charge:.1f}")
            duration = time.monotonic() - session.start_time
            total_secs = int(duration)
            hours = total_secs // 3600
            minutes = (total_secs % 3600) // 60
            seconds = total_secs % 60
            if hours > 0:
                duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                duration_str = f"{minutes}:{seconds:02d}"
            self.metric_duration.set_value(duration_str)
            self.soc_progress.setValue(int(session.state_of_charge))
            self._soc_percent_label.setText(f"{session.state_of_charge:.0f}%")

            self.btn_start_charge.setEnabled(False)
            self.btn_stop_charge.setEnabled(True)
        else:
            self.metric_energy.clear()
            self.metric_soc.clear()
            self.metric_duration.clear()
            self.soc_progress.setValue(0)
            self._soc_percent_label.setText("0%")

            self.btn_start_charge.setEnabled(conn.is_plugged_in)
            self.btn_stop_charge.setEnabled(False)

        self.details.update_metrics(
            tx_id=session.transaction_id if session else None,
            voltage=conn.voltage,
            current=conn.current,
            meter=engine.energy_meter.get_meter_reading(),
        )

    def record_telemetry(self, engine: "Engine") -> None:
        """Record one chart sample. Called every simulation step, even when not visible."""
        power_kw = _compute_effective_power_kw(engine, self._selected_connector_id)
        self.telemetry_chart.record_point(power_kw)

    def set_id_tag(self, tag: str) -> None:
        self.id_tag_input.set_tag(tag)
