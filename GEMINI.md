# ChargeGhost EVSE - Gemini Context

This document provides essential context and instructions for Gemini CLI when working on the **ChargeGhost EVSE** project.

## Project Overview

**ChargeGhost EVSE** is a professional, Python-based Electric Vehicle Supply Equipment (EVSE) simulator. It features a modern graphical user interface built with **PySide6 (Qt)** and communicates with Central Systems (CSMS) using the **OCPP 1.6J** protocol.

### Core Architecture
The project follows a decoupled, event-driven architecture:
- **Simulation Core (`src/chargeghost_evse/engine/`)**: Manages the domain logic (Engine, Connector, Session, EnergyMeter). It uses a custom `Event` system for internal communication.
- **OCPP Adapter (`src/chargeghost_evse/ocpp_adapter/`)**: Handles asynchronous network I/O and OCPP message routing in a dedicated background thread.
- **Bridge Layer (`src/chargeghost_evse/bridge/`)**: Orchestrates thread-safe communication between the Simulation Core and the OCPP Adapter using Qt Signals/Slots and domain events.
- **UI Layer (`src/chargeghost_evse/ui/`)**: A PySide6-based interface for monitoring and manual control.
- **Utilities (`src/chargeghost_evse/util/`)**: Shared logic for events, subscribers, configuration, and update management.

## Tech Stack
- **Language**: Python >=3.11, <3.15
- **GUI Framework**: PySide6 (Qt 6.8+)
- **OCPP Library**: `ocpp` (v2.1+)
- **Async I/O**: `asyncio`, `websockets`, `aiohttp`
- **Build Tool**: Poetry
- **Testing**: pytest, pytest-asyncio, pytest-qt
- **Linting/Formatting**: ruff, mypy

## Codebase Exploration
For all research and exploration tasks, **always use the Qdrant-powered search tools** (`search_code`, `index_codebase`, `contextual_search`, etc.) when applicable. This ensures high-signal discovery of patterns, implementations, and dependencies across the codebase and git history.

## Key Commands

### Development Setup
```bash
poetry install
```

### Running the Application
```bash
poetry run dev
# OR
PYTHONPATH=src python3 -m chargeghost_evse.main
```

### Testing
```bash
poetry run pytest                              # Run all tests
poetry run pytest tests/test_engine.py         # Run specific test file
poetry run pytest -k "test_name"               # Run specific test case
```

### Quality Control
```bash
poetry run ruff check src/     # Linting
poetry run ruff format src/    # Formatting
poetry run mypy src/           # Type checking
```

### Building Standalone Binaries
```bash
poetry run build               # Uses PyInstaller (config in src/chargeghost_evse/build_tools/)
```

## Development Conventions

### Coding Style (Mandatory)
- **Indentation**: Use **Tabs**.
- **Line Length**: Max 100 characters.
- **Naming**: 
    - Classes: `PascalCase`
    - Functions/Methods: `snake_case`
    - Private members: `_prefix`
- **Type Hints**: Mandatory for all function parameters and return types. Use `Optional[T]` instead of `T | None`.
- **Events**: Use the internal `Event` class. Define as instance attributes and emit with keyword arguments.
- **Logging**: Use the internal `_log` method which emits to an `on_log` event.

### Threading and I/O
- The **OCPP Adapter** runs in a daemon thread with its own `asyncio` loop.
- **Qt UI** operations MUST remain on the main thread. Use the `Bridge` or Qt Signals for cross-thread communication.
- Use `asyncio.run_coroutine_threadsafe` when interacting with the OCPP loop from other threads.

### Configuration
- Configuration is managed via the `SimulationConfig` dataclass and persisted in `~/.chargeghost/config.json`.

## Documentation
- `README.md`: General overview and user manual.
- `AGENTS.md`: Detailed coding guidelines for AI agents.
- `OCPP_IMPLEMENTATION_PLAN.md`: Canonical roadmap for remaining OCPP 1.6J implementation and compliance work.
- `docs/plans/`: Architectural and feature design documents.
