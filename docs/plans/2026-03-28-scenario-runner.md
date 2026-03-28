# Scenario Runner Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a deterministic scenario runner that can drive common simulator flows without manual UI interaction, with the same action surface usable from the Qt app and a future headless CLI mode.

**Architecture:** Introduce a protocol-agnostic devtools layer between the UI and the existing `Engine`/`Bridge` APIs. The new layer owns scenario definitions, action dispatch, run state, assertions, and reporting. The UI becomes a thin projection of scenario state, and the same runner can later be driven by a CLI harness.

**Tech Stack:** Python 3.11+, PySide6, asyncio, dataclasses, json, pytest, pytest-qt, existing `Engine`, `Bridge`, and adapter abstractions

**Run tests after every commit:**
```bash
poetry run pytest -x
poetry run ruff check src/ tests/
poetry run mypy src/
```

---

## Context You Must Know

- Manual simulator actions currently live in `src/chargeghost_evse/ui/app.py` on `SimulatorWidget.action_*` methods.
- The main simulation loop already runs at 100 ms cadence in `MainWindow.simulate_step`; reuse that timing instead of adding a second scheduler thread.
- The `Engine` already owns connector/session state changes, while `Bridge` owns outbound OCPP calls such as `send_authorize()` and connection-aware messaging.
- The simulator now supports both OCPP `1.6J` and `2.0.1`; scenario steps should be protocol-agnostic by default and version-gated only where the action surface differs.
- The repo already uses structured events and tests heavily; do not add an embedded scripting language or a database in this pass.
- The runner must not call QWidget methods directly. UI widgets should talk to a non-UI controller/service instead.

## Recommended Scope

Build this as a practical automation tool for backend and integration engineers:

- Support ordered action steps, timed waits, and assertion steps.
- Support JSON import/export for scenarios.
- Add a lightweight UI panel to load, start, cancel, and inspect a run.
- Add an optional headless entry point after the shared runtime is stable.

Do **not** build a visual drag-and-drop editor, plugin system, or arbitrary Python execution in the first pass.

---

## Success Criteria

Success means:

- A user can load a scenario JSON file and run it from the simulator UI.
- The runner can execute core charger actions: connect, authorize, plug in, start, suspend, resume, stop, unplug, and disconnect.
- Wait and assertion steps can fail with actionable error messages and step indices.
- Scenario execution is deterministic under tests without relying on real-time sleeps.
- `SimulatorWidget` actions are refactored to reuse the same controller the scenario runner uses.
- A basic CLI mode can run a scenario file without launching the Qt UI.

---

## Proposed Scenario Shape

Keep the first format intentionally small and explicit.

- Top-level fields: `name`, `description`, `version`, `defaults`, `steps`
- Supported initial step kinds:
  - `action`
  - `wait`
  - `assert`
  - `note`
- Supported initial actions:
  - `connect`
  - `disconnect`
  - `authorize`
  - `plug_in`
  - `unplug`
  - `start_charging`
  - `stop_charging`
  - `suspend_ev`
  - `resume_charging`
  - `set_rfid`
  - `clear_rfid`
  - `send_heartbeat`
- Supported initial assertions:
  - connector status equals expected value
  - session exists / does not exist
  - connection state equals expected value
  - meter reading reaches threshold

Add a `schema_version` field from day one so the format can evolve safely.

---

## Target File Layout

Create or refactor toward this structure:

- `src/chargeghost_evse/devtools/__init__.py`
- `src/chargeghost_evse/devtools/scenario_models.py`
- `src/chargeghost_evse/devtools/scenario_loader.py`
- `src/chargeghost_evse/devtools/scenario_runner.py`
- `src/chargeghost_evse/devtools/simulator_controller.py`
- `src/chargeghost_evse/devtools/scenario_report.py`
- `src/chargeghost_evse/ui/widgets/scenario_runner_panel.py`
- `tests/test_scenario_models.py`
- `tests/test_scenario_runner.py`
- `tests/test_simulator_controller.py`
- `tests/fixtures/scenarios/happy_path.json`
- `tests/fixtures/scenarios/wait_and_assert.json`

If the headless runner is added in the same pass, also add:

- `src/chargeghost_evse/devtools/scenario_cli.py`
- `tests/test_main.py`

---

## Task 1: Add Scenario Models and JSON Loader

**Files:**
- Create: `src/chargeghost_evse/devtools/__init__.py`
- Create: `src/chargeghost_evse/devtools/scenario_models.py`
- Create: `src/chargeghost_evse/devtools/scenario_loader.py`
- Test: `tests/test_scenario_models.py`
- Test: `tests/fixtures/scenarios/happy_path.json`
- Test: `tests/fixtures/scenarios/wait_and_assert.json`

### Step 1: Write the failing tests

Add coverage for:

- valid scenario JSON loads into typed dataclasses
- missing `schema_version` or `steps` raises a clear validation error
- unknown step kind is rejected
- connector-level defaults can be overridden per step
- invalid action names are rejected before runtime

Suggested test names:

- `test_load_scenario_definition_from_json`
- `test_loader_rejects_unknown_step_kind`
- `test_loader_rejects_unknown_action_name`
- `test_step_overrides_default_connector_id`
- `test_loader_requires_schema_version`

### Step 2: Implement the minimal scenario schema

Add dataclasses such as:

- `ScenarioDefinition`
- `ScenarioDefaults`
- `ScenarioStep`
- `ActionStep`
- `WaitStep`
- `AssertStep`

Implementation notes:

- Use plain dataclasses and manual validation; do not add `pydantic`.
- Preserve the original step index in each parsed step for better runtime errors.
- Keep the schema forward-compatible by storing unknown top-level metadata separately if useful.
- Normalize connector IDs and timeout/delay values during load rather than later in the runner.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_scenario_models.py -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/devtools/__init__.py src/chargeghost_evse/devtools/scenario_models.py src/chargeghost_evse/devtools/scenario_loader.py tests/test_scenario_models.py tests/fixtures/scenarios/happy_path.json tests/fixtures/scenarios/wait_and_assert.json
git commit -m "feat: add scenario definition schema"
```

---

## Task 2: Extract a Reusable Simulator Controller from the UI

**Files:**
- Create: `src/chargeghost_evse/devtools/simulator_controller.py`
- Modify: `src/chargeghost_evse/ui/app.py`
- Test: `tests/test_simulator_controller.py`
- Test: `tests/test_ui_widgets.py`

### Step 1: Write the failing tests

Add coverage for:

- controller action methods perform the same side effects as current UI actions
- controller returns structured success/failure results instead of only logging
- `SimulatorWidget` action buttons call into the controller instead of duplicating logic
- transaction ID generation moves out of the widget and into the shared controller

Suggested test names:

- `test_simulator_controller_plug_in_calls_engine`
- `test_simulator_controller_start_charging_assigns_transaction_id`
- `test_simulator_controller_authorize_uses_bridge`
- `test_simulator_widget_uses_simulator_controller`

### Step 2: Implement the controller

Create a `SimulatorController` responsible for:

- wrapping engine and bridge actions behind a non-Qt API
- maintaining transaction counters used for local starts
- returning a small result object such as `ActionResult(success, message, details)`
- emitting or logging consistent messages for UI, scenarios, and future CLI use

Refactor `SimulatorWidget.action_*` methods into thin wrappers that delegate to the controller and only handle widget-specific concerns such as toasts.

Important:

- Keep `Engine` and `Bridge` as the owners of domain and protocol behavior.
- Do not move business logic into the UI panel.
- Do not make the controller depend on Qt types.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_simulator_controller.py tests/test_ui_widgets.py -k "simulator controller or scenario" -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/devtools/simulator_controller.py src/chargeghost_evse/ui/app.py tests/test_simulator_controller.py tests/test_ui_widgets.py
git commit -m "refactor: extract shared simulator action controller"
```

---

## Task 3: Implement the Runner Core and Main-Loop Integration

**Files:**
- Create: `src/chargeghost_evse/devtools/scenario_runner.py`
- Create: `src/chargeghost_evse/devtools/scenario_report.py`
- Modify: `src/chargeghost_evse/ui/app.py`
- Test: `tests/test_scenario_runner.py`

### Step 1: Write the failing tests

Add coverage for:

- runner progresses action steps in order
- delay/wait steps advance from repeated `tick()` calls instead of `time.sleep()`
- cancellation stops the run cleanly and preserves a partial report
- runtime failures include step number, step label, and reason
- only one scenario run can be active at a time

Suggested test names:

- `test_runner_executes_action_steps_in_order`
- `test_runner_wait_step_uses_tick_based_time`
- `test_runner_cancel_stops_after_current_step`
- `test_runner_failure_includes_step_context`
- `test_runner_rejects_second_run_while_active`

### Step 2: Implement the runner state machine

Add a `ScenarioRunner` with explicit states such as:

- `idle`
- `running`
- `completed`
- `failed`
- `cancelled`

Implementation notes:

- Expose a `start(definition)`, `cancel()`, and `tick(interval_seconds)` API.
- Reuse the main Qt app's existing simulation cadence by calling `runner.tick(0.1)` from `MainWindow.simulate_step`.
- Keep the runner single-threaded in the first pass to avoid synchronization problems with `Engine` state.
- Store per-run metadata in a report object with started/finished timestamps, last completed step, and failure info.

### Step 3: Wire it into the app lifecycle

Modify `src/chargeghost_evse/ui/app.py` so that:

- `MainWindow` owns one `ScenarioRunner` instance
- `MainWindow.simulate_step` advances the runner after `engine.simulate(0.1)`
- scenario completion and failure can surface a toast and log entry

### Step 4: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_scenario_runner.py -v
```

Expected: PASS

### Step 5: Commit

```bash
git add src/chargeghost_evse/devtools/scenario_runner.py src/chargeghost_evse/devtools/scenario_report.py src/chargeghost_evse/ui/app.py tests/test_scenario_runner.py
git commit -m "feat: add tick-driven scenario runner"
```

---

## Task 4: Add Wait and Assertion Primitives

**Files:**
- Modify: `src/chargeghost_evse/devtools/scenario_models.py`
- Modify: `src/chargeghost_evse/devtools/scenario_runner.py`
- Modify: `src/chargeghost_evse/devtools/simulator_controller.py`
- Test: `tests/test_scenario_runner.py`

### Step 1: Write the failing tests

Add coverage for:

- waiting for connector status transition within timeout
- waiting for connection state after connect/disconnect steps
- asserting session existence or absence
- asserting meter value threshold after simulated time passes
- timeout errors describe both expected and actual observed state

Suggested test names:

- `test_wait_for_connector_status_succeeds_before_timeout`
- `test_wait_for_connection_state_times_out_with_actual_value`
- `test_assert_session_active_fails_when_missing`
- `test_assert_meter_threshold_passes_after_ticks`

### Step 2: Implement assertion evaluation

Add simple reusable evaluators for:

- connector status
- connection state
- active session existence
- meter reading threshold

Implementation notes:

- Poll existing runtime state; do not add dedicated blocking waits.
- Use controller or engine/bridge query helpers instead of reading UI widget state.
- Keep assertion messages stable so tests and CI snapshots stay readable.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_scenario_runner.py -k "wait or assert" -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/devtools/scenario_models.py src/chargeghost_evse/devtools/scenario_runner.py src/chargeghost_evse/devtools/simulator_controller.py tests/test_scenario_runner.py
git commit -m "feat: add scenario waits and assertions"
```

---

## Task 5: Add a Scenario Runner UI Panel

**Files:**
- Create: `src/chargeghost_evse/ui/widgets/scenario_runner_panel.py`
- Modify: `src/chargeghost_evse/ui/app.py`
- Modify: `src/chargeghost_evse/ui/widgets/__init__.py`
- Modify: `src/chargeghost_evse/ui/widgets/app_settings.py`
- Modify: `src/chargeghost_evse/ui/styles/e_mobility.qss`
- Test: `tests/test_ui_widgets.py`

### Step 1: Write the failing tests

Add coverage for:

- simulator mode exposes a dedicated scenario runner tab or panel
- panel can show loaded scenario name, step list, and current run state
- start button disables while a run is active and cancel becomes enabled
- last opened scenario path persists in `AppSettings`

Suggested test names:

- `test_simulator_widget_exposes_scenario_runner_panel`
- `test_scenario_runner_panel_disables_start_when_running`
- `test_scenario_runner_panel_shows_current_step`
- `test_app_settings_persists_last_scenario_path`

### Step 2: Implement the panel

Add a panel that supports:

- load scenario file
- reload current scenario
- start run
- cancel run
- show step list with current step highlighted
- show final run status and failure message

Design guidance:

- Reuse the existing simulator visual language instead of adding a radically different screen.
- Keep the panel read-only in the first pass; editing the JSON file remains external.
- Favor a simple list + status summary over a dense table.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_ui_widgets.py -k "scenario runner" -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/ui/widgets/scenario_runner_panel.py src/chargeghost_evse/ui/app.py src/chargeghost_evse/ui/widgets/__init__.py src/chargeghost_evse/ui/widgets/app_settings.py src/chargeghost_evse/ui/styles/e_mobility.qss tests/test_ui_widgets.py
git commit -m "feat: add scenario runner panel"
```

---

## Task 6: Add a Headless CLI Entry Point

**Files:**
- Create: `src/chargeghost_evse/devtools/scenario_cli.py`
- Modify: `src/chargeghost_evse/main.py`
- Test: `tests/test_main.py`
- Test: `tests/test_scenario_runner.py`

### Step 1: Write the failing tests

Add coverage for:

- `main.py` still launches the UI by default
- `--run-scenario path.json` launches a headless scenario execution path
- non-zero exit code is returned on scenario failure or timeout
- scenario report is printed in a concise machine-readable format

Suggested test names:

- `test_main_defaults_to_ui_mode`
- `test_main_runs_headless_scenario_when_requested`
- `test_main_returns_non_zero_on_scenario_failure`

### Step 2: Implement the CLI harness

Implementation notes:

- Use `argparse` in `src/chargeghost_evse/main.py`.
- Default behavior must remain unchanged for existing desktop users.
- Headless mode should construct the same `Engine`, `Bridge`, `SimulatorController`, and `ScenarioRunner` components without creating a `QApplication`.
- Drive the same tick loop the UI uses until the scenario completes, fails, or times out.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_main.py tests/test_scenario_runner.py -k "headless or main" -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/devtools/scenario_cli.py src/chargeghost_evse/main.py tests/test_main.py tests/test_scenario_runner.py
git commit -m "feat: add headless scenario runner"
```

---

## Final Validation

Run the full quality suite:

```bash
poetry run pytest
poetry run ruff check src/ tests/
poetry run mypy src/
```

Optional manual verification:

- Launch the app, load a happy-path scenario, and confirm the step list updates live.
- Run the same scenario through `python -m chargeghost_evse.main --run-scenario tests/fixtures/scenarios/happy_path.json`.
- Confirm cancellation leaves the simulator in a predictable state and surfaces a readable report.

---

## Notes and Follow-Ups

- Keep the scenario file format intentionally small until real users request more expressive power.
- Once fault injection exists, add `fault.enable` and `fault.disable` as new step kinds rather than overloading `action`.
- Once the raw OCPP timeline exists, attach scenario step IDs to timeline events so failures are easier to debug.
- Do not let the headless runner fork behavior away from the desktop runtime; the controller and runner should remain the shared core.
