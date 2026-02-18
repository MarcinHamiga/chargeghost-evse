import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call, call_result
from ocpp.v16.enums import RegistrationStatus, RemoteStartStopStatus
from chargeghost_evse.util.event import Event


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
        self.on_registration_accepted = Event()
        self.on_heartbeat_response = Event()

    def _log(
        self, message: str, *, is_ocpp_message: bool = False, is_important: bool = True
    ) -> None:
        self.on_log.emit(
            message=message, is_ocpp_message=is_ocpp_message, is_important=is_important
        )

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
        }

        self.on_ocpp_message.emit(
            direction=direction, action=action, payload=payload_str
        )
        self._log(raw_msg, is_ocpp_message=True, is_important=is_important)

    async def _send_call(self, call):
        self._log_ocpp_raw("TX", call.__class__.__name__, call.__dict__)
        return await super()._send_call(call)

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
        if connector_id is not None:
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

            if ocpp_connector_id < 1:
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
            self._log(
                f"Enqueuing START for connector {target_connector_id}",
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
        request = call.Authorize(id_tag=id_tag)
        self._log(
            f"Authorize: id_tag={id_tag}", is_ocpp_message=True, is_important=True
        )

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
        request = call.StartTransaction(
            connector_id=connector_id,
            id_tag=id_tag,
            meter_start=meter_start,
            timestamp=timestamp,
        )
        self._log(
            f"StartTransaction: connector={connector_id}, id_tag={id_tag}",
            is_ocpp_message=True,
            is_important=True,
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
