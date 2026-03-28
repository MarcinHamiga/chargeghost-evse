import sys

import pytest
from PySide6.QtWidgets import QApplication

from chargeghost_evse.devtools.timeline_models import TimelineFilter
from chargeghost_evse.devtools.timeline_store import TimelineStore


@pytest.fixture(scope="session")
def qt_app():
	app = QApplication.instance() or QApplication(sys.argv)
	yield app


class TestOCPPTimelinePanel:
	def test_log_side_panel_exposes_timeline_view(self, qt_app):
		from chargeghost_evse.ui.widgets.log_side_panel import LogSidePanel

		panel = LogSidePanel()
		assert hasattr(panel, "timeline_panel")
		from chargeghost_evse.ui.widgets.ocpp_timeline_panel import OCPPTimelinePanel

		assert isinstance(panel.timeline_panel, OCPPTimelinePanel)

	def test_ocpp_timeline_panel_filters_by_direction(self, qt_app):
		from chargeghost_evse.ui.widgets.ocpp_timeline_panel import OCPPTimelinePanel

		panel = OCPPTimelinePanel()
		store = TimelineStore(max_length=100)
		panel.set_store(store)

		store.append(
			source="ocpp",
			direction="inbound",
			event_type="action",
			action="Authorize",
			summary="Authorize request",
		)
		store.append(
			source="ocpp",
			direction="outbound",
			event_type="action",
			action="BootNotification",
			summary="BootNotification response",
		)
		store.append(
			source="ocpp",
			direction="local",
			event_type="session",
			action="session_started",
			summary="Session started",
		)

		events_inbound = store.query(TimelineFilter(direction="inbound"))
		assert len(events_inbound) == 1
		assert events_inbound[0].action == "Authorize"

		events_outbound = store.query(TimelineFilter(direction="outbound"))
		assert len(events_outbound) == 1
		assert events_outbound[0].action == "BootNotification"

		events_local = store.query(TimelineFilter(direction="local"))
		assert len(events_local) == 1
		assert events_local[0].action == "session_started"

	def test_ocpp_timeline_panel_updates_when_store_changes(self, qt_app):
		from chargeghost_evse.ui.widgets.ocpp_timeline_panel import OCPPTimelinePanel

		panel = OCPPTimelinePanel()
		store = TimelineStore(max_length=100)
		panel.set_store(store)

		assert len(panel._entry_widgets) == 0

		store.append(
			source="ocpp",
			direction="inbound",
			event_type="action",
			action="Authorize",
			summary="Authorize request",
		)

		qt_app.processEvents()
		assert len(panel._entry_widgets) == 1

		store.append(
			source="ocpp",
			direction="outbound",
			event_type="action",
			action="BootNotification",
			summary="BootNotification response",
		)

		qt_app.processEvents()
		assert len(panel._entry_widgets) == 2

	def test_ocpp_timeline_panel_exposes_export_action(self, qt_app):
		from chargeghost_evse.ui.widgets.ocpp_timeline_panel import OCPPTimelinePanel

		panel = OCPPTimelinePanel()
		assert hasattr(panel, "has_export_action")
		assert panel.has_export_action is True
		assert hasattr(panel, "has_copy_action")
		assert panel.has_copy_action is True
