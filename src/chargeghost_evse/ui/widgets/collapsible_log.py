from typing import Optional

from PySide6.QtCore import QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QMouseEvent
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


class ClickableHeader(QWidget):
    clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class CollapsibleLogPanel(QWidget):
    log_mode_toggled = Signal(bool)
    cleared = Signal()

    COLLAPSED_HEIGHT = 36
    EXPANDED_HEIGHT = 200

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._is_expanded = False
        self._animation: Optional[QPropertyAnimation] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("collapsibleLogPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = ClickableHeader()
        self._header.setObjectName("logHeader")
        self._header.setFixedHeight(self.COLLAPSED_HEIGHT)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.clicked.connect(self.toggle)

        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        header_layout.setSpacing(8)

        self._expand_icon = QLabel()
        self._expand_icon.setObjectName("expandIcon")
        self._expand_icon.setTextFormat(Qt.TextFormat.RichText)
        self._expand_icon.setText(get_icon_html("chevron_right", colors.TEXT_MUTED, 12))
        header_layout.addWidget(self._expand_icon)

        title = QLabel("Activity Log")
        title.setObjectName("logTitle")
        header_layout.addWidget(title)

        self._log_count_label = QLabel("")
        self._log_count_label.setObjectName("logCountLabel")
        header_layout.addWidget(self._log_count_label)

        header_layout.addStretch()

        self.btn_log_mode = QPushButton("Detailed")
        self.btn_log_mode.setObjectName("btnLogMode")
        self.btn_log_mode.setCheckable(True)
        self.btn_log_mode.setFlat(True)
        self.btn_log_mode.clicked.connect(self._on_log_mode_toggle)
        header_layout.addWidget(self.btn_log_mode)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setObjectName("btnClearLog")
        self.btn_clear.setFlat(True)
        self.btn_clear.clicked.connect(self._on_clear)
        header_layout.addWidget(self.btn_clear)

        layout.addWidget(self._header)

        self._content = QWidget()
        self._content.setObjectName("logContent")
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(8, 0, 8, 8)

        self.log_panel = LogPanel()
        content_layout.addWidget(self.log_panel)

        self._content.setMaximumHeight(0)
        self._content.hide()
        layout.addWidget(self._content)

    def toggle(self) -> None:
        self._is_expanded = not self._is_expanded
        self._animate()

    def expand(self) -> None:
        if not self._is_expanded:
            self._is_expanded = True
            self._animate()

    def collapse(self) -> None:
        if self._is_expanded:
            self._is_expanded = False
            self._animate()

    def _animate(self) -> None:
        if self._animation:
            self._animation.stop()
            try:
                self._animation.finished.disconnect()
            except RuntimeError:
                pass

        animation = QPropertyAnimation(self._content, b"maximumHeight")
        animation.setDuration(200)

        if self._is_expanded:
            self._expand_icon.setText(get_icon_html("chevron_down", colors.TEXT_MUTED, 12))
            self._content.show()
            animation.setStartValue(0)
            animation.setEndValue(self.EXPANDED_HEIGHT)
        else:
            self._expand_icon.setText(get_icon_html("chevron_right", colors.TEXT_MUTED, 12))
            animation.setStartValue(self._content.height())
            animation.setEndValue(0)

        animation.finished.connect(self._on_animation_finished)
        animation.start()
        self._animation = animation

    def _on_animation_finished(self) -> None:
        if not self._is_expanded:
            self._content.hide()

    def _on_log_mode_toggle(self) -> None:
        is_detailed = self.btn_log_mode.isChecked()
        self.btn_log_mode.setText("Compact" if is_detailed else "Detailed")
        self.log_mode_toggled.emit(is_detailed)

    def _on_clear(self) -> None:
        self.log_panel.clear()
        self._log_count_label.setText("")
        self.cleared.emit()

    def log_message(self, message: str) -> None:
        self.log_panel.log_message(message)

    def set_log_count(self, count: int) -> None:
        if count > 0:
            self._log_count_label.setText(f"({count})")
        else:
            self._log_count_label.setText("")

    def clear(self) -> None:
        self.log_panel.clear()
        self._log_count_label.setText("")

    def is_expanded(self) -> bool:
        return self._is_expanded
