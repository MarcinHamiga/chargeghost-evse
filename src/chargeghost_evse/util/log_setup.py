import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from chargeghost_evse.util.markup import strip_markup

_LOG_DIR = Path.home() / ".chargeghost" / "logs"

EXTRA_KEYS = (
	"source",
	"ocpp_direction",
	"ocpp_action",
	"ocpp_message_id",
	"ocpp_payload",
	"ocpp_correlated_id",
	"connector_id",
	"transition_from",
	"transition_to",
	"evaluated_profiles",
	"winning_profile",
	"computed_limit_amps",
	"reason",
)


class JsonLogFormatter(logging.Formatter):
	"""Formats log records as JSON lines with structured extra fields."""

	def format(self, record: logging.LogRecord) -> str:
		entry: dict = {
			"ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
			"level": record.levelname,
			"logger": record.name,
			"message": strip_markup(record.getMessage()),
		}
		for key in EXTRA_KEYS:
			if hasattr(record, key):
				entry[key] = getattr(record, key)
		return json.dumps(entry)


class LogBridgeHandler(logging.Handler):
	"""Routes Python log records to a Qt Signal for UI consumption.

	The signal parameter is typed as ``object`` because PySide6 signals
	are defined with ``Signal(object)`` to avoid Qt meta-type registration
	issues with ``logging.LogRecord``.
	"""

	def __init__(self, signal: object) -> None:
		super().__init__()
		self.signal = signal

	def emit(self, record: logging.LogRecord) -> None:
		self.signal.emit(record)  # type: ignore[attr-defined]


def setup_file_logging(
	log_dir: Optional[Path] = None,
) -> RotatingFileHandler:
	"""
	Create and return a RotatingFileHandler with JSON formatting.

	Args:
		log_dir: Directory for log files. Defaults to ~/.chargeghost/logs/.

	Returns:
		Configured RotatingFileHandler (caller must attach to a logger).
	"""
	log_dir = log_dir or _LOG_DIR
	log_dir.mkdir(parents=True, exist_ok=True)

	handler = RotatingFileHandler(
		log_dir / "chargeghost.log",
		maxBytes=5 * 1024 * 1024,
		backupCount=5,
	)
	handler.setLevel(logging.DEBUG)
	handler.setFormatter(JsonLogFormatter())
	return handler
