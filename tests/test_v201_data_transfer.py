import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter
from ocpp.v201.enums import DataTransferStatusEnumType


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


class TestDataTransferHandler:
    def test_unknown_vendor_id(self):
        adapter = _make_adapter()
        result = asyncio.run(
            adapter.on_data_transfer(
                vendor_id="UnknownVendor",
                message_id="SomeMessage",
            )
        )
        assert result.status == DataTransferStatusEnumType.unknown_vendor_id

    def test_empty_vendor_id_rejected(self):
        adapter = _make_adapter()
        result = asyncio.run(
            adapter.on_data_transfer(
                vendor_id="",
                message_id="SomeMessage",
            )
        )
        assert result.status == DataTransferStatusEnumType.rejected

    def test_vendor_without_message_id(self):
        adapter = _make_adapter()
        result = asyncio.run(
            adapter.on_data_transfer(
                vendor_id="SomeVendor",
                message_id=None,
            )
        )
        assert result.status == DataTransferStatusEnumType.unknown_vendor_id

    def test_data_passthrough(self):
        adapter = _make_adapter()
        result = asyncio.run(
            adapter.on_data_transfer(
                vendor_id="VendorX",
                message_id="Msg1",
                data='{"key": "value"}',
            )
        )
        assert result.status == DataTransferStatusEnumType.unknown_vendor_id
        assert result.data == '{"key": "value"}'

    def test_none_data_passthrough(self):
        adapter = _make_adapter()
        result = asyncio.run(
            adapter.on_data_transfer(
                vendor_id="VendorX",
                message_id="Msg1",
                data=None,
            )
        )
        assert result.status == DataTransferStatusEnumType.unknown_vendor_id
        assert result.data is None


class TestSendDataTransfer:
    def test_send_data_transfer_calls_ocpp(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.status = DataTransferStatusEnumType.accepted
        adapter.call = AsyncMock(return_value=mock_response)

        response = asyncio.run(
            adapter.send_data_transfer(
                vendor_id="VendorX",
                message_id="Msg1",
                data='{"foo": "bar"}',
            )
        )

        adapter.call.assert_awaited_once()
        request = adapter.call.call_args[0][0]
        assert request.vendor_id == "VendorX"
        assert request.message_id == "Msg1"
        assert request.data == '{"foo": "bar"}'
        assert response.status == DataTransferStatusEnumType.accepted

    def test_send_data_transfer_without_optional_fields(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.status = DataTransferStatusEnumType.unknown_vendor_id
        adapter.call = AsyncMock(return_value=mock_response)

        response = asyncio.run(adapter.send_data_transfer(vendor_id="VendorX"))

        adapter.call.assert_awaited_once()
        request = adapter.call.call_args[0][0]
        assert request.vendor_id == "VendorX"
        assert request.message_id is None
        assert request.data is None
        assert response.status == DataTransferStatusEnumType.unknown_vendor_id
