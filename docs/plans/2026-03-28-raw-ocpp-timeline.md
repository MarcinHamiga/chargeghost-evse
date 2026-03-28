# Raw OCPP Timeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a dedicated raw OCPP timeline that captures inbound and outbound protocol frames plus related local simulator events, making it easy to debug ordering, correlation, and bad-path behavior.

**Architecture:** Build a reusable timeline store in a devtools layer. Capture events at the adapter, bridge, engine, and controller boundaries, then project that data into the Qt UI through a dedicated diagnostic panel. Keep capture separate from presentation so the same event stream can later power export, replay, and headless diagnostics.

**Tech Stack:** Python 3.11+, PySide6, dataclasses, json, pytest, pytest-qt, existing structured logging and adapter hooks

**Run tests after every commit:**
```bash
poetry run pytest -x
poetry run ruff check src/ tests/
poetry run mypy src/
```

---

## Context You Must Know

- `BaseAdapter` already emits `on_ocpp_message` and structured log extras like `ocpp_direction`, `ocpp_action`, and `ocpp_message_id`.
- `Bridge` already knows about session starts/stops, status changes, heartbeat activity, and queued offline sends.
- `Engine` emits connector and session lifecycle events through the shared `Event` helper.
- The Qt app already routes log records into the UI through `QtSignalBridge.log_record_received` and the right-side `LogSidePanel`.
- Current logging is useful, but it is still log-centric. The timeline should be event-centric and queryable.
- The simulator supports both OCPP `1.6J` and `2.0.1`; timeline capture must work for both.

## Recommended Scope

Ship the first version with:

- rolling in-memory timeline store
- capture of raw inbound/outbound OCPP frames
- capture of key local events such as UI actions, connector status changes, and session lifecycle
- filters by source, action, direction, connector ID, and error state
- copy/export actions

Do **not** build a full replay engine in the first pass, but preserve enough structure that replay can reuse the exported format later.

---

## Success Criteria

Success means:

- Every inbound and outbound OCPP frame is captured with timestamp, direction, action, and message ID when available.
- Local simulator actions and engine/bridge lifecycle events can appear in the same ordered timeline.
- Timeline retention is bounded and does not grow without limit.
- The UI exposes a usable diagnostic surface with filtering and copy/export.
- Structured tests cover event capture, ordering, correlation fields, and export format.

---

## Event Model

Use one normalized event type for both protocol and local entries.

Recommended fields:

- `event_id`
- `timestamp`
- `source` (`ui`, `engine`, `bridge`, `ocpp`)
- `direction` (`inbound`, `outbound`, `local`)
- `event_type` (`frame`, `status_change`, `session`, `action`, `queue`, `error`)
- `protocol_version`
- `action`
- `message_id`
- `connector_id`
- `transaction_id`
- `level`
- `summary`
- `payload`
- `correlation_key`
- `tags`

Keep `payload` JSON-serializable so export is straightforward.

---

## Target File Layout

Create or refactor toward this structure:

- `src/chargeghost_evse/devtools/__init__.py`
- `src/chargeghost_evse/devtools/timeline_models.py`
- `src/chargeghost_evse/devtools/timeline_store.py`
- `src/chargeghost_evse/devtools/timeline_export.py`
- `src/chargeghost_evse/ui/widgets/ocpp_timeline_panel.py`
- `tests/test_timeline_store.py`
- `tests/test_timeline_capture.py`
- `tests/test_ocpp_timeline_panel.py`

Likely modifications:

- `src/chargeghost_evse/ocpp_adapter/base_adapter.py`
- `src/chargeghost_evse/bridge/bridge.py`
- `src/chargeghost_evse/engine/engine.py`
- `src/chargeghost_evse/ui/app.py`
- `src/chargeghost_evse/ui/bridge.py`
- `src/chargeghost_evse/ui/widgets/log_side_panel.py`
- `src/chargeghost_evse/ui/widgets/__init__.py`
- `src/chargeghost_evse/util/log_setup.py`

---

## Task 1: Add Timeline Models and Bounded Store

**Files:**
- Create: `src/chargeghost_evse/devtools/timeline_models.py`
- Create: `src/chargeghost_evse/devtools/timeline_store.py`
- Test: `tests/test_timeline_store.py`

### Step 1: Write the failing tests

Add coverage for:

- appending timeline events preserves insertion order
- store trims old events when max retention is reached
- filtering by source, action, and connector ID works
- clearing the store removes all events
- subscribers are notified when a new event is appended

Suggested test names:

- `test_timeline_store_appends_in_order`
- `test_timeline_store_enforces_max_length`
- `test_timeline_store_filters_by_source_and_action`
- `test_timeline_store_clear_removes_events`
- `test_timeline_store_notifies_subscribers`

### Step 2: Implement the store

Add:

- `TimelineEvent`
- `TimelineFilter`
- `TimelineStore`

Implementation notes:

- Use a bounded `deque` for retention.
- Generate a stable monotonically increasing `event_id` in-process.
- Keep query APIs simple and synchronous for the first pass.
- Use the shared `Event` helper so UI code can subscribe to append events.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_timeline_store.py -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/devtools/timeline_models.py src/chargeghost_evse/devtools/timeline_store.py tests/test_timeline_store.py
git commit -m "feat: add timeline event store"
```

---

## Task 2: Capture Raw OCPP Frames from the Adapter Layer

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/base_adapter.py`
- Test: `tests/test_timeline_capture.py`
- Test: `tests/test_adapter_logging.py`

### Step 1: Write the failing tests

Add coverage for:

- outbound frame append includes action and payload
- inbound frame append includes action and message ID
- both OCPP versions can append timeline entries through the shared base adapter path
- existing logging behavior remains intact after timeline capture is added

Suggested test names:

- `test_base_adapter_appends_outbound_timeline_event`
- `test_base_adapter_appends_inbound_timeline_event`
- `test_timeline_capture_does_not_break_ocpp_logging`

### Step 2: Implement adapter capture hooks

Implementation notes:

- Extend `_log_ocpp_raw()` so it can forward structured frame data into the timeline store in addition to structured logs.
- Preserve raw payload shape where possible instead of only storing pretty-printed strings.
- Capture protocol version and normalized direction values (`inbound` / `outbound`).
- Do not duplicate events by capturing both before and after the same send unless there is a clear reason.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_timeline_capture.py tests/test_adapter_logging.py -k "timeline or ocpp" -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/ocpp_adapter/base_adapter.py tests/test_timeline_capture.py tests/test_adapter_logging.py
git commit -m "feat: capture raw ocpp frames in timeline"
```

---

## Task 3: Capture Local Bridge, Engine, and User Events

**Files:**
- Modify: `src/chargeghost_evse/bridge/bridge.py`
- Modify: `src/chargeghost_evse/engine/engine.py`
- Modify: `src/chargeghost_evse/ui/app.py`
- Test: `tests/test_timeline_capture.py`

### Step 1: Write the failing tests

Add coverage for:

- connector status change appends a local event
- session started and session stopped append timeline entries with connector ID
- offline queueing appends a queue event
- UI-originated actions such as plug in and authorize append local action events

Suggested test names:

- `test_connector_status_change_appends_timeline_event`
- `test_session_lifecycle_appends_timeline_events`
- `test_offline_queue_appends_queue_event`
- `test_ui_action_appends_local_timeline_event`

### Step 2: Implement local event capture

Implementation notes:

- Capture events where the intent is clearest: UI/controller for user actions, engine for domain transitions, bridge for connection and queue behavior.
- Reuse one timeline store owned near `MainWindow` or another top-level runtime object.
- Keep summaries concise, for example `"Connector 1 -> Charging"` or `"Queued StartTransaction while offline"`.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_timeline_capture.py -k "local or session or queue" -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/bridge/bridge.py src/chargeghost_evse/engine/engine.py src/chargeghost_evse/ui/app.py tests/test_timeline_capture.py
git commit -m "feat: capture local simulator events in timeline"
```

---

## Task 4: Add Correlation, Export, and Redaction Rules

**Files:**
- Create: `src/chargeghost_evse/devtools/timeline_export.py`
- Modify: `src/chargeghost_evse/devtools/timeline_models.py`
- Modify: `src/chargeghost_evse/devtools/timeline_store.py`
- Modify: `src/chargeghost_evse/util/log_setup.py`
- Test: `tests/test_timeline_store.py`
- Test: `tests/test_log_setup.py`

### Step 1: Write the failing tests

Add coverage for:

- exported JSON preserves normalized event fields
- message ID becomes part of the correlation key when present
- sensitive fields are redacted before export if needed
- large payloads are truncated or summarized without breaking JSON validity

Suggested test names:

- `test_timeline_export_writes_json_events`
- `test_timeline_event_builds_correlation_key_from_message_id`
- `test_timeline_export_redacts_sensitive_fields`
- `test_timeline_export_truncates_large_payloads`

### Step 2: Implement export and hardening

Implementation notes:

- Start with JSON export; add text export only if it stays thin.
- Redact obvious secrets if any request payloads ever contain them; do not rely on UI-only masking.
- Keep truncation deterministic and explicit, for example with a `payload_truncated` flag.
- Consider updating structured logging extras only if it directly supports timeline parity.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_timeline_store.py tests/test_log_setup.py -k "timeline or redact or export" -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/devtools/timeline_export.py src/chargeghost_evse/devtools/timeline_models.py src/chargeghost_evse/devtools/timeline_store.py src/chargeghost_evse/util/log_setup.py tests/test_timeline_store.py tests/test_log_setup.py
git commit -m "feat: add timeline export and correlation metadata"
```

---

## Task 5: Add a Dedicated Timeline UI Panel

**Files:**
- Create: `src/chargeghost_evse/ui/widgets/ocpp_timeline_panel.py`
- Modify: `src/chargeghost_evse/ui/widgets/log_side_panel.py`
- Modify: `src/chargeghost_evse/ui/widgets/__init__.py`
- Modify: `src/chargeghost_evse/ui/app.py`
- Modify: `src/chargeghost_evse/ui/styles/e_mobility.qss`
- Test: `tests/test_ocpp_timeline_panel.py`
- Test: `tests/test_log_side_panel.py`
- Test: `tests/test_ui_widgets.py`

### Step 1: Write the failing tests

Add coverage for:

- diagnostic side panel exposes a timeline view alongside the existing log view
- timeline view can filter by direction and action
- appending new events updates the panel without reloading the whole widget
- copy/export actions are available from the timeline surface

Suggested test names:

- `test_log_side_panel_exposes_timeline_view`
- `test_ocpp_timeline_panel_filters_by_direction`
- `test_ocpp_timeline_panel_updates_when_store_changes`
- `test_ocpp_timeline_panel_exposes_export_action`

### Step 2: Implement the panel

Implementation notes:

- Extend the existing right-side diagnostics area instead of creating a second permanent side rail.
- Keep the timeline optimized for scanning: timestamp, direction badge, action, summary, and expandable payload.
- Reuse the current visual language from the log panel so the feature feels native.
- Make the timeline useful even on narrow widths.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_ocpp_timeline_panel.py tests/test_log_side_panel.py tests/test_ui_widgets.py -k "timeline" -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/ui/widgets/ocpp_timeline_panel.py src/chargeghost_evse/ui/widgets/log_side_panel.py src/chargeghost_evse/ui/widgets/__init__.py src/chargeghost_evse/ui/app.py src/chargeghost_evse/ui/styles/e_mobility.qss tests/test_ocpp_timeline_panel.py tests/test_log_side_panel.py tests/test_ui_widgets.py
git commit -m "feat: add raw ocpp timeline panel"
```

---

## Task 6: Expose Timeline Events Through the Qt Bridge and Headless Runtime

**Files:**
- Modify: `src/chargeghost_evse/ui/bridge.py`
- Modify: `src/chargeghost_evse/main.py`
- Test: `tests/test_qt_signal_bridge.py`
- Test: `tests/test_main.py`

### Step 1: Write the failing tests

Add coverage for:

- Qt bridge exposes a `timeline_event_received` signal if direct event pushing is needed
- headless runtime can still create a timeline store and export it after a scenario run
- default desktop startup behavior remains unchanged

Suggested test names:

- `test_qt_signal_bridge_has_timeline_event_signal`
- `test_headless_runtime_can_export_timeline`
- `test_main_still_defaults_to_desktop_mode`

### Step 2: Implement bridge and runtime support

Implementation notes:

- Only add a Qt signal if it simplifies UI synchronization; otherwise let the panel subscribe to the shared store directly.
- Make the store available to both desktop and headless runtime assembly.
- Keep `main.py` backward-compatible.

### Step 3: Verify with targeted tests

Run:

```bash
poetry run pytest tests/test_qt_signal_bridge.py tests/test_main.py -k "timeline or main" -v
```

Expected: PASS

### Step 4: Commit

```bash
git add src/chargeghost_evse/ui/bridge.py src/chargeghost_evse/main.py tests/test_qt_signal_bridge.py tests/test_main.py
git commit -m "feat: expose timeline in desktop and headless runtimes"
```

---

## Final Validation

Run the full quality suite:

```bash
poetry run pytest
poetry run ruff check src/ tests/
poetry run mypy src/
```

Manual verification checklist:

- Start the simulator and connect to a CSMS.
- Trigger `BootNotification`, `Heartbeat`, `Authorize`, and a normal transaction flow.
- Open the diagnostics drawer and confirm inbound/outbound frames and local actions appear in chronological order.
- Apply a filter such as `direction=outbound` or `action=Authorize` and confirm results update immediately.
- Export the timeline and confirm the file contains structured JSON entries with stable fields.

---

## Notes and Follow-Ups

- The timeline store is the best foundation for future record/replay work, so keep the schema stable and documented.
- Once the scenario runner exists, attach scenario step IDs to local action events.
- Once fault injection exists, mark fault-triggered events with explicit tags rather than relying on text parsing.
- Do not let the timeline become a second logging system with slightly different semantics; it should be a focused event stream.
