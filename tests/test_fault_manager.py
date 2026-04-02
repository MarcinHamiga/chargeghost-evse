import pytest

from chargeghost_evse.devtools.fault_manager import FaultManager
from chargeghost_evse.devtools.fault_models import FaultConfig


class TestFaultManager:
	def test_enable_persistent_fault(self) -> None:
		mgr = FaultManager()
		mgr.enable("delayed_reconnect")
		assert mgr.is_active("delayed_reconnect")
		state = mgr.peek("delayed_reconnect")
		assert state is not None
		assert state.enabled

	def test_enable_and_disable_fault(self) -> None:
		mgr = FaultManager()
		mgr.enable("delayed_reconnect")
		assert mgr.is_active("delayed_reconnect")
		mgr.disable("delayed_reconnect")
		assert not mgr.is_active("delayed_reconnect")

	def test_consume_one_shot_fault_exactly_once(self) -> None:
		mgr = FaultManager()
		mgr.enable("forced_disconnect")
		result = mgr.consume_if_active("forced_disconnect")
		assert result.triggered
		assert result.remaining == 0
		assert not mgr.is_active("forced_disconnect")
		result2 = mgr.consume_if_active("forced_disconnect")
		assert not result2.triggered

	def test_count_limited_fault_deactivates_after_limit(self) -> None:
		mgr = FaultManager()
		config = FaultConfig(
			fault_id="meter_jump", count_limit=2
		)
		mgr.enable("meter_jump", config=config)
		r1 = mgr.consume_if_active("meter_jump")
		assert r1.triggered
		assert r1.remaining == 1
		r2 = mgr.consume_if_active("meter_jump")
		assert r2.triggered
		assert r2.remaining == 0
		r3 = mgr.consume_if_active("meter_jump")
		assert not r3.triggered

	def test_reject_unknown_fault_id(self) -> None:
		mgr = FaultManager()
		with pytest.raises(ValueError, match="Unknown fault ID"):
			mgr.enable("nonexistent")

	def test_get_active_summary_returns_only_enabled(self) -> None:
		mgr = FaultManager()
		mgr.enable("delayed_reconnect")
		mgr.enable("frozen_meter")
		summary = mgr.get_active_summary()
		assert len(summary) == 2
		ids = {s.fault_id for s in summary}
		assert "delayed_reconnect" in ids
		assert "frozen_meter" in ids

	def test_clear_all_disables_everything(self) -> None:
		mgr = FaultManager()
		mgr.enable("delayed_reconnect")
		mgr.enable("frozen_meter")
		mgr.enable("forced_disconnect")
		mgr.clear_all()
		assert not mgr.is_active("delayed_reconnect")
		assert not mgr.is_active("frozen_meter")
		assert not mgr.is_active("forced_disconnect")
		assert mgr.get_active_summary() == []

	def test_fault_changed_event_fired_on_enable(self) -> None:
		mgr = FaultManager()
		called: list[dict] = []

		def on_fault_changed(**kw: object) -> None:
			called.append(kw)

		mgr.fault_changed.subscribe(on_fault_changed)
		mgr.enable("delayed_reconnect")
		assert len(called) == 1
		assert called[0]["fault_id"] == "delayed_reconnect"
		assert called[0]["enabled"] is True
