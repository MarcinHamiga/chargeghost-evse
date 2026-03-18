import asyncio
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from ocpp.v16.enums import DiagnosticsStatus, FirmwareStatus, MessageTrigger, TriggerMessageStatus

from chargeghost_evse.ocpp_adapter.adapter import Adapter


def _make_adapter() -> Adapter:
    mock_conn = MagicMock()
    mock_conn.recv = AsyncMock()
    mock_conn.send = AsyncMock()
    return Adapter("CP_1", mock_conn)


@pytest.mark.asyncio
async def test_trigger_boot_notification_dispatches_asynchronously() -> None:
    adapter = _make_adapter()
    started = asyncio.Event()
    release = asyncio.Event()

    async def send_boot_notification() -> None:
        started.set()
        await release.wait()

    adapter.send_boot_notification = send_boot_notification

    result_task = asyncio.create_task(
        adapter.on_trigger_message(requested_message=MessageTrigger.boot_notification)
    )
    result = await asyncio.wait_for(result_task, timeout=0.1)

    assert result.status == TriggerMessageStatus.accepted
    await asyncio.wait_for(started.wait(), timeout=0.1)
    release.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_trigger_heartbeat_calls_sender() -> None:
    adapter = _make_adapter()
    called = asyncio.Event()

    async def send_heartbeat() -> None:
        called.set()

    adapter.send_heartbeat = send_heartbeat

    result = await asyncio.wait_for(
        adapter.on_trigger_message(requested_message=MessageTrigger.heartbeat),
        timeout=0.1,
    )

    assert result.status == TriggerMessageStatus.accepted
    await asyncio.wait_for(called.wait(), timeout=0.1)


@pytest.mark.asyncio
async def test_trigger_status_notification_for_known_connector() -> None:
    adapter = _make_adapter()
    adapter.known_connector_ids = [1]
    called = asyncio.Event()
    captured: dict[str, object] = {}

    async def send_status_notification(
        connector_id: int, error_code: str, status: str
    ) -> None:
        captured["args"] = (connector_id, error_code, status)
        called.set()

    adapter.send_status_notification = send_status_notification
    adapter.get_connector_status = MagicMock(return_value="Available")

    result = await asyncio.wait_for(
        adapter.on_trigger_message(
            requested_message=MessageTrigger.status_notification,
            connector_id=1,
        ),
        timeout=0.1,
    )

    assert result.status == TriggerMessageStatus.accepted
    await asyncio.wait_for(called.wait(), timeout=0.1)
    assert captured["args"] == (1, "NoError", "Available")


@pytest.mark.asyncio
async def test_trigger_status_notification_missing_connector_is_rejected() -> None:
    adapter = _make_adapter()
    adapter.known_connector_ids = [1]
    adapter.get_connector_status = MagicMock(return_value="Available")
    adapter.send_status_notification = AsyncMock()

    result = await asyncio.wait_for(
        adapter.on_trigger_message(requested_message=MessageTrigger.status_notification),
        timeout=0.1,
    )

    assert result.status == TriggerMessageStatus.rejected
    adapter.send_status_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_status_notification_unknown_connector_is_rejected() -> None:
    adapter = _make_adapter()
    adapter.known_connector_ids = [1]
    adapter.get_connector_status = MagicMock(return_value="Available")
    adapter.send_status_notification = AsyncMock()

    result = await asyncio.wait_for(
        adapter.on_trigger_message(
            requested_message=MessageTrigger.status_notification,
            connector_id=2,
        ),
        timeout=0.1,
    )

    assert result.status == TriggerMessageStatus.rejected
    adapter.send_status_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_status_notification_missing_callback_is_rejected() -> None:
    adapter = _make_adapter()
    adapter.known_connector_ids = [1]
    adapter.get_connector_status = None
    adapter.send_status_notification = AsyncMock()

    result = await asyncio.wait_for(
        adapter.on_trigger_message(
            requested_message=MessageTrigger.status_notification,
            connector_id=1,
        ),
        timeout=0.1,
    )

    assert result.status == TriggerMessageStatus.rejected
    adapter.send_status_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_meter_values_for_known_connector() -> None:
    adapter = _make_adapter()
    adapter.known_connector_ids = [1]
    called = asyncio.Event()
    captured: dict[str, object] = {}

    async def send_meter_values(
        connector_id: int, value: float, transaction_id: Optional[int]
    ) -> None:
        captured["args"] = (connector_id, value, transaction_id)
        called.set()

    adapter.send_meter_values = send_meter_values
    adapter.get_meter_snapshot = MagicMock(return_value=(123.5, 42))

    result = await asyncio.wait_for(
        adapter.on_trigger_message(
            requested_message=MessageTrigger.meter_values,
            connector_id=1,
        ),
        timeout=0.1,
    )

    assert result.status == TriggerMessageStatus.accepted
    await asyncio.wait_for(called.wait(), timeout=0.1)
    assert captured["args"] == (1, 123.5, 42)


@pytest.mark.asyncio
async def test_trigger_meter_values_missing_snapshot_is_rejected() -> None:
    adapter = _make_adapter()
    adapter.known_connector_ids = [1]
    adapter.get_meter_snapshot = MagicMock(return_value=None)
    adapter.send_meter_values = AsyncMock()

    result = await asyncio.wait_for(
        adapter.on_trigger_message(
            requested_message=MessageTrigger.meter_values,
            connector_id=1,
        ),
        timeout=0.1,
    )

    assert result.status == TriggerMessageStatus.rejected
    adapter.send_meter_values.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_meter_values_unknown_connector_is_rejected() -> None:
    adapter = _make_adapter()
    adapter.known_connector_ids = [1]
    adapter.get_meter_snapshot = MagicMock(return_value=(123.5, 42))
    adapter.send_meter_values = AsyncMock()

    result = await asyncio.wait_for(
        adapter.on_trigger_message(
            requested_message=MessageTrigger.meter_values,
            connector_id=2,
        ),
        timeout=0.1,
    )

    assert result.status == TriggerMessageStatus.rejected
    adapter.send_meter_values.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_meter_values_missing_callback_is_rejected() -> None:
    adapter = _make_adapter()
    adapter.known_connector_ids = [1]
    adapter.get_meter_snapshot = None
    adapter.send_meter_values = AsyncMock()

    result = await asyncio.wait_for(
        adapter.on_trigger_message(
            requested_message=MessageTrigger.meter_values,
            connector_id=1,
        ),
        timeout=0.1,
    )

    assert result.status == TriggerMessageStatus.rejected
    adapter.send_meter_values.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_diagnostics_status_notification_calls_sender() -> None:
    adapter = _make_adapter()
    called = asyncio.Event()
    captured: dict[str, object] = {}

    async def send_diagnostics_status_notification(status: DiagnosticsStatus) -> None:
        captured["status"] = status
        called.set()

    adapter.send_diagnostics_status_notification = send_diagnostics_status_notification

    result = await asyncio.wait_for(
        adapter.on_trigger_message(
            requested_message=MessageTrigger.diagnostics_status_notification
        ),
        timeout=0.1,
    )

    assert result.status == TriggerMessageStatus.accepted
    await asyncio.wait_for(called.wait(), timeout=0.1)
    assert captured["status"] == DiagnosticsStatus.idle


@pytest.mark.asyncio
async def test_trigger_firmware_status_notification_calls_sender() -> None:
    adapter = _make_adapter()
    called = asyncio.Event()
    captured: dict[str, object] = {}

    async def send_firmware_status_notification(status: FirmwareStatus) -> None:
        captured["status"] = status
        called.set()

    adapter.send_firmware_status_notification = send_firmware_status_notification

    result = await asyncio.wait_for(
        adapter.on_trigger_message(
            requested_message=MessageTrigger.firmware_status_notification
        ),
        timeout=0.1,
    )

    assert result.status == TriggerMessageStatus.accepted
    await asyncio.wait_for(called.wait(), timeout=0.1)
    assert captured["status"] == FirmwareStatus.idle


@pytest.mark.asyncio
async def test_trigger_unsupported_message_returns_not_implemented() -> None:
    adapter = _make_adapter()

    result = await asyncio.wait_for(
        adapter.on_trigger_message(requested_message="LogStatusNotification"),
        timeout=0.1,
    )

    assert result.status == TriggerMessageStatus.not_implemented
