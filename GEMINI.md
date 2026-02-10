# ChargeGhost EVSE

## Project Overview
ChargeGhost EVSE is a Python-based Electric Vehicle Supply Equipment (EVSE) simulator. It intends to simulate the internal logic of a charging station, communicate with a Central System via OCPP 1.6, and provide a terminal-based user interface (TUI) using Textual.

## Architecture
The project is organized as a Poetry-managed Python package in `src/chargeghost_evse/`. It is designed to simulate a single-session EVSE, reflecting real-world hardware constraints and OCPP 1.6 standards where only one transaction is active at a time.

### Key Components
- **`engine/`**: Core simulation domain logic.
    - **`Engine`**: Orchestrates the simulator, managing connectors and the active session.
    - **`Connector`**: Models a physical charging connector.
    - **`Session`**: Tracks the active charging transaction data.
    - **`EnergyMeter`**: A global meter simulating power usage for the EVSE.
- **`ocpp_adapter/`**: Handles OCPP 1.6 communication using `websockets`.
- **`ui/`**: Intended for the Textual-based TUI (currently empty).
- **`util/`**: Shared utilities, specifically a custom `Event` class for observer-pattern communication.

## Building and Running

### Prerequisites
- Python 3.11 - 3.15
- Poetry (Package Manager)

### Setup
Install dependencies:
```bash
poetry install
```

### Running Components (Development)
The project does not yet have a single unified entry point. You can run individual components for testing:

**Run the Simulation Engine:**
```bash
poetry run python src/chargeghost_evse/engine/engine.py
```
*Note: The engine currently runs in an infinite loop without sleep.*

**Run the OCPP Adapter:**
```bash
poetry run python src/chargeghost_evse/ocpp_adapter/adapter.py
```
*Note: Defaults to connecting to `ws://localhost:3000/CP_1`.*

## Development Conventions

- **Code Style:** Standard Python conventions with type hints.
- **Event-Driven:** Components communicate via a custom `Event` class (`subscribe`/`emit`) rather than direct coupling where possible.
- **Configuration:** Project dependencies and metadata are managed in `pyproject.toml`.

## Current State & Known Issues
- **UI:** The `ui/` directory is currently empty despite the `textual` dependency.
- **Dependencies:** `pydantic`, `pydantic-settings`, and `pyyaml` are listed in `pyproject.toml` but are not yet imported or used in the codebase.
- **Bugs:** None identified at the moment.
