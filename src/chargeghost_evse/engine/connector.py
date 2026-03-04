"""
Connector Module.

This module defines the Connector class which represents a single EVSE
(Electric Vehicle Supply Equipment) connector and its state management.
Connectors handle the physical charging interface between the EVSE and
electric vehicles.

Classes:
    ConnectorState: Enumeration of possible connector states per OCPP 1.6.
    Connector: Manages connector status, parameters, and charging operations.
"""

import enum
from typing import Optional

from chargeghost_evse.util.config import (
    CURRENT_MAX,
    CURRENT_MIN,
    PHASE_MAX,
    PHASE_MIN,
    VOLTAGE_MAX,
    VOLTAGE_MIN,
)
from chargeghost_evse.util.event import Event
from chargeghost_evse.util.subscriber import Subscriber


class ConnectorState(enum.Enum):
    """
    OCPP 1.6 connector status values.

    These states represent the operational status of a connector as defined
    in the OCPP 1.6 specification. State transitions follow the charging
    session lifecycle.

    Attributes:
        AVAILABLE: Connector is available for a new charging session.
        PREPARING: EV is plugged in, preparing for charging.
        CHARGING: Energy is being transferred to the EV.
        SUSPENDED_EVSE: Charging suspended by EVSE (e.g., schedule limit).
        SUSPENDED_EV: Charging suspended by EV (e.g., battery full).
        FINISHING: Charging session completed, transaction finalizing.
        UNAVAILABLE: Connector is out of service (operator disabled).
        FAULTED: Connector is in a faulted state (hardware error).
    """

    AVAILABLE = "Available"
    PREPARING = "Preparing"
    CHARGING = "Charging"
    SUSPENDED_EVSE = "SuspendedEVSE"
    SUSPENDED_EV = "SuspendedEV"
    FINISHING = "Finishing"
    UNAVAILABLE = "Unavailable"
    FAULTED = "Faulted"


# Valid state transitions: (current_state, action) -> new_state
VALID_TRANSITIONS: dict[tuple[ConnectorState, str], ConnectorState] = {
    # Plug in/out
    (ConnectorState.AVAILABLE, "plug_in"): ConnectorState.PREPARING,
    (ConnectorState.PREPARING, "unplug"): ConnectorState.AVAILABLE,
    (ConnectorState.FINISHING, "unplug"): ConnectorState.AVAILABLE,
    (ConnectorState.CHARGING, "unplug"): ConnectorState.AVAILABLE,
    (ConnectorState.SUSPENDED_EV, "unplug"): ConnectorState.AVAILABLE,
    # Session lifecycle
    (ConnectorState.PREPARING, "start_charging"): ConnectorState.CHARGING,
    (ConnectorState.CHARGING, "stop_charging"): ConnectorState.FINISHING,
    (ConnectorState.SUSPENDED_EV, "stop_charging"): ConnectorState.FINISHING,
    # Suspension
    (ConnectorState.CHARGING, "suspend_ev"): ConnectorState.SUSPENDED_EV,
    (ConnectorState.SUSPENDED_EV, "resume"): ConnectorState.CHARGING,
}


class Connector(Subscriber):
    """
    Represents a single EVSE connector with state and parameter management.

    A Connector manages the physical charging interface, tracking whether
    an EV is plugged in, the current operational status, and electrical
    parameters (voltage, current, phases). It emits events when state or
    parameters change.

    The connector follows OCPP 1.6 state transitions:
    - AVAILABLE → PREPARING (when EV plugs in)
    - PREPARING → CHARGING (when session starts)
    - CHARGING → SUSPENDED_EV/SEVSE (when paused)
    - CHARGING → FINISHING (when session stops)
    - FINISHING → AVAILABLE (after transaction ends)

    Events:
        on_status_change: Emitted when connector status changes.
            Parameters: connector_id (int), status (ConnectorState)

    Attributes:
        id: Unique connector identifier (1-indexed per OCPP).
        voltage: Operating voltage in volts (V).
        current: Maximum current in amperes (A).
        phase: Number of electrical phases (1 or 3).
        is_plugged_in: Whether an EV is currently connected.
        id_tag: Authorization identifier for the connected EV, if any.

    Example:
        >>> connector = Connector(id=1, voltage=230.0, current=32.0, phase=3)
        >>> connector.plug_in()  # Simulate EV connection
        >>> connector.status
        <ConnectorState.PREPARING: 'Preparing'>
    """

    def __init__(
        self,
        id: int,
        voltage: float = 230.0,
        current: float = 32.0,
        phase: int = 1,
    ) -> None:
        """
        Initialize a connector with electrical parameters.

        Args:
            id: Unique connector identifier (OCPP uses 1-indexed IDs).
            voltage: Operating voltage in volts. Defaults to 230.0V (EU standard).
            current: Maximum current in amperes. Defaults to 32.0A.
            phase: Number of electrical phases. Defaults to 1 (single-phase).
        """
        super().__init__()
        self.id: int = id
        self.voltage: float = voltage
        self.current: float = current
        self.phase: int = phase

        # Current operational status
        self._status: ConnectorState = ConnectorState.AVAILABLE
        # Persistent status preserved across plug/unplug cycles
        # Used to restore UNAVAILABLE/FAULTED states after unplugging
        self._persistent_status: ConnectorState = ConnectorState.AVAILABLE
        # Physical connection state
        self.is_plugged_in: bool = False
        # Authorization tag for the connected EV
        self.id_tag: Optional[str] = None

        # Events for state change notifications
        self.on_status_change: Event = Event()

    @property
    def status(self) -> ConnectorState:
        """
        Get the current connector status.

        Returns:
            Current ConnectorState value.
        """
        return self._status

    @status.setter
    def status(self, new_status: ConnectorState) -> None:
        """
        Set the connector status and emit change event.

        Updates persistent status for states that should survive
        plug/unplug cycles (UNAVAILABLE, FAULTED, AVAILABLE).

        Args:
            new_status: The new ConnectorState to set.
        """
        if self._status != new_status:
            # Persistent states survive plug/unplug cycles
            if new_status in (
                ConnectorState.UNAVAILABLE,
                ConnectorState.FAULTED,
                ConnectorState.AVAILABLE,
            ):
                self._persistent_status = new_status

            self._status = new_status
            self.on_status_change.emit(connector_id=self.id, status=new_status)

    def _transition(self, action: str) -> Optional[str]:
        """
        Attempt a state transition.

        Looks up (current_state, action) in VALID_TRANSITIONS.
        If valid, updates status and returns None.
        If invalid, returns an error message string.

        Args:
            action: The transition action name.

        Returns:
            None on success, error string on invalid transition.
        """
        key = (self._status, action)
        new_state = VALID_TRANSITIONS.get(key)
        if new_state is None:
            return f"Invalid transition: {self._status.value} + {action}"
        self.status = new_state
        return None

    def set_parameters(
        self,
        voltage: Optional[float] = None,
        current: Optional[float] = None,
        phase: Optional[int] = None,
    ) -> Optional[str]:
        """
        Update electrical parameters with validation.

        Updates only the parameters that are provided (not None).
        Validates values against configured min/max limits.

        Args:
            voltage: New voltage in volts, or None to skip.
            current: New current in amperes, or None to skip.
            phase: New phase count, or None to skip.

        Returns:
            Error message string if validation fails, None on success.

        Example:
            >>> result = connector.set_parameters(current=16.0)
            >>> if result:
            ...     print(f"Error: {result}")
        """
        if voltage is not None:
            if not (VOLTAGE_MIN <= voltage <= VOLTAGE_MAX):
                return f"Voltage must be between {VOLTAGE_MIN}V and {VOLTAGE_MAX}V"
            self.voltage = voltage

        if current is not None:
            if not (CURRENT_MIN <= current <= CURRENT_MAX):
                return f"Current must be between {CURRENT_MIN}A and {CURRENT_MAX}A"
            self.current = current

        if phase is not None:
            if not (PHASE_MIN <= phase <= PHASE_MAX):
                return f"Phase must be between {PHASE_MIN} and {PHASE_MAX}"
            self.phase = phase

        return None

    @property
    def power(self) -> float:
        """
        Calculate the theoretical maximum power in watts.

        Power is calculated as: P = V × I × phases

        Returns:
            Power capacity in watts (W).
        """
        return self.voltage * self.current * self.phase

    def plug_in(self) -> Optional[str]:
        """
        Simulate an EV being plugged into the connector.

        Sets is_plugged_in to True and transitions from AVAILABLE
        to PREPARING state. Does nothing if already plugged in.

        Returns:
            None on success, error string if transition is invalid.
        """
        if self.is_plugged_in:
            return None  # Already plugged in, no-op
        if self._status in (ConnectorState.FAULTED, ConnectorState.UNAVAILABLE):
            return f"Invalid transition: {self._status.value} + plug_in"
        self.is_plugged_in = True
        return self._transition("plug_in")

    def unplug(self) -> Optional[str]:
        """
        Simulate an EV being unplugged from the connector.

        Sets is_plugged_in to False, clears the id_tag, and restores
        the persistent status (handles UNAVAILABLE/FAULTED states).

        Returns:
            None on success, error string if not plugged in.
        """
        if not self.is_plugged_in:
            return "Cannot unplug: not plugged in"
        self.is_plugged_in = False
        self.id_tag = None
        self.status = self._persistent_status
        return None

    def start_charging(self) -> Optional[str]:
        """
        Transition the connector to CHARGING state.

        Only transitions if an EV is currently plugged in.
        Called by Engine when a charging session begins.

        Returns:
            None on success, error string if transition is invalid.
        """
        if not self.is_plugged_in:
            return "Cannot start charging: not plugged in"
        return self._transition("start_charging")

    def stop_charging(self) -> Optional[str]:
        """
        Stop the charging process and transition state.

        Transitions to FINISHING if plugged in, or AVAILABLE if unplugged.
        Called by Engine when a charging session ends.

        Returns:
            None on success, error string if transition is invalid.
        """
        error = self._transition("stop_charging")
        if error:
            return error
        # If unplugged during charging (race), go to AVAILABLE
        if not self.is_plugged_in:
            self.status = ConnectorState.AVAILABLE
        return None

    def suspend_ev(self) -> Optional[str]:
        """
        Manually suspend charging from the EV side.

        Transitions from CHARGING to SUSPENDED_EV state.
        Only valid when the connector is actively charging.

        Returns:
            None on success, error string if transition is invalid.
        """
        return self._transition("suspend_ev")

    def resume_charging(self) -> Optional[str]:
        """
        Resume charging after EV suspension.

        Transitions from SUSPENDED_EV back to CHARGING state.
        Only valid when the connector is in SUSPENDED_EV state.

        Returns:
            None on success, error string if transition is invalid.
        """
        return self._transition("resume")

    def handle_max_charge_reached(self, connector_id: int) -> None:
        """
        Handle event when EV battery reaches maximum charge.

        Transitions to SUSPENDED_EV state to indicate the EV has
        stopped accepting charge.

        Args:
            connector_id: ID of the connector that reached max charge.
        """
        if self.id == connector_id:
            self.status = ConnectorState.SUSPENDED_EV

    def handle_session_started(self, connector_id: int) -> None:
        """
        Handle event when a charging session starts.

        Transitions this connector to CHARGING state if the event
        is for this connector.

        Args:
            connector_id: ID of the connector starting the session.
        """
        if self.id == connector_id:
            self.start_charging()

    def handle_session_stopped(self, connector_id: int) -> None:
        """
        Handle event when a charging session stops.

        Stops charging on this connector if the event is for this connector.

        Args:
            connector_id: ID of the connector stopping the session.
        """
        if self.id == connector_id:
            self.stop_charging()

