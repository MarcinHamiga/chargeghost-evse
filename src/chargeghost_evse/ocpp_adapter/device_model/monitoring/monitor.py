from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ocpp.v201.datatypes import ComponentType, VariableType

if TYPE_CHECKING:
    from ocpp.v201.datatypes import VariableMonitoringType


@dataclass(frozen=True)
class VariableMonitor:
    id: int
    component: ComponentType
    variable: VariableType
    monitor_type: str
    value: float
    severity: int
    transaction_id: Optional[str] = None
    last_value: Optional[float] = None
    next_fire_time: Optional[float] = None

    def __post_init__(self) -> None:
        if self.severity < 0 or self.severity > 9:
            raise ValueError(f"severity must be 0-9, got {self.severity}")

    def to_variable_monitoring_type(
        self, transaction: bool
    ) -> "VariableMonitoringType":
        from ocpp.v201.datatypes import VariableMonitoringType
        from ocpp.v201.enums import MonitorEnumType

        return VariableMonitoringType(
            id=self.id,
            transaction=transaction,
            value=self.value,
            type=MonitorEnumType(self.monitor_type),
            severity=self.severity,
        )
