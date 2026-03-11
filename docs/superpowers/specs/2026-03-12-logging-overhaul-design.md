# Logging Overhaul Design

## Problem

ChargeGhost's logging uses a custom Event-based system with a binary `is_important` flag. This provides limited filtering (compact/verbose), no log level hierarchy, no structured metadata, no OCPP request/response correlation, no ChargingProfileManager visibility, and file logs that grow without rotation. Both developers debugging the simulator and integrators diagnosing OCPP exchanges need better tooling.

## Goals

- Two clear logging modes: **shallow** (connection lifecycle, transactions, state changes) and **deep** (full OCPP payloads, profile evaluation traces, internal decisions)
- Structured log records with machine-parseable metadata for post-mortem analysis
- OCPP request/response correlation via message IDs
- Full ChargingProfileManager evaluation traces
- Collapsible OCPP payloads and profile traces in the UI
- Rotating file logs with JSON output
- Incremental migration path — components migrate one at a time

## Non-Goals

- Network/remote logging
- Log search or filtering UI beyond shallow/deep toggle
- Console/stdout logging
- Changing the UI layout or log panel position

---

## Architecture

### Logger Hierarchy

Named loggers, one per component, using Python's `logging` module:

```
chargeghost                     — root logger
chargeghost.engine              — Engine domain logic
chargeghost.engine.connector    — Connector state machines
chargeghost.engine.session      — Session lifecycle & energy
chargeghost.ocpp                — OCPP adapter (message handling)
chargeghost.ocpp.tx             — Raw OCPP TX/RX wire traffic
chargeghost.ocpp.profiles       — ChargingProfileManager evaluations
chargeghost.ocpp.firmware       — FirmwareManager operations
chargeghost.ocpp.auth           — LocalAuthListManager
chargeghost.ocpp.config         — ConfigurationKeyManager
chargeghost.bridge              — Bridge/AsyncRunner connection lifecycle
```

### Level Mapping

| Level   | Shallow mode | Deep mode | Usage                                                              |
|---------|--------------|-----------|--------------------------------------------------------------------|
| ERROR   | Shown        | Shown     | Connection failures, protocol errors, exceptions, invalid states   |
| WARNING | Shown        | Shown     | Rejected OCPP requests, auth failures, reconnect attempts          |
| INFO    | Shown        | Shown     | Connection lifecycle, transactions, state changes, profiles applied |
| DEBUG   | Hidden       | Shown     | Full payloads, profile traces, meter values, heartbeats, enqueues  |

Config field rename: `log_mode: Literal["compact", "verbose"]` → `log_mode: Literal["shallow", "deep"]`.

---

## Log Record Structure

### Standard Fields (every record)

```python
{
	"ts": "2026-03-12T14:30:45.123456+00:00",
	"level": "INFO",
	"logger": "chargeghost.engine.connector",
	"message": "Human-readable text (Rich markup for UI, stripped for file)",
	"source": "engine" | "ocpp" | "bridge",
	"component": "connector" | "session" | "profiles" | ...,
}
```

### OCPP-Specific Fields (on `chargeghost.ocpp.tx` records)

```python
{
	"ocpp_direction": "TX" | "RX",
	"ocpp_action": "BootNotification",
	"ocpp_message_id": "abc-123",
	"ocpp_payload": { ... },           # full dict
	"ocpp_correlated_id": "abc-123",   # links request to response
}
```

### State Transition Fields

```python
{
	"transition_from": "Available",
	"transition_to": "Preparing",
	"connector_id": 1,
}
```

### Profile Evaluation Fields (on `chargeghost.ocpp.profiles` DEBUG records)

```python
{
	"evaluated_profiles": [...],
	"winning_profile": {"id": 1, "stack_level": 3, "purpose": "TxProfile"},
	"computed_limit_amps": 16.0,
	"reason": "TxProfile at stack_level 3 overrides TxDefaultProfile at stack_level 0",
}
```

---

## LogBridgeHandler

A custom `logging.Handler` that converts Python log records into Qt signals for the UI:

```python
class LogBridgeHandler(logging.Handler):
	"""Routes Python log records to Qt signal for UI consumption."""

	def __init__(self, signal: Signal):
		super().__init__()
		self.signal = signal

	def emit(self, record: logging.LogRecord):
		self.signal.emit(record)
```

Attached once at app startup:

```python
handler = LogBridgeHandler(self.signal_bridge.log_record_received)
handler.setLevel(logging.DEBUG)
logging.getLogger("chargeghost").addHandler(handler)
```

### QtSignalBridge Changes

- Old signal: `log_received = Signal(str, str, bool)` — `(source, message, is_important)`
- New signal: `log_record_received = Signal(object)` — full `logging.LogRecord`
- Remove: `_on_engine_log`, `_on_bridge_log` methods and their Event subscriptions

Threading: Qt signals with `QueuedConnection` (default for cross-thread) handle the thread hop. No special handling needed.

---

## Component Migration Pattern

### Before (current)

```python
class Engine:
	def __init__(self):
		self.on_log: Event = Event()

	def _log(self, message: str, **kwargs):
		self.on_log.emit(message=message, **kwargs)
```

### After

```python
import logging

class Engine:
	def __init__(self):
		self.logger = logging.getLogger("chargeghost.engine")

	def _log(self, message: str, *, level: int = logging.INFO, **extra):
		self.logger.log(level, message, extra={"source": "engine", **extra})
```

### Key Decisions

- **`_log` wrapper stays** — standardizes `source` field, keeps call sites clean, single hook point
- **`on_log` Event removed** from each component after migration
- **`is_important` and `is_ocpp_message` kwargs removed** — replaced by level + structured extras
- **Migration is incremental** — each component migrates independently

### Component-Specific Notes

- **FirmwareManager**: currently has its own `on_log` that adapter subscribes to and re-emits. After migration, uses `logging.getLogger("chargeghost.ocpp.firmware")` directly. No forwarding.
- **AsyncRunner/Bridge**: both have `on_log`. Merge into `chargeghost.bridge`. Bridge no longer aliases `self.on_log = self.runner.on_log`.
- **ChargingProfileManager**: currently has no logging. Gets `chargeghost.ocpp.profiles` logger (see dedicated section below).

---

## File Logger

Replaces `SessionFileLogger` with standard Python logging infrastructure.

### Setup

```python
file_handler = RotatingFileHandler(
	log_dir / "chargeghost.log",
	maxBytes=5 * 1024 * 1024,   # 5MB
	backupCount=5,               # 25MB total max
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(JsonLogFormatter())
logging.getLogger("chargeghost").addHandler(file_handler)
```

### JSON Formatter

```python
class JsonLogFormatter(logging.Formatter):
	EXTRA_KEYS = (
		"source", "component", "ocpp_direction", "ocpp_action",
		"ocpp_message_id", "ocpp_payload", "ocpp_correlated_id",
		"connector_id", "transition_from", "transition_to",
		"evaluated_profiles", "winning_profile",
		"computed_limit_amps", "reason",
	)

	def format(self, record: logging.LogRecord) -> str:
		entry = {
			"ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
			"level": record.levelname,
			"logger": record.name,
			"message": strip_rich_markup(record.getMessage()),
		}
		for key in self.EXTRA_KEYS:
			if hasattr(record, key):
				entry[key] = getattr(record, key)
		return json.dumps(entry)
```

### What Gets Removed

- `SessionFileLogger` class entirely
- Its instantiation in `MainWindow.__init__`
- Manual file handle management, threading lock, flush logic

### Session Boundaries

INFO-level log at startup: `"=== ChargeGhost session started ==="` marks where each app run begins in the continuous log file.

---

## ChargingProfileManager Logging

Net-new logging addition. Logger: `chargeghost.ocpp.profiles`.

### INFO Level (visible in shallow mode)

- `"Profile installed: TxProfile #1 (stack_level=3, Relative, 16A limit)"`
- `"Profile cleared: TxProfile #1"`
- `"Limit applied to connector 1: 16.0A"`
- `"No active profile for connector 1"`

### DEBUG Level (visible in deep mode, collapsible in UI)

Full evaluation trace when `get_composite_limit()` or `get_composite_schedule()` is called:

```
Profile evaluation for connector 1:
  Candidates:
    ChargePointMaxProfile #0 (stack_level=0): 32A — applicable (no tx required)
    TxDefaultProfile #2 (stack_level=0): 24A — applicable (active tx)
    TxProfile #1 (stack_level=3): 16A — applicable (matches tx)
  Resolution:
    ChargePointMaxProfile cap: 32A
    TxProfile #1 wins over TxDefaultProfile #2 (higher stack_level: 3 > 0)
    Effective: min(32A cap, 16A tx) = 16.0A
  Schedule periods evaluated:
    Period 0: start=0s, limit=16A ← active
    Period 1: start=3600s, limit=24A
```

Structured extras on these records:

```python
extra={
	"evaluated_profiles": [
		{"id": 0, "purpose": "ChargePointMaxProfile", "stack_level": 0, "limit": 32.0},
		{"id": 2, "purpose": "TxDefaultProfile", "stack_level": 0, "limit": 24.0},
		{"id": 1, "purpose": "TxProfile", "stack_level": 3, "limit": 16.0},
	],
	"winning_profile": {"id": 1, "stack_level": 3, "purpose": "TxProfile"},
	"computed_limit_amps": 16.0,
	"reason": "TxProfile at stack_level 3 overrides TxDefaultProfile at stack_level 0",
	"connector_id": 1,
}
```

---

## UI Changes

### Mode Rename

"Compact"/"Verbose" buttons → "Shallow"/"Deep" in `CollapsibleLogPanel`.

### Shallow Mode

Single-line entries for INFO+ records:

```
14:30:45  Connected to ws://localhost:9000
14:30:45  TX BootNotification → RX Accepted
14:30:52  Connector 1: Available → Preparing
14:31:01  Session started (connector 1, tag ABC123)
14:31:15  Profile applied: TxProfile #1 (16A)
14:32:00  ERROR: Connection lost (code=1006)
```

### Deep Mode

DEBUG+ records shown. OCPP payloads and profile traces are collapsible:

```
14:30:45  ▶ TX BootNotification [msg-id: abc-123]
             { "chargePointVendor": "ChargeGhost", ... }
14:30:45  ▶ RX BootNotification [abc-123] Accepted
             { "interval": 300, "status": "Accepted", ... }
14:31:15  ▶ Profile evaluation (connector 1):
             Considered: TxDefaultProfile#0 (8A), TxProfile#1 (16A)
             Winner: TxProfile#1 at stack_level 3
             Computed limit: 16.0A
```

### Implementation

- `LogPanel` receives full `LogRecord` objects instead of pre-formatted strings
- Records with `ocpp_payload` extra: render clickable summary line, payload hidden by default, click toggles monospace JSON block
- Profile evaluation records: same collapsible pattern for trace details
- Color scheme derived from `record.name` (logger hierarchy) instead of `source` string
- WARNING/ERROR lines prefixed with colored marker in both modes

### Collapsible Widget Approach

Test `QTextBrowser` with HTML `<details><summary>` first. Fallback: per-entry child widgets with toggled visibility.

---

## Removals

| What                                    | Why                                              |
|-----------------------------------------|--------------------------------------------------|
| `SessionFileLogger` class              | Replaced by `RotatingFileHandler` + `JsonLogFormatter` |
| `on_log: Event` on Engine, Bridge, etc. | Replaced by Python loggers                        |
| `is_important` kwarg everywhere         | Replaced by log levels                            |
| `is_ocpp_message` kwarg                 | Replaced by `ocpp_direction` extra field           |
| `QtSignalBridge._on_engine_log/bridge_log` | Replaced by `LogBridgeHandler`                 |
| `LogMode = Literal["compact", "verbose"]` | Renamed to `Literal["shallow", "deep"]`          |
