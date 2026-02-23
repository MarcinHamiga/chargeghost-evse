from chargeghost_evse.ui.widgets.update_dialog import UpdateDialog


def test_dialog_exposes_three_user_actions(qtbot):
	dlg = UpdateDialog(current_version="0.1.0", latest_version="0.2.0", release_notes="notes")
	qtbot.addWidget(dlg)
	assert dlg.btn_update_now is not None
	assert dlg.btn_later is not None
	assert dlg.btn_ignore is not None
