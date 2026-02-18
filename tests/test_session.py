import pytest
import time
from chargeghost_evse.engine.session import Session


class TestSession:
    def test_initial_values(self):
        session = Session(
            transaction_id=123, connector_id=0, max_energy=55000.0, id_tag="TEST_TAG"
        )
        assert session.transaction_id == 123
        assert session.connector_id == 0
        assert session.max_energy == 55000.0
        assert session.id_tag == "TEST_TAG"
        assert session.energy_charged == 0.0
        assert session.state_of_charge == 0.0

    def test_default_values(self):
        session = Session()
        assert session.transaction_id == -1
        assert session.connector_id == 0
        assert session.max_energy == 0.0
        assert session.id_tag is None

    def test_process_energy_delivery(self):
        session = Session(max_energy=1000.0)
        session.process_energy_delivery(amount=100.0)
        assert session.energy_charged == 100.0
        assert session.state_of_charge == 10.0

    def test_process_energy_delivery_cumulative(self):
        session = Session(max_energy=1000.0)
        session.process_energy_delivery(amount=100.0)
        session.process_energy_delivery(amount=50.0)
        assert session.energy_charged == 150.0
        assert session.state_of_charge == 15.0

    def test_process_energy_delivery_max_cap(self):
        session = Session(max_energy=100.0)
        session.process_energy_delivery(amount=150.0)
        assert session.energy_charged == 100.0
        assert session.state_of_charge == 100.0

    def test_process_energy_delivery_partial_at_max(self):
        session = Session(max_energy=100.0)
        session.process_energy_delivery(amount=80.0)
        session.process_energy_delivery(amount=50.0)
        assert session.energy_charged == 100.0

    def test_max_charge_reached_event(self):
        session = Session(max_energy=100.0)
        event_fired = []

        def on_max_reached():
            event_fired.append(True)

        session.ev_max_charge_reached.subscribe(on_max_reached)
        session.process_energy_delivery(amount=100.0)

        assert len(event_fired) == 1

    def test_no_event_before_max(self):
        session = Session(max_energy=100.0)
        event_fired = []

        def on_max_reached():
            event_fired.append(True)

        session.ev_max_charge_reached.subscribe(on_max_reached)
        session.process_energy_delivery(amount=50.0)

        assert len(event_fired) == 0

    def test_zero_max_energy(self):
        session = Session(max_energy=0.0)
        session.process_energy_delivery(amount=100.0)
        assert session.energy_charged == 100.0
        assert session.state_of_charge == 0.0

    def test_start_time(self):
        before = time.monotonic()
        session = Session()
        after = time.monotonic()
        assert before <= session.start_time <= after
