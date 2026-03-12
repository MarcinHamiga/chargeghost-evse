class TestQtSignalBridgeLogging:
	def test_has_log_record_received_signal(self):
		from chargeghost_evse.ui.bridge import QtSignalBridge
		assert hasattr(QtSignalBridge, 'log_record_received')

	def test_no_log_received_signal(self):
		from chargeghost_evse.ui.bridge import QtSignalBridge
		assert not hasattr(QtSignalBridge, 'log_received')
