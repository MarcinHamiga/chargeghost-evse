"""Tests for Bridge._inject_limit_getter and _on_adapter_registered behaviour."""
import threading

import pytest


class _MockConnector:
	voltage: float = 230.0
	phase: int = 1


class _MockEngine:
	def __init__(self):
		self.get_limit = None
		self.session = None

	def get_connector(self, connector_id: int):
		return _MockConnector()

	@property
	def connectors(self):
		return []

	def set_connector_availability(self, connector_id: int, availability_type: str) -> str:
		return "accepted"


class _MockAdapter:
	def __init__(self):
		self.get_connector_info = None
		self.charging_profile_manager = None
		self.known_connector_ids = []
		self.set_connector_availability = None


class _MockRunner:
	def __init__(self):
		self.adapter = None
		self._connected = False
		self.loop = None

	@property
	def is_connected(self) -> bool:
		return self._connected and self.adapter is not None


class _NullEvent:
	def emit(self, **kwargs) -> None:
		pass

	def subscribe(self, *args, **kwargs) -> None:
		pass


def _make_bridge(engine, runner):
	"""Create a Bridge instance without triggering its real __init__."""
	from chargeghost_evse.bridge.bridge import Bridge
	from chargeghost_evse.bridge.message_queue import InMemoryBackend, MessageQueue

	bridge = Bridge.__new__(Bridge)
	bridge.engine = engine
	bridge.runner = runner
	bridge._shutdown_event = threading.Event()
	bridge.on_log = _NullEvent()
	bridge._message_queue = MessageQueue(backend=InMemoryBackend(), max_attempts=3)
	return bridge


class TestInjectLimitGetter:
	def test_injects_on_first_connection(self):
		engine = _MockEngine()
		runner = _MockRunner()
		bridge = _make_bridge(engine, runner)

		adapter = _MockAdapter()
		runner.adapter = adapter
		runner._connected = True

		bridge._inject_limit_getter()

		assert adapter.get_connector_info is not None
		assert engine.get_limit is not None

	def test_reinjects_get_connector_info_on_reconnect(self):
		"""After a reconnect a brand-new Adapter must receive get_connector_info.

		With the event-driven approach, _on_adapter_registered is called each time
		the runner emits on_adapter_registered (i.e., after each successful
		BootNotification). Calling it directly simulates what the event does.
		"""
		engine = _MockEngine()
		runner = _MockRunner()
		bridge = _make_bridge(engine, runner)

		# First connection
		adapter1 = _MockAdapter()
		runner.adapter = adapter1
		runner._connected = True
		bridge._on_adapter_registered()

		assert adapter1.get_connector_info is not None, "adapter1 must get connector_info on first connect"

		# Simulate disconnect + reconnect with a *new* adapter instance
		runner._connected = False
		runner.adapter = None

		adapter2 = _MockAdapter()
		runner.adapter = adapter2
		runner._connected = True
		bridge._on_adapter_registered()

		assert adapter2.get_connector_info is not None, (
			"adapter2 must get connector_info re-injected after reconnect"
		)
