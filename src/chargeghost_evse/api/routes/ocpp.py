from __future__ import annotations

from fastapi import APIRouter, Depends

from chargeghost_evse.api.dependencies import get_runtime
from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.schemas import ActionResult, OcppConfigKeyInfo

router = APIRouter(prefix="/api/v1/ocpp", tags=["ocpp"])


@router.post("/connect", response_model=ActionResult)
async def connect(runtime: SimulationRuntime = Depends(get_runtime)) -> ActionResult:
	return await runtime.call(runtime.controller.connect)


@router.post("/disconnect", response_model=ActionResult)
async def disconnect(runtime: SimulationRuntime = Depends(get_runtime)) -> ActionResult:
	return await runtime.call(runtime.controller.disconnect)


@router.post("/authorize", response_model=ActionResult)
async def authorize(
	id_tag: str = "",
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	return await runtime.call(runtime.controller.authorize, id_tag)


@router.post("/heartbeat", response_model=ActionResult)
async def send_heartbeat(runtime: SimulationRuntime = Depends(get_runtime)) -> ActionResult:
	return await runtime.call(runtime.controller.send_heartbeat)


@router.get("/connection_status")
async def connection_status(
	runtime: SimulationRuntime = Depends(get_runtime),
) -> dict[str, bool]:
	connected = await runtime.call(lambda: runtime.controller.is_connected)
	return {"connected": connected}


@router.get("/config-keys", response_model=list[OcppConfigKeyInfo])
async def get_config_keys(
	runtime: SimulationRuntime = Depends(get_runtime),
) -> list[OcppConfigKeyInfo]:
	keys = await runtime.call(
		lambda: (
			[]
			if runtime.bridge is None
			else [
				{
					"key": config_key.key,
					"value": config_key.get_value(),
					"readonly": config_key.readonly,
					"default": config_key.default,
					"description": config_key.description,
					"mandatory": config_key.mandatory,
					"category": config_key.category,
				}
				for config_key in runtime.bridge.get_ocpp_config_keys()
			]
		)
	)
	return [OcppConfigKeyInfo.model_validate(config_key) for config_key in keys]
