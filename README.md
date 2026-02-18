# ChargeGhost EVSE
An EVSE simulator written in Python, beautified and made easy with the help of Textual

## TUI Usage

The ChargeGhost EVSE provides a Textual User Interface (TUI) for interactive EVSE simulation and OCPP 1.6 CSMS connectivity.

### Running the TUI

```bash
chargeghost-evse
```

Or if running from source:

```bash
PYTHONPATH=src python3 -m chargeghost_evse.main
```

### Modes

The TUI offers two modes:

1. **Simulator Mode**: Interactive EVSE simulation with plug/unplug, card swipe, and session control
2. **Manual Mode**: Direct OCPP message sending (BootNotification, Heartbeat, StartTransaction, StopTransaction, StatusNotification)

### Key Bindings (Simulator Mode)

- `p` - Plug In
- `u` - Unplug  
- `a` - Swipe Card (authorize and start/stop session)
- `x` - Stop Session
- `q` - Quit

### Configuration

The Bridge connects to a CSMS via WebSocket. By default, it connects to `wss://localhost:3000/CP_1`.