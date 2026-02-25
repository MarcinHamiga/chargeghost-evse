import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ocpp.v16.enums import (
    ChargingProfileKindType,
    ChargingProfilePurposeType,
    ChargingRateUnitType,
    RecurrencyKind,
)


@dataclass(frozen=True)
class ChargingSchedulePeriodData:
    start_period: int       # seconds from schedule start
    limit: float            # in chargingRateUnit (A or W)
    number_phases: Optional[int] = None


@dataclass(frozen=True)
class ChargingScheduleData:
    charging_rate_unit: ChargingRateUnitType
    charging_schedule_period: tuple[ChargingSchedulePeriodData, ...] = ()
    duration: Optional[int] = None          # seconds; None = no expiry
    start_schedule: Optional[datetime] = None
    min_charging_rate: Optional[float] = None


@dataclass(frozen=True)
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


class ChargingProfileManager:
    def __init__(
        self,
        max_profiles: int = 20,
        max_stack_level: int = 5,
        max_schedule_periods: int = 10,
    ):
        self._lock = threading.RLock()
        self.max_profiles = max_profiles
        self.max_stack_level = max_stack_level
        self.max_schedule_periods = max_schedule_periods
        # key: profile_id, value: (connector_id, ChargingProfileData)
        self._profiles: dict[int, tuple[int, ChargingProfileData]] = {}

    def set_profile(
        self, connector_id: int, profile: ChargingProfileData
    ) -> Optional[str]:
        """Store a profile. Returns an error string on rejection, None on success."""
        with self._lock:
            num_periods = len(profile.charging_schedule.charging_schedule_period)
            if num_periods > self.max_schedule_periods:
                return "too_many_periods"
            if profile.stack_level > self.max_stack_level:
                return "stack_level_exceeded"
            if (
                profile.charging_profile_purpose == ChargingProfilePurposeType.tx_profile
                and profile.transaction_id is None
            ):
                return "tx_profile_missing_transaction_id"
            # Replacing an existing profile with same ID doesn't count against limit
            is_replace = profile.charging_profile_id in self._profiles
            if not is_replace and len(self._profiles) >= self.max_profiles:
                return "max_profiles_exceeded"
            self._profiles[profile.charging_profile_id] = (connector_id, profile)
            return None

    def clear_profiles(
        self,
        profile_id: Optional[int] = None,
        connector_id: Optional[int] = None,
        purpose: Optional[ChargingProfilePurposeType] = None,
        stack_level: Optional[int] = None,
    ) -> int:
        """Remove matching profiles. Returns count of removed profiles."""
        with self._lock:
            to_remove = []
            for pid, (cid, profile) in self._profiles.items():
                if profile_id is not None and pid != profile_id:
                    continue
                if connector_id is not None and cid != connector_id:
                    continue
                if purpose is not None and profile.charging_profile_purpose != purpose:
                    continue
                if stack_level is not None and profile.stack_level != stack_level:
                    continue
                to_remove.append(pid)
            for pid in to_remove:
                del self._profiles[pid]
            return len(to_remove)

    def get_profiles_for_purpose(
        self,
        purpose: ChargingProfilePurposeType,
        connector_id: int,
    ) -> list[ChargingProfileData]:
        """Return all profiles matching purpose and connector (including connectorId=0),
        sorted by stack_level descending."""
        with self._lock:
            result = []
            for cid, profile in self._profiles.values():
                if profile.charging_profile_purpose != purpose:
                    continue
                # connectorId=0 applies to all connectors
                if cid != 0 and cid != connector_id:
                    continue
                result.append(profile)
            result.sort(key=lambda p: p.stack_level, reverse=True)
            return result

    def get_all_profiles(self) -> list[tuple[int, ChargingProfileData]]:
        """Return all (connector_id, profile) pairs."""
        with self._lock:
            return list(self._profiles.values())
