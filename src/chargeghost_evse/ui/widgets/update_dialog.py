from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
)
from PySide6.QtCore import Signal, Qt


class UpdateDialog(QDialog):
    """Dialog for notifying users about available updates."""

    update_now_clicked = Signal()
    later_clicked = Signal()
    ignore_clicked = Signal()

    def __init__(
        self, current_version: str, latest_version: str, release_notes: str, parent=None
    ):
        super().__init__(parent)
        self.current_version = current_version
        self.latest_version = latest_version
        self.release_notes = release_notes

        self.setObjectName("updateDialog")
        self.setWindowTitle("Update Available")
        self.setModal(True)
        self.resize(500, 400)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        self.header_label = QLabel(
            f"Update Available: {self.current_version} → {self.latest_version}"
        )
        self.header_label.setObjectName("updateDialogHeader")
        layout.addWidget(self.header_label)

        # Release notes
        self.notes_label = QLabel("Release Notes")
        self.notes_label.setObjectName("updateDialogNotesLabel")
        layout.addWidget(self.notes_label)

        self.release_notes_text = QTextEdit()
        self.release_notes_text.setObjectName("updateDialogReleaseNotes")
        self.release_notes_text.setPlainText(self.release_notes)
        self.release_notes_text.setReadOnly(True)
        layout.addWidget(self.release_notes_text)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.addStretch()

        self.btn_update_now = QPushButton("Update Now")
        self.btn_update_now.setObjectName("updatePrimaryButton")
        self.btn_update_now.setProperty("primary", True)
        self.btn_update_now.clicked.connect(self._on_update_now)
        button_layout.addWidget(self.btn_update_now)

        self.btn_later = QPushButton("Later")
        self.btn_later.setObjectName("updateSecondaryButton")
        self.btn_later.clicked.connect(self._on_later)
        button_layout.addWidget(self.btn_later)

        self.btn_ignore = QPushButton("Ignore This Version")
        self.btn_ignore.setObjectName("updateIgnoreButton")
        self.btn_ignore.clicked.connect(self._on_ignore)
        button_layout.addWidget(self.btn_ignore)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def _on_update_now(self):
        self.update_now_clicked.emit()
        self.accept()

    def _on_later(self):
        self.later_clicked.emit()
        self.reject()

    def _on_ignore(self):
        self.ignore_clicked.emit()
        self.reject()


class UpdateStatusChip(QPushButton):
    """Clickable status chip showing update availability."""

    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.version = version
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName("updateStatusChip")
        self.setText(f"Update Available: {self.version}")
        self.setCursor(Qt.PointingHandCursor)
