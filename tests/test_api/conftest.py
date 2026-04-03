from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typing import cast

from chargeghost_evse.api.dependencies import ApiAppState
from chargeghost_evse.api.runtime import ConfigApplyResult, ConfigSaveResult
from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.routes import config, connectors, ocpp, sessions, status, ws
from chargeghost_evse.api.serializers import (
	serialize_config,
	serialize_full_state,
	serialize_system_status,
)
from chargeghost_evse.api.ws_manager import WebSocketManager
from chargeghost_evse.util.config import ConnectorConfig, SimulationConfig


class MockRuntime:
	def __init__(self, controller, config, bridge):
		self.controller = controller
		self.engine = controller.engine
		self.config = config
		self.bridge = bridge
		self._pending_action = "no-op"
		self._pending_changed_fields: list[str] = []

	async def call(self, fn, *args, **kwargs):
		return fn(*args, **kwargs)

	async def full_state(self):
		return serialize_full_state(self.engine, self.bridge)

	async def system_status(self, start_time: float):
		return serialize_system_status(self.engine, self.bridge, start_time)

	async def config_snapshot(self):
		return serialize_config(self.config)

	async def has_active_session(self) -> bool:
		return self.engine.session is not None

	async def apply_config_patch(self, patch: dict):
		if patch.get("connection_url") == "":
			return ConfigApplyResult(
				success=False,
				action="rejected",
				message="connection_url cannot be empty",
			)

		if patch.get("multi_evse_mode") != self.config.multi_evse_mode and self.engine.session is not None:
			return ConfigApplyResult(
				success=False,
				action="rejected",
				message="Cannot change multi-EVSE mode while a session is active",
			)

		changed_fields = []
		for key, value in patch.items():
			if getattr(self.config, key) != value:
				setattr(self.config, key, value)
				changed_fields.append(key)

		if "ev_battery_capacity" in changed_fields:
			self.engine.set_battery_capacity(self.config.ev_battery_capacity)

		action = "no-op"
		message = "Configuration updated in memory. Save required to persist."
		if any(key in {"multi_evse_mode", "connectors", "ev_battery_capacity"} for key in changed_fields):
			action = "runtime_rebuild_required"
			message = "Configuration updated in memory. Save required to rebuild runtime."
		elif any(
			key in {
				"charge_point_model",
				"charge_point_vendor",
				"connection_url",
				"ocpp_id",
				"ocpp_password",
				"ocpp_version",
				"skip_tls_verify",
			}
			for key in changed_fields
		):
			action = "bridge_restart_required"
			message = "Configuration updated in memory. Save required to restart bridge."

		self._pending_action = action
		self._pending_changed_fields = changed_fields
		return ConfigApplyResult(
			success=True,
			action=action,
			changed_fields=changed_fields,
			message=message,
		)

	async def save_config(self):
		self.config.save()
		action_taken = "config_saved"
		if self._pending_action == "bridge_restart_required":
			action_taken = "bridge_restarted"
		elif self._pending_action == "runtime_rebuild_required":
			action_taken = "runtime_rebuilt"
		result = ConfigSaveResult(
			saved=True,
			action_taken=action_taken,
			changed_fields=list(self._pending_changed_fields),
		)
		self._pending_action = "no-op"
		self._pending_changed_fields = []
		return result


@pytest.fixture
def mock_controller():
	controller = MagicMock()
	controller.is_connected = False
	controller.engine = MagicMock()
	controller.engine.connectors = []
	controller.engine._sessions = {}
	controller.engine.session = None
	controller.engine.get_session.return_value = None
	controller.engine.get_energy_meter.return_value = MagicMock(
		get_meter_reading=MagicMock(return_value=0.0), is_charging=False
	)
	return controller


@pytest.fixture
def mock_simulation_config():
	config = SimulationConfig(
		connection_url="wss://localhost:3000/CP_1",
		ocpp_id="CP_1",
		connectors=[ConnectorConfig()],
		ev_battery_capacity=55.0,
	)
	config.save = MagicMock()
	return config


@pytest.fixture
def mock_ws_manager():
	manager = WebSocketManager()
	manager.set_loop(MagicMock())
	return manager


@pytest.fixture
def app(mock_controller, mock_ws_manager, mock_simulation_config):
	application = FastAPI()
	bridge = MagicMock()
	mock_controller.adapter = None
	bridge.runner = mock_controller
	runtime = MockRuntime(mock_controller, mock_simulation_config, bridge)

	application.state.api = ApiAppState(
		runtime=cast(SimulationRuntime, runtime),
		ws_manager=mock_ws_manager,
		start_time=0.0,
	)
	application.state.runtime = runtime
	application.state.controller = mock_controller
	application.state.ws_manager = mock_ws_manager
	application.state.engine = mock_controller.engine
	application.state.bridge = bridge
	application.state.config = mock_simulation_config
	application.state.start_time = 0.0

	application.include_router(status.router)
	application.include_router(connectors.router)
	application.include_router(sessions.router)
	application.include_router(config.router)
	application.include_router(ocpp.router)
	application.include_router(ws.router)

	mock_ws_manager.subscribe_to_engine(mock_controller.engine)
	mock_ws_manager.set_state_providers(
		snapshot_provider=runtime.full_state,
		tick_provider=lambda: runtime.system_status(application.state.start_time),
		tick_interval_seconds=0.1,
	)

	return application


@pytest.fixture
def client(app):
	return TestClient(app)
