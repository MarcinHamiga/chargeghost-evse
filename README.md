# ChargeGhost EVSE

<p align="center">
  <img src="assets/ChargeGhost.png" alt="ChargeGhost Logo" width="200">
</p>

A professional, Python-based Electric Vehicle Supply Equipment (EVSE) simulator featuring a modern graphical user interface built with PySide6 (Qt). ChargeGhost simulates complex EV charging sessions and communicates with Central Systems (CSMS) via the OCPP 1.6 protocol over WebSocket.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [User Manual](#user-manual)
  - [Simulator Mode](#simulator-mode)
  - [Manual Mode](#manual-mode)
  - [Configuration](#configuration)
- [Architecture](#architecture)
- [OCPP 1.6 Support](#ocpp-16-support)
- [Development](#development)
- [Building](#building)
- [License](#license)

## Features

- **Full OCPP 1.6J Support**: Robust CSMS communication including Core, Firmware Management, and Local Auth List profiles.
- **Modern Qt GUI**: Sleek, high-performance interface with dark theme and interactive elements.
- **Dual Operational Modes**:
  - **Simulator**: Full autonomous domain logic simulation with realistic charging curves.
  - **Manual**: Direct protocol interaction for debugging and testing CSMS implementations.
- **Multi-Connector Support**: Simulate stations with multiple independent connectors, each with its own configuration.
- **Live Metrics Dashboard**: Real-time tracking of energy (Wh), Power (kW), Voltage (V), Current (A), and State of Charge (SoC).
- **OCPP Config Key Management**: Built-in editor for mandatory, optional, and read-only OCPP configuration keys.
- **Firmware Management**: Simulated firmware updates and diagnostics upload with full status reporting.
- **Local Authorization**: Support for local authorization lists with full and differential update capabilities.
- **Resilient Connectivity**: Automatic reconnection with exponential backoff and periodic heartbeat/meter values.

## Requirements

- **Python**: >=3.11, <3.15
- **OS**: Windows, macOS, or Linux
- **Network**: Access to an OCPP 1.6 WebSocket endpoint (e.g., Steve, MaEVe, or a custom CSMS).

## Installation

### Using Poetry (Development purposes only)

```bash
git clone https://github.com/your-repo/chargeghost-evse.git
cd chargeghost-evse
poetry install
```
### MacOS
1. Download the .zip file labled as a MacOS release
2. Unzip the file
3. Move the .application file to the Applications directory
4. Run the app
5. Close the Gatekeeper popup
6. Go to Settings -> Gatekeeper -> Open anyway
7. Click on Open Anyway
8. ChargeGhost is installed
   
### From Source (pip)

```bash
pip install -e .
```

## Quick Start

1. Start the application:
   ```bash
   poetry run chargeghost-evse
   ```
2. Select **Simulator Mode**.
3. Go to the **Settings** tab and enter your CSMS WebSocket URL (e.g., `ws://localhost:8080/steve/websocket/CentralSystemService/CP_1`).
4. Click **Save General Config**.
5. Switch back to the **Dashboard** tab.
6. Enter an **ID Tag** (e.g., `DEADBEEF`) and click **Apply**.
7. Click **Plug In**, then **Start Charging**.

## User Manual

### Simulator Mode

Simulator Mode provides a high-fidelity EVSE simulation where the engine manages state transitions, energy metering, and protocol responses automatically.

#### Interaction Panels

- **Connector Strip**: Located at the top of the dashboard. Click on connector icons (C1, C2, etc.) to switch focus between physical connectors.
- **Session Controls**: Interactive buttons for simulation actions (Plug In, Start, Stop, Unplug).
- **ID Tag Entry**: Field to specify the RFID tag used for authorization.
- **Session Dashboard**: Real-time visualization of the active transaction and electrical metrics.
- **Collapsible Activity Log**: Expandable log at the bottom showing detailed Engine and OCPP events. Toggle between **Detailed** and **Compact** modes.

#### Typical Charging Workflow

1. **Setup**: Select a connector and apply an `ID Tag`.
2. **Plug In**: The connector transitions to `Preparing`.
3. **Authorize/Start**: Click `Start Charging`. The simulator sends `Authorize` and `StartTransaction`.
4. **Charging**: The connector enters `Charging` state. Meter values are periodically sent to the CSMS.
5. **Stop**: Click `Stop Charging`. The simulator sends `StopTransaction`.
6. **Unplug**: Return the connector to `Available`.

### Manual Mode

Manual Mode bypasses the simulation engine, allowing you to send raw OCPP messages directly. This is ideal for testing CSMS behavior in edge cases or during initial development.

- **OCPP Controls**: Buttons for `BootNotification`, `Heartbeat`, `StatusNotification`, `Start`, and `Stop`.
- **Protocol Log**: Dedicated area to view raw message exchange and server responses.

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
- **Voltage**: 100V - 480V
- **Current Limit**: 6A - 63A
- **Phases**: 1 or 3 Phase simulation.

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
│  (Engine, Connector, Session, EnergyMeter, LocalAuthList)   │
└───────────┬─────────────────────────────────────┬───────────┘
            │                                     │
┌───────────▼─────────────────────────────────────▼───────────┐
│                       OCPP Adapter                          │
│  (AsyncRunner, Message Handlers, ConfigurationKeyManager)   │
└─────────────────────────────────────────────────────────────┘
```

- **Engine**: The heart of the simulation; manages state machines and hardware constraints.
- **OCPP Adapter**: Runs in a dedicated background thread to handle asynchronous network I/O without blocking the UI.
- **LocalAuthList**: Handles offline authorization and CSMS list synchronization.

## OCPP 1.6 Support

| Profile | Status | Implemented Messages |
| :--- | :--- | :--- |
| **Core** | Partial | `BootNotification`, `Heartbeat`, `Authorize`, `StartTransaction`, `StopTransaction`, `StatusNotification`, `ChangeConfiguration`, `GetConfiguration` |
| **Firmware** | Full | `GetDiagnostics`, `DiagnosticsStatusNotification`, `UpdateFirmware`, `FirmwareStatusNotification` |
| **Local Auth** | Full | `SendLocalList`, `GetLocalListVersion` |
| **Smart Charging** | Missing | - |

For a detailed roadmap and missing features, see [OCPP_MISSING_FEATURES.md](OCPP_MISSING_FEATURES.md).

## Development

### Testing

Run the comprehensive test suite:
```bash
poetry run pytest
```

### Linting & Formatting

```bash
poetry run ruff check .
poetry run ruff format .
poetry run mypy src/
```

## Building

Generate standalone executables for your platform using PyInstaller:

```bash
poetry run build
```

## License

Licensed under the **GNU Affero General Public License v3 (AGPLv3)**. See [LICENSE](LICENSE) for full details.
