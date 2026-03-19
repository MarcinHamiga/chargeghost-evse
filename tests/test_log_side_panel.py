# tests/test_log_side_panel.py
import pytest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication
import sys

@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app

def test_log_side_panel_starts_collapsed(qt_app):
    from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel
    panel = LogSidePanel()
    assert not panel.is_open()

def test_log_side_panel_toggle_opens(qt_app):
    from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel
    panel = LogSidePanel()
    panel.toggle()
    assert panel.is_open()

def test_log_side_panel_toggle_closes(qt_app):
    from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel
    panel = LogSidePanel()
    panel.toggle()
    panel.toggle()
    assert not panel.is_open()

def test_unread_badge_increments(qt_app):
    from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel
    panel = LogSidePanel()
    panel.increment_unread()
    panel.increment_unread()
    assert panel._unread_count == 2

def test_clear_unread_resets(qt_app):
    from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel
    panel = LogSidePanel()
    panel.increment_unread()
    panel.clear_unread()
    assert panel._unread_count == 0

def test_log_message_delegates(qt_app):
    from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel
    panel = LogSidePanel()
    panel._log_panel.log_message = MagicMock()
    panel.log_message("hello")
    panel._log_panel.log_message.assert_called_once_with("hello")
