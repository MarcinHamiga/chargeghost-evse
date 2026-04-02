import pytest
from chargeghost_evse.devtools.fault_manager import FaultManager
from chargeghost_evse.devtools.fault_models import FaultConfig
from chargeghost_evse.engine.connector import ConnectorState
from chargeghost_evse.engine.engine import Engine


class TestFrozenMeterFault:
    def test_frozen_meter_fault_prevents_meter_growth(self):
        fm = FaultManager()
        engine = Engine()
        engine.set_fault_manager(fm)
        engine.add_connector(voltage=230, current=10, phase=1)
        engine.plug_in(1)
        engine.start_session(connector_id=1, transaction_id=1)

        engine.simulate(3600)
        initial = engine.energy_meter.get_meter_reading()
        assert initial > 0.0

        fm.enable("frozen_meter")

        engine.simulate(3600)
        after = engine.energy_meter.get_meter_reading()
        assert after == initial

        connector = engine.get_connector(1)
        assert connector.status == ConnectorState.CHARGING

        assert len(engine.event_queue) == 2
        assert engine.event_queue[-1] == initial


class TestMeterJumpFault:
    def test_meter_jump_fault_applies_once(self):
        fm = FaultManager()
        engine = Engine()
        engine.set_fault_manager(fm)
        engine.add_connector(voltage=230, current=10, phase=1)
        engine.plug_in(1)
        engine.start_session(connector_id=1, transaction_id=1)

        engine.simulate(3600)
        before_jump = engine.energy_meter.get_meter_reading()
        assert before_jump > 0.0

        fm.enable(
            "meter_jump",
            config=FaultConfig(
                fault_id="meter_jump",
                parameters={"amount_kwh": 5.0},
            ),
        )

        engine.simulate(3600)
        after_first = engine.energy_meter.get_meter_reading()
        jump_size = after_first - before_jump
        assert jump_size >= 5000.0

        engine.simulate(3600)
        after_second = engine.energy_meter.get_meter_reading()
        normal_growth = after_second - after_first
        assert normal_growth == pytest.approx(2300.0, rel=0.01)
        assert normal_growth < 5000.0


class TestMeterResetFault:
    def test_meter_reset_fault_zeroes_next_visible_reading(self):
        fm = FaultManager()
        engine = Engine()
        engine.set_fault_manager(fm)
        engine.add_connector(voltage=230, current=10, phase=1)
        engine.plug_in(1)
        engine.start_session(connector_id=1, transaction_id=1)

        engine.simulate(3600)
        assert engine.event_queue[-1] > 0.0
        real_value = engine.energy_meter.get_meter_reading()
        assert real_value > 0.0

        fm.enable("meter_reset")

        engine.simulate(3600)
        assert engine.event_queue[-1] == 0.0
        assert engine.energy_meter.get_meter_reading() > real_value


class TestStatusFlapFault:
    def test_status_flap_fault_restores_original_state(self):
        fm = FaultManager()
        engine = Engine()
        engine.set_fault_manager(fm)
        engine.add_connector(voltage=230, current=10, phase=1)

        events: list[tuple[int, ConnectorState]] = []

        def on_status(connector_id: int, status: ConnectorState) -> None:
            events.append((connector_id, status))

        engine.connector_status_changed.subscribe(on_status)

        fm.enable(
            "status_flap",
            config=FaultConfig(
                fault_id="status_flap",
                parameters={"flap_count": 2},
            ),
        )

        engine.plug_in(1)

        assert len(events) == 5
        assert events[0] == (1, ConnectorState.FAULTED)
        assert events[1] == (1, ConnectorState.PREPARING)
        assert events[2] == (1, ConnectorState.FAULTED)
        assert events[3] == (1, ConnectorState.PREPARING)
        assert events[4] == (1, ConnectorState.PREPARING)

        connector = engine.get_connector(1)
        assert connector.status == ConnectorState.PREPARING


class TestNoFaultBaseline:
    def test_no_fault_baseline_unchanged(self):
        engine = Engine()
        engine.add_connector(voltage=230, current=10, phase=1)
        engine.plug_in(1)
        engine.start_session(connector_id=1, transaction_id=1)

        engine.simulate(3600)
        assert engine.energy_meter.get_meter_reading() > 0.0
        assert len(engine.event_queue) == 1
        assert engine.event_queue[0] > 0.0

        engine.simulate(3600)
        assert engine.energy_meter.get_meter_reading() > engine.event_queue[0]
        assert len(engine.event_queue) == 2
