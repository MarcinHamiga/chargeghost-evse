import time
from datetime import datetime, timezone

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

        def on_max_reached(connector_id: int):
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
        before = time.time()
        session = Session()
        after = time.time()
        assert before <= session.start_time <= after


def test_start_time_is_posix_timestamp():
    """start_time must be a valid POSIX timestamp, not a monotonic counter."""
    before = time.time()
    session = Session(connector_id=1, id_tag="TAG1", transaction_id=1)
    after = time.time()

    assert before <= session.start_time <= after

    # Must convert to a valid datetime without producing a 1970-era date
    dt = datetime.fromtimestamp(session.start_time, tz=timezone.utc)
    assert dt.year >= 2024


def test_ev_max_charge_reached_fires_only_once():
    """ev_max_charge_reached must emit exactly once even with repeated calls after max."""
    session = Session(connector_id=1, id_tag="TAG", transaction_id=1, max_energy=1.0)

    fired_count = 0

    def on_max_reached(connector_id):
        nonlocal fired_count
        fired_count += 1

    session.ev_max_charge_reached.subscribe(on_max_reached)

    # First delivery reaches max
    session.process_energy_delivery(1.0, connector_id=1)
    assert fired_count == 1

    # Subsequent calls must not re-fire
    session.process_energy_delivery(0.0, connector_id=1)
    session.process_energy_delivery(0.0, connector_id=1)
    assert fired_count == 1
