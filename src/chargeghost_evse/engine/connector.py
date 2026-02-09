import enum


class Connector:
	def __init__(self, id: int):
		self.status: ConnectorState = ConnectorState.AVAILABLE
		self.id: int = id
		

class ConnectorState(enum.Enum):
	AVAILABLE = "Available"
	PREPARING = "Preparing"
	CHARGING = "Charging"
	SUSPENDED_EVSE = "SuspendedEVSE"
	SUSPENDED_EV = "SuspendedEV"
	UNAVAILABLE = "Unavailable"
	FAULTED = "Faulted"