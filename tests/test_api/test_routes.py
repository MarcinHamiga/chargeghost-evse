from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from chargeghost_evse.api.schemas import ActionResult as ApiActionResult
from chargeghost_evse.devtools.simulator_controller import ActionResult
from chargeghost_evse.ocpp_adapter.config_keys import ConfigurationKey


def _make_connector(
	connector_id: int,
	*,
	status: str = "Available",
	voltage: float = 230.0,
	current: float = 32.0,
	phase: int = 1,
	is_plugged_in: bool = False,
	id_tag: str | None = None,
):
	return SimpleNamespace(
		id=connector_id,
		status=SimpleNamespace(value=status),
		voltage=voltage,
		current=current,
		phase=phase,
		is_plugged_in=is_plugged_in,
		id_tag=id_tag,
	)


def _make_session(
	transaction_id: int,
	connector_id: int,
	*,
	energy_charged: float = 1234.56,
	state_of_charge: float = 67.8,
	start_time: float = 1710000000.0,
	id_tag: str | None = None,
):
	return SimpleNamespace(
		transaction_id=transaction_id,
		connector_id=connector_id,
		energy_charged=energy_charged,
		state_of_charge=state_of_charge,
		start_time=start_time,
		id_tag=id_tag,
	)


def _make_meter(*, reading_wh: float = 0.0, is_charging: bool = False):
	return MagicMock(
		get_meter_reading=MagicMock(return_value=reading_wh),
		is_charging=is_charging,
	)


class TestStatusRoutes:
	def test_get_status_no_connectors(self, client):
		response = client.get("/api/v1/status")

		assert response.status_code == 200
		assert response.json() == {
			"ocpp_connected": False,
			"connectors": [],
			"active_sessions": [],
			"energy_meters": {},
		}

	def test_get_status_with_connector_and_active_session(self, client, mock_controller):
		connector = _make_connector(
			1,
			status="Charging",
			voltage=400.0,
			current=16.0,
			phase=3,
			is_plugged_in=True,
			id_tag="TAG123",
		)
		session = _make_session(99, 1, id_tag="TAG123")
		meter = _make_meter(reading_wh=4321.09, is_charging=True)

		mock_controller.is_connected = True
		mock_controller.engine.connectors = [connector]
		mock_controller.engine.get_session.side_effect = lambda connector_id: (
			session if connector_id == 1 else None
		)
		mock_controller.engine.get_energy_meter.side_effect = lambda connector_id: meter

		response = client.get("/api/v1/status")

		assert response.status_code == 200
		assert response.json() == {
			"ocpp_connected": True,
			"connectors": [
				{
					"id": 1,
					"status": "Charging",
					"voltage": 400.0,
					"current": 16.0,
					"phase": 3,
					"is_plugged_in": True,
					"id_tag": "TAG123",
				}
			],
			"active_sessions": [
				{
					"transaction_id": 99,
					"connector_id": 1,
					"energy_charged_wh": 1234.56,
					"state_of_charge": 67.8,
					"start_time": 1710000000.0,
					"id_tag": "TAG123",
					"is_charging": True,
				}
			],
			"energy_meters": {
				"1": {"reading_wh": 4321.09, "is_charging": True},
			},
		}

	def test_ws_client_count(self, client):
		response = client.get("/api/v1/status/ws-clients")

		assert response.status_code == 200
		assert response.json() == {"count": 0}


class TestConnectorRoutes:
	def test_list_connectors(self, client, mock_controller):
		mock_controller.engine.connectors = [
			_make_connector(1),
			_make_connector(2, status="Preparing", current=40.0, is_plugged_in=True),
		]

		response = client.get("/api/v1/connectors")

		assert response.status_code == 200
		assert response.json() == [
			{
				"id": 1,
				"status": "Available",
				"voltage": 230.0,
				"current": 32.0,
				"phase": 1,
				"is_plugged_in": False,
				"id_tag": None,
			},
			{
				"id": 2,
				"status": "Preparing",
				"voltage": 230.0,
				"current": 40.0,
				"phase": 1,
				"is_plugged_in": True,
				"id_tag": None,
			},
		]

	def test_get_connector(self, client, mock_controller):
		connector = _make_connector(2, status="Faulted", voltage=480.0, phase=3)
		mock_controller.engine.get_connector.return_value = connector

		response = client.get("/api/v1/connectors/2")

		assert response.status_code == 200
		assert response.json() == {
			"id": 2,
			"status": "Faulted",
			"voltage": 480.0,
			"current": 32.0,
			"phase": 3,
			"is_plugged_in": False,
			"id_tag": None,
		}

	def test_get_connector_returns_not_found(self, client, mock_controller):
		mock_controller.engine.get_connector.return_value = None

		response = client.get("/api/v1/connectors/99")

		assert response.status_code == 404
		assert response.json() == {"detail": "Connector 99 not found"}

	def test_create_connector(self, client, mock_controller, mock_simulation_config):
		created_connector = _make_connector(2, voltage=400.0, current=16.0, phase=3)
		mock_controller.engine.connectors = [_make_connector(1)]

		def add_connector(*, voltage: float, current: float, phase: int):
			mock_controller.engine.connectors.append(created_connector)
			return created_connector

		mock_controller.engine.add_connector.side_effect = add_connector

		response = client.post(
			"/api/v1/connectors",
			json={"voltage": 400.0, "current": 16.0, "phase": 3},
		)

		assert response.status_code == 200
		assert response.json() == {
			"success": True,
			"message": "Created connector 2",
			"details": {
				"connector": {
					"id": 2,
					"status": "Available",
					"voltage": 400.0,
					"current": 16.0,
					"phase": 3,
					"is_plugged_in": False,
					"id_tag": None,
				}
			},
		}
		mock_controller.engine.add_connector.assert_called_once_with(
			voltage=400.0,
			current=16.0,
			phase=3,
		)
		mock_simulation_config.save.assert_called_once_with()
		assert [connector.to_dict() for connector in mock_simulation_config.connectors] == [
			{"voltage": 230.0, "current": 32.0, "phase": 1},
			{"voltage": 400.0, "current": 16.0, "phase": 3},
		]

	def test_create_connector_rejects_invalid_parameters(
		self, client, mock_controller, mock_simulation_config
	):
		response = client.post(
			"/api/v1/connectors",
			json={"voltage": 50.0, "current": 16.0, "phase": 1},
		)

		assert response.status_code == 422
		mock_controller.engine.add_connector.assert_not_called()
		mock_simulation_config.save.assert_not_called()

	def test_update_connector(self, client, mock_controller, mock_simulation_config):
		updated_connector = _make_connector(1, voltage=480.0, current=48.0, phase=3)
		mock_controller.engine.connectors = [updated_connector]
		mock_controller.engine.update_connector.return_value = None
		mock_controller.engine.get_connector.return_value = updated_connector

		response = client.put(
			"/api/v1/connectors/1",
			json={"voltage": 480.0, "current": 48.0, "phase": 3},
		)

		assert response.status_code == 200
		assert response.json() == {
			"success": True,
			"message": "Updated connector 1",
			"details": {
				"connector": {
					"id": 1,
					"status": "Available",
					"voltage": 480.0,
					"current": 48.0,
					"phase": 3,
					"is_plugged_in": False,
					"id_tag": None,
				}
			},
		}
		mock_controller.engine.update_connector.assert_called_once_with(
			connector_id=1,
			voltage=480.0,
			current=48.0,
			phase=3,
		)
		mock_simulation_config.save.assert_called_once_with()

	def test_delete_connector(self, client, mock_controller, mock_simulation_config):
		mock_controller.engine.connectors = [_make_connector(1)]

		response = client.delete("/api/v1/connectors/2")

		assert response.status_code == 200
		assert response.json() == {
			"success": True,
			"message": "Removed connector 2",
			"details": {"connector_id": 2},
		}
		mock_controller.engine.remove_connector.assert_called_once_with(2)
		mock_simulation_config.save.assert_called_once_with()

	def test_delete_connector_returns_action_error(
		self, client, mock_controller, mock_simulation_config
	):
		mock_controller.engine.remove_connector.side_effect = ValueError(
			"Cannot remove connector with active session"
		)

		response = client.delete("/api/v1/connectors/1")

		assert response.status_code == 200
		assert response.json() == {
			"success": False,
			"message": "Cannot remove connector with active session",
			"details": None,
		}
		mock_simulation_config.save.assert_not_called()

	def test_plug_in(self, client, mock_controller):
		mock_controller.plug_in.return_value = ActionResult(
			success=True,
			message="Plugged In to Connector 1",
		)

		response = client.post("/api/v1/connectors/1/plug_in")

		assert response.status_code == 200
		assert response.json()["success"] is True
		mock_controller.plug_in.assert_called_once_with(1)

	def test_suspend_ev(self, client, mock_controller):
		mock_controller.suspend_ev.return_value = ActionResult(
			success=True,
			message="EV-side charging suspended on Connector 1",
		)

		response = client.post("/api/v1/connectors/1/suspend_ev")

		assert response.status_code == 200
		assert response.json()["success"] is True
		mock_controller.suspend_ev.assert_called_once_with(1)

	def test_resume_charging(self, client, mock_controller):
		mock_controller.resume_charging.return_value = ActionResult(
			success=True,
			message="Charging resumed on Connector 1",
		)

		response = client.post("/api/v1/connectors/1/resume_charging")

		assert response.status_code == 200
		assert response.json()["success"] is True
		mock_controller.resume_charging.assert_called_once_with(1)

	def test_start_charging_connector_endpoint(self, client, mock_controller):
		mock_controller.start_charging.return_value = ActionResult(
			success=True,
			message="Started charging session on Connector 2",
			details={"transaction_id": 5},
		)

		response = client.post("/api/v1/connectors/2/start-charging")

		assert response.status_code == 200
		assert response.json() == {
			"success": True,
			"message": "Started charging session on Connector 2",
			"details": {"transaction_id": 5},
		}
		mock_controller.start_charging.assert_called_once_with(2)

	def test_stop_charging_connector_endpoint(self, client, mock_controller):
		mock_controller.stop_charging.return_value = ActionResult(
			success=True,
			message="Stopped charging session",
		)

		response = client.post("/api/v1/connectors/1/stop-charging")

		assert response.status_code == 200
		assert response.json()["success"] is True
		mock_controller.stop_charging.assert_called_once_with(1)

	def test_set_and_clear_rfid(self, client, mock_controller):
		mock_controller.set_rfid.return_value = ActionResult(
			success=True,
			message="RFID set to: TAG123",
		)
		mock_controller.clear_rfid.return_value = ActionResult(
			success=True,
			message="RFID cleared",
		)

		set_response = client.put("/api/v1/connectors/1/rfid?rfid_tag=TAG123")
		clear_response = client.delete("/api/v1/connectors/1/rfid")

		assert set_response.status_code == 200
		assert clear_response.status_code == 200
		mock_controller.set_rfid.assert_called_once_with("TAG123", 1)
		mock_controller.clear_rfid.assert_called_once_with(1)


class TestSessionRoutes:
	def test_start_session(self, client, mock_controller):
		mock_controller.start_charging.return_value = ActionResult(
			success=True,
			message="Started charging session on Connector 1",
			details={"transaction_id": 1},
		)

		response = client.post("/api/v1/sessions/start?connector_id=1")

		assert response.status_code == 200
		assert response.json() == {
			"success": True,
			"message": "Started charging session on Connector 1",
			"details": {"transaction_id": 1},
		}

	def test_stop_session(self, client, mock_controller):
		mock_controller.stop_charging.return_value = ActionResult(
			success=True,
			message="Stopped charging session",
		)

		response = client.post("/api/v1/sessions/stop")

		assert response.status_code == 200
		mock_controller.stop_charging.assert_called_once_with()

	def test_list_active_sessions(self, client, mock_controller):
		connector_1 = _make_connector(1)
		connector_2 = _make_connector(2)
		session = _make_session(7, 2, energy_charged=12.345, state_of_charge=81.27, id_tag="RFID-7")
		meter = _make_meter(reading_wh=987.65, is_charging=True)

		mock_controller.engine.connectors = [connector_1, connector_2]
		mock_controller.engine.get_session.side_effect = lambda connector_id: (
			session if connector_id == 2 else None
		)
		mock_controller.engine.get_energy_meter.side_effect = lambda connector_id: meter

		response = client.get("/api/v1/sessions")

		assert response.status_code == 200
		assert response.json() == [
			{
				"transaction_id": 7,
				"connector_id": 2,
				"energy_charged_wh": 12.35,
				"state_of_charge": 81.3,
				"start_time": 1710000000.0,
				"id_tag": "RFID-7",
				"is_charging": True,
			}
		]

	def test_get_session_by_connector(self, client, mock_controller):
		session = _make_session(11, 3)
		meter = _make_meter(is_charging=False)
		mock_controller.engine.get_session.return_value = session
		mock_controller.engine.get_energy_meter.return_value = meter

		response = client.get("/api/v1/sessions/3")

		assert response.status_code == 200
		assert response.json() == {
			"transaction_id": 11,
			"connector_id": 3,
			"energy_charged_wh": 1234.56,
			"state_of_charge": 67.8,
			"start_time": 1710000000.0,
			"id_tag": None,
			"is_charging": False,
		}

	def test_get_active_session_legacy_returns_none(self, client, mock_controller):
		mock_controller.engine.get_session.return_value = None

		response = client.get("/api/v1/sessions/active?connector_id=1")

		assert response.status_code == 200
		assert response.json() is None

	def test_get_last_stopped_session(self, client, mock_controller):
		mock_controller.engine.last_stopped_session = {
			"transaction_id": 55,
			"connector_id": 2,
			"energy_charged": 321.987,
			"meter_stop": 654.321,
			"reason": "Local",
			"id_tag": "STOP-TAG",
		}

		response = client.get("/api/v1/sessions/last-stopped")

		assert response.status_code == 200
		assert response.json() == {
			"transaction_id": 55,
			"connector_id": 2,
			"energy_charged_wh": 321.99,
			"meter_stop": 654.32,
			"reason": "Local",
			"id_tag": "STOP-TAG",
		}


class TestOCPPRoutes:
	def test_connect(self, client, mock_controller):
		mock_controller.connect.return_value = ActionResult(
			success=True,
			message="Connect requested",
		)

		response = client.post("/api/v1/ocpp/connect")

		assert response.status_code == 200
		mock_controller.connect.assert_called_once_with()

	def test_disconnect(self, client, mock_controller):
		mock_controller.disconnect.return_value = ActionResult(
			success=True,
			message="Disconnect requested",
		)

		response = client.post("/api/v1/ocpp/disconnect")

		assert response.status_code == 200
		mock_controller.disconnect.assert_called_once_with()

	def test_authorize(self, client, mock_controller):
		mock_controller.authorize.return_value = ActionResult(
			success=True,
			message="Authorize sent: TAG123",
		)

		response = client.post("/api/v1/ocpp/authorize?id_tag=TAG123")

		assert response.status_code == 200
		mock_controller.authorize.assert_called_once_with("TAG123")

	def test_heartbeat(self, client, mock_controller):
		mock_controller.send_heartbeat.return_value = ActionResult(
			success=True,
			message="Heartbeat sent",
		)

		response = client.post("/api/v1/ocpp/heartbeat")

		assert response.status_code == 200
		mock_controller.send_heartbeat.assert_called_once_with()

	def test_connection_status(self, client, mock_controller):
		mock_controller.is_connected = True

		response = client.get("/api/v1/ocpp/connection_status")

		assert response.status_code == 200
		assert response.json() == {"connected": True}

	def test_get_config_keys(self, client, app):
		key_b = ConfigurationKey(
			key="HeartbeatInterval",
			value="300",
			readonly=False,
			default="300",
			description="Heartbeat interval in seconds",
			mandatory=True,
			category="Core",
		)
		key_a = ConfigurationKey(
			key="AllowOfflineTxForUnknownId",
			value="false",
			readonly=False,
			default="false",
			description="Allow offline transactions for unknown RFID tags",
			mandatory=True,
			category="Core",
		)
		app.state.bridge.get_ocpp_config_keys.return_value = [
			key_a,
			key_b,
		]

		response = client.get("/api/v1/ocpp/config-keys")

		assert response.status_code == 200
		assert response.json() == [
			{
				"key": "AllowOfflineTxForUnknownId",
				"value": "false",
				"readonly": False,
				"default": "false",
				"description": "Allow offline transactions for unknown RFID tags",
				"mandatory": True,
				"category": "Core",
			},
			{
				"key": "HeartbeatInterval",
				"value": "300",
				"readonly": False,
				"default": "300",
				"description": "Heartbeat interval in seconds",
				"mandatory": True,
				"category": "Core",
			},
		]

	def test_get_config_keys_returns_empty_when_adapter_missing(self, client, app):
		app.state.bridge.get_ocpp_config_keys.return_value = []

		response = client.get("/api/v1/ocpp/config-keys")

		assert response.status_code == 200
		assert response.json() == []


class TestConfigRoutes:
	def test_get_config(self, client, mock_simulation_config):
		response = client.get("/api/v1/config")

		assert response.status_code == 200
		assert response.json() == {
			"connection_url": mock_simulation_config.connection_url,
			"ocpp_id": mock_simulation_config.ocpp_id,
			"charge_point_model": mock_simulation_config.charge_point_model,
			"charge_point_vendor": mock_simulation_config.charge_point_vendor,
			"connectors": [{"voltage": 230.0, "current": 32.0, "phase": 1}],
			"skip_tls_verify": False,
			"log_mode": "shallow",
			"multi_evse_mode": False,
			"ev_battery_capacity": 55.0,
			"ocpp_version": "1.6",
			"persist_message_queue": False,
			"rfid_tag": None,
		}

	def test_update_config(self, client, mock_controller, mock_simulation_config):
		mock_controller.engine.set_battery_capacity = MagicMock()

		response = client.patch(
			"/api/v1/config",
			json={
				"connection_url": "wss://test.example.com/CP_1",
				"ev_battery_capacity": 75.0,
				"ocpp_version": "2.0.1",
			},
		)

		assert response.status_code == 200
		assert response.json() == {
			"success": True,
			"message": "Configuration updated in memory. Save required to rebuild runtime.",
			"details": {
				"pending_action": "runtime_rebuild_required",
				"save_required": True,
				"changed_fields": [
					"connection_url",
					"ev_battery_capacity",
					"ocpp_version",
				],
				"config": {
					"connection_url": "wss://test.example.com/CP_1",
					"ocpp_id": "CP_1",
					"charge_point_model": "ChargeGhostV1",
					"charge_point_vendor": "ChargeGhost",
					"connectors": [{"voltage": 230.0, "current": 32.0, "phase": 1}],
					"skip_tls_verify": False,
					"log_mode": "shallow",
					"multi_evse_mode": False,
					"ev_battery_capacity": 75.0,
					"ocpp_version": "2.0.1",
					"persist_message_queue": False,
					"rfid_tag": None,
				},
			},
		}
		assert mock_simulation_config.connection_url == "wss://test.example.com/CP_1"
		assert mock_simulation_config.ev_battery_capacity == 75.0
		assert mock_simulation_config.ocpp_version == "2.0.1"
		mock_simulation_config.save.assert_not_called()
		mock_controller.engine.set_battery_capacity.assert_called_once_with(75.0)

	def test_update_config_rejects_mode_change_with_active_session(
		self, client, mock_controller
	):
		mock_controller.engine.session = object()

		response = client.patch("/api/v1/config", json={"multi_evse_mode": True})

		assert response.status_code == 200
		assert response.json() == ApiActionResult(
			success=False,
			message="Cannot change multi-EVSE mode while a session is active",
		).model_dump()

	def test_save_config(self, client, mock_simulation_config):
		response = client.post("/api/v1/config/save")

		assert response.status_code == 200
		assert response.json() == {
			"success": True,
			"message": "Configuration saved",
			"details": {
				"action_taken": "config_saved",
				"changed_fields": [],
				"config": {
					"connection_url": mock_simulation_config.connection_url,
					"ocpp_id": mock_simulation_config.ocpp_id,
					"charge_point_model": mock_simulation_config.charge_point_model,
					"charge_point_vendor": mock_simulation_config.charge_point_vendor,
					"connectors": [{"voltage": 230.0, "current": 32.0, "phase": 1}],
					"skip_tls_verify": False,
					"log_mode": "shallow",
					"multi_evse_mode": False,
					"ev_battery_capacity": 55.0,
					"ocpp_version": "1.6",
					"persist_message_queue": False,
					"rfid_tag": None,
				},
			},
		}
		mock_simulation_config.save.assert_called_once_with()


class TestWebSocketRoutes:
	def test_websocket_sends_initial_snapshot(self, app, mock_controller):
		mock_controller.engine.connectors = [_make_connector(1, status="Preparing")]
		app.state.bridge.runner.is_connected = True

		with TestClient(app) as client:
			with client.websocket_connect("/ws/state") as websocket:
				msg = websocket.receive_json()
				assert msg["type"] == "state_snapshot"
				assert "timestamp" in msg
				assert msg["data"] == {
					"connectors": [
						{
							"id": 1,
							"status": "Preparing",
							"voltage": 230.0,
							"current": 32.0,
							"phase": 1,
							"is_plugged_in": False,
							"id_tag": None,
						}
					],
					"active_sessions": [],
					"ocpp_connected": True,
				}

	def test_websocket_get_state_request_returns_snapshot(self, app, mock_controller):
		session = _make_session(8, 1, id_tag="WS-TAG")
		meter = _make_meter(is_charging=True)
		mock_controller.engine.connectors = [_make_connector(1, status="Charging")]
		mock_controller.engine.get_session.return_value = session
		mock_controller.engine.get_energy_meter.return_value = meter

		with TestClient(app) as client:
			with client.websocket_connect("/ws/state") as websocket:
				websocket.receive_json()
				websocket.send_text("get_state")
				msg = websocket.receive_json()
				assert msg["type"] == "state_snapshot"
				assert "timestamp" in msg
				assert msg["data"] == {
					"connectors": [
						{
							"id": 1,
							"status": "Charging",
							"voltage": 230.0,
							"current": 32.0,
							"phase": 1,
							"is_plugged_in": False,
							"id_tag": None,
						}
					],
					"active_sessions": [
						{
							"transaction_id": 8,
							"connector_id": 1,
							"energy_charged_wh": 1234.56,
							"state_of_charge": 67.8,
							"start_time": 1710000000.0,
							"id_tag": "WS-TAG",
							"is_charging": True,
						}
					],
					"ocpp_connected": False,
				}

	def test_websocket_tick_broadcast(self, app, mock_controller):
		mock_controller.engine.connectors = [_make_connector(1, status="Available")]
		app.state.start_time = 100.0

		with patch("chargeghost_evse.api.ws_manager.time.monotonic", return_value=105.2):
			with TestClient(app) as client:
				portal = client.portal
				assert portal is not None
				with client.websocket_connect("/ws/state") as websocket:
					websocket.receive_json()
					app.state.ws_manager._last_tick_broadcast_at = 0.0
					portal.call(app.state.ws_manager.maybe_broadcast_tick)
					msg = websocket.receive_json()
					assert msg["type"] == "tick"
					assert "timestamp" in msg
					assert msg["data"] == {
						"ocpp_connected": False,
						"connectors": [
							{
								"id": 1,
								"status": "Available",
								"voltage": 230.0,
								"current": 32.0,
								"phase": 1,
								"is_plugged_in": False,
								"id_tag": None,
							}
						],
						"active_sessions": [],
						"energy_meters": {
							"1": {"reading_wh": 0.0, "is_charging": False},
						},
						"uptime_seconds": 5.2,
					}
