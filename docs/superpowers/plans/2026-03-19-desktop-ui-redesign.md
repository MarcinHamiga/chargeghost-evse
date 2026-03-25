# Desktop UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganise the PySide6 UI layout to target FHD (1920×1080) desktop screens — horizontal information density, collapsible sidebar, connector status bar, horizontal dashboard split, and a toggleable right-side log panel.

**Architecture:** Targeted layout surgery only — `QLayout` hierarchies and widget sizes are rearranged inside existing widgets; all domain logic, signals, and leaf widgets are untouched. Two new widget files are added (`log_side_panel.py`, `connector_status_bar.py`); two old widget files are deleted (`collapsible_log.py`, `connector_strip.py`).

**Tech Stack:** PySide6 (Qt 6), QPropertyAnimation, QToolButton, QHBoxLayout/QVBoxLayout, QSS

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `src/chargeghost_evse/ui/widgets/log_side_panel.py` | `LogSidePanel` — 32px tab ↔ 340px animated log panel |
| Create | `src/chargeghost_evse/ui/widgets/connector_status_bar.py` | `ConnectorStatusBar` + `ConnectorPill` — 38px horizontal connector status bar |
| Modify | `src/chargeghost_evse/ui/widgets/app_settings.py` | Add `sidebar_expanded` key + typed property |
| Modify | `src/chargeghost_evse/ui/widgets/session_dashboard.py` | Rework to horizontal two-column layout; remove hero frame, `ConnectorStrip`, dead Signal, `CollapsibleDetails` |
| Modify | `src/chargeghost_evse/ui/app.py` | Window size; sidebar collapse; `SimulatorWidget`/`ManualWidget` layout; wire new widgets |
| Modify | `src/chargeghost_evse/ui/styles/e_mobility.qss` | Add QSS for sidebar icon-only, `ConnectorStatusBar`, `LogSidePanel`, `ContextChip` |
| Modify | `src/chargeghost_evse/ui/widgets/connector_panel.py` | Replace `cards_container` VBox with responsive `QGridLayout` |
| Delete | `src/chargeghost_evse/ui/widgets/collapsible_log.py` | Replaced by `LogSidePanel` |
| Delete | `src/chargeghost_evse/ui/widgets/connector_strip.py` | Replaced by `ConnectorStatusBar` |

---

## Chunk 1: New widgets — LogSidePanel and ConnectorStatusBar

### Task 1: `LogSidePanel` widget

**Files:**
- Create: `src/chargeghost_evse/ui/widgets/log_side_panel.py`
- Create: `tests/test_log_side_panel.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_log_side_panel.py
import pytest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication
import sys

@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app

def test_log_side_panel_starts_collapsed(qt_app):
    from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel
    panel = LogSidePanel()
    assert not panel.is_open()

def test_log_side_panel_toggle_opens(qt_app):
    from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel
    panel = LogSidePanel()
    panel.toggle()
    assert panel.is_open()

def test_log_side_panel_toggle_closes(qt_app):
    from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel
    panel = LogSidePanel()
    panel.toggle()
    panel.toggle()
    assert not panel.is_open()

def test_unread_badge_increments(qt_app):
    from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel
    panel = LogSidePanel()
    panel.increment_unread()
    panel.increment_unread()
    assert panel._unread_count == 2

def test_clear_unread_resets(qt_app):
    from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel
    panel = LogSidePanel()
    panel.increment_unread()
    panel.clear_unread()
    assert panel._unread_count == 0

def test_log_message_delegates(qt_app):
    from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel
    panel = LogSidePanel()
    panel._log_panel.log_message = MagicMock()
    panel.log_message("hello")
    panel._log_panel.log_message.assert_called_once_with("hello")
```

- [ ] **Step 2: Run tests, verify they all fail**

```bash
poetry run pytest tests/test_log_side_panel.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `log_side_panel` doesn't exist yet.

- [ ] **Step 3: Implement `LogSidePanel`**

Create `src/chargeghost_evse/ui/widgets/log_side_panel.py`:

```python
import logging
from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
	QHBoxLayout,
	QLabel,
	QPushButton,
	QVBoxLayout,
	QWidget,
)

from chargeghost_evse.ui.styles import colors
from chargeghost_evse.ui.widgets.icons import get_icon, get_icon_html
from chargeghost_evse.ui.widgets.log_panel import LogPanel


COLLAPSED_WIDTH = 32
EXPANDED_WIDTH = 340
ANIM_DURATION_MS = 200


class _LogTab(QWidget):
	"""32px vertical tab shown when the panel is collapsed."""

	clicked = Signal()

	def __init__(self, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)
		self.setObjectName("logSideTab")
		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		self.setCursor(Qt.CursorShape.PointingHandCursor)
		self.setFixedWidth(COLLAPSED_WIDTH)

		layout = QVBoxLayout(self)
		layout.setContentsMargins(4, 12, 4, 12)
		layout.setSpacing(6)
		layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

		icon_label = QLabel()
		icon_label.setTextFormat(Qt.TextFormat.RichText)
		icon_label.setText(get_icon_html("terminal", colors.TEXT_MUTED, 14))
		icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
		layout.addWidget(icon_label)

		# Spacer — "Log" text is drawn in paintEvent (rotated 90° CCW)
		layout.addSpacing(24)

		self._badge = QLabel("")
		self._badge.setObjectName("logSideBadge")
		self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
		self._badge.hide()
		layout.addWidget(self._badge)

		layout.addStretch()

	def paintEvent(self, event) -> None:
		super().paintEvent(event)
		# Draw "Log" rotated 90° counter-clockwise (reads bottom-to-top).
		# QLabel text rotation is not possible via QSS, so we paint it manually.
		painter = QPainter(self)
		painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
		painter.setPen(QColor("#6e7681"))
		font = painter.font()
		font.setPixelSize(9)
		painter.setFont(font)
		# Approximate centre of the space between the icon area (~36px from top)
		# and the badge at the bottom.
		text_center_x = self.width() / 2
		text_center_y = 54  # midpoint of the 24px spacer + margins
		painter.translate(text_center_x, text_center_y)
		painter.rotate(-90)
		fm = painter.fontMetrics()
		rect = QRect(-30, -self.width() // 2, 60, self.width())
		painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Log")
		painter.end()

	def set_count(self, count: int) -> None:
		if count > 0:
			self._badge.setText(str(count) if count < 100 else "99+")
			self._badge.show()
		else:
			self._badge.hide()

	def mousePressEvent(self, event) -> None:
		if event.button() == Qt.MouseButton.LeftButton:
			self.clicked.emit()
		super().mousePressEvent(event)


class LogSidePanel(QWidget):
	"""
	Toggleable right-side log panel.

	Collapsed: 32px tab strip with log icon, label, unread badge.
	Expanded: 340px panel with header controls and LogPanel body.
	Animation: QPropertyAnimation on maximumWidth/minimumWidth.
	"""

	log_mode_toggled = Signal(bool)

	def __init__(self, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)
		self.setObjectName("logSidePanel")
		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

		self._is_open = False
		self._unread_count = 0
		self._entry_count = 0
		self._animation: Optional[QPropertyAnimation] = None

		self._setup_ui()
		self._set_collapsed_geometry()

	def _setup_ui(self) -> None:
		layout = QHBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)

		# --- Collapsed tab ---
		self._tab = _LogTab()
		self._tab.clicked.connect(self.toggle)
		layout.addWidget(self._tab)

		# --- Expanded content ---
		self._panel = QWidget()
		self._panel.setObjectName("logSidePanelContent")
		self._panel.hide()
		panel_layout = QVBoxLayout(self._panel)
		panel_layout.setContentsMargins(0, 0, 0, 0)
		panel_layout.setSpacing(0)

		# Header
		header = QWidget()
		header.setObjectName("logSidePanelHeader")
		header.setFixedHeight(32)
		header_layout = QHBoxLayout(header)
		header_layout.setContentsMargins(10, 0, 10, 0)
		header_layout.setSpacing(6)

		icon_label = QLabel()
		icon_label.setTextFormat(Qt.TextFormat.RichText)
		icon_label.setText(get_icon_html("terminal", colors.ACCENT_TEAL, 14))
		header_layout.addWidget(icon_label)

		title = QLabel("Activity Log")
		title.setObjectName("logSidePanelTitle")
		header_layout.addWidget(title)

		self._count_label = QLabel("")
		self._count_label.setObjectName("logSideCountLabel")
		header_layout.addWidget(self._count_label)

		header_layout.addStretch()

		self.btn_log_mode = QPushButton("Deep")
		self.btn_log_mode.setObjectName("btnLogMode")
		self.btn_log_mode.setCheckable(True)
		self.btn_log_mode.setFlat(True)
		self.btn_log_mode.clicked.connect(self._on_log_mode_toggle)
		header_layout.addWidget(self.btn_log_mode)

		self.btn_clear = QPushButton("Clear")
		self.btn_clear.setObjectName("btnClearLog")
		self.btn_clear.setFlat(True)
		self.btn_clear.clicked.connect(self._on_clear)
		header_layout.addWidget(self.btn_clear)

		btn_close = QPushButton("✕")
		btn_close.setObjectName("btnLogSideClose")
		btn_close.setFlat(True)
		btn_close.setFixedWidth(24)
		btn_close.clicked.connect(self.toggle)
		header_layout.addWidget(btn_close)

		panel_layout.addWidget(header)

		self._log_panel = LogPanel()
		panel_layout.addWidget(self._log_panel)

		layout.addWidget(self._panel)

	def _set_collapsed_geometry(self) -> None:
		self.setMinimumWidth(COLLAPSED_WIDTH)
		self.setMaximumWidth(COLLAPSED_WIDTH)

	def _set_expanded_geometry(self) -> None:
		self.setMinimumWidth(EXPANDED_WIDTH)
		self.setMaximumWidth(EXPANDED_WIDTH)

	def is_open(self) -> bool:
		return self._is_open

	def toggle(self) -> None:
		if self._is_open:
			self._close()
		else:
			self._open()

	def _open(self) -> None:
		self._is_open = True
		self.clear_unread()
		self._tab.hide()
		self._panel.show()
		self._animate(COLLAPSED_WIDTH, EXPANDED_WIDTH)

	def _close(self) -> None:
		self._is_open = False
		self._panel.hide()
		self._tab.show()
		self._animate(EXPANDED_WIDTH, COLLAPSED_WIDTH)

	def _animate(self, start: int, end: int) -> None:
		if self._animation:
			self._animation.stop()

		anim = QPropertyAnimation(self, b"maximumWidth")
		anim.setDuration(ANIM_DURATION_MS)
		anim.setStartValue(start)
		anim.setEndValue(end)
		anim.setEasingCurve(QEasingCurve.Type.OutCubic)

		# Keep minimumWidth in sync so layout doesn't fight the animation
		anim2 = QPropertyAnimation(self, b"minimumWidth")
		anim2.setDuration(ANIM_DURATION_MS)
		anim2.setStartValue(start)
		anim2.setEndValue(end)
		anim2.setEasingCurve(QEasingCurve.Type.OutCubic)

		anim.start()
		anim2.start()
		self._animation = anim
		self._anim2 = anim2

	def increment_unread(self) -> None:
		if not self._is_open:
			self._unread_count += 1
			self._tab.set_count(self._unread_count)

	def clear_unread(self) -> None:
		self._unread_count = 0
		self._tab.set_count(0)

	# ── Public log API (delegates to LogPanel) ──────────────────────────────

	def log_message(self, message: str) -> None:
		self._log_panel.log_message(message)
		self._entry_count += 1
		self._count_label.setText(str(self._entry_count))
		self.increment_unread()

	def log_record(self, record: logging.LogRecord) -> None:
		self._log_panel.log_record(record)
		self._entry_count += 1
		self._count_label.setText(str(self._entry_count))
		self.increment_unread()

	def clear(self) -> None:
		self._log_panel.clear()
		self._entry_count = 0
		self._count_label.setText("")

	# ── Header button handlers ───────────────────────────────────────────────

	def _on_log_mode_toggle(self) -> None:
		is_detailed = self.btn_log_mode.isChecked()
		self.btn_log_mode.setText("Shallow" if is_detailed else "Deep")
		self.log_mode_toggled.emit(is_detailed)

	def _on_clear(self) -> None:
		self.clear()
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
poetry run pytest tests/test_log_side_panel.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chargeghost_evse/ui/widgets/log_side_panel.py tests/test_log_side_panel.py
git commit -m "feat(ui): add LogSidePanel — collapsible right-side log tab"
```

---

### Task 2: `ConnectorStatusBar` widget

**Files:**
- Create: `src/chargeghost_evse/ui/widgets/connector_status_bar.py`
- Create: `tests/test_connector_status_bar.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_connector_status_bar.py
import pytest
import sys
from PySide6.QtWidgets import QApplication

@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app

def test_status_bar_creates_pill_per_connector(qt_app):
    from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
    bar = ConnectorStatusBar()
    bar.update_connector(1, "Available", None)
    bar.update_connector(2, "Charging", 62.0)
    assert len(bar._pills) == 2

def test_update_connector_new_pill(qt_app):
    from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
    bar = ConnectorStatusBar()
    bar.update_connector(3, "Faulted", None)
    assert 3 in bar._pills

def test_update_connector_updates_existing_pill(qt_app):
    from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
    bar = ConnectorStatusBar()
    bar.update_connector(1, "Available", None)
    bar.update_connector(1, "Charging", 50.0)
    # Still only one pill for connector 1
    assert len(bar._pills) == 1

def test_session_stats_hidden_when_no_session(qt_app):
    from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
    bar = ConnectorStatusBar()
    assert not bar._stats_widget.isVisible()

def test_session_stats_shown_with_nonzero_power(qt_app):
    from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
    bar = ConnectorStatusBar()
    bar.update_session_stats(7.4, 62.0, "0:24:11")
    assert bar._stats_widget.isVisible()

def test_session_stats_hidden_with_zero_power(qt_app):
    from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
    bar = ConnectorStatusBar()
    bar.update_session_stats(7.4, 62.0, "0:24:11")
    bar.update_session_stats(0.0, 0.0, "--")
    assert not bar._stats_widget.isVisible()

def test_connector_selected_signal(qt_app):
    from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
    bar = ConnectorStatusBar()
    bar.update_connector(1, "Available", None)
    received = []
    bar.connector_selected.connect(lambda cid: received.append(cid))
    bar._pills[1].clicked.emit(1)
    assert received == [1]
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
poetry run pytest tests/test_connector_status_bar.py -v
```

Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Implement `ConnectorStatusBar`**

Create `src/chargeghost_evse/ui/widgets/connector_status_bar.py`:

```python
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
	QFrame,
	QHBoxLayout,
	QLabel,
	QSizePolicy,
	QWidget,
)

from chargeghost_evse.ui.styles import colors
from chargeghost_evse.ui.widgets.icons import get_icon_html


_STATUS_COLORS: dict[str, str] = {
	"Available": colors.SUCCESS,
	"Preparing": colors.WARNING,
	"Charging": colors.ACCENT_TEAL,
	"SuspendedEV": colors.WARNING,
	"SuspendedEVSE": colors.WARNING,
	"Finishing": colors.INFO,
	"Reserved": colors.TEXT_SECONDARY,
	"Unavailable": colors.DANGER,
	"Faulted": colors.DANGER,
}


class ConnectorPill(QWidget):
	"""Compact clickable pill showing connector ID and status."""

	clicked = Signal(int)

	def __init__(self, connector_id: int, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)
		self._connector_id = connector_id
		self._is_selected = False

		self.setObjectName("connectorPill")
		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		self.setCursor(Qt.CursorShape.PointingHandCursor)

		layout = QHBoxLayout(self)
		layout.setContentsMargins(8, 0, 8, 0)
		layout.setSpacing(5)

		self._dot = QLabel()
		self._dot.setObjectName("connectorPillDot")
		self._dot.setFixedSize(7, 7)
		layout.addWidget(self._dot)

		self._label = QLabel(f"{connector_id} · Available")
		self._label.setObjectName("connectorPillLabel")
		layout.addWidget(self._label)

	def update_status(self, status: str, soc: Optional[float]) -> None:
		color = _STATUS_COLORS.get(status, colors.TEXT_MUTED)
		dot_html = get_icon_html("circle_green", color, 7)
		self._dot.setTextFormat(Qt.TextFormat.RichText)
		self._dot.setText(dot_html)

		display = status
		if status == "Charging" and soc is not None:
			display = f"Charging · {soc:.0f}%"
		self._label.setText(f"{self._connector_id} · {display}")

		self.setProperty("status", status.lower())
		self.style().unpolish(self)
		self.style().polish(self)

	def set_selected(self, selected: bool) -> None:
		if self._is_selected != selected:
			self._is_selected = selected
			self.setProperty("selected", selected)
			self.style().unpolish(self)
			self.style().polish(self)

	def mousePressEvent(self, event: QMouseEvent) -> None:
		if event.button() == Qt.MouseButton.LeftButton:
			self.clicked.emit(self._connector_id)
		super().mousePressEvent(event)


class ConnectorStatusBar(QWidget):
	"""
	38px horizontal bar showing all connectors as pills and live session stats.

	Public API:
	  update_connector(connector_id, status, soc)  — update/create a pill
	  update_session_stats(power_kw, soc, duration_str)  — show/hide session stats
	  connector_selected signal  — emitted when a pill is clicked
	"""

	connector_selected = Signal(int)

	def __init__(self, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)
		self.setObjectName("connectorStatusBar")
		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		self.setFixedHeight(38)

		self._pills: dict[int, ConnectorPill] = {}
		self._selected_id: Optional[int] = None

		self._setup_ui()

	def _setup_ui(self) -> None:
		layout = QHBoxLayout(self)
		layout.setContentsMargins(12, 0, 12, 0)
		layout.setSpacing(8)

		connectors_label = QLabel("CONNECTORS")
		connectors_label.setObjectName("connectorBarLabel")
		layout.addWidget(connectors_label)

		self._pills_layout = QHBoxLayout()
		self._pills_layout.setSpacing(6)
		layout.addLayout(self._pills_layout)

		sep = QFrame()
		sep.setFrameShape(QFrame.Shape.VLine)
		sep.setObjectName("connectorBarSep")
		layout.addWidget(sep)

		# Live session stats (right-aligned, hidden when idle)
		self._stats_widget = QWidget()
		stats_layout = QHBoxLayout(self._stats_widget)
		stats_layout.setContentsMargins(0, 0, 0, 0)
		stats_layout.setSpacing(10)

		self._power_label = QLabel("0.0 kW")
		self._power_label.setObjectName("connectorBarStat")
		stats_layout.addWidget(self._power_label)

		stats_layout.addWidget(self._sep_label("·"))

		self._soc_label = QLabel("0%")
		self._soc_label.setObjectName("connectorBarStat")
		stats_layout.addWidget(self._soc_label)

		stats_layout.addWidget(self._sep_label("·"))

		self._duration_label = QLabel("--")
		self._duration_label.setObjectName("connectorBarStat")
		stats_layout.addWidget(self._duration_label)

		layout.addWidget(self._stats_widget)
		self._stats_widget.hide()

		layout.addStretch()

	def _sep_label(self, text: str) -> QLabel:
		lbl = QLabel(text)
		lbl.setObjectName("connectorBarStatSep")
		return lbl

	def update_connector(
		self, connector_id: int, status: str, soc: Optional[float]
	) -> None:
		if connector_id not in self._pills:
			# Compute sorted insert position BEFORE adding to the dict
			insert_pos = sum(1 for k in self._pills if k < connector_id)
			pill = ConnectorPill(connector_id)
			pill.clicked.connect(self._on_pill_clicked)
			self._pills[connector_id] = pill
			self._pills_layout.insertWidget(insert_pos, pill)

			# Auto-select first connector
			if self._selected_id is None:
				self._selected_id = connector_id
				pill.set_selected(True)

		self._pills[connector_id].update_status(status, soc)

	def update_session_stats(
		self, power_kw: float, soc: float, duration_str: str
	) -> None:
		if power_kw > 0.0:
			self._power_label.setText(f"{power_kw:.1f} kW")
			self._soc_label.setText(f"{soc:.0f}%")
			self._duration_label.setText(duration_str)
			self._stats_widget.show()
		else:
			self._stats_widget.hide()

	def set_selected_connector(self, connector_id: int) -> None:
		for cid, pill in self._pills.items():
			pill.set_selected(cid == connector_id)
		self._selected_id = connector_id

	def _on_pill_clicked(self, connector_id: int) -> None:
		self.set_selected_connector(connector_id)
		self.connector_selected.emit(connector_id)
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
poetry run pytest tests/test_connector_status_bar.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Run full test suite, confirm nothing broken**

```bash
poetry run pytest -x -q
```

Expected: All existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/chargeghost_evse/ui/widgets/connector_status_bar.py tests/test_connector_status_bar.py
git commit -m "feat(ui): add ConnectorStatusBar — 38px horizontal pill connector selector"
```

---

## Chunk 2: AppSettings + QSS groundwork

### Task 3: Add `sidebar_expanded` to AppSettings

**Files:**
- Modify: `src/chargeghost_evse/ui/widgets/app_settings.py`
- Modify: `tests/test_app_settings.py` (create if doesn't exist)

- [ ] **Step 1: Write the failing test**

```python
# Append to or create tests/test_app_settings.py
def test_sidebar_expanded_default_false(tmp_path, monkeypatch):
    """sidebar_expanded returns False when key not yet written."""
    import sys
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QSettings
    QApplication.instance() or QApplication(sys.argv)
    # Use a temp org/app name to avoid touching real settings
    monkeypatch.setattr(
        "chargeghost_evse.ui.widgets.app_settings.AppSettings.__init__",
        lambda self: None,
    )
    from chargeghost_evse.ui.widgets.app_settings import AppSettings
    settings = AppSettings.__new__(AppSettings)
    settings._settings = QSettings("TestOrg", "TestEvse_sidebar")
    settings._settings.clear()
    assert settings.sidebar_expanded is False

def test_sidebar_expanded_round_trip(monkeypatch):
    import sys
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QSettings
    QApplication.instance() or QApplication(sys.argv)
    monkeypatch.setattr(
        "chargeghost_evse.ui.widgets.app_settings.AppSettings.__init__",
        lambda self: None,
    )
    from chargeghost_evse.ui.widgets.app_settings import AppSettings
    settings = AppSettings.__new__(AppSettings)
    settings._settings = QSettings("TestOrg", "TestEvse_sidebar")
    settings._settings.clear()
    settings.sidebar_expanded = True
    assert settings.sidebar_expanded is True
```

- [ ] **Step 2: Run test, verify it fails**

```bash
poetry run pytest tests/test_app_settings.py -v -k "sidebar"
```

Expected: `AttributeError: 'AppSettings' object has no attribute 'sidebar_expanded'`

- [ ] **Step 3: Add the key constant and property**

Edit `src/chargeghost_evse/ui/widgets/app_settings.py`. After line 13 (`SETTING_LAST_MODE = "ui/lastMode"`), add:

```python
    SETTING_SIDEBAR_EXPANDED = "ui/sidebarExpanded"
```

After the `last_mode` setter (line 101), add:

```python
    @property
    def sidebar_expanded(self) -> bool:
        return bool(self._settings.value(self.SETTING_SIDEBAR_EXPANDED, False))

    @sidebar_expanded.setter
    def sidebar_expanded(self, expanded: bool) -> None:
        self._settings.setValue(self.SETTING_SIDEBAR_EXPANDED, expanded)
```

- [ ] **Step 4: Run test, verify it passes**

```bash
poetry run pytest tests/test_app_settings.py -v -k "sidebar"
```

Expected: Both sidebar tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chargeghost_evse/ui/widgets/app_settings.py tests/test_app_settings.py
git commit -m "feat(ui): add sidebar_expanded setting to AppSettings"
```

---

### Task 4: Add QSS for new widgets

**Files:**
- Modify: `src/chargeghost_evse/ui/styles/e_mobility.qss`

No new tests — QSS is visual, validated by running the app.

- [ ] **Step 1: Append new QSS rules to the end of `e_mobility.qss`**

Add the following block at the end of `src/chargeghost_evse/ui/styles/e_mobility.qss`:

```css
/* ═══════════════════════════════════════════════════════════════
   ConnectorStatusBar
═══════════════════════════════════════════════════════════════ */
#connectorStatusBar {
    background-color: #161b22;
    border-bottom: 1px solid #21262d;
}

#connectorBarLabel {
    font-size: 9px;
    color: #6e7681;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 600;
}

#connectorPill {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 2px 8px;
    min-height: 24px;
    max-height: 24px;
}
#connectorPill:hover { border-color: #8b949e; }
#connectorPill[selected="true"] {
    background-color: rgba(30, 173, 152, 0.12);
    border-color: rgba(30, 173, 152, 0.5);
}
#connectorPill[status="charging"] { border-color: rgba(30, 173, 152, 0.4); }
#connectorPill[status="faulted"] { border-color: rgba(218, 54, 51, 0.4); }

#connectorPillLabel { font-size: 11px; color: #8b949e; }
#connectorPill[selected="true"] #connectorPillLabel { color: #1EAD98; }

#connectorBarSep { color: #30363d; max-width: 1px; min-width: 1px; }

#connectorBarStat { font-size: 11px; color: #1EAD98; font-weight: 600; }
#connectorBarStatSep { font-size: 11px; color: #484f58; }

/* ═══════════════════════════════════════════════════════════════
   LogSidePanel
═══════════════════════════════════════════════════════════════ */
#logSideTab {
    background-color: #161b22;
    border-left: 1px solid #21262d;
}
#logSideTab:hover { background-color: #1c2128; }

#logSideTabLabel {
    font-size: 9px;
    color: #6e7681;
    text-transform: uppercase;
    letter-spacing: 1px;
}

#logSideBadge {
    background-color: rgba(30, 173, 152, 0.2);
    color: #1EAD98;
    border-radius: 8px;
    font-size: 8px;
    padding: 1px 4px;
}

#logSidePanelContent {
    background-color: #0a0f16;
    border-left: 1px solid #21262d;
}

#logSidePanelHeader {
    background-color: #161b22;
    border-bottom: 1px solid #21262d;
}

#logSidePanelTitle { font-size: 11px; font-weight: 600; color: #e6edf3; }
#logSideCountLabel {
    font-size: 9px;
    color: #8b949e;
    background-color: #21262d;
    border-radius: 8px;
    padding: 1px 6px;
}
#btnLogSideClose { font-size: 11px; color: #6e7681; }
#btnLogSideClose:hover { color: #e6edf3; }

/* ═══════════════════════════════════════════════════════════════
   Collapsible Sidebar (SimulatorWidget / ManualWidget)
═══════════════════════════════════════════════════════════════ */
#sidebar[expanded="false"] QToolButton#sidebarNavBtn {
    min-width: 36px;
    max-width: 36px;
}
#sidebar[expanded="true"] QToolButton#sidebarNavBtn {
    min-width: 160px;
}
#sidebarExpandBtn {
    color: #6e7681;
    border: 1px solid #30363d;
    border-radius: 4px;
    min-height: 24px;
    max-height: 24px;
}
#sidebarExpandBtn:hover { color: #e6edf3; border-color: #8b949e; }

/* ═══════════════════════════════════════════════════════════════
   ContextChip (session dashboard context rail)
═══════════════════════════════════════════════════════════════ */
#contextChip {
    background-color: #161b22;
    border: 1px solid #21262d;
    border-radius: 5px;
    padding: 4px 8px;
}
#contextChipLabel {
    font-size: 8px;
    color: #6e7681;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
#contextChipValue { font-size: 12px; color: #e6edf3; font-family: monospace; }

/* ═══════════════════════════════════════════════════════════════
   Session state badge (replaces hero header)
═══════════════════════════════════════════════════════════════ */
#sessionStateBadge {
    background-color: rgba(30, 173, 152, 0.1);
    border: 1px solid rgba(30, 173, 152, 0.3);
    border-radius: 5px;
    padding: 6px 10px;
}
#sessionStateBadge[state="idle"] {
    background-color: rgba(72, 79, 88, 0.1);
    border-color: rgba(72, 79, 88, 0.3);
}
#sessionStateBadge[state="plugged"] {
    background-color: rgba(245, 158, 11, 0.1);
    border-color: rgba(245, 158, 11, 0.3);
}
#sessionStateName { font-size: 12px; font-weight: 600; color: #1EAD98; }
#sessionStateBadge[state="idle"] #sessionStateName { color: #8b949e; }
#sessionStateBadge[state="plugged"] #sessionStateName { color: #f59e0b; }
#sessionStateSub { font-size: 10px; color: #6e7681; }
```

- [ ] **Step 2: Confirm the app still loads without QSS parse errors**

```bash
poetry run dev &
sleep 3
kill %1
```

Expected: App opens without `QSS parse error` warnings in terminal.

- [ ] **Step 3: Commit**

```bash
git add src/chargeghost_evse/ui/styles/e_mobility.qss
git commit -m "style: add QSS for ConnectorStatusBar, LogSidePanel, sidebar, ContextChip"
```

---

## Chunk 3: SessionDashboard — horizontal two-column layout

### Task 5: Refactor `SessionDashboard`

**Files:**
- Modify: `src/chargeghost_evse/ui/widgets/session_dashboard.py`

This is the largest layout change. The dashboard switches from a vertical stack to a horizontal two-column layout: controls panel (left) + data panel (right). The `ConnectorStrip` import is removed; the hero frame is removed.

- [ ] **Step 1: Add `ContextChip` class above `SessionDashboard` in `session_dashboard.py`**

After the `_compute_effective_power_kw` function (after line 507), add:

```python
class ContextChip(QFrame):
	"""Compact label+value chip for the context rail."""

	def __init__(self, label: str, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)
		self.setObjectName("contextChip")
		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

		layout = QVBoxLayout(self)
		layout.setContentsMargins(8, 4, 8, 4)
		layout.setSpacing(1)

		self._label = QLabel(label)
		self._label.setObjectName("contextChipLabel")
		layout.addWidget(self._label)

		self._value = QLabel("--")
		self._value.setObjectName("contextChipValue")
		layout.addWidget(self._value)

	def set_value(self, value: str) -> None:
		self._value.setText(value)

	def clear(self) -> None:
		self._value.setText("--")
```

- [ ] **Step 2: Remove the `ConnectorStrip` import and other now-unused imports from `session_dashboard.py`**

Remove the `ConnectorStrip` import:
```python
from chargeghost_evse.ui.widgets.connector_strip import ConnectorStrip
```

Also remove any now-unused imports introduced by the hero frame removal (e.g. `QGridLayout`, `QSplitter` if present). Run `poetry run ruff check src/chargeghost_evse/ui/widgets/session_dashboard.py` after the changes in Step 3 to identify any remaining unused imports and remove them.

- [ ] **Step 2b: Remove the `CollapsibleDetails` class**

The `CollapsibleDetails` class (search for `class CollapsibleDetails` in `session_dashboard.py`) is no longer instantiated after the hero frame is removed. Delete the entire class definition. Run `grep -n "CollapsibleDetails" src/chargeghost_evse/ui/widgets/session_dashboard.py` first to confirm it has no remaining callers.

- [ ] **Step 3: Rewrite `SessionDashboard._setup_ui`**

Replace the entire `_setup_ui` method (lines 557–788) with:

```python
	def _setup_ui(self) -> None:
		main_layout = QHBoxLayout(self)
		main_layout.setSpacing(0)
		main_layout.setContentsMargins(0, 0, 0, 0)

		# ── Left: Controls panel ─────────────────────────────────────────────
		controls_panel = QWidget()
		controls_panel.setObjectName("dashControlsPanel")
		controls_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		controls_panel.setMinimumWidth(180)
		controls_panel.setMaximumWidth(280)
		controls_layout = QVBoxLayout(controls_panel)
		controls_layout.setContentsMargins(12, 12, 12, 12)
		controls_layout.setSpacing(12)

		# Session state badge
		self._state_badge = QFrame()
		self._state_badge.setObjectName("sessionStateBadge")
		self._state_badge.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		self._state_badge.setProperty("state", "idle")
		badge_layout = QHBoxLayout(self._state_badge)
		badge_layout.setContentsMargins(8, 6, 8, 6)
		badge_layout.setSpacing(6)
		self._state_name = QLabel("Idle")
		self._state_name.setObjectName("sessionStateName")
		self._state_sub = QLabel("Connector 1")
		self._state_sub.setObjectName("sessionStateSub")
		badge_layout.addWidget(self._state_name)
		badge_layout.addStretch()
		badge_layout.addWidget(self._state_sub)
		controls_layout.addWidget(self._state_badge)

		# Actions section
		actions_label = QLabel("ACTIONS")
		actions_label.setObjectName("dashSectionLabel")
		controls_layout.addWidget(actions_label)

		self.btn_plug = QPushButton("Plug In")
		self.btn_plug.setObjectName("btnPlug")
		self.btn_plug.setProperty("primary", True)
		self.btn_plug.setMinimumHeight(36)
		self.btn_plug.clicked.connect(self.plug_in_clicked)
		controls_layout.addWidget(self.btn_plug)

		self.btn_start_charge = QPushButton("Start Charging")
		self.btn_start_charge.setObjectName("btnStartCharge")
		self.btn_start_charge.setProperty("success", True)
		self.btn_start_charge.setMinimumHeight(36)
		self.btn_start_charge.clicked.connect(self.start_charging_clicked)
		controls_layout.addWidget(self.btn_start_charge)

		stop_unplug_row = QHBoxLayout()
		stop_unplug_row.setSpacing(6)
		self.btn_stop_charge = QPushButton("Stop")
		self.btn_stop_charge.setObjectName("btnStopCharge")
		self.btn_stop_charge.setProperty("warning", True)
		self.btn_stop_charge.setMinimumHeight(36)
		self.btn_stop_charge.clicked.connect(self.stop_charging_clicked)
		stop_unplug_row.addWidget(self.btn_stop_charge)
		self.btn_unplug = QPushButton("Unplug")
		self.btn_unplug.setObjectName("btnUnplug")
		self.btn_unplug.setProperty("danger", True)
		self.btn_unplug.setMinimumHeight(36)
		self.btn_unplug.clicked.connect(self.unplug_clicked)
		stop_unplug_row.addWidget(self.btn_unplug)
		controls_layout.addLayout(stop_unplug_row)

		self.btn_suspend_ev = QPushButton("Suspend EV")
		self.btn_suspend_ev.setObjectName("btnSuspendEV")
		self.btn_suspend_ev.setMinimumHeight(36)
		self.btn_suspend_ev.clicked.connect(self._on_suspend_ev_clicked)
		controls_layout.addWidget(self.btn_suspend_ev)

		# ID tag section
		id_label = QLabel("ID TAG")
		id_label.setObjectName("dashSectionLabel")
		controls_layout.addWidget(id_label)

		self.id_tag_input = IdTagInput()
		self.id_tag_input.tag_applied.connect(self._on_apply_id_tag)
		controls_layout.addWidget(self.id_tag_input)

		# Effective limit
		limit_row = QHBoxLayout()
		limit_lbl = QLabel("Effective Limit")
		limit_lbl.setObjectName("dashLimitLabel")
		limit_row.addWidget(limit_lbl)
		limit_row.addStretch()
		self._context_limit_value = QLabel("No limit")
		self._context_limit_value.setObjectName("contextLimitValue")
		limit_row.addWidget(self._context_limit_value)
		controls_layout.addLayout(limit_row)

		controls_layout.addStretch()
		main_layout.addWidget(controls_panel)

		# Vertical separator
		sep = QFrame()
		sep.setFrameShape(QFrame.Shape.VLine)
		sep.setObjectName("dashVertSep")
		main_layout.addWidget(sep)

		# ── Right: Data panel ────────────────────────────────────────────────
		data_panel = QWidget()
		data_panel.setObjectName("dashDataPanel")
		data_layout = QVBoxLayout(data_panel)
		data_layout.setContentsMargins(12, 12, 12, 12)
		data_layout.setSpacing(10)

		# Metric row (4 cards)
		metric_row = QHBoxLayout()
		metric_row.setSpacing(8)
		self.metric_power = MetricCard("Power", "kW")
		self.metric_soc = MetricCard("State of Charge", "%")
		self.metric_duration = MetricCard("Duration")
		self.metric_energy = MetricCard("Energy Charged", "Wh")
		for card in (self.metric_power, self.metric_soc, self.metric_duration, self.metric_energy):
			metric_row.addWidget(card)
		data_layout.addLayout(metric_row)

		# Telemetry chart (fills remaining vertical space)
		telemetry_panel = QFrame()
		telemetry_panel.setObjectName("telemetryPanel")
		telemetry_panel.setProperty("card", True)
		telemetry_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		telemetry_layout = QVBoxLayout(telemetry_panel)
		telemetry_layout.setContentsMargins(12, 8, 12, 8)
		telemetry_layout.setSpacing(4)
		telemetry_title = QLabel("Live Power Telemetry — 60 s rolling")
		telemetry_title.setObjectName("telemetryTitle")
		telemetry_layout.addWidget(telemetry_title)
		self.telemetry_chart = TelemetryChart()
		telemetry_layout.addWidget(self.telemetry_chart, 1)
		data_layout.addWidget(telemetry_panel, 1)

		# Charging progress row
		progress_row = QHBoxLayout()
		progress_row.setSpacing(8)
		progress_lbl = QLabel("Charging progress")
		progress_lbl.setObjectName("socTitle")
		progress_row.addWidget(progress_lbl)
		self.soc_progress = QProgressBar()
		self.soc_progress.setMinimumHeight(6)
		self.soc_progress.setMaximumHeight(6)
		self.soc_progress.setTextVisible(False)
		self.soc_progress.setValue(0)
		progress_row.addWidget(self.soc_progress, 1)
		self._soc_percent_label = QLabel("0%")
		self._soc_percent_label.setObjectName("socPercent")
		progress_row.addWidget(self._soc_percent_label)
		data_layout.addLayout(progress_row)

		# Context rail (5 chips)
		context_row = QHBoxLayout()
		context_row.setSpacing(6)
		self.chip_tx_id = ContextChip("Transaction")
		self.chip_voltage = ContextChip("Voltage")
		self.chip_current = ContextChip("Current")
		self.chip_meter = ContextChip("Total Meter")
		self.chip_phases = ContextChip("Phases")
		for chip in (self.chip_tx_id, self.chip_voltage, self.chip_current, self.chip_meter, self.chip_phases):
			context_row.addWidget(chip)
		data_layout.addLayout(context_row)

		main_layout.addWidget(data_panel, 1)
```

- [ ] **Step 4: Update `update_from_engine` in `SessionDashboard`**

Replace the body of `update_from_engine` (lines 854–951) with:

```python
	def update_from_engine(self, engine: "Engine") -> None:
		conn = engine.get_connector(self._selected_connector_id)
		if not conn:
			return

		# Button states
		self.btn_plug.setEnabled(not conn.is_plugged_in)
		self.btn_unplug.setEnabled(conn.is_plugged_in)
		self.id_tag_input.set_applied_tag(conn.id_tag)

		power_kw = _compute_effective_power_kw(engine, self._selected_connector_id)
		self.metric_power.set_value(f"{power_kw:.2f}")

		session = engine.session
		if session and session.connector_id == self._selected_connector_id:
			self.metric_energy.set_value(f"{session.energy_charged:.1f}")
			self.metric_soc.set_value(f"{session.state_of_charge:.1f}")
			duration_str = self._format_duration(session.start_time)
			self.metric_duration.set_value(duration_str)
			self.soc_progress.setValue(int(session.state_of_charge))
			self._soc_percent_label.setText(f"{session.state_of_charge:.0f}%")
			self.btn_start_charge.setEnabled(False)
			self.btn_stop_charge.setEnabled(True)

			state_name = conn.status.value
			self._state_name.setText(state_name)
			self._state_badge.setProperty("state", "charging")

			if conn.status == ConnectorState.SUSPENDED_EV:
				self.btn_suspend_ev.setText("Resume Charging")
				self.btn_suspend_ev.setEnabled(True)
			elif conn.status == ConnectorState.CHARGING:
				self.btn_suspend_ev.setText("Suspend EV")
				self.btn_suspend_ev.setEnabled(True)
			else:
				self.btn_suspend_ev.setText("Suspend EV")
				self.btn_suspend_ev.setEnabled(False)
		else:
			self.metric_energy.clear()
			self.metric_soc.clear()
			self.metric_duration.clear()
			self.soc_progress.setValue(0)
			self._soc_percent_label.setText("0%")
			self.btn_start_charge.setEnabled(conn.is_plugged_in)
			self.btn_stop_charge.setEnabled(False)
			self.btn_suspend_ev.setText("Suspend EV")
			self.btn_suspend_ev.setEnabled(False)

			if conn.is_plugged_in:
				self._state_name.setText("Plugged")
				self._state_badge.setProperty("state", "plugged")
			else:
				self._state_name.setText("Idle")
				self._state_badge.setProperty("state", "idle")

		self._state_sub.setText(f"Connector {self._selected_connector_id}")
		self._state_badge.style().unpolish(self._state_badge)
		self._state_badge.style().polish(self._state_badge)

		# Context chips
		selected_tx_id = (
			session.transaction_id
			if session and session.connector_id == self._selected_connector_id
			else None
		)
		self.chip_tx_id.set_value(f"#{selected_tx_id}" if selected_tx_id else "--")
		self.chip_voltage.set_value(f"{conn.voltage:.0f} V")
		self.chip_current.set_value(f"{conn.current:.0f} A")
		self.chip_meter.set_value(f"{engine.energy_meter.get_meter_reading():.1f} Wh")
		self.chip_phases.set_value(f"{conn.phase}Φ")

		# Effective limit display
		effective_limit: Optional[float] = None
		if session and session.connector_id == self._selected_connector_id:
			if engine.get_limit is not None:
				effective_limit = engine.get_limit(session.connector_id, session.transaction_id)
		if effective_limit is None or effective_limit < 0:
			self._context_limit_value.setText("No limit")
			self._context_limit_value.setProperty("limited", False)
		else:
			self._context_limit_value.setText(f"{effective_limit:.1f} A")
			self._context_limit_value.setProperty("limited", effective_limit < conn.current)
		self._context_limit_value.style().unpolish(self._context_limit_value)
		self._context_limit_value.style().polish(self._context_limit_value)
```

- [ ] **Step 4b: Remove the now-dead `connector_selected` Signal and `_on_connector_selected` from `SessionDashboard`**

The `ConnectorStrip` was the only widget inside `SessionDashboard` that emitted `connector_selected`. With `ConnectorStrip` removed and connector selection now handled entirely by `ConnectorStatusBar` in `SimulatorWidget`, the Signal declaration and its internal handler are both dead code.

First, confirm the locations:
```bash
grep -n "_on_connector_selected\|connector_selected" src/chargeghost_evse/ui/widgets/session_dashboard.py
```

Then remove:
1. The Signal declaration from the `SessionDashboard` class body: `connector_selected = Signal(int)`
2. The `_on_connector_selected` method body from `session_dashboard.py` (the method that forwarded `ConnectorStrip` events and emitted `self.connector_selected`)

Also remove the `self.dashboard.connector_selected.connect(...)` wire in `app.py`'s `_build_dashboard_tab` and the `_on_connector_selected` method from `SimulatorWidget` itself — both are covered in Task 7 Step 6.

- [ ] **Step 5: Update `set_selected_connector` — remove `connector_strip` reference**

Replace (around lines 828–838):
```python
	def set_selected_connector(self, connector_id: int) -> None:
		if self._selected_connector_id != connector_id:
			self.telemetry_chart.clear()
		self._selected_connector_id = connector_id
		self.connector_strip.set_selected_connector(connector_id)
```
With:
```python
	def set_selected_connector(self, connector_id: int) -> None:
		if self._selected_connector_id != connector_id:
			self.telemetry_chart.clear()
		self._selected_connector_id = connector_id
```

- [ ] **Step 6: Run the tests**

```bash
poetry run pytest -x -q
```

Expected: All tests PASS. (The dashboard has no direct unit tests today — verify no imports fail.)

- [ ] **Step 7: Commit**

```bash
git add src/chargeghost_evse/ui/widgets/session_dashboard.py
git commit -m "refactor(ui): SessionDashboard — horizontal two-column layout, remove hero frame"
```

---

## Chunk 4: `app.py` — window size, sidebar collapse, layout rewiring

### Task 6: Update window sizing, imports, and shortcuts

**Files:**
- Modify: `src/chargeghost_evse/ui/app.py`

- [ ] **Step 1: Update imports in `app.py`**

Replace the import block (lines 38–43) to swap old widget imports for new ones:

**Remove:**
```python
from chargeghost_evse.ui.widgets.collapsible_log import CollapsibleLogPanel
```
```python
from chargeghost_evse.ui.widgets.session_dashboard import SessionDashboard, IdTagInput
```

**Add (in alphabetical order with existing imports):**
```python
from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel
from chargeghost_evse.ui.widgets.session_dashboard import SessionDashboard, IdTagInput
```

Also remove `QSplitter` from the `QWidgets` import (line 24) since it's no longer used.

- [ ] **Step 2: Update `MainWindow.__init__` window size (lines 879–880)**

Replace:
```python
        self.setMinimumSize(800, 500)
        self.resize(1100, 700)
```
With:
```python
        self.setMinimumSize(1280, 720)
        self.resize(1600, 900)
```

- [ ] **Step 3: Rewrite `MainWindow._setup_ui`**

Replace the entire `_setup_ui` method (lines 958–1019) with:

```python
	def _setup_ui(self) -> None:
		central_widget = QWidget()
		self.setCentralWidget(central_widget)

		main_layout = QVBoxLayout(central_widget)
		main_layout.setSpacing(0)
		main_layout.setContentsMargins(0, 0, 0, 0)

		self.stack = QStackedWidget()
		main_layout.addWidget(self.stack, 1)

		self.toast_manager = ToastManager(self)

		self.mode_select = ModeSelectWidget(self)
		self.simulator = SimulatorWidget(self)
		self.manual = ManualWidget(self)

		self.simulator.connector_range_changed.connect(self.manual.update_connector_range)

		self.stack.addWidget(self.mode_select)
		self.stack.addWidget(self.simulator)
		self.stack.addWidget(self.manual)

		self.stack.setCurrentWidget(self.mode_select)

		self.status_bar = QStatusBar()
		self.setStatusBar(self.status_bar)

		self._connection_indicator = QLabel("Disconnected")
		self._connection_indicator.setObjectName("connection_indicator")
		self._connection_indicator.setProperty("connected", False)
		self._connection_indicator.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		self.status_bar.addPermanentWidget(self._connection_indicator)
```

Note: The `QSplitter`, `CollapsibleLogPanel`, and "Logs" toggle button are all **removed** here. The log panel is now owned by each mode widget.

- [ ] **Step 4: Update `_setup_shortcuts` to point `` ` `` and F1 to the simulator's log panel**

Replace `_setup_shortcuts` (lines 1021–1033) with:

```python
	def _setup_shortcuts(self) -> None:
		shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
		shortcut_save.activated.connect(self._shortcut_save)

		shortcut_log = QShortcut(QKeySequence("`"), self)
		shortcut_log.activated.connect(self._toggle_active_log)

		shortcut_f1 = QShortcut(QKeySequence("F1"), self)
		shortcut_f1.activated.connect(self._toggle_active_log)

		shortcut_home = QShortcut(QKeySequence("Esc"), self)
		shortcut_home.activated.connect(self._go_home)
```

- [ ] **Step 5: Add `_toggle_active_log` helper, remove `_toggle_global_log` and `_sync_log_toggle`**

Remove `_toggle_global_log` (lines 1114–1120) and `_sync_log_toggle` (lines 1122–1131).

Add in their place:

```python
	def _toggle_active_log(self) -> None:
		current = self.stack.currentWidget()
		if current is self.simulator:
			self.simulator.log_side_panel.toggle()
		elif current is self.manual:
			self.manual.log_side_panel.toggle()
```

- [ ] **Step 6: Update `_restore_ui_state` to restore sidebar and log panel state**

Replace `_restore_ui_state` (lines 1056–1073) with:

```python
	def _restore_ui_state(self) -> None:
		geometry = self.app_settings.window_geometry
		if geometry:
			self.restoreGeometry(geometry)

		self.simulator._selected_connector_id = self.app_settings.last_connector_id
		self.simulator.dashboard.set_selected_connector(self.app_settings.last_connector_id)

		if self.app_settings.sidebar_expanded:
			self.simulator.expand_sidebar()
			self.manual.expand_sidebar()

		if self.app_settings.log_panel_expanded:
			self.simulator.log_side_panel.toggle()

		saved_ui_mode = self.app_settings.last_mode
		if saved_ui_mode in ("simulator", "manual"):
			self.switch_to_mode(saved_ui_mode)
```

- [ ] **Step 7: Update `switch_to_mode` — remove `_sync_log_toggle` call**

Replace `switch_to_mode` (lines 1081–1089) with:

```python
	def switch_to_mode(self, mode: str) -> None:
		if mode == "simulator":
			self._fade_to_widget(self.simulator)
			self.update_recent_tags()
		elif mode == "manual":
			self._fade_to_widget(self.manual)
			self.update_recent_tags()
		self.app_settings.last_mode = mode
```

- [ ] **Step 8: Update `log_message` — remove global log panel reference**

Replace `log_message` (lines 1146–1150):

```python
	def log_message(self, message: str) -> None:
		if self.stack.currentWidget() == self.simulator:
			self.simulator.log_side_panel.log_message(message)
		elif self.stack.currentWidget() == self.manual:
			self.manual.log_side_panel.log_message(message)
```

- [ ] **Step 9: Update `on_log_received` — remove global log panel reference**

Replace (lines 1176–1185):

```python
	@Slot(object)
	def on_log_received(self, record: object) -> None:
		if not isinstance(record, logging.LogRecord):
			return
		if self.app_settings.log_mode == "shallow" and record.levelno < logging.INFO:
			return
		if self.stack.currentWidget() == self.simulator:
			self.simulator.log_side_panel.log_record(record)
		elif self.stack.currentWidget() == self.manual:
			self.manual.log_side_panel.log_record(record)
```

- [ ] **Step 10: Update `_on_global_log_mode_toggle` → `_on_log_mode_toggle`**

The signal `log_mode_toggled` now comes from `LogSidePanel`. Replace the old handler:

```python
	def _on_log_mode_toggle(self, is_detailed: bool) -> None:
		mode: LogMode = "deep" if is_detailed else "shallow"
		self.app_settings.log_mode = mode
		# Sync the other mode's log panel button state
		other = self.manual if self.stack.currentWidget() == self.simulator else self.simulator
		other.log_side_panel.btn_log_mode.setChecked(is_detailed)
		other.log_side_panel.btn_log_mode.setText("Shallow" if is_detailed else "Deep")
```

- [ ] **Step 11: Update `closeEvent` — remove global log panel reference**

Replace the relevant lines in `closeEvent` (line 1288):

```python
        self.app_settings.log_panel_expanded = self._global_log_panel.is_expanded()
```
With:
```python
        self.app_settings.log_panel_expanded = self.simulator.log_side_panel.is_open()
        self.app_settings.sidebar_expanded = self.simulator._sidebar_expanded
```

- [ ] **Step 12: Run full test suite**

```bash
poetry run pytest -x -q
```

Expected: All tests pass.

- [ ] **Step 13: Commit**

```bash
git add src/chargeghost_evse/ui/app.py
git commit -m "refactor(ui): update MainWindow — remove global log panel, rewire shortcuts and log routing"
```

---

### Task 7: Rewrite `SimulatorWidget` — sidebar collapse + ConnectorStatusBar + LogSidePanel

**Files:**
- Modify: `src/chargeghost_evse/ui/app.py` (continuing in `SimulatorWidget`)

- [ ] **Step 1: Add `QToolButton` and `QEasingCurve` imports to `app.py`**

In the `PySide6.QtWidgets` import block, add `QToolButton`.
In the `PySide6.QtCore` import block, confirm `QEasingCurve` is already present (it is, line 11).

- [ ] **Step 2: Rewrite `SimulatorWidget._setup_ui` and add collapse helpers**

Replace `SimulatorWidget._setup_ui` (lines 258–361) with:

```python
	def _setup_ui(self) -> None:
		self._sidebar_expanded = self.main_window.app_settings.sidebar_expanded
		self._sidebar_anim: Optional[QPropertyAnimation] = None

		main_layout = QHBoxLayout(self)
		main_layout.setSpacing(0)
		main_layout.setContentsMargins(0, 0, 0, 0)

		# ── Sidebar ──────────────────────────────────────────────────────────
		self._sidebar = QWidget()
		self._sidebar.setObjectName("sidebar")
		self._sidebar.setProperty("expanded", False)
		self._sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		sidebar_layout = QVBoxLayout(self._sidebar)
		sidebar_layout.setContentsMargins(6, 12, 6, 12)
		sidebar_layout.setSpacing(4)

		self._btn_dashboard = self._create_nav_btn("Dashboard", "dashboard")
		self._btn_dashboard.setChecked(True)
		self._btn_dashboard.clicked.connect(lambda: self._on_nav_clicked(0))
		sidebar_layout.addWidget(self._btn_dashboard)

		self._btn_settings = self._create_nav_btn("Settings", "settings")
		self._btn_settings.clicked.connect(lambda: self._on_nav_clicked(1))
		sidebar_layout.addWidget(self._btn_settings)

		self._btn_ocpp_keys = self._create_nav_btn("OCPP Keys", "key")
		self._btn_ocpp_keys.clicked.connect(lambda: self._on_nav_clicked(2))
		sidebar_layout.addWidget(self._btn_ocpp_keys)

		self._btn_profiles = self._create_nav_btn("Profiles", "sliders")
		self._btn_profiles.clicked.connect(lambda: self._on_nav_clicked(3))
		sidebar_layout.addWidget(self._btn_profiles)

		sidebar_layout.addStretch()

		self._btn_home = self._create_nav_btn("Switch Mode", "home")
		self._btn_home.setAutoExclusive(False)
		self._btn_home.clicked.connect(self.main_window._go_home)
		sidebar_layout.addWidget(self._btn_home)

		self._btn_expand_sidebar = QToolButton()
		self._btn_expand_sidebar.setObjectName("sidebarExpandBtn")
		self._btn_expand_sidebar.setToolTip("Expand sidebar")
		self._btn_expand_sidebar.clicked.connect(self.toggle_sidebar)
		sidebar_layout.addWidget(self._btn_expand_sidebar)

		self._apply_sidebar_width(animate=False)
		main_layout.addWidget(self._sidebar)

		# ── Content column ───────────────────────────────────────────────────
		content_col = QWidget()
		content_col_layout = QVBoxLayout(content_col)
		content_col_layout.setSpacing(0)
		content_col_layout.setContentsMargins(0, 0, 0, 0)

		# Connector status bar (always visible)
		self.connector_bar = ConnectorStatusBar()
		self.connector_bar.connector_selected.connect(self._on_connector_bar_selected)
		content_col_layout.addWidget(self.connector_bar)

		# Content stack
		self.stack = QStackedWidget()
		self.stack.setObjectName("contentStack")
		content_col_layout.addWidget(self.stack, 1)

		# Build tabs
		self._build_dashboard_tab()
		self._build_settings_tab()
		self._build_ocpp_keys_tab()
		self._build_profiles_tab()

		main_layout.addWidget(content_col, 1)

		# ── Log side panel ───────────────────────────────────────────────────
		self.log_side_panel = LogSidePanel()
		self.log_side_panel.log_mode_toggled.connect(
			self.main_window._on_log_mode_toggle
		)
		main_layout.addWidget(self.log_side_panel)
```

- [ ] **Step 3: Add sidebar helper methods to `SimulatorWidget`**

Add after `_setup_ui`:

```python
	def _create_nav_btn(self, text: str, icon_name: str) -> QToolButton:
		btn = QToolButton()
		btn.setObjectName("sidebarNavBtn")
		btn.setCheckable(True)
		btn.setAutoExclusive(True)
		btn.setText(text)
		btn.setIcon(get_icon(icon_name, colors.TEXT_SECONDARY))
		btn.setIconSize(QSize(18, 18))
		btn.setMinimumHeight(40)
		btn.setMaximumHeight(40)
		btn.setToolTip(text)
		btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
		btn.setCursor(Qt.CursorShape.PointingHandCursor)
		return btn

	def _apply_sidebar_width(self, animate: bool = True) -> None:
		target = 180 if self._sidebar_expanded else 48
		self._sidebar.setProperty("expanded", self._sidebar_expanded)
		self._sidebar.style().unpolish(self._sidebar)
		self._sidebar.style().polish(self._sidebar)

		icon_style = (
			Qt.ToolButtonStyle.ToolButtonTextBesideIcon
			if self._sidebar_expanded
			else Qt.ToolButtonStyle.ToolButtonIconOnly
		)
		for btn in (
			self._btn_dashboard, self._btn_settings,
			self._btn_ocpp_keys, self._btn_profiles, self._btn_home,
		):
			btn.setToolButtonStyle(icon_style)

		chevron = "▶" if not self._sidebar_expanded else "◀"
		self._btn_expand_sidebar.setText(chevron)
		self._btn_expand_sidebar.setToolTip(
			"Expand sidebar" if not self._sidebar_expanded else "Collapse sidebar"
		)

		if animate and self._sidebar_expanded is not None:
			current = self._sidebar.width()
			anim = QPropertyAnimation(self._sidebar, b"maximumWidth")
			anim.setDuration(180)
			anim.setStartValue(current)
			anim.setEndValue(target)
			anim.setEasingCurve(QEasingCurve.Type.OutCubic)
			anim2 = QPropertyAnimation(self._sidebar, b"minimumWidth")
			anim2.setDuration(180)
			anim2.setStartValue(current)
			anim2.setEndValue(target)
			anim2.setEasingCurve(QEasingCurve.Type.OutCubic)
			anim.start()
			anim2.start()
			self._sidebar_anim = anim
			self._sidebar_anim2 = anim2
		else:
			self._sidebar.setMinimumWidth(target)
			self._sidebar.setMaximumWidth(target)

	def toggle_sidebar(self) -> None:
		self._sidebar_expanded = not self._sidebar_expanded
		self._apply_sidebar_width(animate=True)
		self.main_window.app_settings.sidebar_expanded = self._sidebar_expanded
		if hasattr(self.main_window, "manual"):
			self.main_window.manual._sidebar_expanded = self._sidebar_expanded
			self.main_window.manual._apply_sidebar_width(animate=True)

	def expand_sidebar(self) -> None:
		if not self._sidebar_expanded:
			self.toggle_sidebar()
```

- [ ] **Step 4: Split tab-building into private methods**

Extract the tab-building code (currently inline) into:

```python
	def _build_dashboard_tab(self) -> None:
		dashboard_tab = QWidget()
		dashboard_layout = QVBoxLayout(dashboard_tab)
		dashboard_layout.setSpacing(0)
		dashboard_layout.setContentsMargins(0, 0, 0, 0)
		self.dashboard = SessionDashboard()
		# Note: connector_selected Signal is removed from SessionDashboard in Chunk 3.
		# Connector selection is now handled by ConnectorStatusBar → _on_connector_bar_selected.
		self.dashboard.plug_in_clicked.connect(self.action_plug_in)
		self.dashboard.unplug_clicked.connect(self.action_unplug)
		self.dashboard.start_charging_clicked.connect(self.action_start_charging)
		self.dashboard.stop_charging_clicked.connect(self.action_stop_charging)
		self.dashboard.suspend_ev_clicked.connect(self.action_suspend_ev)
		self.dashboard.resume_charging_clicked.connect(self.action_resume_charging)
		self.dashboard.apply_id_tag_clicked.connect(self.action_apply_id_tag)
		dashboard_layout.addWidget(self.dashboard, 1)
		self.stack.addWidget(dashboard_tab)

	def _build_settings_tab(self) -> None:
		settings_tab = QWidget()
		settings_layout = QVBoxLayout(settings_tab)
		settings_layout.setSpacing(0)
		settings_layout.setContentsMargins(0, 0, 0, 0)
		self.settings_panel = SettingsPanel()
		self.settings_panel.set_engine(self.engine)
		self.settings_panel.set_config(self.config)
		self.settings_panel.set_connector_callbacks(
			on_apply=self._on_connector_apply,
			on_remove=self._on_connector_remove,
			on_add=self._on_connector_add,
		)
		self.settings_panel.save_config_clicked.connect(self.action_save_config)
		self.settings_panel.ocpp_key_changed.connect(self._on_ocpp_key_changed)
		settings_layout.addWidget(self.settings_panel)
		self.stack.addWidget(settings_tab)

	def _build_ocpp_keys_tab(self) -> None:
		tab = QWidget()
		layout = QVBoxLayout(tab)
		layout.setSpacing(16)
		layout.setContentsMargins(16, 16, 16, 16)
		title = QLabel("OCPP Configuration Keys")
		title.setObjectName("sectionHeader")
		layout.addWidget(title)
		self.config_keys_panel = ConfigKeysPanel()
		self.config_keys_panel.key_changed.connect(self._on_ocpp_key_changed)
		self.config_keys_panel.set_keys(self._config_manager.get_all_keys())
		layout.addWidget(self.config_keys_panel)
		self.stack.addWidget(tab)

	def _build_profiles_tab(self) -> None:
		tab = QWidget()
		layout = QVBoxLayout(tab)
		layout.setSpacing(0)
		layout.setContentsMargins(0, 0, 0, 0)
		self.profiles_panel = ChargingProfilesPanel()
		layout.addWidget(self.profiles_panel)
		self.stack.addWidget(tab)
```

- [ ] **Step 5: Wire `ConnectorStatusBar` updates into `update_ui`**

Update `SimulatorWidget.update_ui` (lines 428–435):

```python
	def update_ui(self) -> None:
		self._ensure_valid_selection()
		# Update connector status bar pills
		engine = self.engine
		for conn in engine.connectors:
			session = (
				engine.session
				if engine.session and engine.session.connector_id == conn.id
				else None
			)
			soc = session.state_of_charge if session else None
			self.connector_bar.update_connector(conn.id, conn.status.value, soc)
		self.connector_bar.set_selected_connector(self._selected_connector_id)

		# Update live session stats in bar
		from chargeghost_evse.ui.widgets.session_dashboard import _compute_effective_power_kw
		power_kw = _compute_effective_power_kw(engine, self._selected_connector_id)
		session = engine.session
		if session and session.connector_id == self._selected_connector_id:
			duration_str = self.dashboard._format_duration(session.start_time)
			self.connector_bar.update_session_stats(
				power_kw, session.state_of_charge, duration_str
			)
		else:
			self.connector_bar.update_session_stats(0.0, 0.0, "--")

		self.dashboard.update_from_engine(engine)
		self._profiles_tick_counter += 1
		if self._profiles_tick_counter >= 10:
			self._profiles_tick_counter = 0
			self.profiles_panel.update_from_engine(engine, self.bridge)

	def _on_connector_bar_selected(self, connector_id: int) -> None:
		self._selected_connector_id = connector_id
		self.dashboard.set_selected_connector(connector_id)
		self.main_window.app_settings.last_connector_id = connector_id
```

- [ ] **Step 6: Remove `_on_connector_selected` from `SimulatorWidget`**

The `_on_connector_selected` method (previously called from `dashboard.connector_selected`) is now dead code — connector selection routes through `_on_connector_bar_selected` instead. Delete the method entirely:

```python
# DELETE this method from SimulatorWidget:
def _on_connector_selected(self, connector_id: int) -> None:
    ...
```

- [ ] **Step 7: Update `_on_nav_clicked` — replace `QPushButton` icon updates with `QToolButton` style**

The icon-colour updates already work with `QToolButton` (same `.setIcon()` API). No change needed here; confirm the method still compiles.

- [ ] **Step 8: Run tests and smoke-test the app**

```bash
poetry run pytest -x -q
poetry run dev
```

Expected: App opens. Sidebar is 48px icon-only. Dashboard is side-by-side controls + data. Connector status bar shows at top.

- [ ] **Step 9: Commit**

```bash
git add src/chargeghost_evse/ui/app.py
git commit -m "refactor(ui): SimulatorWidget — collapsible sidebar, ConnectorStatusBar, LogSidePanel"
```

---

### Task 8: Rewrite `ManualWidget` sidebar + log panel

**Files:**
- Modify: `src/chargeghost_evse/ui/app.py` (`ManualWidget` section only)

- [ ] **Step 1: Rewrite `ManualWidget._setup_ui` sidebar section**

Replace the sidebar block (lines 598–617) with:

```python
		self._sidebar_expanded = self.main_window.app_settings.sidebar_expanded
		self._sidebar_anim: Optional[QPropertyAnimation] = None

		self._sidebar = QWidget()
		self._sidebar.setObjectName("sidebar")
		self._sidebar.setProperty("expanded", self._sidebar_expanded)
		self._sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		sidebar_layout = QVBoxLayout(self._sidebar)
		sidebar_layout.setContentsMargins(6, 12, 6, 12)
		sidebar_layout.setSpacing(4)

		self._btn_manual = self._create_nav_btn("Manual Controls", "terminal")
		self._btn_manual.setChecked(True)
		sidebar_layout.addWidget(self._btn_manual)
		sidebar_layout.addStretch()

		self._btn_home = self._create_nav_btn("Switch Mode", "home")
		self._btn_home.setAutoExclusive(False)
		self._btn_home.clicked.connect(self.main_window._go_home)
		sidebar_layout.addWidget(self._btn_home)

		self._btn_expand_sidebar = QToolButton()
		self._btn_expand_sidebar.setObjectName("sidebarExpandBtn")
		self._btn_expand_sidebar.setToolTip("Expand sidebar")
		self._btn_expand_sidebar.clicked.connect(self._toggle_sidebar)
		sidebar_layout.addWidget(self._btn_expand_sidebar)

		self._apply_sidebar_width(animate=False)
		main_layout.addWidget(self._sidebar)
```

- [ ] **Step 2: Replace inline `LogPanel` in `ManualWidget` with `LogSidePanel`**

Remove the entire `right_panel` layout (lines 695–721 approximately) and the `self.log_panel` widget. Add `LogSidePanel` as the rightmost child of `main_layout`:

```python
		self.log_side_panel = LogSidePanel()
		self.log_side_panel.log_mode_toggled.connect(
			self.main_window._on_log_mode_toggle
		)
		main_layout.addWidget(self.log_side_panel)
```

Also remove the inline log header, `btn_clear_logs`, and `btn_log_mode` from `ManualWidget` — these are now in `LogSidePanel.header`.

- [ ] **Step 3: Add `_create_nav_btn`, `_apply_sidebar_width`, `_toggle_sidebar` to `ManualWidget`**

```python
	def _create_nav_btn(self, text: str, icon_name: str) -> QToolButton:
		btn = QToolButton()
		btn.setObjectName("sidebarNavBtn")
		btn.setCheckable(True)
		btn.setAutoExclusive(True)
		btn.setText(text)
		btn.setIcon(get_icon(icon_name, colors.TEXT_SECONDARY))
		btn.setIconSize(QSize(18, 18))
		btn.setMinimumHeight(40)
		btn.setMaximumHeight(40)
		btn.setToolTip(text)
		btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
		btn.setCursor(Qt.CursorShape.PointingHandCursor)
		return btn

	def _apply_sidebar_width(self, animate: bool = True) -> None:
		target = 180 if self._sidebar_expanded else 48
		self._sidebar.setProperty("expanded", self._sidebar_expanded)
		self._sidebar.style().unpolish(self._sidebar)
		self._sidebar.style().polish(self._sidebar)
		icon_style = (
			Qt.ToolButtonStyle.ToolButtonTextBesideIcon
			if self._sidebar_expanded
			else Qt.ToolButtonStyle.ToolButtonIconOnly
		)
		self._btn_manual.setToolButtonStyle(icon_style)
		self._btn_home.setToolButtonStyle(icon_style)
		chevron = "▶" if not self._sidebar_expanded else "◀"
		self._btn_expand_sidebar.setText(chevron)
		if animate:
			current = self._sidebar.width()
			anim = QPropertyAnimation(self._sidebar, b"maximumWidth")
			anim.setDuration(180)
			anim.setStartValue(current)
			anim.setEndValue(target)
			anim.setEasingCurve(QEasingCurve.Type.OutCubic)
			anim2 = QPropertyAnimation(self._sidebar, b"minimumWidth")
			anim2.setDuration(180)
			anim2.setStartValue(current)
			anim2.setEndValue(target)
			anim2.setEasingCurve(QEasingCurve.Type.OutCubic)
			anim.start()
			anim2.start()
			self._sidebar_anim = anim
			self._sidebar_anim2 = anim2
		else:
			self._sidebar.setMinimumWidth(target)
			self._sidebar.setMaximumWidth(target)

	def _toggle_sidebar(self) -> None:
		self._sidebar_expanded = not self._sidebar_expanded
		self._apply_sidebar_width(animate=True)
		self.main_window.app_settings.sidebar_expanded = self._sidebar_expanded
```

- [ ] **Step 4: Update `ManualWidget.log_message` and `log_record` to use `log_side_panel`**

Replace:
```python
	def log_message(self, message: str) -> None:
		self.log_panel.log_message(message)

	def log_record(self, record: logging.LogRecord) -> None:
		self.log_panel.log_record(record)
```
With:
```python
	def log_message(self, message: str) -> None:
		self.log_side_panel.log_message(message)

	def log_record(self, record: logging.LogRecord) -> None:
		self.log_side_panel.log_record(record)
```

- [ ] **Step 5: Remove `action_toggle_log_mode` from `ManualWidget`**

The log mode is now controlled by `LogSidePanel.btn_log_mode`. Remove `ManualWidget.action_toggle_log_mode` entirely and remove the connected `btn_log_mode` widget.

Also remove the reference to `self.main_window._global_log_panel` in the old `action_toggle_log_mode` (line 743).

- [ ] **Step 6: Run tests**

```bash
poetry run pytest -x -q
```

Expected: All tests pass.

- [ ] **Step 7: Smoke-test both modes**

```bash
poetry run dev
```

Switch to Manual mode. Confirm sidebar is icon-only. Confirm log side panel tab is visible on the right.

- [ ] **Step 8: Commit**

```bash
git add src/chargeghost_evse/ui/app.py
git commit -m "refactor(ui): ManualWidget — collapsible sidebar, LogSidePanel replaces inline log"
```

---

## Chunk 5: Cleanup + SettingsPanel responsive grid

### Task 9: Delete old widget files

**Files:**
- Delete: `src/chargeghost_evse/ui/widgets/collapsible_log.py`
- Delete: `src/chargeghost_evse/ui/widgets/connector_strip.py`

- [ ] **Step 1: Verify no remaining imports of deleted modules**

```bash
grep -rn "collapsible_log\|connector_strip\|CollapsibleLogPanel\|ConnectorStrip\|ConnectorIndicator" \
  src/chargeghost_evse/ tests/
```

Expected: No matches.

- [ ] **Step 2: Delete the files**

```bash
git rm src/chargeghost_evse/ui/widgets/collapsible_log.py
git rm src/chargeghost_evse/ui/widgets/connector_strip.py
```

- [ ] **Step 3: Run full test suite**

```bash
poetry run pytest -x -q
```

Expected: All tests pass — no imports of deleted modules anywhere.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(ui): delete CollapsibleLogPanel and ConnectorStrip (replaced by new widgets)"
```

---

### Task 10: ConnectorPanel responsive connector card grid

**Files:**
- Modify: `src/chargeghost_evse/ui/widgets/connector_panel.py`

The connector cards live inside `ConnectorPanel.cards_container` (a `QVBoxLayout` at line ~326 of `connector_panel.py`). `SettingsPanel.rebuild_connector_cards()` already delegates to `self.connector_panel.rebuild_cards()`. The responsive grid therefore belongs in `ConnectorPanel`, not `SettingsPanel`.

- [ ] **Step 1: Write the failing test**

```python
# Append to or create tests/test_connector_panel.py
import pytest
import sys
from PySide6.QtWidgets import QApplication

@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app

def test_connector_panel_has_grid(qt_app):
    """ConnectorPanel should expose _connectors_grid after the refactor."""
    from chargeghost_evse.ui.widgets.connector_panel import ConnectorPanel
    panel = ConnectorPanel()
    assert hasattr(panel, "_connectors_grid")
```

- [ ] **Step 2: Run test, verify it fails**

```bash
poetry run pytest tests/test_connector_panel.py::test_connector_panel_has_grid -v
```

Expected: `AssertionError` — attribute doesn't exist yet.

- [ ] **Step 3: Replace `cards_container` VBox with `QGridLayout` in `ConnectorPanel`**

In `connector_panel.py`, find `self.cards_container = QVBoxLayout()` (line ~326). Replace with:

```python
		self._connectors_grid = QGridLayout()
		self._connectors_grid.setSpacing(12)
		self._grid_cols = 1
		layout.addLayout(self._connectors_grid)
```

Update all references to `self.cards_container` in `_refresh_cards` and `rebuild_cards` to use `self._connectors_grid` instead. When adding cards, use:

```python
		for i, card in enumerate(cards):
			row, col = divmod(i, self._grid_cols)
			self._connectors_grid.addWidget(card, row, col)
```

Add `resizeEvent` override and `_reflow_connector_grid` helper to `ConnectorPanel`:

```python
	def resizeEvent(self, event) -> None:
		super().resizeEvent(event)
		self._reflow_connector_grid()

	def _reflow_connector_grid(self) -> None:
		if not hasattr(self, "_connectors_grid"):
			return
		cols = 2 if self.width() > 700 else 1
		if cols == self._grid_cols:
			return
		self._grid_cols = cols
		# Collect existing card widgets
		cards: list[QWidget] = []
		while self._connectors_grid.count():
			item = self._connectors_grid.takeAt(0)
			if item and item.widget():
				cards.append(item.widget())
		for i, card in enumerate(cards):
			row, col = divmod(i, cols)
			self._connectors_grid.addWidget(card, row, col)
```

Add `QGridLayout` to the imports in `connector_panel.py`.

- [ ] **Step 4: Run test, verify it passes**

```bash
poetry run pytest tests/test_connector_panel.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
poetry run pytest -x -q
```

Expected: All tests PASS.

- [ ] **Step 6: Smoke-test by widening the settings panel**

```bash
poetry run dev
```

Navigate to Settings. Widen the window beyond 700px (the `ConnectorPanel` width, not the window width) and verify connector cards reflow to 2 columns.

- [ ] **Step 7: Commit**

```bash
git add src/chargeghost_evse/ui/widgets/connector_panel.py tests/test_connector_panel.py
git commit -m "feat(ui): ConnectorPanel — responsive 2-column connector grid via resizeEvent"
```

---

### Task 11: Final smoke test and integration check

**Files:** None (validation only)

- [ ] **Step 1: Run full test suite**

```bash
poetry run pytest -q
```

Expected: All tests PASS, 0 failures.

- [ ] **Step 2: Run linter and type checker**

```bash
poetry run ruff check src/
poetry run mypy src/
```

Expected: No errors.

- [ ] **Step 3: Launch app and verify all panels at FHD**

```bash
poetry run dev
```

Verify:
- Window opens at 1600×900.
- Sidebar is 48px icon-only with chevron expand button.
- Clicking chevron expands sidebar to 180px with text labels.
- Connector status bar visible at top of simulator content.
- Dashboard: left controls panel + right data panel side-by-side.
- Log tab (32px) is visible on the right edge. Clicking it opens 340px panel.
- `` ` `` and F1 keyboard shortcuts toggle the log panel.
- Switching to Manual mode: same sidebar + log panel behaviour.
- Settings panel: 2 columns when wide, 1 column when narrow.
- Closing and reopening app: sidebar and log panel state is restored.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(ui): desktop UI redesign — FHD-optimised horizontal layout complete"
```
