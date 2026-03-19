import sys

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qt_app():
	app = QApplication.instance() or QApplication(sys.argv)
	yield app


def test_connector_panel_has_grid(qt_app):
	"""ConnectorPanel should expose _connectors_grid after the refactor."""
	from chargeghost_evse.ui.widgets.connector_panel import ConnectorPanel
	panel = ConnectorPanel()
	assert hasattr(panel, "_connectors_grid")
