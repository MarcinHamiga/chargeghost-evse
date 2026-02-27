"""
OCPP 1.6 Adapter Module.

This module implements the OCPP 1.6 protocol adapter for the ChargeGhost EVSE
simulator. It provides bidirectional communication between the charge point
and a Central System (CSMS), handling both incoming requests and outgoing
messages.

The adapter implements the following OCPP 1.6 features:
- Core profile: BootNotification, Heartbeat, StatusNotification, etc.
- Smart Charging profile: SetChargingProfile, ClearChargingProfile, GetCompositeSchedule
- Firmware Management profile: UpdateFirmware, GetDiagnostics
- Local Auth List Management profile: SendLocalList, GetLocalListVersion

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
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call, call_result
from ocpp.v16.datatypes import KeyValue
from ocpp.v16.enums import (
    ChargingProfileKindType,
    ChargingProfilePurposeType,
    ChargingProfileStatus,
    ChargingRateUnitType,
    ClearChargingProfileStatus,
    DiagnosticsStatus,
    FirmwareStatus,
    RecurrencyKind,
    RegistrationStatus,
    RemoteStartStopStatus,
    UpdateStatus,
    UpdateType,
)

from chargeghost_evse.ocpp_adapter.charging_profile_manager import (
    ChargingProfileData,
    ChargingProfileManager,
    ChargingScheduleData,
    ChargingSchedulePeriodData,
)
from chargeghost_evse.ocpp_adapter.config_keys import ConfigurationKeyManager
from chargeghost_evse.ocpp_adapter.firmware_manager import FirmwareManager
from chargeghost_evse.ocpp_adapter.local_auth_list import LocalAuthListManager
from chargeghost_evse.util.event import Event
from chargeghost_evse.util.helpers import parse_bool_string


class Adapter(cp):
    """
    OCPP 1.6 Charge Point adapter implementation.

    This class extends the ocpp library's ChargePoint class to implement
    the EVSE side of OCPP 1.6 communication. It handles incoming messages
    from the Central System and provides methods to send messages to it.

    The adapter integrates several managers for different OCPP features:
    - ConfigurationKeyManager: OCPP configuration key storage
    - ChargingProfileManager: Smart Charging profile management
    - LocalAuthListManager: Local authorization list storage
    - FirmwareManager: Firmware update and diagnostics handling

    Events:
        on_log: Emitted for log messages.
            Parameters: message (str), is_ocpp_message (bool), is_important (bool)
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

        # Command queue for Engine communication
        self.command_queue = command_queue

        # Event emitters
        self.on_log = Event()
        self.on_ocpp_message = Event()

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
        self.firmware_manager.on_log.subscribe(self._log_from_firmware_manager)
        self._firmware_task: Optional[asyncio.Task] = None
        self._diagnostics_task: Optional[asyncio.Task] = None

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

        # Subscribe to configuration changes
        self.config_manager.on_key_changed.subscribe(self._on_config_key_changed)

        # Injectable callback for connector info (set by Bridge)
        # Signature: (connector_id: int) -> Optional[tuple[voltage, phases]]
        self.get_connector_info: Optional[
            Callable[[int], Optional[tuple[float, int]]]
        ] = None

    def _log(
        self,
        message: str,
        *,
        is_ocpp_message: bool = False,
        is_important: bool = True,
    ) -> None:
        """
        Emit a log message event.

        Args:
            message: Log message text.
            is_ocpp_message: Whether this is an OCPP protocol message.
            is_important: Whether this should be shown in compact log mode.
        """
        self.on_log.emit(
            message=message,
            is_ocpp_message=is_ocpp_message,
            is_important=is_important,
        )

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
                is_ocpp_message=False,
                is_important=True,
            )
        elif key_name == "LocalAuthListMaxLength":
            try:
                max_entries = int(new_value)
                self.local_auth_list.max_entries = max_entries
                self._log(
                    f"LocalAuthListMaxLength changed to {max_entries}",
                    is_ocpp_message=False,
                    is_important=True,
                )
            except (TypeError, ValueError):
                pass
        elif key_name == "HeartbeatInterval":
            try:
                self.heartbeat_interval = int(new_value)
                self._log(
                    f"HeartbeatInterval updated to {new_value}s",
                    is_ocpp_message=False,
                    is_important=True,
                )
            except (TypeError, ValueError):
                pass
        elif key_name == "MeterValueSampleInterval":
            self._log(
                f"MeterValueSampleInterval updated to {new_value}s",
                is_ocpp_message=False,
                is_important=True,
            )
        elif key_name == "ConnectionTimeout":
            try:
                self.response_timeout = int(new_value)
                self._log(
                    f"Response timeout updated to {new_value}s",
                    is_ocpp_message=False,
                    is_important=True,
                )
            except (TypeError, ValueError):
                pass

    def _log_from_firmware_manager(self, message: str) -> None:
        """
        Forward log messages from the firmware manager.

        Args:
            message: Log message from firmware manager.
        """
        self._log(message, is_ocpp_message=False, is_important=True)

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

        # Determine if this message is important for compact logging
        is_important = action in {
            "BootNotification",
            "StartTransaction",
            "StopTransaction",
            "Authorize",
            "RemoteStartTransaction",
            "RemoteStopTransaction",
            "StatusNotification",
            "MeterValues",
            "Heartbeat",
            "GetDiagnostics",
            "DiagnosticsStatusNotification",
            "UpdateFirmware",
            "FirmwareStatusNotification",
            "GetConfiguration",
            "ChangeConfiguration",
            "SendLocalList",
            "GetLocalListVersion",
        }

        self.on_ocpp_message.emit(
            direction=direction, action=action, payload=payload_str
        )
        self._log(raw_msg, is_ocpp_message=True, is_important=is_important)

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
            self._log_ocpp_raw(
                "RX", msg.action, payload, getattr(msg, "unique_id", "")
            )
        return await super()._handle_call(msg)

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

    @on("RemoteStartTransaction")
    async def on_remote_start_transaction(
        self, connector_id: Optional[int], id_tag: str, **kwargs
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
            is_ocpp_message=True,
            is_important=True,
        )

        # Validate connector_id if provided
        target_connector_id: Optional[int] = None
        if connector_id is not None and connector_id != 0:
            try:
                ocpp_connector_id = int(connector_id)
            except (TypeError, ValueError):
                self._log(
                    f"Invalid connector_id: {connector_id}",
                    is_ocpp_message=False,
                    is_important=True,
                )
                return call_result.RemoteStartTransaction(
                    status=RemoteStartStopStatus.rejected
                )

            if ocpp_connector_id < 0:
                self._log(
                    f"Out-of-range connector_id: {ocpp_connector_id}",
                    is_ocpp_message=False,
                    is_important=True,
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
                is_ocpp_message=False,
                is_important=False,
            )
            self.command_queue.put(
                {
                    "action": "START",
                    "connector_id": target_connector_id,
                    "id_tag": id_tag,
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
            is_ocpp_message=True,
            is_important=True,
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
                is_ocpp_message=False,
                is_important=True,
            )
            return call_result.RemoteStopTransaction(
                status=RemoteStartStopStatus.rejected
            )

        # Queue command for Engine
        if self.command_queue:
            self._log(
                f"Enqueuing STOP for tx {transaction_id}",
                is_ocpp_message=False,
                is_important=False,
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
            is_ocpp_message=True,
            is_important=True,
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
                        value=config_key.value,
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
                            value=found_key.value,
                        )
                    )
                else:
                    unknown_key.append(k)

        return call_result.GetConfiguration(
            configuration_key=configuration_key,
            unknown_key=unknown_key if unknown_key else None,
        )

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
            is_ocpp_message=True,
            is_important=True,
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
            is_ocpp_message=True,
            is_important=True,
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
            is_ocpp_message=True,
            is_important=True,
        )

        try:
            update_type_enum = UpdateType(update_type)
        except ValueError:
            self._log(
                f"Invalid update_type: {update_type}",
                is_ocpp_message=False,
                is_important=True,
            )
            return call_result.SendLocalList(status=UpdateStatus.failed)

        success, message = self.local_auth_list.update_list(
            list_version=list_version,
            local_authorization_list=local_authorization_list,
            update_type=update_type_enum,
        )

        status = UpdateStatus.accepted if success else UpdateStatus.failed
        self._log(
            f"SendLocalList result: {status.value} - {message}",
            is_ocpp_message=False,
            is_important=True,
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
            is_ocpp_message=True,
            is_important=True,
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
                    is_ocpp_message=False,
                    is_important=True,
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
            is_ocpp_message=True,
            is_important=True,
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
                await self.send_firmware_status_notification(FirmwareStatus.downloading)
                success = await self.firmware_manager.simulate_firmware_update()
                if success:
                    await self.send_firmware_status_notification(FirmwareStatus.installed)
                else:
                    await self.send_firmware_status_notification(
                        FirmwareStatus.installation_failed
                    )
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self._log(
                    f"Firmware update error: {e}",
                    is_ocpp_message=False,
                    is_important=True,
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
            f"profile_id={cs_charging_profiles.get('chargingProfileId')}",
            is_ocpp_message=True,
            is_important=True,
        )

        try:
            profile = self._parse_charging_profile(cs_charging_profiles)
        except (KeyError, ValueError, TypeError) as e:
            self._log(
                f"Failed to parse charging profile: {e}",
                is_ocpp_message=False,
                is_important=True,
            )
            return call_result.SetChargingProfile(status=ChargingProfileStatus.rejected)

        error = self.charging_profile_manager.set_profile(connector_id, profile)
        if error:
            self._log(
                f"Charging profile rejected: {error}",
                is_ocpp_message=False,
                is_important=True,
            )
            return call_result.SetChargingProfile(status=ChargingProfileStatus.rejected)

        self._log(
            f"Charging profile {profile.charging_profile_id} accepted",
            is_ocpp_message=False,
            is_important=True,
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
            is_ocpp_message=True,
            is_important=True,
        )

        # Parse purpose enum if provided
        purpose_enum = None
        if charging_profile_purpose:
            try:
                purpose_enum = ChargingProfilePurposeType(charging_profile_purpose)
            except ValueError:
                return call_result.ClearChargingProfile(
                    status=ClearChargingProfileStatus.unknown
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
                is_ocpp_message=False,
                is_important=True,
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
            is_ocpp_message=True,
            is_important=True,
        )

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

        rate_unit = charging_rate_unit or ChargingRateUnitType.amps

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
            is_ocpp_message=True,
            is_important=True,
        )

        response: call_result.BootNotification = await self.call(request)
        self._log(
            f"BootNotification response: status={response.status}, "
            f"interval={response.interval}",
            is_ocpp_message=True,
            is_important=True,
        )

        self.registration_status = response.status
        if response.status == RegistrationStatus.accepted:
            self.heartbeat_interval = response.interval
            self._log(
                f"Registration accepted. Heartbeat: {self.heartbeat_interval}s",
                is_ocpp_message=False,
                is_important=True,
            )
            self.on_registration_accepted.emit()
        else:
            self._log(
                f"Registration status: {response.status}",
                is_ocpp_message=False,
                is_important=True,
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
        self._log("Heartbeat", is_ocpp_message=True, is_important=True)

        response: call_result.Heartbeat = await self.call(request)
        self._log(
            f"Heartbeat response: {response.current_time}",
            is_ocpp_message=True,
            is_important=True,
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
            is_ocpp_message=True,
            is_important=True,
        )

        # Check local authorization list first
        local_status = self.local_auth_list.authorize(id_tag)
        if local_status is not None:
            self._log(
                f"Authorize (local): id_tag={id_tag}, status={local_status.value}",
                is_ocpp_message=False,
                is_important=True,
            )
            id_tag_info = self.local_auth_list.get_id_tag_info(id_tag) or {}
            id_tag_info["status"] = local_status.value
            return call_result.Authorize(id_tag_info=id_tag_info)

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
            is_ocpp_message=True,
            is_important=True,
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
            is_ocpp_message=True,
            is_important=True,
        )

        # Check local authorization list first
        local_status = self.local_auth_list.authorize(id_tag)
        if local_status is not None:
            self._log(
                f"StartTransaction (local auth): id_tag={id_tag}, "
                f"status={local_status.value}",
                is_ocpp_message=False,
                is_important=True,
            )
            id_tag_info = self.local_auth_list.get_id_tag_info(id_tag) or {}
            id_tag_info["status"] = local_status.value
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
            is_ocpp_message=True,
            is_important=True,
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
    ) -> call_result.StopTransaction:
        """
        Send StopTransaction to the Central System.

        Reports the end of a charging transaction with final meter reading.

        Args:
            meter_stop: Final meter reading (Wh).
            timestamp: ISO 8601 timestamp of transaction end.
            transaction_id: The transaction to stop.
            reason: Reason for stopping (Local, Remote, EVDisconnected, etc.).

        Returns:
            StopTransaction response.
        """
        request = call.StopTransaction(
            meter_stop=meter_stop,
            timestamp=timestamp,
            transaction_id=transaction_id,
            reason=reason,
        )
        self._log(
            f"StopTransaction: tx_id={transaction_id}, meter_stop={meter_stop}",
            is_ocpp_message=True,
            is_important=True,
        )

        response: call_result.StopTransaction = await self.call(request)
        id_tag_status = (
            response.id_tag_info.get("status", "No info")
            if response.id_tag_info
            else "No info"
        )
        self._log(
            f"StopTransaction response: status={id_tag_status}",
            is_ocpp_message=True,
            is_important=True,
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
    ) -> call_result.MeterValues:
        """
        Send MeterValues to the Central System.

        Reports energy consumption during a charging session.

        Args:
            connector_id: The connector being monitored.
            value: Meter reading in Watt-hours.
            transaction_id: Associated transaction ID if during a session.

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
                            "context": "Sample.Periodic",
                            "measurand": "Energy.Active.Import.Register",
                            "unit": "Wh",
                        }
                    ],
                }
            ],
        )
        self._log(
            f"MeterValues: connector={connector_id}, value={value}Wh",
            is_ocpp_message=True,
            is_important=True,
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
            is_ocpp_message=True,
            is_important=True,
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
            is_ocpp_message=True,
            is_important=True,
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
            is_ocpp_message=True,
            is_important=True,
        )

        response: call_result.FirmwareStatusNotification = await self.call(request)
        return response

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _parse_charging_profile(self, cs_profile: dict) -> ChargingProfileData:
        """
        Parse OCPP CsChargingProfile to internal ChargingProfileData.

        Converts the OCPP dictionary format to the internal dataclass
        representation for use with ChargingProfileManager.

        Args:
            cs_profile: OCPP CsChargingProfile dictionary.

        Returns:
            ChargingProfileData instance.

        Raises:
            KeyError: If required fields are missing.
            ValueError: If enum values are invalid.
        """
        cs_schedule = cs_profile["chargingSchedule"]

        # Parse schedule periods
        periods = []
        for p in cs_schedule["chargingSchedulePeriod"]:
            period = ChargingSchedulePeriodData(
                start_period=p["startPeriod"],
                limit=float(p["limit"]),
                number_phases=p.get("numberPhases"),
            )
            periods.append(period)

        # Parse schedule
        schedule = ChargingScheduleData(
            charging_rate_unit=ChargingRateUnitType(cs_schedule["chargingRateUnit"]),
            charging_schedule_period=tuple(periods),
            duration=cs_schedule.get("duration"),
            start_schedule=(
                datetime.fromisoformat(
                    cs_schedule["startSchedule"].replace("Z", "+00:00")
                )
                if cs_schedule.get("startSchedule")
                else None
            ),
            min_charging_rate=cs_schedule.get("minChargingRate"),
        )

        # Parse recurrency kind
        recurrency = None
        if cs_profile.get("recurrencyKind"):
            recurrency = RecurrencyKind(cs_profile["recurrencyKind"])

        # Parse validity period
        valid_from = None
        if cs_profile.get("validFrom"):
            valid_from = datetime.fromisoformat(
                cs_profile["validFrom"].replace("Z", "+00:00")
            )

        valid_to = None
        if cs_profile.get("validTo"):
            valid_to = datetime.fromisoformat(
                cs_profile["validTo"].replace("Z", "+00:00")
            )

        return ChargingProfileData(
            charging_profile_id=cs_profile["chargingProfileId"],
            stack_level=cs_profile["stackLevel"],
            charging_profile_purpose=ChargingProfilePurposeType(
                cs_profile["chargingProfilePurpose"]
            ),
            charging_profile_kind=ChargingProfileKindType(
                cs_profile["chargingProfileKind"]
            ),
            charging_schedule=schedule,
            transaction_id=cs_profile.get("transactionId"),
            recurrency_kind=recurrency,
            valid_from=valid_from,
            valid_to=valid_to,
        )
