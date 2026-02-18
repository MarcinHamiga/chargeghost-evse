from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class StatusPanel(QWidget):
    _connector_frames: list[QFrame]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._connector_frames = []
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(8, 8, 8, 8)
        self._main_layout.setSpacing(10)

        title = QLabel("⚡ EVSE Status")
        title.setObjectName("sectionHeader")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._main_layout.addWidget(title)

        self.energy_label = QLabel("Energy: 0.000 Wh")
        self.energy_label.setObjectName("sessionLabel")
        self._main_layout.addWidget(self.energy_label)

        self.session_label = QLabel("No active session")
        self.session_label.setWordWrap(True)
        self.session_label.setObjectName("sessionLabel")
        self._main_layout.addWidget(self.session_label)

        connectors_header = QLabel("🔌 Connectors")
        connectors_header.setObjectName("sectionHeader")
        self._main_layout.addWidget(connectors_header)

        self.connectors_container = QVBoxLayout()
        self.connectors_container.setSpacing(8)
        self._main_layout.addLayout(self.connectors_container)

        self._main_layout.addStretch()

    def update_status(self, engine):
        self.energy_label.setText(
            f"Energy Meter: {engine.energy_meter.get_meter_reading():.3f} Wh"
        )

        if engine.session:
            self.session_label.setText(
                f"<b>Session:</b> Trans ID {engine.session.transaction_id}<br/>"
                f"<b>Energy:</b> {engine.session.energy_charged:.3f} Wh<br/>"
                f"<b>SoC:</b> {engine.session.state_of_charge:.1f}%"
            )
        else:
            self.session_label.setText("No active session")

        self._clear_connector_frames()

        for conn in engine.connectors:
            plug_status = "● Plugged In" if conn.is_plugged_in else "○ Unplugged"
            id_tag_status = f"ID Tag: {conn.id_tag}" if conn.id_tag else "No ID Tag"

            frame = QFrame()
            frame.setProperty("connectorCard", True)
            frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            frame_layout = QVBoxLayout(frame)
            frame_layout.setSpacing(4)
            frame_layout.setContentsMargins(12, 10, 12, 10)

            conn_header = QLabel(f"Connector {conn.id}")
            conn_header.setStyleSheet(
                "font-weight: 600; color: #1EAD98; font-size: 13px;"
            )
            frame_layout.addWidget(conn_header)

            status_label = QLabel(f"Status: {conn.status.value}")
            status_label.setStyleSheet(
                "color: #1EAD98;"
                if conn.status.value == "Charging"
                else "color: #8b949e;"
            )
            frame_layout.addWidget(status_label)

            plug_label = QLabel(f"Plug: {plug_status}")
            plug_label.setStyleSheet(
                "color: #238636;" if conn.is_plugged_in else "color: #8b949e;"
            )
            frame_layout.addWidget(plug_label)

            tag_label = QLabel(f"{id_tag_status}")
            tag_label.setStyleSheet("color: #8b949e;")
            frame_layout.addWidget(tag_label)

            output_label = QLabel(
                f"Output: {conn.voltage}V {conn.current}A {conn.phase}Ph"
            )
            output_label.setStyleSheet("color: #8b949e; font-family: monospace;")
            frame_layout.addWidget(output_label)

            self.connectors_container.addWidget(frame)
            self._connector_frames.append(frame)

    def _clear_connector_frames(self):
        for frame in self._connector_frames:
            frame.setParent(None)
            frame.deleteLater()
        self._connector_frames.clear()
