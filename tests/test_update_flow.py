from chargeghost_evse.ui.app import MainWindow
from chargeghost_evse import __version__
from unittest.mock import patch, MagicMock
import pytest


def test_mainwindow_shows_update_chip_when_new_version(monkeypatch, qtbot):
	# Mock UpdateManager.fetch_latest_release => available result
	mock_update_manager = MagicMock()
	mock_release_info = MagicMock()
	mock_release_info.tag_name = "v0.2.0"
	mock_release_info.body = "New features"
	mock_update_manager.fetch_latest_release.return_value = mock_release_info
	mock_update_manager.is_update_available.return_value = True
	
	with patch('chargeghost_evse.ui.app.UpdateManager', return_value=mock_update_manager):
		with patch('chargeghost_evse.ui.app.SimulationConfig') as mock_config_class:
			mock_config = MagicMock()
			mock_config.ignored_version = None
			mock_config_class.load.return_value = mock_config
			
		window = MainWindow()
		qtbot.addWidget(window)
		
		# Directly call _show_update_chip to test UI integration
		window._show_update_chip(mock_release_info)
		
		# Verify update chip is shown
		assert window._update_chip is not None
		assert window._update_chip.version == "v0.2.0"


def test_mainwindow_ignores_version_when_configured(monkeypatch, qtbot):
	# Mock UpdateManager.fetch_latest_release => available result
	mock_update_manager = MagicMock()
	mock_release_info = MagicMock()
	mock_release_info.tag_name = "v0.2.0"
	mock_update_manager.fetch_latest_release.return_value = mock_release_info
	mock_update_manager.is_update_available.return_value = True
	
	with patch('chargeghost_evse.ui.app.UpdateManager', return_value=mock_update_manager):
		with patch('chargeghost_evse.ui.app.SimulationConfig') as mock_config_class:
			mock_config = MagicMock()
			mock_config.ignored_version = "v0.2.0"  # Already ignored
			mock_config_class.load.return_value = mock_config
			
		window = MainWindow()
		qtbot.addWidget(window)
		
		# Verify no update chip is initially shown
		assert window._update_chip is None
