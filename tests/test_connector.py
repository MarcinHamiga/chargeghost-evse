from chargeghost_evse.engine.connector import Connector, ConnectorState


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
