from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from chargeghost_evse.devtools.fault_catalog import FAULT_CATALOG


class FaultInjectionPanel(QWidget):
    fault_toggled = Signal(str, bool)
    clear_all_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._toggle_buttons: dict[str, QPushButton] = {}
        self._count_labels: dict[str, QLabel] = {}
        self._cards: dict[str, QFrame] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Fault Injection")
        title.setObjectName("sectionHeader")
        header.addWidget(title)
        header.addStretch()

        clear_btn = QPushButton("Clear All")
        clear_btn.setObjectName("clearAllBtn")
        clear_btn.clicked.connect(self._on_clear_all_clicked)
        header.addWidget(clear_btn)
        root.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(8)
        container_layout.setContentsMargins(0, 0, 0, 0)

        sorted_faults = sorted(
            FAULT_CATALOG.items(),
            key=lambda item: (item[1].scope.value, item[0]),
        )

        for fault_id, definition in sorted_faults:
            card = QFrame()
            card.setProperty("card", True)
            card.setProperty("faultCard", True)
            card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            card.setObjectName(f"fault_card_{fault_id}")

            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 8)
            card_layout.setSpacing(12)

            left = QVBoxLayout()
            left.setSpacing(2)

            name_label = QLabel(definition.label)
            name_label.setStyleSheet("font-weight: bold;")
            left.addWidget(name_label)

            scope_text = f"{definition.scope.value} · {definition.lifetime.value}"
            scope_label = QLabel(scope_text)
            scope_label.setStyleSheet("color: #8b949e; font-size: 11px;")
            left.addWidget(scope_label)

            card_layout.addLayout(left, 1)

            toggle_btn = QPushButton("Enable")
            toggle_btn.setObjectName(f"fault_toggle_{fault_id}")
            toggle_btn.clicked.connect(
                lambda checked, fid=fault_id: self._on_toggle_clicked(fid)
            )
            card_layout.addWidget(toggle_btn)
            self._toggle_buttons[fault_id] = toggle_btn

            count_label = QLabel("0")
            count_label.setObjectName(f"fault_count_{fault_id}")
            count_label.setStyleSheet("color: #f59e0b; font-size: 12px;")
            count_label.hide()
            card_layout.addWidget(count_label)
            self._count_labels[fault_id] = count_label

            container_layout.addWidget(card)
            self._cards[fault_id] = card

        container_layout.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll)

    def set_fault_states(self, states: list) -> None:
        active_ids = {s.fault_id for s in states}
        for fault_id, btn in self._toggle_buttons.items():
            is_active = fault_id in active_ids
            btn.setText("Disable" if is_active else "Enable")
            card = self._cards[fault_id]
            card.setProperty("faultActive", is_active)
            card.style().unpolish(card)
            card.style().polish(card)

        for fault_id, count_label in self._count_labels.items():
            state = next((s for s in states if s.fault_id == fault_id), None)
            if state is not None and state.trigger_count > 0:
                count_label.setText(str(state.trigger_count))
                count_label.show()
            else:
                count_label.hide()

    def _on_toggle_clicked(self, fault_id: str) -> None:
        btn = self._toggle_buttons[fault_id]
        currently_enabled = btn.text() == "Disable"
        self.fault_toggled.emit(fault_id, not currently_enabled)

    def _on_clear_all_clicked(self) -> None:
        self.clear_all_requested.emit()
