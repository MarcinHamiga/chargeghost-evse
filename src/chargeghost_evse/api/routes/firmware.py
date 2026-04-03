from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from chargeghost_evse.api.dependencies import get_runtime
from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.schemas import (
	ActionResult,
	DiagnosticsStatusInfo,
	DiagnosticsTriggerRequest,
	FirmwareStatusInfo,
	FirmwareTriggerRequest,
)
from chargeghost_evse.api.serializers import (
	serialize_diagnostics_status,
	serialize_firmware_status,
)

router = APIRouter(tags=["firmware"])


def _require_adapter(runtime: SimulationRuntime) -> None:
	if (
		runtime.bridge is None
		or runtime.bridge.runner is None
		or runtime.bridge.runner.adapter is None
	):
		raise HTTPException(status_code=503, detail="OCPP adapter not available")


@router.get("/api/v1/firmware/status", response_model=FirmwareStatusInfo)
async def get_firmware_status(
	runtime: SimulationRuntime = Depends(get_runtime),
) -> FirmwareStatusInfo:
	_require_adapter(runtime)
	data = await runtime.call(
		lambda: serialize_firmware_status(runtime.bridge.runner.adapter.firmware_manager)
	)
	return FirmwareStatusInfo.model_validate(data)


@router.post("/api/v1/firmware/trigger", response_model=ActionResult)
async def trigger_firmware_update(
	request: FirmwareTriggerRequest,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	_require_adapter(runtime)
	await runtime.call(
		lambda: runtime.bridge.runner.adapter.firmware_manager.start_firmware_update(
			request.location, request.retrieve_date or ""
		)
	)
	return ActionResult(success=True, message="Firmware update triggered")


@router.post("/api/v1/firmware/cancel", response_model=ActionResult)
async def cancel_firmware_update(
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	_require_adapter(runtime)
	await runtime.call(
		lambda: runtime.bridge.runner.adapter.firmware_manager.cancel_firmware_update()
	)
	return ActionResult(success=True, message="Firmware update cancelled")


@router.get("/api/v1/diagnostics/status", response_model=DiagnosticsStatusInfo)
async def get_diagnostics_status(
	runtime: SimulationRuntime = Depends(get_runtime),
) -> DiagnosticsStatusInfo:
	_require_adapter(runtime)
	data = await runtime.call(
		lambda: serialize_diagnostics_status(runtime.bridge.runner.adapter.firmware_manager)
	)
	return DiagnosticsStatusInfo.model_validate(data)


@router.post("/api/v1/diagnostics/trigger", response_model=ActionResult)
async def trigger_diagnostics_upload(
	request: DiagnosticsTriggerRequest,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	_require_adapter(runtime)
	await runtime.call(
		lambda: runtime.bridge.runner.adapter.firmware_manager.start_diagnostics_upload(
			request.location, request.retries, request.retry_interval
		)
	)
	return ActionResult(success=True, message="Diagnostics upload triggered")


@router.post("/api/v1/diagnostics/cancel", response_model=ActionResult)
async def cancel_diagnostics_upload(
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	_require_adapter(runtime)
	await runtime.call(
		lambda: runtime.bridge.runner.adapter.firmware_manager.cancel_diagnostics_upload()
	)
	return ActionResult(success=True, message="Diagnostics upload cancelled")
