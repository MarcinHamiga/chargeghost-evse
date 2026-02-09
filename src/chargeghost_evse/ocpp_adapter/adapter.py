import asyncio
import websockets
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call, call_result
from ocpp.v16.enums import RegistrationStatus

class Adapter(cp):
	async def send_boot_notification(self):
		request = call.BootNotification(
			charge_point_model="ChargeGhostV1",
			charge_point_vendor="ChargeGhost"
		)
		response: call_result.BootNotification = await self.call(request)
		if response.status == RegistrationStatus.accepted:
			print("Connection accepted")

	
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
