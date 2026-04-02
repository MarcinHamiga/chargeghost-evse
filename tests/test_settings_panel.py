from __future__ import annotations

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QWidget

from chargeghost_evse.ui.widgets.connector_panel import ConnectorPanel
from chargeghost_evse.ui.widgets.settings_panel import SettingsPanel


def _app() -> QApplication:
	app = QApplication.instance()
	if app is None:
		app = QApplication([])
	return app


def test_settings_panel_exposes_split_layout_sections(qtbot) -> None:
	_app()
	panel = SettingsPanel()
	qtbot.addWidget(panel)

	rail = panel.findChild(QWidget, "settingsRail")
	workspace = panel.findChild(QWidget, "settingsWorkspace")

	assert rail is not None
	assert workspace is not None


def test_settings_panel_exposes_prominent_save_action(qtbot) -> None:
	_app()
	panel = SettingsPanel()
	qtbot.addWidget(panel)

	header = panel.findChild(QWidget, "settingsHeader")
	assert header is not None

	save_btn = panel.findChild(QWidget, "btnSaveConfig")
	assert save_btn is not None
	assert save_btn.property("primary") is True


def test_settings_panel_keeps_connection_and_identity_sections(qtbot) -> None:
	_app()
	panel = SettingsPanel()
	qtbot.addWidget(panel)

	assert panel.input_url is not None
	assert panel.input_ocpp_id is not None
	assert panel.input_password is not None
	assert panel.input_vendor is not None
	assert panel.input_model is not None


def test_settings_panel_embeds_connector_workspace(qtbot) -> None:
	_app()
	panel = SettingsPanel()
	qtbot.addWidget(panel)

	workspace = panel.findChild(QWidget, "settingsWorkspace")
	assert workspace is not None

	connector = panel.findChild(ConnectorPanel)
	assert connector is not None

	parent = connector.parent()
	ancestors: list[QWidget] = []
	current = parent
	while current is not None:
		ancestors.append(current)
		current = current.parent()
	assert workspace in ancestors


def test_settings_panel_switches_to_stacked_mode_when_narrow(qtbot) -> None:
	_app()
	panel = SettingsPanel()
	qtbot.addWidget(panel)
	panel.resize(900, 700)
	panel.show()
	_app().processEvents()

	assert panel.property("layoutMode") == "stacked"


def test_settings_panel_returns_to_split_mode_when_wide(qtbot) -> None:
	_app()
	panel = SettingsPanel()
	qtbot.addWidget(panel)
	panel.resize(1400, 700)
	panel.show()
	_app().processEvents()

	assert panel.property("layoutMode") == "split"
