"""
OCPP 1.6 Adapter Module.

This module implements the OCPP 1.6 protocol adapter for the ChargeGhost EVSE
simulator. It provides bidirectional communication between the charge point
and a Central System (CSMS), handling both incoming requests and outgoing
messages.

The adapter implements the following OCPP 1.6 features:
- Core profile: BootNotification, Heartbeat, StatusNotification, etc.
- Reservation profile: ReserveNow, CancelReservation
- Core maintenance: ClearCache, TriggerMessage
- Smart Charging profile: SetChargingProfile, ClearChargingProfile, GetCompositeSchedule
- Firmware Management profile: UpdateFirmware, GetDiagnostics
- Local Auth List Management profile: SendLocalList, GetLocalListVersion
- Vendor extensions: DataTransfer

Classes:
    Adapter: OCPP 1.6 Charge Point implementation.

Example:
    >>> import websockets
    >>> from chargeghost_evse.ocpp_adapter.adapter import Adapter
    >>>
    >>> async with websockets.connect(
    ...     "wss://csms.example.com/CP_1",
    ...     subprotocols=["ocpp1.6"]
    ... ) as ws:
    ...     adapter = Adapter("CP_1", ws, command_queue=queue)
    ...     await adapter.start()  # Start message handling
"""

import asyncio
import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

from ocpp.exceptions import PropertyConstraintViolationError
from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call, call_result
from ocpp.v16.datatypes import KeyValue
from ocpp.v16.enums import (
    AvailabilityStatus,
    AvailabilityType,
    CancelReservationStatus,
    ChargingProfileKindType,
    ChargingProfilePurposeType,
    ChargingProfileStatus,
    ChargingRateUnitType,
    ClearChargingProfileStatus,
    ClearCacheStatus,
    DataTransferStatus,
    DiagnosticsStatus,
    FirmwareStatus,
    MessageTrigger,
    RegistrationStatus,
    ReservationStatus,
    ResetStatus,
    ResetType,
    RemoteStartStopStatus,
    TriggerMessageStatus,
    UnlockStatus,
    UpdateStatus,
    UpdateType,
)

from chargeghost_evse.ocpp_adapter.charging_profile_manager import (
    ChargingProfileData,
    ChargingProfileManager,
)
from chargeghost_evse.ocpp_adapter.auth_cache import AuthorizationCacheManager
from chargeghost_evse.ocpp_adapter.config_keys import (
    ConfigurationKey,
    ConfigurationKeyManager,
)
from chargeghost_evse.ocpp_adapter.data_transfer import DataTransferRegistry
from chargeghost_evse.ocpp_adapter.firmware_manager import FirmwareManager
from chargeghost_evse.ocpp_adapter.local_auth_list import LocalAuthListManager
from chargeghost_evse.util.event import Event
from chargeghost_evse.util.helpers import parse_bool_string


def validate_charging_profile(profile: ChargingProfileData) -> Optional[str]:
    """
    Validate a charging profile according to OCPP 1.6J specification.

    Performs Kind-specific validation as required by OCPP 1.6J Smart Charging:

    - Absolute profiles: startSchedule is required
    - Recurring profiles: startSchedule AND recurrencyKind are required
    - Relative profiles: no Kind-specific requirements

    Args:
            profile: The charging profile to validate.

    Returns:
            Error code string if validation fails, None if valid.
             Possible errors:
            - "absolute_missing_start_schedule"
            - "recurring_missing_start_schedule"
            - "recurring_missing_recurrency_kind"
    """
    kind = profile.charging_profile_kind
    schedule = profile.charging_schedule

    if kind == ChargingProfileKindType.absolute:
        if schedule.start_schedule is None:
            return "absolute_missing_start_schedule"

    elif kind == ChargingProfileKindType.recurring:
        if schedule.start_schedule is None:
            return "recurring_missing_start_schedule"
        if profile.recurrency_kind is None:
            return "recurring_missing_recurrency_kind"

    return None


class Adapter(cp):
    """
    OCPP 1.6 Charge Point adapter implementation.

    This class extends the ocpp library's ChargePoint class to implement
    the EVSE side of OCPP 1.6 communication. It handles incoming messages
    from the Central System and provides methods to send messages to it.

    The adapter integrates several managers for different OCPP features:
    - ConfigurationKeyManager: OCPP configuration key storage
    - ChargingProfileManager: Smart Charging profile management
    - AuthorizationCacheManager: In-memory authorization cache
    - LocalAuthListManager: Local authorization list storage
    - FirmwareManager: Firmware update and diagnostics handling

    Events:
        on_ocpp_message: Emitted for raw OCPP message logging.
            Parameters: direction (str), action (str), payload (str)
        on_registration_accepted: Emitted when BootNotification is accepted.
        on_heartbeat_response: Emitted when Heartbeat response is received.
            Parameters: current_time (str)

    Attributes:
        command_queue: Queue for sending commands to the Engine.
        charge_point_model: Model name for BootNotification.
        charge_point_vendor: Vendor name for BootNotification.
        heartbeat_interval: Heartbeat interval in seconds from CSMS.
        registration_status: Current registration status with CSMS.
        active_transactions: Map of connector_id to transaction_id.
        config_manager: Configuration key manager.
        charging_profile_manager: Smart Charging profile manager.
        local_auth_list: Local authorization list manager.
        firmware_manager: Firmware update/diagnostics manager.
        get_connector_info: Callback to get connector voltage and phases.

    Example:
        >>> adapter = Adapter(
        ...     id="CP_1",
        ...     connection=websocket,
        ...     command_queue=engine.command_queue,
        ...     charge_point_model="ChargeGhostV1",
        ...     charge_point_vendor="ChargeGhost"
        ... )
        >>> await adapter.send_boot_notification()
        >>> await adapter.start()  # Start handling incoming messages
    """

    def __init__(
        self,
        id: str,
        connection,
        command_queue=None,
        response_timeout: int = 30,
        charge_point_model: str = "ChargeGhostV1",
        charge_point_vendor: str = "ChargeGhost",
    ) -> None:
        """
        Initialize the OCPP adapter.

        Args:
            id: Charge Point identifier (used in OCPP messages).
            connection: WebSocket connection to the Central System.
            command_queue: Queue for sending commands to the Engine.
            response_timeout: Timeout for OCPP responses in seconds.
            charge_point_model: Model name reported in BootNotification.
            charge_point_vendor: Vendor name reported in BootNotification.
        """
        super().__init__(id, connection, response_timeout)

        # Mirror response_timeout as a public attribute so handlers can read it.
        # The base class stores it as _response_timeout; _on_config_key_changed
        # keeps this in sync when the CSMS sends a ConnectionTimeout update.
        self.response_timeout = response_timeout

        # Command queue for Engine communication
        self.command_queue = command_queue

        # Loggers
        self.logger = logging.getLogger("chargeghost.ocpp")
        self._tx_logger = logging.getLogger("chargeghost.ocpp.tx")

        # Event emitters
        self.on_ocpp_message = Event()
        self.on_reset_requested = Event()

        # Charge point identification
        self.charge_point_model = charge_point_model
        self.charge_point_vendor = charge_point_vendor

        # Registration state
        self.heartbeat_interval: int = 0
        self.registration_status: Optional[RegistrationStatus] = None
        self.on_registration_accepted = Event()
        self.on_heartbeat_response = Event()

        # Transaction tracking: connector_id -> transaction_id
        self.active_transactions: Dict[int, int] = {}
        self._next_transaction_id: int = 0

        # Firmware and diagnostics management
        self.firmware_manager = FirmwareManager()
        self._firmware_task: Optional[asyncio.Task] = None
        self._diagnostics_task: Optional[asyncio.Task] = None

        # Authorization cache used for CSMS authorize responses
        self.auth_cache = AuthorizationCacheManager()

        # Lightweight vendor data transfer routing
        self.data_transfer_registry = DataTransferRegistry()
        self.register_data_transfer_handler(
            "ChargeGhost",
            "Capabilities",
            self._handle_capabilities_data_transfer,
        )

        # Configuration key management
        self.config_manager = ConfigurationKeyManager()
        self.config_manager.initialize_defaults()

        # Local authorization list management
        local_auth_max = self.config_manager.get_int_value(
            "LocalAuthListMaxLength", 100
        )
        self.local_auth_list = LocalAuthListManager(max_entries=local_auth_max)
        local_auth_enabled = self.config_manager.get_bool_value(
            "LocalAuthListEnabled", False
        )
        self.local_auth_list.enabled = local_auth_enabled

        # Charging profile management (Smart Charging)
        max_profiles = self.config_manager.get_int_value(
            "MaxChargingProfilesInstalled", 20
        )
        max_stack_level = self.config_manager.get_int_value(
            "ChargeProfileMaxStackLevel", 5
        )
        max_periods = self.config_manager.get_int_value(
            "ChargingScheduleMaxPeriods", 10
        )
        self.charging_profile_manager = ChargingProfileManager(
            max_profiles=max_profiles,
            max_stack_level=max_stack_level,
            max_schedule_periods=max_periods,
        )

        # Register dynamic config key for installed profile IDs
        self.config_manager.register_key(
            ConfigurationKey(
                key="GetProfileIds",
                value="",
                readonly=True,
                default="",
                description="Comma-separated list of installed charging profile IDs",
                mandatory=False,
                category="SmartCharging",
                value_provider=lambda: ",".join(
                    str(pid) for pid in self.charging_profile_manager.get_profile_ids()
                ),
            )
        )

        # Subscribe to configuration changes
        self.config_manager.on_key_changed.subscribe(self._on_config_key_changed)

        # Injectable callback for connector info (set by Bridge)
        # Signature: (connector_id: int) -> Optional[tuple[voltage, phases]]
        self.get_connector_info: Optional[
            Callable[[int], Optional[tuple[float, int]]]
        ] = None
        self.get_connector_status: Optional[Callable[[int], Optional[str]]] = None
        self.get_meter_snapshot: Optional[
            Callable[[int], Optional[tuple[float, Optional[int]]]]
        ] = None

        # Known connector IDs populated by Bridge after each BootNotification
        self.known_connector_ids: list[int] = []

        # Injectable callback to change connector availability (set by Bridge)
        # Signature: (connector_id: int, availability_type: str) -> str
        # Returns "accepted", "scheduled", or "rejected"
        self.set_connector_availability: Optional[Callable[[int, str], str]] = None

        # Injectable callbacks for reservation handling (set by Bridge)
        self.reserve_connector: Optional[Callable[..., str]] = None
        self.cancel_reservation: Optional[Callable[[int], str]] = None

    def _log(
        self,
        message: str,
        *,
        level: int = logging.INFO,
        **extra,
    ) -> None:
        """
        Emit a log message via Python logging.

        Args:
            message: Log message text.
            level: Logging level (default INFO).
            **extra: Additional structured fields for the log record.
        """
        self.logger.log(level, message, extra={"source": "ocpp", **extra})

    def _on_config_key_changed(self, key_name: str, new_value: str) -> None:
        """
        Handle configuration key change notifications.

        Updates internal state when certain configuration keys change.

        Args:
            key_name: The configuration key that changed.
            new_value: The new value of the key.
        """
        if key_name == "LocalAuthListEnabled":
            self.local_auth_list.enabled = parse_bool_string(new_value)
            self._log(
                f"LocalAuthListEnabled changed to {self.local_auth_list.enabled}",
            )
        elif key_name == "LocalAuthListMaxLength":
            try:
                max_entries = int(new_value)
                self.local_auth_list.max_entries = max_entries
                self._log(
                    f"LocalAuthListMaxLength changed to {max_entries}",
                )
            except (TypeError, ValueError):
                pass
        elif key_name == "HeartbeatInterval":
            try:
                self.heartbeat_interval = int(new_value)
                self._log(
                    f"HeartbeatInterval updated to {new_value}s",
                )
            except (TypeError, ValueError):
                pass
        elif key_name == "MeterValueSampleInterval":
            self._log(
                f"MeterValueSampleInterval updated to {new_value}s",
            )
        elif key_name == "ConnectionTimeout":
            try:
                self.response_timeout = int(new_value)
                self._log(
                    f"Response timeout updated to {new_value}s",
                )
            except (TypeError, ValueError):
                pass

    def _parse_remote_start_charging_profile(
        self, charging_profile: dict
    ) -> Optional[ChargingProfileData]:
        """
        Parse and validate a RemoteStartTransaction charging profile.

        RemoteStartTransaction may only carry a TxProfile template. The
        transaction ID is assigned later when StartTransaction succeeds, so any
        incoming transactionId is replaced when the session is registered.
        """
        try:
            profile = ChargingProfileManager.from_ocpp_dict(charging_profile)
        except (KeyError, ValueError, TypeError) as e:
            self._log(
                f"Failed to parse remote start charging profile: {e}",
                level=logging.WARNING,
            )
            return None

        if profile.charging_profile_purpose != ChargingProfilePurposeType.tx_profile:
            self._log(
                "RemoteStartTransaction chargingProfile must use TxProfile purpose",
                level=logging.WARNING,
            )
            return None

        validation_error = validate_charging_profile(profile)
        if validation_error:
            self._log(
                f"RemoteStartTransaction charging profile rejected: {validation_error}",
                level=logging.WARNING,
            )
            return None

        return replace(profile, transaction_id=None)

    def _raise_property_constraint(self, description: str, **details: Any) -> None:
        """Raise an OCPP PropertyConstraintViolation with optional details."""
        raise PropertyConstraintViolationError(
            description=description,
            details=details or None,
        )

    def _validate_smart_charging_connector_id(
        self, connector_id: int, *, allow_zero: bool
    ) -> int:
        """Validate Smart Charging connector IDs against known connectors."""
        try:
            normalized_connector_id = int(connector_id)
        except (TypeError, ValueError):
            self._raise_property_constraint(
                "Invalid Smart Charging connectorId",
                field="connectorId",
                value=connector_id,
            )

        if normalized_connector_id < 0:
            self._raise_property_constraint(
                "Invalid Smart Charging connectorId",
                field="connectorId",
                value=normalized_connector_id,
            )

        if normalized_connector_id == 0:
            if allow_zero:
                return normalized_connector_id
            self._raise_property_constraint(
                "connectorId must reference a physical connector",
                field="connectorId",
                value=normalized_connector_id,
            )

        if (
            self.known_connector_ids
            and normalized_connector_id not in self.known_connector_ids
        ):
            self._raise_property_constraint(
                "Unknown Smart Charging connectorId",
                field="connectorId",
                value=normalized_connector_id,
            )

        return normalized_connector_id

    def _validate_charging_rate_unit(
        self, charging_rate_unit: Optional[str]
    ) -> ChargingRateUnitType:
        """Validate GetCompositeSchedule chargingRateUnit values."""
        if charging_rate_unit is None:
            return ChargingRateUnitType.amps

        if isinstance(charging_rate_unit, ChargingRateUnitType):
            return charging_rate_unit

        try:
            return ChargingRateUnitType(charging_rate_unit)
        except ValueError:
            self._raise_property_constraint(
                "Invalid Smart Charging chargingRateUnit",
                field="chargingRateUnit",
                value=charging_rate_unit,
            )

    def _parse_set_charging_profile(
        self, cs_charging_profiles: dict
    ) -> ChargingProfileData:
        """Parse and validate a SetChargingProfile payload."""
        try:
            profile = ChargingProfileManager.from_ocpp_dict(cs_charging_profiles)
        except (KeyError, ValueError, TypeError) as e:
            self._raise_property_constraint(
                "Malformed Smart Charging profile payload",
                field="csChargingProfiles",
                cause=str(e),
            )

        validation_error = validate_charging_profile(profile)
        if validation_error:
            self._raise_property_constraint(
                "Invalid Smart Charging profile value",
                field="csChargingProfiles",
                cause=validation_error,
            )

        return profile

    def _log_ocpp_raw(
        self,
        direction: str,
        action: str,
        payload: Any,
        message_id: str = "",
    ) -> None:
        """
        Log raw OCPP message for debugging.

        Args:
            direction: "TX" for transmitted, "RX" for received.
            action: OCPP action name.
            payload: Message payload.
            message_id: Optional unique message ID.
        """
        try:
            if isinstance(payload, dict):
                payload_str = json.dumps(payload, indent=2)
            else:
                payload_str = str(payload)
        except (TypeError, ValueError):
            payload_str = str(payload)

        raw_msg = f"[{direction}] {action}"
        if message_id:
            raw_msg += f" (id={message_id})"
        raw_msg += f"\n{payload_str}"

        # Important actions shown in shallow mode (INFO), others are DEBUG
        important_actions = {
            "BootNotification",
            "StartTransaction",
            "StopTransaction",
            "Authorize",
            "RemoteStartTransaction",
            "RemoteStopTransaction",
            "Reset",
            "StatusNotification",
            "GetDiagnostics",
            "DiagnosticsStatusNotification",
            "UpdateFirmware",
            "FirmwareStatusNotification",
            "GetConfiguration",
            "ChangeConfiguration",
            "SendLocalList",
            "GetLocalListVersion",
            "DataTransfer",
        }
        level = logging.INFO if action in important_actions else logging.DEBUG

        self.on_ocpp_message.emit(
            direction=direction, action=action, payload=payload_str
        )
        self._tx_logger.log(
            level,
            raw_msg,
            extra={
                "source": "ocpp",
                "ocpp_direction": direction,
                "ocpp_action": action,
                "ocpp_message_id": message_id,
                "ocpp_payload": payload if isinstance(payload, dict) else payload_str,
                # For RX (responses), set correlated_id to match the TX message_id.
                # In OCPP 1.6, the response uses the same unique_id as the request,
                # so this equals ocpp_message_id on RX records. The UI can group
                # TX+RX records by matching TX.ocpp_message_id == RX.ocpp_correlated_id.
                "ocpp_correlated_id": message_id if direction == "RX" else None,
            },
        )

    async def _send_call(self, message) -> Any:
        """
        Override to log outgoing CALL messages.

        Args:
            message: The OCPP CALL message to send.

        Returns:
            Response from the Central System.
        """
        self._log_ocpp_raw("TX", message.__class__.__name__, message.__dict__)
        return await super()._send_call(message)

    async def _handle_call(self, msg) -> Any:
        """
        Override to log incoming CALL messages.

        Args:
            msg: The incoming OCPP CALL message.

        Returns:
            Response to send back.
        """
        if hasattr(msg, "unique_id") and hasattr(msg, "action"):
            payload = getattr(msg, "payload", msg.__dict__)
            self._log_ocpp_raw("RX", msg.action, payload, getattr(msg, "unique_id", ""))
        return await super()._handle_call(msg)

    def _schedule_background_send(self, awaitable: Awaitable[Any], action: str) -> None:
        """
        Schedule an outbound OCPP send without blocking the caller.

        Args:
            awaitable: Outbound send coroutine.
            action: OCPP action name for logging context.
        """
        task = asyncio.create_task(awaitable)
        task.add_done_callback(
            lambda completed: self._handle_background_send_result(completed, action)
        )

    def _handle_background_send_result(
        self, task: asyncio.Task[Any], action: str
    ) -> None:
        """
        Log exceptions raised by background send tasks.

        Args:
            task: The finished asyncio task.
            action: OCPP action name for logging context.
        """
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._log(
                f"TriggerMessage {action} failed: {exc}",
                level=logging.ERROR,
            )

    # -------------------------------------------------------------------------
    # Transaction Management
    # -------------------------------------------------------------------------

    def get_active_transaction_id(self, connector_id: int) -> Optional[int]:
        """
        Get the active transaction ID for a connector.

        Args:
            connector_id: The connector ID.

        Returns:
            Transaction ID if active, None otherwise.
        """
        return self.active_transactions.get(connector_id)

    def set_active_transaction(self, connector_id: int, transaction_id: int) -> None:
        """
        Set the active transaction for a connector.

        Args:
            connector_id: The connector ID.
            transaction_id: The transaction ID to associate.
        """
        self.active_transactions[connector_id] = transaction_id

    def clear_active_transaction(self, connector_id: int) -> None:
        """
        Clear the active transaction for a connector.

        Args:
            connector_id: The connector ID to clear.
        """
        if connector_id in self.active_transactions:
            del self.active_transactions[connector_id]

    # -------------------------------------------------------------------------
    # Incoming OCPP Message Handlers
    # -------------------------------------------------------------------------

    @on("ReserveNow")
    async def on_reserve_now(
        self,
        connector_id: int,
        expiry_date: str,
        id_tag: str,
        reservation_id: int,
        parent_id_tag: Optional[str] = None,
        **kwargs,
    ) -> call_result.ReserveNow:
        """
        Handle ReserveNow request from CSMS.

        Reserves an idle connector for a specific id_tag until the given expiry.
        """
        self._log(
            f"ReserveNow: connector_id={connector_id}, reservation_id={reservation_id}, "
            f"id_tag={id_tag}",
        )

        if self.reserve_connector is None:
            return call_result.ReserveNow(status=ReservationStatus.rejected)

        # connector_id=0 means "reserve any available connector" per OCPP 1.6 §5.10
        if connector_id == 0:
            target_id: Optional[int] = None
            if self.get_connector_status is not None:
                for cid in self.known_connector_ids:
                    if self.get_connector_status(cid) == "Available":
                        target_id = cid
                        break
            if target_id is None:
                return call_result.ReserveNow(status=ReservationStatus.unavailable)
            connector_id = target_id
        elif connector_id not in self.known_connector_ids:
            return call_result.ReserveNow(status=ReservationStatus.rejected)

        try:
            parsed_expiry = datetime.fromisoformat(expiry_date.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            self._log(
                f"ReserveNow: invalid expiry_date={expiry_date}",
                level=logging.WARNING,
            )
            return call_result.ReserveNow(status=ReservationStatus.rejected)

        result = self.reserve_connector(
            connector_id,
            reservation_id,
            id_tag,
            parsed_expiry,
            parent_id_tag,
        )
        status_map = {
            "accepted": ReservationStatus.accepted,
            "occupied": ReservationStatus.occupied,
            "faulted": ReservationStatus.faulted,
            "unavailable": ReservationStatus.unavailable,
            "rejected": ReservationStatus.rejected,
        }
        return call_result.ReserveNow(
            status=status_map.get(result, ReservationStatus.rejected)
        )

    @on("CancelReservation")
    async def on_cancel_reservation(
        self, reservation_id: int, **kwargs
    ) -> call_result.CancelReservation:
        """
        Handle CancelReservation request from CSMS.

        Cancels an existing reservation by reservation ID.
        """
        self._log(f"CancelReservation: reservation_id={reservation_id}")

        if self.cancel_reservation is None:
            return call_result.CancelReservation(
                status=CancelReservationStatus.rejected
            )

        result = self.cancel_reservation(reservation_id)
        status = (
            CancelReservationStatus.accepted
            if result == "accepted"
            else CancelReservationStatus.rejected
        )
        return call_result.CancelReservation(status=status)

    @on("TriggerMessage")
    async def on_trigger_message(
        self,
        requested_message: str,
        connector_id: Optional[int] = None,
        **kwargs,
    ) -> call_result.TriggerMessage:
        """
        Handle TriggerMessage request from CSMS.

        Supports the simulator's built-in trigger set only.
        """
        try:
            trigger = (
                requested_message
                if isinstance(requested_message, MessageTrigger)
                else MessageTrigger(requested_message)
            )
        except (TypeError, ValueError):
            self._log(
                f"TriggerMessage: unsupported message={requested_message}",
                level=logging.WARNING,
            )
            return call_result.TriggerMessage(
                status=TriggerMessageStatus.not_implemented
            )

        self._log(
            f"TriggerMessage: requested_message={trigger.value}, connector_id={connector_id}",
        )

        if trigger == MessageTrigger.boot_notification:
            self._schedule_background_send(self.send_boot_notification(), trigger.value)
            return call_result.TriggerMessage(status=TriggerMessageStatus.accepted)

        if trigger == MessageTrigger.heartbeat:
            self._schedule_background_send(self.send_heartbeat(), trigger.value)
            return call_result.TriggerMessage(status=TriggerMessageStatus.accepted)

        if trigger == MessageTrigger.status_notification:
            if (
                connector_id is None
                or connector_id not in self.known_connector_ids
                or self.get_connector_status is None
            ):
                return call_result.TriggerMessage(status=TriggerMessageStatus.rejected)

            status = self.get_connector_status(connector_id)
            if status is None:
                return call_result.TriggerMessage(status=TriggerMessageStatus.rejected)

            self._schedule_background_send(
                self.send_status_notification(connector_id, "NoError", status),
                trigger.value,
            )
            return call_result.TriggerMessage(status=TriggerMessageStatus.accepted)

        if trigger == MessageTrigger.meter_values:
            if (
                connector_id is None
                or connector_id not in self.known_connector_ids
                or self.get_meter_snapshot is None
            ):
                return call_result.TriggerMessage(status=TriggerMessageStatus.rejected)

            snapshot = self.get_meter_snapshot(connector_id)
            if snapshot is None or len(snapshot) != 2:
                return call_result.TriggerMessage(status=TriggerMessageStatus.rejected)

            value, transaction_id = snapshot
            self._schedule_background_send(
                self.send_meter_values(connector_id, value, transaction_id),
                trigger.value,
            )
            return call_result.TriggerMessage(status=TriggerMessageStatus.accepted)

        if trigger == MessageTrigger.diagnostics_status_notification:
            self._schedule_background_send(
                self.send_diagnostics_status_notification(
                    self.firmware_manager.get_diagnostics_status()
                ),
                trigger.value,
            )
            return call_result.TriggerMessage(status=TriggerMessageStatus.accepted)

        if trigger == MessageTrigger.firmware_status_notification:
            self._schedule_background_send(
                self.send_firmware_status_notification(
                    self.firmware_manager.get_firmware_status()
                ),
                trigger.value,
            )
            return call_result.TriggerMessage(status=TriggerMessageStatus.accepted)

        return call_result.TriggerMessage(status=TriggerMessageStatus.not_implemented)

    @on("RemoteStartTransaction")
    async def on_remote_start_transaction(
        self,
        connector_id: Optional[int],
        id_tag: str,
        charging_profile: Optional[dict] = None,
        **kwargs,
    ) -> call_result.RemoteStartTransaction:
        """
        Handle RemoteStartTransaction request from CSMS.

        Queues a START command for the Engine to process. If connector_id
        is not specified or is 0, the Engine will select an available connector.

        Args:
            connector_id: Optional target connector ID (0 or None for any).
            id_tag: Authorization identifier for the transaction.
            **kwargs: Additional parameters (chargingProfile, etc.).

        Returns:
            RemoteStartTransaction response with Accepted or Rejected status.
        """
        self._log(
            f"RemoteStartTransaction: connector_id={connector_id}, id_tag={id_tag}",
        )

        remote_start_profile = charging_profile
        if remote_start_profile is None:
            remote_start_profile = kwargs.get("charging_profile")
        if remote_start_profile is None:
            remote_start_profile = kwargs.get("chargingProfile")

        parsed_profile: Optional[ChargingProfileData] = None
        if remote_start_profile is not None:
            parsed_profile = self._parse_remote_start_charging_profile(
                remote_start_profile
            )
            if parsed_profile is None:
                return call_result.RemoteStartTransaction(
                    status=RemoteStartStopStatus.rejected
                )

        # Validate connector_id if provided
        target_connector_id: Optional[int] = None
        if connector_id is not None and connector_id != 0:
            try:
                ocpp_connector_id = int(connector_id)
            except (TypeError, ValueError):
                self._log(
                    f"Invalid connector_id: {connector_id}",
                    level=logging.WARNING,
                )
                return call_result.RemoteStartTransaction(
                    status=RemoteStartStopStatus.rejected
                )

            if ocpp_connector_id < 0:
                self._log(
                    f"Out-of-range connector_id: {ocpp_connector_id}",
                    level=logging.WARNING,
                )
                return call_result.RemoteStartTransaction(
                    status=RemoteStartStopStatus.rejected
                )

            target_connector_id = ocpp_connector_id

        # Queue command for Engine
        if self.command_queue:
            target_desc = (
                f"connector {target_connector_id}"
                if target_connector_id
                else "any connector"
            )
            self._log(
                f"Enqueuing START for {target_desc}",
                level=logging.DEBUG,
            )
            self.command_queue.put(
                {
                    "action": "START",
                    "connector_id": target_connector_id,
                    "id_tag": id_tag,
                    "charging_profile": parsed_profile,
                    "timeout": self.response_timeout,
                }
            )
            return call_result.RemoteStartTransaction(
                status=RemoteStartStopStatus.accepted
            )

        return call_result.RemoteStartTransaction(status=RemoteStartStopStatus.rejected)

    @on("RemoteStopTransaction")
    async def on_remote_stop_transaction(
        self, transaction_id: int, **kwargs
    ) -> call_result.RemoteStopTransaction:
        """
        Handle RemoteStopTransaction request from CSMS.

        Finds the connector with the matching transaction and queues
        a STOP command for the Engine.

        Args:
            transaction_id: The transaction ID to stop.
            **kwargs: Additional parameters.

        Returns:
            RemoteStopTransaction response with Accepted or Rejected status.
        """
        self._log(
            f"RemoteStopTransaction: transaction_id={transaction_id}",
        )

        # Find the connector with this transaction
        matching_connector: Optional[int] = None
        for conn_id, tx_id in self.active_transactions.items():
            if tx_id == transaction_id:
                matching_connector = conn_id
                break

        if matching_connector is None:
            self._log(
                f"No active transaction: {transaction_id}",
                level=logging.WARNING,
            )
            return call_result.RemoteStopTransaction(
                status=RemoteStartStopStatus.rejected
            )

        # Queue command for Engine
        if self.command_queue:
            self._log(
                f"Enqueuing STOP for tx {transaction_id}",
                level=logging.DEBUG,
            )
            self.command_queue.put(
                {
                    "action": "STOP",
                    "transaction_id": transaction_id,
                    "connector_id": matching_connector,
                    "reason": "Remote",
                }
            )
            return call_result.RemoteStopTransaction(
                status=RemoteStartStopStatus.accepted
            )

        return call_result.RemoteStopTransaction(status=RemoteStartStopStatus.rejected)

    @on("Reset")
    async def on_reset(self, type: str, **kwargs) -> call_result.Reset:
        """
        Handle Reset request from CSMS.

        Accepts valid Soft and Hard reset requests, forwards them to the
        Engine command queue, and emits a reset event so the Bridge can
        simulate the post-reset registration flow.

        Args:
            type: Requested reset type ("Soft" or "Hard").
            **kwargs: Additional parameters.

        Returns:
            Reset response with Accepted or Rejected status.
        """
        self._log(
            f"Reset: type={type}",
        )

        try:
            reset_type = ResetType(type)
        except ValueError:
            self._log(
                f"Invalid reset type: {type}",
                level=logging.WARNING,
            )
            return call_result.Reset(status=ResetStatus.rejected)

        if self.command_queue is None:
            self._log(
                "Reset rejected: command queue unavailable",
                level=logging.WARNING,
            )
            return call_result.Reset(status=ResetStatus.rejected)

        self.command_queue.put({"action": "RESET", "type": reset_type.value})
        self.on_reset_requested.emit(reset_type=reset_type.value)
        return call_result.Reset(status=ResetStatus.accepted)

    @on("ChangeAvailability")
    async def on_change_availability(
        self, connector_id: int, type: str, **kwargs
    ) -> call_result.ChangeAvailability:
        """
        Handle ChangeAvailability request from CSMS.

        Sets a connector (or all connectors when connector_id=0) to Operative
        or Inoperative. If a transaction is active on the target connector, the
        change is deferred until the transaction ends and Scheduled is returned.

        Args:
            connector_id: Target connector ID, or 0 for all connectors.
            type: Availability type ("Operative" or "Inoperative").
            **kwargs: Additional parameters.

        Returns:
            ChangeAvailability response with Accepted, Scheduled, or Rejected status.
        """
        self._log(
            f"ChangeAvailability: connector_id={connector_id}, type={type}",
        )

        try:
            availability_type = AvailabilityType(type)
        except ValueError:
            self._log(
                f"ChangeAvailability: unknown type '{type}', rejecting",
                level=logging.WARNING,
            )
            return call_result.ChangeAvailability(status=AvailabilityStatus.rejected)

        if self.set_connector_availability is None:
            self._log(
                "ChangeAvailability: engine callback unavailable, rejecting",
                level=logging.WARNING,
            )
            return call_result.ChangeAvailability(status=AvailabilityStatus.rejected)

        # Validate connector_id: 0 = whole charge point (always valid), else must be known
        if connector_id != 0 and connector_id not in self.known_connector_ids:
            self._log(
                f"ChangeAvailability: unknown connector_id={connector_id}, rejecting",
                level=logging.WARNING,
            )
            return call_result.ChangeAvailability(status=AvailabilityStatus.rejected)

        result = self.set_connector_availability(connector_id, availability_type.value)

        status_map = {
            "accepted": AvailabilityStatus.accepted,
            "scheduled": AvailabilityStatus.scheduled,
            "rejected": AvailabilityStatus.rejected,
        }
        status = status_map.get(result, AvailabilityStatus.rejected)
        self._log(
            f"ChangeAvailability: result={status.value}",
            level=logging.DEBUG,
        )
        return call_result.ChangeAvailability(status=status)

    @on("UnlockConnector")
    async def on_unlock_connector(
        self, connector_id: int, **kwargs
    ) -> call_result.UnlockConnector:
        """
        Handle UnlockConnector request from CSMS.

        Simulates releasing the physical cable lock on a connector. If a
        transaction is active on that connector, it is stopped first (per OCPP
        1.6 §5.15). Always responds Unlocked for a valid connector ID.

        Args:
            connector_id: Target connector ID.
            **kwargs: Additional parameters.

        Returns:
            UnlockConnector response with Unlocked, UnlockFailed, or NotSupported status.
        """
        self._log(
            f"UnlockConnector: connector_id={connector_id}",
        )

        if connector_id not in self.known_connector_ids:
            self._log(
                f"UnlockConnector: unknown connector_id={connector_id}",
                level=logging.WARNING,
            )
            return call_result.UnlockConnector(status=UnlockStatus.not_supported)

        # If an active transaction exists on this connector, stop it first
        if connector_id in self.active_transactions and self.command_queue is not None:
            self._log(
                f"UnlockConnector: stopping active transaction on connector {connector_id}",
                level=logging.DEBUG,
            )
            self.command_queue.put({"action": "STOP", "reason": "UnlockCommand"})
            self.clear_active_transaction(connector_id)

        return call_result.UnlockConnector(status=UnlockStatus.unlocked)

    @on("GetConfiguration")
    async def on_get_configuration(
        self, key: Optional[list[str]] = None, **kwargs
    ) -> call_result.GetConfiguration:
        """
        Handle GetConfiguration request from CSMS.

        Returns configuration key values. If no keys are specified,
        returns all configuration keys.

        Args:
            key: Optional list of specific keys to retrieve.
            **kwargs: Additional parameters.

        Returns:
            GetConfiguration response with key values and unknown key list.
        """
        self._log(
            f"GetConfiguration: keys={key}",
        )

        configuration_key: list[KeyValue] = []
        unknown_key: list[str] = []

        if not key:
            # Return all keys
            for config_key in self.config_manager.get_all_keys():
                configuration_key.append(
                    KeyValue(
                        key=config_key.key,
                        readonly=config_key.readonly,
                        value=config_key.get_value(),
                    )
                )
        else:
            # Return specific keys
            for k in key:
                found_key = self.config_manager.get_key(k)
                if found_key is not None:
                    configuration_key.append(
                        KeyValue(
                            key=found_key.key,
                            readonly=found_key.readonly,
                            value=found_key.get_value(),
                        )
                    )
                else:
                    unknown_key.append(k)

        return call_result.GetConfiguration(
            configuration_key=configuration_key,
            unknown_key=unknown_key if unknown_key else None,
        )

    @on("ClearCache")
    async def on_clear_cache(self, **kwargs) -> call_result.ClearCache:
        """
        Handle ClearCache request from CSMS.

        Clears the in-memory authorization cache only.
        """
        self._log("ClearCache")
        self.auth_cache.clear()
        return call_result.ClearCache(status=ClearCacheStatus.accepted)

    @on("DataTransfer")
    async def on_data_transfer(
        self,
        vendor_id: str,
        message_id: Optional[str] = None,
        data: Optional[str] = None,
        **kwargs,
    ) -> call_result.DataTransfer:
        """
        Handle DataTransfer request from CSMS.

        Routes vendor-specific payloads through the lightweight registry.
        """
        self._log(
            f"DataTransfer: vendor_id={vendor_id}, message_id={message_id}",
        )

        status, response_data = self.data_transfer_registry.handle(
            vendor_id,
            message_id,
            data,
        )
        return call_result.DataTransfer(status=status, data=response_data)

    @on("ChangeConfiguration")
    async def on_change_configuration(
        self, key: str, value: str, **kwargs
    ) -> call_result.ChangeConfiguration:
        """
        Handle ChangeConfiguration request from CSMS.

        Updates a configuration key value.

        Args:
            key: The configuration key to change.
            value: The new value for the key.
            **kwargs: Additional parameters.

        Returns:
            ChangeConfiguration response with status.
        """
        self._log(
            f"ChangeConfiguration: key={key}, value={value}",
        )

        status = self.config_manager.set_key(key, value)
        return call_result.ChangeConfiguration(status=status)

    @on("GetLocalListVersion")
    async def on_get_local_list_version(
        self, **kwargs
    ) -> call_result.GetLocalListVersion:
        """
        Handle GetLocalListVersion request from CSMS.

        Returns the current version number of the local authorization list.

        Args:
            **kwargs: Additional parameters.

        Returns:
            GetLocalListVersion response with list version number.
        """
        version = self.local_auth_list.version
        self._log(
            f"GetLocalListVersion: version={version}",
        )
        return call_result.GetLocalListVersion(list_version=version)

    @on("SendLocalList")
    async def on_send_local_list(
        self,
        list_version: int,
        local_authorization_list: Optional[list] = None,
        update_type: str = "Full",
        **kwargs,
    ) -> call_result.SendLocalList:
        """
        Handle SendLocalList request from CSMS.

        Updates the local authorization list with new entries.

        Args:
            list_version: Version number for this update.
            local_authorization_list: List of authorization entries.
            update_type: "Full" for complete replacement, "Differential" for delta.
            **kwargs: Additional parameters.

        Returns:
            SendLocalList response with Accepted or Failed status.
        """
        self._log(
            f"SendLocalList: version={list_version}, update_type={update_type}, "
            f"entries={len(local_authorization_list) if local_authorization_list else 0}",
        )

        if list_version <= 0:
            self._log(
                f"Invalid SendLocalList version: {list_version}",
                level=logging.WARNING,
            )
            return call_result.SendLocalList(status=UpdateStatus.failed)

        try:
            update_type_enum = UpdateType(update_type)
        except ValueError:
            self._log(
                f"Invalid update_type: {update_type}",
                level=logging.WARNING,
            )
            return call_result.SendLocalList(status=UpdateStatus.failed)

        status, message = self.local_auth_list.update_list(
            list_version=list_version,
            local_authorization_list=local_authorization_list,
            update_type=update_type_enum,
        )

        self._log(
            f"SendLocalList result: {status.value} - {message}",
        )

        return call_result.SendLocalList(status=status)

    @on("GetDiagnostics")
    async def on_get_diagnostics(
        self,
        location: str,
        retries: Optional[int] = None,
        retry_interval: Optional[int] = None,
        start_time: Optional[str] = None,
        stop_time: Optional[str] = None,
        **kwargs,
    ) -> call_result.GetDiagnostics:
        """
        Handle GetDiagnostics request from CSMS.

        Initiates an asynchronous diagnostics upload to the specified location.

        Args:
            location: URI where diagnostics file should be uploaded.
            retries: Number of upload retries on failure.
            retry_interval: Seconds between retries.
            start_time: Only include logs from this time.
            stop_time: Only include logs until this time.
            **kwargs: Additional parameters.

        Returns:
            GetDiagnostics response (file_name is None initially).
        """
        self._log(
            f"GetDiagnostics: location={location}",
        )

        self.firmware_manager.start_diagnostics_upload(
            location=location,
            retries=retries or 0,
            retry_interval=retry_interval or 0,
            start_time=start_time,
            stop_time=stop_time,
        )

        # Cancel any previous diagnostics task
        if self._diagnostics_task and not self._diagnostics_task.done():
            self._diagnostics_task.cancel()

        async def run_diagnostics_upload() -> None:
            """Execute diagnostics upload asynchronously."""
            try:
                file_name = await self.firmware_manager.simulate_diagnostics_upload()
                if file_name:
                    await self.send_diagnostics_status_notification(
                        DiagnosticsStatus.uploaded
                    )
                else:
                    await self.send_diagnostics_status_notification(
                        DiagnosticsStatus.upload_failed
                    )
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self._log(
                    f"Diagnostics upload error: {e}",
                    level=logging.ERROR,
                )
                await self.send_diagnostics_status_notification(
                    DiagnosticsStatus.upload_failed
                )

        self._diagnostics_task = asyncio.create_task(run_diagnostics_upload())

        # Send initial status
        await self.send_diagnostics_status_notification(DiagnosticsStatus.uploading)

        return call_result.GetDiagnostics(file_name=None)

    @on("UpdateFirmware")
    async def on_update_firmware(
        self,
        location: str,
        retrieve_date: str,
        retries: Optional[int] = None,
        retry_interval: Optional[int] = None,
        **kwargs,
    ) -> call_result.UpdateFirmware:
        """
        Handle UpdateFirmware request from CSMS.

        Initiates an asynchronous firmware download and installation.

        Args:
            location: URI where firmware file can be downloaded.
            retrieve_date: When to start the firmware update.
            retries: Number of download retries on failure.
            retry_interval: Seconds between retries.
            **kwargs: Additional parameters.

        Returns:
            UpdateFirmware response (empty, status sent via notifications).
        """
        self._log(
            f"UpdateFirmware: location={location}, retrieve_date={retrieve_date}",
        )

        self.firmware_manager.start_firmware_update(
            location=location,
            retrieve_date=retrieve_date,
            retries=retries or 0,
            retry_interval=retry_interval or 0,
        )

        # Cancel any previous firmware task
        if self._firmware_task and not self._firmware_task.done():
            self._firmware_task.cancel()

        async def run_firmware_update() -> None:
            """Execute firmware update asynchronously."""
            try:
                await self.firmware_manager.wait_until_retrieve_date()
                await self.send_firmware_status_notification(FirmwareStatus.downloading)
                success = await self.firmware_manager.simulate_firmware_update()
                if success:
                    await self.send_firmware_status_notification(
                        FirmwareStatus.installed
                    )
                else:
                    await self.send_firmware_status_notification(
                        FirmwareStatus.installation_failed
                    )
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self._log(
                    f"Firmware update error: {e}",
                    level=logging.ERROR,
                )
                await self.send_firmware_status_notification(
                    FirmwareStatus.installation_failed
                )

        self._firmware_task = asyncio.create_task(run_firmware_update())

        return call_result.UpdateFirmware()

    @on("SetChargingProfile")
    async def on_set_charging_profile(
        self,
        connector_id: int,
        cs_charging_profiles: dict,
        **kwargs,
    ) -> call_result.SetChargingProfile:
        """
        Handle SetChargingProfile request from CSMS.

        Stores or updates a charging profile for smart charging.

        Args:
            connector_id: Connector to apply profile to (0 = all connectors).
            cs_charging_profiles: The charging profile definition.
            **kwargs: Additional parameters.

        Returns:
            SetChargingProfile response with Accepted or Rejected status.
        """
        self._log(
            f"SetChargingProfile: connector_id={connector_id}, "
            f"profile_id={cs_charging_profiles.get('charging_profile_id')}",
        )

        connector_id = self._validate_smart_charging_connector_id(connector_id, allow_zero=True)
        profile = self._parse_set_charging_profile(cs_charging_profiles)

        error = self.charging_profile_manager.set_profile(connector_id, profile)
        if error:
            if error in {
                "too_many_periods",
                "stack_level_exceeded",
                "tx_profile_missing_transaction_id",
            }:
                self._raise_property_constraint(
                    "Invalid Smart Charging profile value",
                    field="csChargingProfiles",
                    cause=error,
                )
            self._log(
                f"Charging profile rejected: {error}",
                level=logging.WARNING,
            )
            return call_result.SetChargingProfile(status=ChargingProfileStatus.rejected)

        self._log(
            f"Charging profile {profile.charging_profile_id} accepted",
        )
        return call_result.SetChargingProfile(status=ChargingProfileStatus.accepted)

    @on("ClearChargingProfile")
    async def on_clear_charging_profile(
        self,
        id: Optional[int] = None,
        connector_id: Optional[int] = None,
        charging_profile_purpose: Optional[str] = None,
        stack_level: Optional[int] = None,
        **kwargs,
    ) -> call_result.ClearChargingProfile:
        """
        Handle ClearChargingProfile request from CSMS.

        Removes charging profiles matching the specified criteria.

        Args:
            id: Specific profile ID to remove.
            connector_id: Remove profiles for this connector.
            charging_profile_purpose: Remove profiles with this purpose.
            stack_level: Remove profiles at this stack level.
            **kwargs: Additional parameters.

        Returns:
            ClearChargingProfile response with Accepted or Unknown status.
        """
        self._log(
            f"ClearChargingProfile: id={id}, connector_id={connector_id}, "
            f"purpose={charging_profile_purpose}",
        )

        if id is not None and id < 0:
            self._raise_property_constraint(
                "Invalid Smart Charging profile id",
                field="id",
                value=id,
            )
        if stack_level is not None and stack_level < 0:
            self._raise_property_constraint(
                "Invalid Smart Charging stackLevel",
                field="stackLevel",
                value=stack_level,
            )
        if connector_id is not None:
            connector_id = self._validate_smart_charging_connector_id(
                connector_id,
                allow_zero=True,
            )

        # Parse purpose enum if provided
        purpose_enum = None
        if charging_profile_purpose:
            try:
                purpose_enum = ChargingProfilePurposeType(charging_profile_purpose)
            except ValueError:
                self._raise_property_constraint(
                    "Invalid Smart Charging chargingProfilePurpose",
                    field="chargingProfilePurpose",
                    value=charging_profile_purpose,
                )

        cleared = self.charging_profile_manager.clear_profiles(
            profile_id=id,
            connector_id=connector_id,
            purpose=purpose_enum,
            stack_level=stack_level,
        )

        if cleared > 0:
            self._log(
                f"Cleared {cleared} charging profile(s)",
            )
            return call_result.ClearChargingProfile(
                status=ClearChargingProfileStatus.accepted
            )
        else:
            return call_result.ClearChargingProfile(
                status=ClearChargingProfileStatus.unknown
            )

    @on("GetCompositeSchedule")
    async def on_get_composite_schedule(
        self,
        connector_id: int,
        duration: int,
        charging_rate_unit: Optional[str] = None,
        **kwargs,
    ) -> call_result.GetCompositeSchedule:
        """
        Handle GetCompositeSchedule request from CSMS.

        Returns the composite charging schedule for a connector, combining
        all applicable charging profiles.

        Args:
            connector_id: Connector to get schedule for.
            duration: Duration of the schedule in seconds.
            charging_rate_unit: Requested rate unit (Amps or Watts).
            **kwargs: Additional parameters.

        Returns:
            GetCompositeSchedule response with composite schedule.
        """
        self._log(
            f"GetCompositeSchedule: connector_id={connector_id}, duration={duration}s",
        )

        connector_id = self._validate_smart_charging_connector_id(connector_id, allow_zero=False)
        rate_unit = self._validate_charging_rate_unit(charging_rate_unit)

        transaction_id = self.active_transactions.get(connector_id)
        now = datetime.now(timezone.utc)

        # Get connector info for Watts->Amps conversion
        connector_voltage = 230.0
        phases = 1
        if self.get_connector_info:
            info = self.get_connector_info(connector_id)
            if info:
                connector_voltage, phases = info

        schedule_periods = self.charging_profile_manager.get_composite_schedule(
            connector_id=connector_id,
            transaction_id=transaction_id,
            start_time=now,
            duration=duration,
            connector_voltage=connector_voltage,
            phases=phases,
        )

        if not schedule_periods:
            return call_result.GetCompositeSchedule(status="Rejected")

        # Convert to OCPP format
        ocpp_periods = []
        for period in schedule_periods:
            period_dict = {
                "startPeriod": period.start_period,
                "limit": period.limit,
            }
            if period.number_phases is not None:
                period_dict["numberPhases"] = period.number_phases
            ocpp_periods.append(period_dict)

        return call_result.GetCompositeSchedule(
            status="Accepted",
            connector_id=connector_id,
            schedule_start=now.isoformat(),
            charging_schedule={
                "duration": duration,
                "chargingRateUnit": rate_unit,
                "chargingSchedulePeriod": ocpp_periods,
            },
        )

    # -------------------------------------------------------------------------
    # Outgoing OCPP Messages
    # -------------------------------------------------------------------------

    async def send_boot_notification(self) -> call_result.BootNotification:
        """
        Send BootNotification to the Central System.

        This should be called immediately after establishing the WebSocket
        connection. The response contains the registration status and
        heartbeat interval.

        Returns:
            BootNotification response from the CSMS.
        """
        request = call.BootNotification(
            charge_point_model=self.charge_point_model,
            charge_point_vendor=self.charge_point_vendor,
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
        if response.status == RegistrationStatus.accepted:
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

    async def send_heartbeat(self) -> call_result.Heartbeat:
        """
        Send Heartbeat to the Central System.

        Should be called periodically based on the heartbeat interval
        received in BootNotification response.

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

    async def send_authorize(self, id_tag: str) -> call_result.Authorize:
        """
        Send Authorize request to the Central System.

        First checks the local authorization list if enabled, then falls
        back to the CSMS if not found locally.

        Args:
            id_tag: The identifier to authorize.

        Returns:
            Authorize response with authorization status.
        """
        self._log(
            f"Authorize: id_tag={id_tag}",
        )

        # Check local authorization list first
        local_result = self._check_local_auth(id_tag)
        if local_result is not None:
            local_status, id_tag_info = local_result
            self._log(
                f"Authorize (local): id_tag={id_tag}, status={local_status.value}",
            )
            return call_result.Authorize(id_tag_info=id_tag_info)

        cache_enabled = self.config_manager.get_bool_value(
            "AuthorizationCacheEnabled", False
        )
        if cache_enabled:
            cached_id_tag_info = self.auth_cache.get(id_tag)
            if cached_id_tag_info is not None:
                self._log(
                    f"Authorize (cache): id_tag={id_tag}, status="
                    f"{cached_id_tag_info.get('status', 'Unknown')}",
                )
                return call_result.Authorize(id_tag_info=cached_id_tag_info)

        # Fall back to CSMS
        request = call.Authorize(id_tag=id_tag)
        response: call_result.Authorize = await self.call(request)
        status = (
            response.id_tag_info.get("status", "Unknown")
            if response.id_tag_info
            else "Unknown"
        )
        self._log(
            f"Authorize response: status={status}",
        )

        if cache_enabled and response.id_tag_info is not None:
            self.auth_cache.put(id_tag, response.id_tag_info)

        # Emit SecurityEventNotification for failed authorizations
        if status in ("Blocked", "Expired", "Invalid", "ConcurrentTx"):
            try:
                await self.send_security_event_notification(
                    event_type="FailedToAuthenticate",
                    timestamp=datetime.now(timezone.utc),
                    tech_info=f"id_tag={id_tag}, status={status}",
                )
            except Exception:
                self._log(
                    "SecurityEventNotification failed (non-critical)",
                    level=logging.DEBUG,
                )

        return response

    async def send_start_transaction(
        self, connector_id: int, id_tag: str, meter_start: int, timestamp: str
    ) -> call_result.StartTransaction:
        """
        Send StartTransaction to the Central System.

        Requests authorization to start a charging transaction. If accepted,
        the CSMS assigns a transaction ID.

        Args:
            connector_id: The connector where charging starts.
            id_tag: The authorization identifier.
            meter_start: Meter reading at transaction start (Wh).
            timestamp: ISO 8601 timestamp of transaction start.

        Returns:
            StartTransaction response with transaction ID.
        """
        self._log(
            f"StartTransaction: connector={connector_id}, id_tag={id_tag}",
        )

        # Check local authorization list first
        local_result = self._check_local_auth(id_tag)
        if local_result is not None:
            local_status, id_tag_info = local_result
            self._log(
                f"StartTransaction (local auth): id_tag={id_tag}, status={local_status.value}",
            )
            self._next_transaction_id += 1
            transaction_id = self._next_transaction_id
            self.set_active_transaction(connector_id, transaction_id)
            return call_result.StartTransaction(
                id_tag_info=id_tag_info,
                transaction_id=transaction_id,
            )

        # Fall back to CSMS
        request = call.StartTransaction(
            connector_id=connector_id,
            id_tag=id_tag,
            meter_start=meter_start,
            timestamp=timestamp,
        )

        response: call_result.StartTransaction = await self.call(request)
        id_tag_status = (
            response.id_tag_info.get("status", "Unknown")
            if response.id_tag_info
            else "Unknown"
        )
        self._log(
            f"StartTransaction response: tx_id={response.transaction_id}, "
            f"status={id_tag_status}",
        )

        if response.transaction_id:
            self.set_active_transaction(connector_id, response.transaction_id)

        return response

    async def send_stop_transaction(
        self,
        meter_stop: int,
        timestamp: str,
        transaction_id: int,
        reason: Optional[str] = None,
        meter_history: Optional[list[dict]] = None,
    ) -> call_result.StopTransaction:
        """
        Send StopTransaction to the Central System.

        Reports the end of a charging transaction with final meter reading.

        Args:
            meter_stop: Final meter reading (Wh).
            timestamp: ISO 8601 timestamp of transaction end.
            transaction_id: The transaction to stop.
            reason: Reason for stopping (Local, Remote, EVDisconnected, etc.).
            meter_history: Meter value history for transactionData.

        Returns:
            StopTransaction response.
        """
        transaction_data: Optional[list[dict]] = None
        max_values = self.config_manager.get_int_value("StopTransactionMaxLength", 0)

        if max_values > 0 and meter_history:
            recent = (
                meter_history[-max_values:]
                if len(meter_history) > max_values
                else meter_history
            )
            transaction_data = [
                {
                    "timestamp": entry["timestamp"],
                    "sampledValue": [
                        {
                            "value": str(entry["value"]),
                            "context": "Sample.Periodic",
                            "measurand": "Energy.Active.Import.Register",
                            "unit": "Wh",
                            "format": "Raw",
                            "location": "Outlet",
                        }
                    ],
                }
                for entry in recent
            ]

        request = call.StopTransaction(
            meter_stop=meter_stop,
            timestamp=timestamp,
            transaction_id=transaction_id,
            reason=reason,
            transaction_data=transaction_data,
        )
        self._log(
            f"StopTransaction: tx_id={transaction_id}, meter_stop={meter_stop}",
        )

        response: call_result.StopTransaction = await self.call(request)
        id_tag_status = (
            response.id_tag_info.get("status", "No info")
            if response.id_tag_info
            else "No info"
        )
        self._log(
            f"StopTransaction response: status={id_tag_status}",
        )

        # Clear the active transaction
        for conn_id, tx_id in list(self.active_transactions.items()):
            if tx_id == transaction_id:
                self.clear_active_transaction(conn_id)
                break

        return response

    async def send_meter_values(
        self,
        connector_id: int,
        value: float,
        transaction_id: Optional[int] = None,
        context: str = "Sample.Periodic",
    ) -> call_result.MeterValues:
        """
        Send MeterValues to the Central System.

        Reports energy consumption during a charging session.

        Args:
            connector_id: The connector being monitored.
            value: Meter reading in Watt-hours.
            transaction_id: Associated transaction ID if during a session.
            context: Meter value context (Sample.Periodic or Sample.Clock).

        Returns:
            MeterValues response.
        """
        request = call.MeterValues(
            connector_id=connector_id,
            transaction_id=transaction_id,
            meter_value=[
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sampled_value": [
                        {
                            "value": str(value),
                            "context": context,
                            "measurand": "Energy.Active.Import.Register",
                            "unit": "Wh",
                            "format": "Raw",
                            "location": "Outlet",
                        }
                    ],
                }
            ],
        )
        self._log(
            f"MeterValues: connector={connector_id}, value={value}Wh",
            level=logging.DEBUG,
        )

        response: call_result.MeterValues = await self.call(request)
        return response

    async def send_status_notification(
        self, connector_id: int, error_code: str, status: str
    ) -> call_result.StatusNotification:
        """
        Send StatusNotification to the Central System.

        Reports connector status changes.

        Args:
            connector_id: The connector whose status changed.
            error_code: Error code (typically "NoError").
            status: Connector status (Available, Preparing, Charging, etc.).

        Returns:
            StatusNotification response.
        """
        request = call.StatusNotification(
            connector_id=connector_id,
            error_code=error_code,
            status=status,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._log(
            f"StatusNotification: connector={connector_id}, status={status}",
        )

        response: call_result.StatusNotification = await self.call(request)
        return response

    async def send_diagnostics_status_notification(
        self, status: DiagnosticsStatus
    ) -> call_result.DiagnosticsStatusNotification:
        """
        Send DiagnosticsStatusNotification to the Central System.

        Reports diagnostics upload progress.

        Args:
            status: Current diagnostics status.

        Returns:
            DiagnosticsStatusNotification response.
        """
        request = call.DiagnosticsStatusNotification(status=status)
        self._log(
            f"DiagnosticsStatusNotification: status={status.value}",
        )

        response: call_result.DiagnosticsStatusNotification = await self.call(request)
        return response

    async def send_firmware_status_notification(
        self, status: FirmwareStatus
    ) -> call_result.FirmwareStatusNotification:
        """
        Send FirmwareStatusNotification to the Central System.

        Reports firmware update progress.

        Args:
            status: Current firmware update status.

        Returns:
            FirmwareStatusNotification response.
        """
        request = call.FirmwareStatusNotification(status=status)
        self._log(
            f"FirmwareStatusNotification: status={status.value}",
        )

        response: call_result.FirmwareStatusNotification = await self.call(request)
        return response

    async def send_security_event_notification(
        self,
        event_type: str,
        timestamp: datetime,
        tech_info: Optional[str] = None,
    ) -> call_result.SecurityEventNotification:
        """
        Send SecurityEventNotification to the Central System.

        Reports security-related events such as failed authentication
        attempts, invalid messages, or tampering detection.

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

    async def send_data_transfer(
        self,
        vendor_id: str,
        message_id: Optional[str] = None,
        data: Optional[str] = None,
    ) -> call_result.DataTransfer:
        """
        Send DataTransfer to the Central System.

        This is a thin wrapper around the OCPP request type.
        """
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

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _check_local_auth(self, id_tag: str) -> Optional[tuple[Optional[Any], dict]]:
        """
        Check the local authorization list for an id_tag.

        Returns None if not found locally (caller should fall back to CSMS).
        Returns (status, id_tag_info) if found locally.
        """
        local_status = self.local_auth_list.authorize(id_tag)
        if local_status is None:
            return None
        id_tag_info = self.local_auth_list.get_id_tag_info(id_tag) or {}
        id_tag_info["status"] = local_status.value
        return local_status, id_tag_info

    def register_data_transfer_handler(
        self,
        vendor_id: str,
        message_id: str,
        handler: Callable[[Optional[str]], tuple[DataTransferStatus, Optional[str]]],
    ) -> None:
        """
        Register a vendor-specific DataTransfer handler.
        """
        self.data_transfer_registry.register(vendor_id, message_id, handler)

    def _handle_capabilities_data_transfer(
        self, data: Optional[str]
    ) -> tuple[DataTransferStatus, Optional[str]]:
        """
        Return the simulator's built-in capability list.
        """
        payload = json.dumps(
            {
                "supports": [
                    "ReserveNow",
                    "CancelReservation",
                    "ClearCache",
                    "TriggerMessage",
                    "DataTransfer",
                ]
            }
        )
        return DataTransferStatus.accepted, payload
