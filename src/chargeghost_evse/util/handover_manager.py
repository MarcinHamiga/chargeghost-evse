import os
import platform
import subprocess
from pathlib import Path


class HandoverManager:
	def __init__(self, temp_dir: Path):
		self.temp_dir = temp_dir

	def build_windows_script(self, pid: int, new_path: str, old_path: str) -> str:
		return f"""@echo off
set "TARGET_PID={pid}"
set "NEW_EXE={new_path}"
set "OLD_EXE={old_path}"
:wait
tasklist /FI "PID eq %TARGET_PID%" | find ":" > nul
if %errorlevel% neq 0 (
	move /y "%NEW_EXE%" "%OLD_EXE%"
	start "" "%OLD_EXE%"
	del "%~f0"
	exit
)
timeout /t 1 /nobreak > nul
goto wait
"""

	def build_macos_script(self, pid: int, new_path: str, old_path: str) -> str:
		return f"""#!/bin/bash
PID={pid}
NEW_APP_PATH="{new_path}"
OLD_APP_PATH="{old_path}"
while kill -0 $PID 2>/dev/null; do sleep 1; done
rm -rf "$OLD_APP_PATH"
mv "$NEW_APP_PATH" "$OLD_APP_PATH"
open "$OLD_APP_PATH"
rm "$0"
"""

	def launch_handover(self, script_path: Path) -> None:
		if platform.system() == "Windows":
			subprocess.Popen(["cmd", "/c", str(script_path)], start_new_session=True)
		else:
			script_path.chmod(0o755)
			subprocess.Popen([str(script_path)], start_new_session=True)
