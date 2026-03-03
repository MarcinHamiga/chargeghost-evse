import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from chargeghost_evse.bridge.message_queue import (
	InMemoryBackend,
	MessageQueue,
	QueuedMessage,
)


class TestInMemoryBackend:
	def test_store_and_pop(self):
		backend = InMemoryBackend()
		msg = QueuedMessage(action="StopTransaction", kwargs={"tx_id": 1}, timestamp="2026-01-01T00:00:00Z")
		backend.store(msg)
		assert backend.size == 1
		popped = backend.pop()
		assert popped is not None
		assert popped.action == "StopTransaction"
		assert backend.size == 0

	def test_pop_empty(self):
		backend = InMemoryBackend()
		assert backend.pop() is None

	def test_fifo_order(self):
		backend = InMemoryBackend()
		backend.store(QueuedMessage(action="A", kwargs={}, timestamp="t1"))
		backend.store(QueuedMessage(action="B", kwargs={}, timestamp="t2"))
		assert backend.pop().action == "A"
		assert backend.pop().action == "B"

	def test_peek(self):
		backend = InMemoryBackend()
		msg = QueuedMessage(action="Test", kwargs={}, timestamp="t1")
		backend.store(msg)
		peeked = backend.peek()
		assert peeked is not None
		assert peeked.action == "Test"
		assert backend.size == 1  # Not consumed

	def test_all(self):
		backend = InMemoryBackend()
		backend.store(QueuedMessage(action="A", kwargs={}, timestamp="t1"))
		backend.store(QueuedMessage(action="B", kwargs={}, timestamp="t2"))
		all_msgs = backend.all()
		assert len(all_msgs) == 2
		assert all_msgs[0].action == "A"

	def test_clear(self):
		backend = InMemoryBackend()
		backend.store(QueuedMessage(action="A", kwargs={}, timestamp="t1"))
		backend.clear()
		assert backend.size == 0


class TestMessageQueue:
	def test_enqueue_and_size(self):
		q = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
		q.enqueue("StopTransaction", {"meter_stop": 100})
		assert q.size == 1

	def test_enqueue_sets_timestamp(self):
		q = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
		q.enqueue("MeterValues", {"value": 42})
		msg = q._backend.peek()
		assert msg is not None
		assert msg.timestamp != ""

	def test_clear(self):
		q = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
		q.enqueue("A", {})
		q.enqueue("B", {})
		q.clear()
		assert q.size == 0


class TestJsonFileBackend:
	def test_store_and_pop(self, tmp_path):
		from chargeghost_evse.bridge.message_queue import JsonFileBackend

		filepath = tmp_path / "queue.json"
		backend = JsonFileBackend(filepath)
		msg = QueuedMessage(action="StopTransaction", kwargs={"tx_id": 1}, timestamp="t1")
		backend.store(msg)
		assert backend.size == 1
		assert filepath.exists()
		popped = backend.pop()
		assert popped is not None
		assert popped.action == "StopTransaction"
		assert backend.size == 0

	def test_persistence_across_instances(self, tmp_path):
		from chargeghost_evse.bridge.message_queue import JsonFileBackend

		filepath = tmp_path / "queue.json"
		backend1 = JsonFileBackend(filepath)
		backend1.store(QueuedMessage(action="A", kwargs={"x": 1}, timestamp="t1"))
		backend1.store(QueuedMessage(action="B", kwargs={"y": 2}, timestamp="t2"))

		# New instance should read existing data
		backend2 = JsonFileBackend(filepath)
		assert backend2.size == 2
		assert backend2.pop().action == "A"

	def test_clear_removes_file(self, tmp_path):
		from chargeghost_evse.bridge.message_queue import JsonFileBackend

		filepath = tmp_path / "queue.json"
		backend = JsonFileBackend(filepath)
		backend.store(QueuedMessage(action="A", kwargs={}, timestamp="t1"))
		backend.clear()
		assert backend.size == 0

	def test_corrupted_file_starts_empty(self, tmp_path):
		from chargeghost_evse.bridge.message_queue import JsonFileBackend

		filepath = tmp_path / "queue.json"
		filepath.write_text("not valid json")
		backend = JsonFileBackend(filepath)
		assert backend.size == 0


class TestMessageQueueDrain:
	def test_drain_sends_all_messages(self):
		q = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
		q.enqueue("StopTransaction", {"meter_stop": 100, "timestamp": "t", "transaction_id": 1, "reason": "Local"})
		q.enqueue("MeterValues", {"connector_id": 1, "value": 42, "transaction_id": 1})

		adapter = MagicMock()
		adapter.send_stop_transaction = AsyncMock()
		adapter.send_meter_values = AsyncMock()

		loop = asyncio.new_event_loop()
		try:
			sent = loop.run_until_complete(q.drain(adapter))
			assert sent == 2
			assert q.size == 0
			adapter.send_stop_transaction.assert_called_once()
			adapter.send_meter_values.assert_called_once()
		finally:
			loop.close()

	def test_drain_empty_queue(self):
		q = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
		adapter = MagicMock()

		loop = asyncio.new_event_loop()
		try:
			sent = loop.run_until_complete(q.drain(adapter))
			assert sent == 0
		finally:
			loop.close()

	def test_drain_drops_after_max_attempts(self):
		q = MessageQueue(backend=InMemoryBackend(), max_attempts=2)
		q.enqueue("StopTransaction", {"meter_stop": 100, "timestamp": "t", "transaction_id": 1, "reason": "Local"})

		# Manually set attempts to max
		msg = q._backend.pop()
		msg.attempts = 2
		q._backend.store(msg)

		adapter = MagicMock()
		adapter.send_stop_transaction = AsyncMock()

		loop = asyncio.new_event_loop()
		try:
			sent = loop.run_until_complete(q.drain(adapter))
			assert sent == 0
			assert q.size == 0  # Dropped, not re-queued
			adapter.send_stop_transaction.assert_not_called()
		finally:
			loop.close()

	def test_drain_requeues_on_failure(self):
		q = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
		q.enqueue("StopTransaction", {"meter_stop": 100, "timestamp": "t", "transaction_id": 1, "reason": "Local"})

		adapter = MagicMock()
		adapter.send_stop_transaction = AsyncMock(side_effect=Exception("Connection lost"))

		loop = asyncio.new_event_loop()
		try:
			sent = loop.run_until_complete(q.drain(adapter))
			assert sent == 0
			assert q.size == 1  # Re-queued
			requeued = q._backend.peek()
			assert requeued.attempts == 1
		finally:
			loop.close()
