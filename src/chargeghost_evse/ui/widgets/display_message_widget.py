from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class DisplayMessageWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._messages: dict[int, dict] = {}
        self._setup_ui()

        self._expiry_timer = QTimer(self)
        self._expiry_timer.setInterval(1000)
        self._expiry_timer.timeout.connect(self._check_expired)
        self._expiry_timer.start()

    def _setup_ui(self) -> None:
        self.setObjectName("displayMessageWidget")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)

        self._header = QLabel("CSMS Messages")
        self._header.setObjectName("displayMessageHeader")
        layout.addWidget(self._header)

        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(3)
        layout.addWidget(self._container)

    def update_message(self, action: str, message_data: dict) -> None:
        msg_id = message_data.get("id", 0)
        if action == "clear":
            self._messages.pop(msg_id, None)
        else:
            self._messages[msg_id] = message_data

        self._rebuild()

    def _rebuild(self) -> None:
        while self._container_layout.count():
            item = self._container_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self._messages:
            self.setVisible(False)
            return

        self.setVisible(True)
        sorted_msgs = sorted(self._messages.values(), key=lambda m: m.get("id", 0))
        for msg in sorted_msgs[-5:]:
            priority = msg.get("priority", "")
            priority_str = (
                priority.value if hasattr(priority, "value") else str(priority)
            )
            text = msg.get("message", "")
            state = msg.get("state", "")
            state_str = state.value if hasattr(state, "value") else str(state)

            chip = QFrame()
            chip.setObjectName("displayMessageChip")
            chip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            if priority_str == "AlwaysFront":
                chip.setProperty("priority", "high")
            elif priority_str in ("High", "MediumHigh"):
                chip.setProperty("priority", "medium")
            else:
                chip.setProperty("priority", "low")

            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(8, 4, 8, 4)
            chip_layout.setSpacing(6)

            priority_label = QLabel(priority_str)
            priority_label.setObjectName("displayMessagePriority")
            chip_layout.addWidget(priority_label)

            text_label = QLabel(text)
            text_label.setObjectName("displayMessageText")
            text_label.setWordWrap(True)
            chip_layout.addWidget(text_label, 1)

            state_label = QLabel(state_str)
            state_label.setObjectName("displayMessageState")
            chip_layout.addWidget(state_label)

            self._container_layout.addWidget(chip)

    def _check_expired(self) -> None:
        import time

        now = time.time()
        expired_ids = []
        for msg_id, msg in self._messages.items():
            timestamp = msg.get("timestamp")
            if timestamp is None:
                continue
            try:
                from datetime import datetime

                if isinstance(timestamp, datetime):
                    created = timestamp.timestamp()
                else:
                    created = datetime.fromisoformat(str(timestamp)).timestamp()
                age = now - created
                if age > 3600:
                    expired_ids.append(msg_id)
            except (ValueError, TypeError, OSError):
                continue

        changed = False
        for msg_id in expired_ids:
            self._messages.pop(msg_id, None)
            changed = True
        if changed:
            self._rebuild()

    def clear_all(self) -> None:
        self._messages.clear()
        self._rebuild()
