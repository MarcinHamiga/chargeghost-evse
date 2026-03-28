import logging
from unittest.mock import AsyncMock, MagicMock

from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.devtools.timeline_store import TimelineStore
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.ocpp_adapter.adapter import Adapter


def _make_adapter(timeline_store: TimelineStore = None) -> Adapter:
	"""Create an Adapter with mocked connection for testing."""
	mock_conn = MagicMock()
	mock_conn.recv = AsyncMock()
	mock_conn.send = AsyncMock()
	adapter = Adapter(
		id="CP_1",
		connection=mock_conn,
		command_queue=MagicMock(),
	)
	if timeline_store is not None:
		adapter.timeline_store = timeline_store
	return adapter


class TestBaseAdapterTimelineCapture:
	def test_base_adapter_appends_outbound_timeline_event(self):
		store = TimelineStore(max_length=100)
		adapter = _make_adapter(timeline_store=store)

		adapter._log_ocpp_raw(
			"TX",
			"BootNotification",
			{"status": "Accepted"},
			"msg-1",
		)

		events = store.all()
		assert len(events) == 1
		event = events[0]
		assert event.direction == "outbound"
		assert event.source == "ocpp"
		assert event.event_type == "frame"
		assert event.action == "BootNotification"
		assert event.message_id == "msg-1"
		assert event.protocol_version == "ocpp1.6"
		assert event.payload == {"status": "Accepted"}

	def test_base_adapter_appends_inbound_timeline_event(self):
		store = TimelineStore(max_length=100)
		adapter = _make_adapter(timeline_store=store)

		adapter._log_ocpp_raw(
			"RX",
			"StartTransaction",
			{"id_tag": "ABCD1234", "connector_id": 1},
			"msg-2",
		)

		events = store.all()
		assert len(events) == 1
		event = events[0]
		assert event.direction == "inbound"
		assert event.source == "ocpp"
		assert event.event_type == "frame"
		assert event.action == "StartTransaction"
		assert event.message_id == "msg-2"
		assert event.protocol_version == "ocpp1.6"
		assert event.payload == {"id_tag": "ABCD1234", "connector_id": 1}

	def test_timeline_capture_does_not_break_ocpp_logging(self, caplog):
		store = TimelineStore(max_length=100)
		adapter = _make_adapter(timeline_store=store)

		with caplog.at_level(logging.DEBUG, logger="chargeghost.ocpp.tx"):
			adapter._log_ocpp_raw(
				"TX",
				"BootNotification",
				{"status": "Accepted"},
				"msg-1",
			)

		records = [r for r in caplog.records if r.name == "chargeghost.ocpp.tx"]
		assert len(records) == 1
		assert records[0].ocpp_direction == "TX"
		assert records[0].ocpp_action == "BootNotification"
		assert records[0].ocpp_message_id == "msg-1"

	def test_timeline_capture_rx_sets_correct_direction(self, caplog):
		store = TimelineStore(max_length=100)
		adapter = _make_adapter(timeline_store=store)

		adapter._log_ocpp_raw(
			"RX",
			"Authorize",
			{"id_tag": "ABCD1234"},
			"msg-3",
		)

		events = store.all()
		assert len(events) == 1
		event = events[0]
		assert event.direction == "inbound"

	def test_timeline_capture_without_store_does_not_error(self):
		adapter = _make_adapter(timeline_store=None)

		adapter._log_ocpp_raw(
			"TX",
			"Heartbeat",
			{},
			"msg-4",
		)

		events = adapter.timeline_store
		assert events is None

	def test_timeline_capture_preserves_dict_payload(self):
		store = TimelineStore(max_length=100)
		adapter = _make_adapter(timeline_store=store)

		payload = {
			"vendor_id": "Acme",
			"message_id": "Debug",
			"data": {"key": "value", "number": 42},
		}
		adapter._log_ocpp_raw("TX", "DataTransfer", payload, "msg-5")

		events = store.all()
		assert len(events) == 1
		event = events[0]
		assert event.payload == payload
		assert event.action == "DataTransfer"


class TestLocalTimelineCapture:
	def test_offline_queue_appends_queue_event(self) -> None:
		"""
		Test that offline queue events are captured in the timeline store.
		"""
		store = TimelineStore(max_length=100)
		engine = Engine()

		connector = engine.add_connector(voltage=230.0, current=32.0, phase=3)
		engine.plug_in(connector_id=connector.id)
		engine.start_session(connector_id=connector.id, transaction_id=12345)

		bridge = Bridge(
			engine=engine,
			url="wss://localhost:9999/CP_1",
		)
		bridge.timeline_store = store

		store.clear()
		bridge.on_engine_session_started(connector.id)

		queue_events = [
			e for e in store.all() if e.event_type == "queue"
		]
		assert len(queue_events) >= 1
		assert queue_events[0].source == "bridge"
		assert queue_events[0].direction == "local"
		assert queue_events[0].action == "queue_message"

	def test_ui_action_appends_local_timeline_event(self) -> None:
		"""
		Test that UI actions are captured in the timeline store.
		"""
		store = TimelineStore(max_length=100)
		engine = Engine()

		connector = engine.add_connector(voltage=230.0, current=32.0, phase=3)

		class MockMainWindow:
			timeline_store = store

			def log_message(self, msg: str) -> None:
				pass

		class MockBridge:
			def send_authorize(self, rfid_tag: str) -> None:
				pass

		class MockSimulatorWidget:
			def __init__(self) -> None:
				self.main_window = MockMainWindow()
				self._selected_connector_id = connector.id
				self._transaction_counter = 0
				self.engine = engine
				self.bridge = MockBridge()

			def action_plug_in(self) -> None:
				from chargeghost_evse.ui.app import SimulatorWidget
				SimulatorWidget.action_plug_in(self)

			def action_authorize(self, rfid_tag: str) -> None:
				from chargeghost_evse.ui.app import SimulatorWidget
				SimulatorWidget.action_authorize(self, rfid_tag)

		simulator = MockSimulatorWidget()

		store.clear()
		simulator.action_plug_in()

		plug_in_events = [
			e for e in store.all()
			if e.event_type == "action" and e.action == "plug_in"
		]
		assert len(plug_in_events) >= 1
		assert plug_in_events[0].source == "ui"
		assert plug_in_events[0].direction == "local"

		store.clear()
		simulator.action_authorize("test_rfid_tag")

		authorize_events = [
			e for e in store.all()
			if e.event_type == "action" and e.action == "authorize"
		]
		assert len(authorize_events) >= 1
		assert authorize_events[0].source == "ui"
		assert authorize_events[0].direction == "local"
