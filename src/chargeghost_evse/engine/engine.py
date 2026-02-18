import time
from chargeghost_evse.engine.energy_meter import EnergyMeter
from chargeghost_evse.engine.session import Session
from chargeghost_evse.engine.connector import Connector, ConnectorState
from chargeghost_evse.util.event import Event
from chargeghost_evse.util.subscriber import Subscriber
import queue

class Engine(Subscriber):
	def __init__(self):
		super().__init__()
		self.session: Session = None
		self.energy_meter: EnergyMeter = EnergyMeter()
		self.command_queue: queue.Queue = queue.Queue()
		self.event_queue: list = []
		self.connectors: list[Connector] = []
		self.last_update_time: float = None
		self.last_display_time: float = None

		self.session_started: Event = Event()
		self.session_stopped: Event = Event()
		self.connector_status_changed: Event = Event()
		self.on_log: Event = Event()

		self.simulation_time_step: float = 0.1 # in seconds
		self.display_time_step: float = 1.0 # in seconds

	def _log(self, message: str):
		self.on_log.emit(message=message)

	def add_connector(self, voltage: float = 230.0, current: float = 32.0, phase: int = 1):
		connector_id = len(self.connectors)
		connector = Connector(connector_id, voltage, current, phase)
		
		connector.subscribe_to(self.session_started, connector.handle_session_started)
		connector.subscribe_to(self.session_stopped, connector.handle_session_stopped)
		connector.on_status_change.subscribe(self.handle_connector_status_change)
		
		self.connectors.append(connector)
		return connector

	def remove_connector(self, connector_id: int):
		if 0 <= connector_id < len(self.connectors):
			# Unsubscribe the connector being removed
			self.connectors[connector_id].unsubscribe_all()
			
			head = self.connectors[:connector_id]
			tail = self.connectors[connector_id + 1:]
			for conn in tail:
				conn.id -= 1
			self.connectors = head + tail

	def handle_connector_status_change(self, connector_id, status):
		self.connector_status_changed.emit(connector_id=connector_id, status=status)

	def plug_in(self, connector_id: int):
		if 0 <= connector_id < len(self.connectors):
			self.connectors[connector_id].plug_in()

	def unplug(self, connector_id: int):
		if 0 <= connector_id < len(self.connectors):
			self.connectors[connector_id].unplug()
			if self.session and self.session.connector_id == connector_id:
				self.stop_session()

	def start_session(self, connector_id: int, transaction_id: int, max_energy: float = 55000.0):
		if not (0 <= connector_id < len(self.connectors)):
			self._log(f"Error: Connector {connector_id} not found.")
			return

		connector = self.connectors[connector_id]
		if not connector.is_plugged_in:
			self._log(f"Error: Connector {connector_id} is not plugged in.")
			return

		if self.session:
			self._log(f"Error: Session already active on connector {self.session.connector_id}.")
			return

		self.session = Session(transaction_id=transaction_id, connector_id=connector_id, max_energy=max_energy)
		self.session.subscribe_to(self.energy_meter.energy_consumed, self.session.process_energy_delivery)
		self.energy_meter.subscribe_to(self.session.ev_max_charge_reached, self.energy_meter.handle_max_charge_reached)
		self.energy_meter.is_charging = True
		self.last_update_time = time.time()
		self.session_started.emit(connector_id=connector_id)

	def stop_session(self):
		if self.session:
			connector_id = self.session.connector_id
			self.energy_meter.unsubscribe_from(self.session.ev_max_charge_reached)
			self.session.unsubscribe_all()
			self._log(f"Session time [s]: {time.time() - self.session.start_time}")
			self.session_stopped.emit(connector_id=connector_id)
			self.session = None
			self.energy_meter.is_charging = False

	def simulate(self):
		self._process_commands()
		if self.session and self.energy_meter.is_charging:
			current_time = time.time()
			if self.last_update_time is None:
				self.last_update_time = current_time
			
			if self.last_display_time is None:
				self.last_display_time = current_time
			
			interval = current_time - self.last_update_time
			display_interval = current_time - self.last_display_time
			if interval < self.simulation_time_step:
				return
			self.last_update_time = current_time

			connector = self.connectors[self.session.connector_id]
			self.energy_meter.update(connector.voltage, connector.current, connector.phase, interval_seconds=interval)
			if display_interval >= self.display_time_step:
				# Removed print(self.get_session_info())
				self.last_display_time = current_time
			
			self.event_queue.append(self.energy_meter.get_meter_reading())
			if len(self.event_queue) > 1000:
				self.event_queue.pop(0)

	def _process_commands(self):
		try:
			while not self.command_queue.empty():
				command = self.command_queue.get_nowait()
				self._handle_command(command)
		except queue.Empty:
			pass

	def _handle_command(self, command):
		action = command.get("action")
		connector_id = command.get("connector_id", 0)
		if action == "START":
			self.start_session(
				connector_id=connector_id,
				transaction_id=command.get("transaction_id", 0),
				max_energy=command.get("max_energy", 55000.0)
			)
		elif action == "STOP":
			self.stop_session()
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