from __future__ import annotations

from unittest.mock import MagicMock, patch

from ocpp.v16.enums import UpdateStatus, UpdateType


def _make_adapter():
	adapter = MagicMock()
	adapter.local_auth_list.version = 1
	adapter.local_auth_list.enabled = True
	adapter.local_auth_list.entry_count = 2
	adapter.local_auth_list.max_entries = 100
	return adapter


class TestGetLocalAuthList:
	def test_returns_503_when_adapter_unavailable(self, client):
		response = client.get("/api/v1/local-auth-list")

		assert response.status_code == 503
		assert response.json() == {"detail": "OCPP adapter not available"}

	def test_returns_list_info(self, client, app, mock_controller):
		mock_controller.adapter = _make_adapter()
		list_data = {
			"version": 1,
			"enabled": True,
			"entry_count": 2,
			"max_entries": 100,
			"entries": [],
		}

		with patch(
			"chargeghost_evse.api.routes.local_auth.serialize_local_auth_list",
			return_value=list_data,
		):
			response = client.get("/api/v1/local-auth-list")

		assert response.status_code == 200
		data = response.json()
		assert data["version"] == 1
		assert data["enabled"] is True
		assert data["entry_count"] == 2
		assert data["max_entries"] == 100
		assert data["entries"] == []


class TestGetLocalAuthEntry:
	def test_returns_503_when_adapter_unavailable(self, client):
		response = client.get("/api/v1/local-auth-list/TAG1")

		assert response.status_code == 503
		assert response.json() == {"detail": "OCPP adapter not available"}

	def test_returns_entry(self, client, app, mock_controller):
		mock_controller.adapter = _make_adapter()
		entry_data = {
			"version": 1,
			"enabled": True,
			"entry_count": 1,
			"max_entries": 100,
			"entries": [
				{
					"id_tag": "TAG1",
					"id_tag_info": {"status": "Accepted"},
					"is_expired": False,
					"authorization_status": "Accepted",
				}
			],
		}

		with patch(
			"chargeghost_evse.api.routes.local_auth.serialize_local_auth_entry",
			return_value=entry_data,
		):
			response = client.get("/api/v1/local-auth-list/TAG1")

		assert response.status_code == 200
		data = response.json()
		assert len(data["entries"]) == 1
		assert data["entries"][0]["id_tag"] == "TAG1"
		assert data["entries"][0]["authorization_status"] == "Accepted"

	def test_returns_404_when_entry_not_found(self, client, app, mock_controller):
		mock_controller.adapter = _make_adapter()

		with patch(
			"chargeghost_evse.api.routes.local_auth.serialize_local_auth_entry",
			return_value=None,
		):
			response = client.get("/api/v1/local-auth-list/UNKNOWN")

		assert response.status_code == 404
		assert response.json() == {"detail": "Entry 'UNKNOWN' not found"}


class TestUpdateLocalAuthList:
	def test_returns_503_when_adapter_unavailable(self, client):
		response = client.put(
			"/api/v1/local-auth-list",
			json={"list_version": 1, "update_type": "full"},
		)

		assert response.status_code == 503
		assert response.json() == {"detail": "OCPP adapter not available"}

	def test_full_update_accepted(self, client, app, mock_controller):
		adapter = _make_adapter()
		mock_controller.adapter = adapter
		adapter.local_auth_list.update_list.return_value = (
			UpdateStatus.accepted,
			"Full update completed (2 entries)",
		)

		with patch(
			"chargeghost_evse.api.routes.local_auth.UpdateType",
		) as mock_ut:
			mock_ut.side_effect = lambda v: {"full": UpdateType.full, "differential": UpdateType.differential}[v]
			response = client.put(
				"/api/v1/local-auth-list",
				json={
					"list_version": 1,
					"update_type": "full",
					"entries": [{"idTag": "TAG1"}, {"idTag": "TAG2"}],
				},
			)

		assert response.status_code == 200
		data = response.json()
		assert data["success"] is True
		assert data["details"]["status"] == "Accepted"
		adapter.local_auth_list.update_list.assert_called_once_with(
			1,
			[{"idTag": "TAG1"}, {"idTag": "TAG2"}],
			UpdateType.full,
		)

	def test_differential_update_version_mismatch(self, client, app, mock_controller):
		adapter = _make_adapter()
		mock_controller.adapter = adapter
		adapter.local_auth_list.update_list.return_value = (
			UpdateStatus.version_mismatch,
			"Expected differential list version 2, got 5",
		)

		with patch(
			"chargeghost_evse.api.routes.local_auth.UpdateType",
		) as mock_ut:
			mock_ut.side_effect = lambda v: {"full": UpdateType.full, "differential": UpdateType.differential}[v]
			response = client.put(
				"/api/v1/local-auth-list",
				json={"list_version": 5, "update_type": "differential"},
			)

		assert response.status_code == 200
		data = response.json()
		assert data["success"] is False
		assert data["details"]["status"] == "VersionMismatch"
		adapter.local_auth_list.update_list.assert_called_once_with(
			5, None, UpdateType.differential
		)

	def test_full_update_failed(self, client, app, mock_controller):
		adapter = _make_adapter()
		mock_controller.adapter = adapter
		adapter.local_auth_list.update_list.return_value = (
			UpdateStatus.failed,
			"Reserved or invalid list version",
		)

		with patch(
			"chargeghost_evse.api.routes.local_auth.UpdateType",
		) as mock_ut:
			mock_ut.side_effect = lambda v: {"full": UpdateType.full, "differential": UpdateType.differential}[v]
			response = client.put(
				"/api/v1/local-auth-list",
				json={"list_version": 0, "update_type": "full"},
			)

		assert response.status_code == 200
		data = response.json()
		assert data["success"] is False
		assert data["details"]["status"] == "Failed"


class TestRemoveLocalAuthEntry:
	def test_returns_503_when_adapter_unavailable(self, client):
		response = client.delete("/api/v1/local-auth-list/TAG1")

		assert response.status_code == 503
		assert response.json() == {"detail": "OCPP adapter not available"}

	def test_removes_entry_successfully(self, client, app, mock_controller):
		adapter = _make_adapter()
		mock_controller.adapter = adapter
		adapter.local_auth_list.remove_entry.return_value = (True, "Saved successfully")

		response = client.delete("/api/v1/local-auth-list/TAG1")

		assert response.status_code == 200
		data = response.json()
		assert data["success"] is True
		assert data["message"] == "Saved successfully"
		adapter.local_auth_list.remove_entry.assert_called_once_with("TAG1")

	def test_remove_entry_not_found(self, client, app, mock_controller):
		adapter = _make_adapter()
		mock_controller.adapter = adapter
		adapter.local_auth_list.remove_entry.return_value = (
			False,
			"id_tag 'UNKNOWN' not found",
		)

		response = client.delete("/api/v1/local-auth-list/UNKNOWN")

		assert response.status_code == 200
		data = response.json()
		assert data["success"] is False
		assert data["message"] == "id_tag 'UNKNOWN' not found"


class TestClearLocalAuthList:
	def test_returns_503_when_adapter_unavailable(self, client):
		response = client.delete("/api/v1/local-auth-list")

		assert response.status_code == 503
		assert response.json() == {"detail": "OCPP adapter not available"}

	def test_clears_list_successfully(self, client, app, mock_controller):
		adapter = _make_adapter()
		mock_controller.adapter = adapter
		adapter.local_auth_list.clear.return_value = (True, "Saved successfully")

		response = client.delete("/api/v1/local-auth-list")

		assert response.status_code == 200
		data = response.json()
		assert data["success"] is True
		assert data["message"] == "Saved successfully"
		adapter.local_auth_list.clear.assert_called_once()

	def test_clear_list_fails(self, client, app, mock_controller):
		adapter = _make_adapter()
		mock_controller.adapter = adapter
		adapter.local_auth_list.clear.return_value = (
			False,
			"Failed to save auth list: permission denied",
		)

		response = client.delete("/api/v1/local-auth-list")

		assert response.status_code == 200
		data = response.json()
		assert data["success"] is False
		assert data["message"] == "Failed to save auth list: permission denied"
