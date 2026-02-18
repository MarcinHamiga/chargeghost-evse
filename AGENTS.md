# AGENTS.md

Guidelines for AI coding agents working on the ChargeGhost EVSE codebase.

## Project Overview

ChargeGhost EVSE is a Python-based Electric Vehicle Supply Equipment (EVSE) simulator that communicates via OCPP 1.6 with a Central System. It uses PySide6 (Qt) for a graphical user interface.

## Build Commands

### Setup
```bash
poetry install
```

### Running the Application
```bash
chargeghost-evse                  # Installed command
PYTHONPATH=src python3 -m chargeghost_evse.main   # From source
```

### Testing
```bash
poetry run pytest                              # Run all tests
poetry run pytest tests/test_engine.py         # Run a single test file
poetry run pytest tests/test_engine.py::TestEngine::test_session_start -v  # Run single test
poetry run pytest -x                           # Stop on first failure
```

### Linting and Type Checking
```bash
poetry run mypy src/           # Type checking
poetry run ruff check src/     # Linting
poetry run ruff format src/    # Format
poetry run ruff check src/ --fix  # Auto-fix lint issues
```

## Project Structure

```
src/chargeghost_evse/
├── main.py              # Application entry point
├── engine/              # Core simulation (Engine, Connector, Session, EnergyMeter)
├── ocpp_adapter/        # OCPP 1.6 protocol handling (Adapter)
├── bridge/              # Connects engine to OCPP adapter (AsyncRunner, Bridge)
├── ui/                  # PySide6 Qt widgets and main window
└── util/                # Shared utilities (Event, Subscriber, config)
```

## Code Style Guidelines

### Python Version
- Requires Python >=3.11,<3.15
- Use modern Python features (type hints, dataclasses, match statements)

### Imports
Group imports in order: stdlib (alphabetical), third-party (alphabetical), local (alphabetical), with blank lines between groups.

```python
import asyncio
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from ocpp.routing import on
from ocpp.v16 import call, call_result

from chargeghost_evse.engine.session import Session
from chargeghost_evse.util.event import Event
```

### Type Annotations
- Always use type hints for function parameters and return types
- Use `Optional[T]` for optional parameters (not `T | None`)
- Use `list[T]`, `dict[K, V]` (not `List`, `Dict` from typing)
- Class instance variables should have type annotations

```python
def start_session(self, connector_id: int, transaction_id: int,
				  max_energy: float = 55000.0, id_tag: Optional[str] = None) -> None:
	...

self.connectors: list[Connector] = []
self.session: Optional[Session] = None
```

### Naming Conventions
- **Classes**: PascalCase (`Engine`, `AsyncRunner`)
- **Functions/Methods**: snake_case (`start_session`, `get_meter_reading`)
- **Private methods**: Prefix with underscore (`_log`, `_process_commands`)
- **Constants**: UPPER_SNAKE_CASE (`CONFIG_FILE`, `STYLES_PATH`)
- Use `TYPE_CHECKING` block for circular import type hints

### Formatting
- Use tabs for indentation
- Maximum line length: 100 characters

### Classes
- Inherit from `Subscriber` when subscribing to events
- Call `super().__init__()` in constructors
- Use `@property` decorators for computed attributes

### Event-Driven Architecture
- Use the `Event` class for observer-pattern communication
- Define events as instance attributes: `self.event_name: Event = Event()`
- Subscribe: `obj.subscribe(callback)` or `self.subscribe_to(event, callback)`
- Emit: `self.event_name.emit(param=value)`

### Logging
- Use internal `_log` method that emits to `on_log` event
- Prefix with context: `"[blue]OCPP:[/blue]"`, `"[yellow]Engine:[/yellow]"`

```python
def _log(self, message: str) -> None:
	self.on_log.emit(message=message)
```

### Error Handling
- Use specific exception types
- Handle `try/except` around external operations (WebSocket, file I/O)

```python
try:
	ocpp_connector_id = int(connector_id)
except (TypeError, ValueError):
	self._log(message=f"Invalid connector_id received: {connector_id}")
	return call_result.RemoteStartTransaction(status=RemoteStartStopStatus.rejected)
```

### Async Code
- Use `asyncio` for WebSocket/OCPP communication
- Run async from threads: `asyncio.run_coroutine_threadsafe(coro, loop)`
- Use `async with` for context managers

### Threading
- OCPP adapter runs in separate daemon thread
- Use `threading.Event` for shutdown signaling
- All Qt UI operations must occur on the main thread

### OCPP Patterns
- Use `@on("MessageName")` decorator for incoming message handlers
- Return appropriate `call_result.*` objects
- OCPP connector IDs are 1-indexed; internal indices are 0-indexed

```python
@on("RemoteStartTransaction")
async def on_remote_start_transaction(
	self, connector_id: Optional[int], id_tag: str, **kwargs
) -> call_result.RemoteStartTransaction:
	...
```

### UI & Styling
- **QSS**: Use `rgba()` for transparency (e.g., `background-color: rgba(30, 173, 152, 0.2);`).
- **Opacity**: The `opacity` property is **NOT** supported in PySide6 QSS. To achieve a faded look for disabled elements, explicitly set `rgba` values for `background-color`, `color`, and `border` in the `:disabled` pseudo-state.

### Configuration
- Use `SimulationConfig` dataclass for user configuration
- Config stored in `~/.chargeghost/config.json`
- Load with `SimulationConfig.load()`, save with `config.save()`

## Key Dependencies

- **PySide6**: Qt GUI framework (>=6.8.0)
- **ocpp**: OCPP protocol implementation (>=2.1.0)
- **websockets**: WebSocket client (>=16.0)
- **pydantic/pydantic-settings**: Configuration validation

## Important Notes

- Single-session EVSE: Only one transaction active at a time
- OCPP 1.6 protocol only
- The Bridge connects engine events to OCPP messages automatically
- WebSocket runs in a background daemon thread with its own asyncio event loop
