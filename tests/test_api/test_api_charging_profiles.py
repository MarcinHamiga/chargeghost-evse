from __future__ import annotations

from unittest.mock import MagicMock


def _sample_profile() -> dict:
    return {
        "charging_profile_id": 7,
        "stack_level": 2,
        "charging_profile_purpose": "TxProfile",
        "charging_profile_kind": "Absolute",
        "charging_schedule": {
            "charging_rate_unit": "A",
            "charging_schedule_period": [
                {"start_period": 0, "limit": 16.0, "number_phases": 3}
            ],
            "duration": 3600,
        },
        "transaction_id": 123,
    }


class TestChargingProfileRoutes:
    def test_list_profiles_requires_adapter(self, client):
        response = client.get("/api/v1/charging-profiles")

        assert response.status_code == 503
        assert response.json()["detail"] == "OCPP adapter not available"

    def test_list_profiles(self, client, runtime, mock_controller):
        mock_controller.adapter = MagicMock()
        runtime.get_charging_profiles_sync = MagicMock(return_value=[_sample_profile()])

        response = client.get("/api/v1/charging-profiles")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["charging_profile_id"] == 7
        assert data[0]["charging_profile_purpose"] == "TxProfile"

    def test_get_profile(self, client, runtime, mock_controller):
        mock_controller.adapter = MagicMock()
        runtime.get_charging_profile_sync = MagicMock(return_value=_sample_profile())

        response = client.get("/api/v1/charging-profiles/7")

        assert response.status_code == 200
        assert response.json()["charging_profile_id"] == 7

    def test_get_profile_not_found(self, client, runtime, mock_controller):
        mock_controller.adapter = MagicMock()
        runtime.get_charging_profile_sync = MagicMock(return_value=None)

        response = client.get("/api/v1/charging-profiles/99")

        assert response.status_code == 404
        assert response.json()["detail"] == "Profile 99 not found"

    def test_clear_profiles(self, client, runtime, mock_controller):
        mock_controller.adapter = MagicMock()
        runtime.clear_charging_profiles_sync = MagicMock(return_value=3)

        response = client.request(
            "DELETE",
            "/api/v1/charging-profiles",
            json={"connector_id": 1, "purpose": "TxProfile"},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["message"] == "Cleared 3 profile(s)"

    def test_set_profile(self, client, runtime, mock_controller):
        mock_controller.adapter = MagicMock()
        runtime.set_charging_profile_sync = MagicMock(
            return_value=(True, "Profile installed")
        )

        response = client.post(
            "/api/v1/charging-profiles",
            json={"connector_id": 1, "profile": _sample_profile()},
        )

        assert response.status_code == 200
        assert response.json() == {
            "success": True,
            "message": "Profile installed",
            "details": None,
        }

    def test_get_composite_schedule(self, client, runtime, mock_controller):
        mock_controller.adapter = MagicMock()
        runtime.get_composite_schedule_sync = MagicMock(
            return_value={
                "connector_id": 1,
                "duration": 600,
                "start_time": "2024-01-01T12:00:00+00:00",
                "periods": [{"start_period": 0, "limit": 16.0}],
            }
        )

        response = client.post(
            "/api/v1/charging-profiles/composite-schedule",
            json={"connector_id": 1, "duration": 600},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["connector_id"] == 1
        assert data["periods"][0]["limit"] == 16.0
