from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


def _set_adapter_available(app):
    app.state.controller.adapter = MagicMock()


def _make_ocpp_result(**kwargs):
    return SimpleNamespace(**kwargs)


class TestBootNotification:
    def test_boot_notification(self, client, app):
        _set_adapter_available(app)
        result = _make_ocpp_result(
            status="Accepted", current_time="2025-01-01T00:00:00Z", interval=300
        )
        with patch.object(
            type(app.state.runtime),
            "send_ocpp_raw",
            new_callable=AsyncMock,
            return_value=result,
        ):
            response = client.post("/api/v1/ocpp/boot-notification")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "BootNotification sent"
        assert data["details"]["status"] == "Accepted"


class TestStatusNotification:
    def test_status_notification(self, client, app):
        _set_adapter_available(app)
        with patch.object(
            type(app.state.runtime),
            "send_ocpp_raw",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send:
            response = client.post(
                "/api/v1/ocpp/status-notification",
                json={
                    "connector_id": 1,
                    "error_code": "NoError",
                    "status": "Available",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "StatusNotification sent"
        mock_send.assert_called_once_with(
            "send_status_notification", 1, "NoError", "Available"
        )


class TestStartTransaction:
    def test_start_transaction(self, client, app):
        _set_adapter_available(app)
        result = _make_ocpp_result(
            transaction_id=42, id_tag_info={"status": "Accepted"}
        )
        with patch.object(
            type(app.state.runtime),
            "send_ocpp_raw",
            new_callable=AsyncMock,
            return_value=result,
        ) as mock_send:
            response = client.post(
                "/api/v1/ocpp/start-transaction",
                json={
                    "connector_id": 1,
                    "id_tag": "TAG1",
                    "meter_start": 1000,
                    "timestamp": "2025-01-01T00:00:00Z",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "StartTransaction sent"
        assert data["details"]["transaction_id"] == 42
        mock_send.assert_called_once_with(
            "send_start_transaction", 1, "TAG1", 1000, "2025-01-01T00:00:00Z"
        )

    def test_start_transaction_defaults(self, client, app):
        _set_adapter_available(app)
        with patch.object(
            type(app.state.runtime),
            "send_ocpp_raw",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send:
            response = client.post(
                "/api/v1/ocpp/start-transaction",
                json={"connector_id": 1, "id_tag": "TAG1"},
            )

        assert response.status_code == 200
        assert response.json()["success"] is True
        args = mock_send.call_args[0]
        assert args[0] == "send_start_transaction"
        assert args[1] == 1
        assert args[2] == "TAG1"
        assert args[3] == 0


class TestStopTransaction:
    def test_stop_transaction(self, client, app):
        _set_adapter_available(app)
        result = _make_ocpp_result(id_tag_info={"status": "Accepted"})
        with patch.object(
            type(app.state.runtime),
            "send_ocpp_raw",
            new_callable=AsyncMock,
            return_value=result,
        ) as mock_send:
            response = client.post(
                "/api/v1/ocpp/stop-transaction",
                json={
                    "transaction_id": 42,
                    "meter_stop": 5000,
                    "timestamp": "2025-01-01T01:00:00Z",
                    "reason": "Local",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "StopTransaction sent"
        mock_send.assert_called_once_with(
            "send_stop_transaction", 5000, "2025-01-01T01:00:00Z", 42, "Local"
        )

    def test_stop_transaction_defaults(self, client, app):
        _set_adapter_available(app)
        with patch.object(
            type(app.state.runtime),
            "send_ocpp_raw",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send:
            response = client.post(
                "/api/v1/ocpp/stop-transaction",
                json={"transaction_id": 42},
            )

        assert response.status_code == 200
        assert response.json()["success"] is True
        args = mock_send.call_args[0]
        assert args[0] == "send_stop_transaction"
        assert args[1] == 0
        assert args[3] == 42
        assert args[4] is None


class TestMeterValues:
    def test_meter_values(self, client, app):
        _set_adapter_available(app)
        with patch.object(
            type(app.state.runtime),
            "send_ocpp_raw",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send:
            response = client.post(
                "/api/v1/ocpp/meter-values",
                json={"connector_id": 1, "value": 1234.5, "transaction_id": 42},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "MeterValues sent"
        mock_send.assert_called_once_with("send_meter_values", 1, 1234.5, 42)

    def test_meter_values_defaults(self, client, app):
        _set_adapter_available(app)
        with patch.object(
            type(app.state.runtime),
            "send_ocpp_raw",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send:
            response = client.post(
                "/api/v1/ocpp/meter-values",
                json={"connector_id": 1},
            )

        assert response.status_code == 200
        assert response.json()["success"] is True
        args = mock_send.call_args[0]
        assert args[0] == "send_meter_values"
        assert args[1] == 1
        assert args[2] == 0.0
        assert args[3] is None


class TestDataTransfer:
    def test_data_transfer(self, client, app):
        _set_adapter_available(app)
        result = _make_ocpp_result(status="Accepted", data="response-data")
        with patch.object(
            type(app.state.runtime),
            "send_ocpp_raw",
            new_callable=AsyncMock,
            return_value=result,
        ) as mock_send:
            response = client.post(
                "/api/v1/ocpp/data-transfer",
                json={
                    "vendor_id": "VendorX",
                    "message_id": "GetInfo",
                    "data": "payload",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "DataTransfer sent"
        assert data["details"]["status"] == "Accepted"
        mock_send.assert_called_once_with(
            "send_data_transfer", "VendorX", "GetInfo", "payload"
        )

    def test_data_transfer_minimal(self, client, app):
        _set_adapter_available(app)
        with patch.object(
            type(app.state.runtime),
            "send_ocpp_raw",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send:
            response = client.post(
                "/api/v1/ocpp/data-transfer",
                json={"vendor_id": "VendorX"},
            )

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_send.assert_called_once_with("send_data_transfer", "VendorX", None, None)


class TestDiagnosticsStatusNotification:
    def test_diagnostics_status_notification(self, client, app):
        _set_adapter_available(app)
        with patch.object(
            type(app.state.runtime),
            "send_ocpp_raw",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send:
            response = client.post(
                "/api/v1/ocpp/diagnostics-status-notification",
                json={"status": "Idle"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "DiagnosticsStatusNotification sent"
        mock_send.assert_called_once()

    def test_diagnostics_status_notification_rejects_invalid_status(self, client, app):
        _set_adapter_available(app)

        response = client.post(
            "/api/v1/ocpp/diagnostics-status-notification",
            json={"status": "NotARealStatus"},
        )

        assert response.status_code == 422


class TestFirmwareStatusNotification:
    def test_firmware_status_notification(self, client, app):
        _set_adapter_available(app)
        with patch.object(
            type(app.state.runtime),
            "send_ocpp_raw",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send:
            response = client.post(
                "/api/v1/ocpp/firmware-status-notification",
                json={"status": "Installed"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "FirmwareStatusNotification sent"
        mock_send.assert_called_once()

    def test_firmware_status_notification_rejects_invalid_status(self, client, app):
        _set_adapter_available(app)

        response = client.post(
            "/api/v1/ocpp/firmware-status-notification",
            json={"status": "NotARealStatus"},
        )

        assert response.status_code == 422


class TestSecurityEventNotification:
    def test_security_event_notification(self, client, app):
        _set_adapter_available(app)
        with patch.object(
            type(app.state.runtime),
            "send_ocpp_raw",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send:
            response = client.post(
                "/api/v1/ocpp/security-event-notification",
                json={
                    "event_type": "FirmwareUpdated",
                    "timestamp": "2025-01-01T00:00:00Z",
                    "tech_info": "v1.2.3",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "SecurityEventNotification sent"
        mock_send.assert_called_once()

    def test_security_event_notification_defaults(self, client, app):
        _set_adapter_available(app)
        with patch.object(
            type(app.state.runtime),
            "send_ocpp_raw",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send:
            response = client.post(
                "/api/v1/ocpp/security-event-notification",
                json={"event_type": "FirmwareUpdated"},
            )

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_send.assert_called_once()

    def test_security_event_notification_rejects_invalid_timestamp(self, client, app):
        _set_adapter_available(app)

        response = client.post(
            "/api/v1/ocpp/security-event-notification",
            json={"event_type": "FirmwareUpdated", "timestamp": "not-a-timestamp"},
        )

        assert response.status_code == 422


class TestAdapterUnavailable:
    def test_boot_notification_503(self, client, app):
        response = client.post("/api/v1/ocpp/boot-notification")
        assert response.status_code == 503
        assert response.json() == {"detail": "OCPP adapter not available"}

    def test_status_notification_503(self, client, app):
        response = client.post(
            "/api/v1/ocpp/status-notification",
            json={"connector_id": 1, "status": "Available"},
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "OCPP adapter not available"}

    def test_start_transaction_503(self, client, app):
        response = client.post(
            "/api/v1/ocpp/start-transaction",
            json={"connector_id": 1, "id_tag": "TAG1"},
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "OCPP adapter not available"}

    def test_stop_transaction_503(self, client, app):
        response = client.post(
            "/api/v1/ocpp/stop-transaction",
            json={"transaction_id": 1},
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "OCPP adapter not available"}

    def test_meter_values_503(self, client, app):
        response = client.post(
            "/api/v1/ocpp/meter-values",
            json={"connector_id": 1},
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "OCPP adapter not available"}

    def test_data_transfer_503(self, client, app):
        response = client.post(
            "/api/v1/ocpp/data-transfer",
            json={"vendor_id": "VendorX"},
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "OCPP adapter not available"}

    def test_diagnostics_status_notification_503(self, client, app):
        response = client.post(
            "/api/v1/ocpp/diagnostics-status-notification",
            json={"status": "Idle"},
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "OCPP adapter not available"}

    def test_firmware_status_notification_503(self, client, app):
        response = client.post(
            "/api/v1/ocpp/firmware-status-notification",
            json={"status": "Installed"},
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "OCPP adapter not available"}

    def test_security_event_notification_503(self, client, app):
        response = client.post(
            "/api/v1/ocpp/security-event-notification",
            json={"event_type": "FirmwareUpdated"},
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "OCPP adapter not available"}
