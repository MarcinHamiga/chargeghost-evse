from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from ocpp.v16.enums import (
    ChargingProfilePurposeType,
    ChargingProfileKindType,
    RecurrencyKind,
    ChargingRateUnitType,
)


@dataclass
class ChargingSchedulePeriodData:
    start_period: int       # seconds from schedule start
    limit: float            # in chargingRateUnit (A or W)
    number_phases: Optional[int] = None


@dataclass
class ChargingScheduleData:
    charging_rate_unit: ChargingRateUnitType
    charging_schedule_period: list[ChargingSchedulePeriodData] = field(default_factory=list)
    duration: Optional[int] = None          # seconds; None = no expiry
    start_schedule: Optional[datetime] = None
    min_charging_rate: Optional[float] = None


@dataclass
class ChargingProfileData:
    charging_profile_id: int
    stack_level: int
    charging_profile_purpose: ChargingProfilePurposeType
    charging_profile_kind: ChargingProfileKindType
    charging_schedule: ChargingScheduleData
    transaction_id: Optional[int] = None
    recurrency_kind: Optional[RecurrencyKind] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
