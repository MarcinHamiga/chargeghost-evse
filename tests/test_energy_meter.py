import pytest
from chargeghost_evse.engine.energy_meter import EnergyMeter


class TestEnergyMeter:
	def test_initial_value(self):
		meter = EnergyMeter()
		assert meter.get_meter_reading() == 0.0

	def test_initial_value_custom(self):
		meter = EnergyMeter(initial_value=100.0)
		assert meter.get_meter_reading() == 100.0

	def test_consume_energy(self):
		meter = EnergyMeter()
		meter.consume_energy(50.0)
		assert meter.get_meter_reading() == 50.0

	def test_consume_energy_cumulative(self):
		meter = EnergyMeter()
		meter.consume_energy(50.0)
		meter.consume_energy(30.0)
		assert meter.get_meter_reading() == 80.0

	def test_update_when_not_charging(self):
		meter = EnergyMeter()
		meter.update(voltage=230.0, current=32.0, phase=1, interval_seconds=1.0)
		assert meter.get_meter_reading() == 0.0

	def test_update_when_charging(self):
		meter = EnergyMeter()
		meter.is_charging = True
		meter.update(voltage=230.0, current=32.0, phase=1, interval_seconds=3600.0)
		assert meter.get_meter_reading() == pytest.approx(7360.0, rel=0.01)

	def test_update_three_phase(self):
		meter = EnergyMeter()
		meter.is_charging = True
		meter.update(voltage=230.0, current=32.0, phase=3, interval_seconds=3600.0)
		assert meter.get_meter_reading() == pytest.approx(22080.0, rel=0.01)

	def test_update_small_interval(self):
		meter = EnergyMeter()
		meter.is_charging = True
		meter.update(voltage=230.0, current=32.0, phase=1, interval_seconds=1.0)
		expected_wh = (230.0 * 32.0 * 1) / 3600.0
		assert meter.get_meter_reading() == pytest.approx(expected_wh, rel=0.01)

	def test_handle_max_charge_reached(self):
		meter = EnergyMeter()
		meter.is_charging = True
		meter.handle_max_charge_reached(connector_id=1)
		assert meter.is_charging is False

	def test_energy_consumed_event(self):
		meter = EnergyMeter()
		received_amounts = []
		
		def on_energy(amount: float):
			received_amounts.append(amount)
		
		meter.energy_consumed.subscribe(on_energy)
		meter.consume_energy(100.0)
		meter.consume_energy(50.0)
		
		assert received_amounts == [100.0, 50.0]
