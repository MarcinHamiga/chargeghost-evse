from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chargeghost_evse.util.config import (
    CURRENT_MAX,
    CURRENT_MIN,
    PHASE_MAX,
    PHASE_MIN,
    VOLTAGE_MAX,
    VOLTAGE_MIN,
)

if TYPE_CHECKING:
    from chargeghost_evse.engine.engine import Engine


class ConnectorEditorCard(QFrame):
    on_apply = Signal(int, float, float, int)
    on_remove = Signal(int)

    def __init__(self, connector_id: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.connector_id = connector_id
        self._setup_ui()

    def _setup_ui(self):
        self.setProperty("connectorCard", True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        header = QHBoxLayout()
        self.title_label = QLabel(f"Connector {self.connector_id}")
        self.title_label.setProperty("connectorTitle", True)
        header.addWidget(self.title_label)
        header.addStretch()
        layout.addLayout(header)

        form = QFormLayout()
        form.setSpacing(6)

        self.voltage_spin = QDoubleSpinBox()
        self.voltage_spin.setRange(VOLTAGE_MIN, VOLTAGE_MAX)
        self.voltage_spin.setValue(230.0)
        self.voltage_spin.setSuffix(" V")
        self.voltage_spin.setDecimals(1)
        self.voltage_spin.setMinimumWidth(100)
        form.addRow("Voltage:", self.voltage_spin)

        self.current_spin = QDoubleSpinBox()
        self.current_spin.setRange(CURRENT_MIN, CURRENT_MAX)
        self.current_spin.setValue(32.0)
        self.current_spin.setSuffix(" A")
        self.current_spin.setDecimals(1)
        self.current_spin.setMinimumWidth(100)
        form.addRow("Current:", self.current_spin)

        self.phase_spin = QSpinBox()
        self.phase_spin.setRange(PHASE_MIN, PHASE_MAX)
        self.phase_spin.setValue(1)
        self.phase_spin.setSuffix(" Ph")
        self.phase_spin.setMinimumWidth(100)
        form.addRow("Phase:", self.phase_spin)

        self.voltage_spin.valueChanged.connect(self._update_power_display)
        self.current_spin.valueChanged.connect(self._update_power_display)
        self.phase_spin.valueChanged.connect(self._update_power_display)

        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setProperty("success", True)
        self.btn_apply.setMinimumHeight(28)
        self.btn_apply.setToolTip(
            "Updates connector in memory. Use 'Save Configuration' to persist to disk."
        )
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        buttons.addWidget(self.btn_apply)

        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setProperty("danger", True)
        self.btn_remove.setMinimumHeight(28)
        self.btn_remove.clicked.connect(self._on_remove_clicked)
        buttons.addWidget(self.btn_remove)

        buttons.addStretch()
        layout.addLayout(buttons)

        self.power_label = QLabel("Power: 7.36 kW")
        self.power_label.setProperty("powerLabel", True)
        layout.addWidget(self.power_label)

    def set_values(self, voltage: float, current: float, phase: int) -> None:
        self.voltage_spin.setValue(voltage)
        self.current_spin.setValue(current)
        self.phase_spin.setValue(phase)
        self._update_power_display()

    def _update_power_display(self) -> None:
        power_w = (
            self.voltage_spin.value()
            * self.current_spin.value()
            * self.phase_spin.value()
        )
        power_kw = power_w / 1000.0
        self.power_label.setText(f"Power: {power_kw:.2f} kW")

    def _on_apply_clicked(self) -> None:
        self.on_apply.emit(
            self.connector_id,
            self.voltage_spin.value(),
            self.current_spin.value(),
            self.phase_spin.value(),
        )

    def _on_remove_clicked(self) -> None:
        result = QMessageBox.question(
            self,
            "Remove Connector",
            f"Remove Connector {self.connector_id}? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.on_remove.emit(self.connector_id)

    def set_connector_id(self, connector_id: int) -> None:
        self.connector_id = connector_id
        self.title_label.setText(f"Connector {connector_id}")


class ConnectorPanel(QWidget):
    on_connectors_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._connector_cards: list[ConnectorEditorCard] = []
        self._engine: Optional["Engine"] = None
        self._on_apply_callback: Optional[Callable] = None
        self._on_remove_callback: Optional[Callable] = None
        self._on_add_callback: Optional[Callable] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Connector Management")
        title.setObjectName("sectionHeader")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        self._empty_state = QWidget()
        self._empty_state.setObjectName("emptyStateWidget")
        empty_layout = QVBoxLayout(self._empty_state)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(12)
        empty_layout.setContentsMargins(0, 40, 0, 40)

        empty_title = QLabel("No Connectors Configured")
        empty_title.setObjectName("emptyStateTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)

        empty_desc = QLabel("Add a connector to start simulation.")
        empty_desc.setObjectName("emptyStateDescription")
        empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_desc)

        layout.addWidget(self._empty_state)
        self._empty_state.hide()

        self.cards_container = QVBoxLayout()
        self.cards_container.setSpacing(12)
        layout.addLayout(self.cards_container)

        self.btn_add = QPushButton("+ Add Connector")
        self.btn_add.setMinimumHeight(32)
        self.btn_add.clicked.connect(self._on_add_clicked)
        layout.addWidget(self.btn_add)

        layout.addStretch()

    def set_engine(self, engine: "Engine") -> None:
        self._engine = engine
        self._refresh_cards()

    def set_callbacks(
        self,
        on_apply: Optional[Callable] = None,
        on_remove: Optional[Callable] = None,
        on_add: Optional[Callable] = None,
    ) -> None:
        self._on_apply_callback = on_apply
        self._on_remove_callback = on_remove
        self._on_add_callback = on_add

    def _refresh_cards(self) -> None:
        self._clear_cards()

        if self._engine is None:
            self._empty_state.show()
            return

        if not self._engine.connectors:
            self._empty_state.show()
        else:
            self._empty_state.hide()

        for connector in self._engine.connectors:
            card = ConnectorEditorCard(connector.id)
            card.set_values(connector.voltage, connector.current, connector.phase)
            card.on_apply.connect(self._on_card_apply)
            card.on_remove.connect(self._on_card_remove)
            self.cards_container.addWidget(card)
            self._connector_cards.append(card)

    def _clear_cards(self) -> None:
        for card in self._connector_cards:
            card.setParent(None)
            card.deleteLater()
        self._connector_cards.clear()

    def _on_card_apply(
        self, connector_id: int, voltage: float, current: float, phase: int
    ) -> None:
        if self._on_apply_callback:
            self._on_apply_callback(connector_id, voltage, current, phase)

    def _on_card_remove(self, connector_id: int) -> None:
        if self._on_remove_callback:
            self._on_remove_callback(connector_id)
        self.on_connectors_changed.emit()

    def _on_add_clicked(self) -> None:
        if self._on_add_callback:
            self._on_add_callback()
        self.on_connectors_changed.emit()

    def update_from_engine(self) -> None:
        for i, connector in enumerate(self._engine.connectors if self._engine else []):
            if i < len(self._connector_cards):
                card = self._connector_cards[i]
                card.set_values(connector.voltage, connector.current, connector.phase)
                if card.connector_id != connector.id:
                    card.set_connector_id(connector.id)

    def rebuild_cards(self) -> None:
        self._refresh_cards()
