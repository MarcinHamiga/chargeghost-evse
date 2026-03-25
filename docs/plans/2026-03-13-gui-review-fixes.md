# GUI Review Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the GUI consistency and UX defects identified in the March 13, 2026 GUI review.

**Architecture:** Add regression coverage around the existing Qt widgets and main window behaviors first, then make focused UI changes in the dashboard, manual mode, configuration panels, notifications, and update surfaces. Preserve the existing architecture while tightening state synchronization and making inactive controls visibly unavailable.

**Tech Stack:** Python, PySide6, pytest, pytest-qt

### Task 1: Add regression tests for dashboard state consistency

**Files:**
- Modify: `tests/test_ui_widgets.py`
- Modify: `src/chargeghost_evse/ui/widgets/session_dashboard.py`

**Step 1: Write the failing tests**

Add tests covering:
- dashboard power metric shows delivered power, not configured max power
- dashboard details show transaction ID only for the selected connector
- details toggle copy is consistent in collapsed and expanded states

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_ui_widgets.py -k "dashboard or details" -v`

**Step 3: Write minimal implementation**

Update `SessionDashboard.update_from_engine()` and `CollapsibleDetails` to align displayed state with the selected connector and actual delivered power.

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_ui_widgets.py -k "dashboard or details" -v`

### Task 2: Add regression tests for connector strip and manual mode behavior

**Files:**
- Modify: `tests/test_ui_widgets.py`
- Modify: `src/chargeghost_evse/ui/widgets/connector_strip.py`
- Modify: `src/chargeghost_evse/ui/app.py`

**Step 1: Write the failing tests**

Add tests covering:
- connector strip preserves meaningful non-charging status labels
- manual controls disable when adapter is unavailable
- manual stop requires an explicit transaction context
- main window does not duplicate logs in manual mode

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_ui_widgets.py -k "manual or connector or log" -v`

**Step 3: Write minimal implementation**

Update `ConnectorIndicator`, `ManualWidget`, and `MainWindow` to remove duplicated logs, disable unavailable actions, and prevent unsafe stop behavior.

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_ui_widgets.py -k "manual or connector or log" -v`

### Task 3: Add regression tests for configuration panel UX

**Files:**
- Modify: `tests/test_ui_widgets.py`
- Modify: `src/chargeghost_evse/ui/widgets/config_keys_panel.py`
- Modify: `src/chargeghost_evse/ui/app.py`

**Step 1: Write the failing tests**

Add tests covering:
- empty search shows an explicit empty state
- OCPP key edits require explicit apply instead of hidden debounce
- success/failure feedback is visible after apply

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_ui_widgets.py -k "config keys" -v`

**Step 3: Write minimal implementation**

Refactor `ConfigKeysPanel` to use explicit apply actions and add visible empty-state and status affordances, then wire it through `MainWindow`.

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_ui_widgets.py -k "config keys" -v`

### Task 4: Add regression tests for notifications and update surfaces

**Files:**
- Modify: `tests/test_ui_widgets.py`
- Modify: `tests/test_update_dialog.py`
- Modify: `tests/test_update_flow.py`
- Modify: `src/chargeghost_evse/ui/widgets/toast.py`
- Modify: `src/chargeghost_evse/ui/widgets/update_dialog.py`
- Modify: `src/chargeghost_evse/ui/app.py`
- Modify: `src/chargeghost_evse/ui/styles/e_mobility.qss`

**Step 1: Write the failing tests**

Add tests covering:
- progress updates reuse a single toast
- toast height grows for multi-line messages
- update dialog/chip use themed object names instead of inline styles
- home-screen log toggle stays disabled and visually in sync

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_update_dialog.py tests/test_update_flow.py tests/test_ui_widgets.py -k "update or toast or home" -v`

**Step 3: Write minimal implementation**

Introduce reusable progress toast handling, make toast sizing content-aware, restyle update surfaces through QSS, and keep the log toggle disabled on the mode picker.

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_update_dialog.py tests/test_update_flow.py tests/test_ui_widgets.py -k "update or toast or home" -v`

### Task 5: Verify the complete GUI fix set

**Files:**
- Verify only

**Step 1: Run targeted GUI tests**

Run: `poetry run pytest tests/test_ui_widgets.py tests/test_update_dialog.py tests/test_update_flow.py tests/test_manual_update_check.py -v`

**Step 2: Run broader regression coverage**

Run: `poetry run pytest tests/test_config_keys.py tests/test_bridge_logging.py tests/test_adapter_logging.py -v`

**Step 3: Run lint on modified UI files**

Run: `poetry run ruff check src/chargeghost_evse/ui tests/test_ui_widgets.py tests/test_update_dialog.py tests/test_update_flow.py`

