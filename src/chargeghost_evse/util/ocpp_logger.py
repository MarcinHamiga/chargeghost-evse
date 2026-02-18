from dataclasses import dataclass
from enum import Enum
from typing import Optional
import json


class LogLevel(Enum):
    VERBOSE = "verbose"
    COMPACT = "compact"


class OcppMessageType(Enum):
    REQUEST = "request"
    RESPONSE = "response"
    INTERNAL = "internal"


IMPORTANT_OCPP_MESSAGES = {
    "BootNotification",
    "StartTransaction",
    "StopTransaction",
    "Authorize",
    "RemoteStartTransaction",
    "RemoteStopTransaction",
    "StatusNotification",
    "MeterValues",
    "Heartbeat",
}


@dataclass
class OcppLogEntry:
    message_type: OcppMessageType
    ocpp_action: Optional[str]
    direction: Optional[str]
    body: str
    is_important: bool
    raw_message: str

    @classmethod
    def from_raw(cls, raw: str, direction: str = "TX") -> "OcppLogEntry":
        message_type = OcppMessageType.INTERNAL
        ocpp_action = None
        body = raw
        is_important = False

        try:
            data = json.loads(raw)
            if isinstance(data, list) and len(data) >= 3:
                message_type = (
                    OcppMessageType.REQUEST
                    if data[0] == 2
                    else OcppMessageType.RESPONSE
                )
                ocpp_action = data[2] if data[0] == 2 else None

                if data[0] == 3 and len(data) >= 3:
                    ocpp_action = getattr(data[2], "__class__", {}).get(
                        "__name__", "Response"
                    )

                if data[0] == 2:
                    payload = data[3] if len(data) > 3 else {}
                    body = json.dumps(payload, indent=2)
                else:
                    body = json.dumps(data[2] if len(data) > 2 else {}, indent=2)

                is_important = (
                    ocpp_action in IMPORTANT_OCPP_MESSAGES if ocpp_action else False
                )
        except (json.JSONDecodeError, TypeError):
            pass

        return cls(
            message_type=message_type,
            ocpp_action=ocpp_action,
            direction=direction,
            body=body,
            is_important=is_important,
            raw_message=raw,
        )


class OcppLogger:
    def __init__(self, level: LogLevel = LogLevel.COMPACT):
        self._level = level

    @property
    def level(self) -> LogLevel:
        return self._level

    @level.setter
    def level(self, value: LogLevel) -> None:
        self._level = value

    def should_log(self, entry: OcppLogEntry) -> bool:
        if self._level == LogLevel.VERBOSE:
            return True
        return entry.is_important

    def format_message(self, entry: OcppLogEntry, source: str = "OCPP") -> str:
        if self._level == LogLevel.VERBOSE:
            return self._format_verbose(entry, source)
        return self._format_compact(entry, source)

    def _format_verbose(self, entry: OcppLogEntry, source: str) -> str:
        if entry.ocpp_action:
            direction = f"[{entry.direction}]" if entry.direction else ""
            return f"{direction} [bold]{entry.ocpp_action}[/bold]\n{entry.body}"
        return entry.raw_message

    def _format_compact(self, entry: OcppLogEntry, source: str) -> str:
        if entry.ocpp_action:
            parts = entry.body.replace("\n", " ").replace("  ", " ").strip()
            if len(parts) > 100:
                parts = parts[:97] + "..."
            return f"[bold]{entry.ocpp_action}[/bold] {parts}"
        return entry.raw_message


def parse_ocpp_message(raw: str, direction: str = "TX") -> OcppLogEntry:
    return OcppLogEntry.from_raw(raw, direction)
