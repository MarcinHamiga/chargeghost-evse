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
