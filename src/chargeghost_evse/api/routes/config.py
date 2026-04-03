from __future__ import annotations

from fastapi import APIRouter, Depends

from chargeghost_evse.api.dependencies import get_runtime
from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.schemas import ActionResult, ConfigInfo, ConfigUpdate

router = APIRouter(prefix="/api/v1/config", tags=["config"])


@router.get("", response_model=ConfigInfo)
async def get_config(runtime: SimulationRuntime = Depends(get_runtime)) -> ConfigInfo:
	return ConfigInfo.model_validate(await runtime.config_snapshot())


@router.patch("", response_model=ActionResult)
async def update_config(
	update: ConfigUpdate,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	updates = update.model_dump(exclude_unset=True)
	if not updates:
		return ActionResult(success=True, message="No changes applied")

	result = await runtime.apply_config_patch(updates)
	if not result.success:
		return ActionResult(success=False, message=result.message)

	config = await runtime.config_snapshot()
	return ActionResult(
		success=True,
		message=result.message or "Configuration updated in memory",
		details={
			"pending_action": result.action,
			"save_required": result.action != "no-op",
			"changed_fields": result.changed_fields,
			"config": config,
		},
	)


@router.post("/save", response_model=ActionResult)
async def save_config(runtime: SimulationRuntime = Depends(get_runtime)) -> ActionResult:
	result = await runtime.save_config()
	if not result.saved:
		return ActionResult(success=False, message=result.action_taken or "Failed to save")

	config = await runtime.config_snapshot()
	return ActionResult(
		success=True,
		message="Configuration saved",
		details={
			"action_taken": result.action_taken,
			"changed_fields": result.changed_fields,
			"config": config,
		},
	)
