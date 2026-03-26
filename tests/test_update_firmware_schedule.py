import asyncio
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from ocpp.v16.enums import FirmwareStatus

from chargeghost_evse.ocpp_adapter.adapter import Adapter


def _make_adapter() -> Adapter:
	mock_conn = MagicMock()
	mock_conn.recv = AsyncMock()
	mock_conn.send = AsyncMock()
	return Adapter("CP_1", mock_conn)


@pytest.mark.asyncio
async def test_update_firmware_waits_until_retrieve_date_before_downloading() -> None:
	adapter = _make_adapter()
	started_wait = asyncio.Event()
	release_wait = asyncio.Event()
	adapter.send_firmware_status_notification = AsyncMock()

	async def wait_until_retrieve_date() -> None:
		started_wait.set()
		await release_wait.wait()

	adapter.firmware_manager.wait_until_retrieve_date = wait_until_retrieve_date
	adapter.firmware_manager.simulate_firmware_update = AsyncMock(return_value=True)

	response = await adapter.on_update_firmware(
		location="http://server/firmware.bin",
		retrieve_date="2099-01-01T00:00:00Z",
	)

	assert response.__class__.__name__ == "UpdateFirmware"
	await asyncio.wait_for(started_wait.wait(), timeout=0.1)
	adapter.send_firmware_status_notification.assert_not_awaited()

	release_wait.set()
	await asyncio.wait_for(adapter._firmware_task, timeout=0.1)

	assert adapter.send_firmware_status_notification.await_args_list == [
		call(FirmwareStatus.downloading),
		call(FirmwareStatus.installed),
	]


@pytest.mark.asyncio
async def test_update_firmware_immediate_retrieve_starts_download_right_away() -> None:
	adapter = _make_adapter()
	adapter.send_firmware_status_notification = AsyncMock()
	adapter.firmware_manager.wait_until_retrieve_date = AsyncMock()
	adapter.firmware_manager.simulate_firmware_update = AsyncMock(return_value=True)

	await adapter.on_update_firmware(
		location="http://server/firmware.bin",
		retrieve_date="2000-01-01T00:00:00Z",
	)
	await asyncio.wait_for(adapter._firmware_task, timeout=0.1)

	adapter.firmware_manager.wait_until_retrieve_date.assert_awaited_once()
	adapter.firmware_manager.simulate_firmware_update.assert_awaited_once()
	assert adapter.send_firmware_status_notification.await_args_list == [
		call(FirmwareStatus.downloading),
		call(FirmwareStatus.installed),
	]
