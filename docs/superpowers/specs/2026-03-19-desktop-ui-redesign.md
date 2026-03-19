# ChargeGhost EVSE — Desktop UI Redesign

**Date:** 2026-03-19
**Status:** Approved for implementation

## Goals

Rework the PySide6 UI to feel native on 16:9 desktop screens (FHD 1920×1080 primary target, scaling gracefully to QHD 2560×1440 and UHD 3840×2160). Pack information by width rather than by height — eliminate the mobile-like vertical stacking in favour of horizontal panels that leverage the full screen width.

## Non-Goals

- No changes to Engine, Bridge, OCPP Adapter, or any domain logic.
- No changes to signals, slots, or cross-thread wiring.
- No redesign of the Manual mode beyond applying the same sidebar and log-panel changes.
- No redesign of the ModeSelectWidget (landing screen).
- No new features — purely layout and sizing.

## Approach

**Targeted layout surgery**: reorganise `QLayout` hierarchies and widget sizing inside existing widgets. Preserve all leaf widgets (MetricCard, TelemetryChart, IdTagInput, LogPanel, etc.) and their internal logic untouched. Only layout wiring, size policies, minimum sizes, and containing structure change.

---

## Design Decisions

### 1. Window sizing

| Property | Current | New |
|---|---|---|
| Minimum size | 1100 × 700 | **1280 × 720** |
| Default/startup size | 1100 × 700 | **1600 × 900** |
| Target resolution | — | 1920 × 1080 |

The `MainWindow` minimum and default sizes are updated. No maximum is set — the layout must fill any reasonable desktop size gracefully.

### 2. Top-level layout topology

Current structure (vertical splitter):
```
QVBoxLayout
  QSplitter (vertical, 4:1)
    QStackedWidget  ← modes
    CollapsibleLogPanel  ← bottom strip
  QStatusBar
```

New structure (log panel owned by each mode widget):
```
MainWindow central widget
  QVBoxLayout
    QStackedWidget  ← modes (ModeSelect / Simulator / Manual)
      SimulatorWidget
        QHBoxLayout
          _Sidebar (48–180px)
          QVBoxLayout (content column)
            ConnectorStatusBar (38px fixed height)
            QStackedWidget (Dashboard / Settings / Keys / Profiles)
          LogSidePanel (32–340px, owned by SimulatorWidget)
      ManualWidget
        QHBoxLayout
          _ManualSidebar (48–180px)
          manual controls panel
          LogSidePanel (32–340px, owned by ManualWidget)
    QStatusBar
```

The vertical splitter and `CollapsibleLogPanel` are **removed**. Each mode widget (`SimulatorWidget`, `ManualWidget`) owns its own `LogSidePanel` instance as the rightmost child in its `QHBoxLayout`. The `QStatusBar` remains at the bottom of `MainWindow`.

### 3. Sidebar — collapsible icon-only

**Current:** `QWidget` fixed at 200px wide, `QVBoxLayout` of `QPushButton` items with icon + text label.

**New behaviour:**
- **Collapsed (default):** 48px wide. Buttons show icon only (no text). A small "expand" chevron button at the bottom.
- **Expanded:** 180px wide. Buttons show icon + text label (same as today). An "collapse" chevron replaces the expand button.
- **Animation:** `QPropertyAnimation` on `maximumWidth` and `minimumWidth`, 180ms, `QEasingCurve.OutCubic`. Width animates between 48 and 180.
- **State persistence:** Collapsed/expanded state is saved to `AppSettings`. Add `SETTING_SIDEBAR_EXPANDED = "ui/sidebarExpanded"` class constant and a typed `sidebar_expanded: bool` property + setter following the existing `log_panel_expanded` pattern.
- **Button layout:** Existing `QPushButton` nav buttons are converted to `QToolButton`. `setToolButtonStyle` is called with `Qt.ToolButtonIconOnly` when collapsed, `Qt.ToolButtonTextBesideIcon` when expanded. Tooltip set to the label text (always shown on hover — useful in collapsed state).
- **Logo/brand area:** 48×48 icon-only when collapsed, 180×48 with "ChargeGhost" text when expanded.

**Implementation note:** The sidebar widget class is `_Sidebar` inside `app.py`. Its `toggle_expand()` method drives the animation and style update.

**Manual mode sidebar:** `ManualWidget` has its own simpler two-button sidebar. It does **not** share the `_Sidebar` class — instead a `_ManualSidebar` inner class is created inside `app.py` using the same 48px/180px `QPropertyAnimation` pattern and the same `SETTING_SIDEBAR_EXPANDED` key (both sidebars share the same expand/collapse state).

### 4. Connector status bar (new widget)

A new `ConnectorStatusBar(QWidget)` is inserted **above** the content `QStackedWidget` inside `SimulatorWidget`. It is always visible regardless of which tab (Dashboard, Settings, etc.) is active.

**Layout:** `QHBoxLayout`, height fixed at 38px.

**Contents (left → right):**
- Label: "CONNECTORS" (small caps, muted)
- One `ConnectorPill` per connector — a compact pill widget (≈100px wide) showing:
  - Coloured status dot (matches existing status colour palette)
  - Connector ID + status string (e.g. "1 · Charging")
  - Clicking a pill selects that connector (delegates to same logic as old `ConnectorStrip`)
- `QFrame` separator
- Right-aligned live stats for the **active session** (hidden when idle):
  - Power (kW) · SoC (%) · Duration

**Data interface:** `ConnectorStatusBar` exposes two public update methods called by `QtSignalBridge` slots:
- `update_connector(connector_id: int, status: str, soc: Optional[float])` — called on the same `connector_status_changed` signal that drove `ConnectorStrip`. Updates the corresponding `ConnectorPill` state and colour.
- `update_session_stats(power_kw: float, soc: float, duration_str: str)` — called by the same engine slots that updated the old hero metric labels. Shows the right-side stat row when called with non-zero power; calling with `power_kw=0.0` (on `session_stopped`) hides the stat row.

`ConnectorStatusBar` replaces `ConnectorStrip` as the connector selector. `ConnectorStrip` and `ConnectorIndicator` are **deleted** after migration.

**ConnectorPill animation:** The existing `ConnectorIndicator` pulse animation (`QPropertyAnimation` on a custom `pulseOpacity` Qt property) is **not carried forward** into `ConnectorPill`. `ConnectorPill` uses a static coloured dot — the per-connector charging state is already visible in the bar's stat row and in the dashboard's controls panel state badge. This keeps the status bar compact and avoids per-connector animation overhead.

### 5. Dashboard — horizontal two-column layout

`SessionDashboard` is restructured from a vertical `QVBoxLayout` to a horizontal `QHBoxLayout` with two panels:

#### Left: Controls panel (`QWidget`, `setMinimumWidth(180)`, `setMaximumWidth(280)`)

Contains (top → bottom, `QVBoxLayout`):

1. **Session state badge** — small coloured badge showing current state text ("Idle", "Plugged", "Charging") and connector ID. Replaces the large "Active Session" hero header.
2. **Actions group** — all four action buttons (`Plug In`, `Start Charging`, `Stop Charging`, `Unplug`) plus `Suspend EV` / `Resume Charging`. Arranged as:
   - Plug In (full width)
   - Start Charging (full width)
   - Stop / Unplug (side-by-side, 50/50)
   - Suspend EV / Resume (full width, mutually exclusive visibility)
3. **ID Tag input** — `IdTagInput` widget (unchanged internally)
4. **Effective limit display** — small label + value row
5. `QSpacerItem` (expanding) to push content to top

Size policy: `Fixed` horizontal (respects the width set by parent), `Expanding` vertical.

#### Right: Data panel (flex, `QWidget`, `Expanding` both axes)

Contains (top → bottom, `QVBoxLayout`):

1. **Metric row** — `QHBoxLayout` of 4 `MetricCard` widgets: Power, SoC, Duration, Energy Charged. Each card is `Expanding` horizontally, fixed height ~64px.
2. **Telemetry chart** — `TelemetryChart`, takes all remaining vertical space (`Expanding` vertical).
3. **Charging progress row** — label + `QProgressBar` + percentage, fixed height ~20px.
4. **Context rail** — `QHBoxLayout` of 5 `ContextChip` widgets: Transaction ID, Voltage, Current, Total Meter, Phases. Fixed height ~42px.

`ContextChip` is a new minimal widget (same concept as existing `MetricCard` but smaller — no icon, compact label/value).

**Removed from dashboard:**
- The "sessionHero" `QFrame` (hero frame with big title, 3-metric grid, 2×2 button grid) — replaced by the left control panel + connector bar.
- The existing 7:3 `QSplitter` — replaced by the two-column layout above.
- `ConnectorStrip` — replaced by `ConnectorStatusBar`.

### 6. Log side panel

A new `LogSidePanel(QWidget)` wraps the existing `LogPanel` with a header.

**Collapsed state (default):**
- A 32px-wide vertical tab strip on the right edge of the owning mode widget.
- Contains: log icon, rotated "Log" label, unread-count badge.
- Clicking anywhere on the tab opens the panel.
- The tab widget (`_LogTab`) is hidden when the panel is expanded, shown when collapsed.
- **Unread-count badge:** `LogSidePanel` exposes `increment_unread()` (called by the owning widget whenever a log entry arrives while the panel is collapsed) and `clear_unread()` (called when the panel is opened). The badge label is updated accordingly.

**Expanded state:**
- 340px wide. No `QSplitter` — the panel is a fixed-width `QWidget` whose `maximumWidth` is animated. The 32px tab widget is **hidden** (`setVisible(False)`) when the panel is expanded; the header's Close (✕) button takes the role of the collapse trigger.
- Header bar (32px): log icon, "Activity Log" title, entry count badge, Shallow/Deep toggle button, Clear button, Close (✕) button.
- Body: existing `LogPanel` (scroll area with log entries) — no changes to `LogPanel`, `CollapsibleLogEntry`, or logging infrastructure.
- Animation: `QPropertyAnimation` on `maximumWidth` and `minimumWidth`, 200ms, `OutCubic`. Collapsed: both at 32px (tab visible). Expanded: both at 340px (tab hidden, header visible).

**State persistence:** Reuse the existing `AppSettings.log_panel_expanded` property (key `"ui/logPanelExpanded"`). The semantic is the same — was the log panel open on last exit. No new key is needed.

**Toggle triggers:**
- Clicking the 32px collapsed tab.
- Clicking the Close (✕) button in the expanded header.
- Backtick (`` ` ``) keyboard shortcut — repointed from `CollapsibleLogPanel` to `LogSidePanel.toggle()`.
- `F1` keyboard shortcut — same repointing.
- The `QStatusBar` "Logs" button is **removed** (replaced by the tab strip; a separate button is redundant).

The existing `CollapsibleLogPanel` widget is **deleted** after migration.

### 7. Secondary panels (Settings, OCPP Keys, Profiles)

These panels are already full-height inside the content stack. With the new layout giving them more horizontal space (no tall hero frame stealing vertical room), minimal changes are needed:

- **SettingsPanel:** Convert the connector management cards from a single column to a `QGridLayout` (2 columns when `self.width() > 700`, 1 column otherwise). Override `resizeEvent` on `SettingsPanel` itself — compare against `self.width()`, not the window width, since sidebar and log panel both reduce available space. Everything else unchanged.
- **ConfigKeysPanel:** The OCPP keys table already uses a `QTableWidget` / list — it will naturally use full width. Ensure `setColumnStretch` gives the value column the most space. No structural changes needed.
- **ChargingProfilesPanel:** Already a table-like layout. Ensure it gets `Expanding` size policy. No structural changes needed.

### 8. Manual mode

`ManualWidget` gets the same sidebar behaviour (it has its own simpler sidebar) and the log-panel replacement. The manual controls panel and activity log are already side-by-side horizontally — this structure is **kept as-is**, just replacing `CollapsibleLogPanel` at the bottom with `LogSidePanel` on the right.

---

## Files Modified

| File | Change |
|---|---|
| `ui/app.py` | Window min/default size; `_Sidebar` collapse animation; `SimulatorWidget` layout replaces vertical splitter with horizontal body + `LogSidePanel`; insert `ConnectorStatusBar` above content stack; `ManualWidget` log panel swap |
| `ui/session_dashboard.py` | `SessionDashboard` layout: vertical stack → horizontal (controls left, data right); remove hero frame; add `ContextChip`; update size policies |
| `ui/collapsible_log.py` | Delete (replaced by `LogSidePanel`) |
| `ui/connector_strip.py` | Delete (replaced by `ConnectorStatusBar`) |
| `ui/log_side_panel.py` | **New file** — `LogSidePanel` widget (tab + animated panel wrapping `LogPanel`) |
| `ui/connector_status_bar.py` | **New file** — `ConnectorStatusBar` + `ConnectorPill` widgets |
| `ui/bridge.py` | Update any references to `ConnectorStrip`/`CollapsibleLogPanel` signals to point to new widgets |
| `ui/styles/e_mobility.qss` | Add styles for sidebar collapsed/expanded states, `ConnectorStatusBar`, `ConnectorPill`, `LogSidePanel` tab and header, `ContextChip` |
| `ui/widgets/app_settings.py` | Add `SETTING_SIDEBAR_EXPANDED = "ui/sidebarExpanded"` constant and typed `sidebar_expanded: bool` property + setter following existing pattern. `log_panel_expanded` key/property is reused for `LogSidePanel` — no new field needed. |

## Files Unchanged

Everything under `engine/`, `bridge/`, `ocpp_adapter/`, `util/` — and all leaf UI widgets: `LogPanel`, `LogEntry`, `TelemetryChart`, `MetricCard`, `IdTagInput`, `SettingsPanel`, `ConfigKeysPanel`, `ChargingProfilesPanel`, `ConnectorPanel`, `UpdateDialog`, `UpdateStatusChip`, `ToastManager`, `icons.py`, `colors.py`.

---

## Key Constraints Carried Forward

- All Qt UI operations on main thread (unchanged).
- `opacity` not used in QSS — `rgba()` for semi-transparent states (unchanged).
- `QPropertyAnimation` targets `maximumWidth`/`minimumWidth` (not `geometry`) to avoid issues with layout managers.
- Tab/space indentation: tabs (per CLAUDE.md).
- Line length: 100 chars max.
- Type hints on all new code.
