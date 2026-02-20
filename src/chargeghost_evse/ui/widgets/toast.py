from typing import Literal, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from chargeghost_evse.ui.widgets.icons import get_icon_svg


ToastType = Literal["success", "error", "warning", "info"]


class ToastNotification(QWidget):
    closed = Signal()

    TOAST_DURATION = 4000

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
        self.setFixedHeight(48)

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

        icon_label = QLabel()
        icon_label.setFixedSize(20, 20)
        svg_data = get_icon_svg(icon_name, icon_color)
        base64_data: bytes = svg_data.toBase64().data()
        icon_label.setText(
            f"<img src='data:image/svg+xml;base64,"
            f"{base64_data.decode()}' width='20' height='20'>"
        )
        layout.addWidget(icon_label)

        message_label = QLabel(message)
        message_label.setObjectName("toastMessage")
        message_label.setWordWrap(True)
        layout.addWidget(message_label, 1)

        close_btn = QPushButton()
        close_btn.setObjectName("toastCloseBtn")
        close_btn.setFixedSize(24, 24)
        close_btn.setFlat(True)
        close_btn.clicked.connect(self._on_close)
        layout.addWidget(close_btn)

    def _auto_close(self) -> None:
        self._animate_out()

    def _on_close(self) -> None:
        self._timer.stop()
        self._animate_out()

    def _animate_out(self) -> None:
        self.closed.emit()
        self.deleteLater()
