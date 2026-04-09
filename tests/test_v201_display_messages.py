import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from ocpp.v201.datatypes import MessageContentType, MessageInfoType
from ocpp.v201.enums import (
    ClearMessageStatusEnumType,
    DisplayMessageStatusEnumType,
    GetDisplayMessagesStatusEnumType,
    MessagePriorityEnumType,
    MessageStateEnumType,
)

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


def _make_message_content(
    content: str = "Hello World",
    format_enum=None,
    language: str | None = None,
) -> MessageContentType:
    return MessageContentType(
        format=format_enum if format_enum else "UTF8",
        content=content,
        language=language,
    )


def _make_message_info(
    msg_id: int = 1,
    priority=MessagePriorityEnumType.normal_cycle,
    state: MessageStateEnumType | None = None,
    transaction_id: str | None = None,
    content: str = "Hello World",
) -> MessageInfoType:
    return MessageInfoType(
        id=msg_id,
        priority=priority,
        message=_make_message_content(content),
        state=state,
        transaction_id=transaction_id,
    )


class TestSetDisplayMessage:
    @pytest.mark.asyncio
    async def test_accept_valid_message(self):
        adapter = _make_adapter()
        msg = _make_message_info(
            msg_id=1,
            priority=MessagePriorityEnumType.normal_cycle,
            state=MessageStateEnumType.charging,
        )

        result = await adapter.on_set_display_message(message=msg)

        assert result.status == DisplayMessageStatusEnumType.accepted
        assert 1 in adapter._display_messages

    @pytest.mark.asyncio
    async def test_auto_assign_id_when_zero(self):
        adapter = _make_adapter()
        msg = _make_message_info(msg_id=0)

        result = await adapter.on_set_display_message(message=msg)

        assert result.status == DisplayMessageStatusEnumType.accepted
        assert adapter._next_message_id == 1
        assert 1 in adapter._display_messages

    @pytest.mark.asyncio
    async def test_incrementing_auto_id(self):
        adapter = _make_adapter()
        msg1 = _make_message_info(msg_id=0)
        msg2 = _make_message_info(msg_id=0)

        await adapter.on_set_display_message(message=msg1)
        await adapter.on_set_display_message(message=msg2)

        assert adapter._next_message_id == 2

    @pytest.mark.asyncio
    async def test_reject_missing_message_content(self):
        adapter = _make_adapter()
        bad_msg = MessageInfoType(
            id=1,
            priority=MessagePriorityEnumType.normal_cycle,
            message=None,
        )

        result = await adapter.on_set_display_message(message=bad_msg)

        assert (
            result.status == DisplayMessageStatusEnumType.not_supported_message_format
        )

    @pytest.mark.asyncio
    async def test_reject_invalid_priority(self):
        adapter = _make_adapter()
        msg = _make_message_info()
        msg.priority = "InvalidPriority"

        result = await adapter.on_set_display_message(message=msg)

        assert result.status == DisplayMessageStatusEnumType.not_supported_priority

    @pytest.mark.asyncio
    async def test_reject_invalid_state(self):
        adapter = _make_adapter()
        msg = _make_message_info(state="InvalidState")

        result = await adapter.on_set_display_message(message=msg)

        assert result.status == DisplayMessageStatusEnumType.not_supported_state

    @pytest.mark.asyncio
    async def test_accept_message_without_state(self):
        adapter = _make_adapter()
        msg = _make_message_info(state=None)

        result = await adapter.on_set_display_message(message=msg)

        assert result.status == DisplayMessageStatusEnumType.accepted
        assert 1 in adapter._display_messages
        assert adapter._display_messages[1].state is None

    @pytest.mark.asyncio
    async def test_emit_event_on_accept(self):
        adapter = _make_adapter()
        received: list[dict] = []

        class Handler:
            def on_msg(self, **kw):
                received.append(kw)

        handler = Handler()
        adapter.on_display_message.subscribe(handler.on_msg)
        msg = _make_message_info(msg_id=42)

        await adapter.on_set_display_message(message=msg)

        assert len(received) == 1
        assert received[0]["action"] == "set"
        assert received[0]["message"].id == 42

    @pytest.mark.asyncio
    async def test_store_with_transaction_id(self):
        adapter = _make_adapter()
        msg = _make_message_info(transaction_id="tx123")

        await adapter.on_set_display_message(message=msg)

        assert adapter._display_messages[1].transaction_id == "tx123"


class TestGetDisplayMessages:
    @pytest.mark.asyncio
    async def test_return_all_when_no_filters(self):
        adapter = _make_adapter()
        msg = _make_message_info(msg_id=1)
        await adapter.on_set_display_message(message=msg)

        result = await adapter.on_get_display_messages(request_id=1)

        assert result.status == GetDisplayMessagesStatusEnumType.accepted

    @pytest.mark.asyncio
    async def test_filter_by_id(self):
        adapter = _make_adapter()
        await adapter.on_set_display_message(message=_make_message_info(msg_id=10))
        await adapter.on_set_display_message(message=_make_message_info(msg_id=20))

        result = await adapter.on_get_display_messages(
            request_id=1,
            id=[10],
        )

        assert result.status == GetDisplayMessagesStatusEnumType.accepted

    @pytest.mark.asyncio
    async def test_filter_by_priority(self):
        adapter = _make_adapter()
        await adapter.on_set_display_message(
            message=_make_message_info(
                msg_id=1,
                priority=MessagePriorityEnumType.always_front,
            ),
        )
        await adapter.on_set_display_message(
            message=_make_message_info(
                msg_id=2,
                priority=MessagePriorityEnumType.normal_cycle,
            ),
        )

        result = await adapter.on_get_display_messages(
            request_id=1,
            priority=MessagePriorityEnumType.always_front,
        )

        assert result.status == GetDisplayMessagesStatusEnumType.accepted

    @pytest.mark.asyncio
    async def test_filter_by_state(self):
        adapter = _make_adapter()
        await adapter.on_set_display_message(
            message=_make_message_info(msg_id=1, state=MessageStateEnumType.charging),
        )
        await adapter.on_set_display_message(
            message=_make_message_info(msg_id=2, state=MessageStateEnumType.idle),
        )

        result = await adapter.on_get_display_messages(
            request_id=1,
            state=MessageStateEnumType.charging,
        )

        assert result.status == GetDisplayMessagesStatusEnumType.accepted

    @pytest.mark.asyncio
    async def test_unknown_when_empty_store(self):
        adapter = _make_adapter()

        result = await adapter.on_get_display_messages(request_id=1)

        assert result.status == GetDisplayMessagesStatusEnumType.unknown

    @pytest.mark.asyncio
    async def test_unknown_when_no_match(self):
        adapter = _make_adapter()
        await adapter.on_set_display_message(
            message=_make_message_info(msg_id=1, state=MessageStateEnumType.charging),
        )

        result = await adapter.on_get_display_messages(
            request_id=1,
            state=MessageStateEnumType.faulted,
        )

        assert result.status == GetDisplayMessagesStatusEnumType.unknown

    @pytest.mark.asyncio
    async def test_send_notify_on_get(self):
        adapter = _make_adapter()
        msg = _make_message_info(msg_id=1)
        await adapter.on_set_display_message(message=msg)

        notify_called = False

        async def mock_call(req):
            nonlocal notify_called
            notify_called = True
            return MagicMock()

        adapter.call = mock_call
        await adapter.on_get_display_messages(request_id=42)
        await asyncio.sleep(0.1)

        assert notify_called


class TestClearDisplayMessage:
    @pytest.mark.asyncio
    async def test_accept_existing_message(self):
        adapter = _make_adapter()
        msg = _make_message_info(msg_id=5)
        await adapter.on_set_display_message(message=msg)
        assert 5 in adapter._display_messages

        result = await adapter.on_clear_display_message(id=5)

        assert result.status == ClearMessageStatusEnumType.accepted
        assert 5 not in adapter._display_messages

    @pytest.mark.asyncio
    async def test_unknown_for_missing_message(self):
        adapter = _make_adapter()

        result = await adapter.on_clear_display_message(id=999)

        assert result.status == ClearMessageStatusEnumType.unknown

    @pytest.mark.asyncio
    async def test_emit_event_on_clear(self):
        adapter = _make_adapter()
        received: list[dict] = []

        class Handler:
            def on_msg(self, **kw):
                received.append(kw)

        handler = Handler()
        adapter.on_display_message.subscribe(handler.on_msg)
        msg = _make_message_info(msg_id=7)
        await adapter.on_set_display_message(message=msg)

        await adapter.on_clear_display_message(id=7)

        assert len(received) == 2
        assert received[1]["action"] == "clear"
        assert received[1]["message"].id == 7


class TestSendNotifyDisplayMessages:
    @pytest.mark.asyncio
    async def test_sends_correct_payload(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())
        messages = [_make_message_info(msg_id=1)]

        await adapter.send_notify_display_messages(request_id=10, messages=messages)

        adapter.call.assert_called_once()
        call_args = adapter.call.call_args[0][0]
        assert call_args.request_id == 10
        assert len(call_args.message_info) == 1
        assert call_args.message_info[0].id == 1
        assert call_args.tbc is False

    @pytest.mark.asyncio
    async def test_sends_empty_list(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        await adapter.send_notify_display_messages(request_id=5, messages=None)

        adapter.call.assert_called_once()
        call_args = adapter.call.call_args[0][0]
        assert call_args.request_id == 5
        assert call_args.message_info is None


class TestDisplayMessageIntegration:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        msg1 = _make_message_info(
            msg_id=1,
            priority=MessagePriorityEnumType.always_front,
            state=MessageStateEnumType.charging,
            content="Welcome",
        )
        msg2 = _make_message_info(
            msg_id=2,
            priority=MessagePriorityEnumType.normal_cycle,
            state=MessageStateEnumType.idle,
            content="Status OK",
        )

        r1 = await adapter.on_set_display_message(message=msg1)
        r2 = await adapter.on_set_display_message(message=msg2)
        assert r1.status == DisplayMessageStatusEnumType.accepted
        assert r2.status == DisplayMessageStatusEnumType.accepted
        assert len(adapter._display_messages) == 2

        r3 = await adapter.on_get_display_messages(
            request_id=1,
            priority=MessagePriorityEnumType.always_front,
        )
        assert r3.status == GetDisplayMessagesStatusEnumType.accepted

        r4 = await adapter.on_clear_display_message(id=1)
        assert r4.status == ClearMessageStatusEnumType.accepted
        assert len(adapter._display_messages) == 1
        assert 1 not in adapter._display_messages
        assert 2 in adapter._display_messages

        r5 = await adapter.on_clear_display_message(id=2)
        assert r5.status == ClearMessageStatusEnumType.accepted
        assert len(adapter._display_messages) == 0

        r6 = await adapter.on_get_display_messages(request_id=2)
        assert r6.status == GetDisplayMessagesStatusEnumType.unknown
