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
