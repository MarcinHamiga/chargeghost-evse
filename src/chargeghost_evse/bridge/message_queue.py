"""
Offline message queue for buffering OCPP messages during disconnection.

When the WebSocket connection drops, transaction-critical messages
(StartTransaction, StopTransaction, MeterValues) are buffered here
and replayed on reconnection per OCPP 1.6 section 4.9.
"""

import json
import logging
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

_logger = logging.getLogger(__name__)


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
