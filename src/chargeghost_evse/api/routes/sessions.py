from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends

from chargeghost_evse.api.dependencies import get_runtime
from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.schemas import (
    ActionResult,
    SessionDetailInfo,
    SessionInfo,
    StoppedSessionResponse,
)
from chargeghost_evse.api.serializers import (
    serialize_session,
    serialize_stopped_session,
)

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def _get_active_session(
    runtime: SimulationRuntime, connector_id: int
) -> Optional[dict]:
    session = runtime.engine.get_session(connector_id)
    if session is None:
        return None
    meter = runtime.engine.get_energy_meter(connector_id)
    return serialize_session(session, meter)


@router.post("/start", response_model=ActionResult)
async def start_session(
    connector_id: int = 1,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    return await runtime.call(runtime.controller.start_charging, connector_id)


@router.post("/stop", response_model=ActionResult)
async def stop_session(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    return await runtime.call(runtime.controller.stop_charging)


@router.get("", response_model=list[SessionInfo])
async def list_active_sessions(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> list[SessionInfo]:
    data = await runtime.call(
        lambda: [
            serialize_session(session, runtime.engine.get_energy_meter(connector.id))
            for connector in runtime.engine.connectors
            if (session := runtime.engine.get_session(connector.id)) is not None
        ]
    )
    return [SessionInfo.model_validate(item) for item in data]


@router.get("/last-stopped", response_model=Optional[StoppedSessionResponse])
async def get_last_stopped_session(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> Optional[StoppedSessionResponse]:
    data = await runtime.call(
        lambda: (
            serialize_stopped_session(runtime.engine.last_stopped_session)
            if runtime.engine.last_stopped_session is not None
            else None
        )
    )
    if data is None:
        return None
    return StoppedSessionResponse.model_validate(data)


@router.get("/active", response_model=Optional[SessionInfo])
async def get_active_session_legacy(
    connector_id: int = 1,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> Optional[SessionInfo]:
    data = await runtime.call(_get_active_session, runtime, connector_id)
    if data is None:
        return None
    return SessionInfo.model_validate(data)


@router.get("/info", response_model=list[SessionDetailInfo])
async def get_session_info(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> list[SessionDetailInfo]:
    def do_get() -> list[dict]:
        results: list[dict] = []
        for conn in runtime.engine.connectors:
            sess = runtime.engine.get_session(conn.id)
            if sess is None:
                continue
            meter = runtime.engine.get_energy_meter(conn.id)
            results.append(
                {
                    "transaction_id": sess.transaction_id,
                    "connector_id": sess.connector_id,
                    "energy_charged_wh": sess.energy_charged,
                    "state_of_charge": sess.state_of_charge,
                    "start_time": sess.start_time,
                    "max_energy": sess.max_energy,
                    "is_charging": meter.is_charging,
                    "id_tag": sess.id_tag,
                }
            )
        return results

    data = await runtime.call(do_get)
    return [SessionDetailInfo.model_validate(item) for item in data]


@router.get("/{connector_id}", response_model=Optional[SessionInfo])
async def get_active_session_by_connector(
    connector_id: int,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> Optional[SessionInfo]:
    data = await runtime.call(_get_active_session, runtime, connector_id)
    if data is None:
        return None
    return SessionInfo.model_validate(data)
