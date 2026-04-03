from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from chargeghost_evse.devtools.scenario_report import ScenarioReport, StepResult
from chargeghost_evse.devtools.scenario_runner import RunnerState


class TestScenarioRoutes:
    def test_load_scenario_valid(self, client):
        scenario_data = {
            "schema_version": "1.0",
            "name": "Test Scenario",
            "description": "A test scenario",
            "version": "1.0",
            "steps": [{"kind": "note", "message": "Hello", "label": "Greeting"}],
        }

        response = client.post("/api/v1/scenarios/load", json=scenario_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Test Scenario" in data["message"]

    def test_load_scenario_invalid(self, client):
        response = client.post(
            "/api/v1/scenarios/load",
            json={
                "schema_version": "1.0",
                "name": "Invalid Scenario",
                "steps": [{"kind": "invalid-kind", "label": "Broken"}],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Failed to load scenario" in data["message"]

    def test_start_scenario_success(self, client, runtime):
        runtime._scenario_runner = MagicMock()
        runtime._scenario_runner.start.return_value = True

        client.post(
            "/api/v1/scenarios/load",
            json={
                "schema_version": "1.0",
                "name": "Test Scenario",
                "steps": [{"kind": "note", "message": "Hello", "label": "Greeting"}],
            },
        )

        response = client.post("/api/v1/scenarios/start")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "started" in data["message"].lower()

    def test_start_scenario_no_scenario_loaded(self, client, runtime):
        runtime._scenario_runner = MagicMock()

        response = client.post("/api/v1/scenarios/start")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "No scenario loaded" in data["message"]

    def test_cancel_scenario(self, client, runtime):
        runtime._scenario_runner = MagicMock()

        response = client.post("/api/v1/scenarios/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cancelled" in data["message"].lower()

    def test_get_status_idle(self, client, runtime):
        runtime._scenario_runner = None

        response = client.get("/api/v1/scenarios/status")

        assert response.status_code == 200
        assert response.json() == {
            "state": "idle",
            "scenario_name": None,
            "current_step_index": 0,
        }

    def test_get_report_empty(self, client, runtime):
        runtime._scenario_runner = None

        response = client.get("/api/v1/scenarios/report")

        assert response.status_code == 200
        assert response.json() == {
            "scenario_name": "",
            "started_at": None,
            "finished_at": None,
            "success": True,
            "failure_reason": None,
            "failed_step_index": None,
            "steps": [],
        }


class TestScenarioRoutesWithRunner:
    def test_scenario_status_when_running(self, client, runtime):
        runtime._scenario_runner = MagicMock()
        runtime._scenario_runner.state = RunnerState.RUNNING
        runtime._scenario_runner._current_step_index = 2
        runtime._loaded_scenario = SimpleNamespace(name="My Scenario")

        response = client.get("/api/v1/scenarios/status")

        assert response.status_code == 200
        assert response.json() == {
            "state": "running",
            "scenario_name": "My Scenario",
            "current_step_index": 2,
        }

    def test_scenario_report_with_results(self, client, runtime):
        report = ScenarioReport(scenario_name="Test Report")
        report.started_at = datetime(2024, 1, 1, 12, 0, 0)
        report.finished_at = datetime(2024, 1, 1, 12, 5, 0)
        report.success = True
        report.add_step_result(
            StepResult(
                step_index=0,
                kind="note",
                label="Start",
                success=True,
                duration=0.001,
            )
        )

        runtime._scenario_runner = MagicMock()
        runtime._scenario_runner.report = report

        response = client.get("/api/v1/scenarios/report")

        assert response.status_code == 200
        data = response.json()
        assert data["scenario_name"] == "Test Report"
        assert data["success"] is True
        assert len(data["steps"]) == 1
        assert data["steps"][0]["label"] == "Start"
