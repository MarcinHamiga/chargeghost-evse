# Fault Injection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add explicit, testable fault injection controls so backend and integration engineers can reproduce transport, timing, metering, and protocol edge cases on demand.

**Architecture:** Introduce a centralized fault manager in a devtools layer and let `AsyncRunner`, `Bridge`, adapters, and the `Engine` consult it through small hooks. Fault state stays session-local, visible in the UI, and structured enough for later scenario-runner integration.

**Tech Stack:** Python 3.11+, PySide6, asyncio, dataclasses, pytest, pytest-qt, existing `Bridge`, `AsyncRunner`, `Engine`, `BaseAdapter`, and structured logging stack

**Run tests after every commit:**
```bash
poetry run pytest -x
poetry run ruff check src/ tests/
poetry run mypy src/
```

---

## Context You Must Know

- Transport and heartbeat behavior live primarily in `src/chargeghost_evse/bridge/bridge.py` on `AsyncRunner` and `Bridge`.
- Raw OCPP send/receive hooks already exist in `src/chargeghost_evse/ocpp_adapter/base_adapter.py`.
- Meter updates and connector state changes originate in `src/chargeghost_evse/engine/engine.py`.
- The app already has structured logging with extra fields in `src/chargeghost_evse/util/log_setup.py`; reuse that instead of inventing a parallel diagnostics pipeline.
- Users need fault behavior to be obvious. Hidden fault state is worse than no fault feature at all.
- This simulator is a devtool, so intentionally weird behavior is acceptable, but it should still be bounded and labeled.

## Recommended Scope

Ship the first version with a small but high-value fault catalog:

- forced disconnect / delayed reconnect
- dropped heartbeat
- delayed outbound response
- rejected inbound action override where protocol-valid
- frozen meter
- one-shot meter jump or reset
- temporary status flap

Do **not** add arbitrary packet mangling, database-backed persistence, or impossible internal connector states in the first pass.

---

## Success Criteria

Success means:

- Faults can be enabled, disabled, and observed without restarting the app.
- A central fault manager owns activation policy, counts, and one-shot behavior.
- Transport faults can affect connection and heartbeat handling.
- Meter and status faults can affect engine-visible behavior without corrupting internal invariants.
- Active faults are visible in the UI and clearly marked in logs.
- Core fault flows are covered by focused tests and do not break the no-fault baseline.

---

## Fault Model

Use two axes:

- **Lifetime:** `persistent`, `one_shot`, `count_limited`
- **Scope:** `transport`, `protocol`, `meter`, `state`

Each fault should have:

- stable ID
- human-readable label
- scope
- configuration payload
- activation policy
- trigger count
- enabled flag

Keep catalog entries explicit rather than free-form scripts.

---

## Target File Layout

Create or refactor toward this structure:

- `src/chargeghost_evse/devtools/__init__.py`
- `src/chargeghost_evse/devtools/fault_models.py`
- `src/chargeghost_evse/devtools/fault_manager.py`
- `src/chargeghost_evse/devtools/fault_catalog.py`
- `src/chargeghost_evse/ui/widgets/fault_injection_panel.py`
- `tests/test_fault_manager.py`
- `tests/test_fault_injection_transport.py`
- `tests/test_fault_injection_protocol.py`
- `tests/test_fault_injection_engine.py`

Likely modifications:

- `src/chargeghost_evse/bridge/bridge.py`
- `src/chargeghost_evse/ocpp_adapter/base_adapter.py`
- `src/chargeghost_evse/ocpp_adapter/adapter.py`
- `src/chargeghost_evse/ocpp_adapter/v201_adapter.py`
- `src/chargeghost_evse/engine/engine.py`
- `src/chargeghost_evse/ui/app.py`
- `src/chargeghost_evse/ui/bridge.py`
- `src/chargeghost_evse/util/log_setup.py`
- `src/chargeghost_evse/ui/styles/e_mobility.qss`

---

## Task 1: Add Central Fault Models and Manager

**Files:**
- Create: `src/chargeghost_evse/devtools/fault_models.py`
- Create: `src/chargeghost_evse/devtools/fault_catalog.py`
- Create: `src/chargeghost_evse/devtools/fault_manager.py`
- Test: `tests/test_fault_manager.py`

### Step 1: Write the failing tests

Add coverage for:

- enabling and disabling a persistent fault
- consuming a one-shot fault exactly once
- count-limited faults deactivate after the configured number of triggers
- unknown fault IDs are rejected cleanly
- fault manager can return an active summary for the UI

Suggested test names:

- `test_fault_manager_enables_persistent_fault`
- `test_fault_manager_consumes_one_shot_fault_once`
- `test_fault_manager_deactivates_count_limited_fault`
- `test_fault_manager_rejects_unknown_fault_id`
- `test_fault_manager_returns_active_fault_summary`

### Step 2: Implement the fault manager

Add:

- `FaultDefinition`
- `FaultConfig`
- `FaultState`
- `FaultTriggerResult`
- `FaultManager`

Implementation notes:

- Use explicit catalog definitions instead of arbitrary dynamic faults.
- Expose small APIs such as `enable()`, `disable()`, `clear_all()`, `peek()`, and `consume_if_active()`.
- Track trigger counts so one-shot and limited faults behave deterministically.
- Emit change notifications with the existing `Event` helper so the UI can update without polling everything.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_fault_manager.py -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/devtools/fault_models.py src/chargeghost_evse/devtools/fault_catalog.py src/chargeghost_evse/devtools/fault_manager.py tests/test_fault_manager.py
git commit -m "feat: add centralized fault manager"
```

---

## Task 2: Add Transport Fault Hooks in `AsyncRunner` and `Bridge`

**Files:**
- Modify: `src/chargeghost_evse/bridge/bridge.py`
- Test: `tests/test_fault_injection_transport.py`

### Step 1: Write the failing tests

Add coverage for:

- forced disconnect fault closes or simulates loss of connection once enabled
- delayed reconnect fault increases reconnect wait without affecting the no-fault path
- dropped heartbeat fault suppresses a heartbeat send and records the trigger
- outbound meter-value send delay fault postpones the send rather than blocking the UI thread

Suggested test names:

- `test_forced_disconnect_fault_marks_runner_disconnected`
- `test_reconnect_delay_fault_extends_backoff`
- `test_drop_heartbeat_fault_skips_single_heartbeat`
- `test_meter_values_delay_fault_defers_send`

### Step 2: Integrate transport-level hooks

Add fault checks in:

- connection establishment / reconnect timing
- heartbeat loop
- fire-and-forget outbound send scheduling where delay is safe

Implementation notes:

- Keep the no-fault path straight-line and easy to read.
- Avoid `time.sleep()` on the UI thread; delays should be handled in existing async or tick-driven code.
- Log fault triggers with structured extras including fault ID and scope.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_fault_injection_transport.py -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/bridge/bridge.py tests/test_fault_injection_transport.py
git commit -m "feat: add transport fault injection hooks"
```

---

## Task 3: Add Protocol-Level Fault Hooks in the Adapters

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/base_adapter.py`
- Modify: `src/chargeghost_evse/ocpp_adapter/adapter.py`
- Modify: `src/chargeghost_evse/ocpp_adapter/v201_adapter.py`
- Test: `tests/test_fault_injection_protocol.py`

### Step 1: Write the failing tests

Add coverage for:

- next `Authorize` response can be delayed
- next `RemoteStartTransaction` or `RequestStartTransaction` request can be rejected through a protocol-valid override
- next `TriggerMessage` request can be forced to `NotImplemented`
- no-fault protocol behavior remains unchanged

Suggested test names:

- `test_authorize_delay_fault_wraps_outbound_send`
- `test_v16_remote_start_reject_fault_returns_rejected`
- `test_v201_request_start_reject_fault_returns_rejected`
- `test_trigger_message_not_implemented_fault_is_protocol_valid`

### Step 2: Implement adapter hooks

Implementation notes:

- Add a small helper in `BaseAdapter` for consulting the fault manager before outbound send or before returning from inbound handlers.
- Prefer protocol-valid overrides and explicit rejections over malformed frames in the first pass.
- Keep version-specific response overrides in the versioned adapters, not in the shared base class.
- Record which action consumed the fault so diagnostics stay readable.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_fault_injection_protocol.py -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/ocpp_adapter/base_adapter.py src/chargeghost_evse/ocpp_adapter/adapter.py src/chargeghost_evse/ocpp_adapter/v201_adapter.py tests/test_fault_injection_protocol.py
git commit -m "feat: add protocol fault injection overrides"
```

---

## Task 4: Add Meter and State Fault Hooks in the Engine

**Files:**
- Modify: `src/chargeghost_evse/engine/engine.py`
- Modify: `src/chargeghost_evse/engine/connector.py`
- Test: `tests/test_fault_injection_engine.py`

### Step 1: Write the failing tests

Add coverage for:

- frozen meter fault prevents meter growth while charging continues logically
- one-shot meter jump increases the next sample then clears itself
- meter reset fault returns next visible reading to zero without breaking session state
- status flap fault emits a temporary status transition sequence without leaving the connector stuck in an invalid state

Suggested test names:

- `test_frozen_meter_fault_prevents_meter_growth`
- `test_meter_jump_fault_applies_once`
- `test_meter_reset_fault_zeroes_next_visible_reading`
- `test_status_flap_fault_restores_original_state`

### Step 2: Implement engine-side hooks

Implementation notes:

- Prefer meter-output overrides and transient event overlays to illegal connector mutations.
- Do not corrupt the real energy meter or connector state beyond what the fault explicitly models.
- If a status flap is simulated, emit matching logs and state-change notifications so UI and diagnostics stay consistent.
- Keep single-session and multi-EVSE behavior aligned.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_fault_injection_engine.py -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/engine/engine.py src/chargeghost_evse/engine/connector.py tests/test_fault_injection_engine.py
git commit -m "feat: add engine fault injection behaviors"
```

---

## Task 5: Surface Fault State in Logs and the Qt UI

**Files:**
- Create: `src/chargeghost_evse/ui/widgets/fault_injection_panel.py`
- Modify: `src/chargeghost_evse/ui/app.py`
- Modify: `src/chargeghost_evse/ui/bridge.py`
- Modify: `src/chargeghost_evse/ui/widgets/__init__.py`
- Modify: `src/chargeghost_evse/util/log_setup.py`
- Modify: `src/chargeghost_evse/ui/styles/e_mobility.qss`
- Test: `tests/test_ui_widgets.py`
- Test: `tests/test_qt_signal_bridge.py`
- Test: `tests/test_log_setup.py`

### Step 1: Write the failing tests

Add coverage for:

- simulator mode exposes a fault injection panel or tab
- active fault summary is visible when any fault is enabled
- clearing faults updates the summary immediately
- structured logs include `fault_id`, `fault_scope`, and `fault_triggered` extras when a fault fires
- Qt bridge can forward fault-state changes if needed for the panel

Suggested test names:

- `test_simulator_widget_exposes_fault_panel`
- `test_fault_panel_shows_active_fault_count`
- `test_fault_panel_clear_all_disables_summary`
- `test_json_log_formatter_includes_fault_fields`

### Step 2: Implement the UI and log wiring

Add a panel that supports:

- toggling supported faults on and off
- editing simple fault parameters such as delay seconds or meter jump amount
- clearing all faults
- showing active trigger counts

Implementation notes:

- Keep fault state session-local; do not persist enabled faults to `SimulationConfig`.
- Make active faults visible even if the dedicated panel is closed.
- Use semantic styling so faulted devtool state is obvious but not visually chaotic.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_ui_widgets.py tests/test_qt_signal_bridge.py tests/test_log_setup.py -k "fault" -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/ui/widgets/fault_injection_panel.py src/chargeghost_evse/ui/app.py src/chargeghost_evse/ui/bridge.py src/chargeghost_evse/ui/widgets/__init__.py src/chargeghost_evse/util/log_setup.py src/chargeghost_evse/ui/styles/e_mobility.qss tests/test_ui_widgets.py tests/test_qt_signal_bridge.py tests/test_log_setup.py
git commit -m "feat: add fault injection controls and visibility"
```

---

## Task 6: Integrate Faults with the Scenario Runner

**Files:**
- Modify: `src/chargeghost_evse/devtools/scenario_models.py`
- Modify: `src/chargeghost_evse/devtools/scenario_runner.py`
- Modify: `src/chargeghost_evse/devtools/fault_manager.py`
- Test: `tests/test_scenario_runner.py`

### Step 1: Write the failing tests

Add coverage for:

- scenario step can enable a named fault
- scenario step can disable a named fault later in the run
- one-shot faults triggered by a scenario are recorded in the run report

Suggested test names:

- `test_scenario_can_enable_fault`
- `test_scenario_can_disable_fault`
- `test_scenario_report_records_fault_triggers`

### Step 2: Implement scenario integration

Add explicit step kinds such as:

- `fault_enable`
- `fault_disable`
- `fault_clear_all`

Keep them separate from generic action steps so validation and reporting stay clear.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_scenario_runner.py -k "fault" -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/devtools/scenario_models.py src/chargeghost_evse/devtools/scenario_runner.py src/chargeghost_evse/devtools/fault_manager.py tests/test_scenario_runner.py
git commit -m "feat: add scenario-driven fault control"
```

---

## Final Validation

Run the full quality suite:

```bash
poetry run pytest
poetry run ruff check src/ tests/
poetry run mypy src/
```

Manual verification checklist:

- Enable a disconnect fault and confirm the connection indicator changes visibly.
- Enable a heartbeat-drop fault and confirm the trigger is logged exactly once when configured as one-shot.
- Enable a frozen meter fault during an active session and confirm the meter display stays flat while session state remains active.
- Clear all faults and confirm the simulator returns to baseline behavior immediately.

---

## Notes and Guardrails

- Prefer central hooks to scattered `if fault_enabled` branches.
- Avoid malformed protocol traffic until there is a clear need; protocol-valid error paths already unlock a lot of backend testing value.
- Make sure faults are always discoverable in logs and, once available, the raw OCPP timeline.
- Do not persist active faults across app restarts unless users explicitly ask for that later.
