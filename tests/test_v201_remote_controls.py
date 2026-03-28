import asyncio
import queue
from unittest.mock import AsyncMock, MagicMock

from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter
from ocpp.v201.datatypes import IdTokenType, EVSEType
from ocpp.v201.enums import (
	IdTokenEnumType,
	MessageTriggerEnumType,
	OperationalStatusEnumType,
	ResetEnumType,
	RequestStartStopStatusEnumType,
	ResetStatusEnumType,
	ChangeAvailabilityStatusEnumType,
	TriggerMessageStatusEnumType,
	UnlockStatusEnumType,
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


class TestRequestStartTransaction:
	def test_accepted_enqueues_start(self):
		cmd_q = queue.Queue()
		adapter = _make_adapter(command_queue=cmd_q)

		id_token = IdTokenType(id_token="RFID_001", type=IdTokenEnumType.central)
		result = asyncio.run(adapter.on_request_start_transaction(
			id_token=id_token,
			remote_start_id=1,
		))

		assert result.status == RequestStartStopStatusEnumType.accepted
		cmd = cmd_q.get_nowait()
		assert cmd["action"] == "START"
		assert cmd["id_tag"] == "RFID_001"
		assert cmd["connector_id"] is None

	def test_with_evse_id_enqueues_targeted_start(self):
		cmd_q = queue.Queue()
		adapter = _make_adapter(command_queue=cmd_q)

		id_token = IdTokenType(id_token="RFID_001", type=IdTokenEnumType.central)
		result = asyncio.run(adapter.on_request_start_transaction(
			id_token=id_token,
			remote_start_id=2,
			evse_id=3,
		))

		assert result.status == RequestStartStopStatusEnumType.accepted
		cmd = cmd_q.get_nowait()
		assert cmd["connector_id"] == 3

	def test_negative_evse_id_rejected(self):
		adapter = _make_adapter()

		id_token = IdTokenType(id_token="RFID_001", type=IdTokenEnumType.central)
		result = asyncio.run(adapter.on_request_start_transaction(
			id_token=id_token,
			remote_start_id=3,
			evse_id=-1,
		))

		assert result.status == RequestStartStopStatusEnumType.rejected

	def test_no_command_queue_rejected(self):
		adapter = _make_adapter()
		adapter.command_queue = None

		id_token = IdTokenType(id_token="RFID_001", type=IdTokenEnumType.central)
		result = asyncio.run(adapter.on_request_start_transaction(
			id_token=id_token,
			remote_start_id=4,
		))

		assert result.status == RequestStartStopStatusEnumType.rejected


class TestRequestStopTransaction:
	def test_accepted_enqueues_stop(self):
		cmd_q = queue.Queue()
		adapter = _make_adapter(command_queue=cmd_q)
		adapter.transaction_manager.begin_transaction(1)

		tx_id = adapter.transaction_manager.get_transaction_id(1)
		result = asyncio.run(adapter.on_request_stop_transaction(
			transaction_id=tx_id,
		))

		assert result.status == RequestStartStopStatusEnumType.accepted
		cmd = cmd_q.get_nowait()
		assert cmd["action"] == "STOP"
		assert cmd["connector_id"] == 1
		assert cmd["reason"] == "Remote"

	def test_unknown_transaction_rejected(self):
		adapter = _make_adapter()

		result = asyncio.run(adapter.on_request_stop_transaction(
			transaction_id="nonexistent",
		))

		assert result.status == RequestStartStopStatusEnumType.rejected


class TestReset:
	def test_immediate_maps_to_hard_and_enqueues(self):
		cmd_q = queue.Queue()
		adapter = _make_adapter(command_queue=cmd_q)
		received_types: list[str] = []

		class Receiver:
			def on_reset_requested(self, reset_type: str) -> None:
				received_types.append(reset_type)

		receiver = Receiver()
		adapter.on_reset_requested.subscribe(receiver.on_reset_requested)

		result = asyncio.run(adapter.on_reset(type=ResetEnumType.immediate))

		assert result.status == ResetStatusEnumType.accepted
		assert cmd_q.get_nowait() == {"action": "RESET", "type": "Hard"}
		assert received_types == ["Hard"]

	def test_on_idle_maps_to_soft_and_enqueues(self):
		cmd_q = queue.Queue()
		adapter = _make_adapter(command_queue=cmd_q)

		result = asyncio.run(adapter.on_reset(type=ResetEnumType.on_idle))

		assert result.status == ResetStatusEnumType.accepted
		assert cmd_q.get_nowait() == {"action": "RESET", "type": "Soft"}

	def test_no_command_queue_rejected(self):
		adapter = _make_adapter()
		adapter.command_queue = None

		result = asyncio.run(adapter.on_reset(type=ResetEnumType.immediate))
		assert result.status == ResetStatusEnumType.rejected


class TestChangeAvailability:
	def test_operative_accepted(self):
		adapter = _make_adapter()
		adapter.known_connector_ids = [1, 2]
		adapter.set_connector_availability = MagicMock(return_value="accepted")

		result = asyncio.run(adapter.on_change_availability(
			operational_status=OperationalStatusEnumType.operative,
			evse=EVSEType(id=1),
		))

		assert result.status == ChangeAvailabilityStatusEnumType.accepted
		adapter.set_connector_availability.assert_called_once_with(1, "Operative")

	def test_inoperative_accepted(self):
		adapter = _make_adapter()
		adapter.known_connector_ids = [1]
		adapter.set_connector_availability = MagicMock(return_value="accepted")

		result = asyncio.run(adapter.on_change_availability(
			operational_status=OperationalStatusEnumType.inoperative,
			evse=EVSEType(id=1),
		))

		assert result.status == ChangeAvailabilityStatusEnumType.accepted
		adapter.set_connector_availability.assert_called_once_with(1, "Inoperative")

	def test_scheduled_when_engine_defers(self):
		adapter = _make_adapter()
		adapter.known_connector_ids = [1]
		adapter.set_connector_availability = MagicMock(return_value="scheduled")

		result = asyncio.run(adapter.on_change_availability(
			operational_status=OperationalStatusEnumType.inoperative,
			evse=EVSEType(id=1),
		))

		assert result.status == ChangeAvailabilityStatusEnumType.scheduled

	def test_unknown_evse_rejected(self):
		adapter = _make_adapter()
		adapter.known_connector_ids = [1]
		adapter.set_connector_availability = MagicMock(return_value="rejected")

		result = asyncio.run(adapter.on_change_availability(
			operational_status=OperationalStatusEnumType.operative,
			evse=EVSEType(id=99),
		))

		assert result.status == ChangeAvailabilityStatusEnumType.rejected

	def test_no_callback_rejected(self):
		adapter = _make_adapter()
		adapter.set_connector_availability = None

		result = asyncio.run(adapter.on_change_availability(
			operational_status=OperationalStatusEnumType.operative,
		))

		assert result.status == ChangeAvailabilityStatusEnumType.rejected


class TestUnlockConnector:
	def test_known_evse_unlocked(self):
		adapter = _make_adapter()
		adapter.known_connector_ids = [1]

		result = asyncio.run(adapter.on_unlock_connector(
			evse_id=1, connector_id=1,
		))

		assert result.status == UnlockStatusEnumType.unlocked

	def test_unknown_evse(self):
		adapter = _make_adapter()
		adapter.known_connector_ids = [1]

		result = asyncio.run(adapter.on_unlock_connector(
			evse_id=99, connector_id=1,
		))

		assert result.status == UnlockStatusEnumType.unknown_connector

	def test_active_transaction_stops_it(self):
		cmd_q = queue.Queue()
		adapter = _make_adapter(command_queue=cmd_q)
		adapter.known_connector_ids = [1]
		adapter.transaction_manager.begin_transaction(1)

		result = asyncio.run(adapter.on_unlock_connector(
			evse_id=1, connector_id=1,
		))

		assert result.status == UnlockStatusEnumType.unlocked
		cmd = cmd_q.get_nowait()
		assert cmd["action"] == "STOP"
		assert cmd["connector_id"] == 1
		assert cmd["reason"] == "UnlockCommand"


class TestTriggerMessage:
	def test_boot_notification_accepted(self):
		adapter = _make_adapter()
		adapter.send_boot_notification = AsyncMock()

		result = asyncio.run(adapter.on_trigger_message(
			requested_message=MessageTriggerEnumType.boot_notification,
		))

		assert result.status == TriggerMessageStatusEnumType.accepted

	def test_heartbeat_accepted(self):
		adapter = _make_adapter()
		adapter.send_heartbeat = AsyncMock()

		result = asyncio.run(adapter.on_trigger_message(
			requested_message=MessageTriggerEnumType.heartbeat,
		))

		assert result.status == TriggerMessageStatusEnumType.accepted

	def test_status_notification_rejected_without_callback(self):
		adapter = _make_adapter()
		adapter.get_connector_status = None

		result = asyncio.run(adapter.on_trigger_message(
			requested_message=MessageTriggerEnumType.status_notification,
			evse=EVSEType(id=1),
		))

		assert result.status == TriggerMessageStatusEnumType.rejected

	def test_status_notification_accepted_with_callback(self):
		adapter = _make_adapter()
		adapter.get_connector_status = MagicMock(return_value="Available")
		adapter.send_status_notification = AsyncMock(return_value=MagicMock())

		result = asyncio.run(adapter.on_trigger_message(
			requested_message=MessageTriggerEnumType.status_notification,
			evse=EVSEType(id=1),
		))

		assert result.status == TriggerMessageStatusEnumType.accepted

	def test_unknown_trigger_not_implemented(self):
		adapter = _make_adapter()

		result = asyncio.run(adapter.on_trigger_message(
			requested_message="SomeFutureMessage",
		))

		assert result.status == TriggerMessageStatusEnumType.not_implemented
