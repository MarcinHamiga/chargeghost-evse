import json
from datetime import datetime
from pathlib import Path

import pytest

from chargeghost_evse.util.event import Event


class _FakeEngine:
	def __init__(self):
		self.on_log = Event()


class _FakeBridge:
	def __init__(self):
		self.on_log = Event()


class TestSessionFileLogger:
	def test_creates_log_file_on_init(self, tmp_path):
		from chargeghost_evse.util.session_logger import SessionFileLogger

		engine = _FakeEngine()
		bridge = _FakeBridge()
		logger = SessionFileLogger(engine, bridge, log_dir=tmp_path)

		files = list(tmp_path.iterdir())
		assert len(files) == 1
		assert files[0].suffix == ".jsonl"
		assert files[0].name.startswith("session-")

		logger.close()

	def test_engine_log_written_as_json_line(self, tmp_path):
		from chargeghost_evse.util.session_logger import SessionFileLogger

		engine = _FakeEngine()
		bridge = _FakeBridge()
		logger = SessionFileLogger(engine, bridge, log_dir=tmp_path)

		engine.on_log.emit(message="Engine started", is_ocpp_message=False, is_important=True)
		logger.close()

		log_file = next(tmp_path.iterdir())
		lines = log_file.read_text().strip().splitlines()
		assert len(lines) == 1
		record = json.loads(lines[0])
		assert record["source"] == "Engine"
		assert record["message"] == "Engine started"
		assert record["is_ocpp_message"] is False
		assert record["is_important"] is True
		assert "ts" in record
		parsed_ts = datetime.fromisoformat(record["ts"])
		assert parsed_ts.tzinfo is not None  # must be timezone-aware (UTC)

	def test_bridge_log_written_as_json_line(self, tmp_path):
		from chargeghost_evse.util.session_logger import SessionFileLogger

		engine = _FakeEngine()
		bridge = _FakeBridge()
		logger = SessionFileLogger(engine, bridge, log_dir=tmp_path)

		bridge.on_log.emit(message="BootNotification sent", is_ocpp_message=True, is_important=True)
		logger.close()

		log_file = next(tmp_path.iterdir())
		lines = log_file.read_text().strip().splitlines()
		assert len(lines) == 1
		record = json.loads(lines[0])
		assert record["source"] == "OCPP"
		assert record["message"] == "BootNotification sent"
		assert record["is_ocpp_message"] is True

	def test_rich_markup_stripped_from_message(self, tmp_path):
		from chargeghost_evse.util.session_logger import SessionFileLogger

		engine = _FakeEngine()
		bridge = _FakeBridge()
		logger = SessionFileLogger(engine, bridge, log_dir=tmp_path)

		engine.on_log.emit(
			message="[yellow]Engine:[/yellow] Session started",
			is_ocpp_message=False,
			is_important=True,
		)
		logger.close()

		log_file = next(tmp_path.iterdir())
		record = json.loads(log_file.read_text().strip())
		assert record["message"] == "Engine: Session started"
		assert "[" not in record["message"]

	def test_multiple_events_produce_multiple_lines(self, tmp_path):
		from chargeghost_evse.util.session_logger import SessionFileLogger

		engine = _FakeEngine()
		bridge = _FakeBridge()
		logger = SessionFileLogger(engine, bridge, log_dir=tmp_path)

		engine.on_log.emit(message="first", is_ocpp_message=False, is_important=True)
		bridge.on_log.emit(message="second", is_ocpp_message=True, is_important=True)
		engine.on_log.emit(message="third", is_ocpp_message=False, is_important=False)
		logger.close()

		log_file = next(tmp_path.iterdir())
		lines = log_file.read_text().strip().splitlines()
		assert len(lines) == 3

	def test_missing_kwargs_use_defaults(self, tmp_path):
		from chargeghost_evse.util.session_logger import SessionFileLogger

		engine = _FakeEngine()
		bridge = _FakeBridge()
		logger = SessionFileLogger(engine, bridge, log_dir=tmp_path)

		# Emit with only message (no is_ocpp_message or is_important)
		engine.on_log.emit(message="bare message")
		logger.close()

		log_file = next(tmp_path.iterdir())
		record = json.loads(log_file.read_text().strip())
		assert record["is_ocpp_message"] is False
		assert record["is_important"] is True

	def test_close_is_idempotent(self, tmp_path):
		from chargeghost_evse.util.session_logger import SessionFileLogger

		engine = _FakeEngine()
		bridge = _FakeBridge()
		logger = SessionFileLogger(engine, bridge, log_dir=tmp_path)
		logger.close()
		logger.close()  # Should not raise
