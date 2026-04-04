import asyncio
import queue
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from chargeghost_evse.engine.reservation import Reservation
from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter
from ocpp.v201.datatypes import IdTokenType
from ocpp.v201.enums import (
    CancelReservationStatusEnumType,
    ConnectorEnumType,
    IdTokenEnumType,
    ReserveNowStatusEnumType,
    ReservationUpdateStatusEnumType,
)


def _make_adapter(command_queue=None) -> V201Adapter:
    mock_conn = MagicMock()
    mock_conn.recv = AsyncMock()
    mock_conn.send = AsyncMock()
    if command_queue is None:
        command_queue = queue.Queue()
    return V201Adapter(
        id="CP_1",
        connection=mock_conn,
        command_queue=command_queue,
    )


class TestReserveNow:
    def test_accepted_with_evse_id(self):
        adapter = _make_adapter()
        adapter.known_connector_ids = [1, 2]
        adapter.reserve_connector = MagicMock(return_value="accepted")

        id_token = IdTokenType(id_token="TAG_1", type=IdTokenEnumType.central)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        result = asyncio.run(
            adapter.on_reserve_now(
                id=100,
                expiry_date_time=expiry,
                id_token=id_token,
                evse_id=1,
            )
        )

        assert result.status == ReserveNowStatusEnumType.accepted
        adapter.reserve_connector.assert_called_once()
        call_args = adapter.reserve_connector.call_args
        assert call_args[0][0] == 1
        assert call_args[0][1] == 100
        assert call_args[0][2] == "TAG_1"

    def test_accepted_with_connector_type(self):
        adapter = _make_adapter()
        adapter.known_connector_ids = [1]
        adapter.reserve_connector = MagicMock(return_value="accepted")

        id_token = IdTokenType(id_token="TAG_1", type=IdTokenEnumType.central)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        result = asyncio.run(
            adapter.on_reserve_now(
                id=101,
                expiry_date_time=expiry,
                id_token=id_token,
                connector_type=ConnectorEnumType.c_ccs2,
                evse_id=1,
            )
        )

        assert result.status == ReserveNowStatusEnumType.accepted

    def test_accepted_with_group_id_token(self):
        adapter = _make_adapter()
        adapter.known_connector_ids = [1]
        adapter.reserve_connector = MagicMock(return_value="accepted")

        id_token = IdTokenType(id_token="TAG_1", type=IdTokenEnumType.central)
        group_token = IdTokenType(id_token="GROUP_1", type=IdTokenEnumType.central)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        result = asyncio.run(
            adapter.on_reserve_now(
                id=102,
                expiry_date_time=expiry,
                id_token=id_token,
                evse_id=1,
                group_id_token=group_token,
            )
        )

        assert result.status == ReserveNowStatusEnumType.accepted

    def test_no_reserve_callback_rejected(self):
        adapter = _make_adapter()
        adapter.reserve_connector = None

        id_token = IdTokenType(id_token="TAG_1", type=IdTokenEnumType.central)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        result = asyncio.run(
            adapter.on_reserve_now(
                id=103,
                expiry_date_time=expiry,
                id_token=id_token,
                evse_id=1,
            )
        )

        assert result.status == ReserveNowStatusEnumType.rejected

    def test_unknown_evse_rejected(self):
        adapter = _make_adapter()
        adapter.known_connector_ids = [1]
        adapter.reserve_connector = MagicMock(return_value="accepted")

        id_token = IdTokenType(id_token="TAG_1", type=IdTokenEnumType.central)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        result = asyncio.run(
            adapter.on_reserve_now(
                id=104,
                expiry_date_time=expiry,
                id_token=id_token,
                evse_id=99,
            )
        )

        assert result.status == ReserveNowStatusEnumType.rejected

    def test_evse_id_zero_picks_available_connector(self):
        adapter = _make_adapter()
        adapter.known_connector_ids = [1, 2]
        adapter.get_connector_status = MagicMock(
            side_effect=lambda cid: "Available" if cid == 2 else "Occupied"
        )
        adapter.reserve_connector = MagicMock(return_value="accepted")

        id_token = IdTokenType(id_token="TAG_1", type=IdTokenEnumType.central)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        result = asyncio.run(
            adapter.on_reserve_now(
                id=105,
                expiry_date_time=expiry,
                id_token=id_token,
                evse_id=0,
            )
        )

        assert result.status == ReserveNowStatusEnumType.accepted
        call_args = adapter.reserve_connector.call_args
        assert call_args[0][0] == 2

    def test_evse_id_zero_unavailable_when_none_available(self):
        adapter = _make_adapter()
        adapter.known_connector_ids = [1]
        adapter.reserve_connector = MagicMock(return_value="accepted")
        adapter.get_connector_status = MagicMock(return_value="Occupied")

        id_token = IdTokenType(id_token="TAG_1", type=IdTokenEnumType.central)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        result = asyncio.run(
            adapter.on_reserve_now(
                id=106,
                expiry_date_time=expiry,
                id_token=id_token,
                evse_id=0,
            )
        )

        assert result.status == ReserveNowStatusEnumType.unavailable

    def test_invalid_expiry_rejected(self):
        adapter = _make_adapter()
        adapter.known_connector_ids = [1]

        id_token = IdTokenType(id_token="TAG_1", type=IdTokenEnumType.central)
        result = asyncio.run(
            adapter.on_reserve_now(
                id=107,
                expiry_date_time="not-a-date",
                id_token=id_token,
                evse_id=1,
            )
        )

        assert result.status == ReserveNowStatusEnumType.rejected

    def test_engine_occupied_returns_occupied(self):
        adapter = _make_adapter()
        adapter.known_connector_ids = [1]
        adapter.reserve_connector = MagicMock(return_value="occupied")

        id_token = IdTokenType(id_token="TAG_1", type=IdTokenEnumType.central)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        result = asyncio.run(
            adapter.on_reserve_now(
                id=108,
                expiry_date_time=expiry,
                id_token=id_token,
                evse_id=1,
            )
        )

        assert result.status == ReserveNowStatusEnumType.occupied

    def test_engine_rejected_returns_rejected(self):
        adapter = _make_adapter()
        adapter.known_connector_ids = [1]
        adapter.reserve_connector = MagicMock(return_value="rejected")

        id_token = IdTokenType(id_token="TAG_1", type=IdTokenEnumType.central)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        result = asyncio.run(
            adapter.on_reserve_now(
                id=109,
                expiry_date_time=expiry,
                id_token=id_token,
                evse_id=1,
            )
        )

        assert result.status == ReserveNowStatusEnumType.rejected


class TestCancelReservation:
    def test_accepted(self):
        adapter = _make_adapter()
        adapter.cancel_reservation = MagicMock(return_value="accepted")

        result = asyncio.run(adapter.on_cancel_reservation(reservation_id=100))

        assert result.status == CancelReservationStatusEnumType.accepted
        adapter.cancel_reservation.assert_called_once_with(100)

    def test_rejected_when_not_found(self):
        adapter = _make_adapter()
        adapter.cancel_reservation = MagicMock(return_value="rejected")

        result = asyncio.run(adapter.on_cancel_reservation(reservation_id=999))

        assert result.status == CancelReservationStatusEnumType.rejected

    def test_no_callback_rejected(self):
        adapter = _make_adapter()
        adapter.cancel_reservation = None

        result = asyncio.run(adapter.on_cancel_reservation(reservation_id=100))

        assert result.status == CancelReservationStatusEnumType.rejected


class TestSendReservationStatusUpdate:
    def test_sends_expired_payload(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(
            adapter.send_reservation_status_update(
                reservation_id=100,
                status=ReservationUpdateStatusEnumType.expired,
            )
        )

        adapter.call.assert_called_once()
        call_args = adapter.call.call_args[0][0]
        assert call_args.reservation_id == 100
        assert (
            call_args.reservation_update_status
            == ReservationUpdateStatusEnumType.expired
        )

    def test_sends_removed_payload(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(
            adapter.send_reservation_status_update(
                reservation_id=200,
                status=ReservationUpdateStatusEnumType.removed,
            )
        )

        adapter.call.assert_called_once()
        call_args = adapter.call.call_args[0][0]
        assert call_args.reservation_id == 200
        assert (
            call_args.reservation_update_status
            == ReservationUpdateStatusEnumType.removed
        )


class TestReservationDataclass:
    def test_v16_defaults_are_none(self):
        r = Reservation(
            reservation_id=1,
            connector_id=1,
            id_tag="TAG_1",
            expiry_date=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert r.connector_type is None
        assert r.group_id_tag is None

    def test_v201_fields_set(self):
        r = Reservation(
            reservation_id=1,
            connector_id=1,
            id_tag="TAG_1",
            expiry_date=datetime.now(timezone.utc) + timedelta(hours=1),
            connector_type="cCCS2",
            group_id_tag="GROUP_1",
        )
        assert r.connector_type == "cCCS2"
        assert r.group_id_tag == "GROUP_1"

    def test_is_expired_returns_false_for_future(self):
        r = Reservation(
            reservation_id=1,
            connector_id=1,
            id_tag="TAG_1",
            expiry_date=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert r.is_expired() is False

    def test_is_expired_returns_true_for_past(self):
        r = Reservation(
            reservation_id=1,
            connector_id=1,
            id_tag="TAG_1",
            expiry_date=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert r.is_expired() is True
