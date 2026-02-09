from chargeghost_evse.engine.session import Session
from chargeghost_evse.engine.connector import Connector

class Engine:
	def __init__(self):
		self.session: Session = None
		self.meter_value: float = 0.0
		self.event_queue: list = []
		self.connectors: list[Connector] = []

	def add_connector(self):
		self.connectors.append(Connector(len(self.connectors)))

	def remove_connector(self, connector_id: int):
		self.head = self.connectors[:connector_id]
		self.tail = self.connectors[connector_id + 1:]
		for conn in self.tail:
			conn.id -= 1
		self.connectors = self.head + self.tail

	def start_session(self, connector_id: int, transaction_id: int):
		self.session = Session(transaction_id=transaction_id, connector_id=connector_id)
		


engine = Engine()