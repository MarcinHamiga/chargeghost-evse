import json
from typing import Any, Callable, Optional

from chargeghost_evse.devtools.timeline_models import TimelineEvent
from chargeghost_evse.devtools.timeline_store import TimelineStore
from chargeghost_evse.util.markup import strip_markup

MAX_PAYLOAD_SIZE = 10 * 1024

SENSITIVE_FIELDS = frozenset({"password", "ocpp_password", "idTag", "id_tag"})

EXPORT_FIELDS = (
    "event_id",
    "timestamp",
    "source",
    "direction",
    "event_type",
    "protocol_version",
    "action",
    "message_id",
    "connector_id",
    "transaction_id",
    "level",
    "summary",
    "payload",
    "correlation_key",
    "tags",
)


class TimelineExporter:
    def __init__(self, store: TimelineStore) -> None:
        self._store = store

    def export(
        self,
        output_path: Optional[str] = None,
        filter_func: Optional[Callable[[Any], bool]] = None,
        truncate_payloads: bool = True,
    ) -> str:
        events = self._store.filtered(filter_func) if filter_func else self._store.all()
        exported = [self._export_event(e, truncate_payloads) for e in events]
        json_str = json.dumps(exported, indent=2)

        if output_path is not None:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(json_str)

        return json_str

    def _export_event(
        self, event: TimelineEvent, truncate_payloads: bool = True
    ) -> dict[str, Any]:
        redacted_payload = self._redact_sensitive_fields(event.payload)

        if truncate_payloads:
            truncated, exceeded = self._truncate_payload(redacted_payload)
            if exceeded:
                truncated["payload_truncated"] = True
                payload_result: dict[str, Any] = truncated
            else:
                payload_result = redacted_payload
        else:
            payload_result = redacted_payload

        return {
            "event_id": event.event_id,
            "timestamp": event.timestamp,
            "source": event.source,
            "direction": event.direction,
            "event_type": event.event_type,
            "protocol_version": event.protocol_version,
            "action": event.action,
            "message_id": event.message_id,
            "connector_id": event.connector_id,
            "transaction_id": event.transaction_id,
            "level": event.level,
            "summary": strip_markup(event.summary),
            "payload": payload_result,
            "correlation_key": event.build_correlation_key(),
            "tags": list(event.tags),
        }

    def _redact_sensitive_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return payload

        redacted: dict[str, Any] = {}
        for key, value in payload.items():
            if key.lower() in SENSITIVE_FIELDS:
                redacted[key] = "***REDACTED***"
            elif isinstance(value, dict):
                redacted[key] = self._redact_sensitive_fields(value)
            elif isinstance(value, list):
                redacted[key] = [
                    self._redact_sensitive_fields(item)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                redacted[key] = value
        return redacted

    def _truncate_payload(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        serialized = json.dumps(payload, default=str)
        if len(serialized) <= MAX_PAYLOAD_SIZE:
            return payload, False

        summary: dict[str, Any] = {
            "_summary": f"Payload truncated. Original size: {len(serialized)} bytes",
            "_keys": list(payload.keys()) if isinstance(payload, dict) else "list",
        }
        return summary, True
