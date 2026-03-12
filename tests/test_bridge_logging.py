import logging
from unittest.mock import MagicMock

from chargeghost_evse.bridge.bridge import AsyncRunner


class TestBridgeLogging:
	def test_runner_uses_python_logger(self):
		runner = AsyncRunner(
			url="ws://localhost:9000/test",
			charge_point_id="CP_1",
			password="",
			command_queue=MagicMock(),
		)
		assert hasattr(runner, 'logger')
		assert runner.logger.name == "chargeghost.bridge"

	def test_runner_log_emits(self, caplog):
		runner = AsyncRunner(
			url="ws://localhost:9000/test",
			charge_point_id="CP_1",
			password="",
			command_queue=MagicMock(),
		)
		with caplog.at_level(logging.DEBUG, logger="chargeghost.bridge"):
			runner._log(message="connecting")
		assert len(caplog.records) == 1
		assert caplog.records[0].source == "bridge"

	def test_runner_no_on_log_event(self):
		runner = AsyncRunner(
			url="ws://localhost:9000/test",
			charge_point_id="CP_1",
			password="",
			command_queue=MagicMock(),
		)
		assert not hasattr(runner, 'on_log')
