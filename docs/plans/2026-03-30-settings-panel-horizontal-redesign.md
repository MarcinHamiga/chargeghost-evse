# Settings Panel Horizontal Redesign Implementation Plan

**Goal:** Redesign the simulator settings panel so it uses horizontal screen real estate like the dashboard, with a compact left settings rail and a dominant right-side connector workspace, while preserving all existing behavior and wiring.

**Architecture:** Keep the current `SettingsPanel`, `ConnectorPanel`, config model, and signal flow intact. This is a layout and presentation refactor only: reorganize `QLayout` hierarchies, introduce settings-specific card surfaces, and add responsive collapse behavior. The connector editor remains the main workspace and should receive enough width to use its existing multi-column reflow.

**Tech Stack:** Python, PySide6, QSS, pytest

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `tests/test_settings_panel.py` | Focused regression coverage for layout structure and responsive behavior |
| Modify | `src/chargeghost_evse/ui/widgets/settings_panel.py` | Rework settings into header + left rail + right workspace layout |
| Modify | `src/chargeghost_evse/ui/styles/e_mobility.qss` | Add settings page shells, cards, header, and responsive visual hierarchy |
| Possible minor modify | `src/chargeghost_evse/ui/widgets/connector_panel.py` | Optional spacing or threshold tuning if the new workspace exposes layout issues |

---

## Design Direction

- Use a workstation-style layout, not a long preferences form.
- Make the connector area the dominant surface because it benefits most from width.
- Keep the left rail compact and readable with strong grouping:
  - Connection
  - Station identity
  - Simulation mode
  - Save action
- Preserve the current dark theme and teal accent, but align the settings page more closely with the dashboard's card rhythm and spacing.

### Intended layout

```text
[ Settings header / helper copy / Save Configuration ]

[ Left rail: fixed-ish width ]   [ Right workspace: flexible ]
- Connection                     - Connector Management
- Station Identity               - Connector cards
- Simulation Mode                - Add connector button
- Save / helper note             - Empty state when no connectors
```

### Responsive behavior

- Wide screens: 2-column layout with left rail + right workspace
- Medium screens: same structure, but tighter spacing and rail width
- Narrow screens: collapse to a single vertical stack, with connector management moving below the rail

---

## Chunk 1: Add regression coverage for settings layout

### Task 1: Add focused tests for the new settings shell

**Files:**
- Create: `tests/test_settings_panel.py`

- [ ] **Step 1: Write the failing tests**

Add tests covering:
- settings panel exposes a distinct left rail and right workspace
- settings panel exposes a page header and a dedicated primary save action
- connection and identity sections remain present after the refactor
- connector workspace remains mounted inside settings and is not buried in a long vertical form
- narrow widths collapse the layout into stacked mode
- wide widths restore split mode

Suggested test names:
- `test_settings_panel_exposes_split_layout_sections`
- `test_settings_panel_exposes_prominent_save_action`
- `test_settings_panel_keeps_connection_and_identity_sections`
- `test_settings_panel_embeds_connector_workspace`
- `test_settings_panel_switches_to_stacked_mode_when_narrow`
- `test_settings_panel_returns_to_split_mode_when_wide`

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
poetry run pytest tests/test_settings_panel.py -v
```

Expected: FAIL because the current `SettingsPanel` is still a single vertical scroll stack and does not expose the new shell structure or responsive mode.

- [ ] **Step 3: Implement the minimum structure required**
- Add stable object names and/or properties in `SettingsPanel` for:
  - page root
  - page header
  - settings rail
  - connector workspace
  - layout mode (`split` / `stacked`)
- Ensure the tests assert structure, not pixel-perfect geometry.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
poetry run pytest tests/test_settings_panel.py -v
```

Expected: PASS

---

## Chunk 2: Refactor `SettingsPanel` into a dashboard-style shell

### Task 2: Replace the vertical form stack with a horizontal workspace

**Files:**
- Modify: `src/chargeghost_evse/ui/widgets/settings_panel.py`

- [ ] **Step 1: Introduce a page shell**
- Keep the `QScrollArea`, but replace the single `QVBoxLayout` content structure with:
  - page header
  - content body
  - left rail container
  - right workspace container

Recommended structure:
- root `QVBoxLayout`
- scroll area
- content widget
- header frame
- body `QHBoxLayout`
- left rail `QWidget`/`QFrame`
- right workspace `QWidget`/`QFrame`

- [ ] **Step 2: Move the primary action into the page shell**
- Promote `Save Configuration` so it reads like a page-level CTA, not the last form element in a scroll list.
- Keep `save_config_clicked` unchanged.
- Keep validation behavior unchanged: invalid URL still blocks save.

- [ ] **Step 3: Keep all data and signals intact**
- Do not change:
  - `set_engine()`
  - `set_config()`
  - `_populate_fields()`
  - `set_connector_callbacks()`
  - `_on_save_config()`
  - `get_url()`
  - `rebuild_connector_cards()`

- [ ] **Step 4: Add helper builders if needed**
Recommended private methods:
- `_build_header()`
- `_build_settings_rail()`
- `_build_connector_workspace()`
- `_set_layout_mode()`
- `_update_layout_mode()`

Keep the refactor readable; avoid packing the entire layout into one large `_setup_ui()` block.

---

## Chunk 3: Reorganize the settings controls into compact cards

### Task 3: Repack fields to use width better inside the rail

**Files:**
- Modify: `src/chargeghost_evse/ui/widgets/settings_panel.py`

- [ ] **Step 1: Replace plain `QGroupBox` stacking with settings cards**
Use card-like framed sections or styled group containers for:
- Connection
- Station Identity
- Simulation

Preferred content structure:

**Connection**
- WebSocket URL on its own row
- OCPP ID and Password side-by-side
- OCPP Version and Skip TLS Verification in a compact controls row

**Station Identity**
- Vendor and Model side-by-side

**Simulation**
- Multi-EVSE mode as a focused option
- Preserve existing tooltip/help

- [ ] **Step 2: Keep form semantics clear**
- Labels stay explicit
- Inputs remain keyboard-friendly
- Validation messaging remains visible
- Avoid over-compressing fields into unclear dense rows

- [ ] **Step 3: Add contextual copy where useful**
Examples:
- Connection helper copy near the URL section
- Small note near save CTA clarifying that connector edits need saving to persist

Keep helper text minimal and secondary.

---

## Chunk 4: Make the connector area the dominant right-side workspace

### Task 4: Elevate connector management into the main content area

**Files:**
- Modify: `src/chargeghost_evse/ui/widgets/settings_panel.py`
- Possible minor modify: `src/chargeghost_evse/ui/widgets/connector_panel.py`

- [ ] **Step 1: Give connector management its own workspace surface**
- Mount `ConnectorPanel` inside a dedicated right-side card or workspace container.
- Add a section title and optional short support text.
- Let the workspace stretch and own the majority of horizontal width.

- [ ] **Step 2: Preserve `ConnectorPanel` behavior**
- Keep add/apply/remove callbacks unchanged.
- Keep empty state behavior unchanged.
- Reuse its existing grid reflow logic.

- [ ] **Step 3: Tune only if necessary**
If the new workspace exposes layout rough edges, make minor follow-up improvements in `ConnectorPanel` such as:
- spacing adjustments
- column threshold tuning
- margins cleanup

Do not rewrite connector logic unless the new shell clearly requires it.

---

## Chunk 5: Add responsive layout switching

### Task 5: Collapse the split layout cleanly on smaller widths

**Files:**
- Modify: `src/chargeghost_evse/ui/widgets/settings_panel.py`

- [ ] **Step 1: Add layout mode tracking**
Expose a property or internal state for:
- `split`
- `stacked`

Recommended trigger:
- switch to stacked when the panel width is below a threshold in roughly the `1000-1150px` range
- use actual widget proportions during implementation to choose the final threshold

- [ ] **Step 2: Update layout on resize**
- Override `resizeEvent()`
- Re-parent or reorder rail/workspace containers as needed
- Avoid rebuilding controls on every resize
- Avoid any layout flicker or duplicate widget creation

- [ ] **Step 3: Keep the connector workspace usable in both modes**
- In split mode, it should expand enough for connector cards to reflow into two columns
- In stacked mode, it should move below the rail and remain fully usable

---

## Chunk 6: Add settings-specific QSS

### Task 6: Style the settings page to match the dashboard's visual hierarchy

**Files:**
- Modify: `src/chargeghost_evse/ui/styles/e_mobility.qss`

- [ ] **Step 1: Add settings page hooks**
Recommended object names / properties:
- `settingsPage`
- `settingsHeader`
- `settingsHeaderTitle`
- `settingsHeaderBody`
- `settingsRail`
- `settingsWorkspace`
- `settingsCard`
- `settingsCardTitle`
- `settingsCardHelp`
- `settingsSaveBar`

Exact names may change, but keep them stable and intentional.

- [ ] **Step 2: Establish hierarchy**
- Stronger page header
- Consistent card padding and spacing
- Better distinction between rail and workspace
- Clear prominence for the save action
- Secondary styling for helper text

- [ ] **Step 3: Preserve theme consistency**
- Stay within the current ChargeGhost dark palette
- Reuse the existing teal accent
- Match dashboard card borders/radii/spacing where practical
- Avoid introducing a second visual language just for settings

---

## Verification

### Functional checks
- [ ] URL validation still blocks save when invalid
- [ ] Existing config values still populate correctly
- [ ] Save still emits `save_config_clicked`
- [ ] Connector add/apply/remove still work
- [ ] `rebuild_connector_cards()` still refreshes the connector workspace correctly

### Layout checks
- [ ] Wide window shows left rail + right connector workspace
- [ ] Narrow window collapses to stacked layout without clipping
- [ ] Connector cards use available width and reflow correctly
- [ ] Save action stays visible and clearly associated with the page

### Commands
Run:
```bash
poetry run pytest tests/test_settings_panel.py tests/test_connector_panel.py tests/test_ui_widgets.py -v
```

Then launch the app and inspect the settings view manually:
```bash
poetry run dev
```

Check:
- wide desktop width
- medium resized window
- narrow width where stacked mode activates

---

## Acceptance Criteria

- The settings screen no longer reads as a single long vertical form.
- The layout uses horizontal space intentionally, similar in spirit to the dashboard.
- The left rail contains compact configuration controls without feeling cramped.
- The right side is clearly the main connector workspace.
- Responsive collapse works cleanly at narrower sizes.
- Existing settings behavior, validation, and connector callbacks remain unchanged.

---

## Non-Goals

- No changes to `SimulationConfig` structure
- No changes to engine or bridge logic
- No new settings fields
- No connector business logic rewrite
- No theme overhaul beyond the settings panel presentation

---

## Risks and Notes

- The biggest implementation risk is responsive re-parenting causing layout duplication or orphaned widgets. Keep containers stable and only move high-level sections.
- Avoid over-compressing fields in the left rail; readability matters more than maximum density.
- The connector workspace should remain the primary surface. If the rail starts growing too large, reduce helper copy before shrinking the workspace.
- Preserve the current save semantics so the redesign remains low-risk behaviorally.
