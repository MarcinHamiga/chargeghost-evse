import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter


def _make_adapter(**overrides) -> V201Adapter:
    mock_conn = MagicMock()
    mock_conn.recv = AsyncMock()
    mock_conn.send = AsyncMock()
    kwargs = {
        "id": "CP_1",
        "connection": mock_conn,
        "command_queue": MagicMock(),
        "charge_point_model": "ChargeGhostV2",
        "charge_point_vendor": "ChargeGhost",
    }
    kwargs.update(overrides)
    return V201Adapter(**kwargs)


class TestSendSecurityEventNotification:
    def test_sends_failed_authentication_event(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        timestamp = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        asyncio.run(
            adapter.send_security_event_notification(
                event_type="FailedToAuthenticate",
                timestamp=timestamp,
                tech_info="id_tag=BAD_TAG, status=Invalid",
            )
        )

        adapter.call.assert_awaited_once()
        request = adapter.call.call_args[0][0]
        assert request.type == "FailedToAuthenticate"
        assert request.timestamp == "2025-06-15T12:00:00+00:00"
        assert request.tech_info == "id_tag=BAD_TAG, status=Invalid"

    def test_sends_firmware_tampering_event(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        timestamp = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        asyncio.run(
            adapter.send_security_event_notification(
                event_type="FirmwareTamperDetected",
                timestamp=timestamp,
                tech_info="checksum_mismatch",
            )
        )

        adapter.call.assert_awaited_once()
        request = adapter.call.call_args[0][0]
        assert request.type == "FirmwareTamperDetected"
        assert request.tech_info == "checksum_mismatch"

    def test_sends_reset_event(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        timestamp = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        asyncio.run(
            adapter.send_security_event_notification(
                event_type="ResetOrReboot",
                timestamp=timestamp,
            )
        )

        adapter.call.assert_awaited_once()
        request = adapter.call.call_args[0][0]
        assert request.type == "ResetOrReboot"
        assert request.tech_info is None

    def test_sends_configuration_change_event(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        timestamp = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        asyncio.run(
            adapter.send_security_event_notification(
                event_type="SettingSystemTime",
                timestamp=timestamp,
                tech_info="key=HeartbeatInterval, old=60, new=30",
            )
        )

        adapter.call.assert_awaited_once()
        request = adapter.call.call_args[0][0]
        assert request.type == "SettingSystemTime"
        assert request.tech_info == "key=HeartbeatInterval, old=60, new=30"

    def test_timestamp_is_iso_formatted(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        timestamp = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        asyncio.run(
            adapter.send_security_event_notification(
                event_type="SecurityLogCleared",
                timestamp=timestamp,
            )
        )

        request = adapter.call.call_args[0][0]
        assert request.timestamp == "2025-01-01T00:00:00+00:00"

    def test_returns_response_from_csms(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        timestamp = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        response = asyncio.run(
            adapter.send_security_event_notification(
                event_type="FailedToAuthenticate",
                timestamp=timestamp,
            )
        )

        assert response is mock_response
