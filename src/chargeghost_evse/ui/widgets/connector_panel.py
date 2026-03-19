"""
Connector Panel Widget Module.

This module provides UI components for managing EVSE connectors in the
ChargeGhost application. It includes widgets for displaying, editing, and
configuring connector parameters such as voltage, current, and phase settings.

Classes:
    ConnectorEditorCard: Individual card widget for editing a single connector.
    ConnectorPanel: Container panel managing multiple connector editor cards.
"""

from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
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
    """
    Card widget for editing a single EVSE connector's parameters.

    This widget provides a form-based interface for configuring connector
    settings including voltage, current, and phase. It displays real-time
    power calculations and emits signals when changes are applied or the
    connector is removed.

    Signals:
        on_apply: Emitted when user applies changes.
            Parameters: (connector_id, voltage, current, phase)
        on_remove: Emitted when user requests connector removal.
            Parameters: (connector_id,)

    Attributes:
        connector_id: The unique identifier for this connector.
    """

    # Signal emitted when apply button is clicked with connector parameters
    on_apply = Signal(int, float, float, int)  # (connector_id, voltage, current, phase)
    # Signal emitted when remove button is clicked
    on_remove = Signal(int)  # (connector_id,)

    def __init__(self, connector_id: int, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the connector editor card.

        Args:
            connector_id: Unique identifier for the connector this card represents.
            parent: Optional parent widget for Qt ownership.
        """
        super().__init__(parent)
        self.connector_id = connector_id
        self._setup_ui()

    def _setup_ui(self) -> None:
        """
        Build and configure the card's user interface.

        Creates the layout structure with:
        - Header showing connector ID
        - Form with voltage, current, and phase spin boxes
        - Apply and Remove action buttons
        - Power calculation display label
        """
        # Set QSS property for styling and enable styled background
        self.setProperty("connectorCard", True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Main vertical layout with consistent spacing and margins
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        # Header row with connector title
        header = QHBoxLayout()
        self.title_label = QLabel(f"Connector {self.connector_id}")
        self.title_label.setProperty("connectorTitle", True)
        header.addWidget(self.title_label)
        header.addStretch()  # Push title to the left
        layout.addLayout(header)

        # Form layout for parameter inputs
        form = QFormLayout()
        form.setSpacing(6)

        # Voltage input: AC voltage in volts (typical range 200-240V)
        self.voltage_spin = QDoubleSpinBox()
        self.voltage_spin.setRange(VOLTAGE_MIN, VOLTAGE_MAX)
        self.voltage_spin.setValue(230.0)  # Default to standard EU voltage
        self.voltage_spin.setSuffix(" V")
        self.voltage_spin.setDecimals(1)
        self.voltage_spin.setMinimumWidth(100)
        form.addRow("Voltage:", self.voltage_spin)

        # Current input: Maximum current in amperes (typical range 6-32A)
        self.current_spin = QDoubleSpinBox()
        self.current_spin.setRange(CURRENT_MIN, CURRENT_MAX)
        self.current_spin.setValue(32.0)  # Default to common EVSE max
        self.current_spin.setSuffix(" A")
        self.current_spin.setDecimals(1)
        self.current_spin.setMinimumWidth(100)
        form.addRow("Current:", self.current_spin)

        # Phase input: Number of electrical phases (1 or 3)
        self.phase_spin = QSpinBox()
        self.phase_spin.setRange(PHASE_MIN, PHASE_MAX)
        self.phase_spin.setValue(1)  # Default to single-phase
        self.phase_spin.setSuffix(" Ph")
        self.phase_spin.setMinimumWidth(100)
        form.addRow("Phase:", self.phase_spin)

        self.voltage_spin.valueChanged.connect(self._update_power_display)
        self.current_spin.valueChanged.connect(self._update_power_display)
        self.phase_spin.valueChanged.connect(self._update_power_display)

        layout.addLayout(form)

        # Action buttons row
        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        # Apply button with success styling (green)
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setProperty("success", True)
        self.btn_apply.setMinimumHeight(28)
        self.btn_apply.setToolTip(
            "Updates connector in memory. Use 'Save Configuration' to persist to disk."
        )
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        buttons.addWidget(self.btn_apply)

        # Remove button with danger styling (red)
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setProperty("danger", True)
        self.btn_remove.setMinimumHeight(28)
        self.btn_remove.clicked.connect(self._on_remove_clicked)
        buttons.addWidget(self.btn_remove)

        buttons.addStretch()  # Push buttons to the left
        layout.addLayout(buttons)

        # Power display: Calculated from V × A × phases
        self.power_label = QLabel("Power: 7.36 kW")
        self.power_label.setProperty("powerLabel", True)
        layout.addWidget(self.power_label)

    def set_values(self, voltage: float, current: float, phase: int) -> None:
        """
        Update the spin box values and recalculate power display.

        Args:
            voltage: Voltage value in volts.
            current: Current value in amperes.
            phase: Number of phases (1 or 3).
        """
        self.voltage_spin.setValue(voltage)
        self.current_spin.setValue(current)
        self.phase_spin.setValue(phase)
        self._update_power_display()

    def _update_power_display(self) -> None:
        """
        Calculate and update the power display label.

        Power is calculated using the formula: P = V × I × phases
        Result is converted from watts to kilowatts for display.
        """
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
        """
        Handle remove button click.

        Emits the on_remove signal to notify parent that this connector
        should be removed from the configuration.
        """
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
        """
        Update the connector ID and refresh the title label.

        Used when connector IDs are renumbered after removal.

        Args:
            connector_id: New connector identifier to display.
        """
        self.connector_id = connector_id
        self.title_label.setText(f"Connector {connector_id}")


class ConnectorPanel(QWidget):
    """
    Panel widget for managing multiple EVSE connectors.

    This panel provides a scrollable container for ConnectorEditorCard widgets,
    handling the addition, removal, and modification of connectors. It maintains
    synchronization with the Engine's connector state and provides callbacks
    for parent components to react to changes.

    Signals:
        on_connectors_changed: Emitted when connectors are added or removed.

    Example:
        >>> panel = ConnectorPanel()
        >>> panel.set_engine(engine)
        >>> panel.set_callbacks(
        ...     on_apply=self._handle_apply,
        ...     on_remove=self._handle_remove,
        ...     on_add=self._handle_add
        ... )
    """

    # Signal emitted when connector list changes (add/remove operations)
    on_connectors_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the connector management panel.

        Args:
            parent: Optional parent widget for Qt ownership.
        """
        super().__init__(parent)
        # List of active connector card widgets
        self._connector_cards: list[ConnectorEditorCard] = []
        # Reference to the engine for data synchronization
        self._engine: Optional["Engine"] = None
        # Callbacks for connector operations
        self._on_apply_callback: Optional[Callable] = None
        self._on_remove_callback: Optional[Callable] = None
        self._on_add_callback: Optional[Callable] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """
        Build and configure the panel's user interface.

        Creates the layout structure with:
        - Section header title
        - Empty state widget (shown when no connectors exist)
        - Container for connector editor cards
        - Add connector button
        """
        # Main vertical layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # Section header with title
        header = QHBoxLayout()
        title = QLabel("Connector Management")
        title.setObjectName("sectionHeader")
        header.addWidget(title)
        header.addStretch()  # Push title to the left
        layout.addLayout(header)

        # Empty state widget shown when no connectors are configured
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
        self._empty_state.hide()  # Hidden by default, shown when no connectors

        # Container grid layout for connector cards
        self._connectors_grid = QGridLayout()
        self._connectors_grid.setSpacing(12)
        self._grid_cols = 1
        layout.addLayout(self._connectors_grid)

        # Add connector button
        self.btn_add = QPushButton("+ Add Connector")
        self.btn_add.setMinimumHeight(32)
        self.btn_add.clicked.connect(self._on_add_clicked)
        layout.addWidget(self.btn_add)

        # Stretch at bottom to push content up
        layout.addStretch()

    def set_engine(self, engine: "Engine") -> None:
        """
        Set the engine reference and refresh the connector cards.

        Args:
            engine: The Engine instance containing connector data.
        """
        self._engine = engine
        self._refresh_cards()

    def set_callbacks(
        self,
        on_apply: Optional[Callable] = None,
        on_remove: Optional[Callable] = None,
        on_add: Optional[Callable] = None,
    ) -> None:
        """
        Register callback functions for connector operations.

        Args:
            on_apply: Callback for when connector settings are applied.
                Signature: (connector_id: int, voltage: float, current: float, phase: int) -> None
            on_remove: Callback for when a connector is removed.
                Signature: (connector_id: int) -> None
            on_add: Callback for when a new connector is requested.
                Signature: () -> None
        """
        self._on_apply_callback = on_apply
        self._on_remove_callback = on_remove
        self._on_add_callback = on_add

    def _refresh_cards(self) -> None:
        """
        Rebuild all connector cards from the engine state.

        Clears existing cards and creates new ones based on the current
        engine connector configuration. Shows/hides empty state as appropriate.
        """
        self._clear_cards()

        # Show empty state if no engine is set
        if self._engine is None:
            self._empty_state.show()
            return

        # Toggle empty state based on connector count
        if not self._engine.connectors:
            self._empty_state.show()
        else:
            self._empty_state.hide()

        # Create a card for each connector in the engine
        cards: list[ConnectorEditorCard] = []
        for connector in self._engine.connectors:
            card = ConnectorEditorCard(connector.id)
            card.set_values(connector.voltage, connector.current, connector.phase)
            # Connect card signals to panel handlers
            card.on_apply.connect(self._on_card_apply)
            card.on_remove.connect(self._on_card_remove)
            cards.append(card)
            self._connector_cards.append(card)
        for i, card in enumerate(cards):
            row, col = divmod(i, self._grid_cols)
            self._connectors_grid.addWidget(card, row, col)

    def _clear_cards(self) -> None:
        """
        Remove and delete all connector card widgets.

        Properly cleans up Qt widgets by removing parent ownership
        and scheduling deletion.
        """
        for card in self._connector_cards:
            card.setParent(None)
            card.deleteLater()
        self._connector_cards.clear()

    def _on_card_apply(
        self, connector_id: int, voltage: float, current: float, phase: int
    ) -> None:
        """
        Handle apply signal from a connector card.

        Forwards the apply event to the registered callback if available.

        Args:
            connector_id: ID of the connector being modified.
            voltage: New voltage value in volts.
            current: New current value in amperes.
            phase: New phase count.
        """
        if self._on_apply_callback:
            self._on_apply_callback(connector_id, voltage, current, phase)

    def _on_card_remove(self, connector_id: int) -> None:
        """
        Handle remove signal from a connector card.

        Forwards the remove event to the registered callback and emits
        the on_connectors_changed signal.

        Args:
            connector_id: ID of the connector to remove.
        """
        if self._on_remove_callback:
            self._on_remove_callback(connector_id)
        self.on_connectors_changed.emit()

    def _on_add_clicked(self) -> None:
        """
        Handle add connector button click.

        Forwards the add event to the registered callback and emits
        the on_connectors_changed signal.
        """
        if self._on_add_callback:
            self._on_add_callback()
        self.on_connectors_changed.emit()

    def update_from_engine(self) -> None:
        """
        Update existing card values from the engine without rebuilding.

        This is a lightweight update that modifies values in place,
        useful for periodic refreshes without full widget reconstruction.
        Also updates connector IDs if they have changed.
        """
        for i, connector in enumerate(self._engine.connectors if self._engine else []):
            if i < len(self._connector_cards):
                card = self._connector_cards[i]
                card.set_values(connector.voltage, connector.current, connector.phase)
                # Update ID if connector was renumbered
                if card.connector_id != connector.id:
                    card.set_connector_id(connector.id)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow_connector_grid()

    def _reflow_connector_grid(self) -> None:
        """
        Reflow connector cards into the appropriate number of columns.

        Switches between 1-column and 2-column layouts based on the panel width.
        Threshold is 700px: wider panels use 2 columns, narrower use 1.
        """
        if not hasattr(self, "_connectors_grid"):
            return
        cols = 2 if self.width() > 700 else 1
        if cols == self._grid_cols:
            return
        self._grid_cols = cols
        # Collect existing card widgets from the grid
        cards: list[QWidget] = []
        while self._connectors_grid.count():
            item = self._connectors_grid.takeAt(0)
            if item and item.widget():
                cards.append(item.widget())
        for i, card in enumerate(cards):
            row, col = divmod(i, cols)
            self._connectors_grid.addWidget(card, row, col)

    def rebuild_cards(self) -> None:
        """
        Force a complete rebuild of all connector cards.

        This is a heavier operation than update_from_engine() and should
        be used when the connector list structure has changed (additions
        or removals).
        """
        self._refresh_cards()
