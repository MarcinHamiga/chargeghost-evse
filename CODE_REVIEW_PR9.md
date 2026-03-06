# Code Review — PR #9

**PR:** feat: add robustness features — state machine validation, offline message queue, CallError recovery
**Commit:** `1d98f15ecba57a564bff72691c30b1469848d954`
**Date:** 2026-03-04

## High-confidence issues (score 80+)

### 1. `.gitignore` corruption — missing newline merges two entries (score: 100)

The previous file had no trailing newline. Appending `.worktrees/` concatenated it with the prior line, producing `.claude/settings.local.json.worktrees/`. Neither pattern is recognized by git — `.claude/settings.local.json` is no longer ignored, risking accidental commits of local settings.

**File:** [`.gitignore#L215-L216`](https://github.com/MarcinHamiga/chargeghost-evse/blob/1d98f15ecba57a564bff72691c30b1469848d954/.gitignore#L215-L216)

### 2. `message_queue.py` uses spaces instead of tabs (score: 100)

CLAUDE.md says "Indentation: tabs (not spaces)." The entire new file uses 4-space indentation throughout every class body, method, and nested block.

**File:** [`src/chargeghost_evse/bridge/message_queue.py#L1-L30`](https://github.com/MarcinHamiga/chargeghost-evse/blob/1d98f15ecba57a564bff72691c30b1469848d954/src/chargeghost_evse/bridge/message_queue.py#L1-L30)

### 3. `drain()` breaks OCPP message ordering on partial failure (score: 100)

Failed messages are re-queued at the end of the queue. If `StartTransaction` fails but a subsequent `StopTransaction` succeeds in the same drain cycle, the server receives `StopTransaction` for a transaction it never saw opened. On retry, the ordering is violated — the server sees `StopTransaction` before `StartTransaction`, breaking OCPP 1.6 transaction sequencing.

**File:** [`src/chargeghost_evse/bridge/message_queue.py#L210-L238`](https://github.com/MarcinHamiga/chargeghost-evse/blob/1d98f15ecba57a564bff72691c30b1469848d954/src/chargeghost_evse/bridge/message_queue.py#L210-L238)

### 4. `MessageQueue` has no thread synchronization (score: 100)

The queue is accessed from the meter-values thread (`enqueue`), main thread (Engine event callbacks), and async runner thread (`drain`). The compound `all()` + `clear()` in `drain()` is not atomic — a message enqueued between these two calls is silently lost.

**File:** [`src/chargeghost_evse/bridge/message_queue.py#L212-L213`](https://github.com/MarcinHamiga/chargeghost-evse/blob/1d98f15ecba57a564bff72691c30b1469848d954/src/chargeghost_evse/bridge/message_queue.py#L212-L213)

### 5. `drain()` clears persistent backend before sends complete (score: 100)

`drain()` snapshots messages then immediately calls `clear()` (which deletes the JSON file for `JsonFileBackend`) before any message is successfully sent. If the process crashes mid-drain, all buffered transaction messages are permanently lost. This defeats the purpose of the persistence feature.

**File:** [`src/chargeghost_evse/bridge/message_queue.py#L212-L213`](https://github.com/MarcinHamiga/chargeghost-evse/blob/1d98f15ecba57a564bff72691c30b1469848d954/src/chargeghost_evse/bridge/message_queue.py#L212-L213)

### 6. Messages exceeding `max_attempts` are silently dropped (score: 100)

When a transaction-critical message (e.g. `StartTransaction`) exceeds the retry limit, `drain()` does `continue` with no log, warning, or event emission. The user has zero visibility into dropped messages. For an OCPP simulator, silently losing transaction messages makes debugging impossible.

**File:** [`src/chargeghost_evse/bridge/message_queue.py#L216-L217`](https://github.com/MarcinHamiga/chargeghost-evse/blob/1d98f15ecba57a564bff72691c30b1469848d954/src/chargeghost_evse/bridge/message_queue.py#L216-L217)

## Below-threshold issues (score 75)

These were flagged but scored below the 80-point cutoff:

- **`drain()` discards `StartTransaction` response** — `transaction_id` is never assigned when replaying offline queue, so subsequent `MeterValues`/`StopTransaction` carry `transaction_id=0`.
- **`unplug()` bypasses `_transition()`** — VALID_TRANSITIONS entries for `unplug` are dead code since the method directly sets `self.status = self._persistent_status`.
- **`SUSPENDED_EVSE` has no transitions** — State is defined per OCPP spec but missing from VALID_TRANSITIONS, blocking future EVSE-initiated suspension features.
- **`JsonFileBackend` uses `logging` module** — CLAUDE.md requires `on_log: Event` / `self._log(message="...")` pattern for class logging.
