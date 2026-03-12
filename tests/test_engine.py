import logging

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
		error = engine.update_connector(1, current=200.0)
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

	def test_delayed_remote_start(self):
		engine = Engine()
		engine.add_connector()
		# 1. Send START command with timeout
		command = {
			"action": "START",
			"connector_id": 1,
			"id_tag": "TEST_TAG",
			"transaction_id": 123,
			"timeout": 5
		}
		engine.command_queue.put(command)
		engine._process_commands()

		# 2. Assert Session has NOT started yet
		assert engine.session is None

		# 3. Simulate Plug-in (within timeout)
		engine.plug_in(1)

		# 4. Assert Session STARTS automatically
		assert engine.session is not None
		assert engine.session.id_tag == "TEST_TAG"
		assert engine.session.connector_id == 1

	def test_delayed_remote_start_expired(self):
		import time
		engine = Engine()
		engine.add_connector()
		# 1. Send START command with short timeout
		command = {
			"action": "START",
			"connector_id": 1,
			"id_tag": "TEST_TAG",
			"transaction_id": 124,
			"timeout": 0.1
		}
		engine.command_queue.put(command)
		engine._process_commands()

		# 2. Wait for expiration
		time.sleep(0.2)

		# 3. Simulate Plug-in
		engine.plug_in(1)

		# 4. Assert Session did NOT start
		assert engine.session is None


def test_energy_meter_stops_when_ev_max_charge_reached():
	"""EnergyMeter must stop charging when ev_max_charge_reached fires."""
	engine = Engine()
	engine.add_connector(voltage=230.0, current=32.0, phase=1)
	connector_id = engine.connectors[0].id

	engine.plug_in(connector_id)
	engine.start_session(connector_id=connector_id, transaction_id=1)
	engine.energy_meter.is_charging = True  # simulate active charging

	assert engine.session is not None
	# Firing ev_max_charge_reached with connector_id — this should NOT crash
	# and should stop the energy meter
	engine.session.ev_max_charge_reached.emit(connector_id=connector_id)

	assert engine.energy_meter.is_charging is False


def test_plug_in_unplugs_other_connectors():
	"""Engine.plug_in() must auto-unplug any other plugged-in connector."""
	engine = Engine()
	engine.add_connector(voltage=230.0, current=32.0, phase=1)
	engine.add_connector(voltage=230.0, current=32.0, phase=1)

	id1 = engine.connectors[0].id
	id2 = engine.connectors[1].id

	engine.plug_in(id1)
	assert engine.connectors[0].is_plugged_in

	# Plugging in connector 2 must auto-unplug connector 1
	engine.plug_in(id2)
	assert engine.connectors[1].is_plugged_in
	assert not engine.connectors[0].is_plugged_in


def test_plug_in_stops_session_on_other_connector():
	"""Engine.plug_in() must stop an active session when auto-unplugging another connector."""
	engine = Engine()
	engine.add_connector(voltage=230.0, current=32.0, phase=1)
	engine.add_connector(voltage=230.0, current=32.0, phase=1)

	id1 = engine.connectors[0].id
	id2 = engine.connectors[1].id

	# Set up an active session on connector 1
	engine.plug_in(id1)
	engine.start_session(connector_id=id1, transaction_id=1)
	assert engine.session is not None

	# Plug into connector 2 — should auto-unplug connector 1 AND stop its session
	engine.plug_in(id2)
	assert engine.connectors[1].is_plugged_in
	assert not engine.connectors[0].is_plugged_in
	assert engine.session is None


def test_remove_connector_raises_on_last():
	"""Engine.remove_connector() must raise ValueError if only one connector."""
	engine = Engine()
	engine.add_connector(voltage=230.0, current=32.0, phase=1)
	connector_id = engine.connectors[0].id

	with pytest.raises(ValueError, match="last connector"):
		engine.remove_connector(connector_id)


def test_remove_connector_raises_on_active_session():
	"""Engine.remove_connector() must raise ValueError if session active on that connector."""
	engine = Engine()
	engine.add_connector(voltage=230.0, current=32.0, phase=1)
	engine.add_connector(voltage=230.0, current=32.0, phase=1)
	id1 = engine.connectors[0].id

	engine.plug_in(id1)
	engine.start_session(connector_id=id1, transaction_id=1)

	with pytest.raises(ValueError, match="active session"):
		engine.remove_connector(id1)


def test_remove_connector_raises_on_unknown_id():
	"""Engine.remove_connector() must raise ValueError if connector_id does not exist."""
	engine = Engine()
	engine.add_connector(voltage=230.0, current=32.0, phase=1)
	engine.add_connector(voltage=230.0, current=32.0, phase=1)

	with pytest.raises(ValueError, match="not found"):
		engine.remove_connector(99)


def test_suspend_ev():
	"""Engine.suspend_ev() transitions connector to SuspendedEV and pauses energy meter."""
	engine = Engine()
	engine.add_connector(voltage=230.0, current=32.0, phase=1)
	conn = engine.connectors[0]

	engine.plug_in(conn.id)
	engine.start_session(connector_id=conn.id, transaction_id=1)
	assert conn.status == ConnectorState.CHARGING
	assert engine.energy_meter.is_charging is True

	engine.suspend_ev(conn.id)
	assert conn.status == ConnectorState.SUSPENDED_EV
	assert engine.energy_meter.is_charging is False


def test_resume_charging():
	"""Engine.resume_charging() transitions from SuspendedEV back to Charging."""
	engine = Engine()
	engine.add_connector(voltage=230.0, current=32.0, phase=1)
	conn = engine.connectors[0]

	engine.plug_in(conn.id)
	engine.start_session(connector_id=conn.id, transaction_id=1)
	engine.suspend_ev(conn.id)
	assert conn.status == ConnectorState.SUSPENDED_EV

	engine.resume_charging(conn.id)
	assert conn.status == ConnectorState.CHARGING
	assert engine.energy_meter.is_charging is True


def test_suspend_ev_only_when_charging():
	"""Engine.suspend_ev() does nothing if connector is not in CHARGING state."""
	engine = Engine()
	engine.add_connector(voltage=230.0, current=32.0, phase=1)
	conn = engine.connectors[0]

	# Not plugged in, no session
	engine.suspend_ev(conn.id)
	assert conn.status == ConnectorState.AVAILABLE


def test_resume_only_when_suspended():
	"""Engine.resume_charging() does nothing if connector is not in SUSPENDED_EV state."""
	engine = Engine()
	engine.add_connector(voltage=230.0, current=32.0, phase=1)
	conn = engine.connectors[0]

	engine.plug_in(conn.id)
	engine.start_session(connector_id=conn.id, transaction_id=1)
	assert conn.status == ConnectorState.CHARGING

	# Should not change state when already charging
	engine.resume_charging(conn.id)
	assert conn.status == ConnectorState.CHARGING


def test_stop_session_from_suspended_ev():
	"""Stopping a session from SUSPENDED_EV state should work correctly."""
	engine = Engine()
	engine.add_connector(voltage=230.0, current=32.0, phase=1)
	conn = engine.connectors[0]

	engine.plug_in(conn.id)
	engine.start_session(connector_id=conn.id, transaction_id=1)
	engine.suspend_ev(conn.id)
	assert conn.status == ConnectorState.SUSPENDED_EV

	engine.stop_session()
	assert conn.status == ConnectorState.FINISHING
	assert engine.session is None


def test_start_session_on_faulted_returns_early():
	"""start_session on FAULTED connector must not create a session."""
	engine = Engine()
	engine.add_connector()
	engine.plug_in(1)
	engine.get_connector(1).status = ConnectorState.FAULTED
	engine.start_session(connector_id=1, transaction_id=123)
	assert engine.session is None


def test_start_session_on_unavailable_returns_early():
	"""start_session on UNAVAILABLE connector must not create a session."""
	engine = Engine()
	engine.add_connector()
	engine.plug_in(1)
	engine.get_connector(1).status = ConnectorState.UNAVAILABLE
	engine.start_session(connector_id=1, transaction_id=123)
	assert engine.session is None


def test_plug_in_on_faulted_connector():
	"""plug_in on FAULTED connector should not transition to PREPARING."""
	engine = Engine()
	engine.add_connector()
	engine.get_connector(1).status = ConnectorState.FAULTED
	engine.plug_in(1)
	assert engine.get_connector(1).status == ConnectorState.FAULTED


# ---------------------------------------------------------------------------
# set_connector_availability / ChangeAvailability
# ---------------------------------------------------------------------------

def test_set_connector_availability_inoperative_no_session():
	"""Immediate unavailability when no active session."""
	engine = Engine()
	engine.add_connector()
	result = engine.set_connector_availability(1, "Inoperative")
	assert result == "accepted"
	assert engine.get_connector(1).status == ConnectorState.UNAVAILABLE


def test_set_connector_availability_operative_restores_available():
	"""set_operative restores connector to AVAILABLE."""
	engine = Engine()
	engine.add_connector()
	engine.set_connector_availability(1, "Inoperative")
	result = engine.set_connector_availability(1, "Operative")
	assert result == "accepted"
	assert engine.get_connector(1).status == ConnectorState.AVAILABLE


def test_set_connector_availability_deferred_during_active_session():
	"""Availability change deferred when session is active on that connector."""
	engine = Engine()
	engine.add_connector()
	engine.plug_in(1)
	engine.start_session(connector_id=1, transaction_id=1)
	assert engine.session is not None

	result = engine.set_connector_availability(1, "Inoperative")
	assert result == "scheduled"
	# Connector still operational during session
	assert engine.get_connector(1).status == ConnectorState.CHARGING


def test_deferred_availability_applied_on_session_stop():
	"""Deferred ChangeAvailability is applied once the session ends."""
	engine = Engine()
	engine.add_connector()
	engine.plug_in(1)
	engine.start_session(connector_id=1, transaction_id=1)

	engine.set_connector_availability(1, "Inoperative")
	engine.stop_session()

	assert engine.session is None
	assert engine.get_connector(1).status == ConnectorState.UNAVAILABLE


def test_set_connector_availability_all_connectors():
	"""connector_id=0 applies change to all connectors."""
	engine = Engine()
	engine.add_connector()
	engine.add_connector()
	result = engine.set_connector_availability(0, "Inoperative")
	assert result == "accepted"
	assert engine.get_connector(1).status == ConnectorState.UNAVAILABLE
	assert engine.get_connector(2).status == ConnectorState.UNAVAILABLE


def test_set_connector_availability_unknown_connector():
	"""Unknown connector_id returns rejected."""
	engine = Engine()
	engine.add_connector()
	result = engine.set_connector_availability(99, "Inoperative")
	assert result == "rejected"


def test_deferred_availability_mixed_session_and_idle():
	"""When connector_id=0 and one connector has active session, result is 'scheduled'."""
	engine = Engine()
	engine.add_connector()
	engine.add_connector()
	engine.plug_in(1)
	engine.start_session(connector_id=1, transaction_id=1)

	result = engine.set_connector_availability(0, "Inoperative")
	assert result == "scheduled"
	# Connector 2 (no session) changed immediately
	assert engine.get_connector(2).status == ConnectorState.UNAVAILABLE
	# Connector 1 (active session) deferred
	assert engine.get_connector(1).status == ConnectorState.CHARGING


# ---------------------------------------------------------------------------
# SUSPENDED_EVSE via simulate() + smart charging limit
# ---------------------------------------------------------------------------

def test_simulate_suspends_evse_when_limit_is_zero():
	"""simulate() transitions connector to SUSPENDED_EVSE when limit drops to 0."""
	engine = Engine()
	engine.add_connector(voltage=230.0, current=32.0)
	engine.plug_in(1)
	engine.start_session(connector_id=1, transaction_id=1)
	engine.get_limit = lambda connector_id, tx_id: 0.0

	engine.simulate(interval_seconds=1.0)

	assert engine.get_connector(1).status == ConnectorState.SUSPENDED_EVSE


def test_simulate_resumes_from_suspended_evse_when_limit_restored():
	"""simulate() returns connector to CHARGING when limit comes back above 0."""
	engine = Engine()
	engine.add_connector(voltage=230.0, current=32.0)
	engine.plug_in(1)
	engine.start_session(connector_id=1, transaction_id=1)

	engine.get_limit = lambda connector_id, tx_id: 0.0
	engine.simulate(interval_seconds=1.0)
	assert engine.get_connector(1).status == ConnectorState.SUSPENDED_EVSE

	engine.get_limit = lambda connector_id, tx_id: 16.0
	engine.simulate(interval_seconds=1.0)
	assert engine.get_connector(1).status == ConnectorState.CHARGING


def test_simulate_no_energy_delivered_when_suspended_evse():
	"""No energy should accumulate while in SUSPENDED_EVSE (limit=0)."""
	engine = Engine()
	engine.add_connector(voltage=230.0, current=32.0)
	engine.plug_in(1)
	engine.start_session(connector_id=1, transaction_id=1, max_energy=10000.0)
	engine.get_limit = lambda connector_id, tx_id: 0.0

	for _ in range(10):
		engine.simulate(interval_seconds=1.0)

	assert engine.session is not None
	assert engine.session.energy_charged == 0.0


class TestEngineLogging:
	def test_engine_uses_python_logger(self):
		"""Engine must use a named Python logger, not Event."""
		engine = Engine()
		assert hasattr(engine, 'logger')
		assert engine.logger.name == "chargeghost.engine"

	def test_engine_log_emits_to_python_logging(self, caplog):
		"""Engine._log must emit to Python logging system."""
		engine = Engine()
		with caplog.at_level(logging.DEBUG, logger="chargeghost.engine"):
			engine._log("[yellow]Engine:[/yellow] test message")

		assert len(caplog.records) == 1
		assert caplog.records[0].getMessage() == "[yellow]Engine:[/yellow] test message"
		assert caplog.records[0].source == "engine"

	def test_engine_no_on_log_event(self):
		"""Engine must not have on_log Event after migration."""
		engine = Engine()
		assert not hasattr(engine, 'on_log')

	def test_engine_session_logger_name(self):
		engine = Engine()
		assert engine._session_logger.name == "chargeghost.engine.session"
