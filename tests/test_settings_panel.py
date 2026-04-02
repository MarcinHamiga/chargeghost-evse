from __future__ import annotations

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QWidget

from chargeghost_evse.ui.widgets.connector_panel import ConnectorPanel
from chargeghost_evse.ui.widgets.settings_panel import SettingsPanel
from chargeghost_evse.util.config import (
    BATTERY_CAPACITY_DEFAULT,
    BATTERY_CAPACITY_MAX,
    BATTERY_CAPACITY_MIN,
    SimulationConfig,
)


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


def test_settings_panel_has_battery_capacity_input(qtbot) -> None:
	_app()
	panel = SettingsPanel()
	qtbot.addWidget(panel)

	assert hasattr(panel, "input_battery_capacity")
	spin = panel.input_battery_capacity
	assert spin.minimum() == BATTERY_CAPACITY_MIN
	assert spin.maximum() == BATTERY_CAPACITY_MAX
	assert spin.suffix() == " kWh"
	assert spin.decimals() == 1
	assert spin.value() == BATTERY_CAPACITY_DEFAULT


def test_settings_panel_populates_battery_capacity(qtbot) -> None:
	_app()
	panel = SettingsPanel()
	qtbot.addWidget(panel)

	config = SimulationConfig()
	config.ev_battery_capacity = 85.0
	panel.set_config(config)

	assert panel.input_battery_capacity.value() == 85.0


def test_settings_panel_saves_battery_capacity(qtbot) -> None:
	_app()
	panel = SettingsPanel()
	qtbot.addWidget(panel)

	config = SimulationConfig()
	panel.set_config(config)

	panel.input_battery_capacity.setValue(120.0)
	saved = []

	def on_save():
		saved.append(True)

	panel.save_config_clicked.connect(on_save)
	panel._on_save_config()

	assert config.ev_battery_capacity == 120.0
	assert len(saved) == 1
