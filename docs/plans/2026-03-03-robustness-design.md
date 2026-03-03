# Robustness Design — 2026-03-03

## Overview

Implement three robustness features for OCPP 1.6J compliance: offline message queuing, structured
CallError handling, and connector state machine validation.

---

## 1. Message Queue (Offline Buffering)

### Problem

When the WebSocket connection drops, Bridge event handlers silently discard transaction-critical
messages (`StartTransaction`, `StopTransaction`, `MeterValues`). OCPP 1.6 section 4.9 requires
these be buffered and replayed on reconnection.

### Design

New module `bridge/message_queue.py` with three components:

**QueueBackend (Protocol)**
- `store(msg: QueuedMessage) -> None`
- `pop() -> Optional[QueuedMessage]`
- `peek() -> Optional[QueuedMessage]`
- `all() -> list[QueuedMessage]`
- `size -> int`
- `clear() -> None`

**InMemoryBackend** — Default. Uses `collections.deque`. Lost on app restart.

**JsonFileBackend** — Optional. Writes to `~/.chargeghost/message_queue.json`. Survives restarts.
Reads full file on init, writes atomically (tmp + `os.replace`) on every mutation.

**QueuedMessage (dataclass)**
```
action: str              # "StartTransaction", "StopTransaction", "MeterValues"
kwargs: dict             # serialized call arguments
timestamp: str           # ISO 8601 when originally enqueued
attempts: int = 0        # retry counter
```

**MessageQueue**
- `__init__(backend: QueueBackend, max_attempts: int = 3)`
- `enqueue(action: str, kwargs: dict) -> None`
- `drain(adapter, loop) -> int` — Replays all messages via adapter send methods. Increments
  `attempts` on failure. Drops messages exceeding `max_attempts`. Returns count sent.
- `size -> int`
- `clear() -> None`

### What Gets Queued

Only transaction-related messages per OCPP 1.6 spec:
- `StartTransaction`
- `StopTransaction`
- `MeterValues`

NOT queued: `StatusNotification` (stale state is worse than none), `Heartbeat`, `BootNotification`.

### Integration

1. **Bridge event handlers**: When `adapter` or `loop` is `None`, call `queue.enqueue()` instead
   of returning early.

2. **`Bridge._on_adapter_registered()`**: After initial status notifications, call
   `queue.drain(adapter, loop)`.

3. **Config**: `SimulationConfig` gets `persist_message_queue: bool = False`. When `True`, uses
   `JsonFileBackend`; otherwise `InMemoryBackend`.

4. **`TransactionMessageAttempts`** config key (already exists, default 3) controls
   `max_attempts`.

### Data Flow

```
Engine.stop_session()
  → Bridge.on_engine_session_stopped()
    → adapter is None (disconnected)
    → queue.enqueue("StopTransaction", {meter_stop, timestamp, tx_id, reason})

[WebSocket reconnects]
  → _on_adapter_registered()
    → queue.drain(adapter, loop)
      → adapter.send_stop_transaction(...)  # replayed from queue
```

---

## 2. CallError Handling

### Problem

OCPP `CallError` responses from the CSMS raise `ocpp.exceptions.*` in the adapter. These bubble up
as unhandled exceptions caught only by the generic `_handle_future_error` logger. No structured
action is taken (e.g., retrying a failed `StopTransaction` or rejecting a session on
`StartTransaction` failure).

### Design

Add `_handle_ocpp_error(action, error_code, error_description)` to `Adapter` for structured
logging and classification.

### Error Code → Action Mapping

| Error Code | Context | Behavior |
|---|---|---|
| `NotImplemented` | Any | Log warning. Feature not supported by CSMS. |
| `NotSupported` | Any | Log warning. |
| `InternalError` | `StartTransaction` | Log error. Don't assign transaction_id. |
| `InternalError` | `StopTransaction` | Log error. Re-enqueue to message queue. |
| `InternalError` | Other | Log error. |
| `SecurityError` | Any | Log as important security event. |
| `GenericError` | Any | Log with full description. |
| `PropertyConstraintViolation` | Any | Log. Request was malformed. |
| `OccurrenceConstraintViolation` | Any | Log. |

### Integration

1. **Bridge `send_start_tx`**: Catch `ocpp` exceptions. On error, log structured message, don't
   set `session.transaction_id`.

2. **Bridge `on_engine_session_stopped`**: On failure, enqueue `StopTransaction` to message queue
   for retry.

3. **`_handle_future_error`**: Enhanced to detect `ocpp` exception types and route to
   `_handle_ocpp_error` for structured logging instead of generic error output.

### Key Principle

CallError handling integrates with the message queue — transaction messages that fail due to
transient errors get re-enqueued rather than silently lost.

---

## 3. State Machine Validation

### Problem

Connector methods have implicit guards (e.g., `plug_in` only transitions from `AVAILABLE`), but
Engine doesn't validate connector state before starting sessions. A transaction can start on a
`FAULTED` or `UNAVAILABLE` connector.

### Design

**Transition table** as a module-level dict in `connector.py`:

```python
VALID_TRANSITIONS: dict[tuple[ConnectorState, str], ConnectorState] = {
    # Plug in/out
    (ConnectorState.AVAILABLE, "plug_in"):          ConnectorState.PREPARING,
    (ConnectorState.PREPARING, "unplug"):            ConnectorState.AVAILABLE,
    (ConnectorState.FINISHING, "unplug"):             ConnectorState.AVAILABLE,
    (ConnectorState.CHARGING, "unplug"):              ConnectorState.AVAILABLE,
    (ConnectorState.SUSPENDED_EV, "unplug"):          ConnectorState.AVAILABLE,

    # Session lifecycle
    (ConnectorState.PREPARING, "start_charging"):     ConnectorState.CHARGING,
    (ConnectorState.CHARGING, "stop_charging"):       ConnectorState.FINISHING,
    (ConnectorState.SUSPENDED_EV, "stop_charging"):   ConnectorState.FINISHING,

    # Suspension
    (ConnectorState.CHARGING, "suspend_ev"):          ConnectorState.SUSPENDED_EV,
    (ConnectorState.SUSPENDED_EV, "resume"):          ConnectorState.CHARGING,

    # Administrative
    (ConnectorState.AVAILABLE, "set_unavailable"):    ConnectorState.UNAVAILABLE,
    (ConnectorState.UNAVAILABLE, "set_available"):    ConnectorState.AVAILABLE,
    (ConnectorState.AVAILABLE, "set_faulted"):        ConnectorState.FAULTED,
    (ConnectorState.FAULTED, "set_available"):        ConnectorState.AVAILABLE,
}
```

**Connector._transition(action: str) -> Optional[str]**

Private helper that looks up the transition. Returns `None` on success (state updated), or an
error string on invalid transition.

**Connector method updates**: `plug_in()`, `unplug()`, `start_charging()`, `stop_charging()`,
`suspend_ev()`, `resume_charging()` all use `_transition()` and return the error string (or `None`).

**Engine guards**: `start_session()`, `plug_in()`, `stop_session()` check connector state and
log+reject invalid operations. Return `Optional[str]` error.

### What This Blocks

- Starting a transaction on `FAULTED` or `UNAVAILABLE` connector
- Plugging in when connector is `FAULTED`
- Suspending when not `CHARGING`
- Resuming when not `SUSPENDED_EV`

### What This Does NOT Block

- `unplug` from any plugged-in state (physical disconnect is always possible)
- Direct `status` setter (preserved for OCPP-driven transitions like future `ChangeAvailability`)

---

## Testing Strategy

- **Message Queue**: Unit tests for `InMemoryBackend`, `JsonFileBackend`, `MessageQueue`. Integration
  test verifying drain-on-reconnect flow via Bridge.
- **CallError**: Unit tests for `_handle_ocpp_error` mapping. Integration test simulating a
  `CallError` response on `StartTransaction`.
- **State Machine**: Unit tests for every valid and invalid transition in the table. Engine-level
  tests for rejected operations on `FAULTED`/`UNAVAILABLE` connectors.

## Files Changed

| Feature | New Files | Modified Files |
|---|---|---|
| Message Queue | `bridge/message_queue.py`, `tests/test_message_queue.py` | `bridge/bridge.py`, `util/config.py` |
| CallError | — | `ocpp_adapter/adapter.py`, `bridge/bridge.py` |
| State Machine | `tests/test_state_machine.py` | `engine/connector.py`, `engine/engine.py` |
