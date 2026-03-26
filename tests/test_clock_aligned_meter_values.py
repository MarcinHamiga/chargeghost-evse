from datetime import datetime, timezone

from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.bridge.message_queue import InMemoryBackend, MessageQueue
from chargeghost_evse.engine.engine import Engine


def _make_bridge() -> Bridge:
	engine = Engine()
	engine.add_connector()
	bridge = Bridge(engine=engine, url="ws://localhost:3000/CP_1")
	bridge._message_queue = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
	bridge.engine.plug_in(1)
	bridge.engine.start_session(connector_id=1, transaction_id=1)
	return bridge


def test_collect_meter_value_contexts_disabled() -> None:
	bridge = _make_bridge()
	now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

	contexts, last_sampled_at, next_aligned_at = bridge._collect_meter_value_contexts(
		now,
		0,
		0,
		None,
		None,
	)

	assert contexts == []
	assert last_sampled_at is None
	assert next_aligned_at is None


def test_collect_meter_value_contexts_sampled_only() -> None:
	bridge = _make_bridge()
	start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

	contexts, last_sampled_at, next_aligned_at = bridge._collect_meter_value_contexts(
		start,
		60,
		0,
		None,
		None,
	)

	assert contexts == ["Sample.Periodic"]
	assert last_sampled_at == start
	assert next_aligned_at is None

	contexts, _, _ = bridge._collect_meter_value_contexts(
		datetime(2026, 1, 1, 12, 0, 30, tzinfo=timezone.utc),
		60,
		0,
		last_sampled_at,
		next_aligned_at,
	)
	assert contexts == []


def test_collect_meter_value_contexts_aligned_only() -> None:
	bridge = _make_bridge()
	start = datetime(2026, 1, 1, 12, 0, 30, tzinfo=timezone.utc)

	contexts, last_sampled_at, next_aligned_at = bridge._collect_meter_value_contexts(
		start,
		0,
		60,
		None,
		None,
	)

	assert contexts == []
	assert last_sampled_at is None
	assert next_aligned_at == datetime(2026, 1, 1, 12, 1, 0, tzinfo=timezone.utc)

	contexts, _, next_aligned_at = bridge._collect_meter_value_contexts(
		datetime(2026, 1, 1, 12, 1, 0, tzinfo=timezone.utc),
		0,
		60,
		last_sampled_at,
		next_aligned_at,
	)

	assert contexts == ["Sample.Clock"]
	assert next_aligned_at == datetime(2026, 1, 1, 12, 2, 0, tzinfo=timezone.utc)


def test_collect_meter_value_contexts_combined_operation() -> None:
	bridge = _make_bridge()
	now = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)

	contexts, last_sampled_at, next_aligned_at = bridge._collect_meter_value_contexts(
		now,
		60,
		300,
		None,
		None,
	)

	assert contexts == ["Sample.Periodic", "Sample.Clock"]
	assert last_sampled_at == now
	assert next_aligned_at == datetime(2026, 1, 1, 12, 10, 0, tzinfo=timezone.utc)


def test_wait_interval_prefers_next_aligned_boundary() -> None:
	bridge = _make_bridge()
	now = datetime(2026, 1, 1, 12, 4, 50, tzinfo=timezone.utc)
	wait_interval = bridge._get_meter_values_wait_interval(
		now,
		60,
		300,
		datetime(2026, 1, 1, 12, 4, 0, tzinfo=timezone.utc),
		datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
	)

	assert wait_interval == 10.0
