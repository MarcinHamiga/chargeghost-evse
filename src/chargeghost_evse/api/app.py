from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from chargeghost_evse.api.dependencies import ApiAppState
from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.ws_manager import WebSocketManager
from chargeghost_evse.devtools.fault_manager import FaultManager
from chargeghost_evse.util.config import SimulationConfig

logger = logging.getLogger("chargeghost.api.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
	config = SimulationConfig.load()
	fault_manager = FaultManager()

	runtime = SimulationRuntime(config=config, fault_manager=fault_manager)
	runtime.start()

	ws_manager = WebSocketManager()
	ws_manager.set_loop(asyncio.get_running_loop())
	ws_manager.subscribe_to_engine(runtime.engine)
	ws_manager.set_state_providers(
		snapshot_provider=runtime.full_state,
		tick_provider=lambda: runtime.system_status(start_time),
	)

	start_time = time.monotonic()
	app.state.api = ApiAppState(
		runtime=runtime,
		ws_manager=ws_manager,
		start_time=start_time,
	)
	app.state.runtime = runtime
	app.state.ws_manager = ws_manager
	tick_task = asyncio.create_task(ws_manager.run_tick_loop())

	logger.info("ChargeGhost API server started")

	try:
		yield
	finally:
		tick_task.cancel()
		try:
			await tick_task
		except asyncio.CancelledError:
			pass
		ws_manager.unsubscribe_all()
		runtime.stop()
		logger.info("ChargeGhost API server stopped")


def create_app() -> FastAPI:
	app = FastAPI(
		title="ChargeGhost EVSE API",
		description="REST + WebSocket API for controlling the ChargeGhost EVSE simulator",
		version="0.4.3",
		lifespan=lifespan,
	)

	from chargeghost_evse.api.routes import (
		config,
		connectors,
		ocpp,
		sessions,
		status,
		ws,
	)

	app.include_router(status.router)
	app.include_router(connectors.router)
	app.include_router(sessions.router)
	app.include_router(config.router)
	app.include_router(ocpp.router)
	app.include_router(ws.router)

	return app
