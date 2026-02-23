from chargeghost_evse.util.handover_manager import HandoverManager


def test_generate_windows_script_contains_move_and_restart(tmp_path):
	h = HandoverManager(tmp_path)
	script = h.build_windows_script(pid=123, new_path="C:/tmp/new.exe", old_path="C:/app/old.exe")
	assert "move /y" in script
	assert "start \"\"" in script


def test_generate_macos_script_contains_commands(tmp_path):
	h = HandoverManager(tmp_path)
	script = h.build_macos_script(pid=123, new_path="/tmp/new.app", old_path="/Applications/Old.app")
	assert "rm -rf" in script
	assert "mv" in script
	assert "open" in script
