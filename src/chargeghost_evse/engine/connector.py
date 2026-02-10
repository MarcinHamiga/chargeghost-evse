import enum

class ConnectorState(enum.Enum):
	AVAILABLE = "Available"
	PREPARING = "Preparing"
	CHARGING = "Charging"
	SUSPENDED_EVSE = "SuspendedEVSE"
	SUSPENDED_EV = "SuspendedEV"
	UNAVAILABLE = "Unavailable"
	FAULTED = "Faulted"

class Connector:
	def __init__(self, id: int, voltage:float = 230.0, current:float = 16.0):
		self.status: ConnectorState = ConnectorState.AVAILABLE
		self.id: int = id
		self.voltage: float = voltage
		self.current: float = current
		
	def set_status(self, status: ConnectorState) -> None:
		self.status = status

	def handle_max_charge_reached(self, connector_id: int) -> None:
		if self.id == connector_id:
			self.set_status(ConnectorState.SUSPENDED_EV)

	def handle_session_started(self, connector_id: int) -> None:
		if self.id == connector_id:
			self.set_status(ConnectorState.CHARGING)

	def handle_session_stopped(self, connector_id: int) -> None:
		if self.id == connector_id:
			self.set_status(ConnectorState.AVAILABLE)
	
	def get_status(self) -> ConnectorState:
		return self.status

