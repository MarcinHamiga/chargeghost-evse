import time
from chargeghost_evse.engine.energy_meter import EnergyMeter
from chargeghost_evse.engine.session import Session
from chargeghost_evse.engine.connector import Connector
from chargeghost_evse.util.event import Event

class Engine:
	def __init__(self):
		self.session: Session = None
		self.energy_meter: EnergyMeter = EnergyMeter()
		self.event_queue: list = []
		self.connectors: list[Connector] = []
		self.subscriptions: dict[int, list] = {}
		self.last_update_time: float = None

		self.session_started: Event = Event()
		self.session_stopped: Event = Event()

	def add_connector(self):
		connector_id = len(self.connectors)
		connector = Connector(connector_id)
		
		unsub_start = self.session_started.subscribe(connector.handle_session_started)
		unsub_stop = self.session_stopped.subscribe(connector.handle_session_stopped)
		self.subscriptions[connector_id] = [unsub_start, unsub_stop]
		
		self.connectors.append(connector)

	def remove_connector(self, connector_id: int):
		if 0 <= connector_id < len(self.connectors):
			# Unsubscribe the connector being removed
			for unsub in self.subscriptions[connector_id]:
				unsub()
			
			# Re-index remaining subscriptions
			new_subscriptions = {}
			for i in range(len(self.connectors)):
				if i < connector_id:
					new_subscriptions[i] = self.subscriptions[i]
				elif i > connector_id:
					new_subscriptions[i - 1] = self.subscriptions[i]
			self.subscriptions = new_subscriptions

			head = self.connectors[:connector_id]
			tail = self.connectors[connector_id + 1:]
			for conn in tail:
				conn.id -= 1
			self.connectors = head + tail

	def start_session(self, connector_id: int, transaction_id: int):
		self.session = Session(transaction_id=transaction_id, connector_id=connector_id)
		self.session_energy_unsub = self.energy_meter.energy_consumed.subscribe(self.session.process_energy_delivery)
		self.session.ev_max_charge_reached.subscribe(self.energy_meter.handle_max_charge_reached)
		self.energy_meter.is_charging = True
		self.last_update_time = time.time()
		self.session_started.emit(connector_id=connector_id)

	def stop_session(self):
		if self.session:
			if hasattr(self, 'session_energy_unsub'):
				self.session_energy_unsub()
			connector_id = self.session.connector_id
			self.session = None
			self.energy_meter.is_charging = False
			self.session_stopped.emit(connector_id=connector_id)

	def simulate(self):
		if self.session and self.energy_meter.is_charging:
			current_time = time.time()
			if self.last_update_time is None:
				self.last_update_time = current_time
			
			interval = current_time - self.last_update_time
			self.last_update_time = current_time

			connector = self.connectors[self.session.connector_id]
			self.energy_meter.update(connector.voltage, connector.current, interval_seconds=interval)
			
			# Limit event queue size to prevent memory leak
			self.event_queue.append(self.energy_meter.get_meter_reading())
			if len(self.event_queue) > 100:
				self.event_queue.pop(0)


engine = Engine()

if __name__ == "__main__":
	engine.add_connector()
	engine.start_session(connector_id=0, transaction_id=1)
	try:
		while True:
			engine.simulate()
			time.sleep(1.0) # Simulate every second
	except KeyboardInterrupt:
		pass