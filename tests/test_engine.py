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
		assert connector.id == 0
		assert connector.status == ConnectorState.AVAILABLE

	def test_add_multiple_connectors(self):
		engine = Engine()
		engine.add_connector()
		engine.add_connector()
		engine.add_connector()
		assert len(engine.connectors) == 3
		assert engine.connectors[0].id == 0
		assert engine.connectors[1].id == 1
		assert engine.connectors[2].id == 2

	def test_remove_connector(self):
		engine = Engine()
		engine.add_connector()
		engine.add_connector()
		engine.add_connector()
		engine.remove_connector(1)
		assert len(engine.connectors) == 2
		assert engine.connectors[0].id == 0
		assert engine.connectors[1].id == 1

	def test_plug_in(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(0)
		assert engine.connectors[0].is_plugged_in is True
		assert engine.connectors[0].status == ConnectorState.PREPARING

	def test_unplug(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(0)
		engine.unplug(0)
		assert engine.connectors[0].is_plugged_in is False
		assert engine.connectors[0].status == ConnectorState.AVAILABLE

	def test_start_session(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(0)
		engine.start_session(connector_id=0, transaction_id=123)
		assert engine.session is not None
		assert engine.session.transaction_id == 123
		assert engine.session.connector_id == 0
		assert engine.energy_meter.is_charging is True

	def test_start_session_not_plugged(self):
		engine = Engine()
		engine.add_connector()
		engine.start_session(connector_id=0, transaction_id=123)
		assert engine.session is None

	def test_start_session_invalid_connector(self):
		engine = Engine()
		engine.add_connector()
		engine.start_session(connector_id=5, transaction_id=123)
		assert engine.session is None

	def test_stop_session(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(0)
		engine.start_session(connector_id=0, transaction_id=123)
		engine.stop_session()
		assert engine.session is None
		assert engine.last_stopped_session is not None
		assert engine.last_stopped_session["transaction_id"] == 123
		assert engine.energy_meter.is_charging is False

	def test_unplug_stops_session(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(0)
		engine.start_session(connector_id=0, transaction_id=123)
		engine.unplug(0)
		assert engine.session is None
		assert engine.last_stopped_session is not None

	def test_command_queue_start(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(0)
		engine.command_queue.put({
			"action": "START",
			"connector_id": 0,
			"transaction_id": 456
		})
		engine._process_commands()
		assert engine.session is not None
		assert engine.session.transaction_id == 456

	def test_command_queue_stop(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(0)
		engine.start_session(connector_id=0, transaction_id=123)
		engine.command_queue.put({"action": "STOP"})
		engine._process_commands()
		assert engine.session is None

	def test_command_queue_plug_in(self):
		engine = Engine()
		engine.add_connector()
		engine.command_queue.put({"action": "PLUG_IN", "connector_id": 0})
		engine._process_commands()
		assert engine.connectors[0].is_plugged_in is True

	def test_command_queue_unplug(self):
		engine = Engine()
		engine.add_connector()
		engine.plug_in(0)
		engine.command_queue.put({"action": "UNPLUG", "connector_id": 0})
		engine._process_commands()
		assert engine.connectors[0].is_plugged_in is False

	def test_session_started_event(self):
		engine = Engine()
		engine.add_connector()
		events = []
		
		def on_session_started(connector_id):
			events.append(connector_id)
		
		engine.session_started.subscribe(on_session_started)
		engine.plug_in(0)
		engine.start_session(connector_id=0, transaction_id=123)
		
		assert len(events) == 1
		assert events[0] == 0

	def test_session_stopped_event(self):
		engine = Engine()
		engine.add_connector()
		events = []
		
		def on_session_stopped(connector_id):
			events.append(connector_id)
		
		engine.session_stopped.subscribe(on_session_stopped)
		engine.plug_in(0)
		engine.start_session(connector_id=0, transaction_id=123)
		engine.stop_session()
		
		assert len(events) == 1
		assert events[0] == 0
