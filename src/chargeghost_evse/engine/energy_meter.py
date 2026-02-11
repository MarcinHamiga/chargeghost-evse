from chargeghost_evse.util.event import Event
from chargeghost_evse.util.subscriber import Subscriber

class EnergyMeter(Subscriber):
	def __init__(self, initial_value:float = 0.0, unit:str = "Wh"):
		super().__init__()
		self.value:float = initial_value
		self.unit: str = unit
		self.is_charging: bool = False
		self.energy_consumed: Event = Event()

	def get_meter_reading(self) -> float:
		return self.value

	def consume_energy(self, amount:float) -> None:
		self.value += amount
		self.energy_consumed.emit(amount=amount)

	def update(self, voltage: float, current: float, phase: int, interval_seconds: float) -> None:
		"""Calculates energy consumed in the given interval and updates the meter."""
		if not self.is_charging:
			return
		
		# Power (W) = Voltage (V) * Current (A)
		power = voltage * current * phase
		# Energy (Wh) = Power (W) * Time (h)
		# interval_seconds / 3600 converts seconds to hours
		wh_consumed = (power * interval_seconds) / 3600.0
		
		self.consume_energy(wh_consumed)

	def handle_max_charge_reached(self) -> None:
		self.is_charging = False