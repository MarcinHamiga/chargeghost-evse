import logging
from unittest.mock import AsyncMock, MagicMock

from chargeghost_evse.ocpp_adapter.adapter import Adapter


def _make_adapter() -> Adapter:
	"""Create an Adapter with mocked connection for testing."""
	mock_conn = MagicMock()
	mock_conn.recv = AsyncMock()
	mock_conn.send = AsyncMock()
	adapter = Adapter(
		id="CP_1",
		connection=mock_conn,
		command_queue=MagicMock(),
	)
	return adapter


class TestAdapterLogging:
	def test_adapter_has_python_logger(self):
		adapter = _make_adapter()
		assert hasattr(adapter, 'logger')
		assert adapter.logger.name == "chargeghost.ocpp"
		assert adapter._tx_logger.name == "chargeghost.ocpp.tx"

	def test_adapter_no_on_log_event(self):
		adapter = _make_adapter()
		assert not hasattr(adapter, 'on_log')

	def test_adapter_log_emits_to_python_logging(self, caplog):
		adapter = _make_adapter()
		with caplog.at_level(logging.DEBUG, logger="chargeghost.ocpp"):
			adapter._log("test config change")
		assert len(caplog.records) >= 1
		assert caplog.records[0].source == "ocpp"
