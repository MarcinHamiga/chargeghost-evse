from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends

from chargeghost_evse.api.dependencies import get_runtime
from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.schemas import (
    ActionResult,
    FaultDefinitionInfo,
    FaultEnableRequest,
    FaultStateInfo,
)
from chargeghost_evse.devtools.fault_catalog import FAULT_CATALOG

router = APIRouter(prefix="/api/v1/faults", tags=["faults"])


@router.get("", response_model=list[FaultDefinitionInfo])
async def list_fault_definitions() -> list[FaultDefinitionInfo]:
    return [
        FaultDefinitionInfo(
            fault_id=fid,
            label=defn.label,
            scope=defn.scope.value,
            lifetime=defn.lifetime.value,
            default_config=defn.default_config,
        )
        for fid, defn in FAULT_CATALOG.items()
    ]


@router.get("/active", response_model=list[FaultStateInfo])
async def list_active_faults(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> list[FaultStateInfo]:
    def do_list() -> list[FaultStateInfo]:
        fm = getattr(runtime.controller, "fault_manager", None)
        if fm is None:
            return []
        active = fm.get_active_summary()
        return [
            FaultStateInfo(
                fault_id=s.fault_id,
                enabled=s.enabled,
                trigger_count=s.trigger_count,
                config={
                    "parameters": s.config.parameters,
                    "count_limit": s.config.count_limit,
                }
                if s.config
                else None,
            )
            for s in active
        ]

    return await runtime.call(do_list)


@router.get("/{fault_id}", response_model=Optional[FaultStateInfo])
async def get_fault_state(
    fault_id: str,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> Optional[FaultStateInfo]:
    def do_get() -> Optional[FaultStateInfo]:
        fm = getattr(runtime.controller, "fault_manager", None)
        if fm is None:
            return None
        state = fm.peek(fault_id)
        if state is None:
            return None
        return FaultStateInfo(
            fault_id=state.fault_id,
            enabled=state.enabled,
            trigger_count=state.trigger_count,
            config={
                "parameters": state.config.parameters,
                "count_limit": state.config.count_limit,
            }
            if state.config
            else None,
        )

    return await runtime.call(do_get)


@router.post("/{fault_id}/enable", response_model=ActionResult)
async def enable_fault(
    fault_id: str,
    request: Optional[FaultEnableRequest] = None,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    from chargeghost_evse.devtools.fault_models import FaultConfig

    config = None
    if request is not None:
        config = FaultConfig(
            fault_id=fault_id,
            parameters=request.parameters or {},
            count_limit=request.count_limit,
        )

    def do_enable() -> ActionResult:
        fm = getattr(runtime.controller, "fault_manager", None)
        if fm is None:
            return ActionResult(success=False, message="Fault manager not available")
        try:
            fm.enable(fault_id, config=config)
            return ActionResult(success=True, message=f"Fault '{fault_id}' enabled")
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))

    return await runtime.call(do_enable)


@router.post("/{fault_id}/disable", response_model=ActionResult)
async def disable_fault(
    fault_id: str,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    def do_disable() -> ActionResult:
        fm = getattr(runtime.controller, "fault_manager", None)
        if fm is None:
            return ActionResult(success=False, message="Fault manager not available")
        fm.disable(fault_id)
        return ActionResult(success=True, message=f"Fault '{fault_id}' disabled")

    return await runtime.call(do_disable)


@router.post("/clear", response_model=ActionResult)
async def clear_all_faults(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    def do_clear() -> ActionResult:
        fm = getattr(runtime.controller, "fault_manager", None)
        if fm is None:
            return ActionResult(success=False, message="Fault manager not available")
        fm.clear_all()
        return ActionResult(success=True, message="All faults cleared")

    return await runtime.call(do_clear)
