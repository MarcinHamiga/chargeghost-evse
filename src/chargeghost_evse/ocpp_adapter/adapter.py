import asyncio
import websockets
from datetime import datetime, timezone
from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call, call_result
from ocpp.v16.enums import RegistrationStatus, RemoteStartStopStatus
from chargeghost_evse.util.event import Event

class Adapter(cp):
	def __init__(self, id, connection, command_queue=None, response_timeout=30):
		super().__init__(id, connection, response_timeout)
		self.command_queue = command_queue
		self.on_log = Event()

	def _log(self, message):
		self.on_log.emit(message)

	@on("RemoteStartTransaction")
	async def on_remote_start_transaction(self, connector_id, id_tag, **kwargs):
		self._log(f"Received RemoteStartTransaction: connector_id={connector_id}, id_tag={id_tag}")
		if self.command_queue:
			self.command_queue.put({
				"action": "START",
				"connector_id": connector_id,
				"id_tag": id_tag
			})
			return call_result.RemoteStartTransaction(status=RemoteStartStopStatus.accepted)
		return call_result.RemoteStartTransaction(status=RemoteStartStopStatus.rejected)

	@on("RemoteStopTransaction")
	async def on_remote_stop_transaction(self, transaction_id, **kwargs):
		self._log(f"Received RemoteStopTransaction: transaction_id={transaction_id}")
		if self.command_queue:
			self.command_queue.put({"action": "STOP"})
			return call_result.RemoteStopTransaction(status=RemoteStartStopStatus.accepted)
		return call_result.RemoteStopTransaction(status=RemoteStartStopStatus.rejected)

	async def send_boot_notification(self):
		request = call.BootNotification(
			charge_point_model="ChargeGhostV1",
			charge_point_vendor="ChargeGhost"
		)
		self._log(f"Sending BootNotification: {request}")
		response: call_result.BootNotification = await self.call(request)
		self._log(f"Received BootNotification response: {response.status}")
		if response.status == RegistrationStatus.accepted:
			self._log("Connection accepted")
		return response

	async def send_heartbeat(self):
		request = call.Heartbeat()
		self._log(f"Sending Heartbeat")
		response: call_result.Heartbeat = await self.call(request)
		self._log(f"Received Heartbeat response: {response.current_time}")
		return response

	async def send_start_transaction(self, connector_id, id_tag, meter_start, timestamp):
		request = call.StartTransaction(
			connector_id=connector_id,
			id_tag=id_tag,
			meter_start=meter_start,
			timestamp=timestamp
		)
		self._log(f"Sending StartTransaction: connector_id={connector_id}, id_tag={id_tag}")
		response: call_result.StartTransaction = await self.call(request)
		self._log(f"Received StartTransaction response: transaction_id={response.transaction_id}, status={response.id_tag_info['status']}")
		return response

	async def send_stop_transaction(self, meter_stop, timestamp, transaction_id, reason=None):
		request = call.StopTransaction(
			meter_stop=meter_stop,
			timestamp=timestamp,
			transaction_id=transaction_id,
			reason=reason
		)
		self._log(f"Sending StopTransaction: transaction_id={transaction_id}")
		response: call_result.StopTransaction = await self.call(request)
		self._log(f"Received StopTransaction response: {response.id_tag_info['status'] if response.id_tag_info else 'No info'}")
		return response

	async def send_meter_values(self, connector_id, value, transaction_id=None):
		request = call.MeterValues(
			connector_id=connector_id,
			transaction_id=transaction_id,
			meter_value=[{
				"timestamp": datetime.now(timezone.utc).isoformat(),
				"sampled_value": [{"value": str(value), "context": "Sample.Periodic", "measurand": "Energy.Active.Import.Register", "unit": "Wh"}]
			}]
		)
		self._log(f"Sending MeterValues: connector_id={connector_id}, value={value}")
		response: call_result.MeterValues = await self.call(request)
		return response

	async def send_status_notification(self, connector_id, error_code, status):
		request = call.StatusNotification(
			connector_id=connector_id,
			error_code=error_code,
			status=status,
			timestamp=datetime.now(timezone.utc).isoformat()
		)
		self._log(f"Sending StatusNotification: connector_id={connector_id}, status={status}")
		response: call_result.StatusNotification = await self.call(request)
		return response

	
async def main():
	async with websockets.connect(
		"ws://localhost:3000/CP_1", subprotocols=["ocpp1.6"]
	) as ws:
		charge_point = Adapter("CP_1", ws)

		await asyncio.gather(
			charge_point.start(),
			charge_point.send_boot_notification()
		)

if __name__ == "__main__":
	asyncio.run(main())
