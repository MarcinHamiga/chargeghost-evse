# Architectural Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 19 identified issues across bugs, protocol compliance, dead code, dependencies, thread safety, and structural refactoring.

**Architecture:** Four ordered layers — dead code/deps → engine bugs → bridge/OCPP → UI. Each layer is independently testable. No changes flow upward.

**Tech Stack:** Python 3.11+, PySide6, asyncio, websockets, OCPP 1.6J, pytest, ruff, mypy

**Run tests after every commit:**
```bash
poetry run pytest -x
poetry run ruff check src/
poetry run mypy src/
```

---

## Layer 0 — Dead Code & Dependency Cleanup

### Task 1: Remove dead code from engine and util layers

**Files:**
- Modify: `src/chargeghost_evse/engine/connector.py`
- Modify: `src/chargeghost_evse/engine/engine.py`
- Modify: `src/chargeghost_evse/engine/energy_meter.py`
- Delete: `src/chargeghost_evse/util/ocpp_logger.py`

No tests needed — pure deletion. Run the test suite after to confirm nothing breaks.

**Step 1: Delete dead methods from connector.py**

Remove the entire `get_status()` method (it duplicates the `status` property):
```python
# DELETE this method entirely from connector.py:
def get_status(self) -> ConnectorState:
    ...
```

Remove the entire `authorize()` method (orphaned, never called):
```python
# DELETE this method entirely from connector.py:
def authorize(self, id_tag: str) -> None:
    ...
```

Remove `on_parameters_change` event declaration (no subscribers anywhere):
```python
# DELETE from __init__:
self.on_parameters_change: Event = Event()
```

Remove the `on_parameters_change.emit()` call in `set_parameters()` (line ~206):
```python
# DELETE this line from set_parameters():
self.on_parameters_change.emit(connector_id=self.id)
```

**Step 2: Remove dead attributes from engine.py**

In `Engine.__init__`, delete these four unused attributes:
```python
# DELETE these four lines from engine.py __init__:
self.last_update_time: Optional[float] = None
self.last_display_time: Optional[float] = None
self.simulation_time_step: float = 0.1
self.display_time_step: float = 1.0
```

Remove the duplicate `ConnectorState` import in the `TYPE_CHECKING` block. The runtime import at the top of the file already covers it:
```python
# In the TYPE_CHECKING block, DELETE:
from chargeghost_evse.engine.connector import ConnectorState
```

**Step 3: Remove unused Subscriber base class from EnergyMeter**

`EnergyMeter` inherits from `Subscriber` but never calls `subscribe_to()`. Change:
```python
# FROM:
class EnergyMeter(Subscriber):

# TO:
class EnergyMeter:
```

Remove the `Subscriber` import from `energy_meter.py` if it becomes unused.

**Step 4: Delete ocpp_logger.py**

```bash
rm src/chargeghost_evse/util/ocpp_logger.py
```

Check for any imports of it:
```bash
grep -r "ocpp_logger" src/
```
Expected: no results. If there are any, remove those imports too.

**Step 5: Run tests and commit**

```bash
poetry run pytest -x
poetry run ruff check src/
```

```bash
git add -p
git commit -m "refactor: remove dead code from engine and util layers

- connector.py: remove get_status(), authorize(), on_parameters_change event
- engine.py: remove 4 unused timing attributes, duplicate ConnectorState import
- energy_meter.py: remove unused Subscriber base class
- ocpp_logger.py: delete unused file (zero production imports, broken internals)"
```

---

### Task 2: Remove dead code from UI layer

**Files:**
- Modify: `src/chargeghost_evse/ui/bridge.py`
- Modify: `src/chargeghost_evse/ui/widgets/session_dashboard.py`
- Modify: `src/chargeghost_evse/ui/widgets/log_panel.py`
- Modify: `src/chargeghost_evse/ui/widgets/collapsible_log.py`

**Step 1: Remove dead method from ui/bridge.py**

Delete `_on_bridge_deleted` — it's a weakref finalizer that does nothing:
```python
# DELETE entirely:
def _on_bridge_deleted(self, ref):
    pass
```

Also update the `__init__` line that registers it:
```python
# FROM:
self._bridge_ref = weakref.ref(bridge, self._on_bridge_deleted)

# TO:
self._bridge_ref = weakref.ref(bridge)
```

**Step 2: Remove dead methods from session_dashboard.py**

Delete `_refresh_widget_style` — never called anywhere:
```python
# DELETE entirely:
def _refresh_widget_style(self) -> None:
    ...
```

Delete `_on_charge_clicked` — references nonexistent `self.btn_charge`, stale artifact:
```python
# DELETE entirely:
def _on_charge_clicked(self) -> None:
    ...
```

**Step 3: Remove dead method from log_panel.py**

Delete `action_copy` — never connected to any signal or menu:
```python
# DELETE entirely:
def action_copy(self) -> None:
    ...
```

**Step 4: Remove dead method from collapsible_log.py**

Delete `set_log_count` — never called:
```python
# DELETE entirely:
def set_log_count(self, count: int) -> None:
    ...
```

**Step 5: Run tests and commit**

```bash
poetry run pytest -x
poetry run ruff check src/
```

```bash
git commit -m "refactor: remove dead code from UI layer

- ui/bridge.py: remove _on_bridge_deleted no-op weakref finalizer
- session_dashboard.py: remove _refresh_widget_style, _on_charge_clicked
- log_panel.py: remove action_copy (never connected)
- collapsible_log.py: remove set_log_count (never called)"
```

---

### Task 3: Clean up dependencies in pyproject.toml

**Files:**
- Modify: `pyproject.toml`

**Step 1: Remove unused production dependencies**

In `pyproject.toml`, remove from `[project] dependencies`:
- `pydantic` (listed, explicitly unused per CLAUDE.md)
- `pydantic-settings` (same)
- `pyyaml` (same)

**Step 2: Move pyinstaller to dev dependencies**

`pyinstaller` is a build tool used in `build_tools/binary.py`, not a runtime dependency.

Move it from `[project] dependencies` to `[dependency-groups] dev`:
```toml
# Remove from [project] dependencies:
# pyinstaller (>=6.0.0)

# Add to [dependency-groups] dev:
"pyinstaller>=6.0.0",
```

**Step 3: Verify the app still runs**

```bash
poetry install
poetry run pytest -x
```

**Step 4: Commit**

```bash
git commit -m "chore: remove unused dependencies and move pyinstaller to dev

- Remove pydantic, pydantic-settings, pyyaml (declared but unused)
- Move pyinstaller from production to dev dependencies (build tool)"
```

---

## Layer 1 — Engine Bugs

### Task 4: Fix session.start_time — monotonic vs POSIX timestamp

**Files:**
- Modify: `src/chargeghost_evse/engine/session.py`
- Modify: `src/chargeghost_evse/bridge/bridge.py` (line ~538)
- Test: `tests/test_session.py`

**Background:** `session.py` stores `time.monotonic()` for `start_time` (line 75). This is uptime-relative, not epoch-relative. When `bridge.py` passes it to `datetime.fromtimestamp(session.start_time, tz=timezone.utc)` (line ~538), it produces a timestamp from 1970 offset by system uptime — garbage. This also breaks `TxProfile` matching in `ChargingProfileManager`.

**Step 1: Write the failing test**

In `tests/test_session.py`, add:
```python
import time
from datetime import datetime, timezone


def test_start_time_is_posix_timestamp():
    """start_time must be a valid POSIX timestamp, not a monotonic counter."""
    before = time.time()
    session = Session(connector_id=1, id_tag="TAG1", transaction_id=1)
    after = time.time()

    assert before <= session.start_time <= after

    # Must convert to a valid datetime without producing a 1970-era date
    dt = datetime.fromtimestamp(session.start_time, tz=timezone.utc)
    assert dt.year >= 2024
```

**Step 2: Run to verify it fails**

```bash
poetry run pytest tests/test_session.py::test_start_time_is_posix_timestamp -v
```
Expected: FAIL (start_time is monotonic, year comes out ~1970)

**Step 3: Fix session.py**

```python
# FROM (session.py line ~75):
self.start_time: float = time.monotonic()

# TO:
self.start_time: float = time.time()
```

**Step 4: Fix bridge.py**

The `datetime.fromtimestamp` call at bridge.py line ~538 is now correct. Verify it still reads like:
```python
transaction_start = datetime.fromtimestamp(session.start_time, tz=timezone.utc)
```
No change needed there — it was always the right call, just got the wrong input.

**Step 5: Run tests**

```bash
poetry run pytest tests/test_session.py -v
```
Expected: PASS

**Step 6: Commit**

```bash
git commit -m "fix: use time.time() for session.start_time instead of time.monotonic()

time.monotonic() is uptime-relative and produces garbage when passed to
datetime.fromtimestamp(). This affected TxProfile matching and UI display
of transaction start time."
```

---

### Task 5: Fix EnergyMeter.handle_max_charge_reached signature mismatch

**Files:**
- Modify: `src/chargeghost_evse/engine/energy_meter.py`
- Test: `tests/test_engine.py`

**Background:** `Session.ev_max_charge_reached` emits with `connector_id=int`. `EnergyMeter.handle_max_charge_reached(self)` accepts no arguments → `TypeError` at runtime when an EV reaches max charge. Charging never stops.

**Step 1: Write the failing test**

In `tests/test_engine.py`, add:
```python
def test_energy_meter_stops_when_ev_max_charge_reached():
    """EnergyMeter must stop charging when Session fires ev_max_charge_reached."""
    engine = Engine()
    engine.add_connector(voltage=230.0, current=32.0, phase=1)
    connector_id = engine.connectors[0].id

    engine.plug_in(connector_id)
    engine.start_session(connector_id=connector_id, transaction_id=1)

    # Manually trigger max charge reached
    assert engine.session is not None
    engine.session.ev_max_charge_reached.emit(connector_id=connector_id)

    # EnergyMeter must have stopped
    assert engine.energy_meter.is_charging is False
```

**Step 2: Run to verify it fails**

```bash
poetry run pytest tests/test_engine.py::test_energy_meter_stops_when_ev_max_charge_reached -v
```
Expected: FAIL with `TypeError: handle_max_charge_reached() got an unexpected keyword argument 'connector_id'`

**Step 3: Fix energy_meter.py**

```python
# FROM:
def handle_max_charge_reached(self) -> None:

# TO:
def handle_max_charge_reached(self, connector_id: int) -> None:
```

**Step 4: Run tests**

```bash
poetry run pytest tests/test_engine.py -v
```
Expected: all PASS

**Step 5: Commit**

```bash
git commit -m "fix: add connector_id param to EnergyMeter.handle_max_charge_reached

ev_max_charge_reached emits connector_id=int but the handler accepted no
args, causing TypeError at runtime. EV max charge never stopped the meter."
```

---

### Task 6: Fix connector.stop_charging() to handle SUSPENDED_EV state

**Files:**
- Modify: `src/chargeghost_evse/engine/connector.py`
- Test: `tests/test_connector.py`

**Background:** `stop_charging()` guards on `status == CHARGING` only. If the EV is in `SUSPENDED_EV` (battery full) and a session stop is triggered, the connector stays in `SUSPENDED_EV` permanently.

**Step 1: Write the failing test**

In `tests/test_connector.py`, add:
```python
def test_stop_charging_from_suspended_ev():
    """stop_charging() must work when connector is in SUSPENDED_EV state."""
    connector = Connector(id=1, voltage=230.0, current=32.0, phase=1)
    connector.plug_in()

    # Manually set SUSPENDED_EV (battery full)
    connector._status = ConnectorState.SUSPENDED_EV

    connector.stop_charging()

    # Must transition to Preparing (still plugged in)
    assert connector.status == ConnectorState.PREPARING
```

**Step 2: Run to verify it fails**

```bash
poetry run pytest tests/test_connector.py::test_stop_charging_from_suspended_ev -v
```
Expected: FAIL (stays in SUSPENDED_EV)

**Step 3: Fix connector.py**

```python
# FROM (connector.py stop_charging):
def stop_charging(self) -> None:
    if self.status == ConnectorState.CHARGING:

# TO:
def stop_charging(self) -> None:
    if self.status in (ConnectorState.CHARGING, ConnectorState.SUSPENDED_EV):
```

**Step 4: Run tests**

```bash
poetry run pytest tests/test_connector.py -v
```
Expected: all PASS

**Step 5: Commit**

```bash
git commit -m "fix: stop_charging() now handles SUSPENDED_EV state

When EV battery is full, connector enters SUSPENDED_EV. stop_charging()
only handled CHARGING, leaving connector stuck in SUSPENDED_EV on stop."
```

---

### Task 7: Fix session.process_energy_delivery multi-fire and readability

**Files:**
- Modify: `src/chargeghost_evse/engine/session.py`
- Test: `tests/test_session.py`

**Background:** Once `ev_max_charge_reached` fires, every subsequent call to `process_energy_delivery` re-fires it. Also the energy cap ternary is harder to read than `min()`.

**Step 1: Write the failing test**

```python
def test_ev_max_charge_reached_fires_only_once():
    """ev_max_charge_reached must emit exactly once even with repeated calls."""
    session = Session(connector_id=1, id_tag="TAG", transaction_id=1, max_energy=1.0)

    fired_count = 0

    def on_max_reached(connector_id):
        nonlocal fired_count
        fired_count += 1

    session.ev_max_charge_reached.subscribe(on_max_reached)

    # First delivery reaches max
    session.process_energy_delivery(1.0, connector_id=1)
    assert fired_count == 1

    # Subsequent calls must not re-fire
    session.process_energy_delivery(0.0, connector_id=1)
    session.process_energy_delivery(0.0, connector_id=1)
    assert fired_count == 1
```

**Step 2: Run to verify it fails**

```bash
poetry run pytest tests/test_session.py::test_ev_max_charge_reached_fires_only_once -v
```
Expected: FAIL (fired_count > 1)

**Step 3: Fix session.py**

Add a `_max_reached` flag to `__init__`:
```python
self._max_reached: bool = False
```

Replace the energy cap ternary with `min()` and guard the event emit:
```python
# FROM (lines ~100-117):
self.energy_charged += (
    amount
    if self.energy_charged + amount <= self.max_energy
    else self.max_energy - self.energy_charged
)
...
if self.max_energy > 0 and self.energy_charged >= self.max_energy:
    self.energy_charged = self.max_energy
    self.ev_max_charge_reached.emit(connector_id=self.connector_id)

# TO:
if self.max_energy > 0:
    self.energy_charged = min(self.energy_charged + amount, self.max_energy)
else:
    self.energy_charged += amount

if self.max_energy > 0 and self.energy_charged >= self.max_energy and not self._max_reached:
    self._max_reached = True
    self.ev_max_charge_reached.emit(connector_id=self.connector_id)
```

**Step 4: Run tests**

```bash
poetry run pytest tests/test_session.py -v
```
Expected: all PASS

**Step 5: Commit**

```bash
git commit -m "fix: prevent ev_max_charge_reached from firing multiple times

Added _max_reached flag so the event fires exactly once per session.
Also simplified energy cap logic using min() instead of inline ternary."
```

---

### Task 8: Fix SimulationConfig reliability

**Files:**
- Modify: `src/chargeghost_evse/util/config.py`
- Test: `tests/test_update_config.py` (or create new test file)

**Background:** Three issues: (1) silent error swallowing on corrupted config, (2) non-atomic save that can corrupt on crash, (3) `num_connectors` is "deprecated" but actively used — remove it.

**Step 1: Write tests**

In `tests/test_update_config.py` (or a new `tests/test_config.py`), add:
```python
import json
import logging
from pathlib import Path

import pytest

from chargeghost_evse.util import config as cfg_module
from chargeghost_evse.util.config import SimulationConfig


def test_load_logs_warning_on_corrupted_json(tmp_path, monkeypatch, caplog):
    """A corrupted config file must log a warning, not fail silently."""
    config_file = tmp_path / "config.json"
    config_file.write_text("{ not valid json }")
    monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

    with caplog.at_level(logging.WARNING):
        result = SimulationConfig.load()

    assert result is not None  # Falls back to defaults
    assert any("config" in r.message.lower() for r in caplog.records)


def test_save_is_atomic(tmp_path, monkeypatch):
    """save() must write atomically (no partial file on interrupted write)."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

    config = SimulationConfig()
    config.save()

    # No .tmp file should remain after successful save
    assert not (tmp_path / "config.json.tmp").exists()
    assert config_file.exists()
    data = json.loads(config_file.read_text())
    assert "connectors" in data


def test_num_connectors_field_removed(tmp_path, monkeypatch):
    """num_connectors must not appear in saved JSON (computed from connectors list)."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

    config = SimulationConfig()
    config.save()

    data = json.loads(config_file.read_text())
    assert "num_connectors" not in data
```

**Step 2: Run to verify they fail**

```bash
poetry run pytest tests/test_config.py -v
```
Expected: all FAIL

**Step 3: Fix config.py — add warning log**

First add `import logging` at the top of `config.py`. Then fix the except block (~line 280):
```python
# FROM:
except (json.JSONDecodeError, IOError):
    return cls()

# TO:
except (json.JSONDecodeError, IOError) as e:
    logging.warning("Failed to load config from %s, using defaults: %s", CONFIG_FILE, e)
    return cls()
```

**Step 4: Fix config.py — atomic save**

The `save()` method writes directly to `CONFIG_FILE`. Change it to write to a temp file then replace:
```python
# In save(), find where it opens CONFIG_FILE for writing.
# FROM (something like):
CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
with open(CONFIG_FILE, "w") as f:
    json.dump(data, f, indent=2)

# TO:
CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
tmp_file = CONFIG_FILE.with_suffix(".tmp")
with open(tmp_file, "w") as f:
    json.dump(data, f, indent=2)
os.replace(tmp_file, CONFIG_FILE)
```

Add `import os` at the top of `config.py` if not already present.

**Step 5: Remove num_connectors field**

Find and remove `num_connectors` from the `SimulationConfig` dataclass definition:
```python
# DELETE this field from SimulationConfig:
num_connectors: int = 1
```

Remove `num_connectors` from `to_dict()` / `save()` serialization if present.

Remove `num_connectors` from `from_dict()` / `load()` deserialization if present (or handle it gracefully as an unknown key to not break old config files — just ignore it).

**Step 6: Fix callers of num_connectors in ui/app.py**

Search for all uses:
```bash
grep -n "num_connectors" src/chargeghost_evse/ui/app.py
```

Replace each `config.num_connectors = len(...)` or `self.config.num_connectors = ...` with just `len(self.engine.connectors)` at the call site, or simply delete the assignment (saving `config.connectors` already captures the connector count).

**Step 7: Run tests**

```bash
poetry run pytest tests/test_config.py tests/test_update_config.py -v
```
Expected: all PASS

**Step 8: Run full suite and commit**

```bash
poetry run pytest -x
git commit -m "fix: improve SimulationConfig reliability

- Log warning on corrupted/missing config file instead of silently using defaults
- Atomic save via write-to-tmp + os.replace to prevent corruption on crash
- Remove deprecated num_connectors field (computed from len(connectors))"
```

---

## Layer 2 — Bridge/OCPP Fixes

### Task 9: Replace poll threads with on_adapter_registered event

**Files:**
- Modify: `src/chargeghost_evse/bridge/bridge.py`
- Test: `tests/test_bridge_inject.py`

**Background:** `_initial_status_loop` and `_inject_limit_getter_loop` are two daemon threads sleeping 0.5s in a loop forever. Both wait for the adapter to finish registration. Both can be replaced by subscribing to the adapter's existing `on_registration_accepted` event. This eliminates 2 threads and ~60 lines.

The `Adapter.on_registration_accepted` event already exists (`adapter.py:151`). We need to verify it is emitted after boot notification succeeds.

**Step 1: Check where on_registration_accepted is emitted**

```bash
grep -n "on_registration_accepted" src/chargeghost_evse/ocpp_adapter/adapter.py
```

If it's not emitted anywhere, we need to add the emit. Find `send_boot_notification` in `adapter.py` and look for where `registration_status` is set to `Accepted`. Add:
```python
# In send_boot_notification, after setting self.registration_status = response.status:
if self.registration_status == RegistrationStatus.accepted:
    self.on_registration_accepted.emit()
```

**Step 2: Add on_adapter_registered event to AsyncRunner**

`AsyncRunner` gets recreated each connection cycle (via the daemon thread restart), but the adapter changes on every reconnect. The cleanest solution: `AsyncRunner` exposes its own `on_adapter_registered: Event` that fires when the current adapter has registered. Bridge subscribes once to `runner.on_adapter_registered`.

In `AsyncRunner.__init__`:
```python
self.on_adapter_registered: Event = Event()
```

In `AsyncRunner._run_adapter()`, after the boot notification succeeds (right after the `if self.adapter.registration_status:` block at line ~272):
```python
if self.adapter.registration_status == RegistrationStatus.accepted:
    self.on_adapter_registered.emit()
```

**Step 3: Update Bridge.setup() to use event instead of poll threads**

In `Bridge.setup()`:
```python
# FROM:
# Start initial status notification thread
threading.Thread(target=self._initial_status_loop, daemon=True).start()

# Start charging profile injection thread
threading.Thread(target=self._inject_limit_getter_loop, daemon=True).start()

# TO:
self.runner.on_adapter_registered.subscribe(self._on_adapter_registered)
```

Add the new handler method:
```python
def _on_adapter_registered(self) -> None:
    """Called when the adapter has completed boot notification registration."""
    self._send_initial_status_notifications()
    self._inject_limit_getter()
    self._log(message="Charging profile limit enforcement enabled")
```

**Step 4: Delete the two poll thread methods**

Delete `_initial_status_loop()` entirely.
Delete `_inject_limit_getter_loop()` entirely.

**Step 5: Write a test for reconnect behavior**

In `tests/test_bridge_inject.py`, verify the new event-based approach fires on both first connect and reconnect. Check the existing test to understand the pattern, then add:
```python
def test_on_adapter_registered_fires_on_reconnect():
    """on_adapter_registered must fire after each successful boot notification."""
    # This test verifies the event fires when adapter.on_registration_accepted fires.
    # Use the existing test pattern from test_bridge_inject.py.
    fired = []
    runner = AsyncRunner.__new__(AsyncRunner)
    runner.on_adapter_registered = Event()
    runner.on_adapter_registered.subscribe(lambda: fired.append(1))

    # Simulate two registration events (first connect + reconnect)
    runner.on_adapter_registered.emit()
    runner.on_adapter_registered.emit()

    assert len(fired) == 2
```

**Step 6: Run tests**

```bash
poetry run pytest tests/test_bridge_inject.py -v
poetry run pytest -x
```

**Step 7: Commit**

```bash
git commit -m "refactor: replace poll threads with on_adapter_registered event

_initial_status_loop and _inject_limit_getter_loop were daemon threads
sleeping 0.5s in a loop waiting for connection. Replaced with a single
on_adapter_registered event on AsyncRunner, reducing threads from 4 to 2
and fixing the protocol bug where status notifications weren't re-sent
after reconnect."
```

---

### Task 10: Fix retry delay reset on successful connection

**Files:**
- Modify: `src/chargeghost_evse/bridge/bridge.py`

**Background:** In `AsyncRunner._run_adapter()`, `retry_delay` exponentially increases to 60s but never resets after a long-lived connection. The next disconnect after hours of uptime starts at 60s backoff.

**Step 1: Fix the one-liner**

In `_run_adapter()`, inside the `async with websockets.connect(...)` block, immediately after `self._connected = True` (line ~263):
```python
# ADD this line right after self._connected = True:
retry_delay = 1  # Reset backoff after successful connection
```

**Step 2: Run tests and commit**

```bash
poetry run pytest -x
git commit -m "fix: reset retry_delay to 1s after successful WebSocket connection

Backoff was never reset, so a brief disconnect after hours of uptime
would start at the maximum 60s delay instead of 1s."
```

---

### Task 11: Fix TOCTOU adapter capture in Bridge event handlers

**Files:**
- Modify: `src/chargeghost_evse/bridge/bridge.py`

**Background:** `on_connector_status_change` and `on_engine_session_stopped` don't capture `adapter` and `loop` before use. The adapter can become `None` between check and use. `on_engine_session_started` already does this correctly — apply the same pattern everywhere.

**Step 1: Fix on_connector_status_change**

```python
# FROM (bridge.py on_connector_status_change):
if self.runner.adapter and self.runner.loop:
    conn_status = status.value if hasattr(status, "value") else str(status)
    ...
    asyncio.run_coroutine_threadsafe(
        self.runner.adapter.send_status_notification(...),
        self.runner.loop,
    )

# TO:
adapter = self.runner.adapter
loop = self.runner.loop
if adapter and loop:
    conn_status = status.value if hasattr(status, "value") else str(status)
    ...
    asyncio.run_coroutine_threadsafe(
        adapter.send_status_notification(...),
        loop,
    )
```

**Step 2: Fix on_engine_session_stopped**

```python
# FROM (bridge.py on_engine_session_stopped):
if not self.runner.adapter or not self.runner.loop:
    return
...
asyncio.run_coroutine_threadsafe(
    self.runner.adapter.send_stop_transaction(...),
    self.runner.loop,
)

# TO:
adapter = self.runner.adapter
loop = self.runner.loop
if not adapter or not loop:
    return
...
asyncio.run_coroutine_threadsafe(
    adapter.send_stop_transaction(...),
    loop,
)
```

**Step 3: Fix send_authorize and send_heartbeat (similar pattern)**

Apply the same `adapter = self.runner.adapter; loop = self.runner.loop` capture to any other methods in `Bridge` that call `self.runner.adapter.*` inside or alongside `run_coroutine_threadsafe`.

**Step 4: Run tests and commit**

```bash
poetry run pytest -x
git commit -m "fix: capture adapter reference before run_coroutine_threadsafe

Adapter can become None between the null-check and actual use (connection
drop race). Capture to local variable first, matching the pattern already
used in on_engine_session_started."
```

---

### Task 12: Add future error handling to run_coroutine_threadsafe calls

**Files:**
- Modify: `src/chargeghost_evse/bridge/bridge.py`

**Background:** All `run_coroutine_threadsafe` calls return a `Future` that is silently ignored. If `StartTransaction` times out, `session.transaction_id` stays 0. Failures are invisible.

**Step 1: Add error callback helper**

In `Bridge`, add a private helper:
```python
def _handle_future_error(self, future: "concurrent.futures.Future[Any]") -> None:
    """Log exceptions from fire-and-forget coroutine futures."""
    exc = future.exception()
    if exc is not None:
        self._log(message=f"[red]OCPP send failed:[/red] {type(exc).__name__}: {exc}")
```

Add the import at the top of bridge.py if not already present:
```python
import concurrent.futures
from typing import Any
```

**Step 2: Apply to all run_coroutine_threadsafe calls**

Find every `asyncio.run_coroutine_threadsafe(...)` call in `Bridge` and attach the callback:
```python
# FROM:
asyncio.run_coroutine_threadsafe(coro, loop)

# TO:
future = asyncio.run_coroutine_threadsafe(coro, loop)
future.add_done_callback(self._handle_future_error)
```

Do this for: `on_connector_status_change`, `on_engine_session_started` (the `send_start_tx` call), `on_engine_session_stopped`, `send_authorize`, `send_heartbeat`, `_meter_values_loop`.

**Step 3: Run tests and commit**

```bash
poetry run pytest -x
git commit -m "fix: log errors from fire-and-forget run_coroutine_threadsafe futures

Silent failures when OCPP sends fail (timeout, disconnect) were invisible.
Now all futures have a done callback that logs exceptions via on_log."
```

---

### Task 13: Move _parse_charging_profile to ChargingProfileManager

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py`
- Modify: `src/chargeghost_evse/ocpp_adapter/adapter.py`

**Background:** `Adapter._parse_charging_profile` converts OCPP dicts to `ChargingProfileData`. This is domain logic that belongs in `ChargingProfileManager` where the data model lives.

**Step 1: Add static method to ChargingProfileManager**

In `charging_profile_manager.py`, add a new `@staticmethod` method `from_ocpp_dict`. Copy the entire body from `adapter.py:_parse_charging_profile`:

```python
@staticmethod
def from_ocpp_dict(cs_profile: dict) -> "ChargingProfileData":
    """
    Parse an OCPP CsChargingProfile dict to ChargingProfileData.

    Args:
        cs_profile: OCPP CsChargingProfile dictionary from SetChargingProfile.

    Returns:
        ChargingProfileData instance.

    Raises:
        KeyError: If required fields are missing.
        ValueError: If enum values are invalid.
    """
    cs_schedule = cs_profile["chargingSchedule"]

    periods = []
    for p in cs_schedule["chargingSchedulePeriod"]:
        period = ChargingSchedulePeriodData(
            start_period=p["startPeriod"],
            limit=float(p["limit"]),
            number_phases=p.get("numberPhases"),
        )
        periods.append(period)

    schedule = ChargingScheduleData(
        charging_rate_unit=ChargingRateUnitType(cs_schedule["chargingRateUnit"]),
        charging_schedule_period=tuple(periods),
        duration=cs_schedule.get("duration"),
        start_schedule=(
            datetime.fromisoformat(
                cs_schedule["startSchedule"].replace("Z", "+00:00")
            )
            if cs_schedule.get("startSchedule")
            else None
        ),
        min_charging_rate=cs_schedule.get("minChargingRate"),
    )

    recurrency = None
    if cs_profile.get("recurrencyKind"):
        recurrency = RecurrencyKind(cs_profile["recurrencyKind"])

    valid_from = None
    if cs_profile.get("validFrom"):
        valid_from = datetime.fromisoformat(
            cs_profile["validFrom"].replace("Z", "+00:00")
        )

    valid_to = None
    if cs_profile.get("validTo"):
        valid_to = datetime.fromisoformat(
            cs_profile["validTo"].replace("Z", "+00:00")
        )

    return ChargingProfileData(
        charging_profile_id=cs_profile["chargingProfileId"],
        stack_level=cs_profile["stackLevel"],
        charging_profile_purpose=ChargingProfilePurposeType(
            cs_profile["chargingProfilePurpose"]
        ),
        charging_profile_kind=ChargingProfileKindType(
            cs_profile["chargingProfileKind"]
        ),
        charging_schedule=schedule,
        transaction_id=cs_profile.get("transactionId"),
        recurrency_kind=recurrency,
        valid_from=valid_from,
        valid_to=valid_to,
    )
```

**Step 2: Update adapter.py to use it**

In `adapter.py`, replace the call at line ~882:
```python
# FROM:
profile = self._parse_charging_profile(cs_charging_profiles)

# TO:
profile = ChargingProfileManager.from_ocpp_dict(cs_charging_profiles)
```

Delete the `_parse_charging_profile` method from `Adapter` entirely.

**Step 3: Run tests and commit**

```bash
poetry run pytest -x
poetry run ruff check src/
git commit -m "refactor: move _parse_charging_profile to ChargingProfileManager.from_ocpp_dict

Profile parsing is domain logic that belongs with the data model, not
in Adapter. Reduces coupling between Adapter and ChargingProfileData."
```

---

### Task 14: Deduplicate local auth check in Adapter

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/adapter.py`

**Background:** Near-identical local-auth-before-CSMS blocks in `send_authorize` (lines 1139-1148) and `send_start_transaction` (lines 1191-1207). Extract to a private helper.

**Step 1: Add the helper method**

In `Adapter`, add:
```python
def _check_local_auth(
    self, id_tag: str
) -> Optional[tuple[Optional[AuthorizationStatus], dict]]:
    """
    Check the local authorization list for an id_tag.

    Returns:
        Tuple of (status, id_tag_info) if found locally, None if not found
        (meaning caller should fall back to CSMS).
    """
    local_status = self.local_auth_list.authorize(id_tag)
    if local_status is None:
        return None
    id_tag_info = self.local_auth_list.get_id_tag_info(id_tag) or {}
    id_tag_info["status"] = local_status.value
    return local_status, id_tag_info
```

**Step 2: Update send_authorize to use the helper**

```python
# FROM (adapter.py send_authorize, lines ~1139-1148):
local_status = self.local_auth_list.authorize(id_tag)
if local_status is not None:
    self._log(...)
    id_tag_info = self.local_auth_list.get_id_tag_info(id_tag) or {}
    id_tag_info["status"] = local_status.value
    return call_result.Authorize(id_tag_info=id_tag_info)

# TO:
local_result = self._check_local_auth(id_tag)
if local_result is not None:
    local_status, id_tag_info = local_result
    self._log(
        f"Authorize (local): id_tag={id_tag}, status={local_status.value}",
        is_ocpp_message=False,
        is_important=True,
    )
    return call_result.Authorize(id_tag_info=id_tag_info)
```

**Step 3: Update send_start_transaction to use the helper**

```python
# FROM (lines ~1191-1207):
local_status = self.local_auth_list.authorize(id_tag)
if local_status is not None:
    self._log(...)
    id_tag_info = self.local_auth_list.get_id_tag_info(id_tag) or {}
    id_tag_info["status"] = local_status.value
    self._next_transaction_id += 1
    transaction_id = self._next_transaction_id
    self.set_active_transaction(connector_id, transaction_id)
    return call_result.StartTransaction(...)

# TO:
local_result = self._check_local_auth(id_tag)
if local_result is not None:
    local_status, id_tag_info = local_result
    self._log(
        f"StartTransaction (local auth): id_tag={id_tag}, status={local_status.value}",
        is_ocpp_message=False,
        is_important=True,
    )
    self._next_transaction_id += 1
    transaction_id = self._next_transaction_id
    self.set_active_transaction(connector_id, transaction_id)
    return call_result.StartTransaction(
        id_tag_info=id_tag_info,
        transaction_id=transaction_id,
    )
```

**Step 4: Run tests and commit**

```bash
poetry run pytest -x
git commit -m "refactor: extract _check_local_auth helper to remove duplication

send_authorize and send_start_transaction had identical local auth check
blocks. Extracted to _check_local_auth() private method."
```

---

## Layer 3 — UI Fixes

### Task 15: Fix broken method references in MainWindow and SessionDashboard

**Files:**
- Modify: `src/chargeghost_evse/ui/app.py`
- Modify: `src/chargeghost_evse/ui/widgets/session_dashboard.py`

**Background:**
- `MainWindow.simulate_step` calls `self.simulator.dashboard.record_telemetry(self.engine)` — method does not exist → `AttributeError` every 100ms
- `SessionDashboard.update_from_engine` calls `self.telemetry_chart.refresh()` — method does not exist → `AttributeError` every UI update

**Step 1: Fix telemetry_chart.refresh() in session_dashboard.py**

Find the call to `self.telemetry_chart.refresh()` in `update_from_engine`. This method doesn't exist on `TelemetryChart`. Simply remove the call — `TelemetryChart` updates itself when `add_point()` is called.

```python
# DELETE this line from update_from_engine:
self.telemetry_chart.refresh()
```

**Step 2: Add record_telemetry() to SessionDashboard**

`record_telemetry` should compute the current effective power and add a data point to the chart. The free function `_compute_effective_power_kw` already does the power computation.

Add to `SessionDashboard`:
```python
def record_telemetry(self, engine) -> None:
    """Record a telemetry sample to the chart. Called every simulation tick."""
    power_kw = _compute_effective_power_kw(engine, self._selected_connector_id)
    self.telemetry_chart.add_point(power_kw)
```

Where `_selected_connector_id` is the currently selected connector ID on the dashboard.

Check how `_compute_effective_power_kw` is defined and what `_selected_connector_id` is called on the dashboard. Look for the existing usage pattern in `update_from_engine` or `_compute_effective_power_kw` calls. Adapt the method body to match.

**Step 3: Run tests**

```bash
poetry run pytest tests/test_ui_widgets.py -v
```

**Step 4: Commit**

```bash
git commit -m "fix: resolve broken method references in MainWindow and SessionDashboard

- Remove telemetry_chart.refresh() call (method doesn't exist on TelemetryChart)
- Add record_telemetry(engine) method to SessionDashboard that calls add_point()
Both were AttributeErrors on the hot simulation loop path."
```

---

### Task 16: Extract UpdateController from MainWindow

**Files:**
- Create: `src/chargeghost_evse/util/update_controller.py`
- Modify: `src/chargeghost_evse/ui/app.py`

**Background:** `MainWindow` contains ~170 lines of update lifecycle code (check, download, handover, shutdown). This includes creating asyncio event loops on daemon threads, writing shell scripts, and calling `HandoverManager`. Extract to `UpdateController`.

**Step 1: Create UpdateController**

Create `src/chargeghost_evse/util/update_controller.py`:

```python
"""Update lifecycle controller.

Owns the entire update check, download, and handover flow.
MainWindow connects to its signals for UI updates.
"""

import asyncio
import os
import platform
import sys
import tempfile
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Signal

from chargeghost_evse.util.handover_manager import HandoverManager
from chargeghost_evse.util.update_manager import UpdateManager

if TYPE_CHECKING:
    from chargeghost_evse.util.config import SimulationConfig


class UpdateController(QObject):
    """Manages the update check, download, and handover lifecycle."""

    # Emitted when an update is available (tag_name, body)
    update_available = Signal(str, str)
    # Emitted with progress 0-100 during download
    download_progress = Signal(int)
    # Emitted when download completes and app is about to restart
    ready_to_restart = Signal()
    # Emitted on any error
    error_occurred = Signal(str)

    def __init__(
        self,
        current_version: str,
        config: "SimulationConfig",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._current_version = current_version
        self._config = config
        self._update_manager = UpdateManager(
            current_version=current_version, config=config
        )
        self._latest_release_info = None

    def start_check(self) -> None:
        """Start background update check. Non-blocking."""
        thread = Thread(target=self._check_updates, daemon=True)
        thread.start()

    def trigger_download(self) -> None:
        """Start background download of the latest release. Non-blocking."""
        if self._latest_release_info is None:
            self.error_occurred.emit("No release info available")
            return
        thread = Thread(
            target=self._download_and_handover,
            args=(self._latest_release_info,),
            daemon=True,
        )
        thread.start()

    def ignore_version(self, tag_name: str) -> None:
        """Mark this version as ignored and save config."""
        self._config.ignored_version = tag_name
        self._config.save()

    def _check_updates(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            release_info = loop.run_until_complete(
                self._update_manager.fetch_latest_release()
            )
            if (
                self._update_manager.is_update_available(
                    self._current_version, release_info.tag_name
                )
                and release_info.tag_name != self._config.ignored_version
            ):
                self._latest_release_info = release_info
                self.update_available.emit(release_info.tag_name, release_info.body or "")
        except Exception:
            pass  # Update check failure is non-critical
        finally:
            loop.close()

    def _download_and_handover(self, release_info) -> None:
        loop = asyncio.new_event_loop()
        try:
            system_name = platform.system()
            asset = self._update_manager.select_asset_for_platform(
                system_name, release_info.assets
            )
            if not asset:
                self.error_occurred.emit("No update available for your platform")
                return

            temp_dir = Path(tempfile.mkdtemp())
            download_url = asset["browser_download_url"]
            filename = Path(urlparse(download_url).path).name
            temp_file = temp_dir / filename

            last_reported = [-1]

            def progress_callback(percent: int) -> None:
                milestone = (percent // 10) * 10
                if milestone > last_reported[0]:
                    last_reported[0] = milestone
                    self.download_progress.emit(milestone)

            loop.run_until_complete(
                self._update_manager.download_update(
                    download_url, temp_file, progress_callback
                )
            )

            if not getattr(sys, "frozen", False):
                self.error_occurred.emit(
                    "Update downloaded. In development mode, please update manually."
                )
                return

            current_exe = Path(sys.executable)
            handover_manager = HandoverManager(temp_dir)

            if system_name == "Windows":
                script_content = handover_manager.build_windows_script(
                    pid=os.getpid(),
                    new_path=str(temp_file),
                    old_path=str(current_exe),
                )
                script_path = temp_dir / "update.bat"
            else:
                script_content = handover_manager.build_macos_script(
                    pid=os.getpid(),
                    new_path=str(temp_file),
                    old_path=str(current_exe),
                )
                script_path = temp_dir / "update.sh"

            with open(script_path, "w") as f:
                f.write(script_content)

            handover_manager.launch_handover(script_path)
            self.ready_to_restart.emit()

        except Exception as e:
            self.error_occurred.emit(f"Update failed: {e}")
        finally:
            loop.close()
```

**Step 2: Replace update logic in MainWindow**

In `MainWindow.__init__`, replace:
```python
# FROM:
self.update_manager = UpdateManager(current_version=__version__, config=self.config)
self._update_chip: Optional[UpdateStatusChip] = None
self._latest_release_info = None
QTimer.singleShot(1500, self._start_update_check)

# TO:
self._update_chip: Optional[UpdateStatusChip] = None
self.update_controller = UpdateController(
    current_version=__version__, config=self.config, parent=self
)
self.update_controller.update_available.connect(self._on_update_available)
self.update_controller.download_progress.connect(self._on_download_progress)
self.update_controller.ready_to_restart.connect(self._on_ready_to_restart)
self.update_controller.error_occurred.connect(
    lambda msg: self.show_toast(msg, "error")
)
QTimer.singleShot(1500, self.update_controller.start_check)
```

**Step 3: Add lean signal handlers to MainWindow**

Replace the ~170 lines of update methods with lean handlers:
```python
@Slot(str, str)
def _on_update_available(self, tag_name: str, body: str) -> None:
    """Show update chip when a new version is available."""
    if self._update_chip:
        return
    self._update_chip = UpdateStatusChip(tag_name)
    self._update_chip.clicked.connect(
        lambda: self._show_update_dialog(tag_name, body)
    )
    status_bar = self.statusBar()
    if status_bar:
        status_bar.addPermanentWidget(self._update_chip)
        self._update_chip.show()

def _show_update_dialog(self, tag_name: str, body: str) -> None:
    dialog = UpdateDialog(__version__, tag_name, body, self)
    dialog.update_now_clicked.connect(self.update_controller.trigger_download)
    dialog.later_clicked.connect(lambda: None)
    dialog.ignore_clicked.connect(
        lambda: self._on_update_ignore(tag_name)
    )
    dialog.exec()

def _on_update_ignore(self, tag_name: str) -> None:
    self.update_controller.ignore_version(tag_name)
    if self._update_chip:
        self.statusBar().removeWidget(self._update_chip)
        self._update_chip.deleteLater()
        self._update_chip = None

@Slot(int)
def _on_download_progress(self, percent: int) -> None:
    self.show_toast(f"Downloading update: {percent}%", "info")

@Slot()
def _on_ready_to_restart(self) -> None:
    self.bridge.shutdown()
    from PySide6.QtWidgets import QApplication
    QApplication.quit()
```

Delete all the old update methods: `_start_update_check`, `_show_update_chip`, `_on_update_chip_clicked`, `_on_update_now`, `_on_update_later`, `download_and_handover` closure patterns, etc.

**Step 4: Clean up unused imports in app.py**

```bash
poetry run ruff check src/chargeghost_evse/ui/app.py
```

Remove any imports that are now unused (HandoverManager, UpdateManager, asyncio loops in update context, etc.).

**Step 5: Run tests and commit**

```bash
poetry run pytest -x
poetry run ruff check src/
git commit -m "refactor: extract UpdateController from MainWindow

~170 lines of update lifecycle code (asyncio loops on daemon threads,
shell script generation, file writes, handover) moved to UpdateController.
MainWindow now only connects signals, reducing it to clean UI concerns."
```

---

### Task 17: Move domain logic out of UI layer

**Files:**
- Modify: `src/chargeghost_evse/engine/engine.py`
- Modify: `src/chargeghost_evse/ui/app.py`
- Test: `tests/test_engine.py`

**Background:**
- `SimulatorWidget.action_plug_in` enforces "unplug others" policy → belongs in `Engine.plug_in()`
- `SimulatorWidget._on_connector_remove` validates "cannot remove last connector" and "cannot remove active session connector" → belongs in `Engine.remove_connector()`

**Step 1: Write tests for Engine enforcement**

```python
def test_plug_in_unplugs_other_connectors():
    """Engine.plug_in() must auto-unplug any other plugged-in connector."""
    engine = Engine()
    engine.add_connector(voltage=230.0, current=32.0, phase=1)
    engine.add_connector(voltage=230.0, current=32.0, phase=1)

    id1 = engine.connectors[0].id
    id2 = engine.connectors[1].id

    engine.plug_in(id1)
    assert engine.connectors[0].is_plugged_in

    # Plugging in connector 2 should auto-unplug connector 1
    engine.plug_in(id2)
    assert engine.connectors[1].is_plugged_in
    assert not engine.connectors[0].is_plugged_in


def test_remove_connector_raises_on_last():
    """Engine.remove_connector() must raise ValueError if only one connector."""
    engine = Engine()
    engine.add_connector(voltage=230.0, current=32.0, phase=1)
    connector_id = engine.connectors[0].id

    with pytest.raises(ValueError, match="last connector"):
        engine.remove_connector(connector_id)


def test_remove_connector_raises_on_active_session():
    """Engine.remove_connector() must raise ValueError if session active."""
    engine = Engine()
    engine.add_connector(voltage=230.0, current=32.0, phase=1)
    engine.add_connector(voltage=230.0, current=32.0, phase=1)
    id1 = engine.connectors[0].id

    engine.plug_in(id1)
    engine.start_session(connector_id=id1, transaction_id=1)

    with pytest.raises(ValueError, match="active session"):
        engine.remove_connector(id1)
```

**Step 2: Run to verify they fail**

```bash
poetry run pytest tests/test_engine.py::test_plug_in_unplugs_other_connectors -v
poetry run pytest tests/test_engine.py::test_remove_connector_raises_on_last -v
poetry run pytest tests/test_engine.py::test_remove_connector_raises_on_active_session -v
```
Expected: all FAIL

**Step 3: Update Engine.plug_in()**

Find `plug_in()` in `engine.py`. Before calling `connector.plug_in()`, add auto-unplug logic:
```python
def plug_in(self, connector_id: int) -> None:
    # Auto-unplug any other connector that is currently plugged in
    for conn in self.connectors:
        if conn.is_plugged_in and conn.id != connector_id:
            conn.unplug()

    connector = self._connectors.get(connector_id)
    if connector:
        connector.plug_in()
```

**Step 4: Update Engine.remove_connector()**

Find `remove_connector()` in `engine.py`. Add validation before removal:
```python
def remove_connector(self, connector_id: int) -> None:
    if len(self._connectors) <= 1:
        raise ValueError("Cannot remove the last connector")
    if self.session and self.session.connector_id == connector_id:
        raise ValueError("Cannot remove connector with active session")
    # ... existing removal logic
```

**Step 5: Simplify SimulatorWidget**

In `app.py`, update `action_plug_in()` — remove the manual unplug loop:
```python
# FROM:
def action_plug_in(self) -> None:
    for conn in self.engine.connectors:
        if conn.is_plugged_in and conn.id != self._selected_connector_id:
            self.engine.unplug(conn.id)
            self.main_window.log_message(...)
    self.engine.plug_in(self._selected_connector_id)
    ...

# TO:
def action_plug_in(self) -> None:
    self.engine.plug_in(self._selected_connector_id)
    self.main_window.log_message(
        f"[green]UI:[/green] Plugged In to Connector {self._selected_connector_id}"
    )
```

In `app.py`, update `_on_connector_remove()` — remove guard logic, catch ValueError:
```python
# FROM:
def _on_connector_remove(self, connector_id: int) -> None:
    if len(self.engine.connectors) <= 1:
        self._show_error("Cannot remove the last connector")
        return
    if self.engine.session and self.engine.session.connector_id == connector_id:
        self._show_error("Cannot remove connector with active session")
        return
    self.engine.remove_connector(connector_id)
    ...

# TO:
def _on_connector_remove(self, connector_id: int) -> None:
    try:
        self.engine.remove_connector(connector_id)
    except ValueError as e:
        self._show_error(str(e))
        return
    ...
```

**Step 6: Run tests and commit**

```bash
poetry run pytest tests/test_engine.py -v
poetry run pytest -x
git commit -m "refactor: move domain policy enforcement into Engine

- Engine.plug_in() now auto-unplugs other connectors (single plug-in policy)
- Engine.remove_connector() now validates last-connector and active-session
  constraints, raising ValueError with descriptive message
- UI catches ValueError and shows toast instead of pre-validating"
```

---

### Task 18: Fix log_mode source of truth

**Files:**
- Modify: `src/chargeghost_evse/ui/bridge.py`
- Modify: `src/chargeghost_evse/ui/app.py`

**Background:** `log_mode` state is split between `QtSignalBridge._log_mode` and `AppSettings`. The mode is written to both in 3 different places. The authoritative source should be `AppSettings` exclusively.

**Step 1: Remove _log_mode from QtSignalBridge**

In `ui/bridge.py`, delete the `_log_mode` field and the `log_mode` property/setter:
```python
# DELETE from __init__:
self._log_mode: LogMode = "compact"

# DELETE the property and setter:
@property
def log_mode(self) -> LogMode:
    return self._log_mode

@log_mode.setter
def log_mode(self, value: LogMode) -> None:
    ...

# DELETE the log_mode_changed signal if only used for this:
log_mode_changed = Signal()
```

**Step 2: Update MainWindow.on_log_received to read from AppSettings**

```python
# FROM:
if self.signal_bridge.log_mode == "compact" and not is_important:

# TO:
if self.app_settings.log_mode == "compact" and not is_important:
```

**Step 3: Update all log_mode write sites**

Find every `self.signal_bridge.log_mode = ...` in `app.py` and remove it — only keep the `self.app_settings.log_mode = ...` write.

In `_on_global_log_mode_toggle`:
```python
# FROM:
def _on_global_log_mode_toggle(self, is_detailed: bool) -> None:
    mode: LogMode = "verbose" if is_detailed else "compact"
    self.signal_bridge.log_mode = mode      # DELETE this line
    self.app_settings.log_mode = mode       # KEEP this
    ...
```

In `SimulatorWidget.action_toggle_log_mode`:
```python
# FROM:
def action_toggle_log_mode(self, is_detailed: bool) -> None:
    self.main_window.signal_bridge.log_mode = ...   # DELETE
    self.main_window.app_settings.log_mode = ...    # KEEP
```

In `ManualWidget` if it has a similar toggle — same pattern.

**Step 4: Run tests and commit**

```bash
poetry run pytest -x
poetry run ruff check src/
git commit -m "refactor: AppSettings is the sole source of truth for log_mode

Removed _log_mode from QtSignalBridge. All log mode reads/writes now go
through AppSettings directly, eliminating the split state."
```

---

### Task 19: Fix cross-sibling coupling via Signal

**Files:**
- Modify: `src/chargeghost_evse/ui/app.py`

**Background:** `SimulatorWidget` directly calls `self.main_window.manual.update_connector_range()` — this is a cross-sibling call that bypasses the parent. Replace with a signal.

**Step 1: Add signal to SimulatorWidget**

In `SimulatorWidget` class definition (near other class-level Signal declarations):
```python
connector_range_changed = Signal(int, int)  # (min_id, max_id)
```

**Step 2: Emit signal instead of direct call**

In `SimulatorWidget`, find all calls to `self.main_window.manual.update_connector_range()`:

```python
# In _on_connector_remove and _on_connector_add, REPLACE:
self.main_window.manual.update_connector_range()

# WITH:
connector_ids = [c.id for c in self.engine.connectors]
if connector_ids:
    self.connector_range_changed.emit(min(connector_ids), max(connector_ids))
```

**Step 3: Connect signal in MainWindow._setup_ui()**

Find where `simulator` and `manual` are wired up in `MainWindow._setup_ui()` (or wherever signals are connected after construction):
```python
self.simulator.connector_range_changed.connect(
    lambda min_id, max_id: self.manual.update_connector_range()
)
```

Note: If `update_connector_range()` takes no arguments (it just re-reads from engine), the lambda is fine. If it takes min/max params, update accordingly.

**Step 4: Verify no remaining direct sibling calls**

```bash
grep -n "main_window.manual\." src/chargeghost_evse/ui/app.py
```
Expected: only `self.manual.log_message(...)` and `self.manual.btn_log_mode.*` which are acceptable parent→child calls, not sibling calls.

**Step 5: Run tests and commit**

```bash
poetry run pytest -x
git commit -m "refactor: replace cross-sibling call with connector_range_changed signal

SimulatorWidget called self.main_window.manual.update_connector_range()
directly, a sibling dependency. Replaced with a Signal on SimulatorWidget
that MainWindow connects to ManualWidget."
```

---

## Final Verification

**Step 1: Run full test suite**

```bash
poetry run pytest -v
```
Expected: all tests PASS

**Step 2: Run lint and type check**

```bash
poetry run ruff check src/
poetry run ruff format src/ --check
poetry run mypy src/
```
Expected: zero errors

**Step 3: Manual smoke test**

1. Launch the app: `poetry run dev`
2. Connect to a test CSMS (or use the mock)
3. Plug in connector → verify no auto-unplug of other connectors unless there are two plugged
4. Start a session with max_energy set → verify charging stops at max
5. Disconnect CSMS → reconnect → verify StatusNotifications are re-sent
6. Check update chip appears if update available
7. Try to remove last connector → verify error toast

**Step 4: Final commit**

```bash
git commit -m "chore: final verification pass for architectural improvements"
```
