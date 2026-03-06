from chargeghost_evse.engine.connector import Connector, ConnectorState


class TestStateTransitions:
	"""Tests for formal state machine validation."""

	def test_plug_in_from_available(self):
		connector = Connector(id=1)
		error = connector.plug_in()
		assert error is None
		assert connector.status == ConnectorState.PREPARING

	def test_plug_in_from_faulted_rejected(self):
		connector = Connector(id=1)
		connector.status = ConnectorState.FAULTED
		error = connector.plug_in()
		assert error is not None
		assert "Invalid" in error
		assert connector.status == ConnectorState.FAULTED

	def test_plug_in_from_unavailable_rejected(self):
		connector = Connector(id=1)
		connector.status = ConnectorState.UNAVAILABLE
		# plug_in already preserves UNAVAILABLE (existing behavior)
		# But now it should also return an error string
		error = connector.plug_in()
		assert error is not None

	def test_start_charging_from_preparing(self):
		connector = Connector(id=1)
		connector.plug_in()
		error = connector.start_charging()
		assert error is None
		assert connector.status == ConnectorState.CHARGING

	def test_start_charging_from_available_rejected(self):
		connector = Connector(id=1)
		error = connector.start_charging()
		assert error is not None
		assert connector.status == ConnectorState.AVAILABLE

	def test_stop_charging_from_charging(self):
		connector = Connector(id=1)
		connector.plug_in()
		connector.start_charging()
		error = connector.stop_charging()
		assert error is None
		assert connector.status == ConnectorState.FINISHING

	def test_stop_charging_from_suspended_ev(self):
		connector = Connector(id=1)
		connector.plug_in()
		connector.start_charging()
		connector.suspend_ev()
		error = connector.stop_charging()
		assert error is None
		assert connector.status == ConnectorState.FINISHING

	def test_stop_charging_from_suspended_evse(self):
		"""stop_charging() must work when EVSE suspended by smart charging."""
		connector = Connector(id=1)
		connector.plug_in()
		connector.start_charging()
		connector._status = ConnectorState.SUSPENDED_EVSE
		error = connector.stop_charging()
		assert error is None
		assert connector.status == ConnectorState.FINISHING

	def test_stop_charging_from_available_rejected(self):
		connector = Connector(id=1)
		error = connector.stop_charging()
		assert error is not None

	def test_suspend_ev_from_charging(self):
		connector = Connector(id=1)
		connector.plug_in()
		connector.start_charging()
		error = connector.suspend_ev()
		assert error is None
		assert connector.status == ConnectorState.SUSPENDED_EV

	def test_suspend_ev_from_preparing_rejected(self):
		connector = Connector(id=1)
		connector.plug_in()
		error = connector.suspend_ev()
		assert error is not None
		assert connector.status == ConnectorState.PREPARING

	def test_resume_from_suspended_ev(self):
		connector = Connector(id=1)
		connector.plug_in()
		connector.start_charging()
		connector.suspend_ev()
		error = connector.resume_charging()
		assert error is None
		assert connector.status == ConnectorState.CHARGING

	def test_resume_from_charging_rejected(self):
		connector = Connector(id=1)
		connector.plug_in()
		connector.start_charging()
		error = connector.resume_charging()
		assert error is not None
		assert connector.status == ConnectorState.CHARGING

	def test_unplug_from_any_plugged_state(self):
		"""Unplug is always valid when plugged in (physical disconnect)."""
		for start_state in [
			ConnectorState.PREPARING,
			ConnectorState.CHARGING,
			ConnectorState.SUSPENDED_EV,
			ConnectorState.FINISHING,
		]:
			connector = Connector(id=1)
			connector.plug_in()
			connector._status = start_state
			connector.is_plugged_in = True
			error = connector.unplug()
			assert error is None, f"unplug from {start_state} should succeed"

	def test_unplug_when_not_plugged_rejected(self):
		connector = Connector(id=1)
		error = connector.unplug()
		assert error is not None

	def test_plug_in_already_plugged_is_noop(self):
		connector = Connector(id=1)
		connector.plug_in()
		error = connector.plug_in()
		# Second plug_in is a no-op, not an error
		assert error is None
		assert connector.status == ConnectorState.PREPARING


class TestConnector:
	def test_initial_state(self):
		connector = Connector(id=1)
		assert connector.id == 1
		assert connector.status == ConnectorState.AVAILABLE
		assert connector.is_plugged_in is False
		assert connector.id_tag is None
		assert connector.voltage == 230.0
		assert connector.current == 32.0
		assert connector.phase == 1

	def test_custom_parameters(self):
		connector = Connector(id=2, voltage=400.0, current=63.0, phase=3)
		assert connector.id == 2
		assert connector.voltage == 400.0
		assert connector.current == 63.0
		assert connector.phase == 3

	def test_plug_in(self):
		connector = Connector(id=1)
		connector.plug_in()
		assert connector.is_plugged_in is True
		assert connector.status == ConnectorState.PREPARING

	def test_plug_in_already_plugged(self):
		connector = Connector(id=1)
		connector.plug_in()
		connector.plug_in()
		assert connector.is_plugged_in is True
		assert connector.status == ConnectorState.PREPARING

	def test_unplug(self):
		connector = Connector(id=1)
		connector.plug_in()
		connector.unplug()
		assert connector.is_plugged_in is False
		assert connector.status == ConnectorState.AVAILABLE

	def test_unplug_persistent_status(self):
		connector = Connector(id=1)
		connector.status = ConnectorState.UNAVAILABLE
		connector.plug_in()
		# Should remain Unavailable because plug_in only changes from Available
		assert connector.status == ConnectorState.UNAVAILABLE
		connector.unplug()
		assert connector.is_plugged_in is False
		assert connector.status == ConnectorState.UNAVAILABLE

		connector.status = ConnectorState.FAULTED
		connector.plug_in()
		# Should remain Faulted
		assert connector.status == ConnectorState.FAULTED
		connector.unplug()
		assert connector.is_plugged_in is False
		assert connector.status == ConnectorState.FAULTED

	def test_start_charging(self):
		connector = Connector(id=1)
		connector.plug_in()
		connector.start_charging()
		assert connector.status == ConnectorState.CHARGING

	def test_start_charging_not_plugged(self):
		connector = Connector(id=1)
		connector.start_charging()
		assert connector.status == ConnectorState.AVAILABLE

	def test_stop_charging_plugged(self):
		connector = Connector(id=1)
		connector.plug_in()
		connector.start_charging()
		connector.stop_charging()
		assert connector.status == ConnectorState.FINISHING

	def test_stop_charging_not_plugged(self):
		connector = Connector(id=1)
		connector.plug_in()
		connector.start_charging()
		connector.unplug()
		connector.stop_charging()
		assert connector.status == ConnectorState.AVAILABLE

	def test_status_change_event(self):
		connector = Connector(id=1)
		status_changes = []
		
		def on_status_change(connector_id, status):
			status_changes.append((connector_id, status))
		
		connector.on_status_change.subscribe(on_status_change)
		connector.plug_in()
		
		assert len(status_changes) == 1
		assert status_changes[0] == (1, ConnectorState.PREPARING)

	def test_set_parameters_voltage(self):
		connector = Connector(id=1)
		error = connector.set_parameters(voltage=400.0)
		assert error is None
		assert connector.voltage == 400.0

	def test_set_parameters_current(self):
		connector = Connector(id=1)
		error = connector.set_parameters(current=63.0)
		assert error is None
		assert connector.current == 63.0

	def test_set_parameters_phase(self):
		connector = Connector(id=1)
		error = connector.set_parameters(phase=3)
		assert error is None
		assert connector.phase == 3

	def test_set_parameters_all(self):
		connector = Connector(id=1)
		error = connector.set_parameters(voltage=400.0, current=50.0, phase=2)
		assert error is None
		assert connector.voltage == 400.0
		assert connector.current == 50.0
		assert connector.phase == 2

	def test_set_parameters_voltage_invalid_low(self):
		connector = Connector(id=1)
		error = connector.set_parameters(voltage=50.0)
		assert error is not None
		assert "Voltage" in error

	def test_set_parameters_voltage_invalid_high(self):
		connector = Connector(id=1)
		error = connector.set_parameters(voltage=600.0)
		assert error is not None
		assert "Voltage" in error

	def test_set_parameters_current_invalid_low(self):
		connector = Connector(id=1)
		error = connector.set_parameters(current=2.0)
		assert error is not None
		assert "Current" in error

	def test_set_parameters_current_invalid_high(self):
		connector = Connector(id=1)
		error = connector.set_parameters(current=100.0)
		assert error is not None
		assert "Current" in error

	def test_set_parameters_phase_invalid_low(self):
		connector = Connector(id=1)
		error = connector.set_parameters(phase=0)
		assert error is not None
		assert "Phase" in error

	def test_set_parameters_phase_invalid_high(self):
		connector = Connector(id=1)
		error = connector.set_parameters(phase=5)
		assert error is not None
		assert "Phase" in error

	def test_power_property(self):
		connector = Connector(id=1, voltage=230.0, current=32.0, phase=1)
		assert connector.power == 7360.0

		connector.set_parameters(voltage=400.0, current=32.0, phase=3)
		assert connector.power == 38400.0

	def test_stop_charging_from_suspended_ev(self):
		"""stop_charging() must work when connector is in SUSPENDED_EV state."""
		connector = Connector(id=1, voltage=230.0, current=32.0, phase=1)
		connector.plug_in()

		# Manually force SUSPENDED_EV status (battery full scenario)
		connector._status = ConnectorState.SUSPENDED_EV

		connector.stop_charging()

		# Must transition to FINISHING (still plugged in), same as a normal stop
		assert connector.status == ConnectorState.FINISHING
