"""
Tests for OCPP 1.6J compliant charging profile validation.

These tests verify that charging profiles are validated according to
OCPP 1.6J specification requirements based on profile Kind.
"""

from datetime import datetime, timezone

from ocpp.v16.enums import (
	ChargingProfileKindType,
	ChargingProfilePurposeType,
	ChargingRateUnitType,
	RecurrencyKind,
)

from chargeghost_evse.ocpp_adapter.adapter import validate_charging_profile
from chargeghost_evse.ocpp_adapter.charging_profile_manager import (
	ChargingProfileData,
	ChargingScheduleData,
	ChargingSchedulePeriodData,
)


def _make_profile(
	kind: ChargingProfileKindType,
	start_schedule: datetime | None = None,
	recurrency_kind: RecurrencyKind | None = None,
) -> ChargingProfileData:
	"""Create a minimal valid ChargingProfileData for testing."""
	period = ChargingSchedulePeriodData(start_period=0, limit=16.0)
	schedule = ChargingScheduleData(
		charging_rate_unit=ChargingRateUnitType.amps,
		charging_schedule_period=(period,),
		start_schedule=start_schedule,
	)
	return ChargingProfileData(
		charging_profile_id=1,
		stack_level=1,
		charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
		charging_profile_kind=kind,
		charging_schedule=schedule,
		recurrency_kind=recurrency_kind,
	)


class TestValidateChargingProfileRelative:
	"""Relative profiles have no Kind-specific requirements."""

	def test_relative_without_start_schedule_is_valid(self):
		profile = _make_profile(kind=ChargingProfileKindType.relative)
		assert validate_charging_profile(profile) is None

	def test_relative_with_start_schedule_is_valid(self):
		profile = _make_profile(
			kind=ChargingProfileKindType.relative,
			start_schedule=datetime(2025, 1, 1, tzinfo=timezone.utc),
		)
		assert validate_charging_profile(profile) is None


class TestValidateChargingProfileAbsolute:
	"""Absolute profiles require startSchedule per OCPP 1.6J."""

	def test_absolute_with_start_schedule_is_valid(self):
		profile = _make_profile(
			kind=ChargingProfileKindType.absolute,
			start_schedule=datetime(2025, 1, 1, tzinfo=timezone.utc),
		)
		assert validate_charging_profile(profile) is None

	def test_absolute_without_start_schedule_is_rejected(self):
		profile = _make_profile(kind=ChargingProfileKindType.absolute)
		error = validate_charging_profile(profile)
		assert error == "absolute_missing_start_schedule"


class TestValidateChargingProfileRecurring:
	"""Recurring profiles require startSchedule AND recurrencyKind per OCPP 1.6J."""

	def test_recurring_with_all_required_fields_is_valid(self):
		profile = _make_profile(
			kind=ChargingProfileKindType.recurring,
			start_schedule=datetime(2025, 1, 1, tzinfo=timezone.utc),
			recurrency_kind=RecurrencyKind.daily,
		)
		assert validate_charging_profile(profile) is None

	def test_recurring_with_weekly_recurrency_is_valid(self):
		profile = _make_profile(
			kind=ChargingProfileKindType.recurring,
			start_schedule=datetime(2025, 1, 1, tzinfo=timezone.utc),
			recurrency_kind=RecurrencyKind.weekly,
		)
		assert validate_charging_profile(profile) is None

	def test_recurring_without_start_schedule_is_rejected(self):
		profile = _make_profile(
			kind=ChargingProfileKindType.recurring,
			recurrency_kind=RecurrencyKind.daily,
		)
		error = validate_charging_profile(profile)
		assert error == "recurring_missing_start_schedule"

	def test_recurring_without_recurrency_kind_is_rejected(self):
		profile = _make_profile(
			kind=ChargingProfileKindType.recurring,
			start_schedule=datetime(2025, 1, 1, tzinfo=timezone.utc),
		)
		error = validate_charging_profile(profile)
		assert error == "recurring_missing_recurrency_kind"

	def test_recurring_without_any_required_fields_is_rejected(self):
		profile = _make_profile(kind=ChargingProfileKindType.recurring)
		error = validate_charging_profile(profile)
		assert error == "recurring_missing_start_schedule"
