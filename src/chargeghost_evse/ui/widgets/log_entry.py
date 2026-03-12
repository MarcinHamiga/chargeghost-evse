from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from chargeghost_evse.ui.styles import colors


class CollapsibleLogEntry(QWidget):
	"""A log entry with a clickable summary and togglable detail section."""

	def __init__(
		self,
		summary: str,
		detail: Optional[str] = None,
		parent: Optional[QWidget] = None,
	) -> None:
		super().__init__(parent)

		layout = QVBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)

		self._summary_label = QLabel(summary)
		self._summary_label.setTextFormat(Qt.TextFormat.RichText)
		self._summary_label.setWordWrap(True)
		layout.addWidget(self._summary_label)

		self._detail_label = QLabel(detail or "")
		self._detail_label.setTextFormat(Qt.TextFormat.PlainText)
		self._detail_label.setWordWrap(True)
		self._detail_label.setStyleSheet(
			f"font-family: monospace; color: {colors.TEXT_SECONDARY}; "
			f"padding: 4px 0 4px 20px;"
		)
		self._detail_label.hide()
		layout.addWidget(self._detail_label)

		if detail:
			self._summary_label.setCursor(Qt.CursorShape.PointingHandCursor)
			self._summary_label.mousePressEvent = lambda _: self._on_toggle()  # type: ignore[method-assign]

		self.show()

	def _on_toggle(self) -> None:
		self._detail_label.setVisible(not self._detail_label.isVisible())
