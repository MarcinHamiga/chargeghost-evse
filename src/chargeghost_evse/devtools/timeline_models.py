from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass
class TimelineEvent:
    event_id: int
    timestamp: str
    source: Literal["ui", "engine", "bridge", "ocpp"]
    direction: Literal["inbound", "outbound", "local"]
    event_type: Literal["frame", "status_change", "session", "action", "queue", "error"]
    protocol_version: str
    action: str
    message_id: str
    connector_id: int
    transaction_id: int
    level: int
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_key: str = ""
    tags: list[str] = field(default_factory=list)

    def build_correlation_key(self) -> str:
        """Build correlation key from action and message_id."""
        if self.message_id:
            return f"{self.action}:{self.message_id}"
        return self.action


@dataclass
class TimelineFilter:
    source: Optional[Literal["ui", "engine", "bridge", "ocpp"]] = None
    direction: Optional[Literal["inbound", "outbound", "local"]] = None
    event_type: Optional[
        Literal["frame", "status_change", "session", "action", "queue", "error"]
    ] = None
    action: Optional[str] = None
    connector_id: Optional[int] = None
    transaction_id: Optional[int] = None
    min_level: Optional[int] = None
    tags: Optional[list[str]] = None
    search: Optional[str] = None

    def matches(self, event: TimelineEvent) -> bool:
        if self.source is not None and event.source != self.source:
            return False
        if self.direction is not None and event.direction != self.direction:
            return False
        if self.event_type is not None and event.event_type != self.event_type:
            return False
        if self.action is not None and event.action != self.action:
            return False
        if self.connector_id is not None and event.connector_id != self.connector_id:
            return False
        if (
            self.transaction_id is not None
            and event.transaction_id != self.transaction_id
        ):
            return False
        if self.min_level is not None and event.level < self.min_level:
            return False
        if self.tags is not None:
            if not any(tag in event.tags for tag in self.tags):
                return False
        if self.search is not None:
            search_lower = self.search.lower()
            if search_lower not in event.summary.lower():
                return False
        return True
