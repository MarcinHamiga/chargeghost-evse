# Code Review: Raw OCPP Timeline Feature

**Date:** 2026-03-28
**Scope:** `docs/plans/2026-03-28-raw-ocpp-timeline.md` implementation (Tasks 1–6)
**Status:** Requested changes

---

## Summary

Solid implementation of the raw OCPP timeline feature across 6 tasks. The core store and event model are well-designed, and the layer separation between capture and presentation is clean. Several issues to address below, ranging from a correctness bug to style inconsistencies.

---

## Critical Issues

### 1. Duplicate events for status changes and session lifecycle

Both `Engine` and `Bridge` capture the same events independently, producing duplicate timeline entries for every status change and session start/stop. For example, `engine.py:447-454` captures `connector_status_changed`, then `bridge.py:1170-1179` captures the same event again from the bridge handler. The user sees two entries per status change.

**Fix:** Pick one capture point per event type. Bridge-level capture is the right place for most events since it has the most context (online/offline state, retry info). Remove the engine-level captures for overlapping events, or deduplicate using `correlation_key`.

---

## Important Issues

### 2. `main.py:15` — `TimelineStore | None` violates project convention

AGENTS.md specifies `Optional[T]` not `T | None`. This is explicitly listed as a code convention.

```python
# Line 15
timeline_store: TimelineStore | None = None
```

**Fix:** Use `Optional[TimelineStore]`.

### 3. `timeline_store.py:71` — Event emitted outside the lock

`on_event.emit(event)` fires after the lock is released, but before the method returns. This is fine for single appends, but if two threads append concurrently, subscribers could see events out of order relative to `store.all()`. Consider emitting inside the lock or documenting the ordering guarantee.

### 4. `ocpp_timeline_panel.py:191-195` — Thread safety: store events may fire from non-Qt threads

`_on_store_event` is called from `TimelineStore.on_event` which fires from whatever thread called `append()`. The Bridge and Adapter run on background threads. Directly updating Qt widgets from a non-main thread is undefined behavior and will crash on some platforms.

**Fix:** Use `QMetaObject.invokeMethod` or `QTimer.singleShot(0, ...)` to marshal to the main thread:

```python
def _on_store_event(self, event: TimelineEvent) -> None:
	QTimer.singleShot(0, lambda: self._handle_store_event(event))
```

### 5. `ocpp_timeline_panel.py:261-266` — Export copies raw dataclass `__dict__` to clipboard

The Export button serializes `e.__dict__` directly, bypassing the `TimelineExporter` which handles redaction and truncation. Sensitive fields like `id_tag` and `password` will appear unredacted in the exported clipboard content.

**Fix:** Use `TimelineExporter` for the export action, or at minimum apply redaction.

### 6. `timeline_export.py:62-64` — Untruncated payloads are wrapped in `{"original": {...}}`

When a payload is small enough to not need truncation, it's still wrapped in `{"original": redacted_payload}`. This creates an inconsistent structure: truncated payloads get `{"_summary": ..., "payload_truncated": True}` while normal ones get `{"original": {...}}`. The plan says "export preserves normalized event fields" — the `payload` key should directly contain the redacted dict.

**Fix:** Set `payload_result = redacted_payload` when not truncated.

### 7. `log_side_panel.py:229-236` — `clicked.disconnect()` without args is unsafe

`_set_active_tab` calls `self._btn_clear.clicked.disconnect()` which disconnects **all** slots connected to that signal. If anything else is connected to that button, it gets silently dropped.

**Fix:** Store the connection reference or use `disconnect(self._on_clear)` / `disconnect(self._on_timeline_clear)` specifically.

---

## Suggestions

### 8. `timeline_models.py:30` — `TimelineFilter` uses a plain class, not a dataclass

Every other model in the codebase uses `@dataclass`. The filter with 9 `__init__` parameters is a prime candidate.

### 9. `timeline_store.py:28-32` — Event ID generation acquires lock twice per `append()`

`_generate_event_id()` acquires `self._lock`, then `append()` acquires it again at line 69. This could be a single critical section.

### 10. `app.py:270-271` — `hasattr` check is fragile

```python
if hasattr(self.main_window, "timeline_store"):
```

MainWindow always creates `timeline_store` before creating child widgets, so `hasattr` will always be `True`. If it's always set, drop the guard. If there's a real edge case, document it.

### 11. `timeline_store.py:13` — Default max_length=10000

10,000 events with full payloads in memory could be substantial. Consider whether the default should be lower (e.g., 1000) or whether the store should cap individual payload sizes.

### 12. Test formatting inconsistency

`test_timeline_store.py` and `test_timeline_capture.py` use tabs (matching codebase convention) while `test_ocpp_timeline_panel.py` and `test_main.py` use spaces. While this doesn't affect correctness, it's inconsistent.

### 13. `test_main.py:185` — Dead assertion

The last line `assert len(store_created) == 0` is at module level indentation after the `finally` block, making it unreachable dead code. The test passes a `timeline_store=None` and `timeline_export_path=exported_path`, so it never creates a store — but the assertion never actually runs.
