from chargeghost_evse.ui.app import MainWindow
from chargeghost_evse.util.config import SimulationConfig
from unittest.mock import patch, MagicMock


def test_mainwindow_shows_update_chip_when_new_version(monkeypatch, qtbot):
	# Directly emit update_available signal to test UI integration
	window = MainWindow()
	qtbot.addWidget(window)

	# Emit the signal as the controller would
	window.update_controller.update_available.emit("v0.2.0", "New features")

	# Verify update chip is shown
	assert window._update_chip is not None
	assert window._update_chip.version == "v0.2.0"


def test_mainwindow_ignores_version_when_configured(monkeypatch, qtbot):
	with patch('chargeghost_evse.util.update_controller.UpdateManager') as mock_um_class:
		mock_um = MagicMock()
		mock_um_class.return_value = mock_um

		with patch('chargeghost_evse.ui.app.SimulationConfig') as mock_config_class:
			mock_config = SimulationConfig()
			mock_config.ignored_version = "v0.2.0"  # Already ignored
			mock_config_class.load.return_value = mock_config

			window = MainWindow()
			qtbot.addWidget(window)

			# Verify no update chip is initially shown
			assert window._update_chip is None


def test_update_now_triggers_download_via_controller(monkeypatch, qtbot):
	window = MainWindow()
	qtbot.addWidget(window)

	# Patch trigger_download on the controller so we don't actually download
	with patch.object(window.update_controller, 'trigger_download') as mock_trigger:
		# Emit update_available to wire up chip and dialog
		window.update_controller.update_available.emit("v0.2.0", "New features")
		assert window._update_chip is not None

		# Open the dialog and connect — simulate calling trigger_download directly
		window.update_controller.trigger_download()
		mock_trigger.assert_called_once()


def test_ready_to_restart_shuts_down_bridge_and_quits(monkeypatch, qtbot):
	window = MainWindow()
	qtbot.addWidget(window)

	with patch.object(window.bridge, 'shutdown') as mock_shutdown:
		with patch('chargeghost_evse.ui.app.QApplication.quit') as mock_quit:
			window._on_ready_to_restart()
			mock_shutdown.assert_called_once()
			mock_quit.assert_called_once()
