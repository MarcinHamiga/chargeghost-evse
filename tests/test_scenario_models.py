import json
from pathlib import Path

import pytest

from chargeghost_evse.devtools.scenario_loader import ScenarioLoader, ScenarioLoadError


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "scenarios"


class TestScenarioLoader:
    def test_load_scenario_definition_from_json(self) -> None:
        path = FIXTURES_DIR / "happy_path.json"
        result = ScenarioLoader.load(path)
        assert result.name == "Happy Path Scenario"
        assert result.version == "1.0"
        assert len(result.steps) == 10
        assert result.steps[0].kind == "action"
        assert result.steps[0].action == "connect"

    def test_loader_rejects_unknown_step_kind(self) -> None:
        data = {
            "schema_version": "1.0",
            "name": "Bad Step Kind",
            "description": "Test",
            "steps": [
                {"kind": "unknown_step", "label": "Bad Step"}
            ]
        }
        with pytest.raises(ScenarioLoadError) as exc_info:
            ScenarioLoader.from_dict(data)
        assert "unknown step kind" in str(exc_info.value).lower()

    def test_loader_rejects_unknown_action_name(self) -> None:
        data = {
            "schema_version": "1.0",
            "name": "Bad Action",
            "description": "Test",
            "steps": [
                {"kind": "action", "action": "invalid_action_name", "label": "Bad Action"}
            ]
        }
        with pytest.raises(ScenarioLoadError) as exc_info:
            ScenarioLoader.from_dict(data)
        assert "unknown action" in str(exc_info.value).lower()

    def test_step_overrides_default_connector_id(self) -> None:
        path = FIXTURES_DIR / "happy_path.json"
        result = ScenarioLoader.load(path)
        defaults = result.defaults
        assert defaults.connector_id == 1
        step_with_override = result.steps[2]
        assert step_with_override.connector_id == 2

    def test_loader_requires_schema_version(self) -> None:
        data = {
            "name": "Missing Schema Version",
            "description": "Test",
            "steps": []
        }
        with pytest.raises(ScenarioLoadError) as exc_info:
            ScenarioLoader.from_dict(data)
        assert "schema_version" in str(exc_info.value).lower()

    def test_loader_requires_steps(self) -> None:
        data = {
            "schema_version": "1.0",
            "name": "Missing Steps",
            "description": "Test"
        }
        with pytest.raises(ScenarioLoadError) as exc_info:
            ScenarioLoader.from_dict(data)
        assert "steps" in str(exc_info.value).lower()

    def test_wait_step_parses_duration(self) -> None:
        path = FIXTURES_DIR / "wait_and_assert.json"
        result = ScenarioLoader.load(path)
        wait_step = result.steps[1]
        assert wait_step.kind == "wait"
        assert wait_step.duration == 2.0

    def test_assert_step_parses_conditions(self) -> None:
        path = FIXTURES_DIR / "wait_and_assert.json"
        result = ScenarioLoader.load(path)
        assert_step = result.steps[2]
        assert assert_step.kind == "assert"
        assert assert_step.condition == "session_exists"
        assert assert_step.expected is False

    def test_note_step_preserves_message(self) -> None:
        path = FIXTURES_DIR / "happy_path.json"
        result = ScenarioLoader.load(path)
        note_step = result.steps[7]
        assert note_step.kind == "note"
        assert "suspend" in note_step.message.lower()

    def test_action_step_preserves_label(self) -> None:
        path = FIXTURES_DIR / "happy_path.json"
        result = ScenarioLoader.load(path)
        action_step = result.steps[0]
        assert action_step.label == "Connect to CS"

    def test_action_step_default_connector_id_from_defaults(self) -> None:
        path = FIXTURES_DIR / "happy_path.json"
        result = ScenarioLoader.load(path)
        action_step = result.steps[0]
        assert action_step.connector_id == 1

    def test_unknown_action_in_action_step_rejected(self) -> None:
        data = {
            "schema_version": "1.0",
            "name": "Test",
            "description": "Test",
            "steps": [
                {"kind": "action", "action": "fly_to_the_moon", "label": "Bad"}
            ]
        }
        with pytest.raises(ScenarioLoadError) as exc_info:
            ScenarioLoader.from_dict(data)
        assert "unknown action" in str(exc_info.value).lower()
