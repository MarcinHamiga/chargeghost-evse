from __future__ import annotations


from chargeghost_evse.devtools.timeline_store import TimelineStore


class TestGetTimeline:
	def test_empty_timeline(self, client, app):
		store = TimelineStore()
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline")

		assert response.status_code == 200
		assert response.json() == []

	def test_returns_events(self, client, app):
		store = TimelineStore()
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="BootNotification",
			summary="Boot notification received",
		)
		store.append(
			source="ui",
			direction="local",
			event_type="action",
			action="StartCharging",
			summary="User started charging",
			connector_id=1,
		)
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline")

		assert response.status_code == 200
		data = response.json()
		assert len(data) == 2
		assert data[0]["action"] == "BootNotification"
		assert data[0]["source"] == "ocpp"
		assert data[0]["direction"] == "inbound"
		assert data[0]["event_type"] == "frame"
		assert data[0]["connector_id"] == 0
		assert data[1]["action"] == "StartCharging"
		assert data[1]["source"] == "ui"
		assert data[1]["connector_id"] == 1

	def test_filter_by_source(self, client, app):
		store = TimelineStore()
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="BootNotification",
			summary="Boot",
		)
		store.append(
			source="ui",
			direction="local",
			event_type="action",
			action="StartCharging",
			summary="Start",
		)
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline?source=ui")

		assert response.status_code == 200
		data = response.json()
		assert len(data) == 1
		assert data[0]["source"] == "ui"

	def test_filter_by_event_type(self, client, app):
		store = TimelineStore()
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="BootNotification",
			summary="Boot",
		)
		store.append(
			source="engine",
			direction="local",
			event_type="status_change",
			action="StatusChanged",
			summary="Status changed",
		)
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline?event_type=status_change")

		assert response.status_code == 200
		data = response.json()
		assert len(data) == 1
		assert data[0]["event_type"] == "status_change"

	def test_filter_by_connector_id(self, client, app):
		store = TimelineStore()
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="StartTransaction",
			summary="Tx start",
			connector_id=1,
		)
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="StartTransaction",
			summary="Tx start",
			connector_id=2,
		)
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline?connector_id=2")

		assert response.status_code == 200
		data = response.json()
		assert len(data) == 1
		assert data[0]["connector_id"] == 2

	def test_filter_by_action(self, client, app):
		store = TimelineStore()
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="BootNotification",
			summary="Boot",
		)
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="Heartbeat",
			summary="Heartbeat",
		)
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline?action=Heartbeat")

		assert response.status_code == 200
		data = response.json()
		assert len(data) == 1
		assert data[0]["action"] == "Heartbeat"

	def test_filter_by_direction(self, client, app):
		store = TimelineStore()
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="BootNotification",
			summary="Boot",
		)
		store.append(
			source="ocpp",
			direction="outbound",
			event_type="frame",
			action="Heartbeat",
			summary="Heartbeat",
		)
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline?direction=outbound")

		assert response.status_code == 200
		data = response.json()
		assert len(data) == 1
		assert data[0]["direction"] == "outbound"

	def test_filter_by_transaction_id(self, client, app):
		store = TimelineStore()
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="StartTransaction",
			summary="Tx start",
			transaction_id=10,
		)
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="StartTransaction",
			summary="Tx start",
			transaction_id=20,
		)
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline?transaction_id=20")

		assert response.status_code == 200
		data = response.json()
		assert len(data) == 1
		assert data[0]["transaction_id"] == 20

	def test_filter_by_min_level(self, client, app):
		store = TimelineStore()
		store.append(
			source="engine",
			direction="local",
			event_type="status_change",
			action="StatusChanged",
			summary="Info status",
			level=20,
		)
		store.append(
			source="engine",
			direction="local",
			event_type="error",
			action="Error",
			summary="Error occurred",
			level=40,
		)
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline?min_level=40")

		assert response.status_code == 200
		data = response.json()
		assert len(data) == 1
		assert data[0]["level"] == 40

	def test_filter_by_search(self, client, app):
		store = TimelineStore()
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="BootNotification",
			summary="Boot notification received",
		)
		store.append(
			source="ui",
			direction="local",
			event_type="action",
			action="StartCharging",
			summary="User started charging",
		)
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline?search=boot")

		assert response.status_code == 200
		data = response.json()
		assert len(data) == 1
		assert "boot" in data[0]["summary"].lower()

	def test_filter_by_tags(self, client, app):
		store = TimelineStore()
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="BootNotification",
			summary="Boot",
			tags=["ocpp", "init"],
		)
		store.append(
			source="ui",
			direction="local",
			event_type="action",
			action="StartCharging",
			summary="Start",
			tags=["ui"],
		)
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline?tags=init")

		assert response.status_code == 200
		data = response.json()
		assert len(data) == 1
		assert data[0]["action"] == "BootNotification"

	def test_limit(self, client, app):
		store = TimelineStore()
		for i in range(5):
			store.append(
				source="ocpp",
				direction="inbound",
				event_type="frame",
				action=f"Action{i}",
				summary=f"Event {i}",
			)
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline?limit=3")

		assert response.status_code == 200
		data = response.json()
		assert len(data) == 3

	def test_offset(self, client, app):
		store = TimelineStore()
		for i in range(5):
			store.append(
				source="ocpp",
				direction="inbound",
				event_type="frame",
				action=f"Action{i}",
				summary=f"Event {i}",
			)
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline?offset=2")

		assert response.status_code == 200
		data = response.json()
		assert len(data) == 3
		assert data[0]["action"] == "Action2"

	def test_limit_and_offset(self, client, app):
		store = TimelineStore()
		for i in range(5):
			store.append(
				source="ocpp",
				direction="inbound",
				event_type="frame",
				action=f"Action{i}",
				summary=f"Event {i}",
			)
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline?offset=1&limit=2")

		assert response.status_code == 200
		data = response.json()
		assert len(data) == 2
		assert data[0]["action"] == "Action1"
		assert data[1]["action"] == "Action2"

	def test_event_fields(self, client, app):
		store = TimelineStore()
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="BootNotification",
			message_id="msg-1",
			connector_id=1,
			transaction_id=42,
			level=20,
			summary="Boot notification received",
			payload={"chargePointModel": "CGV1"},
			tags=["init"],
		)
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline")

		assert response.status_code == 200
		data = response.json()
		assert len(data) == 1
		event = data[0]
		assert event["event_id"] == 1
		assert event["source"] == "ocpp"
		assert event["direction"] == "inbound"
		assert event["event_type"] == "frame"
		assert event["protocol_version"] == "ocpp1.6"
		assert event["action"] == "BootNotification"
		assert event["message_id"] == "msg-1"
		assert event["connector_id"] == 1
		assert event["transaction_id"] == 42
		assert event["level"] == 20
		assert event["summary"] == "Boot notification received"
		assert event["payload"] == {"chargePointModel": "CGV1"}
		assert event["tags"] == ["init"]
		assert "timestamp" in event


class TestGetTimelineCount:
	def test_empty_count(self, client, app):
		store = TimelineStore()
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline/count")

		assert response.status_code == 200
		assert response.json() == {"count": 0}

	def test_returns_correct_count(self, client, app):
		store = TimelineStore()
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="BootNotification",
			summary="Boot",
		)
		store.append(
			source="ui",
			direction="local",
			event_type="action",
			action="StartCharging",
			summary="Start",
		)
		store.append(
			source="engine",
			direction="local",
			event_type="status_change",
			action="StatusChanged",
			summary="Status",
		)
		app.state.bridge.timeline_store = store

		response = client.get("/api/v1/timeline/count")

		assert response.status_code == 200
		assert response.json() == {"count": 3}


class TestClearTimeline:
	def test_clear_all_events(self, client, app):
		store = TimelineStore()
		store.append(
			source="ocpp",
			direction="inbound",
			event_type="frame",
			action="BootNotification",
			summary="Boot",
		)
		store.append(
			source="ui",
			direction="local",
			event_type="action",
			action="StartCharging",
			summary="Start",
		)
		app.state.bridge.timeline_store = store

		response = client.delete("/api/v1/timeline")

		assert response.status_code == 200
		assert response.json() == {"success": True}
		assert store.count == 0

	def test_clear_empty_timeline(self, client, app):
		store = TimelineStore()
		app.state.bridge.timeline_store = store

		response = client.delete("/api/v1/timeline")

		assert response.status_code == 200
		assert response.json() == {"success": True}


class TestTimelineUnavailable:
	def test_get_timeline_503_when_store_missing(self, client, app):
		app.state.bridge.timeline_store = None

		response = client.get("/api/v1/timeline")

		assert response.status_code == 503
		assert response.json() == {"detail": "Timeline store not available"}

	def test_get_timeline_503_when_bridge_missing(self, app):
		app.state.runtime.bridge = None
		from fastapi.testclient import TestClient

		client = TestClient(app)

		response = client.get("/api/v1/timeline")

		assert response.status_code == 503
		assert response.json() == {"detail": "Timeline store not available"}

	def test_get_timeline_count_503_when_store_missing(self, client, app):
		app.state.bridge.timeline_store = None

		response = client.get("/api/v1/timeline/count")

		assert response.status_code == 503
		assert response.json() == {"detail": "Timeline store not available"}

	def test_delete_timeline_503_when_store_missing(self, client, app):
		app.state.bridge.timeline_store = None

		response = client.delete("/api/v1/timeline")

		assert response.status_code == 503
		assert response.json() == {"detail": "Timeline store not available"}
