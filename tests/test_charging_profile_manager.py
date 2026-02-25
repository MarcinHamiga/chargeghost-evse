from datetime import datetime
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

    def test_schedule_default_period_list_is_not_shared(self):
        s1 = ChargingScheduleData(charging_rate_unit=ChargingRateUnitType.amps)
        s2 = ChargingScheduleData(charging_rate_unit=ChargingRateUnitType.amps)
        s1.charging_schedule_period.append(
            ChargingSchedulePeriodData(start_period=0, limit=16.0)
        )
        assert s2.charging_schedule_period == []


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
