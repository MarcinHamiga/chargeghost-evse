from chargeghost_evse.util.event import Event

class Session:
	def __init__(self, transaction_id: int = -1, connector_id: int = 0, max_energy:float = 0.0):
		self.transaction_id: int = transaction_id
		self.start_date: str = None
		self.energy_charged: float = 0.0
		self.connector_id: int = connector_id
		self.state_of_charge: float = 0.0 # Current state of charge of the "EV" in %
		self.max_energy: float = max_energy # Battery capacity of the "EV" in Wh
		self.ev_max_charge_reached: Event = Event()

	def process_energy_delivery(self, amount:float=0.0) -> None:
		if self.max_energy > 0:
			self.energy_charged += amount if self.energy_charged + amount <= self.max_energy else self.max_energy - self.energy_charged
			self.state_of_charge = (self.energy_charged / self.max_energy) * 100
		else:
			self.energy_charged += amount
			self.state_of_charge = 0.0

		if self.max_energy > 0 and self.energy_charged >= self.max_energy:
			self.energy_charged = self.max_energy
			self.ev_max_charge_reached.emit()
