import asyncio
import queue
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from ocpp.v16 import call_result as v16_call_result
from ocpp.v16.enums import (
	MessageTrigger,
	RemoteStartStopStatus,
	TriggerMessageStatus,
)
from ocpp.v201 import call_result as v201_call_result
from ocpp.v201.datatypes import IdTokenType
from ocpp.v201.enums import (
	IdTokenEnumType,
	MessageTriggerEnumType,
	RequestStartStopStatusEnumType,
	TriggerMessageStatusEnumType,
)

from chargeghost_evse.devtools.fault_manager import FaultManager
from chargeghost_evse.devtools.fault_models import FaultConfig
from chargeghost_evse.ocpp_adapter.adapter import Adapter
from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter


def _make_v16_adapter(fault_manager: FaultManager = None) -> Adapter:
	mock_conn = MagicMock()
	mock_conn.recv = AsyncMock()
	mock_conn.send = AsyncMock()
	kwargs = {}
	if fault_manager is not None:
		kwargs["fault_manager"] = fault_manager
	adapter = Adapter("CP_1", mock_conn, **kwargs)
	adapter.call = AsyncMock(
		return_value=v16_call_result.Authorize(
			id_tag_info={"status": "Accepted"}
		)
	)
	return adapter


def _make_v201_adapter(fault_manager: FaultManager = None) -> V201Adapter:
	mock_conn = MagicMock()
	mock_conn.recv = AsyncMock()
	mock_conn.send = AsyncMock()
	kwargs = {}
	if fault_manager is not None:
		kwargs["fault_manager"] = fault_manager
	adapter = V201Adapter("CP_1", mock_conn, **kwargs)
	adapter.call = AsyncMock(
		return_value=v201_call_result.Authorize(
			id_token_info=MagicMock(status=MagicMock(value="Accepted"))
		)
	)
	return adapter


@pytest.mark.asyncio
async def test_authorize_delay_fault_wraps_outbound_send() -> None:
	fm = FaultManager()
	fm.enable("delayed_response", FaultConfig(fault_id="delayed_response"))
	adapter = _make_v16_adapter(fault_manager=fm)

	start = time.monotonic()
	await adapter.send_authorize(id_tag="TAG1")
	elapsed = time.monotonic() - start

	assert elapsed >= 5.0
	adapter.call.assert_awaited_once()


@pytest.mark.asyncio
async def test_authorize_delay_fault_with_custom_delay() -> None:
	fm = FaultManager()
	fm.enable(
		"delayed_response",
		FaultConfig(
			fault_id="delayed_response",
			parameters={"delay_seconds": 0.2},
		),
	)
	adapter = _make_v16_adapter(fault_manager=fm)

	start = time.monotonic()
	await adapter.send_authorize(id_tag="TAG1")
	elapsed = time.monotonic() - start

	assert elapsed >= 0.2
	assert elapsed < 2.0
	adapter.call.assert_awaited_once()


@pytest.mark.asyncio
async def test_v16_remote_start_reject_fault_returns_rejected() -> None:
	fm = FaultManager()
	fm.enable("rejected_action", FaultConfig(fault_id="rejected_action"))
	adapter = _make_v16_adapter(fault_manager=fm)

	result = await adapter.on_remote_start_transaction(
		connector_id=1,
		id_tag="TAG1",
	)

	assert result.status == RemoteStartStopStatus.rejected


@pytest.mark.asyncio
async def test_v201_request_start_reject_fault_returns_rejected() -> None:
	fm = FaultManager()
	fm.enable("rejected_action", FaultConfig(fault_id="rejected_action"))
	adapter = _make_v201_adapter(fault_manager=fm)

	id_token = IdTokenType(id_token="RFID_001", type=IdTokenEnumType.central)
	result = await adapter.on_request_start_transaction(
		id_token=id_token,
		remote_start_id=1,
	)

	assert result.status == RequestStartStopStatusEnumType.rejected


@pytest.mark.asyncio
async def test_trigger_message_not_implemented_fault_is_protocol_valid() -> None:
	fm = FaultManager()
	fm.enable(
		"trigger_message_not_implemented",
		FaultConfig(fault_id="trigger_message_not_implemented"),
	)
	adapter = _make_v16_adapter(fault_manager=fm)

	result = await adapter.on_trigger_message(
		requested_message=MessageTrigger.boot_notification,
	)

	assert result.status == TriggerMessageStatus.not_implemented


@pytest.mark.asyncio
async def test_v201_trigger_message_not_implemented_fault() -> None:
	fm = FaultManager()
	fm.enable(
		"trigger_message_not_implemented",
		FaultConfig(fault_id="trigger_message_not_implemented"),
	)
	adapter = _make_v201_adapter(fault_manager=fm)

	result = await adapter.on_trigger_message(
		requested_message=MessageTriggerEnumType.boot_notification,
	)

	assert result.status == TriggerMessageStatusEnumType.not_implemented


@pytest.mark.asyncio
async def test_no_fault_baseline_unchanged() -> None:
	cmd_q: queue.Queue = queue.Queue()
	adapter = _make_v16_adapter(fault_manager=None)
	adapter.command_queue = cmd_q

	result = await adapter.on_remote_start_transaction(
		connector_id=1,
		id_tag="TAG1",
	)

	assert result.status == RemoteStartStopStatus.accepted
	assert cmd_q.get_nowait()["action"] == "START"
