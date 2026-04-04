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

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ocpp.routing import on
from ocpp.v201 import ChargePoint as cp
from ocpp.v201 import call, call_result
from ocpp.v201.datatypes import (
    ChargingStationType,
    ComponentType,
    CostType,
    EVSEType,
    EventDataType,
    GetVariableResultType,
    IdTokenType,
    MessageContentType,
    MessageInfoType,
    MeterValueType,
    MonitoringDataType,
    SampledValueType,
    SetMonitoringResultType,
    SetVariableResultType,
    StatusInfoType,
    TransactionType,
    VariableType,
)
from ocpp.v201.enums import (
    AttributeEnumType,
    BootReasonEnumType,
    CancelReservationStatusEnumType,
    ChangeAvailabilityStatusEnumType,
    ChargingStateEnumType,
    ClearCacheStatusEnumType,
    ClearMessageStatusEnumType,
    ClearMonitoringStatusEnumType,
    ConnectorStatusEnumType,
    CustomerInformationStatusEnumType,
    DataTransferStatusEnumType,
    DisplayMessageStatusEnumType,
    EventNotificationEnumType,
    EventTriggerEnumType,
    FirmwareStatusEnumType,
    GenericDeviceModelStatusEnumType,
    GenericStatusEnumType,
    GetDisplayMessagesStatusEnumType,
    GetVariableStatusEnumType,
    IdTokenEnumType,
    LogEnumType,
    LogStatusEnumType,
    MeasurandEnumType,
    MessagePriorityEnumType,
    MessageStateEnumType,
    MessageTriggerEnumType,
    MonitorEnumType,
    OperationalStatusEnumType,
    PublishFirmwareStatusEnumType,
    ReadingContextEnumType,
    ReasonEnumType,
    RegistrationStatusEnumType,
    RequestStartStopStatusEnumType,
    ReservationUpdateStatusEnumType,
    ResetEnumType,
    ResetStatusEnumType,
    ReserveNowStatusEnumType,
    SendLocalListStatusEnumType,
    SetMonitoringStatusEnumType,
    SetVariableStatusEnumType,
    TransactionEventEnumType,
    TriggerMessageStatusEnumType,
    TriggerReasonEnumType,
    UnlockStatusEnumType,
    UnpublishFirmwareStatusEnumType,
    UpdateEnumType,
    UpdateFirmwareStatusEnumType,
    UploadLogStatusEnumType,
)

from chargeghost_evse.bridge.message_queue import MessageQueue
from chargeghost_evse.ocpp_adapter.base_adapter import BaseAdapter
from chargeghost_evse.util.event import Event
from chargeghost_evse.ocpp_adapter.charging_profile_manager_v201 import (
    ChargingProfileManagerV201,
)
from chargeghost_evse.ocpp_adapter.device_model.component import Component
from chargeghost_evse.ocpp_adapter.device_model.device_model import (
    ChargingStationDeviceModel,
)
from chargeghost_evse.ocpp_adapter.device_model.monitoring import (
    MonitorManager,
    VariableMonitor,
)
from chargeghost_evse.ocpp_adapter.firmware_manager_v201 import FirmwareManagerV201
from chargeghost_evse.ocpp_adapter.local_auth_list_v201 import (
    LocalAuthListManagerV201,
)
from chargeghost_evse.ocpp_adapter.transaction_manager_v201 import (
    TransactionManagerV201,
    TxStartStopPointConfig,
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

_TRIGGER_REASON_MAP: dict[str, TriggerReasonEnumType] = {
    "CablePluggedIn": TriggerReasonEnumType.cable_plugged_in,
    "Authorized": TriggerReasonEnumType.authorized,
    "ChargingStateChanged": TriggerReasonEnumType.charging_state_changed,
    "ChargingRateChanged": TriggerReasonEnumType.charging_rate_changed,
    "MeterValuePeriodic": TriggerReasonEnumType.meter_value_periodic,
    "MeterValueClock": TriggerReasonEnumType.meter_value_clock,
    "EVDeparted": TriggerReasonEnumType.ev_departed,
    "StopAuthorized": TriggerReasonEnumType.stop_authorized,
    "DeAuthorized": TriggerReasonEnumType.deauthorized,
    "EnergyLimitReached": TriggerReasonEnumType.energy_limit_reached,
    "Trigger": TriggerReasonEnumType.trigger,
    "UnlockCommand": TriggerReasonEnumType.unlock_command,
    "RemoteStart": TriggerReasonEnumType.remote_start,
    "RemoteStop": TriggerReasonEnumType.remote_stop,
}

_CHARGE_STATE_MAP: dict[str, ChargingStateEnumType] = {
    "Charging": ChargingStateEnumType.charging,
    "SuspendedEV": ChargingStateEnumType.suspended_ev,
    "SuspendedEVSE": ChargingStateEnumType.suspended_evse,
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


def _map_trigger_reason(reason: str) -> TriggerReasonEnumType:
    return _TRIGGER_REASON_MAP.get(reason, TriggerReasonEnumType.trigger)


def _map_charge_state(state: str) -> Optional[ChargingStateEnumType]:
    return _CHARGE_STATE_MAP.get(state)


_STOP_REASON_TO_TRIGGER: dict[str, str] = {
    "Local": "StopRequested",
    "Remote": "RemoteStop",
    "EVDisconnected": "EVDeparted",
    "UnlockCommand": "UnlockCommand",
    "StoppedByEV": "EVDeparted",
    "Timeout": "StopRequested",
    "Other": "StopRequested",
    "EmergencyStop": "StopRequested",
    "PowerLoss": "StopRequested",
    "Reboot": "StopRequested",
    "HardReset": "StopRequested",
    "SoftReset": "StopRequested",
    "EnergyLimitReached": "EnergyLimitReached",
    "SOCLimitReached": "EnergyLimitReached",
    "TimeLimitReached": "EnergyLimitReached",
    "DeAuthorized": "DeAuthorized",
}


def _map_stop_reason_to_trigger_reason(reason: Optional[str]) -> str:
    if reason is None:
        return "StopRequested"
    return _STOP_REASON_TO_TRIGGER.get(reason, "StopRequested")


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
        "GetVariables",
        "SetVariables",
        "GetLog",
        "LogStatusNotification",
    }

    def __init__(
        self,
        id: str,
        connection: Any,
        command_queue: Any = None,
        response_timeout: int = 30,
        charge_point_model: str = "ChargeGhostV2",
        charge_point_vendor: str = "ChargeGhost",
        fault_manager: Optional[Any] = None,
        tx_start_stop_config: Optional[TxStartStopPointConfig] = None,
    ) -> None:
        cp.__init__(self, id, connection, response_timeout)
        self._init_base(
            command_queue=command_queue,
            charge_point_model=charge_point_model,
            charge_point_vendor=charge_point_vendor,
            response_timeout=response_timeout,
            protocol_version="ocpp2.0.1",
            fault_manager=fault_manager,
        )
        self.transaction_manager = TransactionManagerV201()
        self._tx_start_stop_config = tx_start_stop_config or TxStartStopPointConfig()
        self.charging_profile_manager = ChargingProfileManagerV201()
        self.local_auth_manager = LocalAuthListManagerV201()
        self.firmware_manager = FirmwareManagerV201()
        self.monitor_manager = MonitorManager()
        self._monitor_seq_no: int = 0
        self._event_seq_no: int = 0
        self.device_model = ChargingStationDeviceModel()
        self.message_queue: Optional[MessageQueue] = None
        self._display_messages: dict[int, MessageInfoType] = {}
        self._next_message_id: int = 0
        self._transaction_costs: dict[str, list[CostType]] = {}
        self.on_display_message = Event()
        self.cost_updated = Event()
        self._log_task: Optional[asyncio.Task] = None
        self._log_request_id: Optional[int] = None
        self.monitor_manager.on_threshold_breach.subscribe(
            self._on_monitor_threshold_breach
        )

    def _on_monitor_threshold_breach(self, **kwargs: Any) -> None:
        monitors = kwargs.get("monitors", [])
        self._log(
            f"Monitor threshold breach: {len(monitors)} monitor(s)",
            level=logging.WARNING,
        )

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
        if self._fault_manager is not None:
            result = self._fault_manager.consume_if_active("delayed_response")
            if result.triggered:
                delay = 5.0
                state = self._fault_manager.peek("delayed_response")
                if state and state.config and state.config.parameters:
                    delay = float(state.config.parameters.get("delay_seconds", 5.0))
                self._log(
                    f"Fault injection: delayed_response delay={delay}s",
                    level=logging.DEBUG,
                    fault_id="delayed_response",
                )
                await asyncio.sleep(delay)
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
        trigger_reason: Optional[str] = None,
        ev_connected: bool = False,
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
                trigger_reason: Optional trigger reason string override.
                ev_connected: Whether the EV is physically connected.

        Returns:
                Tuple of (response, transaction_id_string).
        """
        tx_id = self.transaction_manager.begin_transaction(connector_id)
        seq_no = self.transaction_manager.get_next_seq_no(tx_id)

        reason_str = (
            trigger_reason
            or self._tx_start_stop_config.trigger_reason_for_start(
                ev_connected=ev_connected,
                authorized=True,
                energy_transfer=False,
            )
            or "Authorized"
        )

        reason = _map_trigger_reason(reason_str)

        self._log(
            f"TransactionEvent(Started): evse={connector_id}, "
            f"tx_id={tx_id}, seq_no={seq_no}, reason={reason_str}",
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
            trigger_reason=reason,
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

        self._handle_transaction_event_response(response, tx_id)

        return response, tx_id

    def _handle_transaction_event_response(
        self, response: Any, transaction_id: str
    ) -> None:
        """
        Process response fields from TransactionEvent response.

        Handles: total_cost, charging_priority, id_token_info,
        updated_personal_message.

        Args:
                response: The TransactionEvent response from CSMS.
                transaction_id: The transaction ID this response is for.
        """
        if response is None:
            return

        total_cost = getattr(response, "total_cost", None)
        if total_cost is not None:
            self._transaction_costs[transaction_id] = total_cost
            self.cost_updated.emit(
                transaction_id=transaction_id,
                total_cost=total_cost,
            )
            self._log(
                f"TransactionEvent response: total_cost={total_cost}",
                level=logging.DEBUG,
            )

        charging_priority = getattr(response, "charging_priority", None)
        if charging_priority is not None:
            self._log(
                f"TransactionEvent response: charging_priority={charging_priority}",
                level=logging.DEBUG,
            )

        id_token_info = getattr(response, "id_token_info", None)
        if id_token_info is not None:
            status = (
                id_token_info.status.value
                if hasattr(id_token_info.status, "value")
                else str(id_token_info.status)
            )
            self._log(
                f"TransactionEvent response: id_token_info status={status}",
                level=logging.DEBUG,
            )

        updated_personal_message = getattr(response, "updated_personal_message", None)
        if updated_personal_message is not None:
            self._log(
                "TransactionEvent response: updated_personal_message received",
                level=logging.DEBUG,
            )

    async def send_transaction_event_updated(
        self,
        connector_id: int,
        transaction_id: str,
        timestamp: str,
        meter_value: Optional[list[MeterValueType]] = None,
        trigger_reason: Optional[str] = None,
        charging_state: Optional[str] = None,
    ) -> Any:
        """
        Send TransactionEvent(Updated) to the Central System.

        Args:
                connector_id: The EVSE with an active transaction.
                transaction_id: The active transaction ID.
                timestamp: ISO 8601 timestamp of the update.
                meter_value: Optional meter value readings to embed.
                trigger_reason: Reason string for the update event.
                charging_state: Optional charging state string.

        Returns:
                TransactionEvent response.
        """
        seq_no = self.transaction_manager.get_next_seq_no(transaction_id)

        reason = _map_trigger_reason(trigger_reason or "MeterValuePeriodic")

        tx_info = TransactionType(transaction_id=transaction_id)
        if charging_state is not None:
            mapped_state = _map_charge_state(charging_state)
            if mapped_state is not None:
                tx_info = TransactionType(
                    transaction_id=transaction_id,
                    charging_state=mapped_state,
                )

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

        self._handle_transaction_event_response(response, transaction_id)

        return response

    async def send_transaction_event_ended(
        self,
        connector_id: int,
        transaction_id: str,
        timestamp: str,
        meter_stop: int,
        reason: Optional[str] = None,
        meter_history: Optional[list[dict]] = None,
        trigger_reason: Optional[str] = None,
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
                trigger_reason: Optional trigger reason string override.

        Returns:
                TransactionEvent response.
        """
        seq_no = self.transaction_manager.get_next_seq_no(transaction_id)
        stopped_reason = _map_stop_reason(reason)

        reason_str = trigger_reason or _map_stop_reason_to_trigger_reason(reason)
        mapped_reason = _map_trigger_reason(reason_str)

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
            trigger_reason=mapped_reason,
            seq_no=seq_no,
            transaction_info=tx_info,
            meter_value=meter_value,
            offline=False,
            evse=EVSEType(id=connector_id, connector_id=1),
        )

        response: call_result.TransactionEvent = await self.call(request)

        self._handle_transaction_event_response(response, transaction_id)

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

    def _next_event_id(self) -> int:
        self._event_seq_no += 1
        return self._event_seq_no

    async def send_notify_event(
        self,
        connector_id: int,
        event_id: Optional[int] = None,
        trigger: EventTriggerEnumType = EventTriggerEnumType.alerting,
        actual_value: str = "",
        event_notification_type: EventNotificationEnumType = EventNotificationEnumType.hard_wired_monitor,
        component_name: str = "EVSE",
        variable_name: str = "",
        severity: int = 0,
        transaction_id: Optional[str] = None,
        tech_code: Optional[str] = None,
        tech_info: Optional[str] = None,
        cleared: bool = False,
        variable_monitoring_id: Optional[int] = None,
    ) -> Any:
        timestamp = datetime.now(timezone.utc).isoformat()

        if event_id is None:
            event_id = self._next_event_id()
        else:
            self._event_seq_no = max(self._event_seq_no, event_id)

        evse = EVSEType(id=connector_id, connector_id=1)
        component = ComponentType(name=component_name, evse=evse)
        variable = VariableType(name=variable_name)

        event_data = EventDataType(
            event_id=event_id,
            timestamp=timestamp,
            trigger=trigger,
            actual_value=actual_value,
            event_notification_type=event_notification_type,
            component=component,
            variable=variable,
            cause=severity,
            tech_code=tech_code,
            tech_info=tech_info,
            transaction_id=transaction_id,
            cleared=cleared,
            variable_monitoring_id=variable_monitoring_id,
        )

        request = call.NotifyEvent(
            generated_at=timestamp,
            seq_no=self._event_seq_no,
            event_data=[event_data],
        )

        self._log(
            f"NotifyEvent: evse={connector_id}, event_id={event_id}, "
            f"type={event_notification_type.value}, trigger={trigger.value}",
        )

        response: call_result.NotifyEvent = await self.call(request)
        return response

    async def send_event_notification(
        self,
        connector_id: int,
        trigger: EventTriggerEnumType,
        actual_value: str,
        event_notification_type: EventNotificationEnumType,
        component_name: str,
        variable_name: str,
        severity: int = 0,
        transaction_id: Optional[str] = None,
        tech_code: Optional[str] = None,
        tech_info: Optional[str] = None,
        cleared: bool = False,
        variable_monitoring_id: Optional[int] = None,
    ) -> Any:
        return await self.send_notify_event(
            connector_id=connector_id,
            trigger=trigger,
            actual_value=actual_value,
            event_notification_type=event_notification_type,
            component_name=component_name,
            variable_name=variable_name,
            severity=severity,
            transaction_id=transaction_id,
            tech_code=tech_code,
            tech_info=tech_info,
            cleared=cleared,
            variable_monitoring_id=variable_monitoring_id,
        )

    def _on_monitor_threshold_breach(self, monitors: list[Any]) -> None:
        for monitor in monitors:
            component = monitor.component
            evse_id = component.evse.id if component.evse else 0
            component_name = component.name or "EVSE"
            variable_name = monitor.variable.name if monitor.variable else ""

            coro = self.send_event_notification(
                connector_id=evse_id,
                trigger=EventTriggerEnumType.alerting,
                actual_value=str(monitor.value),
                event_notification_type=EventNotificationEnumType.custom_monitor,
                component_name=component_name,
                variable_name=variable_name,
                severity=monitor.severity,
                transaction_id=monitor.transaction_id,
                variable_monitoring_id=monitor.id,
            )
            self._schedule_background_send(coro, "NotifyEvent")

    async def send_security_event_notification(
        self,
        event_type: str,
        timestamp: datetime,
        tech_info: Optional[str] = None,
    ) -> Any:
        """
        Send SecurityEventNotification to the Central System.

        Reports security-related events such as failed authentication
        attempts, firmware tampering, reset events, or configuration changes.

        Args:
                event_type: Security event type (e.g. "FailedToAuthenticate").
                timestamp: When the event occurred.
                tech_info: Optional technical details about the event.

        Returns:
                SecurityEventNotification response.
        """
        request = call.SecurityEventNotification(
            type=event_type,
            timestamp=timestamp.isoformat(),
            tech_info=tech_info,
        )
        self._log(
            f"SecurityEventNotification: type={event_type}, tech_info={tech_info}",
        )
        response: call_result.SecurityEventNotification = await self.call(request)
        return response

    # -------------------------------------------------------------------------
    # Incoming OCPP Message Handlers
    # -------------------------------------------------------------------------

    def _resolve_component(self, ocpp_component: Any) -> Optional[Component]:
        if ocpp_component is None:
            return None
        evse_id = None
        evse = self._item_attr(ocpp_component, "evse")
        if evse is not None:
            evse_id = self._item_attr(evse, "id")
        instance = self._item_attr(ocpp_component, "instance")
        name = self._item_attr(ocpp_component, "name", "")
        return self.device_model.find_component(
            name=name,
            instance=instance,
            evse_id=evse_id,
        )

    def _resolve_attribute_type(self, ocpp_attribute_type: Optional[Any]) -> str:
        if ocpp_attribute_type is None:
            return "Actual"
        if isinstance(ocpp_attribute_type, AttributeEnumType):
            return ocpp_attribute_type.value
        try:
            return AttributeEnumType(ocpp_attribute_type).value
        except (ValueError, TypeError):
            return "Actual"

    @staticmethod
    def _item_attr(item: Any, key: str, default: Any = None) -> Any:
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    @on("GetVariables")
    async def on_get_variables(
        self,
        get_variable_data: list[Any],
        **kwargs: Any,
    ) -> call_result.GetVariables:
        self._log(f"GetVariables: {len(get_variable_data)} request(s)")

        results: list[GetVariableResultType] = []
        for item in get_variable_data:
            ocpp_component = self._item_attr(item, "component")
            ocpp_variable = self._item_attr(item, "variable")
            component = self._resolve_component(ocpp_component)
            variable_name = self._item_attr(ocpp_variable, "name", "")
            variable_instance = self._item_attr(ocpp_variable, "instance")
            attribute_type = self._resolve_attribute_type(
                self._item_attr(item, "attribute_type")
            )

            if component is None:
                results.append(
                    GetVariableResultType(
                        attribute_status=GetVariableStatusEnumType.unknown_component,
                        component=ocpp_component,
                        variable=ocpp_variable,
                        attribute_type=attribute_type,
                    )
                )
                continue

            var = self.device_model.find_variable(
                component, variable_name, variable_instance
            )
            if var is None:
                results.append(
                    GetVariableResultType(
                        attribute_status=GetVariableStatusEnumType.unknown_variable,
                        component=ocpp_component,
                        variable=ocpp_variable,
                        attribute_type=attribute_type,
                    )
                )
                continue

            attr = var.attributes.get(attribute_type)
            if attr is None:
                results.append(
                    GetVariableResultType(
                        attribute_status=GetVariableStatusEnumType.not_supported_attribute_type,
                        component=ocpp_component,
                        variable=ocpp_variable,
                        attribute_type=attribute_type,
                    )
                )
                continue

            results.append(
                GetVariableResultType(
                    attribute_status=GetVariableStatusEnumType.accepted,
                    component=ocpp_component,
                    variable=ocpp_variable,
                    attribute_type=attribute_type,
                    attribute_value=attr.value,
                )
            )

        return call_result.GetVariables(get_variable_result=results)

    @on("SetVariables")
    async def on_set_variables(
        self,
        set_variable_data: list[Any],
        **kwargs: Any,
    ) -> call_result.SetVariables:
        self._log(f"SetVariables: {len(set_variable_data)} request(s)")

        results: list[SetVariableResultType] = []
        for item in set_variable_data:
            ocpp_component = self._item_attr(item, "component")
            ocpp_variable = self._item_attr(item, "variable")
            component = self._resolve_component(ocpp_component)
            variable_name = self._item_attr(ocpp_variable, "name", "")
            variable_instance = self._item_attr(ocpp_variable, "instance")
            attribute_type = self._resolve_attribute_type(
                self._item_attr(item, "attribute_type")
            )
            new_value = self._item_attr(item, "attribute_value", "")

            if component is None:
                results.append(
                    SetVariableResultType(
                        attribute_status=SetVariableStatusEnumType.unknown_component,
                        component=ocpp_component,
                        variable=ocpp_variable,
                        attribute_type=attribute_type,
                    )
                )
                continue

            var = self.device_model.find_variable(
                component, variable_name, variable_instance
            )
            if var is None:
                results.append(
                    SetVariableResultType(
                        attribute_status=SetVariableStatusEnumType.unknown_variable,
                        component=ocpp_component,
                        variable=ocpp_variable,
                        attribute_type=attribute_type,
                    )
                )
                continue

            attr = var.attributes.get(attribute_type)
            if attr is None:
                results.append(
                    SetVariableResultType(
                        attribute_status=SetVariableStatusEnumType.not_supported_attribute_type,
                        component=ocpp_component,
                        variable=ocpp_variable,
                        attribute_type=attribute_type,
                    )
                )
                continue

            if attr.mutability == "ReadOnly":
                results.append(
                    SetVariableResultType(
                        attribute_status=SetVariableStatusEnumType.rejected,
                        component=ocpp_component,
                        variable=ocpp_variable,
                        attribute_type=attribute_type,
                        attribute_status_info=StatusInfoType(
                            reason_code="ReadOnly",
                            additional_info="Variable attribute is read-only",
                        ),
                    )
                )
                continue

            success = self.device_model.set_variable(
                component, variable_name, attribute_type, new_value
            )
            if not success:
                results.append(
                    SetVariableResultType(
                        attribute_status=SetVariableStatusEnumType.rejected,
                        component=ocpp_component,
                        variable=ocpp_variable,
                        attribute_type=attribute_type,
                        attribute_status_info=StatusInfoType(
                            reason_code="InternalError",
                            additional_info="Failed to write variable",
                        ),
                    )
                )
                continue

            status = SetVariableStatusEnumType.accepted
            if attr.mutability == "RebootRequired":
                status = SetVariableStatusEnumType.reboot_required

            results.append(
                SetVariableResultType(
                    attribute_status=status,
                    component=ocpp_component,
                    variable=ocpp_variable,
                    attribute_type=attribute_type,
                )
            )

        return call_result.SetVariables(set_variable_result=results)

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

        if self._fault_manager is not None:
            result = self._fault_manager.consume_if_active("rejected_action")
            if result.triggered:
                self._log(
                    "Fault injection: rejected_action on RequestStartTransaction",
                    level=logging.DEBUG,
                    fault_id="rejected_action",
                )
                return call_result.RequestStartTransaction(
                    status=RequestStartStopStatusEnumType.rejected,
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
        if self._fault_manager is not None:
            result = self._fault_manager.consume_if_active(
                "trigger_message_not_implemented"
            )
            if result.triggered:
                self._log(
                    "Fault injection: trigger_message_not_implemented",
                    level=logging.DEBUG,
                    fault_id="trigger_message_not_implemented",
                )
                return call_result.TriggerMessage(
                    status=TriggerMessageStatusEnumType.not_implemented,
                )

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

    @on("DataTransfer")
    async def on_data_transfer(
        self,
        vendor_id: str,
        message_id: Optional[str] = None,
        data: Any = None,
        **kwargs: Any,
    ) -> call_result.DataTransfer:
        self._log(
            f"DataTransfer: vendor_id={vendor_id}, message_id={message_id}",
        )

        if not vendor_id:
            return call_result.DataTransfer(
                status=DataTransferStatusEnumType.rejected,
            )

        return call_result.DataTransfer(
            status=DataTransferStatusEnumType.unknown_vendor_id,
            data=data,
        )

    async def send_data_transfer(
        self,
        vendor_id: str,
        message_id: Optional[str] = None,
        data: Any = None,
    ) -> call_result.DataTransfer:
        request = call.DataTransfer(
            vendor_id=vendor_id,
            message_id=message_id,
            data=data,
        )
        self._log(
            f"DataTransfer TX: vendor_id={vendor_id}, message_id={message_id}",
        )
        response: call_result.DataTransfer = await self.call(request)
        return response

    async def send_notify_monitoring_report(
        self,
        request_id: int,
        monitors: list[VariableMonitor],
    ) -> Any:
        from datetime import datetime, timezone

        self._monitor_seq_no += 1
        timestamp = datetime.now(timezone.utc).isoformat()

        monitor_data_list: list[MonitoringDataType] = []
        for m in monitors:
            tx_id_str = m.transaction_id
            transaction = tx_id_str is not None
            vm_type = m.to_variable_monitoring_type(transaction=transaction)
            md = MonitoringDataType(
                component=m.component,
                variable=m.variable,
                variable_monitoring=[vm_type],
            )
            monitor_data_list.append(md)

        request = call.NotifyMonitoringReport(
            request_id=request_id,
            seq_no=self._monitor_seq_no,
            generated_at=timestamp,
            monitor=monitor_data_list if monitor_data_list else None,
        )

        self._log(
            f"NotifyMonitoringReport: request_id={request_id}, "
            f"monitors={len(monitor_data_list)}",
        )

        response: call_result.NotifyMonitoringReport = await self.call(request)
        return response

    @on("SetVariableMonitoring")
    async def on_set_variable_monitoring(
        self,
        set_monitoring_data: list[Any],
        **kwargs: Any,
    ) -> call_result.SetVariableMonitoring:
        self._log(f"SetVariableMonitoring: {len(set_monitoring_data)} monitor(s)")

        results: list[SetMonitoringResultType] = []
        for item in set_monitoring_data:
            comp = item.component if hasattr(item, "component") else None
            var = item.variable if hasattr(item, "variable") else None
            monitor_type = (
                item.type.value if hasattr(item.type, "value") else str(item.type)
            )
            severity = item.severity if hasattr(item, "severity") else 0
            value = item.value if hasattr(item, "value") else 0.0
            provided_id = item.id if hasattr(item, "id") else 0
            tx_flag = item.transaction if hasattr(item, "transaction") else None

            transaction_id: Optional[str] = None
            if tx_flag and hasattr(comp, "evse") and comp.evse is not None:
                tx_id = self.transaction_manager.get_transaction_id(comp.evse.id)
                if tx_id is not None:
                    transaction_id = str(tx_id)

            try:
                monitor = VariableMonitor(
                    id=provided_id or 0,
                    component=comp,
                    variable=var,
                    monitor_type=monitor_type,
                    value=value,
                    severity=severity,
                    transaction_id=transaction_id,
                )
                assigned_id = self.monitor_manager.set_monitor(monitor)
                results.append(
                    SetMonitoringResultType(
                        status=SetMonitoringStatusEnumType.accepted,
                        type=MonitorEnumType(monitor_type),
                        severity=severity,
                        component=comp,
                        variable=var,
                        id=assigned_id,
                    )
                )
            except (ValueError, TypeError):
                results.append(
                    SetMonitoringResultType(
                        status=SetMonitoringStatusEnumType.rejected,
                        type=MonitorEnumType(monitor_type),
                        severity=severity,
                        component=comp,
                        variable=var,
                        id=provided_id,
                    )
                )

        return call_result.SetVariableMonitoring(set_monitoring_result=results)

    @on("ClearVariableMonitoring")
    async def on_clear_variable_monitoring(
        self,
        id: list[int],
        **kwargs: Any,
    ) -> call_result.ClearVariableMonitoring:
        self._log(f"ClearVariableMonitoring: {len(id)} monitor(s)")

        results: list[ClearMonitoringStatusEnumType] = []
        for monitor_id in id:
            if self.monitor_manager.clear_monitor(monitor_id):
                results.append(ClearMonitoringStatusEnumType.accepted)
            else:
                results.append(ClearMonitoringStatusEnumType.not_found)

        return call_result.ClearVariableMonitoring(clear_monitoring_result=results)

    @on("GetMonitoringReport")
    async def on_get_monitoring_report(
        self,
        request_id: int,
        component_variable: Optional[list[Any]] = None,
        monitoring_criteria: Optional[list[Any]] = None,
        **kwargs: Any,
    ) -> call_result.GetMonitoringReport:
        self._log(f"GetMonitoringReport: request_id={request_id}")

        monitors = self.monitor_manager.get_all_monitors()

        async def _send_report() -> None:
            await self.send_notify_monitoring_report(request_id, monitors)

        self._schedule_background_send(
            _send_report(),
            "NotifyMonitoringReport",
        )

        if not monitors:
            return call_result.GetMonitoringReport(
                status=GenericDeviceModelStatusEnumType.empty_result_set,
            )
        return call_result.GetMonitoringReport(
            status=GenericDeviceModelStatusEnumType.accepted,
        )

    @on("SetMonitoringBase")
    async def on_set_monitoring_base(
        self,
        monitoring_base: Any,
        **kwargs: Any,
    ) -> call_result.SetMonitoringBase:
        try:
            base_value = (
                monitoring_base.value
                if hasattr(monitoring_base, "value")
                else str(monitoring_base)
            )
        except (TypeError, ValueError):
            self._log(
                f"SetMonitoringBase: unknown type '{monitoring_base}'",
                level=logging.WARNING,
            )
            return call_result.SetMonitoringBase(
                status=GenericDeviceModelStatusEnumType.rejected,
                status_info=StatusInfoType(reason_code="InvalidType"),
            )

        self.monitor_manager.set_monitoring_base(base_value)
        self._log(f"SetMonitoringBase: {base_value}")

        return call_result.SetMonitoringBase(
            status=GenericDeviceModelStatusEnumType.accepted,
        )

    @on("SetMonitoringLevel")
    async def on_set_monitoring_level(
        self,
        severity: int,
        **kwargs: Any,
    ) -> call_result.SetMonitoringLevel:
        self._log(f"SetMonitoringLevel: severity={severity}")
        self.monitor_manager.set_severity_level(severity)
        return call_result.SetMonitoringLevel(status=GenericStatusEnumType.accepted)

    @on("GetTransactionStatus")
    async def on_get_transaction_status(
        self,
        transaction_id: Optional[str] = None,
        **kwargs: Any,
    ) -> call_result.GetTransactionStatus:
        self._log(f"GetTransactionStatus: transaction_id={transaction_id}")

        if transaction_id is not None:
            is_known = any(
                tx_id == transaction_id
                for tx_id in self.transaction_manager.active_transactions.values()
            )
            if not is_known:
                self._log(
                    f"GetTransactionStatus: unknown transaction {transaction_id}",
                    level=logging.WARNING,
                )
                return call_result.GetTransactionStatus(
                    messages_in_queue=False,
                )

        messages_in_queue = (
            self.message_queue is not None and self.message_queue.size > 0
        )

        ongoing: Optional[bool] = None
        if transaction_id is not None:
            ongoing = any(
                tx_id == transaction_id
                for tx_id in self.transaction_manager.active_transactions.values()
            )
        elif self.transaction_manager.active_transactions:
            ongoing = True

        return call_result.GetTransactionStatus(
            messages_in_queue=messages_in_queue,
            ongoing_indicator=ongoing,
        )

    @on("ReserveNow")
    async def on_reserve_now(
        self,
        id: int,
        expiry_date_time: str,
        id_token: Any,
        connector_type: Optional[Any] = None,
        evse_id: Optional[int] = None,
        group_id_token: Optional[Any] = None,
        **kwargs: Any,
    ) -> call_result.ReserveNow:
        token_str = (
            id_token.id_token if hasattr(id_token, "id_token") else str(id_token)
        )

        self._log(
            f"ReserveNow: id={id}, evse_id={evse_id}, "
            f"id_token={token_str}, expiry={expiry_date_time}",
        )

        if self.reserve_connector is None:
            return call_result.ReserveNow(status=ReserveNowStatusEnumType.rejected)

        if evse_id is None or evse_id == 0:
            target_id: Optional[int] = None
            if self.get_connector_status is not None:
                for cid in self.known_connector_ids:
                    if self.get_connector_status(cid) == "Available":
                        target_id = cid
                        break
            if target_id is None:
                return call_result.ReserveNow(
                    status=ReserveNowStatusEnumType.unavailable
                )
            evse_id = target_id
        elif evse_id not in self.known_connector_ids:
            return call_result.ReserveNow(status=ReserveNowStatusEnumType.rejected)

        try:
            parsed_expiry = datetime.fromisoformat(
                expiry_date_time.replace("Z", "+00:00")
            )
        except (AttributeError, TypeError, ValueError):
            self._log(
                f"ReserveNow: invalid expiry_date_time={expiry_date_time}",
                level=logging.WARNING,
            )
            return call_result.ReserveNow(status=ReserveNowStatusEnumType.rejected)

        result = self.reserve_connector(
            evse_id,
            id,
            token_str,
            parsed_expiry,
            None,
        )

        status_map = {
            "accepted": ReserveNowStatusEnumType.accepted,
            "occupied": ReserveNowStatusEnumType.occupied,
            "faulted": ReserveNowStatusEnumType.faulted,
            "unavailable": ReserveNowStatusEnumType.unavailable,
            "rejected": ReserveNowStatusEnumType.rejected,
        }
        return call_result.ReserveNow(
            status=status_map.get(result, ReserveNowStatusEnumType.rejected)
        )

    @on("CancelReservation")
    async def on_cancel_reservation(
        self,
        reservation_id: int,
        **kwargs: Any,
    ) -> call_result.CancelReservation:
        self._log(f"CancelReservation: reservation_id={reservation_id}")

        if self.cancel_reservation is None:
            return call_result.CancelReservation(
                status=CancelReservationStatusEnumType.rejected
            )

        result = self.cancel_reservation(reservation_id)
        status = (
            CancelReservationStatusEnumType.accepted
            if result == "accepted"
            else CancelReservationStatusEnumType.rejected
        )
        return call_result.CancelReservation(status=status)

    async def send_reservation_status_update(
        self,
        reservation_id: int,
        status: ReservationUpdateStatusEnumType,
    ) -> Any:
        request = call.ReservationStatusUpdate(
            reservation_id=reservation_id,
            reservation_update_status=status,
        )
        self._log(
            f"ReservationStatusUpdate: reservation_id={reservation_id}, "
            f"status={status.value}",
        )
        response: call_result.ReservationStatusUpdate = await self.call(request)
        return response

    @on("GetLocalListVersion")
    async def on_get_local_list_version(
        self,
        **kwargs: Any,
    ) -> call_result.GetLocalListVersion:
        version = self.local_auth_manager.get_local_list_version()
        self._log(f"GetLocalListVersion: version={version}")
        return call_result.GetLocalListVersion(version_number=version)

    @on("SendLocalList")
    async def on_send_local_list(
        self,
        version_number: int,
        update_type: Any,
        local_authorization_list: Optional[list[Any]] = None,
        **kwargs: Any,
    ) -> call_result.SendLocalList:
        try:
            update_enum = (
                update_type
                if isinstance(update_type, UpdateEnumType)
                else UpdateEnumType(update_type)
            )
        except (TypeError, ValueError):
            self._log(
                f"SendLocalList: invalid update_type={update_type}",
                level=logging.WARNING,
            )
            return call_result.SendLocalList(
                status=SendLocalListStatusEnumType.failed,
                status_info=StatusInfoType(
                    reason_code="InvalidType",
                    additional_info="Unknown update type",
                ),
            )

        self._log(
            f"SendLocalList: version={version_number}, type={update_enum.value}, "
            f"entries={len(local_authorization_list) if local_authorization_list else 0}",
        )

        status, msg = self.local_auth_manager.send_local_list(
            list_version=version_number,
            local_authorization_list=local_authorization_list,
            update_type=update_enum,
        )

        if status != SendLocalListStatusEnumType.accepted:
            self._log(f"SendLocalList rejected: {msg}", level=logging.WARNING)
        else:
            self._log(f"SendLocalList accepted: {msg}")

        return call_result.SendLocalList(status=status)

    @on("ClearCache")
    async def on_clear_cache(
        self,
        **kwargs: Any,
    ) -> call_result.ClearCache:
        self._log("ClearCache")
        success, msg = self.local_auth_manager.clear_cache()
        if not success:
            self._log(f"ClearCache failed: {msg}", level=logging.WARNING)
            return call_result.ClearCache(
                status=ClearCacheStatusEnumType.rejected,
                status_info=StatusInfoType(
                    reason_code="InternalError",
                    additional_info=msg,
                ),
            )
        return call_result.ClearCache(status=ClearCacheStatusEnumType.accepted)

    # -------------------------------------------------------------------------
    # Log / Diagnostics
    # -------------------------------------------------------------------------

    @on("GetLog")
    async def on_get_log(
        self,
        log: Any,
        log_type: Any,
        request_id: int,
        retries: Optional[int] = None,
        retry_interval: Optional[int] = None,
        **kwargs: Any,
    ) -> call_result.GetLog:
        self._log(
            f"GetLog: type={log_type}, request_id={request_id}",
        )

        try:
            LogEnumType(log_type) if not isinstance(log_type, LogEnumType) else log_type
        except (TypeError, ValueError):
            self._log(
                f"GetLog: invalid log_type={log_type}",
                level=logging.WARNING,
            )
            return call_result.GetLog(
                status=LogStatusEnumType.rejected,
                status_info=StatusInfoType(
                    reason_code="InvalidType",
                    additional_info="Unknown log type",
                ),
            )

        if self._log_task and not self._log_task.done():
            self._log_task.cancel()

        self._log_request_id = request_id

        async def _simulate_log_upload() -> None:
            try:
                await asyncio.sleep(0.1)
                await self.send_log_status_notification(
                    UploadLogStatusEnumType.uploaded,
                    request_id=request_id,
                )
            except asyncio.CancelledError:
                await self.send_log_status_notification(
                    UploadLogStatusEnumType.idle,
                    request_id=request_id,
                )
            except Exception as e:
                self._log(
                    f"Log upload error: {e}",
                    level=logging.ERROR,
                )
                await self.send_log_status_notification(
                    UploadLogStatusEnumType.upload_failure,
                    request_id=request_id,
                )

        self._log_task = asyncio.create_task(_simulate_log_upload())

        await self.send_log_status_notification(
            UploadLogStatusEnumType.uploading,
            request_id=request_id,
        )

        return call_result.GetLog(status=LogStatusEnumType.accepted)

    async def send_log_status_notification(
        self,
        status: UploadLogStatusEnumType,
        request_id: Optional[int] = None,
    ) -> Any:
        request = call.LogStatusNotification(
            status=status,
            request_id=request_id,
        )
        self._log(
            f"LogStatusNotification: status={status.value}, request_id={request_id}",
        )
        response: call_result.LogStatusNotification = await self.call(request)
        return response

    # -------------------------------------------------------------------------
    # Display Messages
    # -------------------------------------------------------------------------

    @on("SetDisplayMessage")
    async def on_set_display_message(
        self,
        message: Any,
        **kwargs: Any,
    ) -> call_result.SetDisplayMessage:
        msg_id = self._item_attr(message, "id", 0)
        priority = self._item_attr(message, "priority")
        state = self._item_attr(message, "state")
        transaction_id = self._item_attr(message, "transaction_id")
        msg_content = self._item_attr(message, "message")

        self._log(f"SetDisplayMessage: id={msg_id}, priority={priority}, state={state}")

        if not isinstance(msg_content, MessageContentType):
            return call_result.SetDisplayMessage(
                status=DisplayMessageStatusEnumType.not_supported_message_format,
                status_info=StatusInfoType(
                    reason_code="InvalidMessage",
                    additional_info="Missing or invalid message content",
                ),
            )

        try:
            priority_enum = (
                priority
                if isinstance(priority, MessagePriorityEnumType)
                else MessagePriorityEnumType(priority)
            )
        except (TypeError, ValueError):
            return call_result.SetDisplayMessage(
                status=DisplayMessageStatusEnumType.not_supported_priority,
            )

        if state is not None:
            try:
                state_enum = (
                    state
                    if isinstance(state, MessageStateEnumType)
                    else MessageStateEnumType(state)
                )
            except (TypeError, ValueError):
                return call_result.SetDisplayMessage(
                    status=DisplayMessageStatusEnumType.not_supported_state,
                )
        else:
            state_enum = None

        if msg_id == 0:
            self._next_message_id += 1
            msg_id = self._next_message_id

        stored_msg = MessageInfoType(
            id=msg_id,
            priority=priority_enum,
            message=msg_content,
            state=state_enum,
            transaction_id=transaction_id,
        )
        self._display_messages[msg_id] = stored_msg

        self._log(
            f"SetDisplayMessage accepted: id={msg_id}, priority={priority_enum.value}",
            level=logging.DEBUG,
        )

        self.on_display_message.emit(
            action="set",
            message=stored_msg,
        )

        return call_result.SetDisplayMessage(
            status=DisplayMessageStatusEnumType.accepted,
        )

    @on("GetDisplayMessages")
    async def on_get_display_messages(
        self,
        request_id: int,
        id: Optional[list[int]] = None,
        priority: Optional[Any] = None,
        state: Optional[Any] = None,
        **kwargs: Any,
    ) -> call_result.GetDisplayMessages:
        self._log(f"GetDisplayMessages: request_id={request_id}")

        messages = list(self._display_messages.values())

        if id is not None:
            id_set = set(id)
            messages = [m for m in messages if m.id in id_set]

        if priority is not None:
            try:
                priority_enum = (
                    priority
                    if isinstance(priority, MessagePriorityEnumType)
                    else MessagePriorityEnumType(priority)
                )
                messages = [m for m in messages if m.priority == priority_enum]
            except (TypeError, ValueError):
                pass

        if state is not None:
            try:
                state_enum = (
                    state
                    if isinstance(state, MessageStateEnumType)
                    else MessageStateEnumType(state)
                )
                messages = [m for m in messages if m.state == state_enum]
            except (TypeError, ValueError):
                pass

        self._log(
            f"GetDisplayMessages: returning {len(messages)} message(s)",
            level=logging.DEBUG,
        )

        async def _send_notify() -> None:
            await self.send_notify_display_messages(request_id, messages)

        self._schedule_background_send(
            _send_notify(),
            "NotifyDisplayMessages",
        )

        if not messages:
            return call_result.GetDisplayMessages(
                status=GetDisplayMessagesStatusEnumType.unknown,
            )
        return call_result.GetDisplayMessages(
            status=GetDisplayMessagesStatusEnumType.accepted,
        )

    @on("ClearDisplayMessage")
    async def on_clear_display_message(
        self,
        id: int,
        **kwargs: Any,
    ) -> call_result.ClearDisplayMessage:
        self._log(f"ClearDisplayMessage: id={id}")

        if id in self._display_messages:
            removed = self._display_messages.pop(id)
            self._log(
                f"ClearDisplayMessage accepted: id={id}",
                level=logging.DEBUG,
            )
            self.on_display_message.emit(
                action="clear",
                message=removed,
            )
            return call_result.ClearDisplayMessage(
                status=ClearMessageStatusEnumType.accepted,
            )

        self._log(
            f"ClearDisplayMessage: unknown id={id}",
            level=logging.WARNING,
        )
        return call_result.ClearDisplayMessage(
            status=ClearMessageStatusEnumType.unknown,
        )

    async def send_notify_display_messages(
        self,
        request_id: int,
        messages: Optional[list[MessageInfoType]] = None,
    ) -> Any:
        request = call.NotifyDisplayMessages(
            request_id=request_id,
            message_info=messages if messages else None,
            tbc=False,
        )

        self._log(
            f"NotifyDisplayMessages: request_id={request_id}, "
            f"messages={len(messages) if messages else 0}",
        )

        response: call_result.NotifyDisplayMessages = await self.call(request)
        return response

    @on("CostUpdated")
    async def on_cost_updated(
        self,
        total_cost: list[CostType],
        transaction_id: str,
        **kwargs: Any,
    ) -> call_result.CostUpdated:
        self._log(
            f"CostUpdated: transaction_id={transaction_id}, "
            f"cost_entries={len(total_cost)}",
        )

        self._transaction_costs[transaction_id] = total_cost
        self.cost_updated.emit(
            transaction_id=transaction_id,
            total_cost=total_cost,
        )

        for cost in total_cost:
            kind = (
                cost.cost_kind.value
                if hasattr(cost.cost_kind, "value")
                else str(cost.cost_kind)
            )
            multiplier = (
                cost.amount_multiplier if cost.amount_multiplier is not None else 0
            )
            self._log(
                f"CostUpdated entry: kind={kind}, amount={cost.amount}, "
                f"multiplier={multiplier}",
                level=logging.DEBUG,
            )

        return call_result.CostUpdated()

    @on("CustomerInformation")
    async def on_customer_information(
        self,
        request_id: int,
        report: bool,
        clear: bool,
        customer_certificate: Optional[Any] = None,
        id_token: Optional[Any] = None,
        customer_identifier: Optional[str] = None,
        **kwargs: Any,
    ) -> call_result.CustomerInformation:
        self._log(
            f"CustomerInformation: request_id={request_id}, report={report}, "
            f"clear={clear}",
        )

        if not report and not clear:
            return call_result.CustomerInformation(
                status=CustomerInformationStatusEnumType.rejected,
            )

        async def _send_notify() -> None:
            await self.send_notify_customer_information(request_id, clear=clear)

        self._schedule_background_send(
            _send_notify(),
            "NotifyCustomerInformation",
        )

        return call_result.CustomerInformation(
            status=CustomerInformationStatusEnumType.accepted,
        )

    async def send_notify_customer_information(
        self,
        request_id: int,
        data: Optional[list[MessageContentType]] = None,
        seq_no: int = 0,
        tbc: bool = False,
        clear: bool = False,
    ) -> Any:
        timestamp = datetime.now(timezone.utc).isoformat()

        request = call.NotifyCustomerInformation(
            request_id=request_id,
            data=data if data else None,
            seq_no=seq_no,
            generated_at=timestamp,
            tbc=tbc,
        )

        self._log(
            f"NotifyCustomerInformation: request_id={request_id}, "
            f"clear={clear}, data={len(data) if data else 0}",
        )

        response: call_result.NotifyCustomerInformation = await self.call(request)
        return response

    def get_transaction_cost(self, transaction_id: str) -> Optional[list[CostType]]:
        return self._transaction_costs.get(transaction_id)

    # -------------------------------------------------------------------------
    # Firmware Management
    # -------------------------------------------------------------------------

    @on("UpdateFirmware")
    async def on_update_firmware(
        self,
        request_id: int,
        firmware: Any,
        retries: Optional[int] = None,
        retry_interval: Optional[int] = None,
        **kwargs: Any,
    ) -> call_result.UpdateFirmware:
        location = firmware.location if hasattr(firmware, "location") else str(firmware)
        retrieve_date_time = (
            firmware.retrieve_date_time
            if hasattr(firmware, "retrieve_date_time")
            else ""
        )
        install_date_time = getattr(firmware, "install_date_time", None)
        signing_certificate = getattr(firmware, "signing_certificate", None)
        signature = getattr(firmware, "signature", None)

        self._log(
            f"UpdateFirmware: request_id={request_id}, location={location}, "
            f"retrieve_date_time={retrieve_date_time}"
        )

        self.firmware_manager.start_firmware_update(
            location=location,
            retrieve_date_time=retrieve_date_time,
            request_id=request_id,
            retries=retries or 0,
            retry_interval=retry_interval or 0,
            install_date_time=install_date_time,
            signing_certificate=signing_certificate,
            signature=signature,
        )

        async def _run_update() -> None:
            await self.firmware_manager.wait_until_retrieve_date()
            await self.firmware_manager.simulate_firmware_update()

        self._schedule_background_send(
            _run_update(),
            "UpdateFirmware",
        )

        return call_result.UpdateFirmware(
            status=UpdateFirmwareStatusEnumType.accepted,
        )

    @on("PublishFirmware")
    async def on_publish_firmware(
        self,
        location: str,
        checksum: str,
        request_id: int,
        retries: Optional[int] = None,
        retry_interval: Optional[int] = None,
        **kwargs: Any,
    ) -> call_result.PublishFirmware:
        self._log(
            f"PublishFirmware: request_id={request_id}, location={location}, "
            f"checksum={checksum}"
        )

        self.firmware_manager.start_publish_firmware(
            location=location,
            checksum=checksum,
            request_id=request_id,
            retries=retries or 0,
            retry_interval=retry_interval or 0,
        )

        async def _run_publish() -> None:
            await self.firmware_manager.simulate_publish_firmware()

        self._schedule_background_send(
            _run_publish(),
            "PublishFirmware",
        )

        return call_result.PublishFirmware(
            status=GenericStatusEnumType.accepted,
        )

    @on("UnpublishFirmware")
    async def on_unpublish_firmware(
        self,
        checksum: str,
        **kwargs: Any,
    ) -> call_result.UnpublishFirmware:
        self._log(f"UnpublishFirmware: checksum={checksum}")

        success = self.firmware_manager.unpublish_firmware()
        if success:
            return call_result.UnpublishFirmware(
                status=UnpublishFirmwareStatusEnumType.unpublished,
            )

        return call_result.UnpublishFirmware(
            status=UnpublishFirmwareStatusEnumType.no_firmware,
        )

    async def send_firmware_status_notification(
        self,
        status: FirmwareStatusEnumType,
        request_id: Optional[int] = None,
    ) -> Any:
        request = call.FirmwareStatusNotification(
            status=status,
            request_id=request_id,
        )
        self._log(
            f"FirmwareStatusNotification: status={status.value}, "
            f"request_id={request_id}",
        )
        response: call_result.FirmwareStatusNotification = await self.call(request)
        return response

    async def send_publish_firmware_status_notification(
        self,
        status: PublishFirmwareStatusEnumType,
        location: Optional[list[str]] = None,
        request_id: Optional[int] = None,
    ) -> Any:
        request = call.PublishFirmwareStatusNotification(
            status=status,
            location=location,
            request_id=request_id,
        )
        self._log(
            f"PublishFirmwareStatusNotification: status={status.value}, "
            f"request_id={request_id}",
        )
        response: call_result.PublishFirmwareStatusNotification = await self.call(
            request
        )
        return response
