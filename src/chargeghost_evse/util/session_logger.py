import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from chargeghost_evse.util.markup import strip_markup as _strip_markup

if TYPE_CHECKING:
	from chargeghost_evse.bridge.bridge import Bridge
	from chargeghost_evse.engine.engine import Engine

_LOG_DIR = Path.home() / ".chargeghost" / "logs"


class SessionFileLogger:
	"""
	Writes all on_log events from the Engine and Bridge to a per-session JSONL file.

	One file is created per app start at log_dir/session-<timestamp>.jsonl.
	Rich markup tags are stripped from messages before writing.
	All writes are protected by a threading.Lock for safety across the OCPP thread.
	"""

	def __init__(
		self,
		engine: "Engine",
		bridge: "Bridge",
		log_dir: Optional[Path] = None,
	) -> None:
		self._lock = threading.Lock()
		self._closed = False

		log_dir = log_dir or _LOG_DIR
		log_dir.mkdir(parents=True, exist_ok=True)

		timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
		log_path = log_dir / f"session-{timestamp}.jsonl"
		self._file = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
		try:
			engine.on_log.subscribe(self._on_engine_log)
			bridge.on_log.subscribe(self._on_bridge_log)
		except Exception:
			self._file.close()
			raise

	def _on_engine_log(self, message: str, **kwargs) -> None:
		self._write("Engine", message, **kwargs)

	def _on_bridge_log(self, message: str, **kwargs) -> None:
		self._write("OCPP", message, **kwargs)

	def _write(self, source: str, message: str, **kwargs) -> None:
		with self._lock:
			if self._closed:
				return
			record = {
				"ts": datetime.now(timezone.utc).isoformat(),
				"source": source,
				"message": _strip_markup(message),
				"is_ocpp_message": kwargs.get("is_ocpp_message", False),
				"is_important": kwargs.get("is_important", True),
			}
			self._file.write(json.dumps(record) + "\n")
			self._file.flush()

	def close(self) -> None:
		"""Flush and close the log file. Safe to call multiple times."""
		with self._lock:
			if self._closed:
				return
			self._closed = True
			self._file.close()
