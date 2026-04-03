from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chargeghost_evse import __version__
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
    ws_manager.subscribe_to_timeline(runtime.timeline_store)
    ws_manager.set_state_providers(
        snapshot_provider=runtime.full_state,
        tick_provider=lambda: runtime.system_status(start_time),
    )

    if runtime.bridge is not None and runtime.bridge.runner is not None:
        ws_manager.subscribe_to_connection_status(runtime.bridge.runner)
        adapter = runtime.bridge.runner.adapter
        if adapter is not None:
            ws_manager.subscribe_to_firmware(adapter.firmware_manager)

        def _on_adapter_registered() -> None:
            runner = runtime.bridge.runner if runtime.bridge is not None else None
            if runner is not None and runner.adapter is not None:
                ws_manager.subscribe_to_firmware(runner.adapter.firmware_manager)

        runtime.bridge.runner.on_adapter_registered.subscribe(_on_adapter_registered)

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
        version=__version__,
        lifespan=lifespan,
    )

    from chargeghost_evse.api.routes import (
        about,
        charging_profiles,
        config,
        connectors,
        faults,
        firmware,
        local_auth,
        ocpp,
        reservations,
        scenarios,
        sessions,
        status,
        timeline,
        updates,
        ws,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(status.router)
    app.include_router(connectors.router)
    app.include_router(sessions.router)
    app.include_router(config.router)
    app.include_router(ocpp.router)
    app.include_router(ws.router)
    app.include_router(faults.router)
    app.include_router(scenarios.router)
    app.include_router(charging_profiles.router)
    app.include_router(reservations.router)
    app.include_router(updates.router)
    app.include_router(timeline.router)
    app.include_router(local_auth.router)
    app.include_router(firmware.router)
    app.include_router(about.router)

    return app
