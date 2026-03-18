"""
EVSE Simulation Engine Module.

This module provides the core simulation engine for the ChargeGhost EVSE
(Electric Vehicle Supply Equipment) simulator. The engine manages connectors,
charging sessions, energy metering, and the simulation loop.

The engine coordinates between:
- Connectors: Physical charging interface simulation
- Sessions: Active charging transaction tracking
- EnergyMeter: Cumulative energy consumption measurement
- Command Queue: Thread-safe command processing for OCPP operations

Classes:
    Engine: Main simulation engine coordinating all EVSE components.
"""

import logging
import queue
import time
from collections import deque
from typing import Callable, Optional

from chargeghost_evse.engine.connector import Connector, ConnectorState
from chargeghost_evse.engine.energy_meter import EnergyMeter
from chargeghost_evse.engine.session import Session
from chargeghost_evse.util.event import Event
from chargeghost_evse.util.subscriber import Subscriber


class Engine(Subscriber):
    """
    Core simulation engine for EVSE charging operations.

    The Engine manages the overall state of the EVSE simulator, including
    connector management, session lifecycle, energy metering, and command
    processing. It provides an event-driven architecture for UI and OCPP
    integration.

    The engine supports:
    - Multiple connector management (add/remove/configure)
    - Charging session lifecycle (start/stop/suspend)
    - Real-time energy simulation with configurable limits
    - Thread-safe command queue for async operations
    - Pending remote start handling with timeout

    Events:
        session_started: Emitted when a charging session begins.
            Parameters: connector_id (int)
        session_stopped: Emitted when a charging session ends.
            Parameters: connector_id (int)
        connector_status_changed: Emitted when connector status changes.
            Parameters: connector_id (int), status (ConnectorState)
        connector_parameters_changed: Emitted when connector params change.
            Parameters: connector_id (int), voltage (float), current (float), phase (int)

    Attributes:
        session: Currently active charging session, or None.
        last_stopped_session: Details of the most recently stopped session.
        energy_meter: Cumulative energy meter instance.
        command_queue: Thread-safe queue for async commands.
        event_queue: Recent meter readings for UI updates.
        get_limit: Optional callback to get charging current limits.

    Example:
        >>> engine = Engine()
        >>> connector = engine.add_connector(voltage=230.0, current=32.0, phase=3)
        >>> engine.plug_in(connector_id=1)
        >>> engine.start_session(connector_id=1, transaction_id=12345)
        >>> engine.simulate(interval_seconds=0.1)
    """

    def __init__(self) -> None:
        """
        Initialize the EVSE simulation engine.

        Sets up empty connector collection, energy meter, command queue,
        and event emitters. The engine starts with no active session.
        """
        super().__init__()
        self.logger = logging.getLogger("chargeghost.engine")
        self._session_logger = logging.getLogger("chargeghost.engine.session")

        # Current and previous session tracking
        self.session: Optional[Session] = None
        self.last_stopped_session: Optional[dict] = None

        # Energy metering (cumulative across all sessions)
        self.energy_meter: EnergyMeter = EnergyMeter()

        # Thread-safe command queue for OCPP operations
        self.command_queue: queue.Queue = queue.Queue()

        # Recent meter readings for UI charts (rolling buffer)
        self.event_queue: deque[float] = deque(maxlen=1000)

        # Connector management
        self._connectors: dict[int, Connector] = {}
        self._next_connector_id: int = 1

        # Pending remote start requests waiting for plug-in
        # Key: connector_id, Value: request details dict
        self._pending_remote_starts: dict[int, dict] = {}

        # Pending ChangeAvailability changes deferred until active transaction ends
        # Key: connector_id, Value: availability_type ("Operative" | "Inoperative")
        self._pending_availability_changes: dict[int, str] = {}

        # Event emitters for state change notifications
        self.session_started: Event = Event()
        self.session_stopped: Event = Event()
        self.connector_status_changed: Event = Event()
        self.connector_parameters_changed: Event = Event()

        # Injectable callback for external charging limits (e.g., ChargingProfileManager)
        # Signature: (connector_id: int, transaction_id: Optional[int]) -> Optional[float]
        self.get_limit: Optional[Callable[[int, Optional[int]], Optional[float]]] = None

    @property
    def connectors(self) -> list[Connector]:
        """
        Get all connectors sorted by ID.

        Returns:
            List of Connector instances in ascending ID order.
        """
        return [self._connectors[cid] for cid in sorted(self._connectors.keys())]

    def _log(self, message: str, *, level: int = logging.INFO, **extra) -> None:
        """
        Emit a log message via Python logging.

        Args:
            message: Log message text.
            level: Logging level (default INFO).
            **extra: Additional key/value pairs passed as log record extras.
        """
        self.logger.log(level, message, extra={"source": "engine", **extra})

    def add_connector(
        self, voltage: float = 230.0, current: float = 32.0, phase: int = 1
    ) -> Connector:
        """
        Add a new connector to the EVSE.

        Creates a connector with the specified electrical parameters and
        subscribes it to session events. Connectors are assigned sequential IDs.

        Args:
            voltage: Operating voltage in volts. Defaults to 230.0V.
            current: Maximum current in amperes. Defaults to 32.0A.
            phase: Number of electrical phases. Defaults to 1.

        Returns:
            The newly created Connector instance.
        """
        connector_id = self._next_connector_id
        self._next_connector_id += 1
        connector = Connector(connector_id, voltage, current, phase)

        # Subscribe connector to session lifecycle events
        connector.subscribe_to(self.session_started, connector.handle_session_started)
        connector.subscribe_to(self.session_stopped, connector.handle_session_stopped)
        connector.on_status_change.subscribe(self.handle_connector_status_change)

        self._connectors[connector_id] = connector
        return connector

    def remove_connector(self, connector_id: int) -> None:
        """
        Remove a connector from the EVSE.

        Raises ValueError if this is the last connector, or if there is an
        active session on the specified connector.

        Args:
            connector_id: ID of the connector to remove.

        Raises:
            ValueError: If removing would leave zero connectors, or if the
                connector has an active charging session.
        """
        if len(self._connectors) <= 1:
            raise ValueError("Cannot remove the last connector")
        if connector_id not in self._connectors:
            raise ValueError(f"Connector {connector_id} not found")
        if self.session and self.session.connector_id == connector_id:
            raise ValueError("Cannot remove connector with active session")
        self._connectors[connector_id].unsubscribe_all()
        del self._connectors[connector_id]

    def update_connector(
        self,
        connector_id: int,
        voltage: Optional[float] = None,
        current: Optional[float] = None,
        phase: Optional[int] = None,
    ) -> Optional[str]:
        """
        Update electrical parameters for a connector.

        Args:
            connector_id: ID of the connector to update.
            voltage: New voltage in volts, or None to skip.
            current: New current in amperes, or None to skip.
            phase: New phase count, or None to skip.

        Returns:
            Error message string if validation fails, None on success.
        """
        connector = self._connectors.get(connector_id)
        if connector is None:
            return f"Connector {connector_id} not found"

        error = connector.set_parameters(voltage=voltage, current=current, phase=phase)
        if error:
            return error

        self.connector_parameters_changed.emit(
            connector_id=connector_id,
            voltage=connector.voltage,
            current=connector.current,
            phase=connector.phase,
        )
        return None

    def get_connector(self, connector_id: int) -> Optional[Connector]:
        """
        Get a connector by ID.

        Args:
            connector_id: ID of the connector to retrieve.

        Returns:
            Connector instance, or None if not found.
        """
        return self._connectors.get(connector_id)

    def handle_connector_status_change(
        self, connector_id: int, status: "ConnectorState"
    ) -> None:
        """
        Handle connector status change events.

        Forwards status changes to the connector_status_changed event.
        Also processes pending remote start requests when connector
        enters PREPARING state.

        Args:
            connector_id: ID of the connector that changed.
            status: New connector status.
        """
        self.connector_status_changed.emit(connector_id=connector_id, status=status)

        # Process pending remote start when EV plugs in
        if status == ConnectorState.PREPARING:
            pending = self._pending_remote_starts.get(connector_id)
            if pending:
                if time.monotonic() < pending["expiry"]:
                    self._log(f"Executing pending RemoteStart for connector {connector_id}")
                    self.start_session(
                        connector_id=connector_id,
                        transaction_id=pending["transaction_id"],
                        max_energy=pending["max_energy"],
                        id_tag=pending["id_tag"],
                    )
                else:
                    self._log(
                        f"Pending RemoteStart for connector {connector_id} expired.",
                        level=logging.WARNING,
                    )

                # Cleanup handled or expired request
                if connector_id in self._pending_remote_starts:
                    del self._pending_remote_starts[connector_id]

    def plug_in(self, connector_id: int) -> None:
        """
        Simulate an EV being plugged into a connector.

        Enforces the single-plug-in policy: any other currently plugged-in
        connector is automatically unplugged before the target connector is
        plugged in.

        Args:
            connector_id: ID of the connector to plug into.
        """
        # Auto-unplug any other plugged-in connector (single plug-in policy)
        for conn in self._connectors.values():
            if conn.is_plugged_in and conn.id != connector_id:
                self.unplug(conn.id)

        connector = self._connectors.get(connector_id)
        if connector:
            error = connector.plug_in()
            if error:
                self._log(
                    f"[yellow]Engine:[/yellow] Cannot plug in connector {connector_id}: {error}",
                    level=logging.ERROR,
                )

    def unplug(self, connector_id: int) -> None:
        """
        Simulate an EV being unplugged from a connector.

        If a session is active on this connector, it will be stopped.

        Args:
            connector_id: ID of the connector to unplug from.
        """
        connector = self._connectors.get(connector_id)
        if connector:
            connector.unplug()
            # Stop active session if unplugged
            if self.session is not None and self.session.connector_id == connector_id:
                self.stop_session()

    def start_session(
        self,
        connector_id: int,
        transaction_id: int,
        max_energy: float = 55000.0,
        id_tag: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        """
        Start a charging session on a connector.

        If the connector is not plugged in and timeout is specified,
        the start request will be queued as pending until the EV plugs
        in or the timeout expires.

        Args:
            connector_id: ID of the connector for the session.
            transaction_id: OCPP transaction identifier.
            max_energy: Maximum energy to deliver in Watt-hours (Wh).
                Defaults to 55000.0 (55 kWh).
            id_tag: Authorization identifier for the session.
            timeout: Optional timeout in seconds to wait for plug-in.
                If None or 0, fails immediately if not plugged in.

        Note:
            Only one session can be active at a time (single-session EVSE).
        """
        connector = self._connectors.get(connector_id)
        if connector is None:
            self._log(f"Error: Connector {connector_id} not found.", level=logging.ERROR)
            return

        # Handle unplugged connector
        if not connector.is_plugged_in:
            if timeout and timeout > 0:
                # Queue as pending remote start
                self._log(
                    f"Connector {connector_id} unplugged. Pending RemoteStart (timeout={timeout}s)."
                )
                self._pending_remote_starts[connector_id] = {
                    "transaction_id": transaction_id,
                    "max_energy": max_energy,
                    "id_tag": id_tag,
                    "expiry": time.monotonic() + timeout,
                }
            else:
                self._log(f"Error: Connector {connector_id} is not plugged in.", level=logging.ERROR)
            return

        # Clear any pending start for this connector
        if connector_id in self._pending_remote_starts:
            del self._pending_remote_starts[connector_id]

        # Validate connector state
        if connector.status not in (ConnectorState.AVAILABLE, ConnectorState.PREPARING):
            self._log(
                f"Error: Connector {connector_id} is in status {connector.status.value} "
                "and cannot start a session.",
                level=logging.ERROR,
            )
            return

        # Enforce single-session constraint
        if self.session:
            self._log(
                f"Error: Session already active on connector {self.session.connector_id}.",
                level=logging.ERROR,
            )
            return

        # Create and wire up the session
        self.session = Session(
            transaction_id=transaction_id,
            connector_id=connector_id,
            max_energy=max_energy,
            id_tag=id_tag or connector.id_tag,
        )

        # Connect session to energy meter for energy delivery tracking
        self.session.subscribe_to(
            self.energy_meter.energy_consumed, self.session.process_energy_delivery
        )

        # Connect energy meter to session for max charge detection
        self.energy_meter.subscribe_to(
            self.session.ev_max_charge_reached,
            self.energy_meter.handle_max_charge_reached,
        )

        # Connect connector to session for status updates
        connector.subscribe_to(
            self.session.ev_max_charge_reached,
            connector.handle_max_charge_reached,
        )

        # Start charging
        self.energy_meter.is_charging = True
        self.session_started.emit(connector_id=connector_id)

    def suspend_ev(self, connector_id: int) -> None:
        """
        Manually suspend charging on a connector (EV-side suspension).

        Pauses energy accumulation and transitions the connector to
        SUSPENDED_EV state.

        Args:
            connector_id: ID of the connector to suspend.
        """
        connector = self._connectors.get(connector_id)
        if connector and self.session and self.session.connector_id == connector_id:
            error = connector.suspend_ev()
            if error:
                self._log(
                    f"[yellow]Engine:[/yellow] Cannot suspend connector {connector_id}: {error}",
                    level=logging.ERROR,
                )
            if connector.status == ConnectorState.SUSPENDED_EV:
                self.energy_meter.is_charging = False
                self._log(
                    f"[yellow]Engine:[/yellow] Connector {connector_id} suspended (EV)"
                )

    def resume_charging(self, connector_id: int) -> None:
        """
        Resume charging on a connector after EV-side suspension.

        Resumes energy accumulation and transitions the connector back
        to CHARGING state.

        Args:
            connector_id: ID of the connector to resume.
        """
        connector = self._connectors.get(connector_id)
        if connector and self.session and self.session.connector_id == connector_id:
            error = connector.resume_charging()
            if error:
                self._log(
                    f"[yellow]Engine:[/yellow] Cannot resume connector {connector_id}: {error}",
                    level=logging.ERROR,
                )
            if connector.status == ConnectorState.CHARGING:
                self.energy_meter.is_charging = True
                self._log(
                    f"[green]Engine:[/green] Connector {connector_id} resumed charging"
                )

    def set_connector_availability(self, connector_id: int, availability_type: str) -> str:
        """
        Set one or all connectors to Operative or Inoperative.

        Called from the OCPP adapter's ChangeAvailability handler. Connectors
        with an active transaction get a deferred change (returns "scheduled");
        all others are changed immediately (returns "accepted").

        Args:
            connector_id: Target connector ID, or 0 for all connectors.
            availability_type: "Operative" or "Inoperative".

        Returns:
            "accepted" if all changes applied immediately,
            "scheduled" if any connector has a deferred change,
            "rejected" if the specific connector_id is unknown.
        """
        if connector_id == 0:
            target_ids = list(self._connectors.keys())
        else:
            if connector_id not in self._connectors:
                return "rejected"
            target_ids = [connector_id]

        scheduled = False
        for cid in target_ids:
            has_active_session = self.session is not None and self.session.connector_id == cid
            if has_active_session:
                self._pending_availability_changes[cid] = availability_type
                scheduled = True
            else:
                self._apply_connector_availability(cid, availability_type)

        return "scheduled" if scheduled else "accepted"

    def _apply_connector_availability(self, connector_id: int, availability_type: str) -> None:
        """
        Apply an availability change to a connector immediately.

        Args:
            connector_id: Target connector ID.
            availability_type: "Operative" or "Inoperative".
        """
        connector = self._connectors.get(connector_id)
        if connector is None:
            return
        if availability_type == "Inoperative":
            connector.set_unavailable()
        else:
            connector.set_operative()

    def stop_session(self, reason: str = "Local") -> None:
        """
        Stop the active charging session.

        Records session details in last_stopped_session for OCPP
        StopTransaction messages and cleans up all subscriptions.

        Args:
            reason: Reason for stopping. Defaults to "Local".
                Common values: "Local", "Remote", "EVDisconnected", "HardReset", "SoftReset"
        """
        if self.session:
            connector_id = self.session.connector_id
            connector = self._connectors.get(connector_id)

            # Store session details for StopTransaction
            self.last_stopped_session = {
                "transaction_id": self.session.transaction_id,
                "connector_id": connector_id,
                "energy_charged": self.session.energy_charged,
                "id_tag": self.session.id_tag,
                "meter_stop": self.energy_meter.get_meter_reading(),
                "reason": reason,
            }

            # Clean up subscriptions
            self.energy_meter.unsubscribe_from(self.session.ev_max_charge_reached)
            if connector:
                connector.unsubscribe_from(self.session.ev_max_charge_reached)
            self.session.unsubscribe_all()

            self._session_logger.debug(
                f"Session time [s]: {time.time() - self.session.start_time}",
                extra={"source": "engine"},
            )
            self.session_stopped.emit(connector_id=connector_id)
            self.session = None
            self.energy_meter.is_charging = False

            # Apply any deferred ChangeAvailability for this connector
            if connector_id in self._pending_availability_changes:
                availability_type = self._pending_availability_changes.pop(connector_id)
                self._apply_connector_availability(connector_id, availability_type)
                self._log(
                    f"[yellow]Engine:[/yellow] Applied deferred availability change to"
                    f" {availability_type} for connector {connector_id}"
                )

    def simulate(self, interval_seconds: float) -> None:
        """
        Run one simulation step.

        Processes pending commands and updates energy metering if
        a charging session is active. Respects charging limits from
        the get_limit callback if configured.

        Args:
            interval_seconds: Time elapsed since last simulation step.
        """
        self._process_commands()

        if self.session and self.energy_meter.is_charging:
            connector = self._connectors.get(self.session.connector_id)
            if connector is None:
                return

            # Apply charging limit if configured (e.g., from ChargingProfileManager)
            effective_current = connector.current
            if self.get_limit is not None:
                limit = self.get_limit(self.session.connector_id, self.session.transaction_id)
                if limit is not None and limit >= 0:
                    effective_current = min(connector.current, limit)

            # Reflect EVSE-side suspension in connector state when limit drops to 0
            if effective_current == 0 and connector.status == ConnectorState.CHARGING:
                connector.suspend_evse()
            elif effective_current > 0 and connector.status == ConnectorState.SUSPENDED_EVSE:
                connector.resume_charging()

            # Update energy meter with current parameters
            self.energy_meter.update(
                connector.voltage,
                effective_current,
                connector.phase,
                interval_seconds=interval_seconds,
            )

            # Record meter reading for UI charts
            self.event_queue.append(self.energy_meter.get_meter_reading())

    def _process_commands(self) -> None:
        """
        Process all pending commands from the command queue.

        Commands are processed in FIFO order until the queue is empty.
        This method is thread-safe for the command queue.
        """
        try:
            while True:
                command = self.command_queue.get_nowait()
                self._handle_command(command)
        except queue.Empty:
            pass

    def _handle_command(self, command: dict) -> None:
        """
        Handle a single command from the command queue.

        Supported commands:
        - START: Start a charging session
        - STOP: Stop the active session
        - PLUG_IN: Simulate EV plug-in
        - UNPLUG: Simulate EV unplug

        Args:
            command: Dictionary with 'action' key and action-specific parameters.
                START: connector_id, transaction_id, max_energy, id_tag, timeout
                STOP: reason
                PLUG_IN/UNPLUG: connector_id
        """
        action = command.get("action")
        connector_id = command.get("connector_id")

        if action == "START":
            # If connector_id is not provided or 0, find a suitable connector.
            # Prefer PREPARING (EV already plugged in) over AVAILABLE (pending plug-in).
            if not connector_id:
                chosen = None
                for conn in self.connectors:
                    if conn.status == ConnectorState.PREPARING:
                        chosen = conn
                        break
                    if conn.status == ConnectorState.AVAILABLE and chosen is None:
                        chosen = conn
                if chosen is None:
                    self._log("RemoteStartTransaction failed: No available connectors.")
                    return
                connector_id = chosen.id

            self.start_session(
                connector_id=connector_id,
                transaction_id=command.get("transaction_id", 0),
                max_energy=command.get("max_energy", 55000.0),
                id_tag=command.get("id_tag"),
                timeout=command.get("timeout"),
            )
        elif action == "STOP":
            self.stop_session(reason=command.get("reason", "Remote"))
        elif action == "RESET":
            self._handle_reset(command.get("type", "Soft"))
        elif action == "PLUG_IN":
            self.plug_in(connector_id)
        elif action == "UNPLUG":
            self.unplug(connector_id)
        elif action:
            self._log(f"Warning: Unknown command action: {action}")

    def _handle_reset(self, reset_type: str) -> None:
        """
        Apply a remotely requested reset to the engine state.

        Args:
            reset_type: Requested reset type ("Soft" or "Hard").
        """
        reason = "HardReset" if reset_type == "Hard" else "SoftReset"

        if self._pending_remote_starts:
            self._log(
                f"Clearing {len(self._pending_remote_starts)} pending RemoteStart request(s) for {reason}."
            )
            self._pending_remote_starts.clear()

        if self.session is not None:
            self._log(f"Stopping active session for {reason}.")
            self.stop_session(reason=reason)
        else:
            self._log(f"Processing {reason} with no active session.")

    def get_session_info(self) -> str:
        """
        Get a formatted string with current session information.

        Returns:
            Multi-line string with session details, or empty string
            if no session is active.
        """
        if not self.session:
            return ""

        return f"""Session Info:
	- transaction_id: {self.session.transaction_id},
	- connector_id: {self.session.connector_id},
	- energy_charged: {self.session.energy_charged:.3f},
	- state_of_charge: {self.session.state_of_charge:.2f},
	- max_energy: {self.session.max_energy:.3f},
	- is_charging: {self.energy_meter.is_charging}
		"""
