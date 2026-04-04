import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from ocpp.v201.enums import (
    ChargingProfileKindEnumType,
    ChargingProfilePurposeEnumType,
    ChargingRateUnitEnumType,
    RecurrencyKindEnumType,
)


@dataclass(frozen=True)
class ChargingSchedulePeriodDataV201:
    start_period: int
    limit: float
    number_phases: Optional[int] = None
    phase_to_use: Optional[int] = None


@dataclass(frozen=True)
class ChargingScheduleDataV201:
    id: int
    charging_rate_unit: ChargingRateUnitEnumType
    charging_schedule_period: tuple[ChargingSchedulePeriodDataV201, ...] = ()
    start_schedule: Optional[datetime] = None
    duration: Optional[int] = None
    min_charging_rate: Optional[float] = None


@dataclass(frozen=True)
class ChargingProfileDataV201:
    charging_profile_id: int
    stack_level: int
    charging_profile_purpose: ChargingProfilePurposeEnumType
    charging_profile_kind: ChargingProfileKindEnumType
    charging_schedules: tuple[ChargingScheduleDataV201, ...]
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    transaction_id: Optional[str] = None
    recurrency_kind: Optional[RecurrencyKindEnumType] = None

    def to_ocpp_dict(self) -> dict:
        schedule_dicts = []
        for sched in self.charging_schedules:
            period_dicts = []
            for p in sched.charging_schedule_period:
                pd: dict[str, object] = {
                    "start_period": p.start_period,
                    "limit": p.limit,
                }
                if p.number_phases is not None:
                    pd["number_phases"] = p.number_phases
                if p.phase_to_use is not None:
                    pd["phase_to_use"] = p.phase_to_use
                period_dicts.append(pd)

            sd: dict[str, object] = {
                "id": sched.id,
                "charging_rate_unit": sched.charging_rate_unit.value,
                "charging_schedule_period": period_dicts,
            }
            if sched.start_schedule is not None:
                sd["start_schedule"] = sched.start_schedule.isoformat()
            if sched.duration is not None:
                sd["duration"] = sched.duration
            if sched.min_charging_rate is not None:
                sd["min_charging_rate"] = sched.min_charging_rate
            schedule_dicts.append(sd)

        result: dict[str, object] = {
            "id": self.charging_profile_id,
            "stack_level": self.stack_level,
            "charging_profile_purpose": self.charging_profile_purpose.value,
            "charging_profile_kind": self.charging_profile_kind.value,
            "charging_schedule": schedule_dicts,
        }
        if self.transaction_id is not None:
            result["transaction_id"] = self.transaction_id
        if self.recurrency_kind is not None:
            result["recurrency_kind"] = self.recurrency_kind.value
        if self.valid_from is not None:
            result["valid_from"] = self.valid_from.isoformat()
        if self.valid_to is not None:
            result["valid_to"] = self.valid_to.isoformat()
        return result


class ChargingProfileManagerV201:
    def __init__(
        self,
        max_profiles: int = 20,
        max_stack_level: int = 5,
        max_schedule_periods: int = 10,
    ) -> None:
        self._lock = threading.RLock()
        self.max_profiles = max_profiles
        self.max_stack_level = max_stack_level
        self.max_schedule_periods = max_schedule_periods
        self._profiles: dict[int, tuple[int, ChargingProfileDataV201]] = {}
        self.logger = logging.getLogger("chargeghost.ocpp.profiles.v201")

    def set_profile(
        self, evse_id: int, profile: ChargingProfileDataV201
    ) -> Optional[str]:
        with self._lock:
            for sched in profile.charging_schedules:
                num_periods = len(sched.charging_schedule_period)
                if num_periods > self.max_schedule_periods:
                    return "too_many_periods"

            if profile.stack_level > self.max_stack_level:
                return "stack_level_exceeded"

            replaced_profile_ids = []
            if (
                profile.charging_profile_purpose
                == ChargingProfilePurposeEnumType.tx_profile
            ):
                for existing_id, (
                    existing_evse_id,
                    existing_profile,
                ) in self._profiles.items():
                    if existing_id == profile.charging_profile_id:
                        continue
                    if existing_evse_id != evse_id:
                        continue
                    if (
                        existing_profile.charging_profile_purpose
                        != profile.charging_profile_purpose
                    ):
                        continue
                    if existing_profile.stack_level != profile.stack_level:
                        continue
                    if existing_profile.transaction_id != profile.transaction_id:
                        continue
                    replaced_profile_ids.append(existing_id)

            is_replace = profile.charging_profile_id in self._profiles or bool(
                replaced_profile_ids
            )
            if not is_replace and len(self._profiles) >= self.max_profiles:
                return "max_profiles_exceeded"

            for existing_id in replaced_profile_ids:
                del self._profiles[existing_id]

            self._profiles[profile.charging_profile_id] = (evse_id, profile)
            if profile.charging_schedules:
                first_sched = profile.charging_schedules[0]
                if first_sched.charging_schedule_period:
                    self.logger.info(
                        f"V201 Profile installed: {profile.charging_profile_purpose.value} "
                        f"#{profile.charging_profile_id} "
                        f"(stack_level={profile.stack_level}, "
                        f"{profile.charging_profile_kind.value}, "
                        f"{first_sched.charging_schedule_period[0].limit}A limit)",
                        extra={"source": "ocpp", "evse_id": evse_id},
                    )
                else:
                    self.logger.info(
                        f"V201 Profile installed: {profile.charging_profile_purpose.value} "
                        f"#{profile.charging_profile_id}",
                        extra={"source": "ocpp", "evse_id": evse_id},
                    )
            return None

    def get_profile_ids(self) -> list[int]:
        with self._lock:
            return sorted(self._profiles.keys())

    def clear_profiles(
        self,
        profile_id: Optional[int] = None,
        evse_id: Optional[int] = None,
        purpose: Optional[ChargingProfilePurposeEnumType] = None,
        stack_level: Optional[int] = None,
    ) -> int:
        with self._lock:
            to_remove = []
            for pid, (eid, profile) in self._profiles.items():
                if profile_id is not None and pid != profile_id:
                    continue
                if evse_id is not None and eid != evse_id:
                    continue
                if purpose is not None and profile.charging_profile_purpose != purpose:
                    continue
                if stack_level is not None and profile.stack_level != stack_level:
                    continue
                to_remove.append(pid)

            for pid in to_remove:
                del self._profiles[pid]

            if to_remove:
                self.logger.info(
                    f"V201 Profile(s) cleared: {to_remove}",
                    extra={"source": "ocpp"},
                )
            return len(to_remove)

    def get_profiles_for_purpose(
        self,
        purpose: ChargingProfilePurposeEnumType,
        evse_id: int,
    ) -> list[ChargingProfileDataV201]:
        with self._lock:
            result = []
            for eid, profile in self._profiles.values():
                if profile.charging_profile_purpose != purpose:
                    continue
                if eid != 0 and eid != evse_id:
                    continue
                result.append(profile)

            result.sort(key=lambda p: p.stack_level, reverse=True)
            return result

    def get_all_profiles(self) -> list[tuple[int, ChargingProfileDataV201]]:
        with self._lock:
            return list(self._profiles.values())

    def get_composite_limit(
        self,
        evse_id: int,
        transaction_id: Optional[str],
        now: datetime,
        connector_voltage: float,
        transaction_start: Optional[datetime] = None,
        phases: int = 1,
    ) -> Optional[float]:
        purposes_ordered = [
            ChargingProfilePurposeEnumType.tx_profile,
            ChargingProfilePurposeEnumType.tx_default_profile,
            ChargingProfilePurposeEnumType.charging_station_max_profile,
            ChargingProfilePurposeEnumType.charging_station_external_constraints,
        ]

        cp_max_limit: Optional[float] = None
        tx_limit: Optional[float] = None
        ext_limit: Optional[float] = None

        for purpose in purposes_ordered:
            if (
                purpose
                == ChargingProfilePurposeEnumType.charging_station_external_constraints
            ):
                limit = self._resolve_purpose_limit(
                    purpose,
                    evse_id,
                    transaction_id,
                    now,
                    connector_voltage,
                    transaction_start,
                    phases,
                )
                if limit is not None:
                    ext_limit = limit
            elif purpose == ChargingProfilePurposeEnumType.charging_station_max_profile:
                limit = self._resolve_purpose_limit(
                    purpose,
                    evse_id,
                    transaction_id,
                    now,
                    connector_voltage,
                    transaction_start,
                    phases,
                )
                if limit is not None:
                    cp_max_limit = limit
            elif purpose in (
                ChargingProfilePurposeEnumType.tx_profile,
                ChargingProfilePurposeEnumType.tx_default_profile,
            ):
                if purpose == ChargingProfilePurposeEnumType.tx_profile:
                    limit = self._resolve_purpose_limit(
                        purpose,
                        evse_id,
                        transaction_id,
                        now,
                        connector_voltage,
                        transaction_start,
                        phases,
                    )
                    if limit is not None:
                        tx_limit = limit
                else:
                    if tx_limit is None:
                        limit = self._resolve_purpose_limit(
                            purpose,
                            evse_id,
                            transaction_id,
                            now,
                            connector_voltage,
                            transaction_start,
                            phases,
                        )
                        if limit is not None:
                            tx_limit = limit

        active_limits = [lim for lim in [cp_max_limit, tx_limit] if lim is not None]
        if ext_limit is not None:
            active_limits.append(ext_limit)

        if not active_limits:
            self.logger.debug(
                f"No active V201 profile for evse {evse_id}",
                extra={
                    "source": "ocpp",
                    "evse_id": evse_id,
                    "evaluated_profiles": [],
                    "computed_limit_amps": None,
                },
            )
            return None

        evaluated = []
        if cp_max_limit is not None:
            evaluated.append("ChargingStationMaxProfile")
        if tx_limit is not None:
            evaluated.append("TxProfile/TxDefaultProfile")
        if ext_limit is not None:
            evaluated.append("ChargingStationExternalConstraints")
        result = min(active_limits)
        self.logger.debug(
            f"V201 Profile evaluation for evse {evse_id}: limit={result}A",
            extra={
                "source": "ocpp",
                "evse_id": evse_id,
                "evaluated_profiles": evaluated,
                "computed_limit_amps": result,
            },
        )
        return result

    def _resolve_purpose_limit(
        self,
        purpose: ChargingProfilePurposeEnumType,
        evse_id: int,
        transaction_id: Optional[str],
        now: datetime,
        connector_voltage: float,
        transaction_start: Optional[datetime],
        phases: int,
    ) -> Optional[float]:
        profiles = self.get_profiles_for_purpose(purpose, evse_id)

        if purpose == ChargingProfilePurposeEnumType.tx_profile:
            profiles = [p for p in profiles if p.transaction_id == transaction_id]

        profiles = [p for p in profiles if self._is_valid_at(p, now)]

        if not profiles:
            return None

        profile = profiles[0]
        return self._get_limit_from_profile(
            profile, now, connector_voltage, transaction_start, phases
        )

    def _is_valid_at(self, profile: ChargingProfileDataV201, now: datetime) -> bool:
        if profile.valid_from is not None and now < profile.valid_from:
            return False
        if profile.valid_to is not None and now > profile.valid_to:
            return False
        return True

    def _get_limit_from_profile(
        self,
        profile: ChargingProfileDataV201,
        now: datetime,
        connector_voltage: float,
        transaction_start: Optional[datetime],
        phases: int,
    ) -> Optional[float]:
        all_periods: list[tuple[float, float, int]] = []

        for sched in profile.charging_schedules:
            elapsed = self._compute_elapsed(profile, sched, now, transaction_start)
            if elapsed is None:
                continue

            if sched.duration is not None and elapsed > sched.duration:
                continue

            limit = self._find_period_limit(sched.charging_schedule_period, elapsed)
            if limit is None:
                continue

            if sched.charging_rate_unit == ChargingRateUnitEnumType.watts:
                if connector_voltage <= 0:
                    continue
                effective_phases = phases if phases > 0 else 1
                limit = limit / (connector_voltage * effective_phases)

            all_periods.append((elapsed, limit, sched.id))

        if not all_periods:
            return None

        return min(p[1] for p in all_periods)

    def _compute_elapsed(
        self,
        profile: ChargingProfileDataV201,
        sched: ChargingScheduleDataV201,
        now: datetime,
        transaction_start: Optional[datetime],
    ) -> Optional[float]:
        if profile.charging_profile_kind == ChargingProfileKindEnumType.relative:
            if transaction_start is None:
                return None
            elapsed = (now - transaction_start).total_seconds()

        elif profile.charging_profile_kind == ChargingProfileKindEnumType.absolute:
            if sched.start_schedule is None:
                elapsed = 0.0
            else:
                elapsed = (now - sched.start_schedule).total_seconds()
            if elapsed < 0:
                return None

        elif profile.charging_profile_kind == ChargingProfileKindEnumType.recurring:
            if sched.start_schedule is None:
                return None
            total_elapsed = (now - sched.start_schedule).total_seconds()
            if total_elapsed < 0:
                return None
            cycle = (
                86400.0
                if profile.recurrency_kind == RecurrencyKindEnumType.daily
                else 604800.0
            )
            elapsed = total_elapsed % cycle

        else:
            return None

        return elapsed

    def _find_period_limit(
        self,
        periods: tuple[ChargingSchedulePeriodDataV201, ...],
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
        evse_id: int,
        transaction_id: Optional[str],
        start_time: datetime,
        duration: int,
        connector_voltage: float,
        transaction_start: Optional[datetime] = None,
        phases: int = 1,
    ) -> list[ChargingSchedulePeriodDataV201]:
        with self._lock:
            boundaries: set[int] = {0}
            end_time = start_time + timedelta(seconds=duration)

            cp_max_profiles = self._get_active_profiles_for_window(
                ChargingProfilePurposeEnumType.charging_station_max_profile,
                evse_id,
                transaction_id,
                start_time,
                end_time,
            )
            tx_profiles = self._get_active_tx_profiles_for_window(
                evse_id,
                transaction_id,
                start_time,
                end_time,
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

            schedule_periods: list[ChargingSchedulePeriodDataV201] = []
            prev_limit: Optional[float] = None

            for boundary in sorted_boundaries:
                sample_time = start_time + timedelta(seconds=boundary)
                composite_limit = self._compute_composite_limit_at(
                    cp_max_profiles,
                    tx_profiles,
                    sample_time,
                    connector_voltage,
                    transaction_start,
                    phases,
                )

                if composite_limit is None:
                    continue

                if prev_limit is None or composite_limit != prev_limit:
                    schedule_periods.append(
                        ChargingSchedulePeriodDataV201(
                            start_period=boundary,
                            limit=composite_limit,
                            number_phases=phases if phases != 1 else None,
                        )
                    )
                    prev_limit = composite_limit

            return schedule_periods

    def _get_active_profiles_for_window(
        self,
        purpose: ChargingProfilePurposeEnumType,
        evse_id: int,
        transaction_id: Optional[str],
        start_time: datetime,
        end_time: datetime,
    ) -> list[ChargingProfileDataV201]:
        profiles = self.get_profiles_for_purpose(purpose, evse_id)

        if purpose == ChargingProfilePurposeEnumType.tx_profile:
            profiles = [p for p in profiles if p.transaction_id == transaction_id]

        return [
            p for p in profiles if self._is_valid_in_window(p, start_time, end_time)
        ]

    def _get_active_tx_profiles_for_window(
        self,
        evse_id: int,
        transaction_id: Optional[str],
        start_time: datetime,
        end_time: datetime,
    ) -> list[ChargingProfileDataV201]:
        if transaction_id is not None:
            tx_profiles = self._get_active_profiles_for_window(
                ChargingProfilePurposeEnumType.tx_profile,
                evse_id,
                transaction_id,
                start_time,
                end_time,
            )
            if tx_profiles:
                return tx_profiles

        return self._get_active_profiles_for_window(
            ChargingProfilePurposeEnumType.tx_default_profile,
            evse_id,
            transaction_id,
            start_time,
            end_time,
        )

    def _is_valid_in_window(
        self,
        profile: ChargingProfileDataV201,
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        if profile.valid_from is not None and profile.valid_from > end_time:
            return False
        if profile.valid_to is not None and profile.valid_to < start_time:
            return False
        return True

    def _collect_period_boundaries(
        self,
        profiles: list[ChargingProfileDataV201],
        start_time: datetime,
        transaction_start: Optional[datetime],
        duration: int,
    ) -> set[int]:
        boundaries: set[int] = set()

        for profile in profiles:
            for sched in profile.charging_schedules:
                base_time = self._get_profile_base_time(
                    profile, sched, transaction_start
                )

                if base_time is None:
                    continue

                for period in sched.charging_schedule_period:
                    period_time = base_time + timedelta(seconds=period.start_period)
                    offset = int((period_time - start_time).total_seconds())
                    if 0 <= offset < duration:
                        boundaries.add(offset)

        return boundaries

    def _get_profile_base_time(
        self,
        profile: ChargingProfileDataV201,
        sched: ChargingScheduleDataV201,
        transaction_start: Optional[datetime],
    ) -> Optional[datetime]:
        if profile.charging_profile_kind == ChargingProfileKindEnumType.relative:
            return transaction_start
        elif profile.charging_profile_kind == ChargingProfileKindEnumType.absolute:
            return sched.start_schedule if sched.start_schedule else None
        elif profile.charging_profile_kind == ChargingProfileKindEnumType.recurring:
            return sched.start_schedule

        return None

    def _compute_composite_limit_at(
        self,
        cp_max_profiles: list[ChargingProfileDataV201],
        tx_profiles: list[ChargingProfileDataV201],
        sample_time: datetime,
        connector_voltage: float,
        transaction_start: Optional[datetime],
        phases: int,
    ) -> Optional[float]:
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

    @staticmethod
    def from_ocpp_dict(
        cs_profile: dict,
    ) -> ChargingProfileDataV201:
        charging_schedules = []
        for sched_dict in cs_profile["charging_schedule"]:
            periods = []
            for p in sched_dict["charging_schedule_period"]:
                period = ChargingSchedulePeriodDataV201(
                    start_period=p["start_period"],
                    limit=float(p["limit"]),
                    number_phases=p.get("number_phases"),
                    phase_to_use=p.get("phase_to_use"),
                )
                periods.append(period)

            sched = ChargingScheduleDataV201(
                id=sched_dict["id"],
                charging_rate_unit=ChargingRateUnitEnumType(
                    sched_dict["charging_rate_unit"]
                ),
                charging_schedule_period=tuple(periods),
                start_schedule=(
                    datetime.fromisoformat(
                        sched_dict["start_schedule"].replace("Z", "+00:00")
                    )
                    if sched_dict.get("start_schedule")
                    else None
                ),
                duration=sched_dict.get("duration"),
                min_charging_rate=sched_dict.get("min_charging_rate"),
            )
            charging_schedules.append(sched)

        recurrency = None
        if cs_profile.get("recurrency_kind"):
            recurrency = RecurrencyKindEnumType(cs_profile["recurrency_kind"])

        valid_from = None
        if cs_profile.get("valid_from"):
            valid_from = datetime.fromisoformat(
                cs_profile["valid_from"].replace("Z", "+00:00")
            )

        valid_to = None
        if cs_profile.get("valid_to"):
            valid_to = datetime.fromisoformat(
                cs_profile["valid_to"].replace("Z", "+00:00")
            )

        return ChargingProfileDataV201(
            charging_profile_id=cs_profile["id"],
            stack_level=cs_profile["stack_level"],
            charging_profile_purpose=ChargingProfilePurposeEnumType(
                cs_profile["charging_profile_purpose"]
            ),
            charging_profile_kind=ChargingProfileKindEnumType(
                cs_profile["charging_profile_kind"]
            ),
            charging_schedules=tuple(charging_schedules),
            transaction_id=cs_profile.get("transaction_id"),
            recurrency_kind=recurrency,
            valid_from=valid_from,
            valid_to=valid_to,
        )
