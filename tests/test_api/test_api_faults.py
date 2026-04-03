from __future__ import annotations

from unittest.mock import MagicMock

from chargeghost_evse.devtools.fault_catalog import FAULT_CATALOG
from chargeghost_evse.devtools.fault_models import FaultConfig, FaultState


class TestFaultDefinitionRoutes:
    def test_list_fault_definitions(self, client):
        response = client.get("/api/v1/faults")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == len(FAULT_CATALOG)

        fault_ids = {f["fault_id"] for f in data}
        expected_ids = set(FAULT_CATALOG.keys())
        assert fault_ids == expected_ids

    def test_fault_definition_has_required_fields(self, client):
        response = client.get("/api/v1/faults")

        assert response.status_code == 200
        data = response.json()
        for fault in data:
            assert "fault_id" in fault
            assert "label" in fault
            assert "scope" in fault
            assert "lifetime" in fault


class TestFaultStateRoutes:
    def test_get_active_faults_empty(self, client, mock_controller):
        mock_controller.fault_manager = MagicMock()
        mock_controller.fault_manager.get_active_summary.return_value = []

        response = client.get("/api/v1/faults/active")

        assert response.status_code == 200
        assert response.json() == []

    def test_get_active_faults_with_faults(self, client, mock_controller):
        mock_controller.fault_manager = MagicMock()
        mock_controller.fault_manager.get_active_summary.return_value = [
            FaultState(
                fault_id="forced_disconnect",
                enabled=True,
                trigger_count=1,
                config=FaultConfig(fault_id="forced_disconnect", parameters={}),
            ),
            FaultState(
                fault_id="delayed_reconnect",
                enabled=True,
                trigger_count=5,
                config=FaultConfig(
                    fault_id="delayed_reconnect", parameters={"delay_seconds": 30}
                ),
            ),
        ]

        response = client.get("/api/v1/faults/active")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["fault_id"] == "forced_disconnect"
        assert data[0]["enabled"] is True
        assert data[0]["trigger_count"] == 1
        assert data[1]["fault_id"] == "delayed_reconnect"
        assert data[1]["trigger_count"] == 5

    def test_get_fault_state_found(self, client, mock_controller):
        mock_controller.fault_manager = MagicMock()
        mock_controller.fault_manager.peek.return_value = FaultState(
            fault_id="frozen_meter",
            enabled=True,
            trigger_count=3,
            config=None,
        )

        response = client.get("/api/v1/faults/frozen_meter")

        assert response.status_code == 200
        data = response.json()
        assert data["fault_id"] == "frozen_meter"
        assert data["enabled"] is True
        assert data["trigger_count"] == 3

    def test_get_fault_state_not_found(self, client, mock_controller):
        mock_controller.fault_manager = MagicMock()
        mock_controller.fault_manager.peek.return_value = None

        response = client.get("/api/v1/faults/nonexistent_fault")

        assert response.status_code == 200
        assert response.json() is None

    def test_enable_fault_success(self, client, mock_controller):
        mock_controller.fault_manager = MagicMock()

        response = client.post("/api/v1/faults/frozen_meter/enable")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "enabled" in data["message"].lower()

    def test_enable_fault_with_config(self, client, mock_controller):
        mock_controller.fault_manager = MagicMock()

        response = client.post(
            "/api/v1/faults/delayed_reconnect/enable",
            json={"fault_id": "delayed_reconnect", "parameters": {"delay_seconds": 60}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_enable_fault_invalid_id(self, client, mock_controller):
        mock_controller.fault_manager = MagicMock()
        mock_controller.fault_manager.enable.side_effect = ValueError(
            "Unknown fault ID: invalid_fault"
        )

        response = client.post("/api/v1/faults/invalid_fault/enable")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    def test_disable_fault_success(self, client, mock_controller):
        mock_controller.fault_manager = MagicMock()

        response = client.post("/api/v1/faults/frozen_meter/disable")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "disabled" in data["message"].lower()

    def test_clear_all_faults(self, client, mock_controller):
        mock_controller.fault_manager = MagicMock()

        response = client.post("/api/v1/faults/clear")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cleared" in data["message"].lower()
