import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from ocpp.v16.enums import DataTransferStatus

from chargeghost_evse.ocpp_adapter.adapter import Adapter


def test_on_data_transfer_returns_unknown_vendor_for_unregistered_vendor() -> None:
	adapter = Adapter("CP_1", MagicMock())

	result = asyncio.run(
		adapter.on_data_transfer(vendor_id="OtherVendor", message_id="Capabilities")
	)

	assert result.status == DataTransferStatus.unknown_vendor_id
	assert result.data is None


def test_on_data_transfer_returns_unknown_message_for_missing_message() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.register_data_transfer_handler(
		"ChargeGhost",
		"Capabilities",
		lambda data: (DataTransferStatus.accepted, "{}"),
	)

	result = asyncio.run(adapter.on_data_transfer(vendor_id="ChargeGhost"))

	assert result.status == DataTransferStatus.unknown_message_id
	assert result.data is None


def test_on_data_transfer_returns_unknown_message_for_unknown_message_id() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.register_data_transfer_handler(
		"ChargeGhost",
		"Capabilities",
		lambda data: (DataTransferStatus.accepted, "{}"),
	)

	result = asyncio.run(
		adapter.on_data_transfer(vendor_id="ChargeGhost", message_id="Unknown")
	)

	assert result.status == DataTransferStatus.unknown_message_id
	assert result.data is None


def test_on_data_transfer_returns_registered_handler_payload() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.register_data_transfer_handler(
		"ChargeGhost",
		"Echo",
		lambda data: (DataTransferStatus.accepted, data),
	)

	result = asyncio.run(
		adapter.on_data_transfer(
			vendor_id="ChargeGhost",
			message_id="Echo",
			data="hello",
		)
	)

	assert result.status == DataTransferStatus.accepted
	assert result.data == "hello"


def test_on_data_transfer_returns_builtin_capabilities_payload() -> None:
	adapter = Adapter("CP_1", MagicMock())

	result = asyncio.run(
		adapter.on_data_transfer(
			vendor_id="ChargeGhost",
			message_id="Capabilities",
		)
	)

	assert result.status == DataTransferStatus.accepted
	assert result.data is not None

	payload = json.loads(result.data)
	assert payload["supports"] == [
		"ReserveNow",
		"CancelReservation",
		"ClearCache",
		"TriggerMessage",
		"DataTransfer",
	]


def test_send_data_transfer_wraps_ocpp_call() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.call = AsyncMock(
		return_value=MagicMock(
			status=DataTransferStatus.accepted,
			data="ok",
		)
	)

	result = asyncio.run(
		adapter.send_data_transfer(
			vendor_id="ChargeGhost",
			message_id="Echo",
			data="hello",
		)
	)

	assert result.status == DataTransferStatus.accepted
	assert result.data == "ok"
	adapter.call.assert_awaited_once()
	request = adapter.call.call_args.args[0]
	assert request.vendor_id == "ChargeGhost"
	assert request.message_id == "Echo"
	assert request.data == "hello"
