import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ocpp.v201.datatypes import FirmwareType
from ocpp.v201.enums import (
    FirmwareStatusEnumType,
    GenericStatusEnumType,
    PublishFirmwareStatusEnumType,
    UnpublishFirmwareStatusEnumType,
    UpdateFirmwareStatusEnumType,
)

from chargeghost_evse.ocpp_adapter.firmware_manager_v201 import (
    FirmwareManagerV201,
    FirmwareUpdateTaskV201,
    PublishFirmwareTask,
)


class _EventCollector:
    def __init__(self):
        self.events = []

    def on_event(self, **kwargs):
        self.events.append(kwargs)


def _make_manager() -> FirmwareManagerV201:
    return FirmwareManagerV201()


class TestFirmwareUpdateTaskV201:
    def test_default_values(self):
        task = FirmwareUpdateTaskV201(
            location="http://example.com/fw.bin",
            retrieve_date_time=datetime.now(timezone.utc),
        )
        assert task.location == "http://example.com/fw.bin"
        assert task.request_id == 0
        assert task.retries == 0
        assert task.retry_interval == 0
        assert task.status == FirmwareStatusEnumType.idle
        assert task.install_date_time is None
        assert task.signing_certificate is None
        assert task.signature is None
        assert task.file_name is None
        assert task.file_hash is None

    def test_with_all_fields(self):
        install_time = datetime.now(timezone.utc) + timedelta(hours=2)
        task = FirmwareUpdateTaskV201(
            location="http://example.com/fw.bin",
            retrieve_date_time=datetime.now(timezone.utc),
            request_id=42,
            retries=3,
            retry_interval=60,
            install_date_time=install_time,
            signing_certificate="cert_pem",
            signature="sig_data",
        )
        assert task.request_id == 42
        assert task.retries == 3
        assert task.install_date_time == install_time
        assert task.signing_certificate == "cert_pem"
        assert task.signature == "sig_data"


class TestPublishFirmwareTask:
    def test_default_values(self):
        task = PublishFirmwareTask(
            location="http://example.com/fw.bin",
            checksum="abc123",
        )
        assert task.location == "http://example.com/fw.bin"
        assert task.checksum == "abc123"
        assert task.request_id == 0
        assert task.status == PublishFirmwareStatusEnumType.idle


class TestFirmwareManagerV201:
    def test_initial_state(self):
        mgr = _make_manager()
        assert mgr.firmware_task is None
        assert mgr.publish_task is None
        assert mgr.get_firmware_status() == FirmwareStatusEnumType.idle
        assert mgr.get_publish_status() == PublishFirmwareStatusEnumType.idle

    def test_start_firmware_update(self):
        mgr = _make_manager()
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        mgr.start_firmware_update(
            location="http://example.com/fw.bin",
            retrieve_date_time=future_time.isoformat(),
            request_id=1,
            signing_certificate="cert",
            signature="sig",
        )
        assert mgr.firmware_task is not None
        assert mgr.firmware_task.location == "http://example.com/fw.bin"
        assert mgr.firmware_task.request_id == 1
        assert mgr.firmware_task.signing_certificate == "cert"
        assert mgr.firmware_task.signature == "sig"
        assert mgr.firmware_task.file_name == "fw.bin"

    def test_start_firmware_update_invalid_retrieve_date(self):
        mgr = _make_manager()
        mgr.start_firmware_update(
            location="http://example.com/fw.bin",
            retrieve_date_time="not-a-date",
            request_id=2,
        )
        assert mgr.firmware_task is not None
        task = mgr.firmware_task
        now = datetime.now(timezone.utc)
        assert abs((task.retrieve_date_time - now).total_seconds()) < 5

    def test_start_firmware_update_with_install_date(self):
        mgr = _make_manager()
        install = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        mgr.start_firmware_update(
            location="http://example.com/fw.bin",
            retrieve_date_time=datetime.now(timezone.utc).isoformat(),
            request_id=3,
            install_date_time=install,
        )
        assert mgr.firmware_task is not None
        assert mgr.firmware_task.install_date_time is not None

    def test_start_firmware_update_invalid_install_date(self):
        mgr = _make_manager()
        mgr.start_firmware_update(
            location="http://example.com/fw.bin",
            retrieve_date_time=datetime.now(timezone.utc).isoformat(),
            request_id=4,
            install_date_time="bad-date",
        )
        assert mgr.firmware_task is not None
        assert mgr.firmware_task.install_date_time is None

    def test_set_firmware_status(self):
        mgr = _make_manager()
        collector = _EventCollector()
        mgr.on_firmware_status_changed.subscribe(collector.on_event)

        mgr.start_firmware_update(
            location="http://example.com/fw.bin",
            retrieve_date_time=datetime.now(timezone.utc).isoformat(),
            request_id=1,
        )
        mgr.set_firmware_status(FirmwareStatusEnumType.download_scheduled)
        assert mgr.get_firmware_status() == FirmwareStatusEnumType.download_scheduled
        assert len(collector.events) == 1
        assert (
            collector.events[0]["status"] == FirmwareStatusEnumType.download_scheduled
        )

    def test_set_firmware_status_no_task(self):
        mgr = _make_manager()
        collector = _EventCollector()
        mgr.on_firmware_status_changed.subscribe(collector.on_event)
        mgr.set_firmware_status(FirmwareStatusEnumType.downloading)
        assert len(collector.events) == 0

    def test_cancel_firmware_update(self):
        mgr = _make_manager()
        mgr.start_firmware_update(
            location="http://example.com/fw.bin",
            retrieve_date_time=datetime.now(timezone.utc).isoformat(),
            request_id=1,
        )
        mgr.cancel_firmware_update()
        assert mgr.firmware_task is None
        assert mgr.get_firmware_status() == FirmwareStatusEnumType.idle

    def test_cancel_firmware_update_no_task(self):
        mgr = _make_manager()
        mgr.cancel_firmware_update()
        assert mgr.firmware_task is None

    def test_get_retrieve_delay_seconds_future(self):
        mgr = _make_manager()
        future = datetime.now(timezone.utc) + timedelta(seconds=60)
        mgr.start_firmware_update(
            location="http://example.com/fw.bin",
            retrieve_date_time=future.isoformat(),
            request_id=1,
        )
        delay = mgr.get_retrieve_delay_seconds()
        assert 55 < delay <= 60

    def test_get_retrieve_delay_seconds_past(self):
        mgr = _make_manager()
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        mgr.start_firmware_update(
            location="http://example.com/fw.bin",
            retrieve_date_time=past.isoformat(),
            request_id=1,
        )
        delay = mgr.get_retrieve_delay_seconds()
        assert delay == 0.0

    def test_get_retrieve_delay_seconds_no_task(self):
        mgr = _make_manager()
        assert mgr.get_retrieve_delay_seconds() == 0.0

    @pytest.mark.asyncio
    async def test_simulate_firmware_update_full_lifecycle(self):
        mgr = _make_manager()
        collector = _EventCollector()
        mgr.on_firmware_status_changed.subscribe(collector.on_event)

        mgr.start_firmware_update(
            location="http://example.com/fw.bin",
            retrieve_date_time=datetime.now(timezone.utc).isoformat(),
            request_id=1,
            signature="sig_data",
        )

        with patch(
            "chargeghost_evse.ocpp_adapter.firmware_manager_v201.asyncio.sleep"
        ) as mock_sleep:
            mock_sleep.return_value = asyncio.Future()
            mock_sleep.return_value.set_result(None)
            result = await mgr.simulate_firmware_update()

        assert result is True
        statuses = [e["status"] for e in collector.events]
        assert FirmwareStatusEnumType.download_scheduled in statuses
        assert FirmwareStatusEnumType.downloading in statuses
        assert FirmwareStatusEnumType.downloaded in statuses
        assert FirmwareStatusEnumType.signature_verified in statuses
        assert FirmwareStatusEnumType.install_scheduled in statuses
        assert FirmwareStatusEnumType.installing in statuses
        assert FirmwareStatusEnumType.installed in statuses

    @pytest.mark.asyncio
    async def test_simulate_firmware_update_no_signature(self):
        mgr = _make_manager()
        collector = _EventCollector()
        mgr.on_firmware_status_changed.subscribe(collector.on_event)

        mgr.start_firmware_update(
            location="http://example.com/fw.bin",
            retrieve_date_time=datetime.now(timezone.utc).isoformat(),
            request_id=1,
        )

        with patch(
            "chargeghost_evse.ocpp_adapter.firmware_manager_v201.asyncio.sleep"
        ) as mock_sleep:
            mock_sleep.return_value = asyncio.Future()
            mock_sleep.return_value.set_result(None)
            result = await mgr.simulate_firmware_update()

        assert result is True
        statuses = [e["status"] for e in collector.events]
        assert FirmwareStatusEnumType.signature_verified not in statuses

    @pytest.mark.asyncio
    async def test_simulate_firmware_update_no_task(self):
        mgr = _make_manager()
        result = await mgr.simulate_firmware_update()
        assert result is False

    @pytest.mark.asyncio
    async def test_wait_until_retrieve_date_past(self):
        mgr = _make_manager()
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        mgr.start_firmware_update(
            location="http://example.com/fw.bin",
            retrieve_date_time=past.isoformat(),
            request_id=1,
        )
        await mgr.wait_until_retrieve_date()


class TestPublishFirmware:
    def test_start_publish_firmware(self):
        mgr = _make_manager()
        mgr.start_publish_firmware(
            location="http://example.com/fw.bin",
            checksum="abc123",
            request_id=10,
        )
        assert mgr.publish_task is not None
        assert mgr.publish_task.location == "http://example.com/fw.bin"
        assert mgr.publish_task.checksum == "abc123"
        assert mgr.publish_task.request_id == 10

    def test_set_publish_status(self):
        mgr = _make_manager()
        collector = _EventCollector()
        mgr.on_publish_firmware_status_changed.subscribe(collector.on_event)

        mgr.start_publish_firmware(
            location="http://example.com/fw.bin",
            checksum="abc123",
            request_id=1,
        )
        mgr.set_publish_status(PublishFirmwareStatusEnumType.downloading)
        assert mgr.get_publish_status() == PublishFirmwareStatusEnumType.downloading
        assert len(collector.events) == 1

    def test_set_publish_status_no_task(self):
        mgr = _make_manager()
        collector = _EventCollector()
        mgr.on_publish_firmware_status_changed.subscribe(collector.on_event)
        mgr.set_publish_status(PublishFirmwareStatusEnumType.downloading)
        assert len(collector.events) == 0

    def test_unpublish_firmware(self):
        mgr = _make_manager()
        mgr.start_publish_firmware(
            location="http://example.com/fw.bin",
            checksum="abc123",
            request_id=1,
        )
        result = mgr.unpublish_firmware()
        assert result is True
        assert mgr.publish_task is None

    def test_unpublish_firmware_no_task(self):
        mgr = _make_manager()
        result = mgr.unpublish_firmware()
        assert result is False

    @pytest.mark.asyncio
    async def test_simulate_publish_firmware(self):
        mgr = _make_manager()
        collector = _EventCollector()
        mgr.on_publish_firmware_status_changed.subscribe(collector.on_event)

        mgr.start_publish_firmware(
            location="http://example.com/fw.bin",
            checksum="abc123",
            request_id=1,
        )

        with patch(
            "chargeghost_evse.ocpp_adapter.firmware_manager_v201.asyncio.sleep"
        ) as mock_sleep:
            mock_sleep.return_value = asyncio.Future()
            mock_sleep.return_value.set_result(None)
            result = await mgr.simulate_publish_firmware()

        assert result is True
        statuses = [e["status"] for e in collector.events]
        assert PublishFirmwareStatusEnumType.download_scheduled in statuses
        assert PublishFirmwareStatusEnumType.downloading in statuses
        assert PublishFirmwareStatusEnumType.downloaded in statuses
        assert PublishFirmwareStatusEnumType.published in statuses

    @pytest.mark.asyncio
    async def test_simulate_publish_firmware_no_task(self):
        mgr = _make_manager()
        result = await mgr.simulate_publish_firmware()
        assert result is False


class TestCallbacks:
    def test_firmware_update_callback(self):
        mgr = _make_manager()
        callback = MagicMock()
        mgr.set_firmware_update_callback(callback)

        mgr.start_firmware_update(
            location="http://example.com/fw.bin",
            retrieve_date_time=datetime.now(timezone.utc).isoformat(),
            request_id=1,
        )
        callback.assert_called_once()
        assert isinstance(callback.call_args[0][0], FirmwareUpdateTaskV201)

    def test_publish_firmware_callback(self):
        mgr = _make_manager()
        callback = MagicMock()
        mgr.set_publish_firmware_callback(callback)

        mgr.start_publish_firmware(
            location="http://example.com/fw.bin",
            checksum="abc123",
            request_id=1,
        )
        callback.assert_called_once()
        assert isinstance(callback.call_args[0][0], PublishFirmwareTask)
