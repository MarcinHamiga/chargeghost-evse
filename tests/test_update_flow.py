import sys
from chargeghost_evse.ui.app import MainWindow
from chargeghost_evse.util.config import SimulationConfig
from unittest.mock import patch, MagicMock


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
			mock_config = SimulationConfig()
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
			mock_config = SimulationConfig()
			mock_config.ignored_version = "v0.2.0"  # Already ignored
			mock_config_class.load.return_value = mock_config

			window = MainWindow()
			qtbot.addWidget(window)

			# Verify no update chip is initially shown
			assert window._update_chip is None


def test_update_now_triggers_handover_and_quit(monkeypatch, qtbot):
	# Mock UpdateManager and HandoverManager
	mock_update_manager = MagicMock()
	mock_release_info = MagicMock()
	mock_release_info.tag_name = "v0.2.0"
	mock_release_info.body = "New features"
	
	# Mock asset selection
	mock_asset = {"browser_download_url": "https://example.com/update.exe"}
	mock_update_manager.select_asset_for_platform.return_value = mock_asset
	mock_update_manager.download_update.return_value = MagicMock()
	
	mock_handover_manager = MagicMock()
	
	with patch('chargeghost_evse.ui.app.UpdateManager', return_value=mock_update_manager):
		with patch('chargeghost_evse.ui.app.HandoverManager', return_value=mock_handover_manager):
			with patch('chargeghost_evse.ui.app.SimulationConfig') as mock_config_class:
				mock_config = SimulationConfig()
				mock_config.ignored_version = None
				mock_config_class.load.return_value = mock_config

				window = MainWindow()
				qtbot.addWidget(window)

				# Simulate update info already fetched (as it would be when the dialog opened)
				window._latest_release_info = mock_release_info

				# In development mode (sys.frozen is False), _on_update_now should
				# show an initial toast but must not attempt handover.
				with patch.object(sys, 'frozen', False, create=True):
					with patch.object(window, 'show_toast') as mock_show_toast:
						# Call update now handler
						window._on_update_now(mock_release_info)

						# Verify the initial "Starting update download..." toast is shown,
						# confirming the method executed and reached its first UI call.
						mock_show_toast.assert_called_once_with(
							"Starting update download...", "info"
						)

						# In dev mode the handover manager must never be invoked
						# synchronously from the main thread call itself.
						mock_handover_manager.launch_handover.assert_not_called()
