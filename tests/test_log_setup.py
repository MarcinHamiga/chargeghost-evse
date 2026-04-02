import json
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock

from chargeghost_evse.util.log_setup import JsonLogFormatter, LogBridgeHandler


class TestJsonLogFormatter:
	def _make_record(self, message: str, **extra) -> logging.LogRecord:
		record = logging.LogRecord(
			name="chargeghost.engine",
			level=logging.INFO,
			pathname="",
			lineno=0,
			msg=message,
			args=None,
			exc_info=None,
		)
		for k, v in extra.items():
			setattr(record, k, v)
		return record

	def test_basic_fields(self):
		formatter = JsonLogFormatter()
		record = self._make_record("hello")
		output = json.loads(formatter.format(record))
		assert output["message"] == "hello"
		assert output["level"] == "INFO"
		assert output["logger"] == "chargeghost.engine"
		assert "ts" in output
		parsed = datetime.fromisoformat(output["ts"])
		assert parsed.tzinfo is not None

	def test_strips_rich_markup(self):
		formatter = JsonLogFormatter()
		record = self._make_record("[yellow]Engine:[/yellow] started")
		output = json.loads(formatter.format(record))
		assert output["message"] == "Engine: started"

	def test_includes_extra_fields(self):
		formatter = JsonLogFormatter()
		record = self._make_record("test", source="engine", connector_id=1)
		output = json.loads(formatter.format(record))
		assert output["source"] == "engine"
		assert output["connector_id"] == 1

	def test_includes_ocpp_fields(self):
		formatter = JsonLogFormatter()
		record = self._make_record(
			"TX BootNotification",
			ocpp_direction="TX",
			ocpp_action="BootNotification",
			ocpp_payload={"vendor": "ChargeGhost"},
		)
		output = json.loads(formatter.format(record))
		assert output["ocpp_direction"] == "TX"
		assert output["ocpp_action"] == "BootNotification"
		assert output["ocpp_payload"] == {"vendor": "ChargeGhost"}

	def test_omits_absent_extra_fields(self):
		formatter = JsonLogFormatter()
		record = self._make_record("plain")
		output = json.loads(formatter.format(record))
		assert "ocpp_direction" not in output
		assert "connector_id" not in output

	def test_includes_falsy_extra_fields(self):
		formatter = JsonLogFormatter()
		record = self._make_record("limit hit", computed_limit_amps=0.0, connector_id=0)
		output = json.loads(formatter.format(record))
		assert "computed_limit_amps" in output
		assert output["computed_limit_amps"] == 0.0
		assert "connector_id" in output
		assert output["connector_id"] == 0

	def test_json_formatter_includes_fault_fields(self):
		formatter = JsonLogFormatter()
		record = self._make_record(
			"fault triggered",
			fault_id="frozen_meter",
			fault_enabled=True,
			fault_trigger_count=3,
			fault_scope="meter",
		)
		output = json.loads(formatter.format(record))
		assert output["fault_id"] == "frozen_meter"
		assert output["fault_enabled"] is True
		assert output["fault_trigger_count"] == 3
		assert output["fault_scope"] == "meter"


class TestLogBridgeHandler:
	def test_emit_calls_signal(self):
		mock_signal = MagicMock()
		handler = LogBridgeHandler(mock_signal)
		record = logging.LogRecord(
			name="chargeghost.engine",
			level=logging.INFO,
			pathname="",
			lineno=0,
			msg="test",
			args=None,
			exc_info=None,
		)
		handler.emit(record)
		mock_signal.emit.assert_called_once_with(record)

	def test_signal_attribute_is_public(self):
		mock_signal = MagicMock()
		handler = LogBridgeHandler(mock_signal)
		assert handler.signal is mock_signal

	def test_handler_level_filtering(self):
		mock_signal = MagicMock()
		handler = LogBridgeHandler(mock_signal)
		handler.setLevel(logging.WARNING)

		logger = logging.getLogger("chargeghost.test.bridge_handler")
		logger.addHandler(handler)
		logger.setLevel(logging.DEBUG)

		logger.debug("ignored")
		logger.warning("shown")

		assert mock_signal.emit.call_count == 1
		assert mock_signal.emit.call_args[0][0].getMessage() == "shown"

		logger.removeHandler(handler)


class TestSetupFileLogging:
	def test_creates_log_file(self, tmp_path):
		from chargeghost_evse.util.log_setup import setup_file_logging

		handler = setup_file_logging(log_dir=tmp_path)
		logger = logging.getLogger("chargeghost.test.file")
		logger.addHandler(handler)
		logger.setLevel(logging.DEBUG)

		logger.info("test message", extra={"source": "engine"})
		handler.flush()

		log_file = tmp_path / "chargeghost.log"
		assert log_file.exists()
		line = log_file.read_text().strip()
		record = json.loads(line)
		assert record["message"] == "test message"
		assert record["source"] == "engine"
		assert record["level"] == "INFO"

		logger.removeHandler(handler)
		handler.close()

	def test_strips_markup_in_file(self, tmp_path):
		from chargeghost_evse.util.log_setup import setup_file_logging

		handler = setup_file_logging(log_dir=tmp_path)
		logger = logging.getLogger("chargeghost.test.file2")
		logger.addHandler(handler)
		logger.setLevel(logging.DEBUG)

		logger.info("[yellow]Engine:[/yellow] started")
		handler.flush()

		log_file = tmp_path / "chargeghost.log"
		record = json.loads(log_file.read_text().strip())
		assert record["message"] == "Engine: started"

		logger.removeHandler(handler)
		handler.close()
