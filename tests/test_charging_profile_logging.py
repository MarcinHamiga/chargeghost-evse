import logging
from datetime import datetime, timezone
from typing import Optional

from ocpp.v16.enums import (
	ChargingProfileKindType,
	ChargingProfilePurposeType,
	ChargingRateUnitType,
)

from chargeghost_evse.ocpp_adapter.charging_profile_manager import (
	ChargingProfileData,
	ChargingProfileManager,
	ChargingScheduleData,
	ChargingSchedulePeriodData,
)


def _make_profile(
	profile_id: int = 1,
	stack_level: int = 0,
	purpose: ChargingProfilePurposeType = ChargingProfilePurposeType.tx_default_profile,
	limit: float = 16.0,
	transaction_id: Optional[int] = None,
) -> ChargingProfileData:
	return ChargingProfileData(
		charging_profile_id=profile_id,
		stack_level=stack_level,
		charging_profile_purpose=purpose,
		charging_profile_kind=ChargingProfileKindType.absolute,
		charging_schedule=ChargingScheduleData(
			charging_rate_unit=ChargingRateUnitType.amps,
			charging_schedule_period=(
				ChargingSchedulePeriodData(start_period=0, limit=limit),
			),
		),
		transaction_id=transaction_id,
	)


class TestChargingProfileLogging:
	def test_set_profile_logs_info(self, caplog):
		mgr = ChargingProfileManager()
		profile = _make_profile(limit=16.0)
		with caplog.at_level(logging.INFO, logger="chargeghost.ocpp.profiles"):
			mgr.set_profile(connector_id=1, profile=profile)
		assert any("installed" in r.message.lower() for r in caplog.records)

	def test_clear_profiles_logs_info(self, caplog):
		mgr = ChargingProfileManager()
		profile = _make_profile()
		mgr.set_profile(connector_id=1, profile=profile)
		caplog.clear()
		with caplog.at_level(logging.INFO, logger="chargeghost.ocpp.profiles"):
			mgr.clear_profiles(profile_id=1)
		assert any("cleared" in r.message.lower() for r in caplog.records)

	def test_get_composite_limit_logs_debug_trace(self, caplog):
		mgr = ChargingProfileManager()
		profile = _make_profile(limit=16.0)
		mgr.set_profile(connector_id=1, profile=profile)
		with caplog.at_level(logging.DEBUG, logger="chargeghost.ocpp.profiles"):
			mgr.get_composite_limit(
				connector_id=1,
				transaction_id=None,
				now=datetime.now(timezone.utc),
				connector_voltage=230.0,
			)
		debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
		assert len(debug_records) >= 1
		# Verify structured extras
		trace = debug_records[0]
		assert hasattr(trace, 'evaluated_profiles')
		assert hasattr(trace, 'computed_limit_amps')

	def test_no_profiles_logs_debug(self, caplog):
		mgr = ChargingProfileManager()
		with caplog.at_level(logging.DEBUG, logger="chargeghost.ocpp.profiles"):
			result = mgr.get_composite_limit(
				connector_id=1,
				transaction_id=None,
				now=datetime.now(timezone.utc),
				connector_voltage=230.0,
			)
		assert result is None
		debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
		assert any("no active profile" in r.message.lower() for r in debug_records)
