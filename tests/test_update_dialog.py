from chargeghost_evse.ui.widgets.update_dialog import UpdateDialog
from chargeghost_evse.ui.widgets.update_dialog import UpdateStatusChip


def test_dialog_exposes_three_user_actions(qtbot):
	dlg = UpdateDialog(current_version="0.1.0", latest_version="0.2.0", release_notes="notes")
	qtbot.addWidget(dlg)
	assert dlg.btn_update_now is not None
	assert dlg.btn_later is not None
	assert dlg.btn_ignore is not None


def test_update_surfaces_use_theme_object_names(qtbot):
	dlg = UpdateDialog(current_version="0.1.0", latest_version="0.2.0", release_notes="notes")
	chip = UpdateStatusChip("v0.2.0")
	qtbot.addWidget(dlg)
	qtbot.addWidget(chip)

	assert dlg.objectName() == "updateDialog"
	assert dlg.header_label.objectName() == "updateDialogHeader"
	assert dlg.notes_label.objectName() == "updateDialogNotesLabel"
	assert dlg.release_notes_text.objectName() == "updateDialogReleaseNotes"
	assert dlg.btn_update_now.objectName() == "updatePrimaryButton"
	assert chip.objectName() == "updateStatusChip"
	assert dlg.styleSheet() == ""
	assert chip.styleSheet() == ""
