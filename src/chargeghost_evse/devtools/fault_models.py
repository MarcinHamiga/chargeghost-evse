from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FaultLifetime(Enum):
    PERSISTENT = "persistent"
    ONE_SHOT = "one_shot"
    COUNT_LIMITED = "count_limited"


class FaultScope(Enum):
    TRANSPORT = "transport"
    PROTOCOL = "protocol"
    METER = "meter"
    STATE = "state"


@dataclass(frozen=True)
class FaultDefinition:
    fault_id: str
    label: str
    scope: FaultScope
    lifetime: FaultLifetime
    default_config: Optional[dict] = None


@dataclass
class FaultConfig:
    fault_id: str
    parameters: dict = field(default_factory=dict)
    count_limit: Optional[int] = None


@dataclass
class FaultState:
    fault_id: str
    enabled: bool = False
    trigger_count: int = 0
    config: Optional[FaultConfig] = None


@dataclass(frozen=True)
class FaultTriggerResult:
    fault_id: str
    triggered: bool
    remaining: Optional[int] = None
