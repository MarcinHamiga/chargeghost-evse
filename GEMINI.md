# ChargeGhost EVSE

## Project Overview
ChargeGhost EVSE is a Python-based Electric Vehicle Supply Equipment (EVSE) simulator. It simulates the internal logic of a charging station, communicate with a Central System via OCPP 1.6, and provide a graphical user interface (GUI) using PySide6.

## Architecture
The project is organized as a Poetry-managed Python package in `src/chargeghost_evse/`. It is designed to simulate a single-session EVSE, reflecting real-world hardware constraints and OCPP 1.6 standards where only one transaction is active at a time.

### Key Components
- **`engine/`**: Core simulation domain logic.
    - **`Engine`**: Orchestrates the simulator, managing connectors and the active session.
    - **`Connector`**: Models a physical charging connector.
    - **`Session`**: Tracks the active charging transaction data.
    - **`EnergyMeter`**: A global meter simulating power usage for the EVSE.
- **`ocpp_adapter/`**: Handles OCPP 1.6 communication using `websockets`.
- **`ui/`**: PySide6-based GUI with custom widgets and QSS styling.
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

### Running the Application
```bash
poetry run python src/chargeghost_evse/main.py
```

## Development Conventions

- **Code Style:** Standard Python conventions with type hints.
- **Event-Driven:** Components communicate via a custom `Event` class (`subscribe`/`emit`) rather than direct coupling where possible.
- **UI Styling (QSS):** The `opacity` property is **NOT** supported in PySide6 QSS. Use `rgba()` for transparency in colors (e.g., in `:disabled` states).
- **Configuration:** Project dependencies and metadata are managed in `pyproject.toml`.

## Current State & Known Issues
- **UI:** The TUI (Textual) mentioned in early versions has been replaced by a PySide6 GUI.
- **Dependencies:** `pydantic`, `pydantic-settings`, and `pyyaml` are listed in `pyproject.toml` but are not yet imported or used in the codebase.
- **Bugs:** None identified at the moment.
