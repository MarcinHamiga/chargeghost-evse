"""
Charging Profile Manager Module.

This module implements OCPP 1.6 Smart Charging functionality, managing
charging profiles that control the maximum charging current/power delivered
to electric vehicles. It supports all profile types defined in OCPP 1.6:
ChargePointMaxProfile, TxDefaultProfile, and TxProfile.

The manager handles:
- Profile storage with validation and limits
- Profile resolution with stack level precedence
- Composite schedule calculation
- Support for Absolute, Relative, and Recurring profile kinds

Profile Precedence (highest to lowest):
1. TxProfile (specific to a transaction)
2. TxDefaultProfile (connector-specific defaults)
3. ChargePointMaxProfile (overall station limit)

Data Classes:
    ChargingSchedulePeriodData: A single period within a charging schedule.
    ChargingScheduleData: Complete charging schedule with periods.
    ChargingProfileData: Full profile with schedule and metadata.

Classes:
    ChargingProfileManager: Manages charging profile storage and resolution.

Example:
    >>> from chargeghost_evse.ocpp_adapter.charging_profile_manager import (
    ...     ChargingProfileManager, ChargingProfileData
    ... )
    >>>
    >>> manager = ChargingProfileManager()
    >>> # Set a profile
    >>> error = manager.set_profile(connector_id=1, profile=profile_data)
    >>> if error:
    ...     print(f"Profile rejected: {error}")
    >>>
    >>> # Get current charging limit
    >>> limit = manager.get_composite_limit(
    ...     connector_id=1,
    ...     transaction_id=123,
    ...     now=datetime.now(timezone.utc),
    ...     connector_voltage=230.0,
    ...     phases=1
    ... )
"""

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ocpp.v16.enums import (
    ChargingProfileKindType,
    ChargingProfilePurposeType,
    ChargingRateUnitType,
    RecurrencyKind,
)


@dataclass(frozen=True)
class ChargingSchedulePeriodData:
    """
    A single period within a charging schedule.

    Represents a time slice with a specific charging limit. Multiple
    periods allow the schedule to change limits over time.

    Attributes:
        start_period: Start time in seconds from the schedule start.
            The first period should have start_period=0.
        limit: Maximum charging rate in the unit specified by the
            charging schedule (Amperes or Watts).
        number_phases: Number of phases to use (1 or 3). If None,
            uses the connector's default phase count.
    """

    start_period: int  # seconds from schedule start
    limit: float  # in chargingRateUnit (A or W)
    number_phases: Optional[int] = None


@dataclass(frozen=True)
class ChargingScheduleData:
    """
    Complete charging schedule with time-varying limits.

    A schedule consists of one or more periods that define how the
    charging limit changes over time. The schedule can be absolute
    (referenced to a specific time), relative (to transaction start),
    or recurring (repeating daily or weekly).

    Attributes:
        charging_rate_unit: Unit for limit values (Amps or Watts).
        charging_schedule_period: Tuple of period definitions.
        duration: Total schedule duration in seconds. None means
            the schedule has no expiry.
        start_schedule: Reference start time for Absolute profiles.
        min_charging_rate: Minimum charging rate allowed (optional).
    """

    charging_rate_unit: ChargingRateUnitType
    charging_schedule_period: tuple[ChargingSchedulePeriodData, ...] = ()
    duration: Optional[int] = None  # seconds; None = no expiry
    start_schedule: Optional[datetime] = None
    min_charging_rate: Optional[float] = None


@dataclass(frozen=True)
class ChargingProfileData:
    """
    Complete charging profile with schedule and metadata.

    A charging profile defines when and how much to limit charging.
    Profiles are stacked by purpose and stack level, with higher
    stack levels taking precedence.

    Attributes:
        charging_profile_id: Unique identifier for this profile.
        stack_level: Priority level (higher = more priority).
        charging_profile_purpose: Type of profile (ChargePointMax,
            TxDefault, or TxProfile).
        charging_profile_kind: Timing type (Absolute, Relative, Recurring).
        charging_schedule: The schedule containing period limits.
        transaction_id: Required for TxProfile, links to a transaction.
        recurrency_kind: For Recurring profiles (Daily or Weekly).
        valid_from: Start of profile validity period.
        valid_to: End of profile validity period.
    """

    charging_profile_id: int
    stack_level: int
    charging_profile_purpose: ChargingProfilePurposeType
    charging_profile_kind: ChargingProfileKindType
    charging_schedule: ChargingScheduleData
    transaction_id: Optional[int] = None
    recurrency_kind: Optional[RecurrencyKind] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None

    def to_ocpp_dict(self) -> dict:
        """Serialize this profile to an OCPP CsChargingProfile dict."""
        schedule_dict: dict[str, object] = {
            "charging_rate_unit": self.charging_schedule.charging_rate_unit.value,
            "charging_schedule_period": [
                {
                    "start_period": p.start_period,
                    "limit": p.limit,
                    **({"number_phases": p.number_phases} if p.number_phases is not None else {}),
                }
                for p in self.charging_schedule.charging_schedule_period
            ],
        }
        if self.charging_schedule.duration is not None:
            schedule_dict["duration"] = self.charging_schedule.duration
        if self.charging_schedule.start_schedule is not None:
            schedule_dict["start_schedule"] = self.charging_schedule.start_schedule.isoformat()
        if self.charging_schedule.min_charging_rate is not None:
            schedule_dict["min_charging_rate"] = self.charging_schedule.min_charging_rate

        result: dict[str, object] = {
            "charging_profile_id": self.charging_profile_id,
            "stack_level": self.stack_level,
            "charging_profile_purpose": self.charging_profile_purpose.value,
            "charging_profile_kind": self.charging_profile_kind.value,
            "charging_schedule": schedule_dict,
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


class ChargingProfileManager:
    """
    Manages OCPP 1.6 charging profiles for smart charging.

    Provides storage, validation, and resolution of charging profiles.
    Supports the OCPP 1.6 Smart Charging feature set including:
    - Multiple profile purposes (ChargePointMax, TxDefault, TxProfile)
    - Stack level precedence
    - Absolute, Relative, and Recurring profile kinds
    - Daily and weekly recurrency

    The manager is thread-safe for use from multiple threads (OCPP
    handler and simulation loop).

    Attributes:
        max_profiles: Maximum number of profiles allowed.
        max_stack_level: Maximum stack level value.
        max_schedule_periods: Maximum periods per schedule.

    Example:
        >>> manager = ChargingProfileManager(max_profiles=20)
        >>>
        >>> # Add a profile
        >>> error = manager.set_profile(connector_id=1, profile=profile)
        >>>
        >>> # Get effective limit
        >>> limit = manager.get_composite_limit(
        ...     connector_id=1, transaction_id=123,
        ...     now=datetime.now(timezone.utc),
        ...     connector_voltage=230.0
        ... )
        >>>
        >>> # Clear profiles
        >>> removed = manager.clear_profiles(connector_id=1)
    """

    def __init__(
        self,
        max_profiles: int = 20,
        max_stack_level: int = 5,
        max_schedule_periods: int = 10,
        persist_path: Optional[Path] = None,
    ) -> None:
        """
        Initialize the charging profile manager.

        Args:
            max_profiles: Maximum number of profiles to store.
            max_stack_level: Maximum allowed stack level value.
            max_schedule_periods: Maximum periods per schedule.
            persist_path: Path for charging profile persistence. Defaults to
                None (in-memory only). Pass a Path to enable persistence
                at that location; the manager will restore existing profiles
                on initialization.
        """
        self._lock = threading.RLock()
        self.max_profiles = max_profiles
        self.max_stack_level = max_stack_level
        self.max_schedule_periods = max_schedule_periods

        # Profile storage: profile_id -> (connector_id, ChargingProfileData)
        self._profiles: dict[int, tuple[int, ChargingProfileData]] = {}
        self.logger = logging.getLogger("chargeghost.ocpp.profiles")

        self._persist_path = persist_path
        if persist_path is not None and not self._profiles:
            self._restore()

    def _persist(self) -> None:
        """Persist installed profiles to disk for restart survival."""
        if self._persist_path is None:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = []
            with self._lock:
                for profile_id, (connector_id, profile) in self._profiles.items():
                    data.append({
                        "connector_id": connector_id,
                        "profile": profile.to_ocpp_dict(),
                    })
            with open(self._persist_path, "w") as f:
                json.dump(data, f)
        except Exception as e:
            self.logger.warning(
                f"Failed to persist charging profiles: {e}",
                extra={"source": "ocpp"},
            )

    def _restore(self) -> None:
        """Restore installed profiles from disk on startup."""
        if self._profiles:
            return
        if not self._persist_path.exists():
            return

        try:
            with open(self._persist_path, "r") as f:
                data = json.load(f)
        except Exception as e:
            self.logger.warning(
                f"Failed to restore charging profiles (corrupted file): {e}",
                extra={"source": "ocpp"},
            )
            return

        restored = 0
        for entry in data:
            try:
                profile = ChargingProfileManager.from_ocpp_dict(entry["profile"])
                connector_id = entry["connector_id"]
                self._profiles[profile.charging_profile_id] = (connector_id, profile)
                restored += 1
            except Exception:
                continue

        if restored:
            self.logger.info(
                f"Restored {restored} charging profile(s) from disk",
                extra={"source": "ocpp"},
            )

    def set_profile(
        self, connector_id: int, profile: ChargingProfileData
    ) -> Optional[str]:
        """
        Store a charging profile.

        Validates the profile against constraints and stores it if valid.
        Replacing an existing profile with the same ID doesn't count
        against the maximum profile limit.

        Args:
            connector_id: Connector to apply the profile to (0 = all connectors).
            profile: The charging profile to store.

        Returns:
            Error code string if rejected, None if accepted.
            Possible errors: "too_many_periods", "stack_level_exceeded",
            "tx_profile_missing_transaction_id", "max_profiles_exceeded".
        """
        with self._lock:
            # Validate schedule periods
            num_periods = len(profile.charging_schedule.charging_schedule_period)
            if num_periods > self.max_schedule_periods:
                return "too_many_periods"

            # Validate stack level
            if profile.stack_level > self.max_stack_level:
                return "stack_level_exceeded"

            # TxProfile requires transaction_id
            if (
                profile.charging_profile_purpose
                == ChargingProfilePurposeType.tx_profile
                and profile.transaction_id is None
            ):
                return "tx_profile_missing_transaction_id"

            replaced_profile_ids = []
            if profile.charging_profile_purpose == ChargingProfilePurposeType.tx_profile:
                for existing_id, (
                    existing_connector_id,
                    existing_profile,
                ) in self._profiles.items():
                    if existing_id == profile.charging_profile_id:
                        continue
                    if existing_connector_id != connector_id:
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

            # Check profile count limit (replacements don't count)
            is_replace = (
                profile.charging_profile_id in self._profiles
                or bool(replaced_profile_ids)
            )
            if not is_replace and len(self._profiles) >= self.max_profiles:
                return "max_profiles_exceeded"

            for existing_id in replaced_profile_ids:
                del self._profiles[existing_id]

            self._profiles[profile.charging_profile_id] = (connector_id, profile)
            periods = profile.charging_schedule.charging_schedule_period
            if periods:
                self.logger.info(
                    f"Profile installed: {profile.charging_profile_purpose.value} "
                    f"#{profile.charging_profile_id} "
                    f"(stack_level={profile.stack_level}, "
                    f"{profile.charging_profile_kind.value}, "
                    f"{periods[0].limit}A limit)",
                    extra={"source": "ocpp", "connector_id": connector_id},
                )
            else:
                self.logger.info(
                    f"Profile installed: {profile.charging_profile_purpose.value} "
                    f"#{profile.charging_profile_id}",
                    extra={"source": "ocpp", "connector_id": connector_id},
                )
            self._persist()
            return None

    def get_profile_ids(self) -> list[int]:
        """Return sorted list of all installed charging profile IDs."""
        with self._lock:
            return sorted(self._profiles.keys())

    def clear_profiles(
        self,
        profile_id: Optional[int] = None,
        connector_id: Optional[int] = None,
        purpose: Optional[ChargingProfilePurposeType] = None,
        stack_level: Optional[int] = None,
    ) -> int:
        """
        Remove profiles matching the given criteria.

        All parameters are optional; only profiles matching all provided
        criteria are removed. If no parameters are provided, all profiles
        are removed.

        Args:
            profile_id: Specific profile ID to remove.
            connector_id: Remove profiles for this connector only.
            purpose: Remove profiles with this purpose only.
            stack_level: Remove profiles with this stack level only.

        Returns:
            Number of profiles removed.
        """
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

            if to_remove:
                self.logger.info(
                    f"Profile(s) cleared: {to_remove}",
                    extra={"source": "ocpp"},
                )
                self._persist()
            return len(to_remove)

    def get_profiles_for_purpose(
        self,
        purpose: ChargingProfilePurposeType,
        connector_id: int,
    ) -> list[ChargingProfileData]:
        """
        Get all profiles matching a purpose and connector.

        Returns profiles sorted by stack level (highest first).
        Profiles with connector_id=0 (apply to all) are included.

        Args:
            purpose: The profile purpose to filter by.
            connector_id: The connector ID (profiles with connector_id=0
                are always included).

        Returns:
            List of matching profiles, sorted by stack level descending.
        """
        with self._lock:
            result = []
            for cid, profile in self._profiles.values():
                if profile.charging_profile_purpose != purpose:
                    continue
                # connectorId=0 applies to all connectors
                if cid != 0 and cid != connector_id:
                    continue
                result.append(profile)

            # Sort by stack level (highest first for precedence)
            result.sort(key=lambda p: p.stack_level, reverse=True)
            return result

    def get_all_profiles(self) -> list[tuple[int, ChargingProfileData]]:
        """
        Get all stored profiles.

        Returns:
            List of (connector_id, profile) tuples.
        """
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
        """
        Calculate the effective charging current limit.

        Combines limits from ChargePointMaxProfile and TxProfile/TxDefaultProfile,
        returning the most restrictive (lowest) limit.

        Args:
            connector_id: The connector to get the limit for.
            transaction_id: Current transaction ID (for TxProfile matching).
            now: Current time for profile validity and period selection.
            connector_voltage: Connector voltage for Watts->Amps conversion.
            transaction_start: Transaction start time for Relative profiles.
            phases: Number of phases for Watts->Amps conversion.

        Returns:
            Effective current limit in Amperes, or None if no active profiles.
        """
        # Get ChargePointMaxProfile limit
        cp_max_limit = self._resolve_purpose_limit(
            ChargingProfilePurposeType.charge_point_max_profile,
            connector_id,
            transaction_id,
            now,
            connector_voltage,
            transaction_start,
            phases,
        )

        # Get TxProfile or TxDefaultProfile limit
        tx_limit = self._resolve_tx_limit(
            connector_id,
            transaction_id,
            now,
            connector_voltage,
            transaction_start,
            phases,
        )

        # Return the most restrictive limit
        active_limits = [lim for lim in [cp_max_limit, tx_limit] if lim is not None]
        if not active_limits:
            self.logger.debug(
                f"No active profile for connector {connector_id}",
                extra={
                    "source": "ocpp",
                    "connector_id": connector_id,
                    "evaluated_profiles": [],
                    "computed_limit_amps": None,
                },
            )
            return None

        evaluated = []
        if cp_max_limit is not None:
            evaluated.append("ChargePointMaxProfile")
        if tx_limit is not None:
            evaluated.append("TxProfile/TxDefaultProfile")
        result = min(active_limits)
        self.logger.debug(
            f"Profile evaluation for connector {connector_id}: limit={result}A",
            extra={
                "source": "ocpp",
                "connector_id": connector_id,
                "evaluated_profiles": evaluated,
                "computed_limit_amps": result,
            },
        )
        return result

    def _resolve_tx_limit(
        self,
        connector_id: int,
        transaction_id: Optional[int],
        now: datetime,
        connector_voltage: float,
        transaction_start: Optional[datetime],
        phases: int,
    ) -> Optional[float]:
        """
        Resolve limit from TxProfile (if present) or TxDefaultProfile.

        TxProfile takes precedence over TxDefaultProfile when a
        matching transaction ID is found.

        Args:
            connector_id: The connector to get the limit for.
            transaction_id: Current transaction ID.
            now: Current time.
            connector_voltage: Connector voltage.
            transaction_start: Transaction start time.
            phases: Number of phases.

        Returns:
            Current limit in Amperes, or None.
        """
        # Try TxProfile first (transaction-specific)
        if transaction_id is not None:
            tx_limit = self._resolve_purpose_limit(
                ChargingProfilePurposeType.tx_profile,
                connector_id,
                transaction_id,
                now,
                connector_voltage,
                transaction_start,
                phases,
            )
            if tx_limit is not None:
                return tx_limit

        # Fall back to TxDefaultProfile
        return self._resolve_purpose_limit(
            ChargingProfilePurposeType.tx_default_profile,
            connector_id,
            transaction_id,
            now,
            connector_voltage,
            transaction_start,
            phases,
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
        """
        Resolve limit from profiles of a specific purpose.

        Gets the highest-stack-level valid profile and extracts
        the current limit from its schedule.

        Args:
            purpose: The profile purpose to resolve.
            connector_id: The connector ID.
            transaction_id: Current transaction ID (for TxProfile filtering).
            now: Current time.
            connector_voltage: Connector voltage.
            transaction_start: Transaction start time.
            phases: Number of phases.

        Returns:
            Current limit in Amperes, or None.
        """
        profiles = self.get_profiles_for_purpose(purpose, connector_id)

        # Filter TxProfile by transaction_id
        if purpose == ChargingProfilePurposeType.tx_profile:
            profiles = [p for p in profiles if p.transaction_id == transaction_id]

        # Filter by validity period
        profiles = [p for p in profiles if self._is_valid_at(p, now)]

        if not profiles:
            return None

        # Use highest stack level profile
        profile = profiles[0]
        return self._get_limit_from_profile(
            profile, now, connector_voltage, transaction_start, phases
        )

    def _is_valid_at(self, profile: ChargingProfileData, now: datetime) -> bool:
        """
        Check if a profile is valid at the given time.

        Args:
            profile: The profile to check.
            now: The time to check validity for.

        Returns:
            True if the profile is valid at the given time.
        """
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
        """
        Extract the current limit from a profile at a specific time.

        Handles all profile kinds (Absolute, Relative, Recurring) and
        converts Watts to Amperes if necessary.

        Args:
            profile: The profile to extract limit from.
            now: Current time.
            connector_voltage: Connector voltage for conversion.
            transaction_start: Transaction start time for Relative profiles.
            phases: Number of phases for conversion.

        Returns:
            Current limit in Amperes, or None if not applicable.
        """
        schedule = profile.charging_schedule

        # Calculate elapsed time based on profile kind
        if profile.charging_profile_kind == ChargingProfileKindType.relative:
            # Relative: elapsed from transaction start
            if transaction_start is None:
                return None
            elapsed = (now - transaction_start).total_seconds()

        elif profile.charging_profile_kind == ChargingProfileKindType.absolute:
            # Absolute: elapsed from start_schedule
            if schedule.start_schedule is None:
                elapsed = 0.0
            else:
                elapsed = (now - schedule.start_schedule).total_seconds()
            if elapsed < 0:
                return None  # Not yet active

        elif profile.charging_profile_kind == ChargingProfileKindType.recurring:
            # Recurring: elapsed within the current cycle
            if schedule.start_schedule is None:
                return None
            total_elapsed = (now - schedule.start_schedule).total_seconds()
            if total_elapsed < 0:
                return None
            # Daily = 86400s, Weekly = 604800s
            cycle = (
                86400.0 if profile.recurrency_kind == RecurrencyKind.daily else 604800.0
            )
            elapsed = total_elapsed % cycle

        else:
            return None

        # Check if elapsed time exceeds schedule duration
        if schedule.duration is not None and elapsed > schedule.duration:
            return None

        # Find the active period limit
        limit = self._find_period_limit(schedule.charging_schedule_period, elapsed)
        if limit is None:
            return None

        # Convert Watts to Amperes if necessary
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
        """
        Find the applicable limit for a given elapsed time.

        Iterates through periods to find the most recent one that
        started before the elapsed time.

        Args:
            periods: Tuple of ChargingSchedulePeriodData.
            elapsed: Seconds since schedule start.

        Returns:
            The applicable limit, or None if no periods.
        """
        if not periods:
            return None

        # Sort periods by start time
        sorted_periods = sorted(periods, key=lambda p: p.start_period)

        # Find the active period
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

        Combines ChargePointMaxProfile with TxDefaultProfile/TxProfile to
        create a unified schedule showing the effective limit at each
        time boundary.

        Args:
            connector_id: The connector to build schedule for.
            transaction_id: Current transaction ID.
            start_time: Start of the schedule window.
            duration: Duration of the schedule window in seconds.
            connector_voltage: Connector voltage for conversion.
            transaction_start: Transaction start time for Relative profiles.
            phases: Number of phases.

        Returns:
            List of ChargingSchedulePeriodData representing the composite
            schedule, with limits in Amperes.
        """
        with self._lock:
            # Collect all time boundaries where limits change
            boundaries: set[int] = {0}
            end_time = start_time + timedelta(seconds=duration)

            # Get active profiles for the time window
            cp_max_profiles = self._get_active_profiles_for_window(
                ChargingProfilePurposeType.charge_point_max_profile,
                connector_id,
                transaction_id,
                start_time,
                end_time,
            )
            tx_profiles = self._get_active_tx_profiles_for_window(
                connector_id,
                transaction_id,
                start_time,
                end_time,
            )

            # Collect period boundaries from all profiles
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

            # Filter boundaries to the schedule window
            sorted_boundaries = sorted(b for b in boundaries if 0 <= b < duration)
            if not sorted_boundaries:
                sorted_boundaries = [0]

            # Build schedule periods
            schedule_periods: list[ChargingSchedulePeriodData] = []
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

                # Only add period if limit changed
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
        """
        Get profiles that are active during a time window.

        Args:
            purpose: Profile purpose to filter by.
            connector_id: Connector ID.
            transaction_id: Transaction ID for TxProfile.
            start_time: Window start time.
            end_time: Window end time.

        Returns:
            List of profiles active during the window.
        """
        profiles = self.get_profiles_for_purpose(purpose, connector_id)

        if purpose == ChargingProfilePurposeType.tx_profile:
            profiles = [p for p in profiles if p.transaction_id == transaction_id]

        return [
            p for p in profiles if self._is_valid_in_window(p, start_time, end_time)
        ]

    def _get_active_tx_profiles_for_window(
        self,
        connector_id: int,
        transaction_id: Optional[int],
        start_time: datetime,
        end_time: datetime,
    ) -> list[ChargingProfileData]:
        """
        Get active TxProfile or TxDefaultProfile for a window.

        Returns TxProfile if available, otherwise TxDefaultProfile.

        Args:
            connector_id: Connector ID.
            transaction_id: Transaction ID.
            start_time: Window start time.
            end_time: Window end time.

        Returns:
            List of active profiles.
        """
        if transaction_id is not None:
            tx_profiles = self._get_active_profiles_for_window(
                ChargingProfilePurposeType.tx_profile,
                connector_id,
                transaction_id,
                start_time,
                end_time,
            )
            if tx_profiles:
                return tx_profiles

        return self._get_active_profiles_for_window(
            ChargingProfilePurposeType.tx_default_profile,
            connector_id,
            transaction_id,
            start_time,
            end_time,
        )

    def _is_valid_in_window(
        self,
        profile: ChargingProfileData,
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        """
        Check if a profile is active at any point in a time window.

        Args:
            profile: The profile to check.
            start_time: Window start time.
            end_time: Window end time.

        Returns:
            True if the profile is active during the window.
        """
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
        """
        Collect all period start times from profiles.

        Converts period start times to offsets from the schedule start.

        Args:
            profiles: Profiles to collect boundaries from.
            start_time: Schedule start time.
            transaction_start: Transaction start for Relative profiles.
            duration: Schedule duration.

        Returns:
            Set of boundary offsets in seconds.
        """
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
        """
        Get the base time for calculating period offsets.

        Args:
            profile: The profile to get base time for.
            transaction_start: Transaction start time.

        Returns:
            Base time for the profile kind, or None.
        """
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
        """
        Compute composite limit at a specific time.

        Combines limits from pre-filtered profile lists.

        Args:
            cp_max_profiles: ChargePointMaxProfile list.
            tx_profiles: TxProfile/TxDefaultProfile list.
            sample_time: Time to compute limit for.
            connector_voltage: Connector voltage.
            transaction_start: Transaction start time.
            phases: Number of phases.

        Returns:
            Composite limit in Amperes, or None.
        """
        # Get ChargePointMaxProfile limit
        cp_max_limit: Optional[float] = None
        if cp_max_profiles:
            profile = cp_max_profiles[0]
            cp_max_limit = self._get_limit_from_profile(
                profile, sample_time, connector_voltage, transaction_start, phases
            )

        # Get TxProfile/TxDefaultProfile limit
        tx_limit: Optional[float] = None
        if tx_profiles:
            profile = tx_profiles[0]
            tx_limit = self._get_limit_from_profile(
                profile, sample_time, connector_voltage, transaction_start, phases
            )

        # Return the most restrictive limit
        active_limits = [lim for lim in [cp_max_limit, tx_limit] if lim is not None]
        if not active_limits:
            return None
        return min(active_limits)

    @staticmethod
    def from_ocpp_dict(cs_profile: dict) -> "ChargingProfileData":
        """
        Parse an OCPP CsChargingProfile dict to ChargingProfileData.

        Args:
            cs_profile: OCPP CsChargingProfile dictionary from SetChargingProfile.

        Returns:
            ChargingProfileData instance.

        Raises:
            KeyError: If required fields are missing.
            ValueError: If enum values are invalid.
        """
        cs_schedule = cs_profile["charging_schedule"]

        # Parse schedule periods
        periods = []
        for p in cs_schedule["charging_schedule_period"]:
            period = ChargingSchedulePeriodData(
                start_period=p["start_period"],
                limit=float(p["limit"]),
                number_phases=p.get("number_phases"),
            )
            periods.append(period)

        # Parse schedule
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType(cs_schedule["charging_rate_unit"]),
            charging_schedule_period=tuple(periods),
            duration=cs_schedule.get("duration"),
            start_schedule=(
                datetime.fromisoformat(
                    cs_schedule["start_schedule"].replace("Z", "+00:00")
                )
                if cs_schedule.get("start_schedule")
                else None
            ),
            min_charging_rate=cs_schedule.get("min_charging_rate"),
        )

        # Parse recurrency kind
        recurrency = None
        if cs_profile.get("recurrency_kind"):
            recurrency = RecurrencyKind(cs_profile["recurrency_kind"])

        # Parse validity period
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

        return ChargingProfileData(
            charging_profile_id=cs_profile["charging_profile_id"],
            stack_level=cs_profile["stack_level"],
            charging_profile_purpose=ChargingProfilePurposeType(
                cs_profile["charging_profile_purpose"]
            ),
            charging_profile_kind=ChargingProfileKindType(
                cs_profile["charging_profile_kind"]
            ),
            charging_schedule=schedule,
            transaction_id=cs_profile.get("transaction_id"),
            recurrency_kind=recurrency,
            valid_from=valid_from,
            valid_to=valid_to,
        )
