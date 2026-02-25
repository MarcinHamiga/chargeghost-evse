"""Tests for Bridge._inject_limit_getter_loop reconnect behaviour."""
import threading
import time

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


class _MockAdapter:
	def __init__(self):
		self.get_connector_info = None
		self.charging_profile_manager = None


class _MockRunner:
	def __init__(self):
		self.adapter = None
		self._connected = False

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

	bridge = Bridge.__new__(Bridge)
	bridge.engine = engine
	bridge.runner = runner
	bridge._shutdown_event = threading.Event()
	bridge.on_log = _NullEvent()
	return bridge


class TestInjectLimitGetterLoop:
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
		"""After a reconnect a brand-new Adapter must receive get_connector_info."""
		engine = _MockEngine()
		runner = _MockRunner()
		bridge = _make_bridge(engine, runner)

		t = threading.Thread(target=bridge._inject_limit_getter_loop, daemon=True)
		t.start()

		# First connection
		adapter1 = _MockAdapter()
		runner.adapter = adapter1
		runner._connected = True

		deadline = time.monotonic() + 2.0
		while adapter1.get_connector_info is None and time.monotonic() < deadline:
			time.sleep(0.02)
		assert adapter1.get_connector_info is not None, "adapter1 must get connector_info on first connect"

		# Simulate disconnect
		runner._connected = False
		runner.adapter = None
		time.sleep(0.1)

		# Simulate reconnect with a *new* adapter instance
		adapter2 = _MockAdapter()
		runner.adapter = adapter2
		runner._connected = True

		deadline = time.monotonic() + 2.0
		while adapter2.get_connector_info is None and time.monotonic() < deadline:
			time.sleep(0.02)
		assert adapter2.get_connector_info is not None, (
			"adapter2 must get connector_info re-injected after reconnect"
		)

		bridge._shutdown_event.set()
		t.join(timeout=2.0)
