from __future__ import annotations

from typing import Optional

from fastapi import Body, APIRouter, Depends, HTTPException

from chargeghost_evse.api.dependencies import get_runtime
from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.schemas import (
    ActionResult,
    ChargingProfileClearRequest,
    ChargingProfileInfo,
    ChargingProfileSetRequest,
    CompositeScheduleRequest,
    CompositeScheduleResponse,
)

router = APIRouter(prefix="/api/v1/charging-profiles", tags=["charging-profiles"])


@router.get("", response_model=list[ChargingProfileInfo])
async def list_profiles(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> list[ChargingProfileInfo]:
    if (
        runtime.bridge is None
        or runtime.bridge.runner is None
        or runtime.bridge.runner.adapter is None
    ):
        raise HTTPException(status_code=503, detail="OCPP adapter not available")

    profiles = await runtime.call(runtime.get_charging_profiles_sync)
    return [ChargingProfileInfo.model_validate(p) for p in profiles]


@router.get("/{profile_id}", response_model=ChargingProfileInfo)
async def get_profile(
    profile_id: int,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ChargingProfileInfo:
    if (
        runtime.bridge is None
        or runtime.bridge.runner is None
        or runtime.bridge.runner.adapter is None
    ):
        raise HTTPException(status_code=503, detail="OCPP adapter not available")

    profile = await runtime.call(runtime.get_charging_profile_sync, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return ChargingProfileInfo.model_validate(profile)


@router.delete("", response_model=ActionResult)
async def clear_profiles(
    runtime: SimulationRuntime = Depends(get_runtime),
    request: Optional[ChargingProfileClearRequest] = Body(None),
) -> ActionResult:
    if (
        runtime.bridge is None
        or runtime.bridge.runner is None
        or runtime.bridge.runner.adapter is None
    ):
        raise HTTPException(status_code=503, detail="OCPP adapter not available")

    profile_id = request.profile_id if request else None
    connector_id = request.connector_id if request else None
    purpose = request.purpose if request else None
    stack_level = request.stack_level if request else None

    def do_clear() -> ActionResult:
        removed = runtime.clear_charging_profiles_sync(
            profile_id=profile_id,
            connector_id=connector_id,
            purpose=purpose,
            stack_level=stack_level,
        )
        return ActionResult(success=True, message=f"Cleared {removed} profile(s)")

    return await runtime.call(do_clear)


@router.post("", response_model=ActionResult)
async def set_profile(
    request: ChargingProfileSetRequest,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    if (
        runtime.bridge is None
        or runtime.bridge.runner is None
        or runtime.bridge.runner.adapter is None
    ):
        raise HTTPException(status_code=503, detail="OCPP adapter not available")

    def do_set() -> ActionResult:
        success, msg = runtime.set_charging_profile_sync(
            request.connector_id, request.profile
        )
        return ActionResult(success=success, message=msg)

    return await runtime.call(do_set)


@router.post("/composite-schedule", response_model=CompositeScheduleResponse)
async def get_composite_schedule(
    request: CompositeScheduleRequest,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> CompositeScheduleResponse:
    if (
        runtime.bridge is None
        or runtime.bridge.runner is None
        or runtime.bridge.runner.adapter is None
    ):
        raise HTTPException(status_code=503, detail="OCPP adapter not available")

    schedule = await runtime.call(
        runtime.get_composite_schedule_sync, request.connector_id, request.duration
    )
    if not schedule:
        raise HTTPException(
            status_code=503, detail="Failed to compute composite schedule"
        )

    return CompositeScheduleResponse.model_validate(schedule)
