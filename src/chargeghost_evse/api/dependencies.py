from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request

from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.ws_manager import WebSocketManager


@dataclass
class ApiAppState:
	runtime: SimulationRuntime
	ws_manager: WebSocketManager
	start_time: float


def get_api_state(request: Request) -> ApiAppState:
	return request.app.state.api


def get_runtime(state: ApiAppState = Depends(get_api_state)) -> SimulationRuntime:
	return state.runtime


def get_ws_manager(state: ApiAppState = Depends(get_api_state)) -> WebSocketManager:
	return state.ws_manager
