import queue
import time
from collections import deque
from typing import TYPE_CHECKING, Optional
from chargeghost_evse.engine.connector import Connector, ConnectorState
from chargeghost_evse.engine.energy_meter import EnergyMeter
from chargeghost_evse.engine.session import Session
from chargeghost_evse.util.event import Event
from chargeghost_evse.util.subscriber import Subscriber

if TYPE_CHECKING:
    from chargeghost_evse.engine.connector import ConnectorState


class Engine(Subscriber):
    def __init__(self):
        super().__init__()
        self.session: Optional[Session] = None
        self.last_stopped_session: Optional[dict] = None
        self.energy_meter: EnergyMeter = EnergyMeter()
        self.command_queue: queue.Queue = queue.Queue()
        self.event_queue: deque[float] = deque(maxlen=1000)
        self._connectors: dict[int, Connector] = {}
        self._next_connector_id: int = 1
        self.last_update_time: Optional[float] = None
        self.last_display_time: Optional[float] = None

        self._pending_remote_starts: dict[int, dict] = {}

        self.session_started: Event = Event()
        self.session_stopped: Event = Event()
        self.connector_status_changed: Event = Event()
        self.connector_parameters_changed: Event = Event()
        self.on_log: Event = Event()

        self.simulation_time_step: float = 0.1
        self.display_time_step: float = 1.0

    @property
    def connectors(self) -> list[Connector]:
        return [self._connectors[cid] for cid in sorted(self._connectors.keys())]

    def _log(self, message: str, **kwargs):
        self.on_log.emit(message=message, **kwargs)

    def add_connector(
        self, voltage: float = 230.0, current: float = 32.0, phase: int = 1
    ) -> Connector:
        connector_id = self._next_connector_id
        self._next_connector_id += 1
        connector = Connector(connector_id, voltage, current, phase)

        connector.subscribe_to(self.session_started, connector.handle_session_started)
        connector.subscribe_to(self.session_stopped, connector.handle_session_stopped)
        connector.on_status_change.subscribe(self.handle_connector_status_change)

        self._connectors[connector_id] = connector
        return connector

    def remove_connector(self, connector_id: int) -> None:
        if connector_id in self._connectors:
            if self.session and self.session.connector_id == connector_id:
                return
            self._connectors[connector_id].unsubscribe_all()
            del self._connectors[connector_id]

    def update_connector(
        self,
        connector_id: int,
        voltage: Optional[float] = None,
        current: Optional[float] = None,
        phase: Optional[int] = None,
    ) -> Optional[str]:
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
        return self._connectors.get(connector_id)

    def handle_connector_status_change(
        self, connector_id: int, status: "ConnectorState"
    ) -> None:
        self.connector_status_changed.emit(connector_id=connector_id, status=status)

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
                    self._log(f"Pending RemoteStart for connector {connector_id} expired.")
                
                # Cleanup handled or expired request
                if connector_id in self._pending_remote_starts:
                    del self._pending_remote_starts[connector_id]

    def plug_in(self, connector_id: int) -> None:
        connector = self._connectors.get(connector_id)
        if connector:
            connector.plug_in()

    def unplug(self, connector_id: int) -> None:
        connector = self._connectors.get(connector_id)
        if connector:
            connector.unplug()
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
        connector = self._connectors.get(connector_id)
        if connector is None:
            self._log(f"Error: Connector {connector_id} not found.")
            return

        if not connector.is_plugged_in:
            if timeout and timeout > 0:
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
                self._log(f"Error: Connector {connector_id} is not plugged in.")
            return

        # If we are starting a session, clear any pending start for this connector
        if connector_id in self._pending_remote_starts:
            del self._pending_remote_starts[connector_id]

        if connector.status not in (ConnectorState.AVAILABLE, ConnectorState.PREPARING):
            self._log(
                f"Error: Connector {connector_id} is in status {connector.status.value} "
                "and cannot start a session."
            )
            return

        if self.session:
            self._log(
                f"Error: Session already active on connector {self.session.connector_id}."
            )
            return

        self.session = Session(
            transaction_id=transaction_id,
            connector_id=connector_id,
            max_energy=max_energy,
            id_tag=id_tag or connector.id_tag,
        )
        self.session.subscribe_to(
            self.energy_meter.energy_consumed, self.session.process_energy_delivery
        )
        self.energy_meter.subscribe_to(
            self.session.ev_max_charge_reached,
            self.energy_meter.handle_max_charge_reached,
        )
        connector.subscribe_to(
            self.session.ev_max_charge_reached,
            connector.handle_max_charge_reached,
        )
        self.energy_meter.is_charging = True
        self.last_update_time = time.monotonic()
        self.session_started.emit(connector_id=connector_id)

    def stop_session(self, reason: str = "Local"):
        if self.session:
            connector_id = self.session.connector_id
            connector = self._connectors.get(connector_id)
            self.last_stopped_session = {
                "transaction_id": self.session.transaction_id,
                "connector_id": connector_id,
                "energy_charged": self.session.energy_charged,
                "id_tag": self.session.id_tag,
                "meter_stop": self.energy_meter.get_meter_reading(),
                "reason": reason,
            }
            self.energy_meter.unsubscribe_from(self.session.ev_max_charge_reached)
            if connector:
                connector.unsubscribe_from(self.session.ev_max_charge_reached)
            self.session.unsubscribe_all()
            self._log(f"Session time [s]: {time.monotonic() - self.session.start_time}")
            self.session_stopped.emit(connector_id=connector_id)
            self.session = None
            self.energy_meter.is_charging = False

    def simulate(self, interval_seconds: float):
        self._process_commands()
        if self.session and self.energy_meter.is_charging:
            connector = self._connectors.get(self.session.connector_id)
            if connector is None:
                return

            self.energy_meter.update(
                connector.voltage,
                connector.current,
                connector.phase,
                interval_seconds=interval_seconds,
            )
            self.event_queue.append(self.energy_meter.get_meter_reading())

    def _process_commands(self):
        try:
            while True:
                command = self.command_queue.get_nowait()
                self._handle_command(command)
        except queue.Empty:
            pass

    def _handle_command(self, command):
        action = command.get("action")
        connector_id = command.get("connector_id")

        if action == "START":
            # If connector_id is not provided or 0, try to find an available connector
            if not connector_id:
                for conn in self.connectors:
                    if conn.status == ConnectorState.AVAILABLE:
                        connector_id = conn.id
                        break
                else:
                    self._log("RemoteStartTransaction failed: No available connectors.")
                    return

            self.start_session(
                connector_id=connector_id,
                transaction_id=command.get("transaction_id", 0),
                max_energy=command.get("max_energy", 55000.0),
                id_tag=command.get("id_tag"),
                timeout=command.get("timeout"),
            )
        elif action == "STOP":
            self.stop_session(reason=command.get("reason", "Remote"))
        elif action == "PLUG_IN":
            self.plug_in(connector_id)
        elif action == "UNPLUG":
            self.unplug(connector_id)
        elif action:
            self._log(f"Warning: Unknown command action: {action}")

    def get_session_info(self) -> str:
        if not self.session:
            return ""

        return f"""\nSession Info:
	- transaction_id: {self.session.transaction_id},
	- connector_id: {self.session.connector_id},
	- energy_charged: {self.session.energy_charged:.3f},
	- state_of_charge: {self.session.state_of_charge:.2f},
	- max_energy: {self.session.max_energy:.3f},
	- is_charging: {self.energy_meter.is_charging}
		"""
