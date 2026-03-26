import pytest

from chargeghost_evse.engine.engine import Engine


class TestMultiEvseMode:
    """Tests for multi-EVSE mode functionality."""

    def test_multi_evse_mode_default_false(self):
        """Engine defaults to single-EVSE mode."""
        engine = Engine()
        assert engine.multi_evse_mode is False

    def test_multi_evse_mode_enabled(self):
        """Engine can be created with multi_EVSE mode enabled."""
        engine = Engine(multi_evse_mode=True)
        assert engine.multi_evse_mode is True

    def test_single_evse_mode_blocks_second_session(self):
        """In single-EVSE mode, starting a second session is blocked when another is active."""
        engine = Engine(multi_evse_mode=False)
        c1 = engine.add_connector()
        c2 = engine.add_connector()

        engine.plug_in(c1.id)
        engine.start_session(c1.id, transaction_id=1)

        assert engine.session is not None
        assert engine._sessions[c1.id] is engine.session

        engine.plug_in(c2.id)

        assert len(engine._sessions) == 0

    def test_multi_evse_mode_allows_parallel_sessions(self):
        """In multi-EVSE mode, parallel sessions are allowed on different connectors."""
        engine = Engine(multi_evse_mode=True)
        c1 = engine.add_connector()
        c2 = engine.add_connector()

        engine.plug_in(c1.id)
        engine.plug_in(c2.id)

        engine.start_session(c1.id, transaction_id=1)
        engine.start_session(c2.id, transaction_id=2)

        assert len(engine._sessions) == 2
        assert engine.get_session(c1.id) is not None
        assert engine.get_session(c2.id) is not None
        assert engine.get_session(c1.id).transaction_id == 1
        assert engine.get_session(c2.id).transaction_id == 2

    def test_single_evse_mode_auto_unplugs(self):
        """In single-EVSE mode, plugging into one connector auto-unplugs another."""
        engine = Engine(multi_evse_mode=False)
        c1 = engine.add_connector()
        c2 = engine.add_connector()

        engine.plug_in(c1.id)
        assert c1.is_plugged_in is True
        assert c2.is_plugged_in is False

        engine.plug_in(c2.id)
        assert c1.is_plugged_in is False
        assert c2.is_plugged_in is True

    def test_multi_evse_mode_no_auto_unplug(self):
        """In multi-EVSE mode, plugging into one connector does not unplug another."""
        engine = Engine(multi_evse_mode=True)
        c1 = engine.add_connector()
        c2 = engine.add_connector()

        engine.plug_in(c1.id)
        assert c1.is_plugged_in is True
        assert c2.is_plugged_in is False

        engine.plug_in(c2.id)
        assert c1.is_plugged_in is True
        assert c2.is_plugged_in is True

    def test_multi_evse_mode_per_connector_energy_meter(self):
        """In multi-EVSE mode, each connector has its own energy meter."""
        engine = Engine(multi_evse_mode=True)
        c1 = engine.add_connector()
        c2 = engine.add_connector()

        meter1 = engine.get_energy_meter(c1.id)
        meter2 = engine.get_energy_meter(c2.id)

        assert meter1 is not meter2

    def test_single_evse_mode_shared_energy_meter(self):
        """In single-EVSE mode, all connectors share the same energy meter."""
        engine = Engine(multi_evse_mode=False)
        c1 = engine.add_connector()
        c2 = engine.add_connector()

        meter1 = engine.get_energy_meter(c1.id)
        meter2 = engine.get_energy_meter(c2.id)

        assert meter1 is meter2

    def test_stop_session_by_connector_id(self):
        """stop_session can target a specific connector in multi-EVSE mode."""
        engine = Engine(multi_evse_mode=True)
        c1 = engine.add_connector()
        c2 = engine.add_connector()

        engine.plug_in(c1.id)
        engine.plug_in(c2.id)
        engine.start_session(c1.id, transaction_id=1)
        engine.start_session(c2.id, transaction_id=2)

        assert len(engine._sessions) == 2

        engine.stop_session(connector_id=c1.id, reason="Local")

        assert len(engine._sessions) == 1
        assert engine.get_session(c1.id) is None
        assert engine.get_session(c2.id) is not None

    def test_simulate_updates_all_sessions(self):
        """In multi-EVSE mode, simulate() updates all active sessions."""
        engine = Engine(multi_evse_mode=True)
        c1 = engine.add_connector(voltage=230.0, current=10.0, phase=1)
        c2 = engine.add_connector(voltage=230.0, current=10.0, phase=1)

        engine.plug_in(c1.id)
        engine.plug_in(c2.id)
        engine.start_session(c1.id, transaction_id=1, max_energy=100000.0)
        engine.start_session(c2.id, transaction_id=2, max_energy=100000.0)

        meter1_before = engine.get_energy_meter(c1.id).get_meter_reading()
        meter2_before = engine.get_energy_meter(c2.id).get_meter_reading()

        engine.simulate(interval_seconds=1.0)

        meter1_after = engine.get_energy_meter(c1.id).get_meter_reading()
        meter2_after = engine.get_energy_meter(c2.id).get_meter_reading()

        assert meter1_after > meter1_before
        assert meter2_after > meter2_before

    def test_remove_connector_with_active_session_multi_evse(self):
        """In multi-EVSE mode, cannot remove a connector with an active session."""
        engine = Engine(multi_evse_mode=True)
        c1 = engine.add_connector()
        c2 = engine.add_connector()

        engine.plug_in(c1.id)
        engine.start_session(c1.id, transaction_id=1)

        with pytest.raises(ValueError, match="active session"):
            engine.remove_connector(c1.id)

        assert len(engine._connectors) == 2
