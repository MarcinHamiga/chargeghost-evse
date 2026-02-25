from datetime import datetime, timedelta, timezone
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
            charging_schedule_period=(period,),
        )
        assert schedule.charging_rate_unit == ChargingRateUnitType.amps
        assert len(schedule.charging_schedule_period) == 1
        assert schedule.duration is None
        assert schedule.start_schedule is None

    def test_profile_creation(self):
        period = ChargingSchedulePeriodData(start_period=0, limit=16.0)
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=(period,),
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

    def test_schedule_is_immutable(self):
        import pytest
        period = ChargingSchedulePeriodData(start_period=0, limit=16.0)
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=(period,),
        )
        with pytest.raises(Exception):
            schedule.duration = 999  # type: ignore


from typing import Optional


def _make_profile(
    profile_id: int = 1,
    stack_level: int = 0,
    purpose: ChargingProfilePurposeType = ChargingProfilePurposeType.tx_default_profile,
    kind: ChargingProfileKindType = ChargingProfileKindType.relative,
    limit: float = 16.0,
    transaction_id: Optional[int] = None,
    unit: ChargingRateUnitType = ChargingRateUnitType.amps,
    num_periods: int = 1,
) -> "ChargingProfileData":
    periods = tuple(ChargingSchedulePeriodData(start_period=i * 100, limit=limit) for i in range(num_periods))
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
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
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
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=1, limit=16.0))
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=1, limit=32.0))
        profiles = mgr.get_profiles_for_purpose(
            ChargingProfilePurposeType.tx_default_profile, connector_id=1
        )
        assert len(profiles) == 1
        assert profiles[0].charging_schedule.charging_schedule_period[0].limit == 32.0

    def test_clear_by_id(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=1))
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=2))
        cleared = mgr.clear_profiles(profile_id=1)
        assert cleared == 1
        profiles = mgr.get_profiles_for_purpose(
            ChargingProfilePurposeType.tx_default_profile, connector_id=1
        )
        assert len(profiles) == 1
        assert profiles[0].charging_profile_id == 2

    def test_clear_by_purpose(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=1, purpose=ChargingProfilePurposeType.tx_default_profile))
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=2, purpose=ChargingProfilePurposeType.tx_profile, transaction_id=99))
        cleared = mgr.clear_profiles(purpose=ChargingProfilePurposeType.tx_default_profile)
        assert cleared == 1

    def test_clear_nothing_returns_zero(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager()
        cleared = mgr.clear_profiles(profile_id=999)
        assert cleared == 0

    def test_reject_exceeds_max_profiles(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager(max_profiles=2)
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=1))
        mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=2))
        error = mgr.set_profile(connector_id=1, profile=_make_profile(profile_id=3))
        assert error == "max_profiles_exceeded"

    def test_reject_stack_level_too_high(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager(max_stack_level=3)
        error = mgr.set_profile(connector_id=1, profile=_make_profile(stack_level=4))
        assert error == "stack_level_exceeded"

    def test_reject_too_many_periods(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager(max_schedule_periods=3)
        error = mgr.set_profile(connector_id=1, profile=_make_profile(num_periods=4))
        assert error == "too_many_periods"

    def test_reject_tx_profile_without_transaction_id(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager()
        profile = _make_profile(
            purpose=ChargingProfilePurposeType.tx_profile,
            transaction_id=None,
        )
        error = mgr.set_profile(connector_id=1, profile=profile)
        assert error == "tx_profile_missing_transaction_id"

    def test_connector_zero_applies_to_all(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=0, profile=_make_profile(profile_id=1, purpose=ChargingProfilePurposeType.charge_point_max_profile))
        for conn_id in [1, 2, 3]:
            profiles = mgr.get_profiles_for_purpose(
                ChargingProfilePurposeType.charge_point_max_profile, connector_id=conn_id
            )
            assert len(profiles) == 1

    def test_highest_stack_level_returned_first(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
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


import pytest


class TestCompositeLimit:
    """Tests for get_composite_limit() — the core scheduling algorithm."""

    def _mgr_with_profile(self, profile, connector_id=1):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=connector_id, profile=profile)
        return mgr

    def test_no_profiles_returns_none(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager()
        result = mgr.get_composite_limit(
            connector_id=1,
            transaction_id=None,
            now=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            connector_voltage=230.0,
        )
        assert result is None

    def test_relative_profile_single_period(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        period = ChargingSchedulePeriodData(start_period=0, limit=16.0)
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=(period,),
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
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = mgr.get_composite_limit(
            connector_id=1,
            transaction_id=42,
            now=now,
            connector_voltage=230.0,
            transaction_start=now,
        )
        assert result == pytest.approx(16.0)

    def test_relative_profile_steps_through_periods(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        from datetime import timedelta
        periods = (
            ChargingSchedulePeriodData(start_period=0, limit=16.0),
            ChargingSchedulePeriodData(start_period=3600, limit=8.0),
        )
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=periods,
        )
        profile = ChargingProfileData(
            charging_profile_id=1, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_profile,
            charging_profile_kind=ChargingProfileKindType.relative,
            charging_schedule=schedule, transaction_id=42,
        )
        mgr = self._mgr_with_profile(profile)
        tx_start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        assert mgr.get_composite_limit(
            connector_id=1, transaction_id=42, now=tx_start,
            connector_voltage=230.0, transaction_start=tx_start,
        ) == pytest.approx(16.0)

        assert mgr.get_composite_limit(
            connector_id=1, transaction_id=42,
            now=tx_start + timedelta(seconds=1800),
            connector_voltage=230.0, transaction_start=tx_start,
        ) == pytest.approx(16.0)

        assert mgr.get_composite_limit(
            connector_id=1, transaction_id=42,
            now=tx_start + timedelta(seconds=3601),
            connector_voltage=230.0, transaction_start=tx_start,
        ) == pytest.approx(8.0)

    def test_relative_profile_expired_after_duration(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        from datetime import timedelta
        period = ChargingSchedulePeriodData(start_period=0, limit=16.0)
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=(period,),
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
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        from datetime import timedelta
        start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        periods = (
            ChargingSchedulePeriodData(start_period=0, limit=20.0),
            ChargingSchedulePeriodData(start_period=1800, limit=10.0),
        )
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
        assert mgr.get_composite_limit(
            connector_id=1, transaction_id=None, now=start, connector_voltage=230.0,
        ) == pytest.approx(20.0)
        assert mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start + timedelta(seconds=2000), connector_voltage=230.0,
        ) == pytest.approx(10.0)

    def test_watts_converted_to_amps(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        period = ChargingSchedulePeriodData(start_period=0, limit=3680.0)
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.watts,
            charging_schedule_period=(period,),
            start_schedule=start,
        )
        profile = ChargingProfileData(
            charging_profile_id=1, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
            charging_profile_kind=ChargingProfileKindType.absolute,
            charging_schedule=schedule,
        )
        mgr = self._mgr_with_profile(profile)
        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start,
            connector_voltage=230.0,
        )
        assert result == pytest.approx(16.0, rel=1e-3)

    def test_watts_with_zero_voltage_returns_none(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        period = ChargingSchedulePeriodData(start_period=0, limit=3680.0)
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.watts,
            charging_schedule_period=(period,),
            start_schedule=start,
        )
        profile = ChargingProfileData(
            charging_profile_id=1, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
            charging_profile_kind=ChargingProfileKindType.absolute,
            charging_schedule=schedule,
        )
        mgr = self._mgr_with_profile(profile)
        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start,
            connector_voltage=0.0,
        )
        assert result is None

    def test_watts_with_negative_voltage_returns_none(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        period = ChargingSchedulePeriodData(start_period=0, limit=3680.0)
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.watts,
            charging_schedule_period=(period,),
            start_schedule=start,
        )
        profile = ChargingProfileData(
            charging_profile_id=1, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
            charging_profile_kind=ChargingProfileKindType.absolute,
            charging_schedule=schedule,
        )
        mgr = self._mgr_with_profile(profile)
        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start,
            connector_voltage=-230.0,
        )
        assert result is None

    def test_min_of_chargepoint_max_and_tx_profile(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        tx_default_schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=(ChargingSchedulePeriodData(start_period=0, limit=32.0),),
            start_schedule=start,
        )
        tx_default = ChargingProfileData(
            charging_profile_id=1, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
            charging_profile_kind=ChargingProfileKindType.absolute,
            charging_schedule=tx_default_schedule,
        )
        cp_max_schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=(ChargingSchedulePeriodData(start_period=0, limit=16.0),),
            start_schedule=start,
        )
        cp_max = ChargingProfileData(
            charging_profile_id=2, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.charge_point_max_profile,
            charging_profile_kind=ChargingProfileKindType.absolute,
            charging_schedule=cp_max_schedule,
        )
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=tx_default)
        mgr.set_profile(connector_id=0, profile=cp_max)
        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start,
            connector_voltage=230.0,
        )
        assert result == pytest.approx(16.0)

    def test_tx_profile_takes_precedence_over_tx_default(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        tx_default_schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=(ChargingSchedulePeriodData(start_period=0, limit=32.0),),
            start_schedule=start,
        )
        tx_default = ChargingProfileData(
            charging_profile_id=1, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
            charging_profile_kind=ChargingProfileKindType.absolute,
            charging_schedule=tx_default_schedule,
        )
        tx_profile_schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=(ChargingSchedulePeriodData(start_period=0, limit=10.0),),
            start_schedule=start,
        )
        tx_profile = ChargingProfileData(
            charging_profile_id=2, stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_profile,
            charging_profile_kind=ChargingProfileKindType.absolute,
            charging_schedule=tx_profile_schedule,
            transaction_id=99,
        )
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=tx_default)
        mgr.set_profile(connector_id=1, profile=tx_profile)
        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=99,
            now=start,
            connector_voltage=230.0,
        )
        assert result == pytest.approx(10.0)

    def test_valid_from_to_filtering(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        future = datetime(2030, 1, 1, tzinfo=timezone.utc)
        period = ChargingSchedulePeriodData(start_period=0, limit=16.0)
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=(period,),
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
            now=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            connector_voltage=230.0,
        )
        assert result is None


class TestRecurringSchedules:
    """Tests for recurring profile cycle handling."""

    def _mgr_with_recurring_profile(self, kind: RecurrencyKind, start_schedule: datetime, limit: float = 16.0):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        period = ChargingSchedulePeriodData(start_period=0, limit=limit)
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=(period,),
            start_schedule=start_schedule,
            duration=3600,
        )
        profile = ChargingProfileData(
            charging_profile_id=1,
            stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
            charging_profile_kind=ChargingProfileKindType.recurring,
            charging_schedule=schedule,
            recurrency_kind=kind,
        )
        mgr = ChargingProfileManager()
        mgr.set_profile(connector_id=1, profile=profile)
        return mgr

    def test_daily_recurring_within_cycle(self):
        """Limit is active within the first daily cycle."""
        start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        mgr = self._mgr_with_recurring_profile(RecurrencyKind.daily, start, limit=16.0)

        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start + timedelta(seconds=1800),
            connector_voltage=230.0,
        )
        assert result == pytest.approx(16.0)

    def test_daily_recurring_wraps_to_next_day(self):
        """Limit wraps around after 24 hours."""
        start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        mgr = self._mgr_with_recurring_profile(RecurrencyKind.daily, start, limit=16.0)

        # 25 hours + 100 seconds later = 1 hour + 100 seconds into next cycle
        # elapsed within cycle = 3700s, but duration is 3600s, so it's expired
        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start + timedelta(seconds=90100),
            connector_voltage=230.0,
        )
        assert result is None

    def test_daily_recurring_active_next_day_at_same_time(self):
        """Limit is active at the same time next day."""
        start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        mgr = self._mgr_with_recurring_profile(RecurrencyKind.daily, start, limit=16.0)

        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start + timedelta(seconds=86400),
            connector_voltage=230.0,
        )
        assert result == pytest.approx(16.0)

    def test_weekly_recurring_within_cycle(self):
        """Weekly recurring profile is active within first week."""
        start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        mgr = self._mgr_with_recurring_profile(RecurrencyKind.weekly, start, limit=20.0)

        # Within the first hour of the cycle (duration=3600)
        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start + timedelta(seconds=1800),
            connector_voltage=230.0,
        )
        assert result == pytest.approx(20.0)

    def test_weekly_recurring_wraps_after_7_days(self):
        """Weekly recurring profile wraps after 7 days."""
        start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        mgr = self._mgr_with_recurring_profile(RecurrencyKind.weekly, start, limit=20.0)

        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start + timedelta(days=7, seconds=1800),
            connector_voltage=230.0,
        )
        assert result == pytest.approx(20.0)

    def test_recurring_before_start_schedule_returns_none(self):
        """Recurring profile is not active before startSchedule."""
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
        mgr = self._mgr_with_recurring_profile(RecurrencyKind.daily, start, limit=16.0)

        result = mgr.get_composite_limit(
            connector_id=1, transaction_id=None,
            now=start - timedelta(seconds=3600),
            connector_voltage=230.0,
        )
        assert result is None


class TestGetCompositeSchedule:
    """Tests for get_composite_schedule() method."""

    def _make_profile_with_periods(
        self,
        profile_id: int,
        purpose: ChargingProfilePurposeType,
        kind: ChargingProfileKindType,
        periods: list[tuple[int, float]],
        start_schedule: Optional[datetime] = None,
        transaction_id: Optional[int] = None,
    ):
        schedule_periods = tuple(
            ChargingSchedulePeriodData(start_period=sp, limit=lim)
            for sp, lim in periods
        )
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=schedule_periods,
            start_schedule=start_schedule,
        )
        return ChargingProfileData(
            charging_profile_id=profile_id,
            stack_level=0,
            charging_profile_purpose=purpose,
            charging_profile_kind=kind,
            charging_schedule=schedule,
            transaction_id=transaction_id,
        )

    def test_empty_when_no_profiles(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager()
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = mgr.get_composite_schedule(
            connector_id=1,
            transaction_id=None,
            start_time=start,
            duration=3600,
            connector_voltage=230.0,
        )
        assert result == []

    def test_single_profile_schedule(self):
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager()
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        profile = self._make_profile_with_periods(
            profile_id=1,
            purpose=ChargingProfilePurposeType.tx_default_profile,
            kind=ChargingProfileKindType.absolute,
            periods=[(0, 16.0), (1800, 8.0)],
            start_schedule=start,
        )
        mgr.set_profile(connector_id=1, profile=profile)

        result = mgr.get_composite_schedule(
            connector_id=1,
            transaction_id=None,
            start_time=start,
            duration=3600,
            connector_voltage=230.0,
        )

        assert len(result) == 2
        assert result[0].start_period == 0
        assert result[0].limit == pytest.approx(16.0)
        assert result[1].start_period == 1800
        assert result[1].limit == pytest.approx(8.0)

    def test_composite_of_chargepoint_max_and_tx_default(self):
        """Composite schedule takes minimum of ChargePointMaxProfile and TxDefaultProfile."""
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager()
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        cp_max = self._make_profile_with_periods(
            profile_id=1,
            purpose=ChargingProfilePurposeType.charge_point_max_profile,
            kind=ChargingProfileKindType.absolute,
            periods=[(0, 20.0)],
            start_schedule=start,
        )
        mgr.set_profile(connector_id=0, profile=cp_max)

        tx_default = self._make_profile_with_periods(
            profile_id=2,
            purpose=ChargingProfilePurposeType.tx_default_profile,
            kind=ChargingProfileKindType.absolute,
            periods=[(0, 16.0)],
            start_schedule=start,
        )
        mgr.set_profile(connector_id=1, profile=tx_default)

        result = mgr.get_composite_schedule(
            connector_id=1,
            transaction_id=None,
            start_time=start,
            duration=3600,
            connector_voltage=230.0,
        )

        assert len(result) == 1
        assert result[0].limit == pytest.approx(16.0)

    def test_composite_with_different_period_boundaries(self):
        """Composite schedule includes period boundaries from both profiles."""
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager()
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # ChargePointMaxProfile: 32A until 1800s, then 16A
        cp_max = self._make_profile_with_periods(
            profile_id=1,
            purpose=ChargingProfilePurposeType.charge_point_max_profile,
            kind=ChargingProfileKindType.absolute,
            periods=[(0, 32.0), (1800, 16.0)],
            start_schedule=start,
        )
        mgr.set_profile(connector_id=0, profile=cp_max)

        # TxDefaultProfile: 20A until 900s, then 10A
        tx_default = self._make_profile_with_periods(
            profile_id=2,
            purpose=ChargingProfilePurposeType.tx_default_profile,
            kind=ChargingProfileKindType.absolute,
            periods=[(0, 20.0), (900, 10.0)],
            start_schedule=start,
        )
        mgr.set_profile(connector_id=1, profile=tx_default)

        result = mgr.get_composite_schedule(
            connector_id=1,
            transaction_id=None,
            start_time=start,
            duration=3600,
            connector_voltage=230.0,
        )

        # Expected: 0s->20A (min(32,20)), 900s->10A (min(32,10))
        # At 1800s, limit would be min(16,10)=10A, same as 900s, so deduplicated
        assert len(result) == 2
        assert result[0].start_period == 0
        assert result[0].limit == pytest.approx(20.0)  # min(32, 20)
        assert result[1].start_period == 900
        assert result[1].limit == pytest.approx(10.0)  # min(32, 10)

    def test_tx_profile_overrides_tx_default(self):
        """TxProfile takes precedence over TxDefaultProfile."""
        from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager
        mgr = ChargingProfileManager()
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        tx_default = self._make_profile_with_periods(
            profile_id=1,
            purpose=ChargingProfilePurposeType.tx_default_profile,
            kind=ChargingProfileKindType.absolute,
            periods=[(0, 32.0)],
            start_schedule=start,
        )
        mgr.set_profile(connector_id=1, profile=tx_default)

        tx_profile = self._make_profile_with_periods(
            profile_id=2,
            purpose=ChargingProfilePurposeType.tx_profile,
            kind=ChargingProfileKindType.absolute,
            periods=[(0, 8.0)],
            start_schedule=start,
            transaction_id=99,
        )
        mgr.set_profile(connector_id=1, profile=tx_profile)

        result = mgr.get_composite_schedule(
            connector_id=1,
            transaction_id=99,
            start_time=start,
            duration=3600,
            connector_voltage=230.0,
        )

        assert len(result) == 1
        assert result[0].limit == pytest.approx(8.0)


class TestFindPeriodLimitUnsorted:
	"""_find_period_limit must return correct limits even when periods are not sorted."""

	def test_unsorted_periods_at_elapsed_zero(self):
		"""Periods delivered out of order should not confuse limit lookup."""
		from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager

		mgr = ChargingProfileManager()
		# Deliberately unsorted: high-start period first, 0-start period second
		periods = (
			ChargingSchedulePeriodData(start_period=3600, limit=8.0),
			ChargingSchedulePeriodData(start_period=0, limit=16.0),
		)
		schedule = ChargingScheduleData(
			charging_rate_unit=ChargingRateUnitType.amps,
			charging_schedule_period=periods,
		)
		profile = ChargingProfileData(
			charging_profile_id=1,
			stack_level=0,
			charging_profile_purpose=ChargingProfilePurposeType.charge_point_max_profile,
			charging_profile_kind=ChargingProfileKindType.absolute,
			charging_schedule=schedule,
		)
		mgr.set_profile(connector_id=1, profile=profile)

		now = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
		# elapsed = 0, so period at start_period=0 (16A) should apply
		limit = mgr.get_composite_limit(
			connector_id=1, transaction_id=None, now=now, connector_voltage=230.0,
		)
		assert limit == pytest.approx(16.0)

	def test_unsorted_periods_mid_schedule(self):
		"""Mid-schedule lookup with unsorted periods should pick the right step."""
		from chargeghost_evse.ocpp_adapter.charging_profile_manager import ChargingProfileManager

		mgr = ChargingProfileManager()
		start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
		# Reversed order: 1800s→4A then 0s→16A
		periods = (
			ChargingSchedulePeriodData(start_period=1800, limit=4.0),
			ChargingSchedulePeriodData(start_period=0, limit=16.0),
		)
		schedule = ChargingScheduleData(
			charging_rate_unit=ChargingRateUnitType.amps,
			charging_schedule_period=periods,
			start_schedule=start,
		)
		profile = ChargingProfileData(
			charging_profile_id=1,
			stack_level=0,
			charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
			charging_profile_kind=ChargingProfileKindType.absolute,
			charging_schedule=schedule,
		)
		mgr.set_profile(connector_id=1, profile=profile)

		# At elapsed=900s the 0→16A period applies; at elapsed=2000s the 1800→4A applies
		assert mgr.get_composite_limit(
			connector_id=1, transaction_id=None,
			now=start + timedelta(seconds=900), connector_voltage=230.0,
		) == pytest.approx(16.0)
		assert mgr.get_composite_limit(
			connector_id=1, transaction_id=None,
			now=start + timedelta(seconds=2000), connector_voltage=230.0,
		) == pytest.approx(4.0)
