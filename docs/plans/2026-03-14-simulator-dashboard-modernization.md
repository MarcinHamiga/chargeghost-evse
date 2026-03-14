# Simulator Dashboard Modernization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Modernize the simulator dashboard into a clearer, more branded operator surface centered on a status-first session hero while preserving ChargeGhost's signature blue.

**Architecture:** Refactor the existing `SessionDashboard` into a small set of focused presentation widgets: a top-level session hero, a slimmer but richer connector strip, a persistent session context rail, and a cleaner telemetry panel. Keep all business logic and data ownership in `Engine`, `Bridge`, and `SimulatorWidget`; the dashboard remains a read-only projection of current engine state plus user intent signals.

**Tech Stack:** Python, PySide6, Qt Charts, QSS, pytest, pytest-qt

### Task 1: Add regression coverage for the new dashboard hierarchy

**Files:**
- Modify: `tests/test_ui_widgets.py`
- Modify: `src/chargeghost_evse/ui/widgets/session_dashboard.py`

**Step 1: Write the failing tests**

Add tests covering:
- dashboard exposes a dedicated hero section instead of only loose metric cards
- idle connector state renders an idle hero summary and disables start/stop actions correctly
- active session state renders live power, SoC, and duration in the hero summary
- session context metrics remain visible without expanding a details panel

Suggested test names:
- `test_dashboard_exposes_session_hero_sections`
- `test_dashboard_hero_shows_idle_state_when_no_session`
- `test_dashboard_hero_shows_live_session_state`
- `test_dashboard_context_metrics_are_always_visible`

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_ui_widgets.py -k "dashboard and hero or context" -v`

Expected: FAIL because the current dashboard still uses the old metric grid, standalone ID tag card, and collapsible details widget.

**Step 3: Write minimal implementation**

Refactor `SessionDashboard` to introduce:
- a top-level hero container widget
- named sections for connector identity, live metrics, primary actions, and session context
- stable object names and attributes for later QSS styling
- an always-visible context row replacing the old collapsible-details dependency in the main layout

Keep existing signals (`plug_in_clicked`, `start_charging_clicked`, and related actions) unchanged so `SimulatorWidget` wiring does not need behavioral changes.

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_ui_widgets.py -k "dashboard and hero or context" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_ui_widgets.py src/chargeghost_evse/ui/widgets/session_dashboard.py
git commit -m "feat: add simulator dashboard hero layout"
```

### Task 2: Redesign the connector strip as a secondary hardware-switch layer

**Files:**
- Modify: `tests/test_ui_widgets.py`
- Modify: `src/chargeghost_evse/ui/widgets/connector_strip.py`
- Modify: `src/chargeghost_evse/ui/widgets/session_dashboard.py`

**Step 1: Write the failing tests**

Add tests covering:
- connector indicators expose hardware summary text such as voltage/current/phase
- selected connector styling state remains explicit after updates
- charging connectors surface richer state without losing semantic status labels
- connector strip remains a selector, not the primary live-status surface

Suggested test names:
- `test_connector_indicator_shows_hardware_summary`
- `test_connector_strip_preserves_selected_connector_after_status_refresh`
- `test_connector_indicator_retains_status_text_for_non_charging_states`

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_ui_widgets.py -k "connector indicator or connector strip" -v`

Expected: FAIL because connector tiles currently only show ID, status, and optional SoC.

**Step 3: Write minimal implementation**

Update `ConnectorIndicator` to render:
- connector name
- hardware capability summary
- status icon + status label
- optional compact session/status detail only when relevant

Ensure `ConnectorStrip` still owns selection state and does not duplicate hero content. Keep the tile compact enough to support multiple connectors on one row before wrapping becomes necessary.

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_ui_widgets.py -k "connector indicator or connector strip" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_ui_widgets.py src/chargeghost_evse/ui/widgets/connector_strip.py src/chargeghost_evse/ui/widgets/session_dashboard.py
git commit -m "feat: enrich simulator connector strip"
```

### Task 3: Fold ID tag, effective limit, and session metadata into the hero/context surface

**Files:**
- Modify: `tests/test_ui_widgets.py`
- Modify: `src/chargeghost_evse/ui/widgets/session_dashboard.py`

**Step 1: Write the failing tests**

Add tests covering:
- ID tag input is rendered inside the hero or adjacent context section rather than as a standalone card
- applied ID tag placeholder remains accurate for the selected connector
- effective delivered power and session metadata stay visible for the selected connector only
- transaction information clears when a different connector is selected

Suggested test names:
- `test_dashboard_embeds_id_tag_controls_in_hero`
- `test_dashboard_id_tag_placeholder_tracks_selected_connector`
- `test_dashboard_context_clears_transaction_when_switching_connectors`

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_ui_widgets.py -k "id tag or transaction or delivered power" -v`

Expected: FAIL because the current layout still separates ID tag and hides metadata behind the details block.

**Step 3: Write minimal implementation**

Restructure `SessionDashboard` so that:
- `IdTagInput` lives in the hero/context region
- effective limit, plug state, transaction ID, meter reading, and hardware data render as persistent secondary information
- no extra user action is required to inspect session context

Keep `_compute_effective_power_kw()` as the single source for delivered power display.

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_ui_widgets.py -k "id tag or transaction or delivered power" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_ui_widgets.py src/chargeghost_evse/ui/widgets/session_dashboard.py
git commit -m "feat: unify simulator session context and id tag controls"
```

### Task 4: Modernize the telemetry panel into a cleaner diagnostic surface

**Files:**
- Modify: `tests/test_ui_widgets.py`
- Modify: `src/chargeghost_evse/ui/widgets/session_dashboard.py`
- Modify: `src/chargeghost_evse/ui/styles/colors.py`

**Step 1: Write the failing tests**

Add tests covering:
- telemetry panel exposes a titled frame or object name for dedicated styling
- chart panel and hero panel use distinct object names for surface hierarchy
- chart clears when connector selection changes but preserves rolling updates otherwise

Suggested test names:
- `test_dashboard_exposes_named_telemetry_panel`
- `test_dashboard_clears_chart_when_selected_connector_changes`

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_ui_widgets.py -k "telemetry or chart" -v`

Expected: FAIL because the chart currently lives as a bare frame with limited hierarchy hooks.

**Step 3: Write minimal implementation**

Update `TelemetryChart` and the surrounding dashboard layout to:
- wrap the chart in a diagnostic panel with title/subtitle labels
- expose dedicated object names for chart frame, title, subtitle, and scale labels
- extend `colors.py` with a few dashboard-specific blue-tinted surface tokens without replacing the existing brand blue

Keep chart behavior lightweight; do not add extra data series or heavy animation beyond the current rolling line.

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_ui_widgets.py -k "telemetry or chart" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_ui_widgets.py src/chargeghost_evse/ui/widgets/session_dashboard.py src/chargeghost_evse/ui/styles/colors.py
git commit -m "feat: refine simulator telemetry surface"
```

### Task 5: Rework dashboard QSS to establish stronger hierarchy while preserving ChargeGhost blue

**Files:**
- Modify: `src/chargeghost_evse/ui/styles/e_mobility.qss`
- Modify: `src/chargeghost_evse/ui/styles/colors.py`
- Modify: `src/chargeghost_evse/ui/widgets/session_dashboard.py`
- Modify: `src/chargeghost_evse/ui/widgets/connector_strip.py`

**Step 1: Write the failing tests**

Add tests covering:
- new hero, telemetry, connector, and context surfaces expose stable object names and state properties
- charging and idle states set different semantic properties that QSS can target

Suggested test names:
- `test_dashboard_surfaces_expose_theme_object_names`
- `test_dashboard_hero_exposes_state_properties_for_styling`

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_ui_widgets.py -k "theme object names or styling" -v`

Expected: FAIL because the current layout does not expose enough explicit styling hooks for the new hierarchy.

**Step 3: Write minimal implementation**

Update QSS to introduce:
- a branded session hero surface with restrained blue glow/highlight
- quieter secondary surfaces for telemetry and context
- denser connector tiles with clearer active/inactive styling
- stronger value typography and quieter labels
- state-based button emphasis so only the relevant action reads as primary

Preserve the existing ChargeGhost blue as the core accent. Use success/warning/danger only as state colors, not as competing brand colors.

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_ui_widgets.py -k "theme object names or styling" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/chargeghost_evse/ui/styles/e_mobility.qss src/chargeghost_evse/ui/styles/colors.py src/chargeghost_evse/ui/widgets/session_dashboard.py src/chargeghost_evse/ui/widgets/connector_strip.py tests/test_ui_widgets.py
git commit -m "feat: restyle simulator dashboard surfaces"
```

### Task 6: Verify the complete simulator dashboard redesign

**Files:**
- Verify only

**Step 1: Run targeted widget regressions**

Run: `poetry run pytest tests/test_ui_widgets.py -v`

Expected: PASS

**Step 2: Run related GUI regressions**

Run: `poetry run pytest tests/test_update_dialog.py tests/test_update_flow.py tests/test_manual_update_check.py -v`

Expected: PASS

**Step 3: Run lint on modified UI files**

Run: `poetry run ruff check src/chargeghost_evse/ui tests/test_ui_widgets.py`

Expected: PASS

**Step 4: Manual smoke test the simulator UI**

Run: `PYTHONPATH=src python3 -m chargeghost_evse.main`

Verify:
- hero panel reads clearly in idle and active states
- connector switching updates hero and chart correctly
- ChargeGhost blue remains the primary branded accent
- no clipped controls appear at the default 1100x700 window size

**Step 5: Commit**

```bash
git add docs/plans/2026-03-14-simulator-dashboard-modernization.md
git commit -m "docs: add simulator dashboard modernization plan"
```
