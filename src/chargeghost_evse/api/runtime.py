from __future__ import annotations

import asyncio
import logging
import platform
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.metadata import version as get_package_version
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from chargeghost_evse.api.serializers import (
    serialize_config,
    serialize_full_state,
    serialize_system_status,
)
from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.devtools.fault_manager import FaultManager
from chargeghost_evse.devtools.scenario_models import ScenarioDefinition
from chargeghost_evse.devtools.scenario_runner import ScenarioRunner
from chargeghost_evse.devtools.simulator_controller import SimulatorController
from chargeghost_evse.devtools.timeline_store import TimelineStore
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.ocpp_adapter.charging_profile_manager import (
    ChargingProfileManager,
)
from chargeghost_evse.util.config import (
    BATTERY_CAPACITY_MAX,
    BATTERY_CAPACITY_MIN,
    SimulationConfig,
)
from chargeghost_evse.util.update_manager import ReleaseInfo, UpdateManager

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
        self._scenario_runner: Optional[ScenarioRunner] = None
        self._loaded_scenario: Optional[ScenarioDefinition] = None
        self._update_manager: Optional[UpdateManager] = None
        self._latest_release: Optional[ReleaseInfo] = None
        self._download_progress: int = 0
        self._download_status: str = "idle"
        self._timeline_store: Optional[TimelineStore] = None
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
        self._timeline_store = TimelineStore()
        if self._bridge is not None:
            self._bridge.timeline_store = self._timeline_store
        self._controller = SimulatorController(
            engine=self._engine,
            bridge=self._bridge,
            fault_manager=self._fault_manager,
        )
        self._scenario_runner = ScenarioRunner(controller=self._controller)
        try:
            current_ver = get_package_version("chargeghost-evse")
        except Exception:
            current_ver = "0.0.0"
        self._update_manager = UpdateManager(
            current_version=current_ver, config=self._config
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

    @property
    def scenario_runner(self) -> Optional[ScenarioRunner]:
        return self._scenario_runner

    @property
    def update_manager(self) -> Optional[UpdateManager]:
        return self._update_manager

    @property
    def timeline_store(self) -> Optional[TimelineStore]:
        return self._timeline_store

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
            while (
                accumulator >= SIMULATION_STEP_SECONDS and steps < MAX_STEPS_PER_CYCLE
            ):
                if self._stop_event.is_set():
                    break
                self._process_command_queue()
                if self._engine is not None:
                    self._engine.simulate(SIMULATION_STEP_SECONDS)
                if self._scenario_runner is not None:
                    self._scenario_runner.tick(SIMULATION_STEP_SECONDS)
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

    async def send_ocpp_raw(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        if self._bridge is None or self._bridge.runner is None or self._bridge.runner.adapter is None:
            return None
        adapter = self._bridge.runner.adapter
        loop = self._bridge.runner.loop
        if loop is None:
            return None
        coro = getattr(adapter, method_name)(*args, **kwargs)
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)

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
            message = (
                "Configuration updated in memory. Save required to rebuild runtime."
            )
        elif bridge_changed:
            action = "bridge_restart_required"
            message = (
                "Configuration updated in memory. Save required to restart bridge."
            )

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

    def _set_ocpp_config_key_sync(self, key: str, value: str) -> str:
        if self._bridge is None or self._bridge.runner is None:
            return "not_supported"
        adapter = self._bridge.runner.adapter
        if adapter is None:
            return "not_supported"
        config_mgr = getattr(adapter, "config_manager", None)
        if config_mgr is None:
            return "not_supported"
        from ocpp.v16.enums import ConfigurationStatus

        result = config_mgr.set_key(key, value)
        return result.value if result else ConfigurationStatus.not_supported.value

    def get_charging_profiles_sync(self) -> list[dict[str, Any]]:
        if self._bridge is None or self._bridge.runner is None:
            return []
        adapter = self._bridge.runner.adapter
        if adapter is None:
            return []
        profile_mgr = getattr(adapter, "charging_profile_manager", None)
        if profile_mgr is None:
            return []
        profiles = profile_mgr.get_all_profiles()
        result: list[dict[str, Any]] = []
        for connector_id, profile in profiles:
            result.append(
                {
                    "charging_profile_id": profile.charging_profile_id,
                    "stack_level": profile.stack_level,
                    "charging_profile_purpose": profile.charging_profile_purpose.value,
                    "charging_profile_kind": profile.charging_profile_kind.value,
                    "charging_schedule": profile.charging_schedule.to_dict(),
                    "transaction_id": profile.transaction_id,
                    "recurrency_kind": profile.recurrency_kind.value
                    if profile.recurrency_kind
                    else None,
                    "valid_from": profile.valid_from.isoformat()
                    if profile.valid_from
                    else None,
                    "valid_to": profile.valid_to.isoformat()
                    if profile.valid_to
                    else None,
                    "connector_id": connector_id,
                }
            )
        return result

    def get_charging_profile_sync(self, profile_id: int) -> Optional[dict[str, Any]]:
        if self._bridge is None or self._bridge.runner is None:
            return None
        adapter = self._bridge.runner.adapter
        if adapter is None:
            return None
        profile_mgr = getattr(adapter, "charging_profile_manager", None)
        if profile_mgr is None:
            return None
        profiles = profile_mgr.get_all_profiles()
        for connector_id, profile in profiles:
            if profile.charging_profile_id == profile_id:
                return {
                    "charging_profile_id": profile.charging_profile_id,
                    "stack_level": profile.stack_level,
                    "charging_profile_purpose": profile.charging_profile_purpose.value,
                    "charging_profile_kind": profile.charging_profile_kind.value,
                    "charging_schedule": profile.charging_schedule.to_dict(),
                    "transaction_id": profile.transaction_id,
                    "recurrency_kind": profile.recurrency_kind.value
                    if profile.recurrency_kind
                    else None,
                    "valid_from": profile.valid_from.isoformat()
                    if profile.valid_from
                    else None,
                    "valid_to": profile.valid_to.isoformat()
                    if profile.valid_to
                    else None,
                    "connector_id": connector_id,
                }
        return None

    def clear_charging_profiles_sync(
        self,
        profile_id: Optional[int] = None,
        connector_id: Optional[int] = None,
        purpose: Optional[str] = None,
        stack_level: Optional[int] = None,
    ) -> int:
        if self._bridge is None or self._bridge.runner is None:
            return 0
        adapter = self._bridge.runner.adapter
        if adapter is None:
            return 0
        profile_mgr = getattr(adapter, "charging_profile_manager", None)
        if profile_mgr is None:
            return 0
        from ocpp.v16.enums import ChargingProfilePurposeType

        purpose_enum = None
        if purpose:
            try:
                purpose_enum = ChargingProfilePurposeType(purpose)
            except ValueError:
                pass
        return profile_mgr.clear_profiles(
            profile_id=profile_id,
            connector_id=connector_id,
            purpose=purpose_enum,
            stack_level=stack_level,
        )

    def set_charging_profile_sync(
        self, connector_id: int, profile_dict: dict[str, Any]
    ) -> tuple[bool, str]:
        if self._bridge is None or self._bridge.runner is None:
            return False, "Bridge not available"
        adapter = self._bridge.runner.adapter
        if adapter is None:
            return False, "Adapter not available"
        profile_mgr = getattr(adapter, "charging_profile_manager", None)
        if profile_mgr is None:
            return False, "Charging profile manager not available"
        try:
            profile_data = ChargingProfileManager.from_ocpp_dict(profile_dict)
        except Exception as exc:
            return False, f"Invalid profile: {exc}"
        error = profile_mgr.set_profile(connector_id, profile_data)
        if error:
            return False, error
        return True, "Profile installed"

    def get_composite_schedule_sync(
        self, connector_id: int, duration: int
    ) -> dict[str, Any]:
        if self._bridge is None or self._bridge.runner is None:
            return {}
        adapter = self._bridge.runner.adapter
        if adapter is None:
            return {}
        profile_mgr = getattr(adapter, "charging_profile_manager", None)
        if profile_mgr is None:
            return {}
        now = datetime.now(timezone.utc)
        conn = self._engine.get_connector(connector_id) if self._engine else None
        voltage = conn.voltage if conn else 230.0
        phases = conn.phase if conn else 1
        transaction_id = None
        session = self._engine.get_session(connector_id) if self._engine else None
        if session:
            transaction_id = session.transaction_id
        periods = profile_mgr.get_composite_schedule(
            connector_id=connector_id,
            transaction_id=transaction_id,
            start_time=now,
            duration=duration,
            connector_voltage=voltage,
            phases=phases,
        )
        return {
            "connector_id": connector_id,
            "duration": duration,
            "start_time": now.isoformat(),
            "periods": [
                {
                    "start_period": p.start_period,
                    "limit": p.limit,
                    "number_phases": p.number_phases,
                }
                for p in periods
            ],
        }

    async def check_for_updates(self) -> dict[str, Any]:
        if self._update_manager is None:
            return {
                "update_available": False,
                "current_version": "0.0.0",
                "latest_version": None,
            }
        try:
            release = await self._update_manager.fetch_latest_release()
            self._latest_release = release
            current = self._update_manager.current_version
            update_available = UpdateManager.is_update_available(
                current, release.tag_name
            )
            return {
                "update_available": update_available,
                "current_version": current,
                "latest_version": release.tag_name,
                "release": {
                    "tag_name": release.tag_name,
                    "body": release.body,
                    "published_at": release.published_at,
                    "assets": release.assets,
                },
            }
        except Exception as exc:
            return {
                "update_available": False,
                "current_version": self._update_manager.current_version,
                "error": str(exc),
            }

    async def download_update(self, url: Optional[str] = None) -> dict[str, Any]:
        if self._update_manager is None:
            return {
                "status": "error",
                "progress": 0,
                "message": "Update manager not available",
            }
        if self._latest_release is None:
            return {"status": "error", "progress": 0, "message": "No release available"}
        asset = None
        if url:
            for a in self._latest_release.assets:
                if a.get("browser_download_url") == url or a.get("url") == url:
                    asset = a
                    break
        else:
            asset = UpdateManager.select_asset_for_platform(
                platform.system(), self._latest_release.assets
            )
        if asset is None:
            return {
                "status": "error",
                "progress": 0,
                "message": "No suitable asset found",
            }
        self._download_status = "downloading"
        self._download_progress = 0
        try:
            target = Path("/tmp/chargeghost_update.dmg")

            def on_progress(prog: int) -> None:
                self._download_progress = prog

            await self._update_manager.download_update(
                asset["browser_download_url"], target, on_progress=on_progress
            )
            self._download_status = "ready"
            return {"status": "ready", "progress": 100, "message": str(target)}
        except Exception as exc:
            self._download_status = "error"
            return {
                "status": "error",
                "progress": self._download_progress,
                "message": str(exc),
            }

    def ignore_version_sync(self, tag: str) -> None:
        if self._config and hasattr(self._config, "ignored_version"):
            self._config.ignored_version = tag
