import pytest
from chargeghost_evse.engine.connector import Connector, ConnectorState


class TestConnector:
	def test_initial_state(self):
		connector = Connector(id=0)
		assert connector.id == 0
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
		connector = Connector(id=0)
		connector.plug_in()
		assert connector.is_plugged_in is True
		assert connector.status == ConnectorState.PREPARING

	def test_plug_in_already_plugged(self):
		connector = Connector(id=0)
		connector.plug_in()
		connector.plug_in()
		assert connector.is_plugged_in is True
		assert connector.status == ConnectorState.PREPARING

	def test_unplug(self):
		connector = Connector(id=0)
		connector.plug_in()
		connector.unplug()
		assert connector.is_plugged_in is False
		assert connector.status == ConnectorState.AVAILABLE

	def test_authorize(self):
		connector = Connector(id=0)
		connector.authorize(id_tag="TEST_TAG")
		assert connector.id_tag == "TEST_TAG"

	def test_start_charging(self):
		connector = Connector(id=0)
		connector.plug_in()
		connector.start_charging()
		assert connector.status == ConnectorState.CHARGING

	def test_start_charging_not_plugged(self):
		connector = Connector(id=0)
		connector.start_charging()
		assert connector.status == ConnectorState.AVAILABLE

	def test_stop_charging_plugged(self):
		connector = Connector(id=0)
		connector.plug_in()
		connector.start_charging()
		connector.stop_charging()
		assert connector.status == ConnectorState.FINISHING

	def test_stop_charging_not_plugged(self):
		connector = Connector(id=0)
		connector.plug_in()
		connector.start_charging()
		connector.unplug()
		connector.stop_charging()
		assert connector.status == ConnectorState.AVAILABLE

	def test_status_change_event(self):
		connector = Connector(id=0)
		status_changes = []
		
		def on_status_change(connector_id, status):
			status_changes.append((connector_id, status))
		
		connector.on_status_change.subscribe(on_status_change)
		connector.plug_in()
		
		assert len(status_changes) == 1
		assert status_changes[0] == (0, ConnectorState.PREPARING)

	def test_get_status(self):
		connector = Connector(id=0)
		assert connector.get_status() == ConnectorState.AVAILABLE
		connector.plug_in()
		assert connector.get_status() == ConnectorState.PREPARING
