import asyncio
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call, call_result
from ocpp.v16.datatypes import KeyValue
from ocpp.v16.enums import (
    DiagnosticsStatus,
    FirmwareStatus,
    RegistrationStatus,
    RemoteStartStopStatus,
    UpdateStatus,
    UpdateType,
)
from chargeghost_evse.ocpp_adapter.config_keys import ConfigurationKeyManager
from chargeghost_evse.ocpp_adapter.firmware_manager import FirmwareManager
from chargeghost_evse.ocpp_adapter.local_auth_list import LocalAuthListManager
from chargeghost_evse.util.event import Event
from chargeghost_evse.util.helpers import parse_bool_string


class Adapter(cp):
    def __init__(
        self,
        id: str,
        connection,
        command_queue=None,
        response_timeout: int = 30,
        charge_point_model: str = "ChargeGhostV1",
        charge_point_vendor: str = "ChargeGhost",
    ):
        super().__init__(id, connection, response_timeout)
        self.command_queue = command_queue
        self.on_log = Event()
        self.on_ocpp_message = Event()

        self.charge_point_model = charge_point_model
        self.charge_point_vendor = charge_point_vendor
        self.heartbeat_interval: int = 0
        self.registration_status: Optional[RegistrationStatus] = None
        self.active_transactions: Dict[int, int] = {}
        self._next_transaction_id: int = 0
        self.on_registration_accepted = Event()
        self.on_heartbeat_response = Event()

        self.firmware_manager = FirmwareManager()
        self.firmware_manager.on_log.subscribe(self._log_from_firmware_manager)
        self._firmware_task: Optional[asyncio.Task] = None
        self._diagnostics_task: Optional[asyncio.Task] = None

        self.config_manager = ConfigurationKeyManager()
        self.config_manager.initialize_defaults()

        local_auth_max = self.config_manager.get_int_value(
            "LocalAuthListMaxLength", 100
        )
        self.local_auth_list = LocalAuthListManager(max_entries=local_auth_max)
        local_auth_enabled = self.config_manager.get_bool_value(
            "LocalAuthListEnabled", False
        )
        self.local_auth_list.enabled = local_auth_enabled

        self.config_manager.on_key_changed.subscribe(self._on_config_key_changed)

    def _log(
        self, message: str, *, is_ocpp_message: bool = False, is_important: bool = True
    ) -> None:
        self.on_log.emit(
            message=message, is_ocpp_message=is_ocpp_message, is_important=is_important
        )

    def _on_config_key_changed(self, key_name: str, new_value: str) -> None:
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
        self._log(message, is_ocpp_message=False, is_important=True)

    def _log_ocpp_raw(
        self, direction: str, action: str, payload: Any, message_id: str = ""
    ) -> None:
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

    async def _send_call(self, message):
        self._log_ocpp_raw("TX", message.__class__.__name__, message.__dict__)
        return await super()._send_call(message)

    async def _handle_call(self, msg):
        if hasattr(msg, "unique_id") and hasattr(msg, "action"):
            payload = getattr(msg, "payload", msg.__dict__)
            self._log_ocpp_raw("RX", msg.action, payload, getattr(msg, "unique_id", ""))
        return await super()._handle_call(msg)

    def get_active_transaction_id(self, connector_id: int) -> Optional[int]:
        return self.active_transactions.get(connector_id)

    def set_active_transaction(self, connector_id: int, transaction_id: int) -> None:
        self.active_transactions[connector_id] = transaction_id

    def clear_active_transaction(self, connector_id: int) -> None:
        if connector_id in self.active_transactions:
            del self.active_transactions[connector_id]

    @on("RemoteStartTransaction")
    async def on_remote_start_transaction(
        self, connector_id: Optional[int], id_tag: str, **kwargs
    ) -> call_result.RemoteStartTransaction:
        self._log(
            f"RemoteStartTransaction: connector_id={connector_id}, id_tag={id_tag}",
            is_ocpp_message=True,
            is_important=True,
        )

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
        self._log(
            f"RemoteStopTransaction: transaction_id={transaction_id}",
            is_ocpp_message=True,
            is_important=True,
        )

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
        self._log(
            f"GetConfiguration: keys={key}",
            is_ocpp_message=True,
            is_important=True,
        )

        configuration_key: list[KeyValue] = []
        unknown_key: list[str] = []

        if not key:
            for config_key in self.config_manager.get_all_keys():
                configuration_key.append(
                    KeyValue(
                        key=config_key.key,
                        readonly=config_key.readonly,
                        value=config_key.value,
                    )
                )
        else:
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

        if self._diagnostics_task and not self._diagnostics_task.done():
            self._diagnostics_task.cancel()

        async def run_diagnostics_upload() -> None:
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

        if self._firmware_task and not self._firmware_task.done():
            self._firmware_task.cancel()

        async def run_firmware_update() -> None:
            try:
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
                    is_ocpp_message=False,
                    is_important=True,
                )
                await self.send_firmware_status_notification(
                    FirmwareStatus.installation_failed
                )

        self._firmware_task = asyncio.create_task(run_firmware_update())

        return call_result.UpdateFirmware()

    async def send_boot_notification(self) -> call_result.BootNotification:
        request = call.BootNotification(
            charge_point_model=self.charge_point_model,
            charge_point_vendor=self.charge_point_vendor,
        )
        self._log(
            f"BootNotification: model={self.charge_point_model}, vendor={self.charge_point_vendor}",
            is_ocpp_message=True,
            is_important=True,
        )

        response: call_result.BootNotification = await self.call(request)
        self._log(
            f"BootNotification response: status={response.status}, interval={response.interval}",
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
        self._log(
            f"Authorize: id_tag={id_tag}", is_ocpp_message=True, is_important=True
        )

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
        self._log(
            f"StartTransaction: connector={connector_id}, id_tag={id_tag}",
            is_ocpp_message=True,
            is_important=True,
        )

        local_status = self.local_auth_list.authorize(id_tag)
        if local_status is not None:
            self._log(
                f"StartTransaction (local auth): id_tag={id_tag}, status={local_status.value}",
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
            f"StartTransaction response: tx_id={response.transaction_id}, status={id_tag_status}",
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

        for conn_id, tx_id in list(self.active_transactions.items()):
            if tx_id == transaction_id:
                self.clear_active_transaction(conn_id)
                break

        return response

    async def send_meter_values(
        self, connector_id: int, value: float, transaction_id: Optional[int] = None
    ) -> call_result.MeterValues:
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
        request = call.FirmwareStatusNotification(status=status)
        self._log(
            f"FirmwareStatusNotification: status={status.value}",
            is_ocpp_message=True,
            is_important=True,
        )

        response: call_result.FirmwareStatusNotification = await self.call(request)
        return response
