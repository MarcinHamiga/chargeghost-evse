from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from chargeghost_evse.api.serializers import (
	serialize_config,
	serialize_full_state,
	serialize_system_status,
)
from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.devtools.fault_manager import FaultManager
from chargeghost_evse.devtools.simulator_controller import SimulatorController
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.util.config import (
	BATTERY_CAPACITY_MAX,
	BATTERY_CAPACITY_MIN,
	SimulationConfig,
)

logger = logging.getLogger("chargeghost.api.runtime")

SIMULATION_TICK_INTERVAL = 0.05
MAX_STEPS_PER_CYCLE = 5
SIMULATION_STEP_SECONDS = 0.1

BRIDGE_FIELDS = frozenset(
	{
		"connection_url",
		"ocpp_id",
		"ocpp_password",
		"skip_tls_verify",
		"charge_point_model",
		"charge_point_vendor",
		"ocpp_version",
	}
)

TOPOLOGY_FIELDS = frozenset(
	{
		"multi_evse_mode",
		"connectors",
		"ev_battery_capacity",
	}
)

ConfigAction = Literal["no-op", "bridge_restart_required", "runtime_rebuild_required"]


@dataclass
class ConfigApplyResult:
	success: bool
	action: Literal[
		"no-op", "bridge_restart_required", "runtime_rebuild_required", "rejected"
	]
	changed_fields: list[str] = field(default_factory=list)
	message: str = ""


@dataclass
class ConfigSaveResult:
	saved: bool
	action_taken: Optional[str] = None
	changed_fields: list[str] = field(default_factory=list)


class SimulationRuntime:
	def __init__(
		self,
		config: SimulationConfig,
		fault_manager: Optional[FaultManager] = None,
	) -> None:
		self._config = config
		self._fault_manager = fault_manager or FaultManager()
		self._engine: Optional[Engine] = None
		self._bridge: Optional[Bridge] = None
		self._controller: Optional[SimulatorController] = None
		self._command_queue: queue.Queue[
			tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any], Future[Any]]
		] = queue.Queue()
		self._thread: Optional[threading.Thread] = None
		self._running = False
		self._stop_event = threading.Event()
		self._lock = threading.Lock()
		self._pending_config_action: ConfigAction = "no-op"
		self._pending_changed_fields: list[str] = []
		self._build_runtime_objects()

	def _build_runtime_objects(self) -> None:
		self._engine = Engine(multi_evse_mode=self._config.multi_evse_mode)
		self._engine.set_battery_capacity(self._config.ev_battery_capacity)
		self._engine.set_fault_manager(self._fault_manager)
		for connector_config in self._config.connectors:
			self._engine.add_connector(
				voltage=connector_config.voltage,
				current=connector_config.current,
				phase=connector_config.phase,
			)
		self._bridge = self._create_bridge()
		self._controller = SimulatorController(
			engine=self._engine,
			bridge=self._bridge,
			fault_manager=self._fault_manager,
		)

	def _create_bridge(self) -> Optional[Bridge]:
		if not self._config.connection_url or self._engine is None:
			return None
		bridge = Bridge(
			engine=self._engine,
			url=self._config.connection_url,
			charge_point_id=self._config.ocpp_id,
			password=self._config.ocpp_password,
			skip_tls_verify=self._config.skip_tls_verify,
			charge_point_model=self._config.charge_point_model,
			charge_point_vendor=self._config.charge_point_vendor,
			persist_message_queue=self._config.persist_message_queue,
			get_rfid=lambda: self._config.rfid_tag,
			ocpp_version=self._config.ocpp_version,
			fault_manager=self._fault_manager,
		)
		bridge.setup()
		return bridge

	@property
	def engine(self) -> Engine:
		assert self._engine is not None
		return self._engine

	@property
	def controller(self) -> SimulatorController:
		assert self._controller is not None
		return self._controller

	@property
	def bridge(self) -> Optional[Bridge]:
		return self._bridge

	@property
	def config(self) -> SimulationConfig:
		return self._config

	@property
	def is_running(self) -> bool:
		return self._running

	def start(self) -> None:
		with self._lock:
			if self._running:
				return
			self._running = True
			self._stop_event.clear()
			self._thread = threading.Thread(
				target=self._run_loop, daemon=True, name="sim-runtime"
			)
			self._thread.start()
			logger.info("SimulationRuntime started")

	def stop(self) -> None:
		with self._lock:
			if not self._running:
				return
			self._running = False
			self._stop_event.set()
		if self._thread is not None and self._thread.is_alive():
			self._thread.join(timeout=5)
		self._thread = None
		if self._bridge is not None:
			self._bridge.shutdown()
		logger.info("SimulationRuntime stopped")

	def _run_loop(self) -> None:
		accumulator: float = 0.0
		last_tick: float = time.monotonic()
		while not self._stop_event.is_set():
			now = time.monotonic()
			delta = now - last_tick
			last_tick = now
			accumulator += delta
			steps = 0
			while accumulator >= SIMULATION_STEP_SECONDS and steps < MAX_STEPS_PER_CYCLE:
				if self._stop_event.is_set():
					break
				self._process_command_queue()
				if self._engine is not None:
					self._engine.simulate(SIMULATION_STEP_SECONDS)
				accumulator -= SIMULATION_STEP_SECONDS
				steps += 1
			self._stop_event.wait(timeout=SIMULATION_TICK_INTERVAL)

	def _process_command_queue(self) -> None:
		try:
			while True:
				fn, args, kwargs, future = self._command_queue.get_nowait()
				try:
					result = fn(*args, **kwargs)
					future.set_result(result)
				except Exception as exc:
					future.set_exception(exc)
		except queue.Empty:
			pass

	async def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
		loop = asyncio.get_running_loop()
		future: Future[Any] = Future()
		self._command_queue.put((fn, args, kwargs, future))
		result: Any = await loop.run_in_executor(None, future.result)
		return result

	async def snapshot(self) -> dict[str, Any]:
		return await self.call(self._take_snapshot)

	async def full_state(self) -> dict[str, Any]:
		return await self.call(self._serialize_full_state_sync)

	async def system_status(self, start_time: float) -> dict[str, Any]:
		return await self.call(self._serialize_system_status_sync, start_time)

	async def config_snapshot(self) -> dict[str, Any]:
		return await self.call(self._serialize_config_sync)

	async def has_active_session(self) -> bool:
		return await self.call(self._has_active_session_sync)

	def _take_snapshot(self) -> dict[str, Any]:
		eng = self._engine
		if eng is None:
			return {"connectors": [], "sessions": {}, "energy_meters": {}}
		connectors = []
		for conn in eng.connectors:
			connectors.append(
				{
					"id": conn.id,
					"status": conn.status.value,
					"voltage": conn.voltage,
					"current": conn.current,
					"phase": conn.phase,
					"is_plugged_in": conn.is_plugged_in,
					"id_tag": conn.id_tag,
				}
			)
		sessions = {}
		for conn in eng.connectors:
			session = eng.get_session(conn.id)
			if session is None:
				continue
			meter = eng.get_energy_meter(conn.id)
			sessions[str(conn.id)] = {
				"transaction_id": session.transaction_id,
				"connector_id": session.connector_id,
				"energy_charged_wh": session.energy_charged,
				"state_of_charge": session.state_of_charge,
				"start_time": session.start_time,
				"id_tag": session.id_tag,
				"is_charging": meter.is_charging,
			}
		energy_meters = {}
		for conn in eng.connectors:
			meter = eng.get_energy_meter(conn.id)
			energy_meters[str(conn.id)] = {
				"reading_wh": meter.get_meter_reading(),
				"is_charging": meter.is_charging,
			}
		return {
			"connectors": connectors,
			"sessions": sessions,
			"energy_meters": energy_meters,
		}

	def _serialize_full_state_sync(self) -> dict[str, Any]:
		return serialize_full_state(self.engine, self.bridge)

	def _serialize_system_status_sync(self, start_time: float) -> dict[str, Any]:
		return serialize_system_status(self.engine, self.bridge, start_time)

	def _serialize_config_sync(self) -> dict[str, Any]:
		return serialize_config(self._config)

	def _has_active_session_sync(self) -> bool:
		return self._engine is not None and self._engine.session is not None

	def _merge_config_action(self, action: ConfigAction) -> None:
		priority = {
			"no-op": 0,
			"bridge_restart_required": 1,
			"runtime_rebuild_required": 2,
		}
		if priority[action] > priority[self._pending_config_action]:
			self._pending_config_action = action

	def _remember_changed_fields(self, changed_fields: list[str]) -> None:
		for field_name in changed_fields:
			if field_name not in self._pending_changed_fields:
				self._pending_changed_fields.append(field_name)

	async def apply_config_patch(self, patch: dict[str, Any]) -> ConfigApplyResult:
		return await self.call(self._apply_config_patch_sync, patch)

	def _apply_config_patch_sync(self, patch: dict[str, Any]) -> ConfigApplyResult:
		if "connection_url" in patch and patch["connection_url"] == "":
			return ConfigApplyResult(
				success=False,
				action="rejected",
				message="connection_url cannot be empty",
			)

		if "ev_battery_capacity" in patch and patch["ev_battery_capacity"] is not None:
			capacity = patch["ev_battery_capacity"]
			if not BATTERY_CAPACITY_MIN <= capacity <= BATTERY_CAPACITY_MAX:
				return ConfigApplyResult(
					success=False,
					action="rejected",
					message=(
						f"ev_battery_capacity must be between {BATTERY_CAPACITY_MIN} "
						f"and {BATTERY_CAPACITY_MAX}"
					),
				)

		changed_fields: list[str] = []
		for key, value in patch.items():
			if value is None:
				continue
			current = getattr(self._config, key, None)
			if current != value:
				changed_fields.append(key)

		if not changed_fields:
			return ConfigApplyResult(success=True, action="no-op")

		changed_set = set(changed_fields)
		bridge_changed = bool(changed_set & BRIDGE_FIELDS)
		topology_changed = bool(changed_set & TOPOLOGY_FIELDS)

		if topology_changed and self._has_active_session_sync():
			return ConfigApplyResult(
				success=False,
				action="rejected",
				message="Cannot change multi-EVSE mode while a session is active",
			)

		for key, value in patch.items():
			if value is None or key not in changed_fields:
				continue
			setattr(self._config, key, value)

		if "ev_battery_capacity" in changed_fields and self._engine is not None:
			self._engine.set_battery_capacity(self._config.ev_battery_capacity)

		action: ConfigAction = "no-op"
		message = "Configuration updated in memory. Save required to persist."
		if topology_changed:
			action = "runtime_rebuild_required"
			message = "Configuration updated in memory. Save required to rebuild runtime."
		elif bridge_changed:
			action = "bridge_restart_required"
			message = "Configuration updated in memory. Save required to restart bridge."

		self._merge_config_action(action)
		self._remember_changed_fields(changed_fields)

		return ConfigApplyResult(
			success=True,
			action=action,
			changed_fields=changed_fields,
			message=message,
		)

	async def save_config(self) -> ConfigSaveResult:
		return await self.call(self._save_config_sync)

	def _save_config_sync(self) -> ConfigSaveResult:
		try:
			self._config.save()
			action_taken = "config_saved"
			if self._pending_config_action == "runtime_rebuild_required":
				self.rebuild_runtime()
				action_taken = "runtime_rebuilt"
			elif self._pending_config_action == "bridge_restart_required":
				self.restart_bridge()
				action_taken = "bridge_restarted"

			changed_fields = list(self._pending_changed_fields)
			self._pending_config_action = "no-op"
			self._pending_changed_fields = []
			return ConfigSaveResult(
				saved=True,
				action_taken=action_taken,
				changed_fields=changed_fields,
			)
		except Exception as exc:
			logger.error("Failed to save config: %s", exc)
			return ConfigSaveResult(saved=False, action_taken=str(exc))

	def restart_bridge(self) -> None:
		if self._bridge is not None:
			self._bridge.shutdown()
		self._bridge = self._create_bridge()
		if self._controller is not None:
			self._controller.bridge = self._bridge
		logger.info("Bridge restarted")

	def rebuild_runtime(self) -> None:
		if self._bridge is not None:
			self._bridge.shutdown()
		self._build_runtime_objects()
		logger.info("Runtime rebuilt from config")

	def get_ocpp_config_keys(self) -> list[dict[str, Any]]:
		return self._get_ocpp_config_keys_sync()

	def _get_ocpp_config_keys_sync(self) -> list[dict[str, Any]]:
		if self._bridge is None or self._bridge.runner is None:
			return []
		adapter = self._bridge.runner.adapter
		if adapter is None:
			return []
		config_mgr = getattr(adapter, "config_manager", None)
		if config_mgr is None:
			return []
		keys = config_mgr.get_all_keys()
		result: list[dict[str, Any]] = []
		for key_info in keys:
			result.append(
				{
					"key": getattr(key_info, "key", str(key_info)),
					"value": getattr(key_info, "value", ""),
					"readonly": getattr(key_info, "readonly", False),
				}
			)
		return result
