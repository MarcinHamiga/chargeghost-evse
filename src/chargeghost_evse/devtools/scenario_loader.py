import json
from pathlib import Path

from chargeghost_evse.devtools.scenario_models import (
    ActionStep,
    AssertStep,
    NoteStep,
    ScenarioDefinition,
    ScenarioDefaults,
    VALID_ACTIONS,
    VALID_ASSERT_CONDITIONS,
    VALID_WAIT_CONDITIONS,
    WaitStep,
)


class ScenarioLoadError(ValueError):
    pass


class ScenarioLoader:
    @classmethod
    def load(cls, path: Path) -> ScenarioDefinition:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> ScenarioDefinition:
        schema_version = data.get("schema_version")
        if not schema_version:
            raise ScenarioLoadError("Missing required field: schema_version")

        steps_data = data.get("steps")
        if steps_data is None:
            raise ScenarioLoadError("Missing required field: steps")

        if not isinstance(steps_data, list):
            raise ScenarioLoadError("steps must be a list")

        defaults_data = data.get("defaults", {})
        defaults = cls._parse_defaults(defaults_data)

        steps = []
        for idx, step_data in enumerate(steps_data):
            step = cls._parse_step(step_data, idx, defaults)
            steps.append(step)

        known_fields = {"schema_version", "name", "description", "version", "defaults", "steps"}
        metadata = {k: v for k, v in data.items() if k not in known_fields}

        return ScenarioDefinition(
            schema_version=schema_version,
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
            defaults=defaults,
            steps=steps,
            metadata=metadata,
        )

    @classmethod
    def _parse_defaults(cls, data: dict) -> ScenarioDefaults:
        return ScenarioDefaults(
            connector_id=data.get("connector_id", 1),
            timeout=data.get("timeout"),
        )

    @classmethod
    def _parse_step(
        cls, data: dict, index: int, defaults: ScenarioDefaults
    ) -> ActionStep | WaitStep | AssertStep | NoteStep:
        kind = data.get("kind")
        if kind == "action":
            return cls._parse_action_step(data, index, defaults)
        elif kind == "wait":
            return cls._parse_wait_step(data, index, defaults)
        elif kind == "assert":
            return cls._parse_assert_step(data, index, defaults)
        elif kind == "note":
            return cls._parse_note_step(data, index)
        else:
            raise ScenarioLoadError(f"Unknown step kind: {kind!r}")

    @classmethod
    def _parse_action_step(
        cls, data: dict, index: int, defaults: ScenarioDefaults
    ) -> ActionStep:
        action = data.get("action", "")
        if action not in VALID_ACTIONS:
            raise ScenarioLoadError(f"Unknown action: {action!r}")
        return ActionStep(
            kind="action",
            action=action,
            label=data.get("label", ""),
            connector_id=data.get("connector_id", defaults.connector_id),
            params=data.get("params", {}),
            step_index=index,
        )

    @classmethod
    def _parse_wait_step(
        cls, data: dict, index: int, defaults: ScenarioDefaults
    ) -> WaitStep:
        condition = data.get("condition", "connector_status")
        if condition not in VALID_WAIT_CONDITIONS:
            raise ScenarioLoadError(f"Unknown wait condition: {condition!r}")
        return WaitStep(
            kind="wait",
            condition=condition,
            duration=float(data.get("duration", 1.0)),
            label=data.get("label", ""),
            connector_id=data.get("connector_id", defaults.connector_id),
            expected=data.get("expected"),
            step_index=index,
        )

    @classmethod
    def _parse_assert_step(
        cls, data: dict, index: int, defaults: ScenarioDefaults
    ) -> AssertStep:
        condition = data.get("condition", "")
        if condition not in VALID_ASSERT_CONDITIONS:
            raise ScenarioLoadError(f"Unknown assert condition: {condition!r}")
        return AssertStep(
            kind="assert",
            condition=condition,
            expected=data.get("expected"),
            label=data.get("label", ""),
            connector_id=data.get("connector_id", defaults.connector_id),
            step_index=index,
        )

    @classmethod
    def _parse_note_step(cls, data: dict, index: int) -> NoteStep:
        return NoteStep(
            kind="note",
            message=data.get("message", ""),
            label=data.get("label", ""),
            step_index=index,
        )
