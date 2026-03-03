# Robustness Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add offline message queuing, structured CallError handling, and connector state machine validation to improve OCPP 1.6J protocol compliance.

**Architecture:** Three independent features built bottom-up: (1) state machine validation in the engine layer, (2) message queue as a new Bridge component, (3) CallError handling in the Bridge/Adapter layer. Each feature is independently testable.

**Tech Stack:** Python 3.11+, pytest, asyncio, OCPP 1.6J, collections.deque, json

**Run tests after every commit:**
```bash
poetry run pytest -x
poetry run ruff check src/
poetry run mypy src/
```

---

## Feature 1: Connector State Machine Validation

### Task 1: Add transition table and _transition helper to Connector

**Files:**
- Modify: `src/chargeghost_evse/engine/connector.py`
- Test: `tests/test_connector.py`

**Step 1: Write failing tests**

Add to `tests/test_connector.py`:

```python
class TestStateTransitions:
	"""Tests for formal state machine validation."""

	def test_plug_in_from_available(self):
		connector = Connector(id=1)
		error = connector.plug_in()
		assert error is None
		assert connector.status == ConnectorState.PREPARING

	def test_plug_in_from_faulted_rejected(self):
		connector = Connector(id=1)
		connector.status = ConnectorState.FAULTED
		error = connector.plug_in()
		assert error is not None
		assert "Invalid" in error
		assert connector.status == ConnectorState.FAULTED

	def test_plug_in_from_unavailable_rejected(self):
		connector = Connector(id=1)
		connector.status = ConnectorState.UNAVAILABLE
		# plug_in already preserves UNAVAILABLE (existing behavior)
		# But now it should also return an error string
		error = connector.plug_in()
		assert error is not None

	def test_start_charging_from_preparing(self):
		connector = Connector(id=1)
		connector.plug_in()
		error = connector.start_charging()
		assert error is None
		assert connector.status == ConnectorState.CHARGING

	def test_start_charging_from_available_rejected(self):
		connector = Connector(id=1)
		error = connector.start_charging()
		assert error is not None
		assert connector.status == ConnectorState.AVAILABLE

	def test_stop_charging_from_charging(self):
		connector = Connector(id=1)
		connector.plug_in()
		connector.start_charging()
		error = connector.stop_charging()
		assert error is None
		assert connector.status == ConnectorState.FINISHING

	def test_stop_charging_from_suspended_ev(self):
		connector = Connector(id=1)
		connector.plug_in()
		connector.start_charging()
		connector.suspend_ev()
		error = connector.stop_charging()
		assert error is None
		assert connector.status == ConnectorState.FINISHING

	def test_stop_charging_from_available_rejected(self):
		connector = Connector(id=1)
		error = connector.stop_charging()
		assert error is not None

	def test_suspend_ev_from_charging(self):
		connector = Connector(id=1)
		connector.plug_in()
		connector.start_charging()
		error = connector.suspend_ev()
		assert error is None
		assert connector.status == ConnectorState.SUSPENDED_EV

	def test_suspend_ev_from_preparing_rejected(self):
		connector = Connector(id=1)
		connector.plug_in()
		error = connector.suspend_ev()
		assert error is not None
		assert connector.status == ConnectorState.PREPARING

	def test_resume_from_suspended_ev(self):
		connector = Connector(id=1)
		connector.plug_in()
		connector.start_charging()
		connector.suspend_ev()
		error = connector.resume_charging()
		assert error is None
		assert connector.status == ConnectorState.CHARGING

	def test_resume_from_charging_rejected(self):
		connector = Connector(id=1)
		connector.plug_in()
		connector.start_charging()
		error = connector.resume_charging()
		assert error is not None
		assert connector.status == ConnectorState.CHARGING

	def test_unplug_from_any_plugged_state(self):
		"""Unplug is always valid when plugged in (physical disconnect)."""
		for start_state in [
			ConnectorState.PREPARING,
			ConnectorState.CHARGING,
			ConnectorState.SUSPENDED_EV,
			ConnectorState.FINISHING,
		]:
			connector = Connector(id=1)
			connector.plug_in()
			connector._status = start_state
			connector.is_plugged_in = True
			error = connector.unplug()
			assert error is None, f"unplug from {start_state} should succeed"

	def test_unplug_when_not_plugged_rejected(self):
		connector = Connector(id=1)
		error = connector.unplug()
		assert error is not None

	def test_plug_in_already_plugged_is_noop(self):
		connector = Connector(id=1)
		connector.plug_in()
		error = connector.plug_in()
		# Second plug_in is a no-op, not an error
		assert error is None
		assert connector.status == ConnectorState.PREPARING
```

**Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_connector.py::TestStateTransitions -v
```
Expected: FAIL — current methods return `None` implicitly, not error strings.

**Step 3: Add transition table and _transition helper**

In `src/chargeghost_evse/engine/connector.py`, add the transition table after `ConnectorState` and before the `Connector` class:

```python
# Valid state transitions: (current_state, action) -> new_state
VALID_TRANSITIONS: dict[tuple[ConnectorState, str], ConnectorState] = {
	# Plug in/out
	(ConnectorState.AVAILABLE, "plug_in"): ConnectorState.PREPARING,
	(ConnectorState.PREPARING, "unplug"): ConnectorState.AVAILABLE,
	(ConnectorState.FINISHING, "unplug"): ConnectorState.AVAILABLE,
	(ConnectorState.CHARGING, "unplug"): ConnectorState.AVAILABLE,
	(ConnectorState.SUSPENDED_EV, "unplug"): ConnectorState.AVAILABLE,
	# Session lifecycle
	(ConnectorState.PREPARING, "start_charging"): ConnectorState.CHARGING,
	(ConnectorState.CHARGING, "stop_charging"): ConnectorState.FINISHING,
	(ConnectorState.SUSPENDED_EV, "stop_charging"): ConnectorState.FINISHING,
	# Suspension
	(ConnectorState.CHARGING, "suspend_ev"): ConnectorState.SUSPENDED_EV,
	(ConnectorState.SUSPENDED_EV, "resume"): ConnectorState.CHARGING,
}
```

Add `_transition` helper to `Connector`:

```python
def _transition(self, action: str) -> Optional[str]:
	"""
	Attempt a state transition.

	Looks up (current_state, action) in VALID_TRANSITIONS.
	If valid, updates status and returns None.
	If invalid, returns an error message string.

	Args:
		action: The transition action name.

	Returns:
		None on success, error string on invalid transition.
	"""
	key = (self._status, action)
	new_state = VALID_TRANSITIONS.get(key)
	if new_state is None:
		return (
			f"Invalid transition: {self._status.value} + {action}"
		)
	self.status = new_state
	return None
```

**Step 4: Update Connector methods to use _transition and return Optional[str]**

Update each method. The key change: methods now return `Optional[str]` (None on success, error string on failure).

**`plug_in()`:**
```python
def plug_in(self) -> Optional[str]:
	if self.is_plugged_in:
		return None  # Already plugged in, no-op
	if self._status in (ConnectorState.FAULTED, ConnectorState.UNAVAILABLE):
		return f"Invalid transition: {self._status.value} + plug_in"
	self.is_plugged_in = True
	return self._transition("plug_in")
```

**`unplug()`:**
```python
def unplug(self) -> Optional[str]:
	if not self.is_plugged_in:
		return "Cannot unplug: not plugged in"
	self.is_plugged_in = False
	self.id_tag = None
	self.status = self._persistent_status
	return None
```

**`start_charging()`:**
```python
def start_charging(self) -> Optional[str]:
	if not self.is_plugged_in:
		return "Cannot start charging: not plugged in"
	return self._transition("start_charging")
```

**`stop_charging()`:**
```python
def stop_charging(self) -> Optional[str]:
	error = self._transition("stop_charging")
	if error:
		return error
	# If unplugged during charging (race), go to AVAILABLE
	if not self.is_plugged_in:
		self.status = ConnectorState.AVAILABLE
	return None
```

**`suspend_ev()`:**
```python
def suspend_ev(self) -> Optional[str]:
	return self._transition("suspend_ev")
```

**`resume_charging()`:**
```python
def resume_charging(self) -> Optional[str]:
	return self._transition("resume")
```

**Step 5: Run tests**

```bash
poetry run pytest tests/test_connector.py -v
```
Expected: All PASS (both new TestStateTransitions and existing TestConnector).

Note: Some existing tests may need minor updates if they relied on silent no-op behavior. Check `test_start_charging_not_plugged` — it expects status to remain AVAILABLE, which still works since the method returns an error but doesn't crash.

**Step 6: Commit**

```bash
git add src/chargeghost_evse/engine/connector.py tests/test_connector.py
git commit -m "feat: add state machine validation with transition table to Connector

Connector methods now return Optional[str] error on invalid transitions.
VALID_TRANSITIONS dict serves as single source of truth for allowed state
changes. Blocks starting sessions on FAULTED/UNAVAILABLE connectors."
```

---

### Task 2: Update Engine to use Connector return values

**Files:**
- Modify: `src/chargeghost_evse/engine/engine.py`
- Test: `tests/test_engine.py`

**Step 1: Write failing tests**

Add to `tests/test_engine.py`:

```python
def test_start_session_on_faulted_returns_early():
	"""start_session on FAULTED connector must not create a session."""
	engine = Engine()
	engine.add_connector()
	engine.plug_in(1)
	engine.get_connector(1).status = ConnectorState.FAULTED
	engine.start_session(connector_id=1, transaction_id=123)
	assert engine.session is None


def test_start_session_on_unavailable_returns_early():
	"""start_session on UNAVAILABLE connector must not create a session."""
	engine = Engine()
	engine.add_connector()
	engine.plug_in(1)
	engine.get_connector(1).status = ConnectorState.UNAVAILABLE
	engine.start_session(connector_id=1, transaction_id=123)
	assert engine.session is None


def test_plug_in_on_faulted_connector():
	"""plug_in on FAULTED connector should not transition to PREPARING."""
	engine = Engine()
	engine.add_connector()
	engine.get_connector(1).status = ConnectorState.FAULTED
	engine.plug_in(1)
	assert engine.get_connector(1).status == ConnectorState.FAULTED
```

**Step 2: Run tests to verify state**

```bash
poetry run pytest tests/test_engine.py::test_start_session_on_faulted_returns_early tests/test_engine.py::test_start_session_on_unavailable_returns_early tests/test_engine.py::test_plug_in_on_faulted_connector -v
```

The first two should already pass (engine.py lines 357-363 already guard FAULTED/UNAVAILABLE). The third tests the new Connector behavior from Task 1.

**Step 3: Update Engine.plug_in to log validation errors**

In `src/chargeghost_evse/engine/engine.py`, update `plug_in`:

```python
def plug_in(self, connector_id: int) -> None:
	# Auto-unplug any other plugged-in connector (single plug-in policy)
	for conn in self._connectors.values():
		if conn.is_plugged_in and conn.id != connector_id:
			self.unplug(conn.id)

	connector = self._connectors.get(connector_id)
	if connector:
		error = connector.plug_in()
		if error:
			self._log(
				f"[yellow]Engine:[/yellow] Cannot plug in connector {connector_id}: {error}"
			)
```

Update `suspend_ev` and `resume_charging` similarly to log errors from connector methods.

**Step 4: Run full test suite**

```bash
poetry run pytest -x
```
Expected: All PASS.

**Step 5: Commit**

```bash
git add src/chargeghost_evse/engine/engine.py tests/test_engine.py
git commit -m "feat: engine logs state machine validation errors from connector

plug_in, suspend_ev, resume_charging now log errors returned by
Connector transition methods. Existing FAULTED/UNAVAILABLE guards
in start_session remain unchanged."
```

---

## Feature 2: Message Queue (Offline Buffering)

### Task 3: Create MessageQueue with in-memory backend

**Files:**
- Create: `src/chargeghost_evse/bridge/message_queue.py`
- Create: `tests/test_message_queue.py`

**Step 1: Write failing tests**

Create `tests/test_message_queue.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_message_queue.py -v
```
Expected: FAIL — module doesn't exist.

**Step 3: Implement MessageQueue and InMemoryBackend**

Create `src/chargeghost_evse/bridge/message_queue.py`:

```python
"""
Offline message queue for buffering OCPP messages during disconnection.

When the WebSocket connection drops, transaction-critical messages
(StartTransaction, StopTransaction, MeterValues) are buffered here
and replayed on reconnection per OCPP 1.6 section 4.9.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable


@dataclass
class QueuedMessage:
	"""A buffered OCPP message awaiting transmission."""

	action: str
	kwargs: dict
	timestamp: str
	attempts: int = 0


@runtime_checkable
class QueueBackend(Protocol):
	"""Protocol for message queue storage backends."""

	def store(self, msg: QueuedMessage) -> None: ...
	def pop(self) -> Optional[QueuedMessage]: ...
	def peek(self) -> Optional[QueuedMessage]: ...
	def all(self) -> list[QueuedMessage]: ...
	def clear(self) -> None: ...

	@property
	def size(self) -> int: ...


class InMemoryBackend:
	"""In-memory queue backend using collections.deque. Lost on restart."""

	def __init__(self) -> None:
		self._queue: deque[QueuedMessage] = deque()

	def store(self, msg: QueuedMessage) -> None:
		self._queue.append(msg)

	def pop(self) -> Optional[QueuedMessage]:
		if self._queue:
			return self._queue.popleft()
		return None

	def peek(self) -> Optional[QueuedMessage]:
		if self._queue:
			return self._queue[0]
		return None

	def all(self) -> list[QueuedMessage]:
		return list(self._queue)

	def clear(self) -> None:
		self._queue.clear()

	@property
	def size(self) -> int:
		return len(self._queue)


class MessageQueue:
	"""
	Offline message queue for OCPP transaction messages.

	Buffers messages when the WebSocket connection is down and
	replays them on reconnection.

	Args:
		backend: Storage backend (InMemoryBackend or JsonFileBackend).
		max_attempts: Maximum send attempts per message before dropping.
	"""

	def __init__(
		self, backend: QueueBackend, max_attempts: int = 3
	) -> None:
		self._backend = backend
		self._max_attempts = max_attempts

	@property
	def size(self) -> int:
		"""Number of messages in the queue."""
		return self._backend.size

	def enqueue(self, action: str, kwargs: dict) -> None:
		"""
		Add a message to the queue.

		Args:
			action: OCPP action name (e.g., "StopTransaction").
			kwargs: Arguments for the adapter send method.
		"""
		msg = QueuedMessage(
			action=action,
			kwargs=kwargs,
			timestamp=datetime.now(timezone.utc).isoformat(),
		)
		self._backend.store(msg)

	def clear(self) -> None:
		"""Remove all messages from the queue."""
		self._backend.clear()
```

**Step 4: Run tests**

```bash
poetry run pytest tests/test_message_queue.py -v
```
Expected: All PASS.

**Step 5: Commit**

```bash
git add src/chargeghost_evse/bridge/message_queue.py tests/test_message_queue.py
git commit -m "feat: add MessageQueue with in-memory backend for offline buffering

QueuedMessage dataclass, InMemoryBackend (deque-based), and MessageQueue
class. Provides enqueue/drain/clear interface for OCPP message buffering."
```

---

### Task 4: Add JsonFileBackend

**Files:**
- Modify: `src/chargeghost_evse/bridge/message_queue.py`
- Modify: `tests/test_message_queue.py`

**Step 1: Write failing tests**

Add to `tests/test_message_queue.py`:

```python
import json
from pathlib import Path


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
```

**Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_message_queue.py::TestJsonFileBackend -v
```
Expected: FAIL — `JsonFileBackend` doesn't exist.

**Step 3: Implement JsonFileBackend**

Add to `src/chargeghost_evse/bridge/message_queue.py`:

```python
import json
import logging
import os
from pathlib import Path

_logger = logging.getLogger(__name__)


class JsonFileBackend:
	"""
	JSON file queue backend. Persists messages across restarts.

	Reads the full file on init, writes atomically on every mutation.

	Args:
		filepath: Path to the JSON queue file.
	"""

	def __init__(self, filepath: Path) -> None:
		self._filepath = filepath
		self._queue: deque[QueuedMessage] = deque()
		self._load()

	def _load(self) -> None:
		"""Load messages from file, if it exists and is valid."""
		if self._filepath.exists():
			try:
				with open(self._filepath, "r") as f:
					data = json.load(f)
				for item in data:
					self._queue.append(
						QueuedMessage(
							action=item["action"],
							kwargs=item["kwargs"],
							timestamp=item["timestamp"],
							attempts=item.get("attempts", 0),
						)
					)
			except (json.JSONDecodeError, KeyError, IOError) as e:
				_logger.warning("Corrupted message queue file %s: %s", self._filepath, e)
				self._queue.clear()

	def _save(self) -> None:
		"""Write queue to file atomically."""
		self._filepath.parent.mkdir(parents=True, exist_ok=True)
		data = [
			{
				"action": msg.action,
				"kwargs": msg.kwargs,
				"timestamp": msg.timestamp,
				"attempts": msg.attempts,
			}
			for msg in self._queue
		]
		tmp = self._filepath.with_suffix(".tmp")
		with open(tmp, "w") as f:
			json.dump(data, f)
		os.replace(tmp, self._filepath)

	def store(self, msg: QueuedMessage) -> None:
		self._queue.append(msg)
		self._save()

	def pop(self) -> Optional[QueuedMessage]:
		if self._queue:
			msg = self._queue.popleft()
			self._save()
			return msg
		return None

	def peek(self) -> Optional[QueuedMessage]:
		if self._queue:
			return self._queue[0]
		return None

	def all(self) -> list[QueuedMessage]:
		return list(self._queue)

	def clear(self) -> None:
		self._queue.clear()
		if self._filepath.exists():
			self._filepath.unlink()

	@property
	def size(self) -> int:
		return len(self._queue)
```

**Step 4: Run tests**

```bash
poetry run pytest tests/test_message_queue.py -v
```
Expected: All PASS.

**Step 5: Commit**

```bash
git add src/chargeghost_evse/bridge/message_queue.py tests/test_message_queue.py
git commit -m "feat: add JsonFileBackend for persistent message queue

Reads on init, writes atomically on mutation. Handles corrupted files
gracefully by starting empty. Complements InMemoryBackend."
```

---

### Task 5: Add drain method to MessageQueue

**Files:**
- Modify: `src/chargeghost_evse/bridge/message_queue.py`
- Modify: `tests/test_message_queue.py`

**Step 1: Write failing tests**

Add to `tests/test_message_queue.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock


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
```

**Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_message_queue.py::TestMessageQueueDrain -v
```
Expected: FAIL — `drain` method doesn't exist.

**Step 3: Implement drain**

Add to `MessageQueue` in `src/chargeghost_evse/bridge/message_queue.py`:

```python
# Map of OCPP action names to adapter send method names
_ACTION_TO_METHOD: dict[str, str] = {
	"StartTransaction": "send_start_transaction",
	"StopTransaction": "send_stop_transaction",
	"MeterValues": "send_meter_values",
}

async def drain(self, adapter) -> int:
	"""
	Replay all queued messages via the adapter.

	Messages that fail are re-enqueued with incremented attempt count.
	Messages exceeding max_attempts are dropped.

	Args:
		adapter: The OCPP Adapter instance with send_* methods.

	Returns:
		Number of messages successfully sent.
	"""
	sent = 0
	failed: list[QueuedMessage] = []
	messages = self._backend.all()
	self._backend.clear()

	for msg in messages:
		if msg.attempts >= self._max_attempts:
			continue  # Drop message

		method_name = _ACTION_TO_METHOD.get(msg.action)
		if method_name is None:
			continue

		send_method = getattr(adapter, method_name, None)
		if send_method is None:
			continue

		try:
			await send_method(**msg.kwargs)
			sent += 1
		except Exception:
			msg.attempts += 1
			failed.append(msg)

	# Re-queue failed messages
	for msg in failed:
		self._backend.store(msg)

	return sent
```

**Step 4: Run tests**

```bash
poetry run pytest tests/test_message_queue.py -v
```
Expected: All PASS.

**Step 5: Commit**

```bash
git add src/chargeghost_evse/bridge/message_queue.py tests/test_message_queue.py
git commit -m "feat: add drain method to MessageQueue for replaying buffered messages

drain() replays all messages via adapter send methods. Failed messages
are re-queued with incremented attempts. Messages exceeding max_attempts
are dropped."
```

---

### Task 6: Integrate MessageQueue into Bridge

**Files:**
- Modify: `src/chargeghost_evse/bridge/bridge.py`
- Modify: `src/chargeghost_evse/util/config.py`

**Step 1: Add `persist_message_queue` to SimulationConfig**

In `src/chargeghost_evse/util/config.py`, add to `SimulationConfig`:

```python
# Message queue persistence
persist_message_queue: bool = False
```

Update `load()` to read it:
```python
persist_message_queue=data.get("persist_message_queue", False),
```

Update `save()` to write it:
```python
"persist_message_queue": self.persist_message_queue,
```

**Step 2: Add MessageQueue to Bridge**

In `src/chargeghost_evse/bridge/bridge.py`, add imports:

```python
from chargeghost_evse.bridge.message_queue import (
	InMemoryBackend,
	JsonFileBackend,
	MessageQueue,
)
from pathlib import Path
```

In `Bridge.__init__`, after `self._shutdown_event`:

```python
# Offline message queue
self._message_queue = self._create_message_queue(persist=persist_message_queue)
```

Add the `persist_message_queue` parameter to `Bridge.__init__`:

```python
def __init__(
	self,
	engine: Engine,
	url: str = "wss://localhost:3000/CP_1",
	charge_point_id: str = "CP_1",
	password: str = "",
	skip_tls_verify: bool = False,
	charge_point_model: str = "ChargeGhostV1",
	charge_point_vendor: str = "ChargeGhost",
	persist_message_queue: bool = False,
) -> None:
```

Add the factory method:

```python
def _create_message_queue(self, persist: bool) -> MessageQueue:
	"""Create message queue with appropriate backend."""
	if persist:
		filepath = Path.home() / ".chargeghost" / "message_queue.json"
		backend = JsonFileBackend(filepath)
	else:
		backend = InMemoryBackend()
	return MessageQueue(backend=backend, max_attempts=3)
```

**Step 3: Update Bridge event handlers to enqueue when disconnected**

Update `on_engine_session_started` (around line 680):

```python
def on_engine_session_started(self, connector_id: int) -> None:
	adapter = self.runner.adapter
	loop = self.runner.loop

	session = self.engine.session
	if not session:
		return

	self._log(message=f"Session started on connector {connector_id}")
	id_tag = session.id_tag or "UNKNOWN_TAG"

	if not adapter or not loop:
		self._message_queue.enqueue("StartTransaction", {
			"connector_id": connector_id,
			"id_tag": id_tag,
			"meter_start": int(self.engine.energy_meter.get_meter_reading()),
			"timestamp": datetime.now(timezone.utc).isoformat(),
		})
		self._log(message=f"[yellow]Queued[/yellow] StartTransaction (offline)")
		return

	# ... existing send_start_tx logic unchanged ...
```

Update `on_engine_session_stopped` (around line 708):

```python
def on_engine_session_stopped(self, connector_id: int) -> None:
	last_session = self.engine.last_stopped_session
	if not last_session:
		self._log(message=f"No session info available for connector {connector_id}")
		return

	transaction_id = last_session.get("transaction_id", 0)
	meter_stop = last_session.get("meter_stop", 0)
	reason = last_session.get("reason", "Local")

	self._log(
		message=f"Session stopped on connector {connector_id}, tx_id={transaction_id}, reason={reason}"
	)

	adapter = self.runner.adapter
	loop = self.runner.loop
	if not adapter or not loop:
		self._message_queue.enqueue("StopTransaction", {
			"meter_stop": int(meter_stop),
			"timestamp": datetime.now(timezone.utc).isoformat(),
			"transaction_id": transaction_id,
			"reason": reason,
		})
		self._log(message=f"[yellow]Queued[/yellow] StopTransaction (offline)")
		return

	# ... existing send logic unchanged ...
```

Update `_meter_values_loop` — in the block where `adapter and loop` is checked (around line 611):

```python
if adapter and loop:
	# ... existing send logic ...
else:
	# Queue meter values when disconnected
	self._message_queue.enqueue("MeterValues", {
		"connector_id": self.engine.session.connector_id,
		"value": self.engine.energy_meter.get_meter_reading(),
		"transaction_id": self.engine.session.transaction_id,
	})
```

**Step 4: Drain queue on reconnect**

Update `_on_adapter_registered`:

```python
def _on_adapter_registered(self) -> None:
	"""Called after each successful boot notification / registration."""
	self._send_initial_status_notifications()
	self._inject_limit_getter()
	self._drain_message_queue()
	self._log(
		message="[cyan]OCPP:[/cyan] Adapter registered, sending initial status and enabling charging profiles"
	)

def _drain_message_queue(self) -> None:
	"""Replay queued messages after reconnection."""
	if self._message_queue.size == 0:
		return

	adapter = self.runner.adapter
	loop = self.runner.loop
	if not adapter or not loop:
		return

	self._log(
		message=f"[cyan]Queue:[/cyan] Draining {self._message_queue.size} buffered message(s)..."
	)

	async def _do_drain():
		sent = await self._message_queue.drain(adapter)
		remaining = self._message_queue.size
		self._log(
			message=f"[cyan]Queue:[/cyan] Sent {sent} message(s), {remaining} remaining"
		)

	future = asyncio.run_coroutine_threadsafe(_do_drain(), loop)
	future.add_done_callback(self._handle_future_error)
```

**Step 5: Run full test suite**

```bash
poetry run pytest -x
```
Expected: All PASS.

**Step 6: Commit**

```bash
git add src/chargeghost_evse/bridge/bridge.py src/chargeghost_evse/util/config.py
git commit -m "feat: integrate MessageQueue into Bridge for offline buffering

Bridge now enqueues StartTransaction, StopTransaction, and MeterValues
when disconnected. Messages are drained on reconnect. Configurable
persistence via persist_message_queue config flag."
```

---

### Task 7: Update Bridge callers to pass persist_message_queue

**Files:**
- Modify: `src/chargeghost_evse/ui/app.py` (or wherever Bridge is instantiated)

**Step 1: Find Bridge instantiation**

Search for `Bridge(` in the UI layer. It's likely in `app.py` or a setup function. Pass the config value:

```python
bridge = Bridge(
	engine=engine,
	url=config.connection_url,
	# ... existing params ...
	persist_message_queue=config.persist_message_queue,
)
```

**Step 2: Run full test suite**

```bash
poetry run pytest -x
```
Expected: All PASS.

**Step 3: Commit**

```bash
git add src/chargeghost_evse/ui/app.py
git commit -m "feat: pass persist_message_queue config to Bridge"
```

---

## Feature 3: CallError Handling

### Task 8: Add structured CallError handler to Bridge

**Files:**
- Modify: `src/chargeghost_evse/bridge/bridge.py`
- Create: `tests/test_callerror_handling.py`

**Step 1: Write failing tests**

Create `tests/test_callerror_handling.py`:

```python
import asyncio
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
		bridge.on_log.subscribe(lambda message, **kw: logs.append(message))

		# Simulate an OCPP error
		future = asyncio.Future()
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
```

**Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_callerror_handling.py -v
```
Expected: FAIL — current code doesn't enqueue on failure.

**Step 3: Update Bridge event handlers with error recovery**

Update `on_engine_session_stopped` to catch send failures and enqueue:

```python
def on_engine_session_stopped(self, connector_id: int) -> None:
	last_session = self.engine.last_stopped_session
	if not last_session:
		self._log(message=f"No session info available for connector {connector_id}")
		return

	transaction_id = last_session.get("transaction_id", 0)
	meter_stop = last_session.get("meter_stop", 0)
	reason = last_session.get("reason", "Local")
	stop_kwargs = {
		"meter_stop": int(meter_stop),
		"timestamp": datetime.now(timezone.utc).isoformat(),
		"transaction_id": transaction_id,
		"reason": reason,
	}

	self._log(
		message=f"Session stopped on connector {connector_id}, tx_id={transaction_id}, reason={reason}"
	)

	adapter = self.runner.adapter
	loop = self.runner.loop
	if not adapter or not loop:
		self._message_queue.enqueue("StopTransaction", stop_kwargs)
		self._log(message=f"[yellow]Queued[/yellow] StopTransaction (offline)")
		return

	async def _send_stop():
		try:
			await adapter.send_stop_transaction(**stop_kwargs)
		except Exception as e:
			self._log(
				message=f"[red]StopTransaction failed:[/red] {type(e).__name__}: {e}"
			)
			self._message_queue.enqueue("StopTransaction", stop_kwargs)
			self._log(message=f"[yellow]Queued[/yellow] StopTransaction for retry")

	future = asyncio.run_coroutine_threadsafe(_send_stop(), loop)
	future.add_done_callback(self._handle_future_error)
```

Apply the same pattern to `on_engine_session_started`:

```python
def on_engine_session_started(self, connector_id: int) -> None:
	adapter = self.runner.adapter
	loop = self.runner.loop

	session = self.engine.session
	if not session:
		return

	self._log(message=f"Session started on connector {connector_id}")
	id_tag = session.id_tag or "UNKNOWN_TAG"
	start_kwargs = {
		"connector_id": connector_id,
		"id_tag": id_tag,
		"meter_start": int(self.engine.energy_meter.get_meter_reading()),
		"timestamp": datetime.now(timezone.utc).isoformat(),
	}

	if not adapter or not loop:
		self._message_queue.enqueue("StartTransaction", start_kwargs)
		self._log(message=f"[yellow]Queued[/yellow] StartTransaction (offline)")
		return

	async def send_start_tx() -> None:
		try:
			response = await adapter.send_start_transaction(**start_kwargs)
			if response and response.transaction_id and self.engine.session is session:
				session.transaction_id = response.transaction_id
				self._log(message=f"Transaction ID assigned: {response.transaction_id}")
		except Exception as e:
			self._log(
				message=f"[red]StartTransaction failed:[/red] {type(e).__name__}: {e}"
			)
			self._message_queue.enqueue("StartTransaction", start_kwargs)
			self._log(message=f"[yellow]Queued[/yellow] StartTransaction for retry")

	future = asyncio.run_coroutine_threadsafe(send_start_tx(), loop)
	future.add_done_callback(self._handle_future_error)
```

**Step 4: Run tests**

```bash
poetry run pytest tests/test_callerror_handling.py -v
poetry run pytest -x
```
Expected: All PASS.

**Step 5: Commit**

```bash
git add src/chargeghost_evse/bridge/bridge.py tests/test_callerror_handling.py
git commit -m "feat: add CallError recovery — failed sends enqueue for retry

StartTransaction and StopTransaction failures are caught and enqueued
to the message queue for retry on reconnection. Integrates CallError
handling with offline message buffering."
```

---

### Task 9: Update OCPP_MISSING_FEATURES.md

**Files:**
- Modify: `OCPP_MISSING_FEATURES.md`

**Step 1: Update the robustness section**

Mark the three implemented items:

```markdown
### Logic & Robustness
- [x] **Message Queuing (Offline)**: Buffering mandatory messages (like `MeterValues`, `StopTransaction`) when the connection is lost and re-sending them upon reconnection.
- [x] **CallError Handling**: Gracefully handling error responses from the Central System for all message types.
- [x] **State Machine Validation**: Ensuring strict adherence to connector states (e.g., not allowing a transaction to start if the connector is `Faulted` or `Inoperative`).
```

**Step 2: Commit**

```bash
git add OCPP_MISSING_FEATURES.md
git commit -m "docs: mark robustness features as implemented in OCPP status"
```

---

### Task 10: Final verification

**Step 1: Run full test suite**

```bash
poetry run pytest -v
```
Expected: All PASS.

**Step 2: Run linter and type checker**

```bash
poetry run ruff check src/
poetry run mypy src/
```
Expected: No errors.

**Step 3: Verify no regressions**

```bash
poetry run pytest tests/test_engine.py tests/test_connector.py tests/test_bridge_inject.py -v
```
Expected: All PASS — existing tests still work with the new return types.
