# Architectural Improvements Design

**Date:** 2026-02-27
**Branch:** fix/architectural-review
**Approach:** Layered (Option C) — 4 ordered layers with test checkpoints between each

## Summary

Full sweep of 19 issues identified in architectural review: runtime bugs, protocol compliance gaps,
dead code, unused dependencies, thread safety concerns, and structural refactoring.

---

## Layer 0 — Dead Code & Dependency Cleanup

Pure deletion. No logic changes. Zero risk.

### Dead code

| File | What to remove |
|------|----------------|
| `engine/connector.py` | `get_status()` method; `authorize()` method; `on_parameters_change` event + its `emit()` call in `set_parameters()` |
| `engine/engine.py` | 4 unused attributes: `last_update_time`, `last_display_time`, `simulation_time_step`, `display_time_step`; duplicate `ConnectorState` import in `TYPE_CHECKING` block |
| `engine/energy_meter.py` | Remove `Subscriber` base class (never calls `subscribe_to`) |
| `ui/bridge.py` | `_on_bridge_deleted` no-op weakref finalizer |
| `ui/widgets/session_dashboard.py` | `_refresh_widget_style`; `_on_charge_clicked` (references nonexistent `self.btn_charge`) |
| `ui/widgets/log_panel.py` | `action_copy` (never connected) |
| `ui/widgets/collapsible_log.py` | `set_log_count` (never called) |
| `util/ocpp_logger.py` | **Entire file deleted** (unused in production, broken internal code) |

### Dependencies (`pyproject.toml`)

- Remove from `[project] dependencies`: `pydantic`, `pydantic-settings`, `pyyaml`
- Move `pyinstaller` from `[project] dependencies` to `[dependency-groups] dev`

---

## Layer 1 — Engine Bugs

Fix 3 crash/data-corruption bugs plus config reliability improvements.

### 1. `session.start_time` — POSIX vs monotonic timestamp

**Problem:** `session.py:75` stores `time.monotonic()` but `bridge.py:539` passes it to
`datetime.fromtimestamp()`, producing garbage timestamps. Affects `TxProfile` matching and UI display.

**Fix:** Change to `time.time()` in `session.py`. No consumer changes needed — `fromtimestamp()`
now works correctly. Update `charging_profiles_panel.py:152` which also misuses the value.

### 2. `EnergyMeter.handle_max_charge_reached` signature mismatch

**Problem:** `Session.ev_max_charge_reached` emits with `connector_id=...` but
`EnergyMeter.handle_max_charge_reached(self)` accepts no arguments → `TypeError` at runtime.
Charging never stops when EV reaches max energy.

**Fix:** Add `connector_id: int` parameter to `energy_meter.py:116`. Add log emit inside.

### 3. `connector.stop_charging()` doesn't handle SUSPENDED_EV

**Problem:** `connector.py:280` guards on `self.status == ConnectorState.CHARGING` only.
When battery is full (status is `SUSPENDED_EV`) and `stop_session` is called, the connector
stays in `SUSPENDED_EV` permanently.

**Fix:** Change guard to `if self.status in (ConnectorState.CHARGING, ConnectorState.SUSPENDED_EV):`.

### 4. `session.process_energy_delivery` multi-fire

**Problem:** `ev_max_charge_reached` re-emits on every call once max is reached.

**Fix:** Add `_max_reached: bool = False` flag on `Session`; set to `True` on first emit, skip
subsequent emits.

### 5. Session energy cap readability

**Fix:** Replace ternary at `session.py:102` with `min()`:
```python
self.energy_charged = min(self.energy_charged + amount, self.max_energy)
```

### 6. `SimulationConfig` silent error swallowing

**Problem:** `config.py:280-282` catches `JSONDecodeError`/`IOError` and silently falls back to
defaults. Corrupted config = silent data loss.

**Fix:** Add `logging.warning("Failed to load config, using defaults: %s", e)` in the `except` block.

### 7. Non-atomic config save

**Problem:** Direct write to `CONFIG_FILE` — interrupted write corrupts the file.

**Fix:** Write to `CONFIG_FILE.with_suffix('.tmp')` then `os.replace(tmp, CONFIG_FILE)`.

### 8. `num_connectors` undead field

**Problem:** Documented as deprecated but still actively maintained in `ui/app.py`.

**Fix:** Remove from `SimulationConfig` dataclass. Replace `len(config.connectors)` at all 3 call
sites in `ui/app.py` (lines 474, 501, 1362). Remove from JSON serialization.

---

## Layer 2 — Bridge/OCPP Fixes

Protocol compliance, thread safety, and simplification.

### 1. Status notifications after reconnect (protocol compliance)

**Problem:** `_initial_status_loop` fires once after first connection only. OCPP 1.6 requires
`StatusNotification` for all connectors after each `BootNotification`.

**Design:**
- Add `on_registration_accepted: Event` to `AsyncRunner` (or expose the adapter's existing event)
- Emit it after successful registration in `_run_adapter()`
- `Bridge` subscribes to it and calls `_send_initial_status_notifications()` each time
- **Remove** `_initial_status_loop` polling thread entirely

### 2. Eliminate `_inject_limit_getter_loop` polling thread

**Problem:** Same poll-thread pattern with 0.5s intervals.

**Fix:** Subscribe `Bridge._inject_limit_getter()` to the same `on_registration_accepted` event.
**Remove** `_inject_limit_getter_loop` thread entirely.

Both fixes together eliminate 2 daemon threads and ~60 lines of polling code.

### 3. Retry delay reset

**Problem:** `retry_delay` never resets after a long-lived successful connection.

**Fix:** Add `retry_delay = 1` inside the `async with` block after `self._connected = True`.

### 4. TOCTOU adapter capture consistency

**Problem:** `on_connector_status_change` and `on_engine_session_stopped` don't capture adapter
reference before use, unlike `on_engine_session_started` which does it correctly.

**Fix:** Add `adapter = self.runner.adapter; loop = self.runner.loop` capture pattern to all
`run_coroutine_threadsafe` call sites in `Bridge`.

### 5. Fire-and-forget future error handling

**Problem:** All 6 `run_coroutine_threadsafe` calls ignore the returned `Future`. Silent failures.

**Fix:** Add `.add_done_callback(lambda f: self._log(f"OCPP send failed: {f.exception()}") if f.exception() else None)`
to each call.

### 6. Move `_parse_charging_profile` to `ChargingProfileManager`

**Problem:** Profile parsing logic lives in `Adapter`, tightly coupling it to the internal data model.

**Fix:** Move to `@staticmethod ChargingProfileManager.from_ocpp_dict(cs_profile, connector_id)`.
Update the single call site in `adapter.py`.

### 7. Deduplicate local auth check

**Problem:** Near-identical local-auth-before-CSMS blocks in `send_authorize` (lines 1139-1148)
and `send_start_transaction` (lines 1191-1207).

**Fix:** Extract `_get_local_auth_result(id_tag: str) -> Optional[AuthorizationStatus]` private
method in `Adapter`. Both methods call it.

### 8. `active_transactions` divergence

**Problem:** Adapter maintains its own counter for local-auth transactions, can diverge from
engine session state.

**Fix:** After `engine.session.transaction_id` is set (CSMS response path), ensure
`adapter.active_transactions` is updated to use that value. Document that local-auth path uses
adapter counter until CSMS confirms (or assign engine's counter directly).

---

## Layer 3 — UI Fixes

Fix broken references, extract UpdateController, move domain logic.

### 1. Fix broken method references

**Problem:**
- `MainWindow.simulate_step` calls `self.simulator.dashboard.record_telemetry(self.engine)` — method does not exist
- `SessionDashboard.update_from_engine` calls `self.telemetry_chart.refresh()` — method does not exist

**Fix:**
- `record_telemetry(engine)` → call `self.telemetry_chart.add_point(power_kw)` with the current
  effective power computed from engine state
- Remove `self.telemetry_chart.refresh()` call (or replace with correct API if refresh is needed)

### 2. Extract `UpdateController`

**Problem:** `MainWindow` contains ~80 lines of update lifecycle code: asyncio loops on daemon
threads, shell script generation, file writes, handover invocation.

**Design:** New `util/update_controller.py`:
```
UpdateController
  signals: update_available(release_info), progress(int), completed(), failed(str)
  methods: start(config), trigger_download(), cancel()
  owns: UpdateManager, HandoverManager references
  runs its own daemon thread for async operations
```

`MainWindow`:
- Holds `self.update_controller = UpdateController(config, parent=self)`
- Connects signals to existing UI update slots (show chip, show dialog, shutdown)
- Calls `self.update_controller.start()` in `__init__`

### 3. Domain logic out of UI

**Problem:** `SimulatorWidget.action_plug_in` enforces "unplug others" policy; `SimulatorWidget._on_connector_remove` validates domain invariants.

**Fix:**
- `Engine.plug_in(connector_id)` unplugs others before plugging in the new one
- `Engine.remove_connector(connector_id)` raises `ValueError("Cannot remove last connector")` or
  `ValueError("Cannot remove connector with active session")` — UI catches and shows toast

### 4. `log_mode` source of truth

**Problem:** `log_mode` state split between `QtSignalBridge._log_mode` and `AppSettings`.

**Fix:** Remove `_log_mode` from `QtSignalBridge`. All 3 toggle call sites read/write
`AppSettings.log_mode` directly. `MainWindow.log_message` reads `self.app_settings.log_mode`.

### 5. Cross-sibling coupling fix

**Problem:** `SimulatorWidget` calls `self.main_window.manual.update_connector_range()` directly.

**Fix:** Add `connector_range_changed = Signal(int, int)` to `SimulatorWidget`.
`MainWindow` connects it to `ManualWidget.update_connector_range()`.

---

## Testing Strategy

After each layer, run:
```bash
poetry run pytest
poetry run ruff check src/
poetry run mypy src/
```

Layer 0 and 1: verify no regressions in existing test suite.
Layer 2: manually verify OCPP reconnect sends status notifications (or add test to `test_bridge_inject.py`).
Layer 3: `poetry run pytest tests/test_ui_widgets.py` + manual smoke test of plug-in and update flow.

---

## Files Changed (by layer)

**Layer 0:** `connector.py`, `engine.py`, `energy_meter.py`, `ui/bridge.py`, `session_dashboard.py`, `log_panel.py`, `collapsible_log.py`, ~~`util/ocpp_logger.py`~~, `pyproject.toml`

**Layer 1:** `engine/session.py`, `engine/energy_meter.py`, `engine/connector.py`, `util/config.py`, `ui/widgets/charging_profiles_panel.py`, `bridge/bridge.py`

**Layer 2:** `bridge/bridge.py`, `ocpp_adapter/adapter.py`, `ocpp_adapter/charging_profile_manager.py`

**Layer 3:** `ui/app.py`, `ui/bridge.py`, `util/update_controller.py` (new), `engine/engine.py`
