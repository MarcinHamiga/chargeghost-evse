import asyncio
import logging
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


class TestV201AdapterInit:
    def test_adapter_has_python_logger(self):
        adapter = _make_adapter()
        assert adapter.logger.name == "chargeghost.ocpp"
        assert adapter._tx_logger.name == "chargeghost.ocpp.tx"

    def test_adapter_has_transaction_manager(self):
        adapter = _make_adapter()
        assert adapter.transaction_manager is not None

    def test_adapter_has_base_events(self):
        adapter = _make_adapter()
        assert hasattr(adapter, "on_ocpp_message")
        assert hasattr(adapter, "on_registration_accepted")
        assert hasattr(adapter, "on_heartbeat_response")
        assert hasattr(adapter, "on_reset_requested")

    def test_adapter_has_injectable_callbacks(self):
        adapter = _make_adapter()
        assert adapter.get_connector_info is None
        assert adapter.get_connector_status is None
        assert adapter.get_meter_snapshot is None
        assert adapter.known_connector_ids == []

    def test_adapter_log_emits_to_python_logging(self, caplog):
        adapter = _make_adapter()
        with caplog.at_level(logging.DEBUG, logger="chargeghost.ocpp"):
            adapter._log("test v201 message")
        assert len(caplog.records) >= 1
        assert caplog.records[0].source == "ocpp"


class TestV201AdapterBootNotification:
    def test_boot_notification_sends_request(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.status = MagicMock(value="Accepted")
        mock_response.status.value = "Accepted"
        mock_response.interval = 300
        adapter.call = AsyncMock(return_value=mock_response)

        response = asyncio.run(adapter.send_boot_notification())

        adapter.call.assert_awaited_once()
        request = adapter.call.call_args[0][0]
        assert request.charging_station.vendor_name == "ChargeGhost"
        assert request.charging_station.model == "ChargeGhostV2"
        assert response == mock_response

    def test_boot_notification_accepted_updates_state(self):
        adapter = _make_adapter()
        from ocpp.v201.enums import RegistrationStatusEnumType

        mock_response = MagicMock()
        mock_response.status = RegistrationStatusEnumType.accepted
        mock_response.interval = 120
        adapter.call = AsyncMock(return_value=mock_response)

        asyncio.run(adapter.send_boot_notification())

        assert adapter.registration_status == RegistrationStatusEnumType.accepted
        assert adapter.heartbeat_interval == 120

    def test_boot_notification_pending_does_not_set_heartbeat(self):
        adapter = _make_adapter()
        from ocpp.v201.enums import RegistrationStatusEnumType

        mock_response = MagicMock()
        mock_response.status = RegistrationStatusEnumType.pending
        mock_response.interval = 0
        adapter.call = AsyncMock(return_value=mock_response)

        asyncio.run(adapter.send_boot_notification())

        assert adapter.heartbeat_interval == 0


class TestV201AdapterHeartbeat:
    def test_heartbeat_sends_request(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.current_time = "2026-01-01T00:00:00Z"
        adapter.call = AsyncMock(return_value=mock_response)

        response = asyncio.run(adapter.send_heartbeat())

        adapter.call.assert_awaited_once()
        assert response == mock_response


class TestV201AdapterStatusNotification:
    def test_status_notification_maps_available(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(
            adapter.send_status_notification(connector_id=1, status="Available")
        )

        request = adapter.call.call_args[0][0]
        from ocpp.v201.enums import ConnectorStatusEnumType

        assert request.connector_status == ConnectorStatusEnumType.available
        assert request.evse_id == 1

    def test_status_notification_maps_charging_to_occupied(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(adapter.send_status_notification(connector_id=2, status="Charging"))

        request = adapter.call.call_args[0][0]
        from ocpp.v201.enums import ConnectorStatusEnumType

        assert request.connector_status == ConnectorStatusEnumType.occupied
        assert request.evse_id == 2

    def test_status_notification_maps_faulted(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(adapter.send_status_notification(connector_id=0, status="Faulted"))

        request = adapter.call.call_args[0][0]
        from ocpp.v201.enums import ConnectorStatusEnumType

        assert request.connector_status == ConnectorStatusEnumType.faulted


class TestV201AdapterAuthorize:
    def test_authorize_sends_id_token(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.id_token_info = MagicMock()
        mock_response.id_token_info.status = MagicMock(value="Accepted")
        adapter.call = AsyncMock(return_value=mock_response)

        asyncio.run(adapter.send_authorize(id_tag="RFID_123"))

        request = adapter.call.call_args[0][0]
        assert request.id_token.id_token == "RFID_123"
        from ocpp.v201.enums import IdTokenEnumType

        assert request.id_token.type == IdTokenEnumType.central


class TestV201AdapterTransactionEvent:
    def test_transaction_event_started_creates_transaction(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        response, tx_id = asyncio.run(
            adapter.send_transaction_event_started(
                connector_id=1,
                id_tag="TAG1",
                meter_start=100,
                timestamp="2026-01-01T00:00:00Z",
            )
        )

        import uuid

        uuid.UUID(tx_id)
        request = adapter.call.call_args[0][0]
        from ocpp.v201.enums import TransactionEventEnumType

        assert request.event_type == TransactionEventEnumType.started
        assert request.transaction_info.transaction_id == tx_id
        assert request.seq_no == 0

    def test_transaction_event_started_with_meter_value(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        response, tx_id = asyncio.run(
            adapter.send_transaction_event_started(
                connector_id=1,
                id_tag="TAG1",
                meter_start=500,
                timestamp="2026-01-01T00:00:00Z",
            )
        )

        request = adapter.call.call_args[0][0]
        assert request.meter_value is not None
        assert len(request.meter_value) == 1
        assert request.meter_value[0].sampled_value[0].value == 500.0

    def test_transaction_event_started_with_reservation(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        response, tx_id = asyncio.run(
            adapter.send_transaction_event_started(
                connector_id=1,
                id_tag="TAG1",
                meter_start=0,
                timestamp="2026-01-01T00:00:00Z",
                reservation_id=42,
            )
        )

        request = adapter.call.call_args[0][0]
        assert request.reservation_id == 42

    def test_transaction_event_updated_increments_seq(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        _, tx_id = asyncio.run(
            adapter.send_transaction_event_started(
                connector_id=1,
                id_tag="TAG1",
                meter_start=0,
                timestamp="2026-01-01T00:00:00Z",
            )
        )

        asyncio.run(
            adapter.send_transaction_event_updated(
                connector_id=1,
                transaction_id=tx_id,
                timestamp="2026-01-01T00:01:00Z",
            )
        )

        request = adapter.call.call_args[0][0]
        from ocpp.v201.enums import TransactionEventEnumType

        assert request.event_type == TransactionEventEnumType.updated
        assert request.seq_no == 1

    def test_transaction_event_ended_ends_transaction(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        _, tx_id = asyncio.run(
            adapter.send_transaction_event_started(
                connector_id=1,
                id_tag="TAG1",
                meter_start=0,
                timestamp="2026-01-01T00:00:00Z",
            )
        )

        asyncio.run(
            adapter.send_transaction_event_ended(
                connector_id=1,
                transaction_id=tx_id,
                timestamp="2026-01-01T01:00:00Z",
                meter_stop=5000,
                reason="Local",
            )
        )

        request = adapter.call.call_args[0][0]
        from ocpp.v201.enums import TransactionEventEnumType

        assert request.event_type == TransactionEventEnumType.ended
        assert request.seq_no == 1
        assert request.transaction_info.transaction_id == tx_id

        assert adapter.transaction_manager.get_transaction_id(1) is None

    def test_transaction_event_ended_maps_stop_reason(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        _, tx_id = asyncio.run(
            adapter.send_transaction_event_started(
                connector_id=1,
                id_tag="TAG1",
                meter_start=0,
                timestamp="2026-01-01T00:00:00Z",
            )
        )

        asyncio.run(
            adapter.send_transaction_event_ended(
                connector_id=1,
                transaction_id=tx_id,
                timestamp="2026-01-01T01:00:00Z",
                meter_stop=5000,
                reason="SoftReset",
            )
        )

        request = adapter.call.call_args[0][0]
        from ocpp.v201.enums import ReasonEnumType

        assert request.transaction_info.stopped_reason == ReasonEnumType.reboot


class TestV201AdapterMeterValues:
    def test_meter_values_sends_request(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(
            adapter.send_meter_values(
                connector_id=1, value=1234.5, context="Sample.Periodic"
            )
        )

        request = adapter.call.call_args[0][0]
        assert request.evse_id == 1
        assert len(request.meter_value) == 1
        assert request.meter_value[0].sampled_value[0].value == 1234.5


class TestV201AdapterNotifyEvent:
    def test_notify_event_sends_request(self):
        from ocpp.v201.enums import EventNotificationEnumType, EventTriggerEnumType

        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(
            adapter.send_notify_event(
                connector_id=1,
                event_id=42,
                trigger=EventTriggerEnumType.alerting,
                actual_value="Faulted",
                event_notification_type=EventNotificationEnumType.custom_monitor,
                component_name="EVSE",
                variable_name="FaultState",
                severity=5,
            )
        )

        adapter.call.assert_awaited_once()
        request = adapter.call.call_args[0][0]
        assert request.seq_no == 42
        assert len(request.event_data) == 1
        assert request.event_data[0].trigger == EventTriggerEnumType.alerting
        assert (
            request.event_data[0].event_notification_type
            == EventNotificationEnumType.custom_monitor
        )

    def test_notify_event_with_transaction_id(self):
        from ocpp.v201.enums import EventNotificationEnumType, EventTriggerEnumType

        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(
            adapter.send_notify_event(
                connector_id=1,
                event_id=1,
                trigger=EventTriggerEnumType.alerting,
                actual_value="Faulted",
                event_notification_type=EventNotificationEnumType.custom_monitor,
                component_name="EVSE",
                variable_name="FaultState",
                transaction_id="tx_123",
            )
        )

        request = adapter.call.call_args[0][0]
        assert request.event_data[0].transaction_id == "tx_123"
