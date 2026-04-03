from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from chargeghost_evse.api.dependencies import get_runtime
from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.schemas import (
	ActionResult,
	LocalAuthListInfo,
	LocalAuthListUpdateRequest,
)
from chargeghost_evse.api.serializers import (
	serialize_local_auth_entry,
	serialize_local_auth_list,
)
from ocpp.v16.enums import UpdateType

router = APIRouter(prefix="/api/v1/local-auth-list", tags=["local-auth-list"])


def _require_adapter(runtime: SimulationRuntime) -> None:
	if (
		runtime.bridge is None
		or runtime.bridge.runner is None
		or runtime.bridge.runner.adapter is None
	):
		raise HTTPException(status_code=503, detail="OCPP adapter not available")


@router.get("", response_model=LocalAuthListInfo)
async def get_local_auth_list(
	runtime: SimulationRuntime = Depends(get_runtime),
) -> LocalAuthListInfo:
	_require_adapter(runtime)
	data = await runtime.call(
		lambda: serialize_local_auth_list(runtime.bridge.runner.adapter.local_auth_list)
	)
	return LocalAuthListInfo.model_validate(data)


@router.get("/{id_tag}", response_model=LocalAuthListInfo)
async def get_local_auth_entry(
	id_tag: str,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> LocalAuthListInfo:
	_require_adapter(runtime)
	data = await runtime.call(
		lambda: serialize_local_auth_entry(
			runtime.bridge.runner.adapter.local_auth_list, id_tag
		)
	)
	if data is None:
		raise HTTPException(status_code=404, detail=f"Entry '{id_tag}' not found")
	return LocalAuthListInfo.model_validate(data)


@router.put("", response_model=ActionResult)
async def update_local_auth_list(
	request: LocalAuthListUpdateRequest,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	_require_adapter(runtime)

	def do_update() -> ActionResult:
		adapter = runtime.bridge.runner.adapter
		update_type = UpdateType(request.update_type)
		status, message = adapter.local_auth_list.update_list(
			request.list_version, request.entries, update_type
		)
		return ActionResult(
			success=(status.value == "Accepted"),
			message=message,
			details={"status": status.value},
		)

	return await runtime.call(do_update)


@router.delete("/{id_tag}", response_model=ActionResult)
async def remove_local_auth_entry(
	id_tag: str,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	_require_adapter(runtime)

	def do_remove() -> ActionResult:
		success, message = runtime.bridge.runner.adapter.local_auth_list.remove_entry(id_tag)
		return ActionResult(success=success, message=message)

	return await runtime.call(do_remove)


@router.delete("", response_model=ActionResult)
async def clear_local_auth_list(
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	_require_adapter(runtime)

	def do_clear() -> ActionResult:
		success, message = runtime.bridge.runner.adapter.local_auth_list.clear()
		return ActionResult(success=success, message=message)

	return await runtime.call(do_clear)
