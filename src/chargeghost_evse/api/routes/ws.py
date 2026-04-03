from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/state")
async def websocket_endpoint(websocket: WebSocket) -> None:
    ws_manager = websocket.app.state.api.ws_manager
    await ws_manager.connect(websocket)
    try:
        while True:
            message = await websocket.receive_text()
            if message == "get_state":
                await ws_manager.send_state_snapshot(websocket)
                continue

            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                continue

            if isinstance(payload, dict) and payload.get("type") == "get_state":
                await ws_manager.send_state_snapshot(websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket)
