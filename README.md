# ChargeGhost EVSE

An Electric Vehicle Supply Equipment (EVSE) simulator written in Python, featuring a beautiful terminal-based user interface (TUI) powered by Textual. ChargeGhost simulates EV charging sessions and communicates with Central Systems via the OCPP 1.6 protocol over WebSocket.

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
- [License](#license)

## Features

- Full OCPP 1.6 protocol support for CSMS communication
- Interactive terminal UI with real-time status updates
- Two operational modes: Simulator and Manual
- Configurable connection parameters (URL, credentials, TLS)
- Automatic reconnection with exponential backoff
- Periodic heartbeat and meter values reporting
- Multi-connector support

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

### Simulator Mode

The Simulator Mode provides an interactive EVSE simulation with realistic charging behavior.

#### Key Bindings

| Key | Action | Description |
|-----|--------|-------------|
| `p` | Plug In | Simulates connecting an EV to the charging station |
| `u` | Unplug | Simulates disconnecting the EV |
| `a` | Swipe Card | Authorizes and starts/stops a charging session |
| `x` | Stop Session | Stops the current charging session |
| `c` | Copy Logs | Copies log content to clipboard |
| `q` | Quit | Exits the application |

#### Typical Charging Session Workflow

1. **Plug In** (`p`): Connector transitions from `Available` to `Preparing`
2. **Swipe Card** (`a`): Sends authorization and starts transaction with CSMS
3. **Charging**: Session runs, meter values are sent periodically
4. **Stop Session** (`x`) or **Swipe Card** (`a`): Ends the transaction
5. **Unplug** (`u`): Connector returns to `Available`

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

### Manual Mode

Manual Mode allows direct OCPP message control without simulation logic. Use this for testing specific CSMS interactions.

#### Available Messages

| Button | OCPP Message | Description |
|--------|--------------|-------------|
| BootNotification | `BootNotification` | Registers the charge point with CSMS |
| Heartbeat | `Heartbeat` | Sends a heartbeat to maintain connection |
| StartTransaction | `StartTransaction` | Starts a charging session (enter ID Tag) |
| StopTransaction | `StopTransaction` | Stops the current transaction |
| StatusNotification | `StatusNotification` | Reports connector status |

### Configuration

Configuration is stored in `~/.chargeghost/config.json` and can be edited via the Config tab in Simulator Mode.

| Setting | Description | Default |
|---------|-------------|---------|
| Connection URL | CSMS WebSocket endpoint | `wss://localhost:3000/CP_1` |
| OCPP ID | Charge point identifier | `CP_1` |
| OCPP Password | Basic auth password (optional) | (empty) |
| Charge Point Model | Device model name | `ChargeGhostV1` |
| Charge Point Vendor | Manufacturer name | `ChargeGhost` |
| Number of Connectors | Simulated connectors | `1` |
| Skip TLS Verification | Disable TLS certificate checks | `false` |

After saving configuration, restart the application to apply connection changes.

## Architecture

ChargeGhost follows an event-driven architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                         UI Layer                            │
│  (Textual TUI - SimulatorScreen, ManualScreen, Widgets)    │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                       Bridge Layer                          │
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
- **OCPP Adapter**: Implements OCPP 1.6 protocol with message handlers and senders
- **Bridge**: Connects engine events to OCPP messages, runs async OCPP in a daemon thread
- **UI**: Textual-based terminal interface with multiple screens and widgets

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
│   ├── app.py           # Textual app and screens
│   └── widgets/         # UI components (LogPanel, StatusPanel)
└── util/
    ├── config.py        # Configuration management
    ├── event.py         # Event system for observer pattern
    └── subscriber.py    # Base class for event subscribers
```

### Testing

```bash
poetry run pytest                              # Run all tests
poetry run pytest tests/test_engine.py         # Run specific test file
poetry run pytest tests/test_engine.py::test_session_start -v  # Run single test
```

### Linting and Type Checking

```bash
poetry run mypy src/           # Type checking
poetry run ruff check src/     # Linting
poetry run ruff format src/    # Format code
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

## License

This project is licensed under the GNU Affero General Public License v3 (AGPLv3).
