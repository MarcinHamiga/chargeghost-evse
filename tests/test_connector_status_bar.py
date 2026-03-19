# tests/test_connector_status_bar.py
import sys

import pytest
from PySide6.QtWidgets import QApplication

@pytest.fixture(scope="session")
def qt_app():
	app = QApplication.instance() or QApplication(sys.argv)
	yield app

def test_status_bar_creates_pill_per_connector(qt_app):
	from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
	bar = ConnectorStatusBar()
	bar.update_connector(1, "Available", None)
	bar.update_connector(2, "Charging", 62.0)
	assert len(bar._pills) == 2

def test_update_connector_new_pill(qt_app):
	from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
	bar = ConnectorStatusBar()
	bar.update_connector(3, "Faulted", None)
	assert 3 in bar._pills

def test_update_connector_updates_existing_pill(qt_app):
	from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
	bar = ConnectorStatusBar()
	bar.update_connector(1, "Available", None)
	bar.update_connector(1, "Charging", 50.0)
	# Still only one pill for connector 1
	assert len(bar._pills) == 1

def test_session_stats_hidden_when_no_session(qt_app):
	from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
	bar = ConnectorStatusBar()
	assert not bar._stats_widget.isVisible()

def test_session_stats_shown_with_active_session(qt_app):
	from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
	bar = ConnectorStatusBar()
	bar.update_session_stats(7.4, 62.0, "0:24:11")
	assert bar._stats_widget.isVisible()

def test_session_stats_shown_when_suspended_zero_power(qt_app):
	"""Stats must remain visible during SuspendedEV/EVSE where power is 0."""
	from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
	bar = ConnectorStatusBar()
	bar.update_session_stats(0.0, 45.0, "0:10:00")
	assert bar._stats_widget.isVisible()

def test_session_stats_hidden_via_hide_session_stats(qt_app):
	from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
	bar = ConnectorStatusBar()
	bar.update_session_stats(7.4, 62.0, "0:24:11")
	bar.hide_session_stats()
	assert not bar._stats_widget.isVisible()

def test_connector_selected_signal(qt_app):
	from chargeghost_evse.ui.widgets.connector_status_bar import ConnectorStatusBar
	bar = ConnectorStatusBar()
	bar.update_connector(1, "Available", None)
	received = []
	bar.connector_selected.connect(lambda cid: received.append(cid))
	bar._pills[1].clicked.emit(1)
	assert received == [1]
