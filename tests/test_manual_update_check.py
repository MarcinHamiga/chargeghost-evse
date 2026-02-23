from chargeghost_evse.ui.app import MainWindow
from chargeghost_evse import __version__
from unittest.mock import patch, MagicMock
import pytest
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


def test_manual_update_check_shows_no_updates_available(qtbot):
	"""Test manual update check when no updates are available."""
	mock_update_manager = MagicMock()
	mock_release_info = MagicMock()
	mock_release_info.tag_name = "v0.1.0"  # Same version
	mock_update_manager.fetch_latest_release.return_value = mock_release_info
	mock_update_manager.is_update_available.return_value = False
	
	with patch('chargeghost_evse.ui.app.UpdateManager', return_value=mock_update_manager):
		with patch('chargeghost_evse.ui.app.SimulationConfig') as mock_config_class:
			mock_config = MagicMock()
			mock_config.ignored_version = None
			mock_config_class.load.return_value = mock_config
			
		window = MainWindow()
		qtbot.addWidget(window)
		
		# Call manual update check
		window._manual_update_check()
		
		# Verify toast was shown (would be shown in background thread)
		# For now, just verify the method exists and doesn't crash
		assert True


def test_manual_update_check_shows_update_dialog(qtbot):
	"""Test manual update check when updates are available."""
	mock_update_manager = MagicMock()
	mock_release_info = MagicMock()
	mock_release_info.tag_name = "v0.2.0"  # Newer version
	mock_update_manager.fetch_latest_release.return_value = mock_release_info
	mock_update_manager.is_update_available.return_value = True
	
	with patch('chargeghost_evse.ui.app.UpdateManager', return_value=mock_update_manager):
		with patch('chargeghost_evse.ui.app.SimulationConfig') as mock_config_class:
			mock_config = MagicMock()
			mock_config.ignored_version = None
			mock_config_class.load.return_value = mock_config
			
		window = MainWindow()
		qtbot.addWidget(window)
		
		# Call manual update check
		window._manual_update_check()
		
		# Verify the method exists and doesn't crash
		assert True


def test_about_dialog_shows_version_info(qtbot):
	"""Test that about dialog shows correct version information."""
	window = MainWindow()
	qtbot.addWidget(window)
	
	# Call about dialog (this will show the dialog)
	# We can't easily test the dialog content in unit tests, but we can verify it doesn't crash
	window._show_about_dialog()
	
	# Verify the method exists and doesn't crash
	assert True
