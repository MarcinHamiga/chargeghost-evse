"""Tests for FirmwareManager diagnostics and firmware update flows."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from ocpp.v16.enums import DiagnosticsStatus, FirmwareStatus

from chargeghost_evse.ocpp_adapter.firmware_manager import (
	DiagnosticsUploadTask,
	FirmwareManager,
	FirmwareUpdateTask,
)


@pytest.fixture
def manager(tmp_path: Path) -> FirmwareManager:
	return FirmwareManager(log_dir=tmp_path / "logs")


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

class TestDiagnosticsUpload:
	def test_initial_state(self, manager: FirmwareManager):
		assert manager.diagnostics_task is None
		assert manager.get_diagnostics_status() == DiagnosticsStatus.idle

	def test_start_diagnostics_upload_creates_task(self, manager: FirmwareManager):
		manager.start_diagnostics_upload(location="ftp://server/diag")
		assert manager.diagnostics_task is not None
		assert manager.diagnostics_task.location == "ftp://server/diag"
		assert manager.diagnostics_task.status == DiagnosticsStatus.idle

	def test_start_diagnostics_upload_calls_callback(self, manager: FirmwareManager):
		received: list = []
		manager.set_diagnostics_upload_callback(lambda task: received.append(task))
		manager.start_diagnostics_upload(location="ftp://server/diag")
		assert len(received) == 1
		assert isinstance(received[0], DiagnosticsUploadTask)

	def test_start_diagnostics_upload_parses_valid_times(self, manager: FirmwareManager):
		manager.start_diagnostics_upload(
			location="ftp://x",
			start_time="2026-01-01T00:00:00Z",
			stop_time="2026-01-02T00:00:00Z",
		)
		assert manager.diagnostics_task.start_time is not None
		assert manager.diagnostics_task.stop_time is not None

	def test_start_diagnostics_upload_handles_invalid_times(self, manager: FirmwareManager):
		logs: list = []
		handler = logging.Handler()
		handler.emit = lambda record: logs.append(record.getMessage())
		manager.logger.addHandler(handler)
		manager.start_diagnostics_upload(
			location="ftp://x",
			start_time="not-a-date",
			stop_time="also-bad",
		)
		manager.logger.removeHandler(handler)
		assert manager.diagnostics_task is not None
		assert manager.diagnostics_task.start_time is None
		assert manager.diagnostics_task.stop_time is None

	def test_set_diagnostics_status(self, manager: FirmwareManager):
		manager.start_diagnostics_upload(location="ftp://x")
		manager.set_diagnostics_status(DiagnosticsStatus.uploading)
		assert manager.get_diagnostics_status() == DiagnosticsStatus.uploading

	def test_set_diagnostics_status_emits_event(self, manager: FirmwareManager):
		manager.start_diagnostics_upload(location="ftp://x")
		statuses: list = []

		def on_status(status):
			statuses.append(status)

		manager.on_diagnostics_status_changed.subscribe(on_status)
		manager.set_diagnostics_status(DiagnosticsStatus.uploaded)
		assert DiagnosticsStatus.uploaded in statuses

	def test_set_diagnostics_status_noop_without_task(self, manager: FirmwareManager):
		events: list = []
		manager.on_diagnostics_status_changed.subscribe(lambda status: events.append(status))
		manager.set_diagnostics_status(DiagnosticsStatus.uploading)
		assert len(events) == 0

	def test_cancel_diagnostics_upload(self, manager: FirmwareManager):
		manager.start_diagnostics_upload(location="ftp://x")
		manager.cancel_diagnostics_upload()
		assert manager.diagnostics_task is None

	def test_cancel_diagnostics_upload_noop_without_task(self, manager: FirmwareManager):
		manager.cancel_diagnostics_upload()  # Should not raise

	def test_simulate_diagnostics_upload_no_url(self, manager: FirmwareManager):
		"""Non-uploadable URL falls back to local file."""
		manager.start_diagnostics_upload(location="/local/path")
		loop = asyncio.new_event_loop()
		try:
			result = loop.run_until_complete(manager.simulate_diagnostics_upload())
		finally:
			loop.close()
		assert result is not None
		assert manager.get_diagnostics_status() == DiagnosticsStatus.uploaded

	def test_simulate_diagnostics_upload_no_task(self, manager: FirmwareManager):
		loop = asyncio.new_event_loop()
		try:
			result = loop.run_until_complete(manager.simulate_diagnostics_upload())
		finally:
			loop.close()
		assert result is None

	def test_simulate_diagnostics_upload_http_success(self, manager: FirmwareManager):
		manager.start_diagnostics_upload(location="http://server/upload")
		with patch.object(manager, "_upload_file", new=AsyncMock(return_value=True)):
			loop = asyncio.new_event_loop()
			try:
				result = loop.run_until_complete(manager.simulate_diagnostics_upload())
			finally:
				loop.close()
		assert result is not None
		assert manager.get_diagnostics_status() == DiagnosticsStatus.uploaded

	def test_simulate_diagnostics_upload_http_failure(self, manager: FirmwareManager):
		manager.start_diagnostics_upload(location="http://server/upload")
		with patch.object(manager, "_upload_file", new=AsyncMock(return_value=False)):
			loop = asyncio.new_event_loop()
			try:
				result = loop.run_until_complete(manager.simulate_diagnostics_upload())
			finally:
				loop.close()
		assert result is None
		assert manager.get_diagnostics_status() == DiagnosticsStatus.upload_failed


# ---------------------------------------------------------------------------
# Firmware update
# ---------------------------------------------------------------------------

class TestFirmwareUpdate:
	def test_initial_state(self, manager: FirmwareManager):
		assert manager.firmware_task is None
		assert manager.get_firmware_status() == FirmwareStatus.idle

	def test_start_firmware_update_creates_task(self, manager: FirmwareManager):
		manager.start_firmware_update(
			location="http://server/firmware.bin",
			retrieve_date="2026-01-01T00:00:00Z",
		)
		assert manager.firmware_task is not None
		assert manager.firmware_task.location == "http://server/firmware.bin"
		assert manager.firmware_task.file_name == "firmware.bin"
		assert manager.firmware_task.status == FirmwareStatus.idle

	def test_start_firmware_update_calls_callback(self, manager: FirmwareManager):
		received: list = []
		manager.set_firmware_update_callback(lambda task: received.append(task))
		manager.start_firmware_update(
			location="http://server/firmware.bin",
			retrieve_date="2026-01-01T00:00:00Z",
		)
		assert len(received) == 1
		assert isinstance(received[0], FirmwareUpdateTask)

	def test_start_firmware_update_invalid_date_falls_back_to_now(self, manager: FirmwareManager):
		logs: list = []
		handler = logging.Handler()
		handler.emit = lambda record: logs.append(record.getMessage())
		manager.logger.addHandler(handler)
		manager.start_firmware_update(
			location="http://server/firmware.bin",
			retrieve_date="not-a-date",
		)
		manager.logger.removeHandler(handler)
		assert manager.firmware_task is not None
		assert manager.firmware_task.retrieve_date is not None

	def test_get_retrieve_delay_seconds_is_zero_for_past_dates(self, manager: FirmwareManager):
		manager.start_firmware_update(
			location="http://server/firmware.bin",
			retrieve_date=(datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
		)
		assert manager.get_retrieve_delay_seconds() == pytest.approx(0.0)

	def test_wait_until_retrieve_date_sleeps_for_future_dates(self, manager: FirmwareManager):
		manager.start_firmware_update(
			location="http://server/firmware.bin",
			retrieve_date=(datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
		)
		with patch("chargeghost_evse.ocpp_adapter.firmware_manager.asyncio.sleep", new=AsyncMock()) as sleep_mock:
			loop = asyncio.new_event_loop()
			try:
				loop.run_until_complete(manager.wait_until_retrieve_date())
			finally:
				loop.close()
		sleep_mock.assert_awaited_once()
		assert sleep_mock.await_args.args[0] == pytest.approx(30.0, abs=1.0)

	def test_set_firmware_status(self, manager: FirmwareManager):
		manager.start_firmware_update(
			location="http://server/firmware.bin",
			retrieve_date="2026-01-01T00:00:00Z",
		)
		manager.set_firmware_status(FirmwareStatus.downloading)
		assert manager.get_firmware_status() == FirmwareStatus.downloading

	def test_set_firmware_status_emits_event(self, manager: FirmwareManager):
		manager.start_firmware_update(
			location="http://server/firmware.bin",
			retrieve_date="2026-01-01T00:00:00Z",
		)
		statuses: list = []

		def on_status(status):
			statuses.append(status)

		manager.on_firmware_status_changed.subscribe(on_status)
		manager.set_firmware_status(FirmwareStatus.installed)
		assert FirmwareStatus.installed in statuses

	def test_set_firmware_status_noop_without_task(self, manager: FirmwareManager):
		events: list = []
		manager.on_firmware_status_changed.subscribe(lambda status: events.append(status))
		manager.set_firmware_status(FirmwareStatus.downloading)
		assert len(events) == 0

	def test_cancel_firmware_update(self, manager: FirmwareManager):
		manager.start_firmware_update(
			location="http://server/firmware.bin",
			retrieve_date="2026-01-01T00:00:00Z",
		)
		manager.cancel_firmware_update()
		assert manager.firmware_task is None

	def test_cancel_firmware_update_noop_without_task(self, manager: FirmwareManager):
		manager.cancel_firmware_update()  # Should not raise

	def test_simulate_firmware_update_no_task(self, manager: FirmwareManager):
		loop = asyncio.new_event_loop()
		try:
			result = loop.run_until_complete(manager.simulate_firmware_update())
		finally:
			loop.close()
		assert result is False

	def test_simulate_firmware_update_full_flow(self, manager: FirmwareManager):
		manager.start_firmware_update(
			location="http://server/firmware.bin",
			retrieve_date="2026-01-01T00:00:00Z",
		)
		statuses_seen: list = []

		def on_status(status):
			statuses_seen.append(status)

		manager.on_firmware_status_changed.subscribe(on_status)

		loop = asyncio.new_event_loop()
		try:
			result = loop.run_until_complete(manager.simulate_firmware_update())
		finally:
			loop.close()

		assert result is True
		assert FirmwareStatus.downloading in statuses_seen
		assert FirmwareStatus.downloaded in statuses_seen
		assert FirmwareStatus.installing in statuses_seen
		assert FirmwareStatus.installed in statuses_seen
		assert manager.get_firmware_status() == FirmwareStatus.installed

	def test_simulate_firmware_update_sets_file_hash(self, manager: FirmwareManager):
		manager.start_firmware_update(
			location="http://server/firmware.bin",
			retrieve_date="2026-01-01T00:00:00Z",
		)
		loop = asyncio.new_event_loop()
		try:
			loop.run_until_complete(manager.simulate_firmware_update())
		finally:
			loop.close()
		assert manager.firmware_task is not None
		assert manager.firmware_task.file_hash is not None


# ---------------------------------------------------------------------------
# is_uploadable_url
# ---------------------------------------------------------------------------

class TestIsUploadableUrl:
	def test_http_is_uploadable(self, manager: FirmwareManager):
		assert manager._is_uploadable_url("http://server/file") is True

	def test_https_is_uploadable(self, manager: FirmwareManager):
		assert manager._is_uploadable_url("https://server/file") is True

	def test_ftp_is_uploadable(self, manager: FirmwareManager):
		assert manager._is_uploadable_url("ftp://server/file") is True

	def test_local_path_not_uploadable(self, manager: FirmwareManager):
		assert manager._is_uploadable_url("/local/path") is False

	def test_empty_string_not_uploadable(self, manager: FirmwareManager):
		assert manager._is_uploadable_url("") is False


# ---------------------------------------------------------------------------
# Log events
# ---------------------------------------------------------------------------

def test_log_event_emitted_on_start_diagnostics(manager: FirmwareManager):
	logs: list = []
	handler = logging.Handler()
	handler.emit = lambda record: logs.append(record.getMessage())
	handler.setLevel(logging.DEBUG)
	manager.logger.addHandler(handler)
	manager.logger.setLevel(logging.DEBUG)
	manager.start_diagnostics_upload(location="ftp://server/diag")
	manager.logger.removeHandler(handler)
	assert any("Diagnostics" in m for m in logs)


def test_log_event_emitted_on_start_firmware_update(manager: FirmwareManager):
	logs: list = []
	handler = logging.Handler()
	handler.emit = lambda record: logs.append(record.getMessage())
	handler.setLevel(logging.DEBUG)
	manager.logger.addHandler(handler)
	manager.logger.setLevel(logging.DEBUG)
	manager.start_firmware_update(
		location="http://server/firmware.bin",
		retrieve_date="2026-01-01T00:00:00Z",
	)
	manager.logger.removeHandler(handler)
	assert any("Firmware" in m for m in logs)


# ---------------------------------------------------------------------------
# Logging migration
# ---------------------------------------------------------------------------


class TestFirmwareManagerLogging:
	def test_uses_python_logger(self):
		from chargeghost_evse.ocpp_adapter.firmware_manager import FirmwareManager
		fm = FirmwareManager()
		assert hasattr(fm, 'logger')
		assert fm.logger.name == "chargeghost.ocpp.firmware"

	def test_no_on_log_event(self):
		from chargeghost_evse.ocpp_adapter.firmware_manager import FirmwareManager
		fm = FirmwareManager()
		assert not hasattr(fm, 'on_log')
