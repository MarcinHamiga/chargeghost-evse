from datetime import datetime, timezone
from typing import Optional, Dict
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

        self.charge_point_model = charge_point_model
        self.charge_point_vendor = charge_point_vendor
        self.heartbeat_interval: int = 0
        self.registration_status: Optional[RegistrationStatus] = None
        self.active_transactions: Dict[int, int] = {}
        self.on_registration_accepted = Event()
        self.on_heartbeat_response = Event()

    def _log(self, message: str) -> None:
        self.on_log.emit(message=message)

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
            message=f"Received RemoteStartTransaction: connector_id={connector_id}, id_tag={id_tag}"
        )

        internal_connector_index: Optional[int] = None
        if connector_id is not None:
            try:
                ocpp_connector_id = int(connector_id)
            except (TypeError, ValueError):
                self._log(message=f"Invalid connector_id received: {connector_id}")
                return call_result.RemoteStartTransaction(
                    status=RemoteStartStopStatus.rejected
                )

            if ocpp_connector_id <= 0:
                self._log(message=f"Out-of-range connector_id: {ocpp_connector_id}")
                return call_result.RemoteStartTransaction(
                    status=RemoteStartStopStatus.rejected
                )

            internal_connector_index = ocpp_connector_id - 1

        if self.command_queue:
            self._log(
                message=f"Enqueuing START command for connector index: {internal_connector_index}"
            )
            self.command_queue.put(
                {
                    "action": "START",
                    "connector_id": internal_connector_index,
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
            message=f"Received RemoteStopTransaction: transaction_id={transaction_id}"
        )

        matching_connector: Optional[int] = None
        for conn_id, tx_id in self.active_transactions.items():
            if tx_id == transaction_id:
                matching_connector = conn_id
                break

        if matching_connector is None:
            self._log(message=f"No active transaction found with id: {transaction_id}")
            return call_result.RemoteStopTransaction(
                status=RemoteStartStopStatus.rejected
            )

        if self.command_queue:
            self._log(
                message=f"Enqueuing STOP command for transaction: {transaction_id}"
            )
            self.command_queue.put(
                {
                    "action": "STOP",
                    "transaction_id": transaction_id,
                    "connector_id": matching_connector,
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
            message=f"Sending BootNotification: model={self.charge_point_model}, vendor={self.charge_point_vendor}"
        )

        response: call_result.BootNotification = await self.call(request)
        self._log(
            message=f"BootNotification response: status={response.status}, interval={response.interval}"
        )

        self.registration_status = response.status
        if response.status == RegistrationStatus.accepted:
            self.heartbeat_interval = response.interval
            self._log(
                message=f"Registration accepted. Heartbeat interval: {self.heartbeat_interval}s"
            )
            self.on_registration_accepted.emit()
        else:
            self._log(message=f"Registration status: {response.status}")

        return response

    async def send_heartbeat(self) -> call_result.Heartbeat:
        request = call.Heartbeat()
        self._log(message="Sending Heartbeat")

        response: call_result.Heartbeat = await self.call(request)
        self._log(message=f"Heartbeat response: current_time={response.current_time}")
        self.on_heartbeat_response.emit(current_time=response.current_time)

        return response

    async def send_authorize(self, id_tag: str) -> call_result.Authorize:
        request = call.Authorize(id_tag=id_tag)
        self._log(message=f"Sending Authorize: id_tag={id_tag}")

        response: call_result.Authorize = await self.call(request)
        status = (
            response.id_tag_info.get("status", "Unknown")
            if response.id_tag_info
            else "Unknown"
        )
        self._log(message=f"Authorize response: status={status}")

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
            message=f"Sending StartTransaction: connector_id={connector_id}, id_tag={id_tag}"
        )

        response: call_result.StartTransaction = await self.call(request)
        id_tag_status = (
            response.id_tag_info.get("status", "Unknown")
            if response.id_tag_info
            else "Unknown"
        )
        self._log(
            message=f"StartTransaction response: transaction_id={response.transaction_id}, status={id_tag_status}"
        )

        if response.transaction_id:
            self.set_active_transaction(connector_id - 1, response.transaction_id)

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
            message=f"Sending StopTransaction: transaction_id={transaction_id}, meter_stop={meter_stop}"
        )

        response: call_result.StopTransaction = await self.call(request)
        id_tag_status = (
            response.id_tag_info.get("status", "No info")
            if response.id_tag_info
            else "No info"
        )
        self._log(message=f"StopTransaction response: status={id_tag_status}")

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
            message=f"Sending MeterValues: connector_id={connector_id}, value={value}Wh"
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
            message=f"Sending StatusNotification: connector_id={connector_id}, status={status}"
        )

        response: call_result.StatusNotification = await self.call(request)
        return response
