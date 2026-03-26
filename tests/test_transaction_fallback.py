from unittest.mock import MagicMock

from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.bridge.message_queue import InMemoryBackend, MessageQueue
from chargeghost_evse.engine.engine import Engine


def _make_bridge() -> Bridge:
	engine = Engine()
	engine.add_connector()
	bridge = Bridge(engine=engine, url="ws://localhost:3000/CP_1")
	bridge._message_queue = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
	return bridge


def test_meter_values_queue_uses_minus_one_before_start_transaction_conf() -> None:
	bridge = _make_bridge()
	bridge.runner.adapter = None
	bridge.runner.loop = None

	bridge.engine.plug_in(1)
	bridge.engine.start_session(connector_id=1, transaction_id=0)

	shutdown = MagicMock()
	shutdown.is_set.side_effect = [False, True]
	shutdown.wait.return_value = None
	bridge._shutdown_event = shutdown

	bridge._meter_values_loop()

	queued = bridge._message_queue._backend.peek()
	assert queued is not None
	assert queued.action == "MeterValues"
	assert queued.kwargs["transaction_id"] == -1


def test_stop_transaction_queue_uses_minus_one_before_start_transaction_conf() -> None:
	bridge = _make_bridge()
	bridge.runner.adapter = None
	bridge.runner.loop = None

	bridge.engine.plug_in(1)
	bridge.engine.start_session(connector_id=1, transaction_id=0)
	bridge.engine.stop_session(reason="Remote")

	bridge.on_engine_session_stopped(1)

	queued = bridge._message_queue._backend.peek()
	assert queued is not None
	assert queued.action == "StopTransaction"
	assert queued.kwargs["transaction_id"] == -1


def test_meter_snapshot_reports_minus_one_before_start_transaction_conf() -> None:
	bridge = _make_bridge()
	adapter = MagicMock()
	bridge.runner.adapter = adapter
	bridge._inject_limit_getter()

	bridge.engine.plug_in(1)
	bridge.engine.start_session(connector_id=1, transaction_id=0)

	assert adapter.get_meter_snapshot is not None
	assert adapter.get_meter_snapshot(1) == (0.0, -1)
