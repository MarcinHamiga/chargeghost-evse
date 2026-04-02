from dataclasses import dataclass, field
from typing import Any, Literal, Optional


VALID_FAULT_ACTIONS: frozenset[str] = frozenset(["enable", "disable", "clear_all"])


VALID_ACTIONS = frozenset(
    [
        "connect",
        "disconnect",
        "authorize",
        "plug_in",
        "unplug",
        "start_charging",
        "stop_charging",
        "suspend_ev",
        "resume_charging",
        "set_rfid",
        "clear_rfid",
        "send_heartbeat",
    ]
)

VALID_WAIT_CONDITIONS = frozenset(
    [
        "connector_status",
        "connection_state",
        "session_exists",
        "meter_threshold",
    ]
)

VALID_ASSERT_CONDITIONS = frozenset(
    [
        "connector_status",
        "connection_state",
        "session_exists",
        "meter_threshold",
    ]
)


@dataclass
class ScenarioDefaults:
    connector_id: int = 1
    timeout: Optional[float] = None


@dataclass
class ActionStep:
    kind: Literal["action"] = "action"
    action: str = ""
    label: str = ""
    connector_id: Optional[int] = None
    params: dict[str, Any] = field(default_factory=dict)
    step_index: int = 0


@dataclass
class WaitStep:
    kind: Literal["wait"] = "wait"
    condition: str = "connector_status"
    duration: float = 1.0
    label: str = ""
    connector_id: Optional[int] = None
    expected: Any = None
    step_index: int = 0


@dataclass
class AssertStep:
    kind: Literal["assert"] = "assert"
    condition: str = ""
    expected: Any = None
    label: str = ""
    connector_id: Optional[int] = None
    step_index: int = 0


@dataclass
class NoteStep:
    kind: Literal["note"] = "note"
    message: str = ""
    label: str = ""
    step_index: int = 0


@dataclass
class FaultStep:
    kind: Literal["fault"] = "fault"
    fault_action: str = ""
    fault_id: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    count_limit: Optional[int] = None
    label: str = ""
    step_index: int = 0


ScenarioStep = ActionStep | WaitStep | AssertStep | NoteStep | FaultStep


@dataclass
class ScenarioDefinition:
    schema_version: str = "1.0"
    name: str = ""
    description: str = ""
    version: str = "1.0"
    defaults: ScenarioDefaults = field(default_factory=ScenarioDefaults)
    steps: list[ScenarioStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
