from unittest.mock import AsyncMock, MagicMock

from chargeghost_evse.api.ws_manager import WebSocketManager
from chargeghost_evse.engine.connector import ConnectorState


class TestWebSocketManager:
	def test_initial_state(self):
		manager = WebSocketManager()
		assert manager.client_count == 0

	def test_subscribe_and_unsubscribe(self):
		manager = WebSocketManager()
		engine = MagicMock()
		manager.subscribe_to_engine(engine)
		assert len(manager._unsubscribers) == 3
		manager.unsubscribe_all()
		assert len(manager._unsubscribers) == 0

	def test_connector_status_handler_schedules_broadcast(self):
		manager = WebSocketManager()
		loop = MagicMock()
		manager.set_loop(loop)
		manager._on_connector_status_changed(1, ConnectorState.CHARGING)
		assert loop is not None

	def test_session_started_handler(self):
		manager = WebSocketManager()
		loop = MagicMock()
		manager.set_loop(loop)
		manager._on_session_started(1)

	def test_session_stopped_handler(self):
		manager = WebSocketManager()
		loop = MagicMock()
		manager.set_loop(loop)
		manager._on_session_stopped(1)

	async def test_connect_and_disconnect(self):
		manager = WebSocketManager()
		ws = AsyncMock()
		await manager.connect(ws)
		assert manager.client_count == 1
		await manager.disconnect(ws)
		assert manager.client_count == 0

	async def test_broadcast_sends_to_all_clients(self):
		manager = WebSocketManager()
		ws1 = AsyncMock()
		ws2 = AsyncMock()
		await manager.connect(ws1)
		await manager.connect(ws2)
		await manager._broadcast("test", {"data": "value"})
		assert ws1.send_text.await_count == 2
		assert ws2.send_text.await_count == 2

	async def test_broadcast_removes_dead_clients(self):
		manager = WebSocketManager()
		ws_good = AsyncMock()
		ws_bad = AsyncMock()
		ws_bad.send_text.side_effect = Exception("disconnected")
		await manager.connect(ws_good)
		await manager.connect(ws_bad)
		await manager._broadcast("test", {})
		assert manager.client_count == 1
