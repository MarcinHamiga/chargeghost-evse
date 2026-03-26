import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from ocpp.exceptions import PropertyConstraintViolationError
from ocpp.messages import Call, unpack
from ocpp.v16.enums import (
    ChargingProfileKindType,
    ChargingProfilePurposeType,
    ChargingRateUnitType,
)

from chargeghost_evse.ocpp_adapter.adapter import Adapter
from chargeghost_evse.ocpp_adapter.charging_profile_manager import (
    ChargingProfileData,
    ChargingScheduleData,
    ChargingSchedulePeriodData,
)


def _make_adapter() -> Adapter:
    mock_conn = MagicMock()
    mock_conn.recv = AsyncMock()
    mock_conn.send = AsyncMock()
    adapter = Adapter("CP_1", mock_conn)
    adapter.known_connector_ids = [1]
    adapter.get_connector_info = MagicMock(return_value=(230.0, 1))
    return adapter


def _make_profile_payload(
    *,
    purpose: str = "TxProfile",
    profile_id: int = 1,
) -> dict:
    return {
        "chargingProfileId": profile_id,
        "stackLevel": 1,
        "chargingProfilePurpose": purpose,
        "chargingProfileKind": "Relative",
        "transactionId": 77,
        "chargingSchedule": {
            "chargingRateUnit": "A",
            "chargingSchedulePeriod": [
                {
                    "startPeriod": 0,
                    "limit": 16.0,
                }
            ],
        },
    }


async def _dispatch_call(adapter: Adapter, action: str, payload: dict):
    adapter._send = AsyncMock()
    await adapter._handle_call(Call("msg-1", action, payload))
    assert adapter._send.await_count == 1
    raw_response = adapter._send.await_args.args[0]
    return unpack(raw_response)


def test_set_charging_profile_invalid_connector_returns_call_error() -> None:
    adapter = _make_adapter()

    response = asyncio.run(
        _dispatch_call(
            adapter,
            "SetChargingProfile",
            {
                "connectorId": 2,
                "csChargingProfiles": _make_profile_payload(),
            },
        )
    )

    assert response.error_code == "PropertyConstraintViolation"
    assert response.error_details["field"] == "connectorId"


def test_set_charging_profile_missing_tx_id_returns_call_error() -> None:
    adapter = _make_adapter()
    payload = _make_profile_payload()
    del payload["transactionId"]

    response = asyncio.run(
        _dispatch_call(
            adapter,
            "SetChargingProfile",
            {
                "connectorId": 1,
                "csChargingProfiles": payload,
            },
        )
    )

    assert response.error_code == "PropertyConstraintViolation"
    assert response.error_details["cause"] == "tx_profile_missing_transaction_id"


def test_set_charging_profile_direct_invalid_profile_raises_property_constraint() -> None:
    adapter = _make_adapter()

    with pytest.raises(PropertyConstraintViolationError):
        asyncio.run(
            adapter.on_set_charging_profile(
                connector_id=1,
                cs_charging_profiles={
                    "charging_profile_id": 1,
                    "stack_level": 1,
                    "charging_profile_purpose": "TxProfile",
                },
            )
        )


def test_clear_charging_profile_invalid_purpose_raises_property_constraint() -> None:
    adapter = _make_adapter()

    with pytest.raises(PropertyConstraintViolationError):
        asyncio.run(
            adapter.on_clear_charging_profile(
                connector_id=1,
                charging_profile_purpose="BadPurpose",
            )
        )


def test_get_composite_schedule_invalid_connector_raises_property_constraint() -> None:
    adapter = _make_adapter()

    with pytest.raises(PropertyConstraintViolationError):
        asyncio.run(
            adapter.on_get_composite_schedule(
                connector_id=0,
                duration=60,
            )
        )


def test_get_composite_schedule_invalid_rate_unit_raises_property_constraint() -> None:
    adapter = _make_adapter()

    with pytest.raises(PropertyConstraintViolationError):
        asyncio.run(
            adapter.on_get_composite_schedule(
                connector_id=1,
                duration=60,
                charging_rate_unit="kW",
            )
        )


def test_get_composite_schedule_valid_request_still_succeeds() -> None:
    adapter = _make_adapter()
    now = datetime.now(timezone.utc)
    profile = ChargingProfileData(
        charging_profile_id=1,
        stack_level=1,
        charging_profile_purpose=ChargingProfilePurposeType.tx_default_profile,
        charging_profile_kind=ChargingProfileKindType.absolute,
        charging_schedule=ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType.amps,
            charging_schedule_period=(
                ChargingSchedulePeriodData(start_period=0, limit=16.0),
            ),
            start_schedule=now,
        ),
    )
    assert adapter.charging_profile_manager.set_profile(1, profile) is None

    response = asyncio.run(
        adapter.on_get_composite_schedule(
            connector_id=1,
            duration=60,
            charging_rate_unit="A",
        )
    )

    assert response.status == "Accepted"
    assert response.charging_schedule["chargingRateUnit"] == ChargingRateUnitType.amps
