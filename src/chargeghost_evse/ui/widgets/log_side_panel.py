import logging
from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
	QHBoxLayout,
	QLabel,
	QPushButton,
	QVBoxLayout,
	QWidget,
)

from chargeghost_evse.ui.styles import colors
from chargeghost_evse.ui.widgets.icons import get_icon_html
from chargeghost_evse.ui.widgets.log_panel import LogPanel


COLLAPSED_WIDTH = 32
EXPANDED_WIDTH = 340
ANIM_DURATION_MS = 200


class _LogTab(QWidget):
	"""32px vertical tab shown when the panel is collapsed."""

	clicked = Signal()

	def __init__(self, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)
		self.setObjectName("logSideTab")
		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		self.setCursor(Qt.CursorShape.PointingHandCursor)
		self.setFixedWidth(COLLAPSED_WIDTH)

		layout = QVBoxLayout(self)
		layout.setContentsMargins(4, 12, 4, 12)
		layout.setSpacing(6)
		layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

		icon_label = QLabel()
		icon_label.setTextFormat(Qt.TextFormat.RichText)
		icon_label.setText(get_icon_html("terminal", colors.TEXT_MUTED, 14))
		icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
		layout.addWidget(icon_label)

		# Spacer — "Log" text is drawn in paintEvent (rotated 90° CCW)
		layout.addSpacing(24)

		self._badge = QLabel("")
		self._badge.setObjectName("logSideBadge")
		self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
		self._badge.hide()
		layout.addWidget(self._badge)

		layout.addStretch()

	def paintEvent(self, event) -> None:
		super().paintEvent(event)
		# Draw "Log" rotated 90° counter-clockwise (reads bottom-to-top).
		# QLabel text rotation is not possible via QSS, so we paint it manually.
		painter = QPainter(self)
		painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
		painter.setPen(QColor(colors.TEXT_MUTED))
		font = painter.font()
		font.setPixelSize(9)
		painter.setFont(font)
		# Approximate centre of the space between the icon area (~36px from top)
		# and the badge at the bottom.
		text_center_x = self.width() / 2
		text_center_y = 54  # midpoint of the 24px spacer + margins
		painter.translate(text_center_x, text_center_y)
		painter.rotate(-90)
		rect = QRect(-30, -self.width() // 2, 60, self.width())
		painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Log")
		painter.end()

	def set_count(self, count: int) -> None:
		if count > 0:
			self._badge.setText(str(count) if count < 100 else "99+")
			self._badge.show()
		else:
			self._badge.hide()

	def mousePressEvent(self, event) -> None:
		if event.button() == Qt.MouseButton.LeftButton:
			self.clicked.emit()
		super().mousePressEvent(event)


class LogSidePanel(QWidget):
	"""
	Toggleable right-side log panel.

	Collapsed: 32px tab strip with log icon, label, unread badge.
	Expanded: 340px panel with header controls and LogPanel body.
	Animation: QPropertyAnimation on maximumWidth/minimumWidth.
	"""

	log_mode_toggled = Signal(bool)

	def __init__(self, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)
		self.setObjectName("logSidePanel")
		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

		self._is_open = False
		self._unread_count = 0
		self._entry_count = 0
		self._animation: Optional[QPropertyAnimation] = None
		self._anim2: Optional[QPropertyAnimation] = None
		self._finish_close_pending = False  # True when _finish_close is connected

		self._setup_ui()
		self._set_collapsed_geometry()

	def _setup_ui(self) -> None:
		layout = QHBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)

		# --- Collapsed tab ---
		self._tab = _LogTab()
		self._tab.clicked.connect(self.toggle)
		layout.addWidget(self._tab)

		# --- Expanded content ---
		self._panel = QWidget()
		self._panel.setObjectName("logSidePanelContent")
		self._panel.hide()
		panel_layout = QVBoxLayout(self._panel)
		panel_layout.setContentsMargins(0, 0, 0, 0)
		panel_layout.setSpacing(0)

		# Header
		header = QWidget()
		header.setObjectName("logSidePanelHeader")
		header.setFixedHeight(32)
		header_layout = QHBoxLayout(header)
		header_layout.setContentsMargins(10, 0, 10, 0)
		header_layout.setSpacing(6)

		icon_label = QLabel()
		icon_label.setTextFormat(Qt.TextFormat.RichText)
		icon_label.setText(get_icon_html("terminal", colors.ACCENT_TEAL, 14))
		header_layout.addWidget(icon_label)

		title = QLabel("Activity Log")
		title.setObjectName("logSidePanelTitle")
		header_layout.addWidget(title)

		self._count_label = QLabel("")
		self._count_label.setObjectName("logSideCountLabel")
		header_layout.addWidget(self._count_label)

		header_layout.addStretch()

		self._btn_log_mode = QPushButton("Deep")
		self._btn_log_mode.setObjectName("btnLogMode")
		self._btn_log_mode.setCheckable(True)
		self._btn_log_mode.setFlat(True)
		self._btn_log_mode.clicked.connect(self._on_log_mode_toggle)
		header_layout.addWidget(self._btn_log_mode)

		self._btn_clear = QPushButton("Clear")
		self._btn_clear.setObjectName("btnClearLog")
		self._btn_clear.setFlat(True)
		self._btn_clear.clicked.connect(self._on_clear)
		header_layout.addWidget(self._btn_clear)

		btn_close = QPushButton("›")
		btn_close.setObjectName("btnLogSideClose")
		btn_close.setFixedWidth(28)
		btn_close.setToolTip("Collapse log panel  (`)")
		btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
		btn_close.clicked.connect(self.toggle)
		header_layout.addWidget(btn_close)

		panel_layout.addWidget(header)

		self._log_panel = LogPanel()
		panel_layout.addWidget(self._log_panel)

		layout.addWidget(self._panel)

	def _set_collapsed_geometry(self) -> None:
		self.setMinimumWidth(COLLAPSED_WIDTH)
		self.setMaximumWidth(COLLAPSED_WIDTH)

	def _set_expanded_geometry(self) -> None:
		self.setMinimumWidth(EXPANDED_WIDTH)
		self.setMaximumWidth(EXPANDED_WIDTH)

	def is_open(self) -> bool:
		return self._is_open

	def toggle(self) -> None:
		if self._is_open:
			self._close()
		else:
			self._open()

	def _open(self) -> None:
		self._is_open = True
		self.clear_unread()
		self._tab.hide()
		self._panel.show()
		self._animate(COLLAPSED_WIDTH, EXPANDED_WIDTH)

	def _close(self) -> None:
		self._is_open = False
		self._animate(EXPANDED_WIDTH, COLLAPSED_WIDTH)
		# Defer the panel/tab swap until the animation finishes so content
		# doesn't vanish before the width has animated to zero.
		self._animation.finished.connect(self._finish_close)
		self._finish_close_pending = True

	def _finish_close(self) -> None:
		self._finish_close_pending = False
		self._panel.hide()
		self._tab.show()

	def _animate(self, start: int, end: int) -> None:
		# Disconnect any pending close-finish callback before stopping so it
		# doesn't fire on the next (open) animation.
		if self._animation and self._finish_close_pending:
			self._animation.finished.disconnect(self._finish_close)
			self._finish_close_pending = False
		if self._animation:
			self._animation.stop()
		if self._anim2:
			self._anim2.stop()

		anim = QPropertyAnimation(self, b"maximumWidth")
		anim.setDuration(ANIM_DURATION_MS)
		anim.setStartValue(start)
		anim.setEndValue(end)
		anim.setEasingCurve(QEasingCurve.Type.OutCubic)

		# Keep minimumWidth in sync so layout doesn't fight the animation
		anim2 = QPropertyAnimation(self, b"minimumWidth")
		anim2.setDuration(ANIM_DURATION_MS)
		anim2.setStartValue(start)
		anim2.setEndValue(end)
		anim2.setEasingCurve(QEasingCurve.Type.OutCubic)

		self._animation = anim
		self._anim2 = anim2
		anim.start()
		anim2.start()

	def increment_unread(self) -> None:
		if not self._is_open:
			self._unread_count += 1
			self._tab.set_count(self._unread_count)

	def clear_unread(self) -> None:
		self._unread_count = 0
		self._tab.set_count(0)

	# ── Public log API (delegates to LogPanel) ──────────────────────────────

	def log_message(self, message: str) -> None:
		self._log_panel.log_message(message)
		self._entry_count += 1
		self._count_label.setText(str(self._entry_count))
		self.increment_unread()

	def log_record(self, record: logging.LogRecord) -> None:
		self._log_panel.log_record(record)
		self._entry_count += 1
		self._count_label.setText(str(self._entry_count))
		self.increment_unread()

	def clear(self) -> None:
		self._log_panel.clear()
		self._entry_count = 0
		self._count_label.setText("")

	def set_log_mode(self, is_detailed: bool) -> None:
		"""Sync the log-mode toggle button state without emitting log_mode_toggled."""
		self._btn_log_mode.setChecked(is_detailed)
		self._btn_log_mode.setText("Shallow" if is_detailed else "Deep")

	# ── Header button handlers ───────────────────────────────────────────────

	def _on_log_mode_toggle(self) -> None:
		is_detailed = self._btn_log_mode.isChecked()
		self._btn_log_mode.setText("Shallow" if is_detailed else "Deep")
		self.log_mode_toggled.emit(is_detailed)

	def _on_clear(self) -> None:
		self.clear()
