import threading
import time

from chargeghost_evse.devtools.timeline_models import TimelineEvent, TimelineFilter
from chargeghost_evse.devtools.timeline_store import TimelineStore


class TestTimelineStore:
	def test_timeline_store_appends_in_order(self):
		store = TimelineStore(max_length=100)
		
		e1 = store.append(
			source="ocpp",
			direction="inbound",
			event_type="action",
			action="Authorize",
			summary="Authorize request",
		)
		e2 = store.append(
			source="ocpp",
			direction="outbound",
			event_type="action",
			action="StartTransaction",
			summary="StartTransaction response",
		)
		e3 = store.append(
			source="engine",
			direction="local",
			event_type="session",
			action="session_started",
			summary="Session started",
		)
		
		events = store.all()
		assert len(events) == 3
		assert events[0].event_id == e1.event_id
		assert events[1].event_id == e2.event_id
		assert events[2].event_id == e3.event_id
		assert events[0].action == "Authorize"
		assert events[1].action == "StartTransaction"
		assert events[2].action == "session_started"
		assert events[0].timestamp <= events[1].timestamp <= events[2].timestamp

	def test_timeline_store_enforces_max_length(self):
		max_len = 5
		store = TimelineStore(max_length=max_len)
		
		for i in range(10):
			store.append(
				source="ocpp",
				direction="inbound",
				event_type="action",
				action=f"Action{i}",
				summary=f"Event {i}",
			)
		
		events = store.all()
		assert len(events) == max_len
		assert events[0].action == "Action5"
		assert events[-1].action == "Action9"
		assert store.count == max_len

	def test_timeline_store_filters_by_source_and_action(self):
		store = TimelineStore(max_length=100)
		
		store.append(source="ocpp", direction="inbound", event_type="action", action="Authorize", summary="1")
		store.append(source="ocpp", direction="outbound", event_type="action", action="BootNotification", summary="2")
		store.append(source="engine", direction="local", event_type="session", action="session_started", summary="3")
		store.append(source="ocpp", direction="inbound", event_type="action", action="Authorize", summary="4")
		
		filter_by_source = TimelineFilter(source="ocpp")
		filtered = store.query(filter_by_source)
		assert len(filtered) == 3
		assert all(e.source == "ocpp" for e in filtered)
		
		filter_by_action = TimelineFilter(action="Authorize")
		filtered = store.query(filter_by_action)
		assert len(filtered) == 2
		assert all(e.action == "Authorize" for e in filtered)
		
		filter_combined = TimelineFilter(source="ocpp", action="Authorize")
		filtered = store.query(filter_combined)
		assert len(filtered) == 2
		assert all(e.source == "ocpp" and e.action == "Authorize" for e in filtered)

	def test_timeline_store_clear_removes_events(self):
		store = TimelineStore(max_length=100)
		
		store.append(source="ocpp", direction="inbound", event_type="action", action="Authorize", summary="1")
		store.append(source="engine", direction="local", event_type="session", action="session_started", summary="2")
		
		assert store.count == 2
		
		store.clear()
		
		assert store.count == 0
		assert store.all() == []

	def test_timeline_store_notifies_subscribers(self):
		store = TimelineStore(max_length=100)
		received_events = []
		lock = threading.Lock()
		
		def callback(event: TimelineEvent) -> None:
			with lock:
				received_events.append(event)
		
		store.on_event.subscribe(callback)
		
		e1 = store.append(source="ocpp", direction="inbound", event_type="action", action="Authorize", summary="1")
		e2 = store.append(source="engine", direction="local", event_type="session", action="session_started", summary="2")
		
		time.sleep(0.05)
		
		with lock:
			assert len(received_events) == 2
			assert received_events[0].event_id == e1.event_id
			assert received_events[1].event_id == e2.event_id


class TestTimelineExport:
	def test_timeline_export_writes_json_events(self):
		import json
		import tempfile
		
		from chargeghost_evse.devtools.timeline_export import TimelineExporter
		
		store = TimelineStore(max_length=100)
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="Authorize",
			message_id="msg-1",
			summary="Authorize request",
			payload={"id_tag": "ABCD1234"},
		)
		
		exporter = TimelineExporter(store)
		
		with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
			output_path = f.name
		
		json_str = exporter.export(output_path=output_path)
		events = json.loads(json_str)
		
		assert len(events) == 1
		assert events[0]["action"] == "Authorize"
		assert events[0]["message_id"] == "msg-1"
		assert events[0]["source"] == "ocpp"
		assert events[0]["direction"] == "inbound"
		assert "correlation_key" in events[0]
		assert events[0]["correlation_key"] == "Authorize:msg-1"

	def test_timeline_event_builds_correlation_key_from_message_id(self):
		event_with_msg_id = TimelineEvent(
			event_id=1,
			timestamp="2026-03-28T10:00:00Z",
			source="ocpp",
			direction="inbound",
			event_type="frame",
			protocol_version="ocpp1.6",
			action="BootNotification",
			message_id="msg-42",
			connector_id=1,
			transaction_id=0,
			level=20,
			summary="Boot",
			payload={},
		)
		assert event_with_msg_id.build_correlation_key() == "BootNotification:msg-42"
		
		event_without_msg_id = TimelineEvent(
			event_id=2,
			timestamp="2026-03-28T10:00:00Z",
			source="engine",
			direction="local",
			event_type="session",
			protocol_version="ocpp1.6",
			action="session_started",
			message_id="",
			connector_id=1,
			transaction_id=123,
			level=20,
			summary="Session started",
			payload={},
		)
		assert event_without_msg_id.build_correlation_key() == "session_started"

	def test_timeline_export_redacts_sensitive_fields(self):
		import json
		
		from chargeghost_evse.devtools.timeline_export import TimelineExporter
		
		store = TimelineStore(max_length=100)
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="Authorize",
			message_id="msg-1",
			summary="Authorize request",
			payload={
				"id_tag": "ABCD1234",
				"password": "secret123",
				"ocpp_password": "another_secret",
				"connector_id": 1,
			},
		)
		
		exporter = TimelineExporter(store)
		json_str = exporter.export()
		events = json.loads(json_str)
		
		assert events[0]["payload"]["id_tag"] == "***REDACTED***"
		assert events[0]["payload"]["password"] == "***REDACTED***"
		assert events[0]["payload"]["ocpp_password"] == "***REDACTED***"
		assert events[0]["payload"]["connector_id"] == 1

	def test_timeline_export_truncates_large_payloads(self):
		import json
		
		from chargeghost_evse.devtools.timeline_export import MAX_PAYLOAD_SIZE, TimelineExporter
		
		store = TimelineStore(max_length=100)
		large_data = "x" * (MAX_PAYLOAD_SIZE + 1000)
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="DataTransfer",
			message_id="msg-large",
			summary="Large data transfer",
			payload={"data": large_data},
		)
		
		exporter = TimelineExporter(store)
		json_str = exporter.export(truncate_payloads=True)
		events = json.loads(json_str)
		
		assert events[0]["payload"]["payload_truncated"] is True
		assert "_summary" in events[0]["payload"]
		assert "Original size:" in events[0]["payload"]["_summary"]
