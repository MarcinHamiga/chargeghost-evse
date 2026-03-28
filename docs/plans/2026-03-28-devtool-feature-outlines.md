# Devtool Feature Outlines

**Goal:** Capture very rough implementation outlines for three high-value devtool features: a scenario runner, fault injection controls, and a raw OCPP timeline.

**Architecture:** Keep the existing layering intact. Add reusable devtool primitives in the engine/bridge/adapter boundary, then expose them through both the Qt UI and a future headless automation path.

**Tech Stack:** Python 3.11+, PySide6, asyncio, pytest, OCPP 1.6J, existing `Engine`, `Bridge`, and `OcppAdapter` abstractions

## Detailed plans

- Scenario runner: `docs/plans/2026-03-28-scenario-runner.md`
- Fault injection: `docs/plans/2026-03-28-fault-injection.md`
- Raw OCPP timeline: `docs/plans/2026-03-28-raw-ocpp-timeline.md`

---

## Feature 1: Scenario Runner

**Why:** Backend and integration engineers need repeatable charger behavior without manually clicking through the UI every time.

### Rough shape

- Add a small scenario model describing ordered steps such as connect, authorize, plug in, remote start, suspend, resume, stop, unplug, and disconnect.
- Introduce a scenario executor that drives existing simulator actions rather than re-implementing charger logic in a parallel code path.
- Allow step timing controls so scenarios can either run instantly or with realistic delays.
- Surface scenario progress, current step, and failures in the UI.
- Leave room for a future headless entry point that can run scenarios from CLI or CI.

### Likely building blocks

- New module for scenario dataclasses and execution state, likely under `src/chargeghost_evse/devtools/` or a similar package.
- Thin action adapters that translate scenario steps into existing `Engine`, `Bridge`, or adapter operations.
- Basic serialization format for import/export, likely JSON first.
- UI panel for choosing a scenario, starting it, cancelling it, and viewing results.
- Tests for step sequencing, delay handling, cancellation, and deterministic failures.

### Early milestones

1. Hard-coded in-memory scenarios for common happy-path flows.
2. JSON-backed scenarios editable outside the app.
3. Assertion steps such as "expect status Preparing within 2s".
4. Headless runner for CI usage.

### Main risks

- Duplicating business rules if the runner bypasses normal simulator APIs.
- Race conditions between manual user actions and active scenario execution.
- Flaky tests if execution timing is tied too tightly to wall-clock sleeps.

---

## Feature 2: Fault Injection

**Why:** A simulator used as a devtool should make it easy to reproduce backend edge cases and protocol robustness issues on demand.

### Rough shape

- Add a set of injectable faults that can affect transport, timing, meter behavior, and protocol responses.
- Support both one-shot faults and persistent toggles.
- Keep faults explicit and visible so users always know when the simulator is behaving abnormally.
- Make faults composable with scenarios so a scripted flow can turn failures on and off at specific moments.

### Likely first-wave fault types

- WebSocket disconnects, delayed reconnects, and dropped heartbeats.
- Artificial response latency for inbound or outbound OCPP calls.
- Rejected or malformed responses where the adapter can safely simulate them.
- Meter anomalies such as frozen readings, sudden jumps, or reset-to-zero behavior.
- Status anomalies such as temporary flapping between `Preparing`, `Charging`, and `SuspendedEV`.

### Likely building blocks

- A centralized fault registry/service owned near the bridge/adapter layer so transport and protocol hooks can consult it.
- Lightweight hooks in outbound send paths, inbound handlers, heartbeat scheduling, and meter sampling.
- UI controls for toggles, numeric delays, and one-shot triggers.
- Clear logging markers so fault-driven behavior is obvious in logs and future transcripts.
- Tests covering no-fault baseline behavior plus each enabled fault path.

### Early milestones

1. Transport faults: disconnect, reconnect delay, heartbeat drop.
2. Timing faults: delayed responses and slow meter updates.
3. Meter/state faults: frozen meter, reset jump, status flap.
4. Scenario integration so faults can be scheduled as steps.

### Main risks

- Letting fault logic leak across too many code paths instead of centralizing it.
- Generating impossible simulator states that confuse users more than they help.
- Making the UI noisy if active faults are not summarized clearly.

---

## Feature 3: Raw OCPP Timeline

**Why:** When a test flow fails, developers usually need a precise timeline of frames, message IDs, payloads, and local simulator actions.

### Rough shape

- Capture every inbound and outbound OCPP frame with timestamp, direction, message type, action, message ID, and decoded payload.
- Correlate protocol frames with local simulator events such as plug in, start charging, suspend, and connector status changes.
- Provide a live diagnostic surface in the UI with filtering and easy copy/export.
- Keep transcript capture independent from presentation so the same data can later power export, replay, or headless diagnostics.

### Likely building blocks

- A timeline event model that can represent both raw OCPP frames and local simulator events.
- Hook points in the adapter send/receive path plus engine and bridge event listeners.
- Retention strategy for in-memory history with optional export to JSON or text.
- UI panel with filters by connector, action, direction, and error state.
- Tests covering event ordering, correlation fields, and payload redaction rules if needed.

### Useful timeline fields

- timestamp
- source (`ui`, `engine`, `bridge`, `ocpp`)
- direction (`inbound`, `outbound`, `local`)
- OCPP action and message ID
- connector ID or transaction ID when available
- rendered summary plus raw payload

### Early milestones

1. Basic rolling transcript of raw inbound/outbound OCPP frames.
2. Local simulator events added to the same timeline.
3. UI filters and copy/export actions.
4. Reuse transcript format for future record/replay work.

### Main risks

- Capturing frames in the wrong layer and missing failed or partial operations.
- Producing a timeline that is technically complete but too noisy to be useful.
- Storing too much payload data in memory without bounds.

---

## Suggested delivery order

1. Raw OCPP timeline: strongest debugging payoff and foundational for later replay features.
2. Fault injection: unlocks bad-path testing once diagnostics are visible.
3. Scenario runner: highest automation value once observability and fault controls exist.

## Cross-feature notes

- Keep data models reusable so scenarios can trigger faults and the timeline can record both.
- Prefer deterministic clocks and injectable schedulers where possible to keep tests stable.
- Preserve the existing UI-first workflow, but avoid designs that block a later headless mode.
