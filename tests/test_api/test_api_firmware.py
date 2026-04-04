from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from chargeghost_evse.ocpp_adapter.firmware_manager import FirmwareManager


def _make_adapter(*, firmware_manager: MagicMock | None = None) -> MagicMock:
    if firmware_manager is None:
        firmware_manager = _make_firmware_manager()
    return MagicMock(firmware_manager=firmware_manager)


def _make_firmware_manager(
    *,
    status: str = "Idle",
    location: str | None = None,
    retrieve_date: datetime | None = None,
    file_name: str | None = None,
    file_hash: str | None = None,
) -> MagicMock:
    manager = MagicMock(spec=FirmwareManager)
    task = None
    if location is not None:
        task = SimpleNamespace(
            location=location,
            retrieve_date=retrieve_date,
            retries=0,
            retry_interval=0,
            file_name=file_name,
            file_hash=file_hash,
        )
    manager.firmware_task = task
    manager.diagnostics_task = None
    manager.get_firmware_status.return_value = SimpleNamespace(value=status)
    manager.get_diagnostics_status.return_value = SimpleNamespace(value="Idle")
    manager.start_firmware_update = MagicMock()
    manager.cancel_firmware_update = MagicMock()
    manager.start_diagnostics_upload = MagicMock()
    manager.cancel_diagnostics_upload = MagicMock()
    return manager


def _make_diagnostics_manager(
    *,
    fw_status: str = "Idle",
    diag_status: str = "Idle",
    location: str | None = None,
) -> MagicMock:
    manager = MagicMock(spec=FirmwareManager)
    fw_task = None
    diag_task = None
    if location is not None:
        diag_task = SimpleNamespace(
            location=location,
            start_time=None,
            stop_time=None,
            retries=0,
            retry_interval=0,
        )
    manager.firmware_task = fw_task
    manager.diagnostics_task = diag_task
    manager.get_firmware_status.return_value = SimpleNamespace(value=fw_status)
    manager.get_diagnostics_status.return_value = SimpleNamespace(value=diag_status)
    manager.start_firmware_update = MagicMock()
    manager.cancel_firmware_update = MagicMock()
    manager.start_diagnostics_upload = MagicMock()
    manager.cancel_diagnostics_upload = MagicMock()
    return manager


class TestFirmwareStatus:
    def test_get_firmware_status_idle(self, client, app):
        fm = _make_firmware_manager()
        app.state.controller.adapter = _make_adapter(firmware_manager=fm)

        response = client.get("/api/v1/firmware/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Idle"
        assert data["location"] is None
        assert data["retrieve_date"] is None
        assert data["retries"] == 0
        assert data["retry_interval"] == 0
        assert data["file_name"] is None
        assert data["file_hash"] is None

    def test_get_firmware_status_with_active_task(self, client, app):
        retrieve_date = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
        fm = _make_firmware_manager(
            status="Downloaded",
            location="https://example.com/fw.bin",
            retrieve_date=retrieve_date,
            file_name="fw.bin",
            file_hash="abc123def456",
        )
        app.state.controller.adapter = _make_adapter(firmware_manager=fm)

        response = client.get("/api/v1/firmware/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Downloaded"
        assert data["location"] == "https://example.com/fw.bin"
        assert data["retrieve_date"] is not None
        assert data["retries"] == 0
        assert data["retry_interval"] == 0
        assert data["file_name"] == "fw.bin"
        assert data["file_hash"] == "abc123def456"

    def test_get_firmware_status_503_when_adapter_unavailable(self, client, app):
        app.state.controller.adapter = None

        response = client.get("/api/v1/firmware/status")

        assert response.status_code == 503
        assert response.json() == {"detail": "OCPP adapter not available"}


class TestFirmwareTrigger:
    def test_trigger_firmware_update(self, client, app):
        fm = _make_firmware_manager()
        app.state.controller.adapter = _make_adapter(firmware_manager=fm)

        response = client.post(
            "/api/v1/firmware/trigger",
            json={
                "location": "https://example.com/fw.bin",
                "retrieve_date": "2026-05-01T12:00:00Z",
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            "success": True,
            "message": "Firmware update triggered",
            "details": None,
        }
        fm.start_firmware_update.assert_called_once_with(
            "https://example.com/fw.bin", "2026-05-01T12:00:00Z"
        )

    def test_trigger_firmware_update_without_retrieve_date(self, client, app):
        fm = _make_firmware_manager()
        app.state.controller.adapter = _make_adapter(firmware_manager=fm)

        response = client.post(
            "/api/v1/firmware/trigger",
            json={"location": "https://example.com/fw.bin"},
        )

        assert response.status_code == 200
        fm.start_firmware_update.assert_called_once_with(
            "https://example.com/fw.bin", ""
        )

    def test_trigger_firmware_update_503_when_adapter_unavailable(self, client, app):
        app.state.controller.adapter = None

        response = client.post(
            "/api/v1/firmware/trigger",
            json={"location": "https://example.com/fw.bin"},
        )

        assert response.status_code == 503


class TestFirmwareCancel:
    def test_cancel_firmware_update(self, client, app):
        fm = _make_firmware_manager()
        app.state.controller.adapter = _make_adapter(firmware_manager=fm)

        response = client.post("/api/v1/firmware/cancel")

        assert response.status_code == 200
        assert response.json() == {
            "success": True,
            "message": "Firmware update cancelled",
            "details": None,
        }
        fm.cancel_firmware_update.assert_called_once()

    def test_cancel_firmware_update_503_when_adapter_unavailable(self, client, app):
        app.state.controller.adapter = None

        response = client.post("/api/v1/firmware/cancel")

        assert response.status_code == 503


class TestDiagnosticsStatus:
    def test_get_diagnostics_status_idle(self, client, app):
        fm = _make_firmware_manager()
        app.state.controller.adapter = _make_adapter(firmware_manager=fm)

        response = client.get("/api/v1/diagnostics/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Idle"
        assert data["location"] is None
        assert data["start_time"] is None
        assert data["stop_time"] is None
        assert data["retries"] == 0
        assert data["retry_interval"] == 0

    def test_get_diagnostics_status_with_active_task(self, client, app):
        fm = _make_diagnostics_manager(
            diag_status="Uploading",
            location="https://example.com/diagnostics",
        )
        app.state.controller.adapter = _make_adapter(firmware_manager=fm)

        response = client.get("/api/v1/diagnostics/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Uploading"
        assert data["location"] == "https://example.com/diagnostics"
        assert data["start_time"] is None
        assert data["stop_time"] is None
        assert data["retries"] == 0
        assert data["retry_interval"] == 0

    def test_get_diagnostics_status_503_when_adapter_unavailable(self, client, app):
        app.state.controller.adapter = None

        response = client.get("/api/v1/diagnostics/status")

        assert response.status_code == 503
        assert response.json() == {"detail": "OCPP adapter not available"}


class TestDiagnosticsTrigger:
    def test_trigger_diagnostics_upload(self, client, app):
        fm = _make_firmware_manager()
        app.state.controller.adapter = _make_adapter(firmware_manager=fm)

        response = client.post(
            "/api/v1/diagnostics/trigger",
            json={
                "location": "https://example.com/diagnostics",
                "retries": 3,
                "retry_interval": 30,
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            "success": True,
            "message": "Diagnostics upload triggered",
            "details": None,
        }
        fm.start_diagnostics_upload.assert_called_once_with(
            "https://example.com/diagnostics", 3, 30
        )

    def test_trigger_diagnostics_upload_defaults(self, client, app):
        fm = _make_firmware_manager()
        app.state.controller.adapter = _make_adapter(firmware_manager=fm)

        response = client.post(
            "/api/v1/diagnostics/trigger",
            json={"location": "https://example.com/diagnostics"},
        )

        assert response.status_code == 200
        fm.start_diagnostics_upload.assert_called_once_with(
            "https://example.com/diagnostics", 0, 0
        )

    def test_trigger_diagnostics_upload_503_when_adapter_unavailable(self, client, app):
        app.state.controller.adapter = None

        response = client.post(
            "/api/v1/diagnostics/trigger",
            json={"location": "https://example.com/diagnostics"},
        )

        assert response.status_code == 503


class TestDiagnosticsCancel:
    def test_cancel_diagnostics_upload(self, client, app):
        fm = _make_firmware_manager()
        app.state.controller.adapter = _make_adapter(firmware_manager=fm)

        response = client.post("/api/v1/diagnostics/cancel")

        assert response.status_code == 200
        assert response.json() == {
            "success": True,
            "message": "Diagnostics upload cancelled",
            "details": None,
        }
        fm.cancel_diagnostics_upload.assert_called_once()

    def test_cancel_diagnostics_upload_503_when_adapter_unavailable(self, client, app):
        app.state.controller.adapter = None

        response = client.post("/api/v1/diagnostics/cancel")

        assert response.status_code == 503
