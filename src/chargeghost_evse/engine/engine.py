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
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Optional

from chargeghost_evse.engine.connector import Connector, ConnectorState
from chargeghost_evse.engine.energy_meter import EnergyMeter
from chargeghost_evse.engine.reservation import Reservation
from chargeghost_evse.engine.session import Session
from chargeghost_evse.util.event import Event
from chargeghost_evse.util.subscriber import Subscriber

if TYPE_CHECKING:
    from chargeghost_evse.devtools.fault_manager import FaultManager


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
    - Multi-EVSE mode for parallel sessions on each connector

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
        session: Currently active charging session, or None (single-EVSE mode).
        last_stopped_session: Details of the most recently stopped session.
        energy_meter: Cumulative energy meter instance (single-EVSE mode).
        multi_evse_mode: Whether each connector operates as independent EVSE.
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

    def __init__(self, multi_evse_mode: bool = False) -> None:
        """
        Initialize the EVSE simulation engine.

        Sets up empty connector collection, energy meter(s), command queue,
        and event emitters. The engine starts with no active session.

        Args:
            multi_evse_mode: If True, each connector operates as an independent
                EVSE allowing parallel charging sessions. If False (default),
                only one session can be active at a time (single-EVSE mode).
        """
        super().__init__()
        self.logger = logging.getLogger("chargeghost.engine")
        self._session_logger = logging.getLogger("chargeghost.engine.session")

        # Multi-EVSE mode flag
        self._multi_evse_mode: bool = multi_evse_mode

        # Session tracking: keyed by connector_id for both modes
        self._sessions: dict[int, Session] = {}
        self.last_stopped_session: Optional[dict] = None

        # Energy metering: per-connector in multi-EVSE mode, single global otherwise
        self._energy_meters: dict[int, EnergyMeter] = {}
        self._global_energy_meter: EnergyMeter = EnergyMeter()

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

        # Active reservation by connector
        self._reservations: dict[int, Reservation] = {}

        # Event emitters for state change notifications
        self.session_started: Event = Event()
        self.session_stopped: Event = Event()
        self.connector_status_changed: Event = Event()
        self.connector_parameters_changed: Event = Event()
        self.reservation_expired: Event = Event()

        # Injectable callback for external charging limits (e.g., ChargingProfileManager)
        # Signature: (connector_id: int, transaction_id: Optional[int]) -> Optional[float]
        self.get_limit: Optional[Callable[[int, Optional[int]], Optional[float]]] = None

        # Injectable fault manager for meter/state fault injection
        self._fault_manager: Optional["FaultManager"] = None

        # EV battery capacity in Watt-hours (controls SoC calculation)
        self.ev_battery_capacity: float = 55000.0

    @property
    def multi_evse_mode(self) -> bool:
        """Check if multi-EVSE mode is enabled."""
        return self._multi_evse_mode

    @property
    def connectors(self) -> list[Connector]:
        """
        Get all connectors sorted by ID.

        Returns:
            List of Connector instances in ascending ID order.
        """
        return [self._connectors[cid] for cid in sorted(self._connectors.keys())]

    @property
    def session(self) -> Optional[Session]:
        """
        Get the currently active charging session (backward compatible).

        In single-EVSE mode, returns the active session.
        In multi-EVSE mode, returns the first session if any (for compatibility).

        Returns:
            Session instance, or None if no session.
        """
        sessions = list(self._sessions.values())
        return sessions[0] if sessions else None

    @property
    def energy_meter(self) -> EnergyMeter:
        """
        Get the global energy meter (backward compatible, single-EVSE mode).

        In multi-EVSE mode, use get_energy_meter(connector_id) instead.

        Returns:
            Global EnergyMeter instance.
        """
        return self._global_energy_meter

    def get_session(self, connector_id: int) -> Optional[Session]:
        """
        Get the session for a specific connector.

        Args:
            connector_id: ID of the connector to look up.

        Returns:
            Session instance, or None if not found.
        """
        return self._sessions.get(connector_id)

    def get_energy_meter(self, connector_id: int) -> EnergyMeter:
        """
        Get energy meter for a specific connector.

        In multi-EVSE mode, returns the per-connector meter.
        In single-EVSE mode, returns the global meter.

        Args:
            connector_id: ID of the connector.

        Returns:
            EnergyMeter instance for the connector.
        """
        if self._multi_evse_mode:
            if connector_id not in self._energy_meters:
                self._energy_meters[connector_id] = EnergyMeter()
            return self._energy_meters[connector_id]
        return self._global_energy_meter

    def _has_active_session(self, connector_id: int) -> bool:
        """
        Check if a connector has an active session.

        Args:
            connector_id: ID of the connector to check.

        Returns:
            True if the connector has an active session.
        """
        return connector_id in self._sessions

    def _log(self, message: str, *, level: int = logging.INFO, **extra) -> None:
        """
        Emit a log message via Python logging.

        Args:
            message: Log message text.
            level: Logging level (default INFO).
            **extra: Additional key/value pairs passed as log record extras.
        """
        self.logger.log(level, message, extra={"source": "engine", **extra})

    def set_fault_manager(self, fault_manager: "FaultManager") -> None:
        """
        Inject a FaultManager for meter and state fault injection.

        Args:
            fault_manager: FaultManager instance to use for fault checks.
        """
        self._fault_manager = fault_manager

    def set_battery_capacity(self, capacity_kwh: float) -> None:
        """
        Set the EV battery capacity used as the default max_energy for sessions.

        Args:
            capacity_kwh: Battery capacity in kilowatt-hours (kWh).
        """
        self.ev_battery_capacity = capacity_kwh * 1000.0

    def _get_fault_config_param(self, fault_id: str, key: str, default: Any) -> Any:
        if self._fault_manager is None:
            return default
        state = self._fault_manager.peek(fault_id)
        if state and state.config and key in state.config.parameters:
            return state.config.parameters[key]
        return default

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
        if self._has_active_session(connector_id):
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

    def get_reservation(self, connector_id: int) -> Optional[Reservation]:
        """
        Get the active reservation for a connector, if any.

        Args:
            connector_id: ID of the connector to inspect.

        Returns:
            Reservation if one is active, None otherwise.
        """
        self._expire_reservations()
        return self._reservations.get(connector_id)

    def reserve_connector(
        self,
        connector_id: int,
        reservation_id: int,
        id_tag: str,
        expiry_date: datetime,
        parent_id_tag: Optional[str] = None,
    ) -> str:
        """
        Reserve a connector for a future charging session.

        Returns:
            accepted, occupied, faulted, unavailable, or rejected.
        """
        self._expire_reservations()

        connector = self._connectors.get(connector_id)
        if connector is None:
            return "rejected"
        if connector.status == ConnectorState.FAULTED:
            return "faulted"
        if connector.status == ConnectorState.UNAVAILABLE:
            return "unavailable"
        if self._has_active_session(connector_id):
            return "occupied"
        if connector.is_plugged_in:
            return "occupied"
        if any(
            reservation.reservation_id == reservation_id
            for reservation in self._reservations.values()
        ):
            return "rejected"
        if connector_id in self._reservations:
            return "occupied"

        self._reservations[connector_id] = Reservation(
            reservation_id=reservation_id,
            connector_id=connector_id,
            id_tag=id_tag,
            expiry_date=expiry_date,
            parent_id_tag=parent_id_tag,
        )
        connector.set_reserved()
        return "accepted"

    def cancel_reservation(self, reservation_id: int) -> str:
        """
        Cancel a reservation by reservation ID.

        Returns:
            accepted if a reservation was removed, rejected otherwise.
        """
        self._expire_reservations()

        for connector_id, reservation in list(self._reservations.items()):
            if reservation.reservation_id != reservation_id:
                continue
            del self._reservations[connector_id]
            connector = self._connectors.get(connector_id)
            if connector is not None:
                connector.clear_reservation()
            return "accepted"

        return "rejected"

    def _expire_reservations(self) -> None:
        """
        Remove reservations that have passed their expiry time.
        """
        if not self._reservations:
            return

        now = datetime.now(timezone.utc)
        expired_items = [
            (connector_id, reservation)
            for connector_id, reservation in self._reservations.items()
            if reservation.is_expired(now)
        ]

        for connector_id, reservation in expired_items:
            del self._reservations[connector_id]
            connector = self._connectors.get(connector_id)
            if connector is not None:
                connector.clear_reservation()
            self.reservation_expired.emit(
                reservation_id=reservation.reservation_id,
                connector_id=connector_id,
            )

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
        if self._fault_manager is not None:
            flap = self._fault_manager.consume_if_active("status_flap")
            if flap.triggered:
                flap_count = self._get_fault_config_param(
                    "status_flap", "flap_count", 2
                )
                self._log(
                    f"Fault: status_flap — emitting {flap_count} flap cycles",
                    level=logging.DEBUG,
                    fault_id="status_flap",
                )
                for _ in range(flap_count):
                    self.connector_status_changed.emit(
                        connector_id=connector_id,
                        status=ConnectorState.FAULTED,
                    )
                    self.connector_status_changed.emit(
                        connector_id=connector_id,
                        status=status,
                    )

        self.connector_status_changed.emit(connector_id=connector_id, status=status)

        # Process pending remote start when EV plugs in
        if status == ConnectorState.PREPARING:
            pending = self._pending_remote_starts.get(connector_id)
            if pending:
                if time.monotonic() < pending["expiry"]:
                    self._log(
                        f"Executing pending RemoteStart for connector {connector_id}"
                    )
                    self.start_session(
                        connector_id=connector_id,
                        transaction_id=pending["transaction_id"],
                        max_energy=pending["max_energy"],
                        id_tag=pending["id_tag"],
                        remote_start_charging_profile=pending.get("charging_profile"),
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

        In single-EVSE mode, enforces the single-plug-in policy: any other
        currently plugged-in connector is automatically unplugged before the
        target connector is plugged in.

        In multi-EVSE mode, multiple EVs can be plugged in simultaneously.

        Args:
            connector_id: ID of the connector to plug into.
        """
        self._expire_reservations()

        # Auto-unplug any other plugged-in connector (single plug-in policy)
        # Skip this in multi-EVSE mode to allow parallel sessions
        if not self._multi_evse_mode:
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
        self._expire_reservations()

        connector = self._connectors.get(connector_id)
        if connector:
            connector.unplug()
            # Stop active session if unplugged
            if self._has_active_session(connector_id):
                self.stop_session(connector_id=connector_id)

    def start_session(
        self,
        connector_id: int,
        transaction_id: int,
        max_energy: Optional[float] = None,
        id_tag: Optional[str] = None,
        timeout: Optional[float] = None,
        remote_start_charging_profile: Optional[Any] = None,
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
                Defaults to the engine's ev_battery_capacity.
            id_tag: Authorization identifier for the session.
            timeout: Optional timeout in seconds to wait for plug-in.
                If None or 0, fails immediately if not plugged in.
            remote_start_charging_profile: Optional deferred charging profile
                from RemoteStartTransaction.

        Note:
            In single-EVSE mode, only one session can be active at a time.
            In multi-EVSE mode, each connector can have its own session.
        """
        if max_energy is None:
            max_energy = self.ev_battery_capacity
        self._expire_reservations()

        connector = self._connectors.get(connector_id)
        if connector is None:
            self._log(
                f"Error: Connector {connector_id} not found.", level=logging.ERROR
            )
            return

        reservation = self._reservations.get(connector_id)
        effective_id_tag = id_tag or connector.id_tag
        if reservation is not None:
            if effective_id_tag not in (reservation.id_tag, reservation.parent_id_tag):
                self._log(
                    f"Error: Connector {connector_id} is reserved for a different id_tag.",
                    level=logging.ERROR,
                )
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
                    "charging_profile": remote_start_charging_profile,
                    "expiry": time.monotonic() + timeout,
                }
            else:
                self._log(
                    f"Error: Connector {connector_id} is not plugged in.",
                    level=logging.ERROR,
                )
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

        # Enforce session constraints based on mode
        if self._multi_evse_mode:
            # In multi-EVSE mode, only block if this connector already has a session
            if connector_id in self._sessions:
                self._log(
                    f"Error: Session already active on connector {connector_id}.",
                    level=logging.ERROR,
                )
                return
        else:
            # In single-EVSE mode, block if any session is active
            if self._sessions:
                active_connector = list(self._sessions.keys())[0]
                self._log(
                    f"Error: Session already active on connector {active_connector}.",
                    level=logging.ERROR,
                )
                return

        if reservation is not None:
            self._reservations.pop(connector_id, None)
            connector.clear_reservation()

        # Create and wire up the session
        session = Session(
            transaction_id=transaction_id,
            connector_id=connector_id,
            max_energy=max_energy,
            id_tag=effective_id_tag,
            remote_start_charging_profile=remote_start_charging_profile,
            reservation_id=reservation.reservation_id if reservation else None,
        )

        # Get the appropriate energy meter
        meter = self.get_energy_meter(connector_id)

        # Connect session to energy meter for energy delivery tracking
        session.subscribe_to(meter.energy_consumed, session.process_energy_delivery)

        # Connect energy meter to session for max charge detection
        meter.subscribe_to(
            session.ev_max_charge_reached,
            meter.handle_max_charge_reached,
        )

        # Connect connector to session for status updates
        connector.subscribe_to(
            session.ev_max_charge_reached,
            connector.handle_max_charge_reached,
        )

        # Store the session
        self._sessions[connector_id] = session

        # Start charging
        meter.is_charging = True
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
        if connector is None:
            return
        session = self.get_session(connector_id)
        if session is None:
            return
        error = connector.suspend_ev()
        if error:
            self._log(
                f"[yellow]Engine:[/yellow] Cannot suspend connector {connector_id}: {error}",
                level=logging.ERROR,
            )
            return
        meter = self.get_energy_meter(connector_id)
        meter.is_charging = False
        self._log(f"[yellow]Engine:[/yellow] Connector {connector_id} suspended (EV)")

    def resume_charging(self, connector_id: int) -> None:
        """
        Resume charging on a connector after EV-side suspension.

        Resumes energy accumulation and transitions the connector back
        to CHARGING state.

        Args:
            connector_id: ID of the connector to resume.
        """
        connector = self._connectors.get(connector_id)
        if connector is None:
            return
        session = self.get_session(connector_id)
        if session is None:
            return
        error = connector.resume_charging()
        if error:
            self._log(
                f"[yellow]Engine:[/yellow] Cannot resume connector {connector_id}: {error}",
                level=logging.ERROR,
            )
            return
        meter = self.get_energy_meter(connector_id)
        meter.is_charging = True
        self._log(f"[green]Engine:[/green] Connector {connector_id} resumed charging")

    def set_connector_availability(
        self, connector_id: int, availability_type: str
    ) -> str:
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
            if self._has_active_session(cid):
                self._pending_availability_changes[cid] = availability_type
                scheduled = True
            else:
                self._apply_connector_availability(cid, availability_type)

        return "scheduled" if scheduled else "accepted"

    def _apply_connector_availability(
        self, connector_id: int, availability_type: str
    ) -> None:
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

    def stop_session(
        self,
        connector_id: Optional[int] = None,
        reason: str = "Local",
    ) -> None:
        """
        Stop the active charging session on a connector.

        Records session details in last_stopped_session for OCPP
        StopTransaction messages and cleans up all subscriptions.

        Args:
            connector_id: ID of the connector to stop the session on.
                If None, stops any active session (single-EVSE behavior).
            reason: Reason for stopping. Defaults to "Local".
                Common values: "Local", "Remote", "EVDisconnected", "HardReset", "SoftReset"
        """
        # Find session to stop
        if connector_id is None:
            if self._sessions:
                connector_id = list(self._sessions.keys())[0]
            else:
                return

        session = self._sessions.pop(connector_id, None)
        if session is None:
            return

        connector = self._connectors.get(connector_id)
        meter = self.get_energy_meter(connector_id)

        # Store session details for StopTransaction
        self.last_stopped_session = {
            "transaction_id": session.transaction_id,
            "connector_id": connector_id,
            "energy_charged": session.energy_charged,
            "id_tag": session.id_tag,
            "meter_stop": meter.get_meter_reading(),
            "reason": reason,
            "meter_history": session.get_meter_history(),
            "reservation_id": session.reservation_id,
        }

        # Clean up subscriptions
        meter.unsubscribe_from(session.ev_max_charge_reached)
        if connector:
            connector.unsubscribe_from(session.ev_max_charge_reached)
        session.unsubscribe_all()

        self._session_logger.debug(
            f"Session time [s]: {time.time() - session.start_time}",
            extra={"source": "engine"},
        )
        self.session_stopped.emit(connector_id=connector_id)
        meter.is_charging = False

        # Clean up per-connector meter in multi-EVSE mode
        if self._multi_evse_mode and connector_id in self._energy_meters:
            del self._energy_meters[connector_id]

        # Apply any deferred ChangeAvailability for this connector
        if connector_id in self._pending_availability_changes:
            availability_type = self._pending_availability_changes.pop(connector_id)
            self._apply_connector_availability(connector_id, availability_type)
            self._log(
                f"[yellow]Engine:[/yellow] Applied deferred availability change to "
                f"{availability_type} for connector {connector_id}"
            )

    def simulate(self, interval_seconds: float) -> None:
        """
        Run one simulation step.

        Processes pending commands and updates energy metering for all active
        charging sessions. Respects charging limits from the get_limit callback
        if configured.

        Args:
            interval_seconds: Time elapsed since last simulation step.
        """
        self._expire_reservations()
        self._process_commands()

        # Process all active sessions (single or multi-EVSE)
        for cid in list(self._sessions.keys()):
            session = self._sessions[cid]
            connector = self._connectors.get(cid)
            meter = self.get_energy_meter(cid)

            if connector is None or meter is None:
                continue

            if not meter.is_charging:
                continue

            # Apply charging limit if configured (e.g., from ChargingProfileManager)
            effective_current = connector.current
            if self.get_limit is not None:
                limit = self.get_limit(cid, session.transaction_id)
                if limit is not None and limit >= 0:
                    effective_current = min(connector.current, limit)

            # Reflect EVSE-side suspension in connector state when limit drops to 0
            if effective_current == 0 and connector.status == ConnectorState.CHARGING:
                connector.suspend_evse()
            elif (
                effective_current > 0
                and connector.status == ConnectorState.SUSPENDED_EVSE
            ):
                connector.resume_charging()

            # Update energy meter with current parameters
            if self._fault_manager is not None:
                frozen = self._fault_manager.consume_if_active("frozen_meter")
                if frozen.triggered:
                    self._log(
                        "Fault: frozen_meter — skipping meter.update()",
                        level=logging.DEBUG,
                        fault_id="frozen_meter",
                    )
                else:
                    meter.update(
                        connector.voltage,
                        effective_current,
                        connector.phase,
                        interval_seconds=interval_seconds,
                    )
            else:
                meter.update(
                    connector.voltage,
                    effective_current,
                    connector.phase,
                    interval_seconds=interval_seconds,
                )

            if self._fault_manager is not None:
                jumped = self._fault_manager.consume_if_active("meter_jump")
                if jumped.triggered:
                    amount_kwh = self._get_fault_config_param(
                        "meter_jump", "amount_kwh", 10.0
                    )
                    amount_wh = amount_kwh * 1000.0
                    meter.consume_energy(amount_wh)
                    self._log(
                        f"Fault: meter_jump — injected {amount_wh:.1f} Wh",
                        level=logging.DEBUG,
                        fault_id="meter_jump",
                    )

            reading = meter.get_meter_reading()

            if self._fault_manager is not None:
                reset = self._fault_manager.consume_if_active("meter_reset")
                if reset.triggered:
                    self._log(
                        f"Fault: meter_reset — reporting 0.0 instead of {reading:.3f}",
                        level=logging.DEBUG,
                        fault_id="meter_reset",
                    )
                    reading = 0.0

            self.event_queue.append(reading)

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
                STOP: connector_id, reason
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
                max_energy=command.get("max_energy"),
                id_tag=command.get("id_tag"),
                timeout=command.get("timeout"),
                remote_start_charging_profile=command.get("charging_profile"),
            )
        elif action == "STOP":
            self.stop_session(
                connector_id=connector_id,
                reason=command.get("reason", "Remote"),
            )
        elif action == "RESET":
            self._handle_reset(command.get("type", "Soft"))
        elif action == "PLUG_IN":
            if connector_id is not None:
                self.plug_in(connector_id)
        elif action == "UNPLUG":
            if connector_id is not None:
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

        # Stop all active sessions
        if self._sessions:
            for cid in list(self._sessions.keys()):
                self._log(f"Stopping active session on connector {cid} for {reason}.")
                self.stop_session(connector_id=cid, reason=reason)
        else:
            self._log(f"Processing {reason} with no active session.")

    def get_session_info(self) -> str:
        """
        Get a formatted string with current session information.

        In single-EVSE mode, returns info for the active session.
        In multi-EVSE mode, returns info for all active sessions.

        Returns:
            Multi-line string with session details, or empty string
            if no session is active.
        """
        if not self._sessions:
            return ""

        lines = []
        for cid, sess in self._sessions.items():
            meter = self.get_energy_meter(cid)
            lines.append(
                f"Connector {cid}:\n"
                f"  - transaction_id: {sess.transaction_id}\n"
                f"  - energy_charged: {sess.energy_charged:.3f}\n"
                f"  - state_of_charge: {sess.state_of_charge:.2f}\n"
                f"  - max_energy: {sess.max_energy:.3f}\n"
                f"  - is_charging: {meter.is_charging}"
            )

        return "\n".join(lines)
