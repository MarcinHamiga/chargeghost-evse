from datetime import datetime, timedelta, timezone

from ocpp.v201.enums import (
    ChargingProfileKindEnumType,
    ChargingProfilePurposeEnumType,
    ChargingRateUnitEnumType,
    RecurrencyKindEnumType,
)

from chargeghost_evse.ocpp_adapter.charging_profile_manager_v201 import (
    ChargingProfileDataV201,
    ChargingProfileManagerV201,
    ChargingScheduleDataV201,
    ChargingSchedulePeriodDataV201,
)


def _make_schedule(
    sched_id: int = 1,
    unit: ChargingRateUnitEnumType = ChargingRateUnitEnumType.amps,
    periods: tuple = (),
    start_schedule: datetime = None,
    duration: int = None,
    min_charging_rate: float = None,
) -> ChargingScheduleDataV201:
    return ChargingScheduleDataV201(
        id=sched_id,
        charging_rate_unit=unit,
        charging_schedule_period=periods,
        start_schedule=start_schedule,
        duration=duration,
        min_charging_rate=min_charging_rate,
    )


def _make_profile(
    profile_id: int = 1,
    stack_level: int = 0,
    purpose: ChargingProfilePurposeEnumType = ChargingProfilePurposeEnumType.tx_default_profile,
    kind: ChargingProfileKindEnumType = ChargingProfileKindEnumType.relative,
    limit: float = 16.0,
    transaction_id: str = None,
    unit: ChargingRateUnitEnumType = ChargingRateUnitEnumType.amps,
    num_periods: int = 1,
    recurrency_kind: RecurrencyKindEnumType = None,
    valid_from: datetime = None,
    valid_to: datetime = None,
) -> ChargingProfileDataV201:
    periods = tuple(
        ChargingSchedulePeriodDataV201(start_period=i * 100, limit=limit)
        for i in range(num_periods)
    )
    sched = _make_schedule(
        sched_id=1,
        unit=unit,
        periods=periods,
    )
    return ChargingProfileDataV201(
        charging_profile_id=profile_id,
        stack_level=stack_level,
        charging_profile_purpose=purpose,
        charging_profile_kind=kind,
        charging_schedules=(sched,),
        transaction_id=transaction_id,
        recurrency_kind=recurrency_kind,
        valid_from=valid_from,
        valid_to=valid_to,
    )


class TestChargingProfileV201Dataclass:
    def test_period_creation(self):
        period = ChargingSchedulePeriodDataV201(
            start_period=0, limit=16.0, number_phases=1
        )
        assert period.start_period == 0
        assert period.limit == 16.0
        assert period.number_phases == 1

    def test_period_default_phases(self):
        period = ChargingSchedulePeriodDataV201(start_period=0, limit=16.0)
        assert period.number_phases is None

    def test_schedule_creation(self):
        period = ChargingSchedulePeriodDataV201(start_period=0, limit=16.0)
        sched = _make_schedule(
            sched_id=1,
            unit=ChargingRateUnitEnumType.amps,
            periods=(period,),
        )
        assert sched.charging_rate_unit == ChargingRateUnitEnumType.amps
        assert len(sched.charging_schedule_period) == 1
        assert sched.duration is None
        assert sched.start_schedule is None

    def test_profile_creation(self):
        period = ChargingSchedulePeriodDataV201(start_period=0, limit=16.0)
        sched = _make_schedule(
            sched_id=1,
            unit=ChargingRateUnitEnumType.amps,
            periods=(period,),
        )
        profile = ChargingProfileDataV201(
            charging_profile_id=1,
            stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeEnumType.tx_profile,
            charging_profile_kind=ChargingProfileKindEnumType.relative,
            charging_schedules=(sched,),
            transaction_id="42",
        )
        assert profile.charging_profile_id == 1
        assert profile.stack_level == 0
        assert profile.transaction_id == "42"
        assert profile.valid_from is None
        assert profile.valid_to is None
        assert profile.recurrency_kind is None


class TestChargingProfileManagerV201Storage:
    def test_set_and_retrieve_profile(self):
        mgr = ChargingProfileManagerV201()
        profile = _make_profile(profile_id=1)
        error = mgr.set_profile(evse_id=1, profile=profile)
        assert error is None
        profiles = mgr.get_profiles_for_purpose(
            ChargingProfilePurposeEnumType.tx_default_profile, evse_id=1
        )
        assert len(profiles) == 1
        assert profiles[0].charging_profile_id == 1

    def test_replace_same_id(self):
        mgr = ChargingProfileManagerV201()
        mgr.set_profile(evse_id=1, profile=_make_profile(profile_id=1, limit=16.0))
        mgr.set_profile(evse_id=1, profile=_make_profile(profile_id=1, limit=32.0))
        profiles = mgr.get_profiles_for_purpose(
            ChargingProfilePurposeEnumType.tx_default_profile, evse_id=1
        )
        assert len(profiles) == 1
        assert (
            profiles[0].charging_schedules[0].charging_schedule_period[0].limit == 32.0
        )

    def test_clear_by_id(self):
        mgr = ChargingProfileManagerV201()
        mgr.set_profile(evse_id=1, profile=_make_profile(profile_id=1))
        mgr.set_profile(evse_id=1, profile=_make_profile(profile_id=2))
        cleared = mgr.clear_profiles(profile_id=1)
        assert cleared == 1
        profiles = mgr.get_profiles_for_purpose(
            ChargingProfilePurposeEnumType.tx_default_profile, evse_id=1
        )
        assert len(profiles) == 1
        assert profiles[0].charging_profile_id == 2

    def test_clear_by_purpose(self):
        mgr = ChargingProfileManagerV201()
        mgr.set_profile(
            evse_id=1,
            profile=_make_profile(
                profile_id=1,
                purpose=ChargingProfilePurposeEnumType.tx_default_profile,
            ),
        )
        mgr.set_profile(
            evse_id=1,
            profile=_make_profile(
                profile_id=2,
                purpose=ChargingProfilePurposeEnumType.tx_profile,
                transaction_id="99",
            ),
        )
        cleared = mgr.clear_profiles(
            purpose=ChargingProfilePurposeEnumType.tx_default_profile
        )
        assert cleared == 1

    def test_clear_nothing_returns_zero(self):
        mgr = ChargingProfileManagerV201()
        cleared = mgr.clear_profiles(profile_id=999)
        assert cleared == 0

    def test_reject_exceeds_max_profiles(self):
        mgr = ChargingProfileManagerV201(max_profiles=2)
        mgr.set_profile(evse_id=1, profile=_make_profile(profile_id=1))
        mgr.set_profile(evse_id=1, profile=_make_profile(profile_id=2))
        error = mgr.set_profile(evse_id=1, profile=_make_profile(profile_id=3))
        assert error == "max_profiles_exceeded"

    def test_reject_stack_level_too_high(self):
        mgr = ChargingProfileManagerV201(max_stack_level=3)
        error = mgr.set_profile(evse_id=1, profile=_make_profile(stack_level=4))
        assert error == "stack_level_exceeded"

    def test_reject_too_many_periods(self):
        mgr = ChargingProfileManagerV201(max_schedule_periods=3)
        error = mgr.set_profile(evse_id=1, profile=_make_profile(num_periods=4))
        assert error == "too_many_periods"

    def test_tx_profile_none_transaction_id_is_valid(self):
        mgr = ChargingProfileManagerV201()
        profile = _make_profile(
            purpose=ChargingProfilePurposeEnumType.tx_profile,
            transaction_id=None,
        )
        error = mgr.set_profile(evse_id=1, profile=profile)
        assert error is None

    def test_evse_zero_applies_to_all(self):
        mgr = ChargingProfileManagerV201()
        mgr.set_profile(
            evse_id=0,
            profile=_make_profile(
                profile_id=1,
                purpose=ChargingProfilePurposeEnumType.charging_station_max_profile,
            ),
        )
        for evse_id in [1, 2, 3]:
            profiles = mgr.get_profiles_for_purpose(
                ChargingProfilePurposeEnumType.charging_station_max_profile,
                evse_id=evse_id,
            )
            assert len(profiles) == 1

    def test_highest_stack_level_returned_first(self):
        mgr = ChargingProfileManagerV201()
        mgr.set_profile(
            evse_id=1, profile=_make_profile(profile_id=1, stack_level=0, limit=10.0)
        )
        mgr.set_profile(
            evse_id=1, profile=_make_profile(profile_id=2, stack_level=2, limit=20.0)
        )
        mgr.set_profile(
            evse_id=1, profile=_make_profile(profile_id=3, stack_level=1, limit=15.0)
        )
        profiles = mgr.get_profiles_for_purpose(
            ChargingProfilePurposeEnumType.tx_default_profile, evse_id=1
        )
        assert profiles[0].stack_level == 2
        assert profiles[1].stack_level == 1
        assert profiles[2].stack_level == 0

    def test_external_constraints_purpose_accepted(self):
        mgr = ChargingProfileManagerV201()
        profile = _make_profile(
            profile_id=1,
            purpose=ChargingProfilePurposeEnumType.charging_station_external_constraints,
            limit=8.0,
        )
        error = mgr.set_profile(evse_id=1, profile=profile)
        assert error is None

    def test_charging_station_max_profile_accepted(self):
        mgr = ChargingProfileManagerV201()
        profile = _make_profile(
            profile_id=1,
            purpose=ChargingProfilePurposeEnumType.charging_station_max_profile,
            limit=32.0,
        )
        error = mgr.set_profile(evse_id=1, profile=profile)
        assert error is None


class TestV201CompositeLimit:
    def _mgr_with_profile(self, profile, evse_id=1):
        mgr = ChargingProfileManagerV201()
        mgr.set_profile(evse_id=evse_id, profile=profile)
        return mgr

    def test_no_profiles_returns_none(self):
        mgr = ChargingProfileManagerV201()
        result = mgr.get_composite_limit(
            evse_id=1,
            transaction_id=None,
            now=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            connector_voltage=230.0,
        )
        assert result is None

    def test_relative_profile_single_period(self):
        periods = (ChargingSchedulePeriodDataV201(start_period=0, limit=16.0),)
        sched = _make_schedule(
            sched_id=1,
            unit=ChargingRateUnitEnumType.amps,
            periods=periods,
        )
        profile = ChargingProfileDataV201(
            charging_profile_id=1,
            stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeEnumType.tx_profile,
            charging_profile_kind=ChargingProfileKindEnumType.relative,
            charging_schedules=(sched,),
            transaction_id="42",
        )
        mgr = self._mgr_with_profile(profile)
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = mgr.get_composite_limit(
            evse_id=1,
            transaction_id="42",
            now=now,
            connector_voltage=230.0,
            transaction_start=now,
        )
        assert result == 16.0

    def test_relative_profile_steps_through_periods(self):
        periods = (
            ChargingSchedulePeriodDataV201(start_period=0, limit=16.0),
            ChargingSchedulePeriodDataV201(start_period=3600, limit=8.0),
        )
        sched = _make_schedule(
            sched_id=1,
            unit=ChargingRateUnitEnumType.amps,
            periods=periods,
        )
        profile = ChargingProfileDataV201(
            charging_profile_id=1,
            stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeEnumType.tx_profile,
            charging_profile_kind=ChargingProfileKindEnumType.relative,
            charging_schedules=(sched,),
            transaction_id="42",
        )
        mgr = self._mgr_with_profile(profile)
        tx_start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        assert (
            mgr.get_composite_limit(
                evse_id=1,
                transaction_id="42",
                now=tx_start,
                connector_voltage=230.0,
                transaction_start=tx_start,
            )
            == 16.0
        )

        assert (
            mgr.get_composite_limit(
                evse_id=1,
                transaction_id="42",
                now=tx_start + timedelta(seconds=3601),
                connector_voltage=230.0,
                transaction_start=tx_start,
            )
            == 8.0
        )

    def test_watts_converted_to_amps(self):
        periods = (ChargingSchedulePeriodDataV201(start_period=0, limit=3680.0),)
        sched = _make_schedule(
            sched_id=1,
            unit=ChargingRateUnitEnumType.watts,
            periods=periods,
        )
        profile = ChargingProfileDataV201(
            charging_profile_id=1,
            stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeEnumType.tx_default_profile,
            charging_profile_kind=ChargingProfileKindEnumType.relative,
            charging_schedules=(sched,),
        )
        mgr = self._mgr_with_profile(profile)
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = mgr.get_composite_limit(
            evse_id=1,
            transaction_id=None,
            now=now,
            connector_voltage=230.0,
            transaction_start=now,
            phases=1,
        )
        assert result == 16.0

    def test_most_restrictive_across_schedules(self):
        sched1_periods = (ChargingSchedulePeriodDataV201(start_period=0, limit=16.0),)
        sched2_periods = (ChargingSchedulePeriodDataV201(start_period=0, limit=8.0),)
        sched1 = _make_schedule(
            sched_id=1, unit=ChargingRateUnitEnumType.amps, periods=sched1_periods
        )
        sched2 = _make_schedule(
            sched_id=2, unit=ChargingRateUnitEnumType.amps, periods=sched2_periods
        )
        profile = ChargingProfileDataV201(
            charging_profile_id=1,
            stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeEnumType.charging_station_max_profile,
            charging_profile_kind=ChargingProfileKindEnumType.absolute,
            charging_schedules=(sched1, sched2),
        )
        mgr = ChargingProfileManagerV201()
        mgr.set_profile(evse_id=1, profile=profile)
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = mgr.get_composite_limit(
            evse_id=1,
            transaction_id=None,
            now=now,
            connector_voltage=230.0,
        )
        assert result == 8.0

    def test_tx_profile_takes_precedence_over_tx_default(self):
        mgr = ChargingProfileManagerV201()
        tx_default = _make_profile(
            profile_id=1,
            purpose=ChargingProfilePurposeEnumType.tx_default_profile,
            limit=16.0,
            stack_level=0,
        )
        tx = _make_profile(
            profile_id=2,
            purpose=ChargingProfilePurposeEnumType.tx_profile,
            limit=8.0,
            stack_level=0,
            transaction_id="42",
        )
        mgr.set_profile(evse_id=1, profile=tx_default)
        mgr.set_profile(evse_id=1, profile=tx)
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = mgr.get_composite_limit(
            evse_id=1,
            transaction_id="42",
            now=now,
            connector_voltage=230.0,
            transaction_start=now,
        )
        assert result == 8.0

    def test_external_constraints_is_grid_limit(self):
        mgr = ChargingProfileManagerV201()
        ext = _make_profile(
            profile_id=1,
            purpose=ChargingProfilePurposeEnumType.charging_station_external_constraints,
            limit=6.0,
            stack_level=0,
        )
        mgr.set_profile(evse_id=1, profile=ext)
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = mgr.get_composite_limit(
            evse_id=1,
            transaction_id=None,
            now=now,
            connector_voltage=230.0,
            transaction_start=now,
        )
        assert result == 6.0

    def test_tx_profile_not_used_for_different_transaction(self):
        mgr = ChargingProfileManagerV201()
        tx_default = _make_profile(
            profile_id=1,
            purpose=ChargingProfilePurposeEnumType.tx_default_profile,
            limit=16.0,
            stack_level=0,
        )
        tx = _make_profile(
            profile_id=2,
            purpose=ChargingProfilePurposeEnumType.tx_profile,
            limit=8.0,
            stack_level=0,
            transaction_id="42",
        )
        mgr.set_profile(evse_id=1, profile=tx_default)
        mgr.set_profile(evse_id=1, profile=tx)
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = mgr.get_composite_limit(
            evse_id=1,
            transaction_id="99",
            now=now,
            connector_voltage=230.0,
            transaction_start=now,
        )
        assert result == 16.0

    def test_tx_profile_none_transaction_id_matches(self):
        mgr = ChargingProfileManagerV201()
        tx = _make_profile(
            profile_id=1,
            purpose=ChargingProfilePurposeEnumType.tx_profile,
            limit=8.0,
            stack_level=0,
            transaction_id=None,
        )
        mgr.set_profile(evse_id=1, profile=tx)
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = mgr.get_composite_limit(
            evse_id=1,
            transaction_id=None,
            now=now,
            connector_voltage=230.0,
            transaction_start=now,
        )
        assert result == 8.0


class TestV201CompositeSchedule:
    def test_empty_returns_no_periods(self):
        mgr = ChargingProfileManagerV201()
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        periods = mgr.get_composite_schedule(
            evse_id=1,
            transaction_id=None,
            start_time=now,
            duration=3600,
            connector_voltage=230.0,
        )
        assert len(periods) == 0

    def test_single_period_schedule(self):
        periods = (ChargingSchedulePeriodDataV201(start_period=0, limit=16.0),)
        sched = _make_schedule(
            sched_id=1, unit=ChargingRateUnitEnumType.amps, periods=periods
        )
        profile = ChargingProfileDataV201(
            charging_profile_id=1,
            stack_level=0,
            charging_profile_purpose=ChargingProfilePurposeEnumType.tx_default_profile,
            charging_profile_kind=ChargingProfileKindEnumType.absolute,
            charging_schedules=(sched,),
        )
        mgr = ChargingProfileManagerV201()
        mgr.set_profile(evse_id=1, profile=profile)
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = mgr.get_composite_schedule(
            evse_id=1,
            transaction_id=None,
            start_time=now,
            duration=3600,
            connector_voltage=230.0,
        )
        assert len(result) == 1
        assert result[0].limit == 16.0


class TestV201FromOcppDict:
    def test_parse_profile(self):
        ocpp_dict = {
            "id": 1,
            "stack_level": 0,
            "charging_profile_purpose": "TxDefaultProfile",
            "charging_profile_kind": "Relative",
            "charging_schedule": [
                {
                    "id": 1,
                    "charging_rate_unit": "A",
                    "charging_schedule_period": [
                        {"start_period": 0, "limit": 16.0},
                        {"start_period": 3600, "limit": 8.0},
                    ],
                }
            ],
            "transaction_id": "42",
        }
        profile = ChargingProfileManagerV201.from_ocpp_dict(ocpp_dict)
        assert profile.charging_profile_id == 1
        assert profile.stack_level == 0
        assert (
            profile.charging_profile_purpose
            == ChargingProfilePurposeEnumType.tx_default_profile
        )
        assert profile.charging_profile_kind == ChargingProfileKindEnumType.relative
        assert len(profile.charging_schedules) == 1
        assert len(profile.charging_schedules[0].charging_schedule_period) == 2
        assert profile.transaction_id == "42"

    def test_parse_profile_with_validity_period(self):
        ocpp_dict = {
            "id": 1,
            "stack_level": 0,
            "charging_profile_purpose": "TxDefaultProfile",
            "charging_profile_kind": "Absolute",
            "charging_schedule": [
                {
                    "id": 1,
                    "charging_rate_unit": "A",
                    "charging_schedule_period": [{"start_period": 0, "limit": 16.0}],
                    "start_schedule": "2024-01-01T12:00:00+00:00",
                }
            ],
            "valid_from": "2024-01-01T00:00:00+00:00",
            "valid_to": "2024-12-31T23:59:59+00:00",
        }
        profile = ChargingProfileManagerV201.from_ocpp_dict(ocpp_dict)
        assert profile.valid_from is not None
        assert profile.valid_to is not None
        assert profile.charging_schedules[0].start_schedule is not None
