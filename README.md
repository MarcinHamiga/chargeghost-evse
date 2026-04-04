# ChargeGhost EVSE

<p align="center">
  <img src="assets/ChargeGhost.png" alt="ChargeGhost Logo" width="200">
</p>

**Version v0.8.1** | A professional, Python-based Electric Vehicle Supply Equipment (EVSE) simulator featuring a modern graphical user interface built with PySide6 (Qt). ChargeGhost simulates complex EV charging sessions and communicates with Central Systems (CSMS) via the OCPP 1.6 and OCPP 2.0.1 protocols over WebSocket.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [User Manual](#user-manual)
  - [Simulator Mode](#simulator-mode)
  - [Manual Mode](#manual-mode)
  - [Headless API Mode](#headless-api-mode)
  - [Configuration](#configuration)
- [Architecture](#architecture)
- [OCPP Support](#ocpp-support)
- [Development](#development)
- [Building](#building)
- [License](#license)

> **⚠️ Deprecation Notice**: The integrated PySide6 GUI is deprecated and will be removed in v1.0. Use the [Headless API Mode](#headless-api-mode) for all new workflows. The GUI remains functional in v0.x but will not receive new features.

## Features

- **Comprehensive OCPP 1.6J & 2.0.1 Support**: Robust CSMS communication across Core, FirmwareManagement, LocalAuthListManagement, Reservation, RemoteTrigger, and SmartCharging profiles.
- **Modern Qt GUI** *(deprecated)*: Sleek, high-performance interface with dark theme and interactive elements. Will be removed in v1.0.
- **Dual Operational Modes**:
  - **Simulator**: Full autonomous domain logic simulation with realistic charging curves.
  - **Manual**: Direct protocol interaction for debugging and testing CSMS implementations.
- **Headless API Server**: FastAPI-based REST API for CI/CD integration, automated testing, and external tooling. Exposes simulator control, session management, OCPP raw endpoints, and timeline introspection.
- **Multi-EVSE Simulation**: Simulate multiple EVSEs with parallel charging sessions on independent connectors.
- **Scenario Runner**: Define and execute test scenarios with actions (plug_in, start_charging, etc.), wait conditions (connector_status, meter_threshold), and assertions for automated testing.
- **Fault Injection**: Inject faults (overcurrent, undervoltage, ground fault, etc.) to test CSMS error handling.
- **Live Metrics Dashboard**: Real-time tracking of energy (Wh), Power (kW), Voltage (V), Current (A), and State of Charge (SoC) with a rolling window telemetry chart for visualizing power trends. Configurable EV battery capacity.
- **OCPP Config Key Management**: Built-in editor for mandatory, optional, and read-only OCPP configuration keys.
- **Firmware Management**: Simulated firmware updates and diagnostics upload with full status reporting.
- **Local Authorization**: Support for local authorization lists with full and differential update capabilities.
- **Resilient Connectivity**: Automatic reconnection with exponential backoff and periodic heartbeat/meter values.
- **Smart Charging**: Full OCPP 1.6 Smart Charging profile support with charging profile management, composite schedule calculation, and real-time power limit visualization. Supports all profile purposes (ChargePointMaxProfile, TxDefaultProfile, TxProfile) and schedule kinds (Absolute, Recurring, Relative).
- **EV-Side Suspension**: Simulate EV-initiated charging suspension and resume, with proper energy meter pausing during suspended state.
- **Auto-Update System**: Automatic update checking from GitHub releases with platform-specific handling for Windows and macOS.

## Requirements

- **Python**: >=3.11, <3.15
- **OS**: Windows, macOS, or Linux
- **Network**: Access to an OCPP 1.6 WebSocket endpoint (e.g., Steve, MaEVe, or a custom CSMS).

## Installation

### Using Poetry (Development purposes only)

```bash
git clone https://github.com/MarcinHamiga/chargeghost-evse.git
cd chargeghost-evse
poetry install
```
### MacOS
1. Download the .zip file labeled as a MacOS release
2. Unzip the file
3. Move the .app file to the Applications directory
4. Run the app
5. Close the Gatekeeper popup
6. Go to Settings -> Privacy & Security -> Open Anyway
7. Click on Open Anyway
8. ChargeGhost is installed

### From Source (pip)

```bash
pip install -e .
```

## Quick Start

### GUI Mode

1. Start the application:
   ```bash
   poetry run dev
   ```
2. Select **Simulator Mode**.
3. Go to the **Settings** tab and enter your CSMS WebSocket URL (e.g., `ws://localhost:8080/steve/websocket/CentralSystemService/CP_1`).
4. Click **Save General Config**.
5. Switch back to the **Dashboard** tab.
6. Enter an **ID Tag** (e.g., `DEADBEEF`) and click **Apply**.
7. Click **Plug In**, then **Start Charging**.

### Headless API Mode

```bash
poetry run api
# Then control via HTTP:
curl -X POST http://localhost:8080/connectors/1/plug_in
curl -X POST http://localhost:8080/sessions/start -d '{"id_tag": "DEADBEEF"}'
```

## User Manual

### Simulator Mode

Simulator Mode provides a high-fidelity EVSE simulation where the engine manages state transitions, energy metering, and protocol responses automatically.

#### Interaction Panels

- **Connector Strip**: Located at the top of the dashboard. Click on connector icons (C1, C2, etc.) to switch focus between physical connectors.
- **Session Controls**: Interactive buttons for simulation actions (Plug In, Start, Stop, Unplug).
- **ID Tag Entry**: Field to specify the RFID tag used for authorization.
- **Session Dashboard**: Real-time visualization of the active transaction and electrical metrics in a two-column layout with telemetry chart and session controls.
- **Collapsible Activity Log**: Expandable log at the bottom showing detailed Engine and OCPP events. Toggle between **Detailed** and **Compact** modes.

#### Typical Charging Workflow

1. **Setup**: Select a connector and apply an `ID Tag`.
2. **Plug In**: The connector transitions to `Preparing`.
3. **Authorize/Start**: Click `Start Charging`. The simulator sends `Authorize` and `StartTransaction`.
4. **Charging**: The connector enters `Charging` state. Meter values are periodically sent to the CSMS.
5. **Suspend/Resume** *(optional)*: Click `Suspend EV` to simulate an EV-initiated pause (connector transitions to `SuspendedEV`). Click `Resume Charging` to continue.
6. **Stop**: Click `Stop Charging`. The simulator sends `StopTransaction`.
7. **Unplug**: Return the connector to `Available`.

### Manual Mode

Manual Mode bypasses the simulation engine, allowing you to send raw OCPP messages directly. This is ideal for testing CSMS behavior in edge cases or during initial development.

- **OCPP Controls**: Buttons for `BootNotification`, `Heartbeat`, `StatusNotification`, `Start`, and `Stop`.
- **Protocol Log**: Dedicated area to view raw message exchange and server responses.

### Headless API Mode

The headless API server provides a FastAPI-based REST interface for controlling the simulator without the GUI. Ideal for CI/CD pipelines, automated test suites, and external tooling integration.

Start the API server:
```bash
poetry run api
# Or with custom host/port:
poetry run api --host 0.0.0.0 --port 9000
```

Key API capabilities:
- **Simulator Control**: Plug in, start/stop charging, suspend/resume, authorize
- **Session Management**: Query and control active sessions
- **OCPP Raw Endpoints**: Send arbitrary OCPP messages and receive responses
- **Timeline Introspection**: Access message history with filtering and export
- **Charging Profiles**: View and manage active profiles
- **Fault Injection**: Enable/disable faults programmatically
- **Connectors**: Configure per-connector hardware limits

See `poetry run api --help` for server options.

### Configuration

Configuration is managed via the **Settings** tab in the UI and persisted to `~/.chargeghost/config.json`.

#### General & OCPP Settings

| Section | Description |
|---------|-------------|
| **Connection** | URL, Identity (Charge Point ID), and Auth credentials. |
| **Identity** | Vendor and Model strings reported in `BootNotification`. |
| **OCPP Keys** | Interactive editor for mandatory and optional OCPP 1.6 configuration keys. |

#### Connector Hardware

Each connector can be individually tuned:
- **Voltage**: 120V - 1000V
- **Current Limit**: 6A - 150A
- **Phases**: 1 or 3 Phase simulation.

#### Charging Profiles

The **Charging Profiles** panel displays active charging profiles received from the CSMS:

- **Profile List**: Shows all installed charging profiles with their stack level, purpose, and kind.
- **Composite Limit**: Displays the effective power/current limit after combining all applicable profiles.
- **Profile Purposes**: Supports ChargePointMaxProfile (station-wide), TxDefaultProfile (default for transactions), and TxProfile (transaction-specific).
- **Profile Kinds**: Handles Absolute (fixed schedule), Recurring (repeating schedule), and Relative (offset from transaction start) profiles.

## Architecture

ChargeGhost uses a decoupled, event-driven architecture to ensure UI responsiveness and simulation accuracy.

```text
┌─────────────────────────────────────────────────────────────┐
│                         UI Layer                            │
│    (PySide6 Qt: Dashboard, Settings, Manual, Log Widgets)   │
└─────────────────────────┬───────────────────────────────────┘
                          │ (Qt Signals / Slots)
┌─────────────────────────▼───────────────────────────────────┐
│                       Bridge Layer                          │
│  (QtSignalBridge: Thread-safe communication between layers) │
└─────────────────────────┬───────────────────────────────────┘
                          │ (Domain Events)
┌─────────────────────────▼───────────────────────────────────┐
│                     Simulation Core                         │
│  (Engine, Connector, Session, EnergyMeter, LocalAuthList,   │
│                    ChargingProfileManager)                  │
└───────────┬─────────────────────────────────────┬───────────┘
            │                                     │
┌───────────▼─────────────────────────────────────▼───────────┐
│                       OCPP Adapter                          │
│  (AsyncRunner, Message Handlers, ConfigurationKeyManager)  │
│                OCPP 1.6 Adapter  │  OCPP 2.0.1 Adapter      │
└─────────────────────────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────────────────┐
│                     Headless API Server                      │
│  (FastAPI: REST endpoints, WebSocket manager, timeline)     │
│              Scenario Runner │ Fault Injection              │
└─────────────────────────────────────────────────────────────┘
```

- **Engine**: The heart of the simulation; manages state machines and hardware constraints.
- **Bridge**: Orchestrates communication between the Engine and the OCPP Adapter.
- **OCPP Adapter**: Runs in a dedicated background thread to handle asynchronous network I/O without blocking the UI. Supports both OCPP 1.6J and OCPP 2.0.1.
- **LocalAuthList**: Handles offline authorization and CSMS list synchronization.
- **ChargingProfileManager**: Manages charging profiles, calculates composite schedules, and enforces power/current limits.
- **Headless API Server**: FastAPI-based REST API for programmatic simulator control, CI/CD integration, and automated testing.
- **Scenario Runner**: Executes predefined test scenarios with actions, wait conditions, and assertions.
- **Fault Manager**: Injects faults (overcurrent, undervoltage, ground fault, etc.) to test error handling.

## OCPP Support

### OCPP 1.6J - Implemented Profiles

| Profile | Status | Notes |
| :--- | :--- | :--- |
| **Core** | Full | All required messages implemented |
| **Firmware** | Full | Diagnostics and firmware update support |
| **Local Auth** | Full | Local authorization list with differential updates |
| **Smart Charging** | Full | All profile purposes and schedule kinds supported |
| **Reservation** | Full | ReserveNow and CancelReservation supported |
| **Remote Trigger** | Full | TriggerMessage for all supported message types |

### OCPP 2.0.1

Initial adapter support is available. Core messages and transaction handling are implemented.

## Development

### Testing

Run the comprehensive test suite:
```bash
poetry run pytest
```

### Linting & Formatting

```bash
poetry run ruff check src/
poetry run ruff check src/ --fix
poetry run ruff format src/
poetry run mypy src/
```

## Building

Generate standalone executables for your platform using PyInstaller:

```bash
poetry run build
```

## License

Licensed under the **GNU Affero General Public License v3 (AGPLv3)**. See [LICENSE](LICENSE) for full details.
