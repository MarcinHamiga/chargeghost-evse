"""
OCPP Timeline Panel Widget.

Displays OCPP timeline events with filtering by direction/action
and real-time updates when new events are appended to the store.
"""

import json
from typing import Literal, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from chargeghost_evse.devtools.timeline_export import TimelineExporter
from chargeghost_evse.devtools.timeline_models import TimelineEvent, TimelineFilter
from chargeghost_evse.devtools.timeline_store import TimelineStore
from chargeghost_evse.ui.styles import colors


class TimelineEntry(QWidget):
    """A single timeline event row with expandable payload."""

    def __init__(self, event: TimelineEvent, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._event = event
        self._expanded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)

        self._summary_widget = QWidget()
        self._summary_widget.setObjectName("timelineEntry")
        self._summary_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        summary_layout = QHBoxLayout(self._summary_widget)
        summary_layout.setContentsMargins(6, 4, 6, 4)
        summary_layout.setSpacing(8)

        ts = event.timestamp[11:23] if len(event.timestamp) > 23 else event.timestamp
        ts_label = QLabel(ts)
        ts_label.setObjectName("timelineTs")
        ts_label.setFixedWidth(80)
        summary_layout.addWidget(ts_label)

        dir_color = {
            "inbound": colors.INFO,
            "outbound": colors.SUCCESS,
            "local": colors.WARNING,
        }.get(event.direction, colors.TEXT_MUTED)
        dir_badge = QLabel(
            f"<span style='color:{dir_color}'>{event.direction[:3].upper()}</span>"
        )
        dir_badge.setFixedWidth(36)
        summary_layout.addWidget(dir_badge)

        action_label = QLabel(event.action)
        action_label.setObjectName("timelineAction")
        action_label.setStyleSheet(f"color: {colors.ACCENT_TEAL}; font-weight: 600;")
        action_label.setFixedWidth(140)
        summary_layout.addWidget(action_label)

        summary_text = event.summary[:60] + ("..." if len(event.summary) > 60 else "")
        desc_label = QLabel(summary_text)
        desc_label.setObjectName("timelineDesc")
        desc_label.setStyleSheet(f"color: {colors.TEXT_SECONDARY};")
        summary_layout.addWidget(desc_label, 1)

        self._payload_widget = QLabel()
        self._payload_widget.setObjectName("timelinePayload")
        self._payload_widget.setTextFormat(Qt.TextFormat.PlainText)
        self._payload_widget.setWordWrap(True)
        self._payload_widget.hide()
        layout.addWidget(self._payload_widget)

        layout.addWidget(self._summary_widget)

        if event.payload:
            self._summary_widget.mousePressEvent = lambda _: self._on_toggle()  # type: ignore[method-assign]

        self._update_payload_text()

    def _update_payload_text(self) -> None:
        if self._event.payload:
            try:
                text = json.dumps(self._event.payload, indent=2)
            except Exception:
                text = str(self._event.payload)
            self._payload_widget.setText(text)

    def _on_toggle(self) -> None:
        self._expanded = not self._expanded
        self._payload_widget.setVisible(self._expanded)


class OCPPTimelinePanel(QWidget):
    """
    Timeline panel displaying OCPP events with filtering.

    Supports filtering by direction (inbound/outbound/local) and action.
    Real-time updates when new events are appended to the store.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._store: Optional[TimelineStore] = None
        self._filter = TimelineFilter()
        self._entry_widgets: list[TimelineEntry] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        filter_bar = QWidget()
        filter_bar.setObjectName("timelineFilterBar")
        filter_bar.setFixedHeight(32)
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(8, 0, 8, 0)
        filter_layout.setSpacing(6)

        dir_combo = QComboBox()
        dir_combo.setObjectName("timelineDirFilter")
        dir_combo.addItems(["All", "inbound", "outbound", "local"])
        dir_combo.setFixedWidth(90)
        dir_combo.currentIndexChanged.connect(self._on_dir_changed)
        filter_layout.addWidget(QLabel("Dir:"))
        filter_layout.addWidget(dir_combo)

        self._action_combo = QComboBox()
        self._action_combo.setObjectName("timelineActionFilter")
        self._action_combo.setEditable(True)
        self._action_combo.setFixedWidth(120)
        self._action_combo.addItem("All")
        self._action_combo.currentIndexChanged.connect(self._on_action_changed)
        filter_layout.addWidget(QLabel("Action:"))
        filter_layout.addWidget(self._action_combo)

        filter_layout.addStretch()

        self._btn_copy = QPushButton("Copy")
        self._btn_copy.setObjectName("btnTimelineCopy")
        self._btn_copy.setFlat(True)
        self._btn_copy.setFixedWidth(50)
        self._btn_copy.clicked.connect(self._on_copy)
        filter_layout.addWidget(self._btn_copy)

        self._btn_export = QPushButton("Export")
        self._btn_export.setObjectName("btnTimelineExport")
        self._btn_export.setFlat(True)
        self._btn_export.setFixedWidth(56)
        self._btn_export.clicked.connect(self._on_export)
        filter_layout.addWidget(self._btn_export)

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setObjectName("btnTimelineClear")
        self._btn_clear.setFlat(True)
        self._btn_clear.setFixedWidth(50)
        self._btn_clear.clicked.connect(self._on_clear)
        filter_layout.addWidget(self._btn_clear)

        layout.addWidget(filter_bar)

        scroll = QScrollArea()
        scroll.setObjectName("timelineScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(4, 4, 4, 4)
        self._container_layout.setSpacing(2)
        self._container_layout.addStretch()

        scroll.setWidget(self._container)
        layout.addWidget(scroll)

    def set_store(self, store: TimelineStore) -> None:
        self._store = store
        self._store.on_event.subscribe(self._on_store_event)
        self._refresh()

    def _on_store_event(self, event: TimelineEvent) -> None:
        if self._store is None:
            return
        if self._filter.matches(event):
            QTimer.singleShot(0, lambda: self._add_entry(event))

    def _add_entry(self, event: TimelineEvent) -> None:
        entry = TimelineEntry(event)
        self._container_layout.insertWidget(0, entry)
        self._entry_widgets.insert(0, entry)

        while len(self._entry_widgets) > 500:
            w = self._entry_widgets.pop()
            self._container_layout.removeWidget(w)
            w.deleteLater()

    def _refresh(self) -> None:
        if self._store is None:
            return
        for w in self._entry_widgets:
            self._container_layout.removeWidget(w)
            w.deleteLater()
        self._entry_widgets.clear()

        events = self._store.query(self._filter)
        for event in reversed(events):
            self._add_entry(event)

        unique_actions = sorted(set(e.action for e in self._store.all()))
        current = self._action_combo.currentText()
        self._action_combo.blockSignals(True)
        self._action_combo.clear()
        self._action_combo.addItem("All")
        self._action_combo.addItems(unique_actions)
        if current in unique_actions:
            self._action_combo.setCurrentText(current)
        elif current == "All":
            self._action_combo.setCurrentText("All")
        self._action_combo.blockSignals(False)

    def _on_dir_changed(self, index: int) -> None:
        dir_map: list[Literal["inbound", "outbound", "local"] | None] = [
            None,
            "inbound",
            "outbound",
            "local",
        ]
        self._filter.direction = dir_map[index] if index > 0 else None
        self._refresh()

    def _on_action_changed(self, index: int) -> None:
        action = self._action_combo.itemText(index)
        self._filter.action = None if action == "All" or index == 0 else action
        self._refresh()

    def _on_copy(self) -> None:
        if self._store is None:
            return
        events = self._store.query(self._filter)
        lines = []
        for e in events:
            lines.append(f"{e.timestamp} {e.direction} {e.action}: {e.summary}")
        text = "\n".join(lines)
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(text)

    def _on_export(self) -> None:
        if self._store is None:
            return
        exporter = TimelineExporter(self._store)
        text = exporter.export(filter_func=self._filter.matches)
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(text)

    def _on_clear(self) -> None:
        if self._store is None:
            return
        self._store.clear()
        for w in self._entry_widgets:
            self._container_layout.removeWidget(w)
            w.deleteLater()
        self._entry_widgets.clear()

    @property
    def has_export_action(self) -> bool:
        return True

    @property
    def has_copy_action(self) -> bool:
        return True
