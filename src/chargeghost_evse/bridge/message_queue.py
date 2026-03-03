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
