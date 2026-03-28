import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from chargeghost_evse.util.event import Event

from chargeghost_evse.devtools.timeline_models import TimelineEvent, TimelineFilter


class TimelineStore:
    def __init__(self, max_length: int = 1000) -> None:
        self._events: deque[TimelineEvent] = deque(maxlen=max_length)
        self._max_length = max_length
        self._next_id: int = 1
        self._lock = threading.Lock()
        self.on_event = Event()

    @property
    def max_length(self) -> int:
        return self._max_length

    @property
    def count(self) -> int:
        return len(self._events)

    def append(
        self,
        source: Literal["ui", "engine", "bridge", "ocpp"],
        direction: Literal["inbound", "outbound", "local"],
        event_type: Literal[
            "frame", "status_change", "session", "action", "queue", "error"
        ],
        action: str,
        message_id: str = "",
        connector_id: int = 0,
        transaction_id: int = 0,
        level: int = 20,
        summary: str = "",
        payload: Optional[dict[str, Any]] = None,
        correlation_key: str = "",
        tags: Optional[list[str]] = None,
        protocol_version: str = "ocpp1.6",
    ) -> TimelineEvent:
        with self._lock:
            event_id = self._next_id
            self._next_id += 1
            event = TimelineEvent(
                event_id=event_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                source=source,
                direction=direction,
                event_type=event_type,
                protocol_version=protocol_version,
                action=action,
                message_id=message_id,
                connector_id=connector_id,
                transaction_id=transaction_id,
                level=level,
                summary=summary,
                payload=payload or {},
                correlation_key=correlation_key,
                tags=tags or [],
            )
            self._events.append(event)
            self.on_event.emit(event)
        return event

    def all(self) -> list[TimelineEvent]:
        with self._lock:
            return list(self._events)

    def filtered(
        self, filter_func: Callable[[TimelineEvent], bool]
    ) -> list[TimelineEvent]:
        with self._lock:
            return [e for e in self._events if filter_func(e)]

    def query(self, filter_obj: Optional[TimelineFilter] = None) -> list[TimelineEvent]:
        if filter_obj is None:
            return self.all()
        return self.filtered(filter_obj.matches)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
