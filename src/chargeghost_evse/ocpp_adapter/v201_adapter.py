"""
OCPP 2.0.1 Adapter Module.

This module provides the OCPP 2.0.1 adapter implementation for the ChargeGhost
EVSE simulator. It implements bidirectional OCPP 2.0.1 communication using
TransactionEvent for session lifecycle instead of StartTransaction/StopTransaction.

The adapter accepts the same bridge-level call signatures as the OCPP 1.6 adapter
where possible (send_status_notification, send_meter_values, send_authorize) and
translates payloads internally to OCPP 2.0.1 format.

Classes:
    V201Adapter: OCPP 2.0.1 Charge Point implementation.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ocpp.routing import on
from ocpp.v201 import ChargePoint as cp
from ocpp.v201 import call, call_result
from ocpp.v201.datatypes import (
    ChargingStationType,
    EVSEType,
    IdTokenType,
    MeterValueType,
    SampledValueType,
    TransactionType,
)
from ocpp.v201.enums import (
    BootReasonEnumType,
    ChangeAvailabilityStatusEnumType,
    ConnectorStatusEnumType,
    IdTokenEnumType,
    MeasurandEnumType,
    MessageTriggerEnumType,
    OperationalStatusEnumType,
    ReadingContextEnumType,
    ReasonEnumType,
    RegistrationStatusEnumType,
    RequestStartStopStatusEnumType,
    ResetEnumType,
    ResetStatusEnumType,
    TransactionEventEnumType,
    TriggerMessageStatusEnumType,
    TriggerReasonEnumType,
    UnlockStatusEnumType,
)

from chargeghost_evse.ocpp_adapter.base_adapter import BaseAdapter
from chargeghost_evse.ocpp_adapter.transaction_manager_v201 import (
    TransactionManagerV201,
)


_STATUS_MAP: dict[str, ConnectorStatusEnumType] = {
    "Available": ConnectorStatusEnumType.available,
    "Preparing": ConnectorStatusEnumType.occupied,
    "Charging": ConnectorStatusEnumType.occupied,
    "SuspendedEVSE": ConnectorStatusEnumType.occupied,
    "SuspendedEV": ConnectorStatusEnumType.occupied,
    "Finishing": ConnectorStatusEnumType.occupied,
    "Reserved": ConnectorStatusEnumType.reserved,
    "Unavailable": ConnectorStatusEnumType.unavailable,
    "Faulted": ConnectorStatusEnumType.faulted,
}

_REASON_MAP: dict[str, ReasonEnumType] = {
    "Local": ReasonEnumType.local,
    "Remote": ReasonEnumType.remote,
    "SoftReset": ReasonEnumType.reboot,
    "HardReset": ReasonEnumType.immediate_reset,
    "EVDisconnected": ReasonEnumType.ev_disconnected,
    "UnlockCommand": ReasonEnumType.other,
    "StoppedByEV": ReasonEnumType.stopped_by_ev,
    "Timeout": ReasonEnumType.timeout,
    "Other": ReasonEnumType.other,
    "EmergencyStop": ReasonEnumType.emergency_stop,
    "PowerLoss": ReasonEnumType.power_loss,
    "Reboot": ReasonEnumType.reboot,
    "EnergyLimitReached": ReasonEnumType.energy_limit_reached,
    "SOCLimitReached": ReasonEnumType.soc_limit_reached,
    "TimeLimitReached": ReasonEnumType.time_limit_reached,
    "DeAuthorized": ReasonEnumType.de_authorized,
}

_CONTEXT_MAP: dict[str, ReadingContextEnumType] = {
    "Sample.Periodic": ReadingContextEnumType.sample_periodic,
    "Sample.Clock": ReadingContextEnumType.sample_clock,
    "Transaction.Begin": ReadingContextEnumType.transaction_begin,
    "Transaction.End": ReadingContextEnumType.transaction_end,
    "Trigger": ReadingContextEnumType.trigger,
    "Other": ReadingContextEnumType.other,
}


def _map_connector_status(status: str) -> ConnectorStatusEnumType:
    return _STATUS_MAP.get(status, ConnectorStatusEnumType.available)


def _map_stop_reason(reason: Optional[str]) -> ReasonEnumType:
    if reason is None:
        return ReasonEnumType.local
    return _REASON_MAP.get(reason, ReasonEnumType.other)


def _map_reading_context(context: str) -> ReadingContextEnumType:
    return _CONTEXT_MAP.get(context, ReadingContextEnumType.other)


class V201Adapter(BaseAdapter, cp):
    """
    OCPP 2.0.1 Charge Point adapter implementation.

    Extends the ocpp library's v201 ChargePoint class to implement the EVSE
    side of OCPP 2.0.1 communication. Uses TransactionEvent for session
    lifecycle and a TransactionManagerV201 for transaction ID and sequence
    number tracking.

    Incoming handlers:
            RequestStartTransaction, RequestStopTransaction, TriggerMessage,
            ChangeAvailability, UnlockConnector, Reset

    Outbound methods:
            send_boot_notification, send_heartbeat, send_status_notification,
            send_authorize, send_transaction_event_started,
            send_transaction_event_updated, send_transaction_event_ended,
            send_meter_values

    Attributes:
            transaction_manager: OCPP 2.0.1 transaction state tracker.
    """

    _log_important_actions = {
        "BootNotification",
        "TransactionEvent",
        "Authorize",
        "RequestStartTransaction",
        "RequestStopTransaction",
        "Reset",
        "StatusNotification",
        "MeterValues",
        "DataTransfer",
    }

    def __init__(
        self,
        id: str,
        connection: Any,
        command_queue: Any = None,
        response_timeout: int = 30,
        charge_point_model: str = "ChargeGhostV2",
        charge_point_vendor: str = "ChargeGhost",
    ) -> None:
        cp.__init__(self, id, connection, response_timeout)
        self._init_base(
            command_queue=command_queue,
            charge_point_model=charge_point_model,
            charge_point_vendor=charge_point_vendor,
            response_timeout=response_timeout,
            protocol_version="ocpp2.0.1",
        )
        self.transaction_manager = TransactionManagerV201()

    # -------------------------------------------------------------------------
    # Outbound OCPP Messages
    # -------------------------------------------------------------------------

    async def send_boot_notification(self) -> Any:
        """
        Send BootNotification to the Central System.

        Returns:
                BootNotification response from the CSMS.
        """
        request = call.BootNotification(
            reason=BootReasonEnumType.power_up,
            charging_station=ChargingStationType(
                vendor_name=self.charge_point_vendor,
                model=self.charge_point_model,
            ),
        )
        self._log(
            f"BootNotification: model={self.charge_point_model}, "
            f"vendor={self.charge_point_vendor}",
        )

        response: call_result.BootNotification = await self.call(request)
        self._log(
            f"BootNotification response: status={response.status}, "
            f"interval={response.interval}",
        )

        self.registration_status = response.status
        if response.status == RegistrationStatusEnumType.accepted:
            self.heartbeat_interval = response.interval
            self._log(
                f"Registration accepted. Heartbeat: {self.heartbeat_interval}s",
            )
            self.on_registration_accepted.emit()
        else:
            self._log(
                f"Registration status: {response.status}",
            )

        return response

    async def send_heartbeat(self) -> Any:
        """
        Send Heartbeat to the Central System.

        Returns:
                Heartbeat response with current server time.
        """
        request = call.Heartbeat()
        self._log("Heartbeat", level=logging.DEBUG)

        response: call_result.Heartbeat = await self.call(request)
        self._log(
            f"Heartbeat response: {response.current_time}",
            level=logging.DEBUG,
        )
        self.on_heartbeat_response.emit(current_time=response.current_time)
        return response

    async def send_status_notification(self, **kwargs: Any) -> Any:
        """
        Send StatusNotification to the Central System.

        Accepts the same keyword arguments as the V16 adapter for bridge
        compatibility and translates internally to OCPP 2.0.1 format.

        Keyword Args:
                connector_id: Mapped to evse_id in 2.0.1.
                error_code: Ignored in 2.0.1 (no error code field).
                status: Engine status string, mapped to ConnectorStatusEnumType.

        Returns:
                StatusNotification response.
        """
        connector_id = kwargs.get("connector_id", 0)
        status_str = kwargs.get("status", "Available")
        connector_status = _map_connector_status(status_str)
        timestamp = datetime.now(timezone.utc).isoformat()

        request = call.StatusNotification(
            timestamp=timestamp,
            connector_status=connector_status,
            evse_id=connector_id,
            connector_id=1,
        )
        self._log(
            f"StatusNotification: evse={connector_id}, status={connector_status.value}",
        )

        response: call_result.StatusNotification = await self.call(request)
        return response

    async def send_authorize(self, **kwargs: Any) -> Any:
        """
        Send Authorize request to the Central System.

        Accepts the same keyword arguments as the V16 adapter for bridge
        compatibility. Translates id_tag to IdTokenType (Central).

        Keyword Args:
                id_tag: The identifier to authorize.

        Returns:
                Authorize response with authorization status.
        """
        id_tag = kwargs.get("id_tag", "")
        self._log(f"Authorize: id_token={id_tag}")

        request = call.Authorize(
            id_token=IdTokenType(
                id_token=id_tag,
                type=IdTokenEnumType.central,
            ),
        )
        response: call_result.Authorize = await self.call(request)

        id_token_info = response.id_token_info
        status = (
            id_token_info.status.value
            if id_token_info and hasattr(id_token_info.status, "value")
            else "Unknown"
        )
        self._log(f"Authorize response: status={status}")
        return response

    async def send_transaction_event_started(
        self,
        connector_id: int,
        id_tag: str,
        meter_start: int,
        timestamp: str,
        reservation_id: Optional[int] = None,
    ) -> Any:
        """
        Send TransactionEvent(Started) to the Central System.

        Creates a new transaction via the TransactionManager, sends the
        Started event, and returns the CSMS response.

        Args:
                connector_id: The EVSE where charging starts.
                id_tag: The authorization identifier.
                meter_start: Meter reading at transaction start (Wh).
                timestamp: ISO 8601 timestamp of transaction start.
                reservation_id: Optional reservation identifier.

        Returns:
                Tuple of (response, transaction_id_string).
        """
        tx_id = self.transaction_manager.begin_transaction(connector_id)
        seq_no = self.transaction_manager.get_next_seq_no(tx_id)

        self._log(
            f"TransactionEvent(Started): evse={connector_id}, "
            f"tx_id={tx_id}, seq_no={seq_no}",
        )

        meter_value: Optional[list[MeterValueType]] = None
        if meter_start >= 0:
            meter_value = [
                MeterValueType(
                    timestamp=timestamp,
                    sampled_value=[
                        SampledValueType(
                            value=float(meter_start),
                            context=ReadingContextEnumType.transaction_begin,
                            measurand=MeasurandEnumType.energy_active_import_register,
                        ),
                    ],
                )
            ]

        request = call.TransactionEvent(
            event_type=TransactionEventEnumType.started,
            timestamp=timestamp,
            trigger_reason=TriggerReasonEnumType.authorized,
            seq_no=seq_no,
            transaction_info=TransactionType(transaction_id=tx_id),
            meter_value=meter_value,
            offline=False,
            evse=EVSEType(id=connector_id, connector_id=1),
            id_token=IdTokenType(
                id_token=id_tag,
                type=IdTokenEnumType.central,
            ),
            reservation_id=reservation_id,
        )

        response: call_result.TransactionEvent = await self.call(request)
        self._log(
            f"TransactionEvent(Started) response: tx_id={tx_id}",
        )

        return response, tx_id

    async def send_transaction_event_updated(
        self,
        connector_id: int,
        transaction_id: str,
        timestamp: str,
        meter_value: Optional[list[MeterValueType]] = None,
        trigger_reason: Optional[TriggerReasonEnumType] = None,
        charging_state: Optional[str] = None,
    ) -> Any:
        """
        Send TransactionEvent(Updated) to the Central System.

        Args:
                connector_id: The EVSE with an active transaction.
                transaction_id: The active transaction ID.
                timestamp: ISO 8601 timestamp of the update.
                meter_value: Optional meter value readings.
                trigger_reason: Reason for the update event.
                charging_state: Optional charging state.

        Returns:
                TransactionEvent response.
        """
        seq_no = self.transaction_manager.get_next_seq_no(transaction_id)

        tx_info = TransactionType(transaction_id=transaction_id)
        if charging_state is not None:
            try:
                from ocpp.v201.enums import ChargingStateEnumType

                tx_info = TransactionType(
                    transaction_id=transaction_id,
                    charging_state=ChargingStateEnumType(charging_state),
                )
            except (ValueError, TypeError):
                pass

        reason = trigger_reason or TriggerReasonEnumType.meter_value_periodic

        request = call.TransactionEvent(
            event_type=TransactionEventEnumType.updated,
            timestamp=timestamp,
            trigger_reason=reason,
            seq_no=seq_no,
            transaction_info=tx_info,
            meter_value=meter_value,
            offline=False,
            evse=EVSEType(id=connector_id, connector_id=1),
        )

        response: call_result.TransactionEvent = await self.call(request)
        self._log(
            f"TransactionEvent(Updated): tx_id={transaction_id}, seq_no={seq_no}",
            level=logging.DEBUG,
        )
        return response

    async def send_transaction_event_ended(
        self,
        connector_id: int,
        transaction_id: str,
        timestamp: str,
        meter_stop: int,
        reason: Optional[str] = None,
        meter_history: Optional[list[dict]] = None,
    ) -> Any:
        """
        Send TransactionEvent(Ended) to the Central System.

        Ends the transaction via the TransactionManager and sends the Ended
        event with the final meter reading.

        Args:
                connector_id: The EVSE where the transaction ends.
                transaction_id: The transaction ID to end.
                timestamp: ISO 8601 timestamp of transaction end.
                meter_stop: Final meter reading (Wh).
                reason: Stop reason string from engine.
                meter_history: Meter value history (reserved for future use).

        Returns:
                TransactionEvent response.
        """
        seq_no = self.transaction_manager.get_next_seq_no(transaction_id)
        stopped_reason = _map_stop_reason(reason)

        self._log(
            f"TransactionEvent(Ended): tx_id={transaction_id}, "
            f"seq_no={seq_no}, reason={stopped_reason.value}",
        )

        tx_info = TransactionType(
            transaction_id=transaction_id,
            stopped_reason=stopped_reason,
        )

        meter_value: Optional[list[MeterValueType]] = None
        if meter_stop >= 0:
            meter_value = [
                MeterValueType(
                    timestamp=timestamp,
                    sampled_value=[
                        SampledValueType(
                            value=float(meter_stop),
                            context=ReadingContextEnumType.transaction_end,
                            measurand=MeasurandEnumType.energy_active_import_register,
                        ),
                    ],
                )
            ]

        request = call.TransactionEvent(
            event_type=TransactionEventEnumType.ended,
            timestamp=timestamp,
            trigger_reason=TriggerReasonEnumType.ev_departed,
            seq_no=seq_no,
            transaction_info=tx_info,
            meter_value=meter_value,
            offline=False,
            evse=EVSEType(id=connector_id, connector_id=1),
        )

        response: call_result.TransactionEvent = await self.call(request)

        self.transaction_manager.end_transaction(connector_id)

        return response

    async def send_meter_values(self, **kwargs: Any) -> Any:
        """
        Send MeterValues to the Central System.

        Accepts the same keyword arguments as the V16 adapter for bridge
        compatibility and translates to OCPP 2.0.1 format.

        Keyword Args:
                connector_id: The EVSE being monitored.
                value: Meter reading in Watt-hours.
                transaction_id: Associated transaction ID (ignored for 2.0.1
                        standalone MeterValues; use TransactionEvent instead).
                context: Reading context string.

        Returns:
                MeterValues response.
        """
        connector_id = kwargs.get("connector_id", 0)
        value = kwargs.get("value", 0.0)
        context_str = kwargs.get("context", "Sample.Periodic")
        reading_context = _map_reading_context(context_str)

        timestamp = datetime.now(timezone.utc).isoformat()

        request = call.MeterValues(
            evse_id=connector_id,
            meter_value=[
                MeterValueType(
                    timestamp=timestamp,
                    sampled_value=[
                        SampledValueType(
                            value=float(value),
                            context=reading_context,
                            measurand=MeasurandEnumType.energy_active_import_register,
                        ),
                    ],
                )
            ],
        )
        self._log(
            f"MeterValues: evse={connector_id}, value={value}Wh",
            level=logging.DEBUG,
        )

        response: call_result.MeterValues = await self.call(request)
        return response

    # -------------------------------------------------------------------------
    # Incoming OCPP Message Handlers
    # -------------------------------------------------------------------------

    @on("RequestStartTransaction")
    async def on_request_start_transaction(
        self,
        id_token: Any,
        remote_start_id: int,
        evse_id: Optional[int] = None,
        group_id_token: Optional[Any] = None,
        charging_profile: Optional[Any] = None,
        **kwargs: Any,
    ) -> call_result.RequestStartTransaction:
        """
        Handle RequestStartTransaction request from CSMS.

        Queues a START command for the Engine to process. If evse_id
        is not provided or is 0, the Engine will select an available EVSE.

        Args:
                id_token: IdTokenType with the authorization token.
                remote_start_id: CSMS identifier for this remote start request.
                evse_id: Optional target EVSE ID (None or 0 for any).
                group_id_token: Optional group authorization token.
                charging_profile: Optional charging profile.
                **kwargs: Additional parameters.

        Returns:
                RequestStartTransaction response.
        """
        token_str = (
            id_token.id_token if hasattr(id_token, "id_token") else str(id_token)
        )
        self._log(
            f"RequestStartTransaction: evse_id={evse_id}, id_token={token_str}",
        )

        target_evse_id: Optional[int] = None
        if evse_id is not None and evse_id != 0:
            if evse_id < 0:
                self._log(
                    f"Invalid evse_id: {evse_id}",
                    level=logging.WARNING,
                )
                return call_result.RequestStartTransaction(
                    status=RequestStartStopStatusEnumType.rejected,
                )
            target_evse_id = evse_id

        if self.command_queue:
            self._log(
                f"Enqueuing START for "
                f"{'evse ' + str(target_evse_id) if target_evse_id else 'any evse'}",
                level=logging.DEBUG,
            )
            self.command_queue.put(
                {
                    "action": "START",
                    "connector_id": target_evse_id,
                    "id_tag": token_str,
                    "timeout": self.response_timeout,
                }
            )
            return call_result.RequestStartTransaction(
                status=RequestStartStopStatusEnumType.accepted,
            )

        return call_result.RequestStartTransaction(
            status=RequestStartStopStatusEnumType.rejected,
        )

    @on("RequestStopTransaction")
    async def on_request_stop_transaction(
        self,
        transaction_id: str,
        **kwargs: Any,
    ) -> call_result.RequestStopTransaction:
        """
        Handle RequestStopTransaction request from CSMS.

        Finds the EVSE with the matching transaction and queues a STOP
        command for the Engine.

        Args:
                transaction_id: The string transaction ID to stop.
                **kwargs: Additional parameters.

        Returns:
                RequestStopTransaction response.
        """
        self._log(
            f"RequestStopTransaction: transaction_id={transaction_id}",
        )

        matching_evse: Optional[int] = None
        for evse_id, tx_id in self.transaction_manager.active_transactions.items():
            if tx_id == transaction_id:
                matching_evse = evse_id
                break

        if matching_evse is None:
            self._log(
                f"No active transaction: {transaction_id}",
                level=logging.WARNING,
            )
            return call_result.RequestStopTransaction(
                status=RequestStartStopStatusEnumType.rejected,
            )

        if self.command_queue:
            self._log(
                f"Enqueuing STOP for tx {transaction_id}",
                level=logging.DEBUG,
            )
            self.command_queue.put(
                {
                    "action": "STOP",
                    "connector_id": matching_evse,
                    "reason": "Remote",
                }
            )
            return call_result.RequestStopTransaction(
                status=RequestStartStopStatusEnumType.accepted,
            )

        return call_result.RequestStopTransaction(
            status=RequestStartStopStatusEnumType.rejected,
        )

    @on("TriggerMessage")
    async def on_trigger_message(
        self,
        requested_message: Any,
        evse: Optional[Any] = None,
        **kwargs: Any,
    ) -> call_result.TriggerMessage:
        """
        Handle TriggerMessage request from CSMS.

        Supports the simulator's built-in trigger set for OCPP 2.0.1.

        Args:
                requested_message: MessageTriggerEnumType value.
                evse: Optional EVSEType target.
                **kwargs: Additional parameters.

        Returns:
                TriggerMessage response.
        """
        try:
            trigger = (
                requested_message
                if isinstance(requested_message, MessageTriggerEnumType)
                else MessageTriggerEnumType(requested_message)
            )
        except (TypeError, ValueError):
            self._log(
                f"TriggerMessage: unsupported message={requested_message}",
                level=logging.WARNING,
            )
            return call_result.TriggerMessage(
                status=TriggerMessageStatusEnumType.not_implemented,
            )

        self._log(f"TriggerMessage: requested_message={trigger.value}")

        if trigger == MessageTriggerEnumType.boot_notification:
            self._schedule_background_send(self.send_boot_notification(), trigger.value)
            return call_result.TriggerMessage(
                status=TriggerMessageStatusEnumType.accepted,
            )

        if trigger == MessageTriggerEnumType.heartbeat:
            self._schedule_background_send(self.send_heartbeat(), trigger.value)
            return call_result.TriggerMessage(
                status=TriggerMessageStatusEnumType.accepted,
            )

        if trigger == MessageTriggerEnumType.status_notification:
            evse_id = evse.id if evse and hasattr(evse, "id") else None
            if evse_id is None or self.get_connector_status is None:
                return call_result.TriggerMessage(
                    status=TriggerMessageStatusEnumType.rejected,
                )

            status = self.get_connector_status(evse_id)
            if status is None:
                return call_result.TriggerMessage(
                    status=TriggerMessageStatusEnumType.rejected,
                )

            self._schedule_background_send(
                self.send_status_notification(
                    connector_id=evse_id,
                    status=status,
                ),
                trigger.value,
            )
            return call_result.TriggerMessage(
                status=TriggerMessageStatusEnumType.accepted,
            )

        if trigger == MessageTriggerEnumType.meter_values:
            evse_id = evse.id if evse and hasattr(evse, "id") else None
            if evse_id is None or self.get_meter_snapshot is None:
                return call_result.TriggerMessage(
                    status=TriggerMessageStatusEnumType.rejected,
                )

            snapshot = self.get_meter_snapshot(evse_id)
            if snapshot is None or len(snapshot) != 2:
                return call_result.TriggerMessage(
                    status=TriggerMessageStatusEnumType.rejected,
                )

            value, _transaction_id = snapshot
            self._schedule_background_send(
                self.send_meter_values(
                    connector_id=evse_id,
                    value=value,
                ),
                trigger.value,
            )
            return call_result.TriggerMessage(
                status=TriggerMessageStatusEnumType.accepted,
            )

        return call_result.TriggerMessage(
            status=TriggerMessageStatusEnumType.not_implemented,
        )

    @on("ChangeAvailability")
    async def on_change_availability(
        self,
        operational_status: Any,
        evse: Optional[Any] = None,
        **kwargs: Any,
    ) -> call_result.ChangeAvailability:
        """
        Handle ChangeAvailability request from CSMS.

        Sets an EVSE (or all EVSEs when no evse specified) to Operative
        or Inoperative.

        Args:
                operational_status: OperationalStatusEnumType value.
                evse: Optional EVSEType target.
                **kwargs: Additional parameters.

        Returns:
                ChangeAvailability response.
        """
        try:
            avail_type = (
                operational_status
                if isinstance(operational_status, OperationalStatusEnumType)
                else OperationalStatusEnumType(operational_status)
            )
        except (TypeError, ValueError):
            self._log(
                f"ChangeAvailability: unknown type '{operational_status}'",
                level=logging.WARNING,
            )
            return call_result.ChangeAvailability(
                status=ChangeAvailabilityStatusEnumType.rejected,
            )

        if self.set_connector_availability is None:
            self._log(
                "ChangeAvailability: engine callback unavailable",
                level=logging.WARNING,
            )
            return call_result.ChangeAvailability(
                status=ChangeAvailabilityStatusEnumType.rejected,
            )

        evse_id = 0
        if evse and hasattr(evse, "id"):
            evse_id = evse.id

        if evse_id != 0 and evse_id not in self.known_connector_ids:
            self._log(
                f"ChangeAvailability: unknown evse_id={evse_id}",
                level=logging.WARNING,
            )
            return call_result.ChangeAvailability(
                status=ChangeAvailabilityStatusEnumType.rejected,
            )

        result = self.set_connector_availability(evse_id, avail_type.value)

        status_map = {
            "accepted": ChangeAvailabilityStatusEnumType.accepted,
            "scheduled": ChangeAvailabilityStatusEnumType.scheduled,
            "rejected": ChangeAvailabilityStatusEnumType.rejected,
        }
        status = status_map.get(result, ChangeAvailabilityStatusEnumType.rejected)
        return call_result.ChangeAvailability(status=status)

    @on("UnlockConnector")
    async def on_unlock_connector(
        self,
        evse_id: int,
        connector_id: int,
        **kwargs: Any,
    ) -> call_result.UnlockConnector:
        """
        Handle UnlockConnector request from CSMS.

        Simulates releasing the physical cable lock. If a transaction is
        active on the EVSE, it is stopped first.

        Args:
                evse_id: Target EVSE ID.
                connector_id: Target connector ID within the EVSE.
                **kwargs: Additional parameters.

        Returns:
                UnlockConnector response.
        """
        self._log(f"UnlockConnector: evse_id={evse_id}")

        if evse_id not in self.known_connector_ids:
            self._log(
                f"UnlockConnector: unknown evse_id={evse_id}",
                level=logging.WARNING,
            )
            return call_result.UnlockConnector(
                status=UnlockStatusEnumType.unknown_connector,
            )

        if (
            self.transaction_manager.get_transaction_id(evse_id) is not None
            and self.command_queue is not None
        ):
            self._log(
                f"UnlockConnector: stopping active transaction on evse {evse_id}",
                level=logging.DEBUG,
            )
            self.command_queue.put(
                {"action": "STOP", "connector_id": evse_id, "reason": "UnlockCommand"}
            )

        return call_result.UnlockConnector(status=UnlockStatusEnumType.unlocked)

    @on("Reset")
    async def on_reset(
        self,
        type: Any,
        evse_id: Optional[int] = None,
        **kwargs: Any,
    ) -> call_result.Reset:
        """
        Handle Reset request from CSMS.

        Accepts Immediate and OnIdle reset types, maps them to the engine's
        Hard/Soft reset commands.

        OCPP 2.0.1 mapping:
                Immediate → Hard reset (interrupts active transactions)
                OnIdle → Soft reset (waits for transactions to complete)

        Args:
                type: ResetEnumType value (Immediate or OnIdle).
                evse_id: Optional target EVSE.
                **kwargs: Additional parameters.

        Returns:
                Reset response.
        """
        self._log(f"Reset: type={type}")

        try:
            reset_type = (
                type if isinstance(type, ResetEnumType) else ResetEnumType(type)
            )
        except (TypeError, ValueError):
            self._log(
                f"Invalid reset type: {type}",
                level=logging.WARNING,
            )
            return call_result.Reset(status=ResetStatusEnumType.rejected)

        if self.command_queue is None:
            self._log(
                "Reset rejected: command queue unavailable",
                level=logging.WARNING,
            )
            return call_result.Reset(status=ResetStatusEnumType.rejected)

        engine_reset_type = "Hard" if reset_type == ResetEnumType.immediate else "Soft"
        self.command_queue.put({"action": "RESET", "type": engine_reset_type})
        self.on_reset_requested.emit(reset_type=engine_reset_type)
        return call_result.Reset(status=ResetStatusEnumType.accepted)
