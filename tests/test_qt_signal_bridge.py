class TestQtSignalBridgeLogging:
    def test_has_log_record_received_signal(self):
        from chargeghost_evse.ui.bridge import QtSignalBridge

        assert hasattr(QtSignalBridge, "log_record_received")

    def test_no_log_received_signal(self):
        from chargeghost_evse.ui.bridge import QtSignalBridge

        assert not hasattr(QtSignalBridge, "log_received")


class TestQtSignalBridgeTimeline:
    def test_has_timeline_event_received_signal(self):
        from chargeghost_evse.ui.bridge import QtSignalBridge

        assert hasattr(QtSignalBridge, "timeline_event_received")

    def test_set_timeline_store_subscribes_to_store_events(self):
        from unittest.mock import MagicMock
        from chargeghost_evse.engine.engine import Engine
        from chargeghost_evse.ui.bridge import QtSignalBridge

        engine = Engine()
        bridge = MagicMock()
        qt_bridge = QtSignalBridge(engine, bridge)

        mock_store = MagicMock()
        qt_bridge.set_timeline_store(mock_store)

        assert mock_store.on_event.subscribe.called
        call_args = mock_store.on_event.subscribe.call_args
        assert callable(call_args[0][0])

    def test_timeline_store_unsubscribe_called_on_replace(self):
        from unittest.mock import MagicMock
        from chargeghost_evse.engine.engine import Engine
        from chargeghost_evse.ui.bridge import QtSignalBridge

        engine = Engine()
        bridge = MagicMock()
        qt_bridge = QtSignalBridge(engine, bridge)

        mock_unsubscribe = MagicMock()
        mock_store = MagicMock()
        mock_store.on_event.subscribe.return_value = mock_unsubscribe

        qt_bridge.set_timeline_store(mock_store)
        assert qt_bridge._timeline_unsubscribe == mock_unsubscribe

        mock_store2 = MagicMock()
        qt_bridge.set_timeline_store(mock_store2)

        mock_unsubscribe.assert_called_once()
        assert qt_bridge._timeline_store == mock_store2


class TestQtSignalBridgeFault:
    def test_fault_changed_signal_exists(self):
        from chargeghost_evse.ui.bridge import QtSignalBridge

        assert hasattr(QtSignalBridge, "fault_changed")

    def test_set_fault_manager_subscribes(self):
        from unittest.mock import MagicMock
        from chargeghost_evse.engine.engine import Engine
        from chargeghost_evse.ui.bridge import QtSignalBridge

        engine = Engine()
        bridge = MagicMock()
        qt_bridge = QtSignalBridge(engine, bridge)

        mock_fault_manager = MagicMock()
        qt_bridge.set_fault_manager(mock_fault_manager)

        mock_fault_manager.fault_changed.subscribe.assert_called_once()
