from chargeghost_evse.util.subscriber import Subscriber
from chargeghost_evse.util.event import Event
from chargeghost_evse.util.config import (
    VOLTAGE_MIN,
    VOLTAGE_MAX,
    CURRENT_MIN,
    CURRENT_MAX,
    PHASE_MIN,
    PHASE_MAX,
)
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
        self._persistent_status: ConnectorState = ConnectorState.AVAILABLE
        self.is_plugged_in: bool = False
        self.id_tag: Optional[str] = None

        self.on_status_change: Event = Event()
        self.on_parameters_change: Event = Event()

    @property
    def status(self) -> ConnectorState:
        return self._status

    @status.setter
    def status(self, new_status: ConnectorState) -> None:
        if self._status != new_status:
            # Persistent states that shouldn't be cleared by unplugging/plugging
            if new_status in (ConnectorState.UNAVAILABLE, ConnectorState.FAULTED, ConnectorState.AVAILABLE):
                self._persistent_status = new_status
            
            self._status = new_status
            self.on_status_change.emit(connector_id=self.id, status=new_status)

    def set_parameters(
        self,
        voltage: Optional[float] = None,
        current: Optional[float] = None,
        phase: Optional[int] = None,
    ) -> Optional[str]:
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

        self.on_parameters_change.emit(
            connector_id=self.id,
            voltage=self.voltage,
            current=self.current,
            phase=self.phase,
        )
        return None

    @property
    def power(self) -> float:
        return self.voltage * self.current * self.phase

    def plug_in(self) -> None:
        if not self.is_plugged_in:
            self.is_plugged_in = True
            if self.status == ConnectorState.AVAILABLE:
                self.status = ConnectorState.PREPARING

    def unplug(self) -> None:
        if self.is_plugged_in:
            self.is_plugged_in = False
            self.id_tag = None
            self.status = self._persistent_status

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
