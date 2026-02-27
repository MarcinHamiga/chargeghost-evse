"""
OCPP Message Logger Module.

This module provides functionality for parsing, filtering, and formatting
OCPP (Open Charge Point Protocol) messages for display in the UI. It
supports both verbose (full JSON) and compact (summarized) logging modes.

The logger parses OCPP message arrays to extract action names and payloads,
identifying important message types that should always be displayed.

Classes:
    LogLevel: Enumeration of logging verbosity levels.
    OcppMessageType: Enumeration of OCPP message types.
    OcppLogEntry: Parsed representation of an OCPP message.
    OcppLogger: Logger for filtering and formatting OCPP messages.

Constants:
    IMPORTANT_OCPP_MESSAGES: Set of message actions always shown in compact mode.

Functions:
    parse_ocpp_message: Convenience function to parse raw OCPP messages.

Example:
    >>> from chargeghost_evse.util.ocpp_logger import OcppLogger, LogLevel
    >>> 
    >>> logger = OcppLogger(LogLevel.COMPACT)
    >>> entry = parse_ocpp_message('[2,"1234","StartTransaction",{"idTag":"ABC"}]', "TX")
    >>> if logger.should_log(entry):
    ...     print(logger.format_message(entry))
    StartTransaction {"idTag": "ABC"}
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import json


class LogLevel(Enum):
    """
    OCPP logging verbosity level.

    Attributes:
        VERBOSE: Log all OCPP messages with full JSON formatting.
        COMPACT: Log only important messages in summarized format.
    """

    VERBOSE = "verbose"
    COMPACT = "compact"


class OcppMessageType(Enum):
    """
    Type classification for OCPP messages.

    Attributes:
        REQUEST: OCPP CALL message (message type 2, from CP to CSMS or vice versa).
        RESPONSE: OCPP CALLRESULT message (message type 3, response to a request).
        INTERNAL: Non-OCPP internal message or unparseable content.
    """

    REQUEST = "request"
    RESPONSE = "response"
    INTERNAL = "internal"


# Set of OCPP actions that are considered important enough to always log
# These are shown even in compact mode
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
    """
    Parsed representation of an OCPP message for logging.

    This class extracts relevant information from raw OCPP JSON messages
    for display purposes. It identifies message types, actions, and
    determines importance for filtering.

    Attributes:
        message_type: Classification of the message (request/response/internal).
        ocpp_action: OCPP action name (e.g., "StartTransaction"), or None.
        direction: Message direction ("TX" for transmitted, "RX" for received).
        body: Formatted message body (pretty-printed JSON for OCPP messages).
        is_important: Whether this message is in IMPORTANT_OCPP_MESSAGES.
        raw_message: Original raw message string.

    Example:
        >>> entry = OcppLogEntry.from_raw('[2,"1","Heartbeat",{}]', "TX")
        >>> entry.ocpp_action
        'Heartbeat'
        >>> entry.is_important
        True
    """

    message_type: OcppMessageType
    ocpp_action: Optional[str]
    direction: Optional[str]
    body: str
    is_important: bool
    raw_message: str

    @classmethod
    def from_raw(cls, raw: str, direction: str = "TX") -> "OcppLogEntry":
        """
        Parse a raw OCPP message string into a log entry.

        OCPP messages are JSON arrays with the following structure:
        - CALL (type 2): [2, uniqueId, action, payload]
        - CALLRESULT (type 3): [3, uniqueId, payload]
        - CALLERROR (type 4): [4, uniqueId, errorCode, errorDescription, details]

        Args:
            raw: Raw message string (JSON array or plain text).
            direction: Message direction indicator ("TX" or "RX").

        Returns:
            OcppLogEntry with parsed message information.
            If parsing fails, returns an INTERNAL type entry with raw content.
        """
        message_type = OcppMessageType.INTERNAL
        ocpp_action = None
        body = raw
        is_important = False

        try:
            data = json.loads(raw)
            if isinstance(data, list) and len(data) >= 3:
                # Determine message type from array structure
                message_type = (
                    OcppMessageType.REQUEST
                    if data[0] == 2
                    else OcppMessageType.RESPONSE
                )

                # Extract action name (only present in CALL messages)
                ocpp_action = data[2] if data[0] == 2 else None

                # For responses, try to get action from response object
                if data[0] == 3 and len(data) >= 3:
                    ocpp_action = getattr(data[2], "__class__", {}).get(
                        "__name__", "Response"
                    )

                # Format body as pretty-printed JSON
                if data[0] == 2:
                    payload = data[3] if len(data) > 3 else {}
                    body = json.dumps(payload, indent=2)
                else:
                    body = json.dumps(data[2] if len(data) > 2 else {}, indent=2)

                # Check if this action is important
                is_important = (
                    ocpp_action in IMPORTANT_OCPP_MESSAGES if ocpp_action else False
                )
        except (json.JSONDecodeError, TypeError):
            # Not valid JSON, treat as internal message
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
    """
    Logger for filtering and formatting OCPP messages.

    Provides methods to determine whether a message should be logged
    based on the current log level, and to format messages appropriately.

    Attributes:
        _level: Current logging verbosity level.

    Example:
        >>> logger = OcppLogger(LogLevel.COMPACT)
        >>> entry = parse_ocpp_message('[2,"1","MeterValues",{"meterValue":[1]}]', "TX")
        >>> if logger.should_log(entry):
        ...     formatted = logger.format_message(entry)
        ...     print(formatted)
        MeterValues {"meterValue": [1]}
    """

    def __init__(self, level: LogLevel = LogLevel.COMPACT) -> None:
        """
        Initialize the OCPP logger.

        Args:
            level: Initial logging verbosity level. Defaults to COMPACT.
        """
        self._level = level

    @property
    def level(self) -> LogLevel:
        """
        Get the current logging level.

        Returns:
            Current LogLevel value.
        """
        return self._level

    @level.setter
    def level(self, value: LogLevel) -> None:
        """
        Set the logging level.

        Args:
            value: New LogLevel to set.
        """
        self._level = value

    def should_log(self, entry: OcppLogEntry) -> bool:
        """
        Determine whether a log entry should be displayed.

        In VERBOSE mode, all messages are logged.
        In COMPACT mode, only important messages are logged.

        Args:
            entry: The OcppLogEntry to evaluate.

        Returns:
            True if the entry should be logged, False otherwise.
        """
        if self._level == LogLevel.VERBOSE:
            return True
        return entry.is_important

    def format_message(self, entry: OcppLogEntry, source: str = "OCPP") -> str:
        """
        Format a log entry for display.

        Delegates to the appropriate formatting method based on log level.

        Args:
            entry: The OcppLogEntry to format.
            source: Source identifier for the message (default "OCPP").

        Returns:
            Formatted message string, potentially with Rich markup.
        """
        if self._level == LogLevel.VERBOSE:
            return self._format_verbose(entry, source)
        return self._format_compact(entry, source)

    def _format_verbose(self, entry: OcppLogEntry, source: str) -> str:
        """
        Format a log entry in verbose mode.

        Shows direction indicator, action name (bold), and full JSON body.

        Args:
            entry: The OcppLogEntry to format.
            source: Source identifier (unused in verbose mode).

        Returns:
            Formatted message with Rich markup for bold action names.
        """
        if entry.ocpp_action:
            direction = f"[{entry.direction}]" if entry.direction else ""
            return f"{direction} [bold]{entry.ocpp_action}[/bold]\n{entry.body}"
        return entry.raw_message

    def _format_compact(self, entry: OcppLogEntry, source: str) -> str:
        """
        Format a log entry in compact mode.

        Shows action name (bold) followed by a single-line summary of the body.
        Long payloads are truncated to 100 characters.

        Args:
            entry: The OcppLogEntry to format.
            source: Source identifier (unused in compact mode).

        Returns:
            Formatted message with Rich markup for bold action names.
        """
        if entry.ocpp_action:
            # Collapse body to single line
            parts = entry.body.replace("\n", " ").replace("  ", " ").strip()
            # Truncate long payloads
            if len(parts) > 100:
                parts = parts[:97] + "..."
            return f"[bold]{entry.ocpp_action}[/bold] {parts}"
        return entry.raw_message


def parse_ocpp_message(raw: str, direction: str = "TX") -> OcppLogEntry:
    """
    Parse a raw OCPP message string into a log entry.

    This is a convenience function that delegates to OcppLogEntry.from_raw().

    Args:
        raw: Raw message string to parse.
        direction: Message direction ("TX" for transmit, "RX" for receive).

    Returns:
        Parsed OcppLogEntry instance.

    Example:
        >>> entry = parse_ocpp_message('[2,"1","Heartbeat",{}]', "TX")
        >>> entry.ocpp_action
        'Heartbeat'
    """
    return OcppLogEntry.from_raw(raw, direction)
