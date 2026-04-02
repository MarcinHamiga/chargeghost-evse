import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.bridge.message_queue import InMemoryBackend, MessageQueue
from chargeghost_evse.engine.engine import Engine


def _make_bridge() -> Bridge:
	engine = Engine()
	engine.add_connector()
	bridge = Bridge(engine=engine, url="ws://localhost:3000/CP_1")
	bridge._message_queue = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
	return bridge


def _run_loop_until_idle(loop: asyncio.AbstractEventLoop) -> None:
	thread = threading.Thread(target=loop.run_forever, daemon=True)
	thread.start()
	sentinel = asyncio.run_coroutine_threadsafe(asyncio.sleep(0), loop)
	sentinel.result(timeout=5)
	loop.call_soon_threadsafe(loop.stop)
	thread.join(timeout=2)


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


def test_v201_transaction_id_string_is_preserved_in_meter_snapshot() -> None:
	bridge = Bridge(engine=Engine(), url="ws://localhost:3000/CP_1", ocpp_version="2.0.1")
	bridge.engine.add_connector()
	adapter = MagicMock()
	bridge.runner.adapter = adapter
	bridge._inject_limit_getter()

	bridge.engine.plug_in(1)
	bridge.engine.start_session(connector_id=1, transaction_id=0)
	bridge.engine.session.transaction_id = "tx-1"

	assert adapter.get_meter_snapshot is not None
	assert adapter.get_meter_snapshot(1) == (0.0, "tx-1")


def test_v201_session_start_queue_uses_distinct_started_action() -> None:
	bridge = Bridge(engine=Engine(), url="ws://localhost:3000/CP_1", ocpp_version="2.0.1")
	bridge.engine.add_connector()
	bridge._message_queue = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
	bridge.runner.adapter = None
	bridge.runner.loop = None

	bridge.engine.plug_in(1)
	bridge.engine.start_session(connector_id=1, transaction_id=0)
	bridge.on_engine_session_started(1)

	queued = bridge._message_queue._backend.peek()
	assert queued is not None
	assert queued.action == "TransactionEventStarted"


def test_v201_session_stop_queue_uses_distinct_ended_action() -> None:
	bridge = Bridge(engine=Engine(), url="ws://localhost:3000/CP_1", ocpp_version="2.0.1")
	bridge.engine.add_connector()
	bridge._message_queue = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
	bridge.runner.adapter = None
	bridge.runner.loop = None

	bridge.engine.plug_in(1)
	bridge.engine.start_session(connector_id=1, transaction_id=0)
	bridge.engine.session.transaction_id = "tx-1"
	bridge.engine.stop_session(reason="Remote")

	bridge.on_engine_session_stopped(1)

	queued = bridge._message_queue._backend.peek()
	assert queued is not None
	assert queued.action == "TransactionEventEnded"
	assert queued.kwargs["transaction_id"] == "tx-1"


def test_v201_queue_drain_assigns_generated_transaction_id() -> None:
	bridge = Bridge(engine=Engine(), url="ws://localhost:3000/CP_1", ocpp_version="2.0.1")
	bridge.engine.add_connector()
	bridge._message_queue = MessageQueue(backend=InMemoryBackend(), max_attempts=3)

	bridge.engine.plug_in(1)
	bridge.engine.start_session(connector_id=1, transaction_id=0)
	bridge._message_queue.enqueue(
		"TransactionEventStarted",
		{
			"connector_id": 1,
			"id_tag": "ABC",
			"meter_start": 0,
			"timestamp": "t",
			"reservation_id": None,
		},
	)

	adapter = MagicMock()
	adapter.send_transaction_event_started = AsyncMock(
		return_value=(MagicMock(), "tx-queued")
	)
	bridge.runner.adapter = adapter
	loop = asyncio.new_event_loop()
	bridge.runner.loop = loop

	bridge._drain_message_queue()
	_run_loop_until_idle(loop)

	assert bridge.engine.session is not None
	assert bridge.engine.session.transaction_id == "tx-queued"
	loop.close()


def test_remote_started_session_uses_remote_id_tag_in_v16_start_transaction() -> None:
	bridge = Bridge(
		engine=Engine(),
		url="ws://localhost:3000/CP_1",
		get_rfid=lambda: "LOCAL-TAG",
	)
	bridge.engine.add_connector()
	bridge.engine.session_started.subscribe(bridge.on_engine_session_started)

	adapter = MagicMock()
	adapter.send_start_transaction = AsyncMock(
		return_value=MagicMock(transaction_id=77, id_tag_info={"status": "Accepted"})
	)
	bridge.runner.adapter = adapter
	loop = asyncio.new_event_loop()
	bridge.runner.loop = loop

	bridge.engine.plug_in(1)
	bridge.engine.command_queue.put(
		{
			"action": "START",
			"connector_id": 1,
			"id_tag": "REMOTE-TAG",
			"timeout": 30,
		}
	)
	bridge.engine._process_commands()
	_run_loop_until_idle(loop)

	assert bridge.engine.session is not None
	assert bridge.engine.session.id_tag == "REMOTE-TAG"
	assert adapter.send_start_transaction.await_args is not None
	assert adapter.send_start_transaction.await_args.kwargs["id_tag"] == "REMOTE-TAG"
	loop.close()


def test_app_started_session_falls_back_to_persistent_rfid_in_v16_start_transaction() -> None:
	bridge = Bridge(
		engine=Engine(),
		url="ws://localhost:3000/CP_1",
		get_rfid=lambda: "LOCAL-TAG",
	)
	bridge.engine.add_connector()
	bridge.engine.session_started.subscribe(bridge.on_engine_session_started)

	adapter = MagicMock()
	adapter.send_start_transaction = AsyncMock(
		return_value=MagicMock(transaction_id=77, id_tag_info={"status": "Accepted"})
	)
	bridge.runner.adapter = adapter
	loop = asyncio.new_event_loop()
	bridge.runner.loop = loop

	bridge.engine.plug_in(1)
	bridge.engine.start_session(connector_id=1, transaction_id=0)
	_run_loop_until_idle(loop)

	assert bridge.engine.session is not None
	assert bridge.engine.session.id_tag is None
	assert adapter.send_start_transaction.await_args is not None
	assert adapter.send_start_transaction.await_args.kwargs["id_tag"] == "LOCAL-TAG"
	loop.close()


def test_multi_evse_v16_start_transaction_uses_connector_specific_session_data() -> None:
	engine = Engine(multi_evse_mode=True)
	bridge = Bridge(engine=engine, url="ws://localhost:3000/CP_1")
	engine.add_connector()
	engine.add_connector()
	bridge.engine.session_started.subscribe(bridge.on_engine_session_started)

	async def send_start_transaction(**kwargs):
		return MagicMock(
			transaction_id=700 + kwargs["connector_id"],
			id_tag_info={"status": "Accepted"},
		)

	adapter = MagicMock()
	adapter.send_start_transaction = AsyncMock(side_effect=send_start_transaction)
	bridge.runner.adapter = adapter
	loop = asyncio.new_event_loop()
	bridge.runner.loop = loop

	engine.plug_in(1)
	engine.plug_in(2)
	engine.get_energy_meter(1).value = 111.0
	engine.get_energy_meter(2).value = 222.0

	engine.start_session(connector_id=1, transaction_id=0, id_tag="TAG-1")
	engine.start_session(connector_id=2, transaction_id=0, id_tag="TAG-2")
	_run_loop_until_idle(loop)

	start_calls = {
		call.kwargs["connector_id"]: call.kwargs
		for call in adapter.send_start_transaction.await_args_list
	}
	assert start_calls[1]["id_tag"] == "TAG-1"
	assert start_calls[1]["meter_start"] == 111
	assert start_calls[2]["id_tag"] == "TAG-2"
	assert start_calls[2]["meter_start"] == 222
	assert engine.get_session(1) is not None
	assert engine.get_session(1).transaction_id == 701
	assert engine.get_session(2) is not None
	assert engine.get_session(2).transaction_id == 702
	loop.close()


def test_remote_started_session_uses_remote_id_tag_in_v201_transaction_event() -> None:
	bridge = Bridge(
		engine=Engine(),
		url="ws://localhost:3000/CP_1",
		ocpp_version="2.0.1",
		get_rfid=lambda: "LOCAL-TAG",
	)
	bridge.engine.add_connector()
	bridge.engine.session_started.subscribe(bridge.on_engine_session_started)

	adapter = MagicMock()
	adapter.send_transaction_event_started = AsyncMock(
		return_value=(MagicMock(), "tx-77")
	)
	bridge.runner.adapter = adapter
	loop = asyncio.new_event_loop()
	bridge.runner.loop = loop

	bridge.engine.plug_in(1)
	bridge.engine.command_queue.put(
		{
			"action": "START",
			"connector_id": 1,
			"id_tag": "REMOTE-TAG",
			"timeout": 30,
		}
	)
	bridge.engine._process_commands()
	_run_loop_until_idle(loop)

	assert bridge.engine.session is not None
	assert bridge.engine.session.id_tag == "REMOTE-TAG"
	assert adapter.send_transaction_event_started.await_args is not None
	assert (
		adapter.send_transaction_event_started.await_args.kwargs["id_tag"]
		== "REMOTE-TAG"
	)
	loop.close()
