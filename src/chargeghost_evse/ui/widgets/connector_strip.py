from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
	QFrame,
	QHBoxLayout,
	QLabel,
	QVBoxLayout,
	QWidget,
)


class ConnectorIndicator(QFrame):
	clicked = Signal(int)

	def __init__(self, connector_id: int, parent: Optional[QWidget] = None):
		super().__init__(parent)
		self._connector_id = connector_id
		self._is_selected = False
		self._status = "Available"
		self._is_plugged = False
		self._soc: Optional[float] = None

		self._setup_ui()

	def _setup_ui(self) -> None:
		self.setProperty("connectorIndicator", True)
		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		self.setCursor(Qt.CursorShape.PointingHandCursor)
		self.setFixedHeight(60)
		self.setMinimumWidth(120)

		layout = QVBoxLayout(self)
		layout.setSpacing(4)
		layout.setContentsMargins(12, 8, 12, 8)

		header = QHBoxLayout()
		self._id_label = QLabel(f"C{self._connector_id}")
		self._id_label.setObjectName("connectorIdLabel")
		header.addWidget(self._id_label)
		header.addStretch()

		self._status_icon = QLabel("🟢")
		header.addWidget(self._status_icon)
		layout.addLayout(header)

		self._status_label = QLabel("Available")
		self._status_label.setObjectName("connectorStatusLabel")
		layout.addWidget(self._status_label)

		self._soc_label = QLabel("")
		self._soc_label.setObjectName("connectorSocLabel")
		self._soc_label.hide()
		layout.addWidget(self._soc_label)

	def connector_id(self) -> int:
		return self._connector_id

	def set_selected(self, selected: bool) -> None:
		if self._is_selected != selected:
			self._is_selected = selected
			self.setProperty("selected", selected)
			self.style().unpolish(self)
			self.style().polish(self)

	def update_status(
		self,
		status: str,
		is_plugged: bool,
		soc: Optional[float] = None,
		id_tag: Optional[str] = None,
	) -> None:
		self._status = status
		self._is_plugged = is_plugged
		self._soc = soc

		status_icons = {
			"Available": "🟢",
			"Preparing": "🟡",
			"Charging": "⚡",
			"SuspendedEV": "⏸️",
			"SuspendedEVSE": "⏸️",
			"Finishing": "🔵",
			"Reserved": "🔒",
			"Unavailable": "🔴",
			"Faulted": "⚠️",
		}
		icon = status_icons.get(status, "⚪")
		self._status_icon.setText(icon)

		if status == "Charging" and soc is not None:
			self._status_label.setText("Charging")
			self._soc_label.setText(f"{soc:.0f}%")
			self._soc_label.show()
		elif is_plugged:
			self._status_label.setText("Plugged")
			self._soc_label.hide()
		else:
			self._status_label.setText(status)
			self._soc_label.hide()

		self.setProperty("charging", status == "Charging")
		self.style().unpolish(self)
		self.style().polish(self)

	def mousePressEvent(self, event: QMouseEvent) -> None:
		if event.button() == Qt.MouseButton.LeftButton:
			self.clicked.emit(self._connector_id)
		super().mousePressEvent(event)


class ConnectorStrip(QWidget):
	connector_selected = Signal(int)

	def __init__(self, parent: Optional[QWidget] = None):
		super().__init__(parent)
		self._indicators: list[ConnectorIndicator] = []
		self._selected_id: Optional[int] = None
		self._setup_ui()

	def _setup_ui(self) -> None:
		self.setObjectName("connectorStrip")

		self._main_layout = QHBoxLayout(self)
		self._main_layout.setContentsMargins(0, 0, 0, 0)
		self._main_layout.setSpacing(8)

		self._indicators_layout = QHBoxLayout()
		self._indicators_layout.setSpacing(8)
		self._main_layout.addLayout(self._indicators_layout)
		self._main_layout.addStretch()

	def set_selected_connector(self, connector_id: int) -> None:
		self._selected_id = connector_id
		for indicator in self._indicators:
			indicator.set_selected(indicator.connector_id() == connector_id)

	def update_connectors(self, engine) -> None:
		self._clear_indicators()

		for conn in engine.connectors:
			session = (
				engine.session
				if engine.session and engine.session.connector_id == conn.id
				else None
			)

			indicator = ConnectorIndicator(conn.id)
			indicator.update_status(
				status=conn.status.value,
				is_plugged=conn.is_plugged_in,
				soc=session.state_of_charge if session else None,
				id_tag=conn.id_tag,
			)
			indicator.set_selected(conn.id == self._selected_id)
			indicator.clicked.connect(self._on_indicator_clicked)

			self._indicators_layout.addWidget(indicator)
			self._indicators.append(indicator)

		if self._selected_id is None and self._indicators:
			self._selected_id = self._indicators[0].connector_id()
			self._indicators[0].set_selected(True)

	def update_indicator_status(
		self,
		connector_id: int,
		status: str,
		is_plugged: bool,
		soc: Optional[float] = None,
	) -> None:
		for indicator in self._indicators:
			if indicator.connector_id() == connector_id:
				indicator.update_status(status, is_plugged, soc)
				break

	def _on_indicator_clicked(self, connector_id: int) -> None:
		self.set_selected_connector(connector_id)
		self.connector_selected.emit(connector_id)

	def _clear_indicators(self) -> None:
		for indicator in self._indicators:
			indicator.setParent(None)
			indicator.deleteLater()
		self._indicators.clear()

	def get_selected_connector_id(self) -> Optional[int]:
		return self._selected_id
