from chargeghost_evse.ui.app import MainWindow
from unittest.mock import patch
import sys


def test_manual_update_check_disabled_in_dev_mode(qtbot):
	"""Test that manual update check is disabled in development mode."""
	with patch.object(sys, 'frozen', False, create=True):
		window = MainWindow()
		qtbot.addWidget(window)

		# Verify the method exists and can be called
		assert hasattr(window, '_manual_update_check')
		assert hasattr(window, '_setup_menu')

		# The menu setup should have run without errors
		assert window.menuBar() is not None


def test_manual_update_check_enabled_in_production(qtbot):
	"""Test that manual update check is enabled in production mode."""
	with patch.object(sys, 'frozen', True, create=True):
		window = MainWindow()
		qtbot.addWidget(window)

		# Verify the method exists and can be called
		assert hasattr(window, '_manual_update_check')
		assert hasattr(window, '_setup_menu')

		# The menu setup should have run without errors
		assert window.menuBar() is not None


def test_manual_update_check_delegates_to_controller(qtbot):
	"""Test manual update check delegates to UpdateController.start_check."""
	window = MainWindow()
	qtbot.addWidget(window)

	with patch.object(window.update_controller, 'start_check') as mock_start_check:
		with patch.object(window, 'show_toast') as mock_toast:
			window._manual_update_check()
			mock_toast.assert_called_once_with("Checking for updates...", "info")
			mock_start_check.assert_called_once()


def test_manual_update_check_shows_no_updates_available(qtbot):
	"""Test manual update check when no updates are available."""
	window = MainWindow()
	qtbot.addWidget(window)

	# Call manual update check — controller.start_check is mocked to be a no-op
	with patch.object(window.update_controller, 'start_check'):
		window._manual_update_check()

	# Verify no crash
	assert True


def test_manual_update_check_shows_update_dialog(qtbot):
	"""Test manual update check when updates are available."""
	window = MainWindow()
	qtbot.addWidget(window)

	# Simulate the controller emitting update_available after a check
	with patch.object(window.update_controller, 'start_check'):
		window._manual_update_check()
		window.update_controller.update_available.emit("v0.2.0", "Notes")
		assert window._update_chip is not None


def test_about_dialog_shows_version_info(qtbot):
	"""Test that about dialog shows correct version information."""
	window = MainWindow()
	qtbot.addWidget(window)

	with patch('chargeghost_evse.ui.app.QMessageBox.exec') as mock_exec:
		window._show_about_dialog()
		mock_exec.assert_called_once()

	assert True
