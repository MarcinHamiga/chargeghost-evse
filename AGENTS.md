# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
poetry install

# Run
poetry run dev
PYTHONPATH=src python3 -m chargeghost_evse.main   # from source without installing

# Tests
poetry run pytest                                                              # all tests
poetry run pytest tests/test_engine.py                                        # single file
poetry run pytest tests/test_engine.py::TestEngine::test_session_start -v    # single test
poetry run pytest -x                                                          # stop on first failure

# Lint / type check
poetry run ruff check src/
poetry run ruff check src/ --fix
poetry run ruff format src/
poetry run mypy src/

# Build standalone binary
poetry run build
```

## Architecture

ChargeGhost is a PySide6 EVSE simulator that speaks OCPP 1.6 over WebSocket. Four layers:

```
UI (PySide6)  →  QtSignalBridge (ui/bridge.py)  →  Engine + Bridge  →  OCPP Adapter
```

**Engine** (`engine/engine.py`) — domain logic only. Manages `Connector` objects (1-indexed IDs), a single active `Session`, a global `EnergyMeter`, and a `command_queue` shared with the OCPP adapter. Exposes `session_started`, `session_stopped`, `connector_status_changed` events. Has an injectable `get_limit` callback that the Bridge hooks up to `ChargingProfileManager` once connected. Supports EV-side charging suspension (`suspend_ev`) and resume (`resume_charging`), which pause/resume energy accumulation without ending the session.

**Bridge** (`bridge/bridge.py`) — two classes:
- `AsyncRunner`: Owns the background daemon thread and its dedicated `asyncio` event loop. Handles WebSocket connection lifecycle with exponential-backoff reconnect, heartbeat loop, and exposes `adapter`.
- `Bridge`: Subscribes to Engine events and dispatches OCPP calls cross-thread via `asyncio.run_coroutine_threadsafe`. Also runs a meter-values polling loop.

**OCPP Adapter** (`ocpp_adapter/adapter.py`) — extends `ocpp.v16.ChargePoint`. Handles all inbound OCPP message handlers (`@on(...)`) and outbound sends. Owns `ConfigurationKeyManager`, `LocalAuthListManager`, `FirmwareManager`, and `ChargingProfileManager`.

**UI** (`ui/`) — `app.py` holds the main window. `ui/bridge.py` (`QtSignalBridge`) translates domain events into Qt signals so the UI always runs on the main thread. Widgets live in `ui/widgets/`: `ChargingProfilesPanel` displays active profiles, `UpdateDialog`/`UpdateStatusChip` handle update UI, `icons.py` provides SVG icons. QSS styles in `ui/styles/e_mobility.qss`.

**Util** (`util/`) — `Event` (thread-safe, weak-reference observer), `Subscriber` (mixin for auto-cleanup), `SimulationConfig` (dataclass, persisted to `~/.chargeghost/config.json`, password stored in system keyring). `UpdateManager` checks GitHub releases for updates; `HandoverManager` handles app replacement during updates (used by standalone binary builds).

## Code Conventions

- **Indentation**: tabs (not spaces).
- **Line length**: 100 characters max.
- **Type hints**: always use them. `Optional[T]` not `T | None`. `list[T]`/`dict[K,V]` (not `List`/`Dict`).
- **Imports**: stdlib → third-party → local, each group alphabetically, blank lines between. Use `TYPE_CHECKING` block for circular imports.
- **Logging**: classes use Python `logging` module with named loggers under the `chargeghost` namespace (e.g., `logging.getLogger("chargeghost.engine")`). The `_log()` wrapper standardizes the `source` extra field. Log levels: ERROR (failures), WARNING (rejected/retry), INFO (lifecycle/state changes — shown in shallow mode), DEBUG (payloads/traces — shown in deep mode). Rich markup in messages is supported for UI rendering and stripped for file output. File logs: `~/.chargeghost/logs/chargeghost.log` (rotating JSON).
- **OCPP connector IDs**: 1-indexed in OCPP protocol; internal `Connector.id` matches (also 1-indexed).
- **Threading**: all Qt UI operations must occur on the main thread. Cross-thread OCPP calls use `asyncio.run_coroutine_threadsafe`.
- **QSS**: `opacity` property is **not** supported in PySide6 QSS — use `rgba()` for transparency in `:disabled` states instead.
- **Config**: use `SimulationConfig.load()` / `config.save()`; `ocpp_password` is not written to JSON, only to the system keyring.
- **ChargingProfileManager**: thread-safe via `RLock`; inject into Engine via `get_limit` callback from Bridge.
- **Update system**: `UpdateManager` runs GitHub API checks off-main-thread; `HandoverManager` handles atomic app replacement for standalone binaries.

## Codebase Search

Use `Grep` and `Glob` tools for code search. For broad conceptual exploration, use the `Explore` subagent.

## Key Constraints

- Single active transaction at a time (mirrors real hardware).
- OCPP 1.6J only.
- Smart Charging is fully implemented via `ChargingProfileManager`: supports `SetChargingProfile`, `ClearChargingProfile`, `GetCompositeSchedule` with `ChargePointMaxProfile`, `TxDefaultProfile`, `TxProfile` purposes and `Absolute`, `Recurring`, `Relative` kinds. Composite limits are calculated with stack level resolution.
- Hardware limits: Voltage 120–1000V, Current 6–150A (defined in `util/config.py`).
- `pyyaml` and `pydantic`/`pydantic-settings` are listed as dependencies but not used in application logic (config uses plain `dataclasses` + `json`).
