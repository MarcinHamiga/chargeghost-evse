import asyncio
import concurrent.futures
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

	def test_stop_transaction_failure_enqueues(self):
		"""If StopTransaction send fails, it should be enqueued for retry."""
		bridge = self._make_bridge()

		adapter = MagicMock()
		adapter.send_stop_transaction = AsyncMock(
			side_effect=Exception("Connection lost")
		)
		bridge.runner.adapter = adapter
		bridge.runner.loop = asyncio.new_event_loop()

		# Set up a stopped session
		bridge.engine.plug_in(1)
		bridge.engine.start_session(connector_id=1, transaction_id=99)
		bridge.engine.stop_session(reason="Remote")

		bridge.on_engine_session_stopped(1)

		# Give the future time to complete
		bridge.runner.loop.run_until_complete(asyncio.sleep(0.1))

		# The message should be in the queue for retry
		assert bridge._message_queue.size == 1
		bridge.runner.loop.close()
