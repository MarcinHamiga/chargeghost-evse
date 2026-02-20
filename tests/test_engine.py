import pytest
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.engine.connector import ConnectorState


class TestEngine:
	def test_initial_state(self):
		engine = Engine()
		assert engine.session is None
		assert engine.last_stopped_session is None
		assert len(engine.connectors) == 0
		assert engine.energy_meter.get_meter_reading() == 0.0

	def test_add_connector(self):
		engine = Engine()
		connector = engine.add_connector()
		assert len(engine.connectors) == 1
		assert connector.id == 1
		assert connector.status == ConnectorState.AVAILABLE

	def test_add_multiple_connectors(self):
		engine = Engine()
		engine.add_connector()
		engine.add_connector()
		engine.add_connector()
		assert len(engine.connectors) == 3
		assert engine.connectors[0].id == 1
		assert engine.connectors[1].id == 2
		assert engine.connectors[2].id == 3

	def test_remove_connector(self):
		engine = Engine()
		engine.add_connector()
		engine.add_connector()
		engine.add_connector()
		engine.remove_connector(2)
		assert len(engine.connectors) == 2
		assert engine.connectors[0].id == 1
		assert engine.connectors[1].id == 3

	def test_plug_in(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(1)
		assert engine.connectors[0].is_plugged_in is True
		assert engine.connectors[0].status == ConnectorState.PREPARING

	def test_unplug(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(1)
		engine.unplug(1)
		assert engine.connectors[0].is_plugged_in is False
		assert engine.connectors[0].status == ConnectorState.AVAILABLE

	def test_start_session(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(1)
		engine.start_session(connector_id=1, transaction_id=123)
		assert engine.session is not None
		assert engine.session.transaction_id == 123
		assert engine.session.connector_id == 1
		assert engine.energy_meter.is_charging is True

	def test_start_session_not_plugged(self):
		engine = Engine()
		engine.add_connector()
		engine.start_session(connector_id=1, transaction_id=123)
		assert engine.session is None

	def test_start_session_invalid_connector(self):
		engine = Engine()
		engine.add_connector()
		engine.start_session(connector_id=5, transaction_id=123)
		assert engine.session is None

	def test_stop_session(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(1)
		engine.start_session(connector_id=1, transaction_id=123)
		engine.stop_session()
		assert engine.session is None
		assert engine.last_stopped_session is not None
		assert engine.last_stopped_session["transaction_id"] == 123
		assert engine.energy_meter.is_charging is False

	def test_unplug_stops_session(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(1)
		engine.start_session(connector_id=1, transaction_id=123)
		engine.unplug(1)
		assert engine.session is None
		assert engine.last_stopped_session is not None

	def test_command_queue_start(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(1)
		engine.command_queue.put({
			"action": "START",
			"connector_id": 1,
			"transaction_id": 456
		})
		engine._process_commands()
		assert engine.session is not None
		assert engine.session.transaction_id == 456

	def test_command_queue_stop(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(1)
		engine.start_session(connector_id=1, transaction_id=123)
		engine.command_queue.put({"action": "STOP"})
		engine._process_commands()
		assert engine.session is None

	def test_command_queue_plug_in(self):
		engine = Engine()
		engine.add_connector()
		engine.command_queue.put({"action": "PLUG_IN", "connector_id": 1})
		engine._process_commands()
		assert engine.connectors[0].is_plugged_in is True

	def test_command_queue_unplug(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(1)
		engine.command_queue.put({"action": "UNPLUG", "connector_id": 1})
		engine._process_commands()
		assert engine.connectors[0].is_plugged_in is False

	def test_session_started_event(self):
		engine = Engine()
		engine.add_connector()
		events = []
		
		def on_session_started(connector_id):
			events.append(connector_id)
		
		engine.session_started.subscribe(on_session_started)
		engine.plug_in(1)
		engine.start_session(connector_id=1, transaction_id=123)
		
		assert len(events) == 1
		assert events[0] == 1

	def test_session_stopped_event(self):
		engine = Engine()
		engine.add_connector()
		events = []
		
		def on_session_stopped(connector_id):
			events.append(connector_id)
		
		engine.session_stopped.subscribe(on_session_stopped)
		engine.plug_in(1)
		engine.start_session(connector_id=1, transaction_id=123)
		engine.stop_session()
		
		assert len(events) == 1
		assert events[0] == 1

	def test_update_connector_parameters(self):
		engine = Engine()
		engine.add_connector()
		error = engine.update_connector(1, voltage=400.0, current=50.0, phase=3)
		assert error is None
		assert engine.connectors[0].voltage == 400.0
		assert engine.connectors[0].current == 50.0
		assert engine.connectors[0].phase == 3

	def test_update_connector_invalid_id(self):
		engine = Engine()
		engine.add_connector()
		error = engine.update_connector(5, voltage=400.0)
		assert error is not None
		assert "not found" in error

	def test_update_connector_invalid_voltage(self):
		engine = Engine()
		engine.add_connector()
		error = engine.update_connector(1, voltage=50.0)
		assert error is not None

	def test_update_connector_invalid_current(self):
		engine = Engine()
		engine.add_connector()
		error = engine.update_connector(1, current=100.0)
		assert error is not None

	def test_update_connector_invalid_phase(self):
		engine = Engine()
		engine.add_connector()
		error = engine.update_connector(1, phase=5)
		assert error is not None

	def test_connector_parameters_changed_event(self):
		engine = Engine()
		engine.add_connector()
		changes = []

		def on_params_change(connector_id, voltage, current, phase):
			changes.append((connector_id, voltage, current, phase))

		engine.connector_parameters_changed.subscribe(on_params_change)
		engine.update_connector(1, voltage=400.0, current=50.0, phase=2)

		assert len(changes) == 1
		assert changes[0] == (1, 400.0, 50.0, 2)

	def test_start_session_invalid_status(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(1)
		
		# Test FAULTED
		engine.get_connector(1).status = ConnectorState.FAULTED
		engine.start_session(connector_id=1, transaction_id=123)
		assert engine.session is None
		
		# Test UNAVAILABLE
		engine.get_connector(1).status = ConnectorState.UNAVAILABLE
		engine.start_session(connector_id=1, transaction_id=123)
		assert engine.session is None

	def test_simulate_step(self):
		engine = Engine()
		engine.add_connector(voltage=230, current=10, phase=1) # 2300W
		engine.plug_in(1)
		engine.start_session(connector_id=1, transaction_id=123)
		
		# Simulate 1 hour (3600s)
		# Wh = (2300 * 3600) / 3600 = 2300 Wh
		engine.simulate(3600)
		assert engine.energy_meter.get_meter_reading() == pytest.approx(2300.0)

	def test_get_connector(self):
		engine = Engine()
		engine.add_connector()
		engine.add_connector(voltage=400.0, current=63.0, phase=3)

		conn = engine.get_connector(1)
		assert conn is not None
		assert conn.voltage == 230.0

		conn = engine.get_connector(2)
		assert conn is not None
		assert conn.voltage == 400.0
		assert conn.current == 63.0
		assert conn.phase == 3

	def test_get_connector_invalid_id(self):
		engine = Engine()
		engine.add_connector()
		conn = engine.get_connector(5)
		assert conn is None

	def test_add_connector_with_custom_params(self):
		engine = Engine()
		connector = engine.add_connector(voltage=400.0, current=63.0, phase=3)
		assert connector.voltage == 400.0
		assert connector.current == 63.0
		assert connector.phase == 3
