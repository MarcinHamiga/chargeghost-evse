from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from chargeghost_evse.ui.widgets.icons import get_icon_html


class StatusPanel(QWidget):
    on_connector_selected = Signal(int)
    _connector_frames: list[QFrame]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._connector_frames = []
        self._selected_connector_id: Optional[int] = None
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(12)

        title_container = QWidget()
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(8, 0, 8, 0)

        title = QLabel("EVSE Status")
        title.setObjectName("sectionHeader")
        title_layout.addWidget(title)
        title_layout.addStretch()

        self._main_layout.addWidget(title_container)

        self.connectors_container = QVBoxLayout()
        self.connectors_container.setSpacing(10)
        self.connectors_container.setContentsMargins(8, 0, 8, 0)
        self._main_layout.addLayout(self.connectors_container)

        self._main_layout.addStretch()

    def set_selected_connector(self, connector_id: int) -> None:
        self._selected_connector_id = connector_id
        for frame in self._connector_frames:
            if hasattr(frame, "_connector_id"):
                is_selected = frame._connector_id == connector_id
                frame.setProperty("selected", is_selected)
                frame.style().unpolish(frame)
                frame.style().polish(frame)

    def update_status(self, engine):
        self._clear_connector_frames()

        for conn in engine.connectors:
            is_selected = conn.id == self._selected_connector_id
            session = (
                engine.session
                if engine.session and engine.session.connector_id == conn.id
                else None
            )

            frame = QFrame()
            frame.setObjectName("connectorStatusCard")
            frame._connector_id = conn.id
            frame.setProperty("connectorCard", True)
            frame.setProperty("selected", is_selected)
            frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            frame.setCursor(Qt.CursorShape.PointingHandCursor)

            frame_layout = QVBoxLayout(frame)
            frame_layout.setSpacing(6)
            frame_layout.setContentsMargins(12, 12, 12, 12)

            header_layout = QHBoxLayout()
            conn_header = QLabel(f"Connector {conn.id}")
            conn_header.setProperty("connectorTitle", True)
            header_layout.addWidget(conn_header)
            header_layout.addStretch()

            status_icon_map = {
                "Available": ("circle_green", "#238636"),
                "Preparing": ("circle_yellow", "#f59e0b"),
                "Charging": ("zap", "#1EAD98"),
                "SuspendedEV": ("pause", "#f59e0b"),
                "SuspendedEVSE": ("pause", "#f59e0b"),
                "Finishing": ("circle_blue", "#3b82f6"),
                "Reserved": ("lock", "#8b949e"),
                "Unavailable": ("circle_red", "#da3633"),
                "Faulted": ("alert_triangle", "#f85149"),
            }
            icon_name, icon_color = status_icon_map.get(
                conn.status.value, ("circle_gray", "#6e7681")
            )

            status_label = QLabel(
                f"{get_icon_html(icon_name, icon_color, 14)} {conn.status.value}"
            )
            status_label.setProperty("statusBadge", True)
            status_label.setProperty("status", conn.status.value.lower())
            header_layout.addWidget(status_label)
            frame_layout.addLayout(header_layout)

            details_layout = QHBoxLayout()
            plug_icon_name = "plug"
            plug_icon_color = "#1EAD98" if conn.is_plugged_in else "#6e7681"
            plug_label = QLabel(
                f"{get_icon_html(plug_icon_name, plug_icon_color, 14)} "
                f"{'Plugged' if conn.is_plugged_in else 'Unplugged'}"
            )
            plug_label.setProperty("plugStatus", True)
            details_layout.addWidget(plug_label)
            details_layout.addStretch()

            output_label = QLabel(f"{conn.voltage}V {conn.current}A {conn.phase}Ph")
            output_label.setProperty("outputInfo", True)
            details_layout.addWidget(output_label)
            frame_layout.addLayout(details_layout)

            if session:
                soc_layout = QVBoxLayout()
                soc_layout.setSpacing(2)

                soc_header = QHBoxLayout()
                soc_title = QLabel("State of Charge")
                soc_title.setProperty("socTitle", True)
                soc_header.addWidget(soc_title)
                soc_header.addStretch()
                soc_value = QLabel(f"{session.state_of_charge:.1f}%")
                soc_value.setProperty("socValue", True)
                soc_header.addWidget(soc_value)
                soc_layout.addLayout(soc_header)

                progress = QProgressBar()
                progress.setMaximumHeight(6)
                progress.setTextVisible(False)
                progress.setValue(int(session.state_of_charge))
                soc_layout.addWidget(progress)
                frame_layout.addLayout(soc_layout)
            elif conn.id_tag:
                tag_label = QLabel(f"user {conn.id_tag}")
                tag_label.setProperty("tagLabel", True)
                frame_layout.addWidget(tag_label)

            frame.mousePressEvent = lambda event, cid=conn.id: self._on_frame_clicked(
                event, cid
            )

            self.connectors_container.addWidget(frame)
            self._connector_frames.append(frame)

    def _on_frame_clicked(self, event, connector_id: int) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_connector_selected.emit(connector_id)

    def _clear_connector_frames(self):
        for frame in self._connector_frames:
            frame.setParent(None)
            frame.deleteLater()
        self._connector_frames.clear()
