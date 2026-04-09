import asyncio
from unittest.mock import AsyncMock, MagicMock

from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter
from ocpp.v201.enums import LogEnumType, LogStatusEnumType, UploadLogStatusEnumType


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


class TestOnGetLog:
    def test_diagnostic_log_accepted(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        result = asyncio.run(
            adapter.on_get_log(
                log=MagicMock(),
                log_type=LogEnumType.diagnostics_log,
                request_id=42,
            )
        )

        assert result.status == LogStatusEnumType.accepted

    def test_security_log_accepted(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        result = asyncio.run(
            adapter.on_get_log(
                log=MagicMock(),
                log_type=LogEnumType.security_log,
                request_id=7,
            )
        )

        assert result.status == LogStatusEnumType.accepted

    def test_log_type_as_string(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        result = asyncio.run(
            adapter.on_get_log(
                log=MagicMock(),
                log_type="DiagnosticsLog",
                request_id=1,
            )
        )

        assert result.status == LogStatusEnumType.accepted

    def test_invalid_log_type_rejected(self):
        adapter = _make_adapter()

        result = asyncio.run(
            adapter.on_get_log(
                log=MagicMock(),
                log_type="InvalidLogType",
                request_id=99,
            )
        )

        assert result.status == LogStatusEnumType.rejected
        assert result.status_info is not None
        assert result.status_info.reason_code == "InvalidType"

    def test_sends_uploading_notification_immediately(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        asyncio.run(
            adapter.on_get_log(
                log=MagicMock(),
                log_type=LogEnumType.diagnostics_log,
                request_id=10,
            )
        )

        assert adapter.call.call_count >= 1
        first_call = adapter.call.call_args_list[0]
        request = first_call[0][0]
        assert request.status == UploadLogStatusEnumType.uploading
        assert request.request_id == 10

    def test_cancels_previous_log_task(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        async def _run():
            await adapter.on_get_log(
                log=MagicMock(),
                log_type=LogEnumType.security_log,
                request_id=1,
            )
            first_task = adapter._log_task
            assert first_task is not None

            await adapter.on_get_log(
                log=MagicMock(),
                log_type=LogEnumType.diagnostics_log,
                request_id=2,
            )

            assert first_task is not adapter._log_task

        asyncio.run(_run())

    def test_background_task_sends_uploaded(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        async def _run():
            await adapter.on_get_log(
                log=MagicMock(),
                log_type=LogEnumType.diagnostics_log,
                request_id=5,
            )
            await asyncio.sleep(0.3)

        asyncio.run(_run())

        uploading_calls = [
            c
            for c in adapter.call.call_args_list
            if c[0][0].status == UploadLogStatusEnumType.uploading
        ]
        uploaded_calls = [
            c
            for c in adapter.call.call_args_list
            if c[0][0].status == UploadLogStatusEnumType.uploaded
        ]
        assert len(uploading_calls) == 1
        assert len(uploaded_calls) == 1

        uploaded_call = uploaded_calls[0]
        assert uploaded_call[0][0].request_id == 5


class TestSendLogStatusNotification:
    def test_sends_notification_with_status(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        response = asyncio.run(
            adapter.send_log_status_notification(
                status=UploadLogStatusEnumType.uploading,
                request_id=42,
            )
        )

        adapter.call.assert_awaited_once()
        request = adapter.call.call_args[0][0]
        assert request.status == UploadLogStatusEnumType.uploading
        assert request.request_id == 42
        assert response == mock_response

    def test_sends_notification_without_request_id(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        asyncio.run(
            adapter.send_log_status_notification(
                status=UploadLogStatusEnumType.idle,
                request_id=None,
            )
        )

        request = adapter.call.call_args[0][0]
        assert request.status == UploadLogStatusEnumType.idle
        assert request.request_id is None
