# ChargeGhost EVSE

A Python-based Electric Vehicle Supply Equipment (EVSE) simulator featuring a modern graphical user interface built with PySide6 (Qt). ChargeGhost simulates EV charging sessions and communicates with Central Systems via the OCPP 1.6 protocol over WebSocket.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [User Manual](#user-manual)
  - [Running the Application](#running-the-application)
  - [Simulator Mode](#simulator-mode)
  - [Manual Mode](#manual-mode)
  - [Configuration](#configuration)
- [Architecture](#architecture)
- [Development](#development)
  - [Project Structure](#project-structure)
  - [Testing](#testing)
  - [Linting and Type Checking](#linting-and-type-checking)
- [OCPP 1.6 Support](#ocpp-16-support)
- [Building](#building)
- [License](#license)

## Features

- Full OCPP 1.6 protocol support for CSMS communication
- Modern Qt-based graphical user interface with dark theme
- Two operational modes: Simulator and Manual
- Configurable connection parameters (URL, credentials, TLS)
- Automatic reconnection with exponential backoff
- Periodic heartbeat and meter values reporting
- Multi-connector support with per-connector configuration
- Real-time session metrics dashboard (energy, SoC, power, voltage, current)
- Activity log with detailed/compact view modes

## Requirements

- Python >=3.11, <3.15
- A CSMS (Central System Management System) with OCPP 1.6 WebSocket endpoint

## Installation

### From Source

```bash
git clone https://github.com/your-repo/chargeghost-evse.git
cd chargeghost-evse
poetry install
```

## User Manual

### Running the Application

After installation, start the application:

```bash
chargeghost-evse
```

Or run from source:

```bash
PYTHONPATH=src python3 -m chargeghost_evse.main
```

Upon launch, you are presented with a mode selection screen to choose between Simulator Mode and Manual Mode.

### Simulator Mode

The Simulator Mode provides an interactive EVSE simulation with realistic charging behavior and full OCPP integration.

#### Controls

| Button | Action | Description |
|--------|--------|-------------|
| Plug In | Connect EV | Simulates connecting an EV to the selected connector |
| Start/Stop Charging | Swipe Card | Starts or stops a charging session |
| Unplug | Disconnect EV | Simulates disconnecting the EV |

#### Tabs

- **Controls**: Primary simulation controls and connector status
- **Connectors**: Add, remove, and configure connector parameters (voltage, current, phases)
- **Config**: Connection settings, station identity, and TLS options
- **Session**: Real-time charging metrics dashboard

#### Typical Charging Session Workflow

1. **Plug In**: Connector transitions from `Available` to `Preparing`
2. **Start Charging**: Sends authorization and starts transaction with CSMS
3. **Charging**: Session runs, meter values are sent periodically
4. **Stop Charging**: Ends the transaction, connector transitions to `Finishing`
5. **Unplug**: Connector returns to `Available`

#### Connector States

| State | Description |
|-------|-------------|
| `Available` | Connector is free and ready |
| `Preparing` | EV is plugged in, awaiting authorization |
| `Charging` | Active charging session |
| `SuspendedEV` | EV paused charging (battery full) |
| `SuspendedEVSE` | EVSE paused charging |
| `Finishing` | Session ended, EV still plugged |
| `Unavailable` | Connector is disabled |
| `Faulted` | Connector has a fault |

#### Session Dashboard Metrics

- Transaction ID
- Session Duration
- Energy Charged (Wh)
- State of Charge (%)
- Current Power (kW)
- Total Meter Reading (Wh)
- Voltage (V)
- Current (A)

### Manual Mode

Manual Mode allows direct OCPP message control without simulation logic. Use this for testing specific CSMS interactions and protocol debugging.

#### Available Messages

| Button | OCPP Message | Description |
|--------|--------------|-------------|
| BootNotification | `BootNotification` | Registers the charge point with CSMS |
| Heartbeat | `Heartbeat` | Sends a heartbeat to maintain connection |
| StatusNotification | `StatusNotification` | Reports connector status |
| Start | `StartTransaction` | Starts a charging session (enter ID Tag) |
| Stop | `StopTransaction` | Stops the current transaction (enter TX ID) |

### Configuration

Configuration is stored in `~/.chargeghost/config.json` and can be edited via the Config tab in Simulator Mode.

| Setting | Description | Default |
|---------|-------------|---------|
| Connection URL | CSMS WebSocket endpoint | `wss://localhost:3000/CP_1` |
| OCPP ID | Charge point identifier | `CP_1` |
| OCPP Password | Basic auth password (optional) | (empty) |
| Charge Point Model | Device model name | `ChargeGhostV1` |
| Charge Point Vendor | Manufacturer name | `ChargeGhost` |
| Skip TLS Verification | Disable TLS certificate checks | `false` |

#### Connector Configuration

Each connector can be configured with:

| Parameter | Range | Default |
|-----------|-------|---------|
| Voltage | 100-480V | 230V |
| Current | 6-63A | 32A |
| Phases | 1-3 | 1 |

Configuration is automatically persisted when closing the application or when modifying connector settings.

## Architecture

ChargeGhost follows an event-driven architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                         UI Layer                            │
│  (PySide6 Qt - MainWindow, SimulatorWidget, ManualWidget)   │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                       Bridge Layer                          │
│  (QtSignalBridge - Thread-safe signal emission to Qt)       │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                       Bridge Core                           │
│  (Connects Engine events to OCPP messages via AsyncRunner)  │
└───────────┬─────────────────────────────────────┬───────────┘
            │                                     │
┌───────────▼───────────┐           ┌─────────────▼───────────┐
│    Engine (Core)      │           │    OCPP Adapter         │
│  - Session            │           │  - Message handlers     │
│  - Connector          │           │  - Message senders      │
│  - EnergyMeter        │           │  - WebSocket client     │
│  - Event system       │           │                         │
└───────────────────────┘           └─────────────────────────┘
```

### Key Components

- **Engine**: Core simulation logic handling sessions, connectors, and energy metering
- **OCPP Adapter**: Implements OCPP 1.6 protocol with incoming message handlers and outgoing message senders
- **Bridge**: Connects engine events to OCPP messages, runs async OCPP in a daemon thread
- **AsyncRunner**: Manages WebSocket connection with automatic reconnection and heartbeat loop
- **UI**: PySide6-based graphical interface with mode selection, controls, and real-time metrics

### Event System

The application uses an observer pattern for component communication:

- `Event`: Observable that emits to subscribers
- `Subscriber`: Base class providing subscribe/unsubscribe functionality
- Events: `session_started`, `session_stopped`, `connector_status_changed`, `on_log`, etc.

### Threading Model

- **Main Thread**: Qt UI event loop
- **OCPP Thread**: Daemon thread running asyncio event loop for WebSocket communication
- **Meter Values Thread**: Daemon thread for periodic meter value transmission

## Development

### Project Structure

```
src/chargeghost_evse/
├── main.py              # Application entry point
├── engine/
│   ├── engine.py        # Core simulation engine
│   ├── connector.py     # Connector state management
│   ├── session.py       # Charging session logic
│   └── energy_meter.py  # Energy consumption simulation
├── ocpp_adapter/
│   └── adapter.py       # OCPP 1.6 protocol implementation
├── bridge/
│   └── bridge.py        # Engine-to-OCPP connection (AsyncRunner, Bridge)
├── ui/
│   ├── app.py           # Qt main window and widgets
│   ├── bridge.py        # Qt signal bridge for thread-safe UI updates
│   ├── widgets/         # UI components
│   │   ├── log_panel.py
│   │   ├── status_panel.py
│   │   └── connector_panel.py
│   └── styles/          # QSS stylesheets
├── build_tools/
│   ├── binary.py        # PyInstaller binary builder
│   └── icons.py         # Icon generation
└── util/
    ├── config.py        # Configuration management (SimulationConfig)
    ├── event.py         # Event system for observer pattern
    └── subscriber.py    # Base class for event subscribers
```

### Testing

```bash
poetry run pytest                              # Run all tests
poetry run pytest tests/test_engine.py         # Run specific test file
poetry run pytest tests/test_engine.py::TestEngine::test_session_start -v  # Run single test
poetry run pytest -x                           # Stop on first failure
```

Test files are located in the `tests/` directory:
- `test_engine.py` - Engine and session management tests
- `test_connector.py` - Connector state machine tests
- `test_session.py` - Charging session tests
- `test_energy_meter.py` - Energy metering tests
- `test_event.py` - Event system tests

### Linting and Type Checking

```bash
poetry run mypy src/           # Type checking
poetry run ruff check src/     # Linting
poetry run ruff format src/    # Format code
poetry run ruff check src/ --fix  # Auto-fix lint issues
```

## OCPP 1.6 Support

### Outgoing Messages (Charge Point → CSMS)

| Message | Description |
|---------|-------------|
| `BootNotification` | Sent on connection to register with CSMS |
| `Heartbeat` | Periodic connection health check |
| `Authorize` | Validates an ID tag with CSMS |
| `StartTransaction` | Initiates a charging session |
| `StopTransaction` | Ends a charging session |
| `StatusNotification` | Reports connector status changes |
| `MeterValues` | Periodic energy meter readings |

### Incoming Messages (CSMS → Charge Point)

| Message | Description |
|---------|-------------|
| `RemoteStartTransaction` | CSMS requests session start |
| `RemoteStopTransaction` | CSMS requests session stop |

## Building

Build standalone executables using PyInstaller:

```bash
poetry run build              # Build binary for current platform
poetry run build-icons        # Generate application icons
```

## License

This project is licensed under the GNU Affero General Public License v3 (AGPLv3). See [LICENSE](LICENSE) for details.
