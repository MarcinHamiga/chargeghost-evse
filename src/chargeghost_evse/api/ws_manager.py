from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Optional, cast

from fastapi import WebSocket

from chargeghost_evse.api.serializers import (
	create_ws_message,
	serialize_session,
	serialize_stopped_session,
)
from chargeghost_evse.engine.connector import ConnectorState

StateProvider = Callable[[], dict[str, Any] | Awaitable[dict[str, Any]]]


class WebSocketManager:
	def __init__(self) -> None:
		self._clients: set[WebSocket] = set()
		self._loop: Optional[asyncio.AbstractEventLoop] = None
		self._unsubscribers: list[Any] = []
		self._snapshot_provider: Optional[StateProvider] = None
		self._tick_provider: Optional[StateProvider] = None
		self._tick_interval_seconds = 1.0
		self._last_tick_broadcast_at = 0.0
		self._logger = logging.getLogger("chargeghost.api.ws_manager")
		self._engine: Optional[Any] = None

	@property
	def client_count(self) -> int:
		return len(self._clients)

	def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
		self._loop = loop

	def subscribe_to_engine(self, engine: Any) -> None:
		self._engine = engine
		self._on_connector_status_changed_ref = self._on_connector_status_changed
		self._on_session_started_ref = self._on_session_started
		self._on_session_stopped_ref = self._on_session_stopped

		self._unsubscribers = [
			engine.connector_status_changed.subscribe(self._on_connector_status_changed_ref),
			engine.session_started.subscribe(self._on_session_started_ref),
			engine.session_stopped.subscribe(self._on_session_stopped_ref),
		]

	def set_state_providers(
		self,
		snapshot_provider: StateProvider,
		tick_provider: StateProvider,
		tick_interval_seconds: float = 1.0,
	) -> None:
		self._snapshot_provider = snapshot_provider
		self._tick_provider = tick_provider
		self._tick_interval_seconds = max(tick_interval_seconds, 0.1)

	def unsubscribe_all(self) -> None:
		for unsub in self._unsubscribers:
			unsub()
		self._unsubscribers.clear()

	async def _resolve_provider(self, provider: Optional[StateProvider]) -> dict[str, Any]:
		if provider is None:
			return {}
		data = provider()
		if inspect.isawaitable(data):
			return await cast(Awaitable[dict[str, Any]], data)
		return cast(dict[str, Any], data)

	async def connect(self, websocket: WebSocket) -> None:
		await websocket.accept()
		self._clients.add(websocket)
		self._logger.info("WebSocket client connected (total: %s)", len(self._clients))
		try:
			await self.send_state_snapshot(websocket)
		except Exception as exc:
			self._logger.warning("Initial WebSocket snapshot failed: %s", exc)
			await self.disconnect(websocket)

	async def disconnect(self, websocket: WebSocket) -> None:
		self._clients.discard(websocket)
		self._logger.info("WebSocket client disconnected (total: %s)", len(self._clients))

	async def _broadcast(self, event_type: str, data: dict[str, Any]) -> None:
		message = json.dumps(create_ws_message(event_type, data))
		dead: set[WebSocket] = set()
		for ws in self._clients:
			try:
				await ws.send_text(message)
			except Exception as exc:
				self._logger.warning("WebSocket send failed: %s", exc)
				dead.add(ws)
		self._clients -= dead

	def _schedule_broadcast(self, event_type: str, data: dict[str, Any]) -> None:
		if self._loop is not None and not self._loop.is_closed():
			asyncio.run_coroutine_threadsafe(self._broadcast(event_type, data), self._loop)

	async def send_state_snapshot(self, websocket: WebSocket) -> None:
		data = await self._resolve_provider(self._snapshot_provider)
		message = json.dumps(create_ws_message("state_snapshot", data))
		await websocket.send_text(message)

	async def maybe_broadcast_tick(self) -> None:
		if not self._clients or self._tick_provider is None:
			return

		now = time.monotonic()
		if now - self._last_tick_broadcast_at < self._tick_interval_seconds:
			return

		self._last_tick_broadcast_at = now
		await self._broadcast("tick", await self._resolve_provider(self._tick_provider))

	async def run_tick_loop(self) -> None:
		while True:
			await self.maybe_broadcast_tick()
			await asyncio.sleep(0.1)

	def _on_connector_status_changed(
		self, connector_id: int, status: ConnectorState
	) -> None:
		self._schedule_broadcast(
			"connector_status_changed",
			{"connector_id": connector_id, "status": status.value},
		)

	def _on_session_started(self, connector_id: int) -> None:
		if self._engine is None:
			self._schedule_broadcast("session_started", {"connector_id": connector_id})
			return
		session = self._engine.get_session(connector_id)
		meter = self._engine.get_energy_meter(connector_id)
		data = (
			serialize_session(session, meter)
			if session is not None
			else {"connector_id": connector_id}
		)
		self._schedule_broadcast("session_started", data)

	def _on_session_stopped(self, connector_id: int) -> None:
		if self._engine is None or self._engine.last_stopped_session is None:
			self._schedule_broadcast("session_stopped", {"connector_id": connector_id})
			return
		self._schedule_broadcast(
			"session_stopped",
			serialize_stopped_session(self._engine.last_stopped_session),
		)
