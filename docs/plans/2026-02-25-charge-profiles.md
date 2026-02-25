# Charge Profiles Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement full OCPP 1.6J Smart Charging (SetChargingProfile / ClearChargingProfile / GetCompositeSchedule) with actual enforcement of power limits during simulation.

**Architecture:** A thread-safe `ChargingProfileManager` lives in the `ocpp_adapter` layer. The `Adapter` owns it and handles all three OCPP messages. The `Bridge` injects a `get_limit` lambda into the `Engine`. The `Engine.simulate()` clamps connector current via that lambda before each `EnergyMeter.update()`.

**Tech Stack:** Python 3.11+, PySide6, `ocpp` library (v16 enums/datatypes), `threading.RLock`, `pytest`

---

## Context You Must Know

- Run all tests with: `poetry run pytest tests/ -v`
- Run a single test file: `poetry run pytest tests/test_charging_profile_manager.py -v`
- All source lives under `src/chargeghost_evse/`
- OCPP enums to import: `from ocpp.v16.enums import ChargingProfilePurposeType, ChargingProfileKindType, RecurrencyKind, ChargingRateUnitType, ChargingProfileStatus, ClearChargingProfileStatus, GetCompositeScheduleStatus`
- OCPP datatypes: `from ocpp.v16.datatypes import ChargingProfile as OcppChargingProfile, ChargingSchedule, ChargingSchedulePeriod`
- `ChargingProfilePurposeType.charge_point_max_profile`, `.tx_default_profile`, `.tx_profile`
- `ChargingProfileKindType.absolute`, `.recurring`, `.relative`
- `RecurrencyKind.daily` (86400s), `.weekly` (604800s)
- `ChargingRateUnitType.amps` = `'A'`, `.watts` = `'W'`
- Existing config keys (read-only, already in `ConfigurationKeyManager`):
  - `MaxChargingProfilesInstalled` = 20
  - `ChargeProfileMaxStackLevel` = 5
  - `ChargingScheduleMaxPeriods` = 10
  - `ChargingScheduleAllowedChargingRateUnit` = `"Current,Power"` (maps to A and W)
- The adapter's `active_transactions` dict maps `connector_id -> transaction_id`
- `datetime` objects in the ocpp library arrive as ISO 8601 strings — parse with `datetime.fromisoformat()`
- OCPP 1.6J spec: `connectorId=0` in `SetChargingProfile` means "applies to all connectors"

---

## Task 1: ChargingProfile Internal Dataclass

**Files:**
- Create: `src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py`
- Create: `tests/test_charging_profile_manager.py`

### Step 1: Write failing tests for the dataclass

```python
# tests/test_charging_profile_manager.py
import pytest
from datetime import datetime, timezone
from ocpp.v16.enums import (
    ChargingProfilePurposeType,
    ChargingProfileKindType,
    RecurrencyKind,
    ChargingRateUnitType,
)
from chargeghost_evse.ocpp_adapter.charging_profile_manager import (
    ChargingProfileData,
    ChargingSchedulePeriodData,
    ChargingScheduleData,
)


class TestChargingProfileDataclass:
    def test_period_creation(self):
        period = ChargingSchedulePeriodData(start_period=0, limit=16.0, number_phases=1)
        assert period.start_period == 0
        assert period.limit == 16.0
        assert period.number_phases == 1

    def test_period_default_phases(self):
        period = ChargingSchedulePeriodData(start_period=0, limit=16.0)
        assert period.number_phases is None

    def test_schedule_creation(self):
        period = ChargingSchedulePeriodData(start_period=0, limit=16.0)
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=[period],
        )
        assert schedule.charging_rate_unit == ChargingRateUnitType.amps
        assert len(schedule.charging_schedule_period) == 1
        assert schedule.duration is None
        assert schedule.start_schedule is None

    def test_profile_creation(self):
        period = ChargingSchedulePeriodData(start_period=0, limit=16.0)
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=[period],
        )
        profile = ChargingProfileData(
            charging_profile_id=1,
            stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_profile,
            charging_profile_kind=ChargingProfileKindType.relative,
            charging_schedule=schedule,
            transaction_id=42,
        )
        assert profile.charging_profile_id == 1
        assert profile.stack_level == 0
        assert profile.transaction_id == 42
        assert profile.valid_from is None
        assert profile.valid_to is None
        assert profile.recurrency_kind is None
```

### Step 2: Run test to verify it fails

```bash
poetry run pytest tests/test_charging_profile_manager.py -v
```
Expected: `ImportError` — module does not exist yet.

### Step 3: Create the module with just the dataclasses

```python
# src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py
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
```

### Step 4: Run tests to verify they pass

```bash
poetry run pytest tests/test_charging_profile_manager.py::TestChargingProfileDataclass -v
```
Expected: All 5 tests PASS.

### Step 5: Commit

```bash
git add src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py tests/test_charging_profile_manager.py
git commit -m "feat: add ChargingProfile internal dataclasses"
```

---

## Task 2: Profile Storage — set, clear, and constraint validation

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py`
- Modify: `tests/test_charging_profile_manager.py`

### Step 1: Write failing tests for storage and constraints

Add this class to `tests/test_charging_profile_manager.py`:

```python
from chargeghost_evse.ocpp_adapter.charging_profile_manager import (
    ChargingProfileData,
    ChargingSchedulePeriodData,
    ChargingScheduleData,
    ChargingProfileManager,
)


def _make_profile(
    profile_id: int = 1,
    stack_level: int = 0,
    purpose: ChargingProfilePurposeType = ChargingProfilePurposeType.tx_default_profile,
    kind: ChargingProfileKindType = ChargingProfileKindType.relative,
    limit: float = 16.0,
    transaction_id: Optional[int] = None,
    unit: ChargingRateUnitType = ChargingRateUnitType.amps,
    num_periods: int = 1,
) -> ChargingProfileData:
    periods = [ChargingSchedulePeriodData(start_period=i * 100, limit=limit) for i in range(num_periods)]
    schedule = ChargingScheduleData(
        charging_rate_unit=unit,
        charging_schedule_period=periods,
    )
    return ChargingProfileData(
        charging_profile_id=profile_id,
        stack_level=stack_level,
        charging_profile_purpose=purpose,
        charging_profile_kind=kind,
        charging_schedule=schedule,
        transaction_id=transaction_id,
    )


class TestChargingProfileManagerStorage:
    def test_set_and_retrieve_profile(self):
        mgr = ChargingProfileManager()
        profile = _make_profile(profile_id=1)
        error = mgr.set_profile(connector_id=1, profile=profile)
        assert error is None
        profiles = mgr.get_profiles_for_purpose(
            ChargingProfilePurposeType.tx_default_profile, connector_id=1
        )
        assert len(profiles) == 1
        assert profiles[0].charging_profile_id == 1

    def test_replace_same_id(self):
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=1, limit=16.0))
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=1, limit=32.0))
        profiles = mgr.get_profiles_for_purpose(
            ChargingProfilePurposeType.tx_default_profile, connector_id=1
        )
        assert len(profiles) == 1
        assert profiles[0].charging_schedule.charging_schedule_period[0].limit == 32.0

    def test_clear_by_id(self):
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=1))
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=2))
        cleared = mgr.clear_profiles(profile_id=1)
        assert cleared == 1
        profiles = mgr.get_profiles_for_purpose(
            ChargingProfilePurposeType.tx_default_profile, connector_id=1
        )
        assert len(profiles) == 1

    def test_clear_by_purpose(self):
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=1, purpose=ChargingProfilePurposeType.tx_default_profile))
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=2, purpose=ChargingProfilePurposeType.tx_profile, transaction_id=99))
        cleared = mgr.clear_profiles(purpose=ChargingProfilePurposeType.tx_default_profile)
        assert cleared == 1

    def test_clear_nothing_returns_zero(self):
        mgr = ChargingProfileManager()
        cleared = mgr.clear_profiles(profile_id=999)
        assert cleared == 0

    def test_reject_exceeds_max_profiles(self):
        mgr = ChargingProfileManager(max_profiles=2)
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=1))
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=2))
        error = mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=3))
        assert error == "max_profiles_exceeded"

    def test_reject_stack_level_too_high(self):
        mgr = ChargingProfileManager(max_stack_level=3)
        error = mgr.set_profile(connector_id=1, profile=_make_profile(stack_level=4))
        assert error == "stack_level_exceeded"

    def test_reject_too_many_periods(self):
        mgr = ChargingProfileManager(max_schedule_periods=3)
        error = mgr.set_profile(connector_id=1, profile=_make_profile(num_periods=4))
        assert error == "too_many_periods"

    def test_reject_tx_profile_without_transaction_id(self):
        mgr = ChargingProfileManager()
        profile = _make_profile(
            purpose=ChargingProfilePurposeType.tx_profile,
            transaction_id=None,
        )
        error = mgr.set_profile(connector_id=1, profile=profile)
        assert error == "tx_profile_missing_transaction_id"

    def test_connector_zero_applies_to_all(self):
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=0, profile=_make_profile(profile_id=1, purpose=ChargingProfilePurposeType.charge_point_max_profile))
        for conn_id in [1, 2, 3]:
            profiles = mgr.get_profiles_for_purpose(
                ChargingProfilePurposeType.charge_point_max_profile, connector_id=conn_id
            )
            assert len(profiles) == 1

    def test_highest_stack_level_returned_first(self):
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=1, stack_level=0, limit=10.0))
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=2, stack_level=2, limit=20.0))
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=3, stack_level=1, limit=15.0))
        profiles = mgr.get_profiles_for_purpose(
            ChargingProfilePurposeType.tx_default_profile, connector_id=1
        )
        assert profiles[0].stack_level == 2
        assert profiles[1].stack_level == 1
        assert profiles[2].stack_level == 0
```

### Step 2: Run tests to verify they fail

```bash
poetry run pytest tests/test_charging_profile_manager.py::TestChargingProfileManagerStorage -v
```
Expected: `ImportError: cannot import name 'ChargingProfileManager'`

### Step 3: Add ChargingProfileManager class to the module

Append to `src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py`:

```python
import threading


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
```

### Step 4: Run tests to verify they pass

```bash
poetry run pytest tests/test_charging_profile_manager.py::TestChargingProfileManagerStorage -v
```
Expected: All 11 tests PASS.

### Step 5: Commit

```bash
git add src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py tests/test_charging_profile_manager.py
git commit -m "feat: add ChargingProfileManager storage with constraint validation"
```

---

## Task 3: Composite Limit — Relative and Absolute Schedules

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py`
- Modify: `tests/test_charging_profile_manager.py`

### Step 1: Write failing tests

Add to `tests/test_charging_profile_manager.py`:

```python
class TestCompositeLimit:
    """Tests for get_composite_limit() — the core scheduling algorithm."""

    def _mgr_with_profile(self, profile: ChargingProfileData, connector_id: int = 1) -> ChargingProfileManager:
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=connector_id, profile=profile)
        return mgr

    def test_no_profiles_returns_none(self):
        mgr = ChargingProfileManager()
        result = mgr.get_composite_limit(
            connector_id=1,
            transaction_id=None,
            now=datetime.now(timezone.utc),
            connector_voltage=230.0,
        )
        assert result is None

    def test_relative_profile_single_period(self):
        """A relative TxProfile with one period at 16A should always return 16A."""
        period = ChargingSchedulePeriodData(start_period=0, limit=16.0)
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=[period],
        )
        profile = ChargingProfileData(
            charging_profile_id=1,
            stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_profile,
            charging_profile_kind=ChargingProfileKindType.relative,
            charging_schedule=schedule,
            transaction_id=42,
        )
        mgr = self._mgr_with_profile(profile)
        now = datetime.now(timezone.utc)
        result = mgr.get_composite_limit(
            connector_id=1,
            transaction_id=42,
            now=now,
            connector_voltage=230.0,
            transaction_start=now,
        )
        assert result == pytest.approx(16.0)

    def test_relative_profile_steps_through_periods(self):
        """A relative profile with two periods: 0-3600s → 16A, 3600s+ → 8A."""
        from datetime import timedelta
        periods = [
            ChargingSchedulePeriodData(start_period=0, limit=16.0),
            ChargingSchedulePeriodData(start_period=3600, limit=8.0),
        ]
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=periods,
        )
        profile = ChargingProfileData(
            charging_profile_id=1,
            stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_profile,
            charging_profile_kind=ChargingProfileKindType.relative,
            charging_schedule=schedule,
            transaction_id=42,
        )
        mgr = self._mgr_with_profile(profile)
        tx_start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # At t=0: should be 16A
        result_at_start = mgr.get_composite_limit(
            connector_id=1, transaction_id=42, now=tx_start,
            connector_voltage=230.0, transaction_start=tx_start,
        )
        assert result_at_start == pytest.approx(16.0)

        # At t=1800s (30 min): still 16A
        result_mid = mgr.get_composite_limit(
            connector_id=1, transaction_id=42,
            now=tx_start + timedelta(seconds=1800),
            connector_voltage=230.0, transaction_start=tx_start,
        )
        assert result_mid == pytest.approx(16.0)

        # At t=3601s: should be 8A
        result_after = mgr.get_composite_limit(
            connector_id=1, transaction_id=42,
            now=tx_start + timedelta(seconds=3601),
            connector_voltage=230.0, transaction_start=tx_start,
        )
        assert result_after == pytest.approx(8.0)

    def test_relative_profile_expired_after_duration(self):
        """A profile with duration=3600 should expire after 3600s."""
        from datetime import timedelta
        period = ChargingSchedulePeriodData(start_period=0, limit=16.0)
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=[period],
            duration=3600,
        )
        profile = ChargingProfileData(
            charging_profile_id=1, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_profile,
            charging_profile_kind=ChargingProfileKindType.relative,
            charging_schedule=schedule, transaction_id=42,
        )
        mgr = self._mgr_with_profile(profile)
        tx_start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=42,
            now=tx_start + timedelta(seconds=3601),
            connector_voltage=230.0, transaction_start=tx_start,
        )
        assert result is None

    def test_absolute_profile(self):
        """An absolute TxDefaultProfile uses startSchedule as t=0."""
        from datetime import timedelta
        start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        periods = [
            ChargingSchedulePeriodData(start_period=0, limit=20.0),
            ChargingSchedulePeriodData(start_period=1800, limit=10.0),
        ]
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=periods,
            start_schedule=start,
        )
        profile = ChargingProfileData(
            charging_profile_id=1, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
            charging_profile_kind=ChargingProfileKindType.absolute,
            charging_schedule=schedule,
        )
        mgr = self._mgr_with_profile(profile)
        # At exactly startSchedule: 20A
        assert mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start, connector_voltage=230.0,
        ) == pytest.approx(20.0)
        # At start + 2000s (> 1800s): 10A
        assert mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start + timedelta(seconds=2000), connector_voltage=230.0,
        ) == pytest.approx(10.0)

    def test_watts_converted_to_amps(self):
        """A profile in W should be converted: limit_A = limit_W / voltage."""
        period = ChargingSchedulePeriodData(start_period=0, limit=3680.0)  # 3680W / 230V = 16A
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.watts,
            charging_schedule_period=[period],
        )
        profile = ChargingProfileData(
            charging_profile_id=1, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
            charging_profile_kind=ChargingProfileKindType.relative,
            charging_schedule=schedule,
        )
        mgr = self._mgr_with_profile(profile)
        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=datetime.now(timezone.utc), connector_voltage=230.0,
        )
        assert result == pytest.approx(16.0, rel=1e-3)

    def test_min_of_chargepoint_max_and_tx_profile(self):
        """ChargePointMaxProfile caps a higher TxDefaultProfile."""
        from datetime import timedelta
        tx_default = _make_profile(profile_id=1, purpose=ChargingProfilePurposeType.tx_default_profile, limit=32.0)
        cp_max = _make_profile(profile_id=2, purpose=ChargingProfilePurposeType.charge_point_max_profile, limit=16.0)
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=tx_default)
        mgr.set_profile(connector_id=0, profile=cp_max)

        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=datetime.now(timezone.utc), connector_voltage=230.0,
        )
        assert result == pytest.approx(16.0)

    def test_tx_profile_takes_precedence_over_tx_default(self):
        """Active TxProfile replaces TxDefaultProfile for that transaction."""
        tx_default = _make_profile(profile_id=1, purpose=ChargingProfilePurposeType.tx_default_profile, limit=32.0)
        tx_profile = _make_profile(
            profile_id=2, purpose=ChargingProfilePurposeType.tx_profile,
            limit=10.0, transaction_id=99,
        )
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=tx_default)
        mgr.set_profile(connector_id=1, profile=tx_profile)

        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=99,
            now=datetime.now(timezone.utc), connector_voltage=230.0,
        )
        assert result == pytest.approx(10.0)

    def test_valid_from_to_filtering(self):
        """Profile outside validFrom/validTo window returns None."""
        from datetime import timedelta
        future = datetime(2030, 1, 1, tzinfo=timezone.utc)
        period = ChargingSchedulePeriodData(start_period=0, limit=16.0)
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=[period],
        )
        profile = ChargingProfileData(
            charging_profile_id=1, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
            charging_profile_kind=ChargingProfileKindType.relative,
            charging_schedule=schedule,
            valid_from=future,
        )
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=profile)
        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=datetime.now(timezone.utc), connector_voltage=230.0,
        )
        assert result is None
```

### Step 2: Run tests to verify they fail

```bash
poetry run pytest tests/test_charging_profile_manager.py::TestCompositeLimit -v
```
Expected: `AttributeError` — `get_composite_limit` not defined.

### Step 3: Implement get_composite_limit

Add these methods to `ChargingProfileManager` in the module:

```python
def get_composite_limit(
    self,
    connector_id: int,
    transaction_id: Optional[int],
    now: "datetime",
    connector_voltage: float,
    transaction_start: Optional["datetime"] = None,
    phases: int = 1,
) -> Optional[float]:
    """Return effective current limit in Amps, or None if no active profiles."""
    with self._lock:
        cp_max_limit = self._resolve_purpose_limit(
            ChargingProfilePurposeType.charge_point_max_profile,
            connector_id, transaction_id, now, connector_voltage,
            transaction_start, phases,
        )
        tx_limit = self._resolve_tx_limit(
            connector_id, transaction_id, now, connector_voltage,
            transaction_start, phases,
        )

        active_limits = [l for l in [cp_max_limit, tx_limit] if l is not None]
        if not active_limits:
            return None
        return min(active_limits)

def _resolve_tx_limit(
    self,
    connector_id: int,
    transaction_id: Optional[int],
    now: "datetime",
    connector_voltage: float,
    transaction_start: Optional["datetime"],
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
    now: "datetime",
    connector_voltage: float,
    transaction_start: Optional["datetime"],
    phases: int,
) -> Optional[float]:
    profiles = self.get_profiles_for_purpose(purpose, connector_id)
    # Filter by transaction_id for TxProfile
    if purpose == ChargingProfilePurposeType.tx_profile:
        profiles = [p for p in profiles if p.transaction_id == transaction_id]
    # Filter by validFrom/validTo
    profiles = [p for p in profiles if self._is_valid_at(p, now)]
    if not profiles:
        return None
    # Highest stack level is first (sorted in get_profiles_for_purpose)
    profile = profiles[0]
    return self._get_limit_from_profile(
        profile, now, connector_voltage, transaction_start, phases
    )

def _is_valid_at(self, profile: ChargingProfileData, now: "datetime") -> bool:
    if profile.valid_from is not None and now < profile.valid_from:
        return False
    if profile.valid_to is not None and now > profile.valid_to:
        return False
    return True

def _get_limit_from_profile(
    self,
    profile: ChargingProfileData,
    now: "datetime",
    connector_voltage: float,
    transaction_start: Optional["datetime"],
    phases: int,
) -> Optional[float]:
    schedule = profile.charging_schedule

    # Determine elapsed seconds into the schedule
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
            return None  # Schedule hasn't started yet
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

    # Check duration expiry
    if schedule.duration is not None and elapsed > schedule.duration:
        return None

    # Walk periods to find active one
    limit = self._find_period_limit(schedule.charging_schedule_period, elapsed)
    if limit is None:
        return None

    # Convert W → A if needed
    if schedule.charging_rate_unit == ChargingRateUnitType.watts:
        effective_phases = phases if phases > 0 else 1
        limit = limit / (connector_voltage * effective_phases)

    return limit

def _find_period_limit(
    self,
    periods: list[ChargingSchedulePeriodData],
    elapsed: float,
) -> Optional[float]:
    """Walk the period list and return the limit for the given elapsed seconds."""
    if not periods:
        return None
    active_limit = periods[0].limit
    for period in periods:
        if period.start_period <= elapsed:
            active_limit = period.limit
        else:
            break
    return active_limit
```

Also add the missing `datetime` import at the top of the file:
```python
from datetime import datetime
```

### Step 4: Run tests to verify they pass

```bash
poetry run pytest tests/test_charging_profile_manager.py::TestCompositeLimit -v
```
Expected: All 9 tests PASS.

### Step 5: Run all profile manager tests

```bash
poetry run pytest tests/test_charging_profile_manager.py -v
```
Expected: All tests PASS.

### Step 6: Commit

```bash
git add src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py tests/test_charging_profile_manager.py
git commit -m "feat: add composite limit calculation for Relative, Absolute and multi-purpose profiles"
```

---

## Task 4: Composite Limit — Recurring Schedules

**Files:**
- Modify: `tests/test_charging_profile_manager.py`

The recurring logic is already implemented in Task 3. This task verifies it with explicit tests.

### Step 1: Write failing tests for Recurring profiles

Add to `tests/test_charging_profile_manager.py`:

```python
class TestRecurringSchedules:
    def test_daily_recurring_wraps_cycle(self):
        """A daily profile cycles every 86400s. At elapsed=0 and elapsed=86400 both hit period 0."""
        from datetime import timedelta
        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        periods = [
            ChargingSchedulePeriodData(start_period=0, limit=24.0),
            ChargingSchedulePeriodData(start_period=43200, limit=8.0),  # noon: 8A
        ]
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=periods,
            start_schedule=start,
        )
        profile = ChargingProfileData(
            charging_profile_id=1, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
            charging_profile_kind=ChargingProfileKindType.recurring,
            charging_schedule=schedule,
            recurrency_kind=RecurrencyKind.daily,
        )
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=profile)

        # At midnight (elapsed=0): 24A
        assert mgr.get_composite_limit(
            connector_id=1, transaction_id=None, now=start, connector_voltage=230.0,
        ) == pytest.approx(24.0)

        # At noon same day (elapsed=43200): 8A
        assert mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start + timedelta(hours=12), connector_voltage=230.0,
        ) == pytest.approx(8.0)

        # Next midnight (elapsed=86400, wraps to 0): back to 24A
        assert mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start + timedelta(days=1), connector_voltage=230.0,
        ) == pytest.approx(24.0)

    def test_weekly_recurring(self):
        """A weekly profile cycles every 604800s."""
        from datetime import timedelta
        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)  # Monday
        periods = [
            ChargingSchedulePeriodData(start_period=0, limit=32.0),
            ChargingSchedulePeriodData(start_period=345600, limit=16.0),  # Day 4 (Thu)
        ]
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=periods,
            start_schedule=start,
        )
        profile = ChargingProfileData(
            charging_profile_id=1, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
            charging_profile_kind=ChargingProfileKindType.recurring,
            charging_schedule=schedule,
            recurrency_kind=RecurrencyKind.weekly,
        )
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=profile)

        # Monday: 32A
        assert mgr.get_composite_limit(
            connector_id=1, transaction_id=None, now=start, connector_voltage=230.0,
        ) == pytest.approx(32.0)

        # Thursday+: 16A
        assert mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start + timedelta(days=4), connector_voltage=230.0,
        ) == pytest.approx(16.0)

        # Next Monday (wraps): 32A again
        assert mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start + timedelta(weeks=1), connector_voltage=230.0,
        ) == pytest.approx(32.0)

    def test_recurring_before_start_schedule_returns_none(self):
        """A recurring profile before startSchedule is inactive."""
        from datetime import timedelta
        future_start = datetime(2030, 1, 1, tzinfo=timezone.utc)
        period = ChargingSchedulePeriodData(start_period=0, limit=16.0)
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=[period],
            start_schedule=future_start,
        )
        profile = ChargingProfileData(
            charging_profile_id=1, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
            charging_profile_kind=ChargingProfileKindType.recurring,
            charging_schedule=schedule,
            recurrency_kind=RecurrencyKind.daily,
        )
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=profile)
        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=datetime.now(timezone.utc), connector_voltage=230.0,
        )
        assert result is None
```

### Step 2: Run tests

```bash
poetry run pytest tests/test_charging_profile_manager.py::TestRecurringSchedules -v
```
Expected: All 3 tests PASS (recurring logic already in Task 3 implementation).

### Step 3: Commit

```bash
git add tests/test_charging_profile_manager.py
git commit -m "test: add recurring schedule coverage for daily and weekly profiles"
```

---

## Task 5: GetCompositeSchedule Period Builder

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py`
- Modify: `tests/test_charging_profile_manager.py`

### Step 1: Write failing tests

Add to `tests/test_charging_profile_manager.py`:

```python
class TestGetCompositeSchedule:
    def test_no_profiles_returns_empty_schedule(self):
        mgr = ChargingProfileManager()
        result = mgr.get_composite_schedule(
            connector_id=1,
            duration=3600,
            now=datetime.now(timezone.utc),
            connector_voltage=230.0,
            transaction_id=None,
        )
        assert result["status"] == "Accepted"
        assert result["schedule_periods"] == []

    def test_single_period_profile(self):
        from datetime import timedelta
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=1, limit=16.0))
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = mgr.get_composite_schedule(
            connector_id=1, duration=3600, now=now,
            connector_voltage=230.0, transaction_id=None,
        )
        assert result["status"] == "Accepted"
        assert len(result["schedule_periods"]) == 1
        assert result["schedule_periods"][0]["limit"] == pytest.approx(16.0)
        assert result["schedule_periods"][0]["start_period"] == 0

    def test_two_period_profile_produces_two_entries(self):
        from datetime import timedelta
        periods = [
            ChargingSchedulePeriodData(start_period=0, limit=16.0),
            ChargingSchedulePeriodData(start_period=1800, limit=8.0),
        ]
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=periods,
        )
        profile = ChargingProfileData(
            charging_profile_id=1, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
            charging_profile_kind=ChargingProfileKindType.relative,
            charging_schedule=schedule,
        )
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=profile)
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = mgr.get_composite_schedule(
            connector_id=1, duration=3600, now=now,
            connector_voltage=230.0, transaction_id=None,
            transaction_start=now,
        )
        assert len(result["schedule_periods"]) == 2
        assert result["schedule_periods"][0]["limit"] == pytest.approx(16.0)
        assert result["schedule_periods"][1]["limit"] == pytest.approx(8.0)
        assert result["schedule_periods"][1]["start_period"] == 1800
```

### Step 2: Run to verify failure

```bash
poetry run pytest tests/test_charging_profile_manager.py::TestGetCompositeSchedule -v
```
Expected: `AttributeError` — `get_composite_schedule` not defined.

### Step 3: Implement get_composite_schedule

Add to `ChargingProfileManager`:

```python
def get_composite_schedule(
    self,
    connector_id: int,
    duration: int,
    now: "datetime",
    connector_voltage: float,
    transaction_id: Optional[int] = None,
    transaction_start: Optional["datetime"] = None,
    requested_unit: "ChargingRateUnitType" = None,
    phases: int = 1,
) -> dict:
    """Build a composite schedule for the requested duration window.
    Returns dict with 'status', 'schedule_periods', and 'charging_rate_unit'."""
    from datetime import timedelta

    # Sample the limit at each second where a period boundary occurs,
    # building a minimal change-only list.
    # We collect all period boundary offsets from all active profiles,
    # then evaluate the composite limit at each boundary.
    boundaries = set([0])

    with self._lock:
        for cid, profile in self._profiles.values():
            if cid != 0 and cid != connector_id:
                continue
            if not self._is_valid_at(profile, now):
                continue
            for period in profile.charging_schedule.charging_schedule_period:
                sp = period.start_period
                # Adjust boundary for profile kind
                if profile.charging_profile_kind == ChargingProfileKindType.relative:
                    offset = sp
                elif profile.charging_profile_kind == ChargingProfileKindType.absolute:
                    start = profile.charging_schedule.start_schedule or now
                    base = max(0.0, (now - start).total_seconds())
                    offset = max(0, int(sp - base))
                elif profile.charging_profile_kind == ChargingProfileKindType.recurring:
                    start = profile.charging_schedule.start_schedule
                    if start is None:
                        continue
                    total = (now - start).total_seconds()
                    if total < 0:
                        continue
                    cycle = 86400.0 if profile.recurrency_kind == RecurrencyKind.daily else 604800.0
                    elapsed_in_cycle = total % cycle
                    offset = max(0, int(sp - elapsed_in_cycle))
                else:
                    continue
                if 0 <= offset < duration:
                    boundaries.add(offset)

    schedule_periods = []
    last_limit = None
    for offset in sorted(boundaries):
        check_time = now + timedelta(seconds=offset)
        limit = self.get_composite_limit(
            connector_id=connector_id,
            transaction_id=transaction_id,
            now=check_time,
            connector_voltage=connector_voltage,
            transaction_start=transaction_start,
            phases=phases,
        )
        if limit != last_limit:
            schedule_periods.append({
                "start_period": offset,
                "limit": limit,
            })
            last_limit = limit

    return {
        "status": "Accepted",
        "schedule_periods": schedule_periods,
        "charging_rate_unit": "A",
    }
```

### Step 4: Run tests to verify they pass

```bash
poetry run pytest tests/test_charging_profile_manager.py::TestGetCompositeSchedule -v
```
Expected: All 3 tests PASS.

### Step 5: Run the full test suite

```bash
poetry run pytest tests/test_charging_profile_manager.py -v
```
Expected: All tests PASS.

### Step 6: Commit

```bash
git add src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py tests/test_charging_profile_manager.py
git commit -m "feat: add GetCompositeSchedule period list builder"
```

---

## Task 6: Adapter OCPP Handlers

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/adapter.py`

### Step 1: Add imports to adapter.py

At the top of the file, add to the existing imports:

```python
from ocpp.v16.enums import (
    # existing imports...
    ChargingProfileStatus,
    ClearChargingProfileStatus,
    GetCompositeScheduleStatus,
    ChargingProfilePurposeType,
    ChargingProfileKindType,
    RecurrencyKind,
    ChargingRateUnitType,
)
from chargeghost_evse.ocpp_adapter.charging_profile_manager import (
    ChargingProfileManager,
    ChargingProfileData,
    ChargingScheduleData,
    ChargingSchedulePeriodData,
)
```

### Step 2: Instantiate ChargingProfileManager in Adapter.__init__

In `Adapter.__init__`, after `self.config_manager.initialize_defaults()`, add:

```python
max_profiles = self.config_manager.get_int_value("MaxChargingProfilesInstalled", 20)
max_stack = self.config_manager.get_int_value("ChargeProfileMaxStackLevel", 5)
max_periods = self.config_manager.get_int_value("ChargingScheduleMaxPeriods", 10)
self.charging_profile_manager = ChargingProfileManager(
    max_profiles=max_profiles,
    max_stack_level=max_stack,
    max_schedule_periods=max_periods,
)
```

### Step 3: Add _parse_charging_profile helper method

Add this private method to `Adapter`:

```python
def _parse_charging_profile(self, raw: dict) -> Optional[ChargingProfileData]:
    """Convert the raw dict from the ocpp library into a ChargingProfileData."""
    from datetime import datetime, timezone
    try:
        raw_schedule = raw.get("charging_schedule", {})
        periods = [
            ChargingSchedulePeriodData(
                start_period=p["start_period"],
                limit=float(p["limit"]),
                number_phases=p.get("number_phases"),
            )
            for p in raw_schedule.get("charging_schedule_period", [])
        ]
        start_schedule_str = raw_schedule.get("start_schedule")
        start_schedule = (
            datetime.fromisoformat(start_schedule_str)
            if start_schedule_str else None
        )
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType(raw_schedule.get("charging_rate_unit", "A")),
            charging_schedule_period=periods,
            duration=raw_schedule.get("duration"),
            start_schedule=start_schedule,
            min_charging_rate=raw_schedule.get("min_charging_rate"),
        )
        valid_from_str = raw.get("valid_from")
        valid_to_str = raw.get("valid_to")
        recurrency_str = raw.get("recurrency_kind")
        return ChargingProfileData(
            charging_profile_id=int(raw["charging_profile_id"]),
            stack_level=int(raw["stack_level"]),
            charging_profile_purpose=ChargingProfilePurposeType(raw["charging_profile_purpose"]),
            charging_profile_kind=ChargingProfileKindType(raw["charging_profile_kind"]),
            charging_schedule=schedule,
            transaction_id=raw.get("transaction_id"),
            recurrency_kind=RecurrencyKind(recurrency_str) if recurrency_str else None,
            valid_from=datetime.fromisoformat(valid_from_str) if valid_from_str else None,
            valid_to=datetime.fromisoformat(valid_to_str) if valid_to_str else None,
        )
    except (KeyError, ValueError, TypeError) as e:
        self._log(f"Failed to parse ChargingProfile: {e}", is_important=True)
        return None
```

### Step 4: Add the three OCPP handlers

Add these handler methods to `Adapter` (before the `send_boot_notification` method):

```python
@on("SetChargingProfile")
async def on_set_charging_profile(
    self, connector_id: int, cs_charging_profiles, **kwargs
) -> call_result.SetChargingProfile:
    self._log(
        f"SetChargingProfile: connector_id={connector_id}",
        is_ocpp_message=True, is_important=True,
    )
    raw = cs_charging_profiles if isinstance(cs_charging_profiles, dict) else vars(cs_charging_profiles)
    profile = self._parse_charging_profile(raw)
    if profile is None:
        return call_result.SetChargingProfile(status=ChargingProfileStatus.rejected)

    error = self.charging_profile_manager.set_profile(
        connector_id=connector_id, profile=profile
    )
    if error:
        self._log(f"SetChargingProfile rejected: {error}", is_important=True)
        return call_result.SetChargingProfile(status=ChargingProfileStatus.rejected)

    self._log(
        f"SetChargingProfile accepted: id={profile.charging_profile_id}, "
        f"purpose={profile.charging_profile_purpose.value}, "
        f"stack={profile.stack_level}",
        is_important=True,
    )
    return call_result.SetChargingProfile(status=ChargingProfileStatus.accepted)


@on("ClearChargingProfile")
async def on_clear_charging_profile(
    self,
    id: Optional[int] = None,
    connector_id: Optional[int] = None,
    charging_profile_purpose: Optional[str] = None,
    stack_level: Optional[int] = None,
    **kwargs,
) -> call_result.ClearChargingProfile:
    self._log(
        f"ClearChargingProfile: id={id}, connector_id={connector_id}, "
        f"purpose={charging_profile_purpose}, stack_level={stack_level}",
        is_ocpp_message=True, is_important=True,
    )
    purpose_enum = (
        ChargingProfilePurposeType(charging_profile_purpose)
        if charging_profile_purpose else None
    )
    cleared = self.charging_profile_manager.clear_profiles(
        profile_id=id,
        connector_id=connector_id,
        purpose=purpose_enum,
        stack_level=stack_level,
    )
    if cleared == 0:
        return call_result.ClearChargingProfile(status=ClearChargingProfileStatus.unknown)
    self._log(f"ClearChargingProfile: removed {cleared} profile(s)", is_important=True)
    return call_result.ClearChargingProfile(status=ClearChargingProfileStatus.accepted)


@on("GetCompositeSchedule")
async def on_get_composite_schedule(
    self,
    connector_id: int,
    duration: int,
    charging_rate_unit: Optional[str] = None,
    **kwargs,
) -> call_result.GetCompositeSchedule:
    from datetime import datetime, timezone
    self._log(
        f"GetCompositeSchedule: connector_id={connector_id}, duration={duration}",
        is_ocpp_message=True, is_important=True,
    )
    transaction_id = self.active_transactions.get(connector_id)
    now = datetime.now(timezone.utc)
    result = self.charging_profile_manager.get_composite_schedule(
        connector_id=connector_id,
        duration=duration,
        now=now,
        connector_voltage=230.0,  # Default; Bridge will override via connector lookup
        transaction_id=transaction_id,
    )
    if not result["schedule_periods"]:
        return call_result.GetCompositeSchedule(
            status=GetCompositeScheduleStatus.accepted,
            connector_id=connector_id,
        )
    return call_result.GetCompositeSchedule(
        status=GetCompositeScheduleStatus.accepted,
        connector_id=connector_id,
        schedule_start=now.isoformat(),
        charging_schedule={
            "chargingRateUnit": result["charging_rate_unit"],
            "chargingSchedulePeriod": [
                {"startPeriod": p["start_period"], "limit": p["limit"]}
                for p in result["schedule_periods"]
            ],
            "duration": duration,
        },
    )
```

### Step 5: Run tests to confirm nothing is broken

```bash
poetry run pytest tests/ -v
```
Expected: All existing tests PASS.

### Step 6: Commit

```bash
git add src/chargeghost_evse/ocpp_adapter/adapter.py
git commit -m "feat: add SetChargingProfile, ClearChargingProfile, GetCompositeSchedule handlers to adapter"
```

---

## Task 7: Engine — Injectable Limit Enforcement

**Files:**
- Modify: `src/chargeghost_evse/engine/engine.py`
- Modify: `tests/test_engine.py`

### Step 1: Write failing tests for limit enforcement

Add to `tests/test_engine.py`:

```python
class TestChargingProfileEnforcement:
    def test_simulate_without_limit_uses_full_current(self):
        engine = Engine()
        engine.add_connector(voltage=230, current=32, phase=1)
        engine.plug_in(1)
        engine.start_session(connector_id=1, transaction_id=1)
        engine.simulate(3600)
        # 230V * 32A * 1 phase * 1h = 7360 Wh
        assert engine.energy_meter.get_meter_reading() == pytest.approx(7360.0)

    def test_simulate_with_limit_caps_current(self):
        engine = Engine()
        engine.add_connector(voltage=230, current=32, phase=1)
        engine.plug_in(1)
        engine.start_session(connector_id=1, transaction_id=1)

        # Inject a limit of 16A
        engine.get_limit = lambda conn_id, tx_id: 16.0

        engine.simulate(3600)
        # 230V * 16A * 1 phase * 1h = 3680 Wh
        assert engine.energy_meter.get_meter_reading() == pytest.approx(3680.0)

    def test_simulate_limit_none_uses_full_current(self):
        engine = Engine()
        engine.add_connector(voltage=230, current=32, phase=1)
        engine.plug_in(1)
        engine.start_session(connector_id=1, transaction_id=1)

        engine.get_limit = lambda conn_id, tx_id: None

        engine.simulate(3600)
        assert engine.energy_meter.get_meter_reading() == pytest.approx(7360.0)

    def test_limit_cannot_exceed_connector_current(self):
        """A limit higher than connector.current is clamped to connector.current."""
        engine = Engine()
        engine.add_connector(voltage=230, current=16, phase=1)
        engine.plug_in(1)
        engine.start_session(connector_id=1, transaction_id=1)

        # Limit of 32A but connector only supports 16A
        engine.get_limit = lambda conn_id, tx_id: 32.0

        engine.simulate(3600)
        # Should use connector's 16A, not 32A
        assert engine.energy_meter.get_meter_reading() == pytest.approx(3680.0)
```

### Step 2: Run tests to verify failure

```bash
poetry run pytest tests/test_engine.py::TestChargingProfileEnforcement -v
```
Expected: First test passes (no `get_limit` yet but no error), others fail.

### Step 3: Modify Engine to support injectable limit

In `Engine.__init__`, add:
```python
self.get_limit: Optional[callable] = None
```

In `Engine.simulate()`, replace the `self.energy_meter.update(...)` call with:

```python
def simulate(self, interval_seconds: float):
    self._process_commands()
    if self.session and self.energy_meter.is_charging:
        connector = self._connectors.get(self.session.connector_id)
        if connector is None:
            return

        effective_current = connector.current
        if self.get_limit is not None:
            limit = self.get_limit(self.session.connector_id, self.session.transaction_id)
            if limit is not None:
                effective_current = min(connector.current, limit)

        self.energy_meter.update(
            connector.voltage,
            effective_current,
            connector.phase,
            interval_seconds=interval_seconds,
        )
        self.event_queue.append(self.energy_meter.get_meter_reading())
```

### Step 4: Run tests to verify they pass

```bash
poetry run pytest tests/test_engine.py -v
```
Expected: All tests PASS including the 4 new ones.

### Step 5: Commit

```bash
git add src/chargeghost_evse/engine/engine.py tests/test_engine.py
git commit -m "feat: add injectable get_limit to Engine for charging profile enforcement"
```

---

## Task 8: Bridge Wiring

**Files:**
- Modify: `src/chargeghost_evse/bridge/bridge.py`

### Step 1: Wire get_limit into Engine after adapter comes online

In `Bridge.setup()`, after `self.engine.session_started.subscribe(...)`, add:

```python
# Start a thread to inject the limit getter once the adapter is ready
threading.Thread(target=self._inject_limit_getter, daemon=True).start()
```

Add this method to `Bridge`:

```python
def _inject_limit_getter(self) -> None:
    """Wait for the adapter to be ready, then inject the composite limit getter."""
    while not self._shutdown_event.is_set():
        if self.runner.is_connected and self.runner.adapter:
            adapter = self.runner.adapter

            def get_limit(connector_id: int, transaction_id: Optional[int]) -> Optional[float]:
                if not self.runner.adapter:
                    return None
                connector = self.engine.get_connector(connector_id)
                voltage = connector.voltage if connector else 230.0
                phases = connector.phase if connector else 1
                from datetime import datetime, timezone
                return self.runner.adapter.charging_profile_manager.get_composite_limit(
                    connector_id=connector_id,
                    transaction_id=transaction_id,
                    now=datetime.now(timezone.utc),
                    connector_voltage=voltage,
                    phases=phases,
                )

            self.engine.get_limit = get_limit
            self._log(message="Charging profile limit getter injected into engine.")
            break
        self._shutdown_event.wait(timeout=0.5)
```

Also add `Optional` to imports at the top if not already there:
```python
from typing import Optional
```

### Step 2: Run all tests

```bash
poetry run pytest tests/ -v
```
Expected: All tests PASS.

### Step 3: Commit

```bash
git add src/chargeghost_evse/bridge/bridge.py
git commit -m "feat: wire charging profile limit getter from adapter into engine via bridge"
```

---

## Task 9: Integration Tests

**Files:**
- Create: `tests/test_smart_charging.py`

### Step 1: Write integration tests

```python
# tests/test_smart_charging.py
"""
Integration tests for Smart Charging: adapter → profile manager → engine enforcement.
"""
import pytest
from datetime import datetime, timezone, timedelta
from ocpp.v16.enums import (
    ChargingProfilePurposeType,
    ChargingProfileKindType,
    ChargingRateUnitType,
    ChargingProfileStatus,
    ClearChargingProfileStatus,
)
from chargeghost_evse.ocpp_adapter.charging_profile_manager import (
    ChargingProfileManager,
    ChargingProfileData,
    ChargingScheduleData,
    ChargingSchedulePeriodData,
)
from chargeghost_evse.engine.engine import Engine


def _build_profile(
    profile_id: int,
    purpose: ChargingProfilePurposeType,
    limit_amps: float,
    stack_level: int = 0,
    transaction_id: int = None,
    kind: ChargingProfileKindType = ChargingProfileKindType.relative,
) -> ChargingProfileData:
    return ChargingProfileData(
        charging_profile_id=profile_id,
        stack_level=stack_level,
        charging_profile_purpose=purpose,
        charging_profile_kind=kind,
        charging_schedule=ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=[
                ChargingSchedulePeriodData(start_period=0, limit=limit_amps)
            ],
        ),
        transaction_id=transaction_id,
    )


class TestSetAndClearProfile:
    def test_set_profile_and_limit_is_active(self):
        mgr = ChargingProfileManager()
        profile = _build_profile(1, ChargingProfilePurposeType.tx_default_profile, 16.0)
        error = mgr.set_profile(connector_id=1, profile=profile)
        assert error is None
        limit = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=datetime.now(timezone.utc), connector_voltage=230.0,
        )
        assert limit == pytest.approx(16.0)

    def test_clear_profile_removes_limit(self):
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=_build_profile(1, ChargingProfilePurposeType.tx_default_profile, 16.0))
        mgr.clear_profiles(profile_id=1)
        limit = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=datetime.now(timezone.utc), connector_voltage=230.0,
        )
        assert limit is None

    def test_higher_stack_level_overrides_lower(self):
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=_build_profile(1, ChargingProfilePurposeType.tx_default_profile, 32.0, stack_level=0))
        mgr.set_profile(connector_id=1, profile=_build_profile(2, ChargingProfilePurposeType.tx_default_profile, 10.0, stack_level=1))
        limit = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=datetime.now(timezone.utc), connector_voltage=230.0,
        )
        assert limit == pytest.approx(10.0)

    def test_profile_expiry_reverts_to_none(self):
        tx_start = datetime.now(timezone.utc) - timedelta(seconds=7200)
        profile = ChargingProfileData(
            charging_profile_id=1, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_profile,
            charging_profile_kind=ChargingProfileKindType.relative,
            charging_schedule=ChargingScheduleData(
                charging_rate_unit=ChargingRateUnitType.amps,
                charging_schedule_period=[ChargingSchedulePeriodData(start_period=0, limit=16.0)],
                duration=3600,
            ),
            transaction_id=1,
        )
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=profile)
        limit = mgr.get_composite_limit(
            connector_id=1, transaction_id=1,
            now=datetime.now(timezone.utc), connector_voltage=230.0,
            transaction_start=tx_start,
        )
        assert limit is None


class TestEngineEnforcement:
    def test_engine_respects_profile_limit(self):
        """A 16A profile on a 32A connector should halve the energy consumed."""
        engine = Engine()
        engine.add_connector(voltage=230, current=32, phase=1)
        engine.plug_in(1)
        engine.start_session(connector_id=1, transaction_id=1)

        engine.get_limit = lambda conn_id, tx_id: 16.0

        engine.simulate(3600)
        # 230V * 16A * 1h = 3680 Wh (not 7360 Wh)
        assert engine.energy_meter.get_meter_reading() == pytest.approx(3680.0)

    def test_engine_without_profile_uses_connector_current(self):
        engine = Engine()
        engine.add_connector(voltage=230, current=32, phase=1)
        engine.plug_in(1)
        engine.start_session(connector_id=1, transaction_id=1)
        engine.simulate(3600)
        assert engine.energy_meter.get_meter_reading() == pytest.approx(7360.0)

    def test_limit_changes_mid_session(self):
        """Changing the limit callable mid-session changes simulation output."""
        engine = Engine()
        engine.add_connector(voltage=230, current=32, phase=1)
        engine.plug_in(1)
        engine.start_session(connector_id=1, transaction_id=1)

        # First 30 minutes at 32A
        engine.get_limit = lambda c, t: None
        engine.simulate(1800)
        energy_at_half = engine.energy_meter.get_meter_reading()

        # Second 30 minutes at 8A
        engine.get_limit = lambda c, t: 8.0
        engine.simulate(1800)
        energy_at_end = engine.energy_meter.get_meter_reading()

        # First half: 230*32*0.5h = 3680 Wh
        # Second half: 230*8*0.5h = 920 Wh
        assert energy_at_half == pytest.approx(3680.0)
        assert energy_at_end == pytest.approx(3680.0 + 920.0)
```

### Step 2: Run integration tests

```bash
poetry run pytest tests/test_smart_charging.py -v
```
Expected: All 7 tests PASS.

### Step 3: Run full test suite

```bash
poetry run pytest tests/ -v
```
Expected: All tests PASS.

### Step 4: Commit

```bash
git add tests/test_smart_charging.py
git commit -m "test: add smart charging integration tests"
```

---

## Task 10: Read-Only Profiles UI Panel

**Files:**
- Create: `src/chargeghost_evse/ui/widgets/charging_profiles_panel.py`
- Modify: `src/chargeghost_evse/ui/widgets/session_dashboard.py` (or wherever the main dashboard assembles panels — check the file to find the right insertion point)

### Step 1: Read session_dashboard.py to understand the widget patterns

```bash
cat src/chargeghost_evse/ui/widgets/session_dashboard.py
```

### Step 2: Create the profiles panel widget

```python
# src/chargeghost_evse/ui/widgets/charging_profiles_panel.py
from typing import Optional, TYPE_CHECKING
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

if TYPE_CHECKING:
    from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager


class ChargingProfilesPanel(QWidget):
    """Read-only panel showing active OCPP charging profiles and the current effective limit."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 8)
        layout.setSpacing(6)

        title = QLabel("Charging Profiles")
        title.setObjectName("sectionHeader")
        layout.addWidget(title)

        self._effective_limit_label = QLabel("Effective limit: —")
        self._effective_limit_label.setObjectName("metricValue")
        layout.addWidget(self._effective_limit_label)

        self._profiles_container = QVBoxLayout()
        self._profiles_container.setSpacing(4)
        layout.addLayout(self._profiles_container)

        self._no_profiles_label = QLabel("No active profiles")
        self._no_profiles_label.setObjectName("dimLabel")
        self._profiles_container.addWidget(self._no_profiles_label)

        layout.addStretch()

    def update_profiles(
        self,
        profile_manager: "ChargingProfileManager",
        connector_id: int,
        transaction_id: Optional[int],
        connector_voltage: float = 230.0,
    ) -> None:
        from datetime import datetime, timezone

        # Clear old rows
        while self._profiles_container.count():
            item = self._profiles_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        all_profiles = profile_manager.get_all_profiles()
        active_rows = []
        for cid, profile in all_profiles:
            if cid != 0 and cid != connector_id:
                continue
            purpose = profile.charging_profile_purpose.value
            stack = profile.stack_level
            pid = profile.charging_profile_id
            active_rows.append((pid, purpose, stack))

        if not active_rows:
            no_label = QLabel("No active profiles")
            no_label.setObjectName("dimLabel")
            self._profiles_container.addWidget(no_label)
            self._effective_limit_label.setText("Effective limit: —")
            return

        for pid, purpose, stack in active_rows:
            row = QLabel(f"  #{pid}  {purpose}  (stack {stack})")
            row.setObjectName("profileRow")
            self._profiles_container.addWidget(row)

        now = datetime.now(timezone.utc)
        limit = profile_manager.get_composite_limit(
            connector_id=connector_id,
            transaction_id=transaction_id,
            now=now,
            connector_voltage=connector_voltage,
        )
        if limit is not None:
            self._effective_limit_label.setText(f"Effective limit: {limit:.1f} A")
        else:
            self._effective_limit_label.setText("Effective limit: —")
```

### Step 3: Read session_dashboard.py fully, find the right place to add the panel

Read `src/chargeghost_evse/ui/widgets/session_dashboard.py` in full, then add:
1. Import `ChargingProfilesPanel` at the top
2. Instantiate it in `__init__` and add it to the layout after the existing metrics section
3. Add a `update_charging_profiles(profile_manager, connector_id, transaction_id, voltage)` method that delegates to the panel

### Step 4: Run the full test suite

```bash
poetry run pytest tests/ -v
```
Expected: All tests PASS.

### Step 5: Commit

```bash
git add src/chargeghost_evse/ui/widgets/charging_profiles_panel.py src/chargeghost_evse/ui/widgets/session_dashboard.py
git commit -m "feat: add read-only charging profiles panel to session dashboard"
```

---

## Task 11: Final Verification

### Step 1: Run the complete test suite

```bash
poetry run pytest tests/ -v --tb=short
```
Expected: All tests PASS. No regressions.

### Step 2: Quick smoke test — verify SetChargingProfile is in the adapter's handler list

```bash
poetry run python -c "
from chargeghost_evse.ocpp_adapter.adapter import Adapter
handlers = [h for h in dir(Adapter) if h.startswith('on_')]
for h in sorted(handlers):
    print(h)
"
```
Expected output includes: `on_set_charging_profile`, `on_clear_charging_profile`, `on_get_composite_schedule`

### Step 3: Final commit if any stray changes

```bash
git status
# If clean, nothing to do. If there are stray files:
git add <any remaining files>
git commit -m "chore: finalize smart charging implementation"
```
