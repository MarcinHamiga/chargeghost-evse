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
	
	def __init__(self, current_version: str, latest_version: str, release_notes: str, parent=None):
		super().__init__(parent)
		self.current_version = current_version
		self.latest_version = latest_version
		self.release_notes = release_notes
		
		self.setWindowTitle("Update Available")
		self.setModal(True)
		self.resize(500, 400)
		
		self._setup_ui()
	
	def _setup_ui(self):
		layout = QVBoxLayout()
		
		# Header
		header_label = QLabel(f"Update Available: {self.current_version} → {self.latest_version}")
		header_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2196F3;")
		layout.addWidget(header_label)
		
		# Release notes
		notes_label = QLabel("Release Notes:")
		notes_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
		layout.addWidget(notes_label)
		
		self.release_notes_text = QTextEdit()
		self.release_notes_text.setPlainText(self.release_notes)
		self.release_notes_text.setReadOnly(True)
		self.release_notes_text.setMaximumHeight(200)
		layout.addWidget(self.release_notes_text)
		
		# Buttons
		button_layout = QHBoxLayout()
		
		self.btn_update_now = QPushButton("Update Now")
		self.btn_update_now.setStyleSheet("""
			QPushButton {
				background-color: #2196F3;
				color: white;
				border: none;
				padding: 8px 16px;
				border-radius: 4px;
				font-weight: bold;
			}
			QPushButton:hover {
				background-color: #1976D2;
			}
		""")
		self.btn_update_now.clicked.connect(self._on_update_now)
		button_layout.addWidget(self.btn_update_now)
		
		self.btn_later = QPushButton("Later")
		self.btn_later.clicked.connect(self._on_later)
		button_layout.addWidget(self.btn_later)
		
		self.btn_ignore = QPushButton("Ignore This Version")
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
	
	clicked = Signal()
	
	def __init__(self, version: str, parent=None):
		super().__init__(parent)
		self.version = version
		self._setup_ui()
	
	def _setup_ui(self):
		self.setText(f"Update Available: {self.version}")
		self.setStyleSheet("""
			QPushButton {
				background-color: rgba(33, 150, 243, 0.2);
				color: #1976D2;
				border: 1px solid #2196F3;
				padding: 4px 12px;
				border-radius: 12px;
				font-size: 12px;
				font-weight: bold;
			}
			QPushButton:hover {
				background-color: rgba(33, 150, 243, 0.3);
			}
		""")
		self.setCursor(Qt.PointingHandCursor)
