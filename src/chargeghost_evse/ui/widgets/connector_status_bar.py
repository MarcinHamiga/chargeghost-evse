from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
	QFrame,
	QHBoxLayout,
	QLabel,
	QWidget,
)

from chargeghost_evse.ui.styles import colors
from chargeghost_evse.ui.widgets.icons import get_icon_html


_STATUS_COLORS: dict[str, str] = {
	"Available": colors.SUCCESS,
	"Preparing": colors.WARNING,
	"Charging": colors.ACCENT_TEAL,
	"SuspendedEV": colors.WARNING,
	"SuspendedEVSE": colors.WARNING,
	"Finishing": colors.INFO,
	"Reserved": colors.TEXT_SECONDARY,
	"Unavailable": colors.DANGER,
	"Faulted": colors.DANGER,
}


class ConnectorPill(QWidget):
	"""Compact clickable pill showing connector ID and status."""

	clicked = Signal(int)

	def __init__(self, connector_id: int, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)
		self._connector_id = connector_id
		self._is_selected = False

		self.setObjectName("connectorPill")
		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		self.setCursor(Qt.CursorShape.PointingHandCursor)

		layout = QHBoxLayout(self)
		layout.setContentsMargins(8, 0, 8, 0)
		layout.setSpacing(5)

		self._dot = QLabel()
		self._dot.setObjectName("connectorPillDot")
		self._dot.setFixedSize(7, 7)
		layout.addWidget(self._dot)

		self._label = QLabel(f"{connector_id} · Available")
		self._label.setObjectName("connectorPillLabel")
		layout.addWidget(self._label)

	def update_status(self, status: str, soc: Optional[float]) -> None:
		color = _STATUS_COLORS.get(status, colors.TEXT_MUTED)
		dot_html = get_icon_html("circle_green", color, 7)
		self._dot.setTextFormat(Qt.TextFormat.RichText)
		self._dot.setText(dot_html)

		display = status
		if status == "Charging" and soc is not None:
			display = f"Charging · {soc:.0f}%"
		self._label.setText(f"{self._connector_id} · {display}")

		self.setProperty("status", status.lower())
		self.style().unpolish(self)
		self.style().polish(self)

	def set_selected(self, selected: bool) -> None:
		if self._is_selected != selected:
			self._is_selected = selected
			self.setProperty("selected", selected)
			self.style().unpolish(self)
			self.style().polish(self)

	def mousePressEvent(self, event: QMouseEvent) -> None:
		if event.button() == Qt.MouseButton.LeftButton:
			self.clicked.emit(self._connector_id)
		super().mousePressEvent(event)


class ConnectorStatusBar(QWidget):
	"""
	38px horizontal bar showing all connectors as pills and live session stats.

	Public API:
	  update_connector(connector_id, status, soc)  — update/create a pill
	  update_session_stats(power_kw, soc, duration_str)  — show/hide session stats
	  connector_selected signal  — emitted when a pill is clicked
	"""

	connector_selected = Signal(int)

	def __init__(self, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)
		self.setObjectName("connectorStatusBar")
		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		self.setFixedHeight(38)

		self._pills: dict[int, ConnectorPill] = {}
		self._selected_id: Optional[int] = None

		self._setup_ui()
		self.show()

	def _setup_ui(self) -> None:
		layout = QHBoxLayout(self)
		layout.setContentsMargins(12, 0, 12, 0)
		layout.setSpacing(8)

		connectors_label = QLabel("CONNECTORS")
		connectors_label.setObjectName("connectorBarLabel")
		layout.addWidget(connectors_label)

		self._pills_layout = QHBoxLayout()
		self._pills_layout.setSpacing(6)
		layout.addLayout(self._pills_layout)

		sep = QFrame()
		sep.setFrameShape(QFrame.Shape.VLine)
		sep.setObjectName("connectorBarSep")
		layout.addWidget(sep)

		# Live session stats (right-aligned, hidden when idle)
		self._stats_widget = QWidget()
		stats_layout = QHBoxLayout(self._stats_widget)
		stats_layout.setContentsMargins(0, 0, 0, 0)
		stats_layout.setSpacing(10)

		self._power_label = QLabel("0.0 kW")
		self._power_label.setObjectName("connectorBarStat")
		stats_layout.addWidget(self._power_label)

		stats_layout.addWidget(self._sep_label("·"))

		self._soc_label = QLabel("0%")
		self._soc_label.setObjectName("connectorBarStat")
		stats_layout.addWidget(self._soc_label)

		stats_layout.addWidget(self._sep_label("·"))

		self._duration_label = QLabel("--")
		self._duration_label.setObjectName("connectorBarStat")
		stats_layout.addWidget(self._duration_label)

		layout.addWidget(self._stats_widget)
		self._stats_widget.hide()

		layout.addStretch()

	def _sep_label(self, text: str) -> QLabel:
		lbl = QLabel(text)
		lbl.setObjectName("connectorBarStatSep")
		return lbl

	def update_connector(
		self, connector_id: int, status: str, soc: Optional[float]
	) -> None:
		if connector_id not in self._pills:
			# Compute sorted insert position BEFORE adding to the dict
			insert_pos = sum(1 for k in self._pills if k < connector_id)
			pill = ConnectorPill(connector_id)
			pill.clicked.connect(self._on_pill_clicked)
			self._pills[connector_id] = pill
			self._pills_layout.insertWidget(insert_pos, pill)

			# Auto-select first connector
			if self._selected_id is None:
				self._selected_id = connector_id
				pill.set_selected(True)

		self._pills[connector_id].update_status(status, soc)

	def update_session_stats(
		self, power_kw: float, soc: float, duration_str: str
	) -> None:
		if power_kw > 0.0:
			self._power_label.setText(f"{power_kw:.1f} kW")
			self._soc_label.setText(f"{soc:.0f}%")
			self._duration_label.setText(duration_str)
			self._stats_widget.show()
		else:
			self._stats_widget.hide()

	def set_selected_connector(self, connector_id: int) -> None:
		for cid, pill in self._pills.items():
			pill.set_selected(cid == connector_id)
		self._selected_id = connector_id

	def _on_pill_clicked(self, connector_id: int) -> None:
		self.set_selected_connector(connector_id)
		self.connector_selected.emit(connector_id)
