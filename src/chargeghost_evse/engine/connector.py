from chargeghost_evse.util.subscriber import Subscriber
from chargeghost_evse.util.event import Event
from typing import Optional
import enum


class ConnectorState(enum.Enum):
    AVAILABLE = "Available"
    PREPARING = "Preparing"
    CHARGING = "Charging"
    SUSPENDED_EVSE = "SuspendedEVSE"
    SUSPENDED_EV = "SuspendedEV"
    FINISHING = "Finishing"
    UNAVAILABLE = "Unavailable"
    FAULTED = "Faulted"


class Connector(Subscriber):
    def __init__(
        self, id: int, voltage: float = 230.0, current: float = 32.0, phase: int = 1
    ):
        super().__init__()
        self.id: int = id
        self.voltage: float = voltage
        self.current: float = current
        self.phase: int = phase

        self._status: ConnectorState = ConnectorState.AVAILABLE
        self.is_plugged_in: bool = False
        self.id_tag: Optional[str] = None

        self.on_status_change: Event = Event()

    @property
    def status(self) -> ConnectorState:
        return self._status

    @status.setter
    def status(self, new_status: ConnectorState) -> None:
        if self._status != new_status:
            self._status = new_status
            self.on_status_change.emit(connector_id=self.id, status=new_status)

    def plug_in(self) -> None:
        if not self.is_plugged_in:
            self.is_plugged_in = True
            if self.status == ConnectorState.AVAILABLE:
                self.status = ConnectorState.PREPARING

    def unplug(self) -> None:
        if self.is_plugged_in:
            self.is_plugged_in = False
            self.id_tag = None
            self.status = ConnectorState.AVAILABLE

    def authorize(self, id_tag: str) -> None:
        self.id_tag = id_tag
        # If we are preparing (plugged in) and now authorized, we might want to start charging
        # But typically the Engine orchestrates the StartTransaction which then sets Charging
        pass

    def start_charging(self) -> None:
        if self.is_plugged_in:
            self.status = ConnectorState.CHARGING

    def stop_charging(self) -> None:
        if self.status == ConnectorState.CHARGING:
            if self.is_plugged_in:
                self.status = ConnectorState.FINISHING
            else:
                self.status = ConnectorState.AVAILABLE

    def handle_max_charge_reached(self, connector_id: int) -> None:
        if self.id == connector_id:
            self.status = ConnectorState.SUSPENDED_EV

    def handle_session_started(self, connector_id: int) -> None:
        if self.id == connector_id:
            self.start_charging()

    def handle_session_stopped(self, connector_id: int) -> None:
        if self.id == connector_id:
            self.stop_charging()

    def get_status(self) -> ConnectorState:
        return self.status
