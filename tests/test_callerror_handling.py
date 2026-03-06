import asyncio
import concurrent.futures
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.bridge.message_queue import InMemoryBackend, MessageQueue
from chargeghost_evse.engine.engine import Engine


class TestCallErrorHandling:
	def _make_bridge(self) -> Bridge:
		"""Create a Bridge with mocked runner for testing."""
		engine = Engine()
		engine.add_connector()
		bridge = Bridge(engine=engine, url="ws://localhost:3000/CP_1")
		bridge._message_queue = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
		return bridge

	def test_handle_future_error_logs_ocpp_error(self):
		"""_handle_future_error should log structured info for OCPP errors."""
		bridge = self._make_bridge()
		logs = []

		def on_log(message, **kw):
			logs.append(message)

		bridge.on_log.subscribe(on_log)

		# Simulate an OCPP error using concurrent.futures.Future (what Bridge uses)
		future: concurrent.futures.Future = concurrent.futures.Future()
		future.set_exception(Exception("InternalError: server busy"))
		bridge._handle_future_error(future)

		assert len(logs) == 1
		assert "OCPP send failed" in logs[0]

	def _run_loop_until_idle(self, loop: asyncio.AbstractEventLoop) -> None:
		"""Run loop in a thread, wait for a sentinel to confirm all pending tasks ran."""
		t = threading.Thread(target=loop.run_forever, daemon=True)
		t.start()
		# Schedule a no-op and wait for it — ensures all previously scheduled coroutines ran
		sentinel = asyncio.run_coroutine_threadsafe(asyncio.sleep(0), loop)
		sentinel.result(timeout=5)
		loop.call_soon_threadsafe(loop.stop)
		t.join(timeout=2)

	def test_stop_transaction_failure_enqueues(self):
		"""If StopTransaction send fails, it should be enqueued for retry."""
		bridge = self._make_bridge()

		adapter = MagicMock()
		adapter.send_stop_transaction = AsyncMock(
			side_effect=Exception("Connection lost")
		)
		bridge.runner.adapter = adapter
		loop = asyncio.new_event_loop()
		bridge.runner.loop = loop

		# Set up a stopped session
		bridge.engine.plug_in(1)
		bridge.engine.start_session(connector_id=1, transaction_id=99)
		bridge.engine.stop_session(reason="Remote")

		bridge.on_engine_session_stopped(1)
		self._run_loop_until_idle(loop)

		# The message should be in the queue for retry
		assert bridge._message_queue.size == 1
		loop.close()

	def test_start_transaction_offline_drain_assigns_transaction_id(self):
		"""Transaction ID from CSMS response must be set on session after offline queue drain."""
		bridge = self._make_bridge()

		# Session starts while offline (no adapter) — StartTransaction is queued
		bridge.engine.plug_in(1)
		bridge.engine.start_session(connector_id=1, transaction_id=0)
		bridge.on_engine_session_started(1)
		assert bridge._message_queue.size == 1

		# Now the connection comes up; adapter returns transaction_id=42 from CSMS
		adapter = MagicMock()
		adapter.send_start_transaction = AsyncMock(
			return_value=MagicMock(transaction_id=42, id_tag_info={"status": "Accepted"})
		)
		adapter.set_active_transaction = MagicMock()
		bridge.runner.adapter = adapter
		loop = asyncio.new_event_loop()
		bridge.runner.loop = loop

		bridge._drain_message_queue()
		self._run_loop_until_idle(loop)

		# Session transaction_id should now reflect the CSMS-assigned value
		assert bridge.engine.session is not None
		assert bridge.engine.session.transaction_id == 42
		adapter.set_active_transaction.assert_called_once_with(1, 42)
		loop.close()
