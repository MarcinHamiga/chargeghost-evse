from __future__ import annotations

from fastapi import APIRouter, Depends

from chargeghost_evse.api.dependencies import ApiAppState, get_api_state, get_ws_manager
from chargeghost_evse.api.schemas import SystemStatus
from chargeghost_evse.api.ws_manager import WebSocketManager

router = APIRouter(prefix="/api/v1", tags=["status"])


@router.get("/status", response_model=SystemStatus)
async def get_status(state: ApiAppState = Depends(get_api_state)) -> SystemStatus:
	data = await state.runtime.system_status(state.start_time)
	return SystemStatus.model_validate(data)


@router.get("/status/ws-clients")
async def get_ws_client_count(
	ws_manager: WebSocketManager = Depends(get_ws_manager),
) -> dict[str, int]:
	return {"count": ws_manager.client_count}
