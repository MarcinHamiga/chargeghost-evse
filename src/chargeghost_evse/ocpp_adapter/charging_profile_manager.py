import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
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

    def get_composite_limit(
        self,
        connector_id: int,
        transaction_id: Optional[int],
        now: datetime,
        connector_voltage: float,
        transaction_start: Optional[datetime] = None,
        phases: int = 1,
    ) -> Optional[float]:
        """Return effective current limit in Amps, or None if no active profiles."""
        cp_max_limit = self._resolve_purpose_limit(
            ChargingProfilePurposeType.charge_point_max_profile,
            connector_id, transaction_id, now, connector_voltage,
            transaction_start, phases,
        )
        tx_limit = self._resolve_tx_limit(
            connector_id, transaction_id, now, connector_voltage,
            transaction_start, phases,
        )
        active_limits = [lim for lim in [cp_max_limit, tx_limit] if lim is not None]
        if not active_limits:
            return None
        return min(active_limits)

    def _resolve_tx_limit(
        self,
        connector_id: int,
        transaction_id: Optional[int],
        now: datetime,
        connector_voltage: float,
        transaction_start: Optional[datetime],
        phases: int,
    ) -> Optional[float]:
        """TxProfile takes precedence over TxDefaultProfile."""
        if transaction_id is not None:
            tx_limit = self._resolve_purpose_limit(
                ChargingProfilePurposeType.tx_profile,
                connector_id, transaction_id, now, connector_voltage,
                transaction_start, phases,
            )
            if tx_limit is not None:
                return tx_limit
        return self._resolve_purpose_limit(
            ChargingProfilePurposeType.tx_default_profile,
            connector_id, transaction_id, now, connector_voltage,
            transaction_start, phases,
        )

    def _resolve_purpose_limit(
        self,
        purpose: ChargingProfilePurposeType,
        connector_id: int,
        transaction_id: Optional[int],
        now: datetime,
        connector_voltage: float,
        transaction_start: Optional[datetime],
        phases: int,
    ) -> Optional[float]:
        profiles = self.get_profiles_for_purpose(purpose, connector_id)
        if purpose == ChargingProfilePurposeType.tx_profile:
            profiles = [p for p in profiles if p.transaction_id == transaction_id]
        profiles = [p for p in profiles if self._is_valid_at(p, now)]
        if not profiles:
            return None
        profile = profiles[0]
        return self._get_limit_from_profile(
            profile, now, connector_voltage, transaction_start, phases
        )

    def _is_valid_at(self, profile: ChargingProfileData, now: datetime) -> bool:
        if profile.valid_from is not None and now < profile.valid_from:
            return False
        if profile.valid_to is not None and now > profile.valid_to:
            return False
        return True

    def _get_limit_from_profile(
        self,
        profile: ChargingProfileData,
        now: datetime,
        connector_voltage: float,
        transaction_start: Optional[datetime],
        phases: int,
    ) -> Optional[float]:
        schedule = profile.charging_schedule

        if profile.charging_profile_kind == ChargingProfileKindType.relative:
            if transaction_start is None:
                return None
            elapsed = (now - transaction_start).total_seconds()
        elif profile.charging_profile_kind == ChargingProfileKindType.absolute:
            if schedule.start_schedule is None:
                elapsed = 0.0
            else:
                elapsed = (now - schedule.start_schedule).total_seconds()
            if elapsed < 0:
                return None
        elif profile.charging_profile_kind == ChargingProfileKindType.recurring:
            if schedule.start_schedule is None:
                return None
            total_elapsed = (now - schedule.start_schedule).total_seconds()
            if total_elapsed < 0:
                return None
            cycle = 86400.0 if profile.recurrency_kind == RecurrencyKind.daily else 604800.0
            elapsed = total_elapsed % cycle
        else:
            return None

        if schedule.duration is not None and elapsed > schedule.duration:
            return None

        limit = self._find_period_limit(schedule.charging_schedule_period, elapsed)
        if limit is None:
            return None

        if schedule.charging_rate_unit == ChargingRateUnitType.watts:
            if connector_voltage <= 0:
                return None
            effective_phases = phases if phases > 0 else 1
            limit = limit / (connector_voltage * effective_phases)

        return limit

    def _find_period_limit(
        self,
        periods: tuple,
        elapsed: float,
    ) -> Optional[float]:
        if not periods:
            return None
        sorted_periods = sorted(periods, key=lambda p: p.start_period)
        active_limit = sorted_periods[0].limit
        for period in sorted_periods:
            if period.start_period <= elapsed:
                active_limit = period.limit
            else:
                break
        return active_limit

    def get_composite_schedule(
        self,
        connector_id: int,
        transaction_id: Optional[int],
        start_time: datetime,
        duration: int,
        connector_voltage: float,
        transaction_start: Optional[datetime] = None,
        phases: int = 1,
    ) -> list[ChargingSchedulePeriodData]:
        """
        Build a composite schedule for a connector and time window.

        Returns a list of ChargingSchedulePeriodData representing the effective
        schedule, combining ChargePointMaxProfile with TxDefaultProfile/TxProfile.
        Limits are returned in Amps.
        """
        with self._lock:
            boundaries: set[int] = {0}
            end_time = start_time + timedelta(seconds=duration)

            cp_max_profiles = self._get_active_profiles_for_window(
                ChargingProfilePurposeType.charge_point_max_profile,
                connector_id, transaction_id, start_time, end_time,
            )
            tx_profiles = self._get_active_tx_profiles_for_window(
                connector_id, transaction_id, start_time, end_time,
            )

            boundaries.update(
                self._collect_period_boundaries(
                    cp_max_profiles, start_time, transaction_start, duration
                )
            )
            boundaries.update(
                self._collect_period_boundaries(
                    tx_profiles, start_time, transaction_start, duration
                )
            )

            sorted_boundaries = sorted(b for b in boundaries if 0 <= b < duration)
            if not sorted_boundaries:
                sorted_boundaries = [0]

            schedule_periods: list[ChargingSchedulePeriodData] = []
            prev_limit: Optional[float] = None

            for boundary in sorted_boundaries:
                sample_time = start_time + timedelta(seconds=boundary)
                composite_limit = self._compute_composite_limit_at(
                    cp_max_profiles, tx_profiles,
                    sample_time, connector_voltage, transaction_start, phases,
                )
                if composite_limit is None:
                    continue
                if prev_limit is None or composite_limit != prev_limit:
                    schedule_periods.append(
                        ChargingSchedulePeriodData(
                            start_period=boundary,
                            limit=composite_limit,
                            number_phases=phases if phases != 1 else None,
                        )
                    )
                    prev_limit = composite_limit

            return schedule_periods

    def _get_active_profiles_for_window(
        self,
        purpose: ChargingProfilePurposeType,
        connector_id: int,
        transaction_id: Optional[int],
        start_time: datetime,
        end_time: datetime,
    ) -> list[ChargingProfileData]:
        """Get profiles valid during the time window for a purpose."""
        profiles = self.get_profiles_for_purpose(purpose, connector_id)
        if purpose == ChargingProfilePurposeType.tx_profile:
            profiles = [p for p in profiles if p.transaction_id == transaction_id]
        return [
            p for p in profiles
            if self._is_valid_in_window(p, start_time, end_time)
        ]

    def _get_active_tx_profiles_for_window(
        self,
        connector_id: int,
        transaction_id: Optional[int],
        start_time: datetime,
        end_time: datetime,
    ) -> list[ChargingProfileData]:
        """Get active TxProfile or TxDefaultProfile for the window."""
        if transaction_id is not None:
            tx_profiles = self._get_active_profiles_for_window(
                ChargingProfilePurposeType.tx_profile,
                connector_id, transaction_id, start_time, end_time,
            )
            if tx_profiles:
                return tx_profiles
        return self._get_active_profiles_for_window(
            ChargingProfilePurposeType.tx_default_profile,
            connector_id, transaction_id, start_time, end_time,
        )

    def _is_valid_in_window(
        self,
        profile: ChargingProfileData,
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        """Check if profile is active at any point in the time window."""
        if profile.valid_from is not None and profile.valid_from > end_time:
            return False
        if profile.valid_to is not None and profile.valid_to < start_time:
            return False
        return True

    def _collect_period_boundaries(
        self,
        profiles: list[ChargingProfileData],
        start_time: datetime,
        transaction_start: Optional[datetime],
        duration: int,
    ) -> set[int]:
        """Collect all period start times (in seconds from start_time) from profiles."""
        boundaries: set[int] = set()
        for profile in profiles:
            schedule = profile.charging_schedule
            base_time = self._get_profile_base_time(profile, transaction_start)
            if base_time is None:
                continue
            for period in schedule.charging_schedule_period:
                if base_time is None:
                    continue
                period_time = base_time + timedelta(seconds=period.start_period)
                offset = int((period_time - start_time).total_seconds())
                if 0 <= offset < duration:
                    boundaries.add(offset)
        return boundaries

    def _get_profile_base_time(
        self,
        profile: ChargingProfileData,
        transaction_start: Optional[datetime],
    ) -> Optional[datetime]:
        """Get the base time for calculating period offsets."""
        schedule = profile.charging_schedule
        if profile.charging_profile_kind == ChargingProfileKindType.relative:
            return transaction_start
        elif profile.charging_profile_kind == ChargingProfileKindType.absolute:
            return schedule.start_schedule if schedule.start_schedule else None
        elif profile.charging_profile_kind == ChargingProfileKindType.recurring:
            return schedule.start_schedule
        return None

    def _compute_composite_limit_at(
        self,
        cp_max_profiles: list[ChargingProfileData],
        tx_profiles: list[ChargingProfileData],
        sample_time: datetime,
        connector_voltage: float,
        transaction_start: Optional[datetime],
        phases: int,
    ) -> Optional[float]:
        """Compute composite limit at a specific time from pre-filtered profiles."""
        cp_max_limit: Optional[float] = None
        if cp_max_profiles:
            profile = cp_max_profiles[0]
            cp_max_limit = self._get_limit_from_profile(
                profile, sample_time, connector_voltage, transaction_start, phases
            )

        tx_limit: Optional[float] = None
        if tx_profiles:
            profile = tx_profiles[0]
            tx_limit = self._get_limit_from_profile(
                profile, sample_time, connector_voltage, transaction_start, phases
            )

        active_limits = [lim for lim in [cp_max_limit, tx_limit] if lim is not None]
        if not active_limits:
            return None
        return min(active_limits)
