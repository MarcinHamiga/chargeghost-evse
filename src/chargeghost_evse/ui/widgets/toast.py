from typing import Literal, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QWidget

from chargeghost_evse.ui.widgets.icons import get_icon, get_icon_svg


ToastType = Literal["success", "error", "warning", "info"]


class ToastNotification(QWidget):
    closed = Signal()

    TOAST_DURATION = 4000
    MIN_TOAST_HEIGHT = 48

    def __init__(
        self,
        message: str,
        toast_type: ToastType = "info",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._toast_type = toast_type
        self._setup_ui(message)

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._auto_close)
        self._timer.start(self.TOAST_DURATION)

    def _setup_ui(self, message: str) -> None:
        self.setObjectName("toastNotification")
        self.setProperty("toastType", self._toast_type)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(self.MIN_TOAST_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        icon_map = {
            "success": ("check", "#238636"),
            "error": ("x", "#da3633"),
            "warning": ("alert_triangle", "#f59e0b"),
            "info": ("info", "#3b82f6"),
        }
        icon_name, icon_color = icon_map.get(self._toast_type, ("info", "#3b82f6"))

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(20, 20)
        svg_data = get_icon_svg(icon_name, icon_color)
        base64_data: bytes = svg_data.toBase64().data()
        self._icon_label.setText(
            f"<img src='data:image/svg+xml;base64,"
            f"{base64_data.decode()}' width='20' height='20'>"
        )
        layout.addWidget(self._icon_label)

        self._message_label = QLabel(message)
        self._message_label.setObjectName("toastMessage")
        self._message_label.setWordWrap(True)
        layout.addWidget(self._message_label, 1)

        close_btn = QPushButton()
        close_btn.setObjectName("toastCloseBtn")
        close_btn.setFixedSize(24, 24)
        close_btn.setFlat(True)
        close_btn.setIcon(get_icon("x", "#ffffff"))
        close_btn.setIconSize(QSize(16, 16))
        close_btn.clicked.connect(self._on_close)
        layout.addWidget(close_btn)
        self._refresh_height()

    def update_message(self, message: str, toast_type: Optional[ToastType] = None) -> None:
        if toast_type and toast_type != self._toast_type:
            self._toast_type = toast_type
            self.setProperty("toastType", self._toast_type)
            self.style().unpolish(self)
            self.style().polish(self)
        self._message_label.setText(message)
        self._refresh_height()
        self._timer.start(self.TOAST_DURATION)

    def message_text(self) -> str:
        return self._message_label.text()

    def _refresh_height(self) -> None:
        lines = max(1, self._message_label.text().count("\n") + 1)
        target_height = max(self.MIN_TOAST_HEIGHT, 32 + (lines * 18))
        self.setMinimumHeight(target_height)
        self.adjustSize()

    def _auto_close(self) -> None:
        self._animate_out()

    def _on_close(self) -> None:
        self._timer.stop()
        self._animate_out()

    def _animate_out(self) -> None:
        if hasattr(self, "_anim"):
            return
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        self._anim = QPropertyAnimation(effect, b"opacity")
        self._anim.setDuration(200)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._anim.finished.connect(self.closed.emit)
        self._anim.finished.connect(self.deleteLater)
        self._anim.start()
