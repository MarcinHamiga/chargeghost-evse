#!/usr/bin/env python3
"""Build binary using PyInstaller with platform-specific icons."""

import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
SPEC_FILE = PROJECT_ROOT / "assets" / "build" / "chargeghost-evse.spec"
ICONS_DIR = PROJECT_ROOT / "assets" / "icons"

current_os = platform.system()


def check_icons() -> bool:
	if current_os == "Windows":
		icon_path = ICONS_DIR / "windows" / "ChargeGhost.ico"
	elif current_os == "Darwin":
		icon_path = ICONS_DIR / "macos" / "ChargeGhost.icns"
	else:
		icon_path = ICONS_DIR / "linux" / "hicolor" / "256x256" / "apps" / "chargeghost-evse.png"
	
	return icon_path.exists()


def fix_macos_terminal_launch():
	app_path = PROJECT_ROOT / "dist" / "ChargeGhost EVSE.app"
	contents_dir = app_path / "Contents"
	macos_dir = contents_dir / "MacOS"
	
	old_exe = macos_dir / "chargeghost-evse"
	new_exe = macos_dir / "chargeghost-evse-bin"
	
	if old_exe.exists():
		old_exe.rename(new_exe)
	
	wrapper_script = macos_dir / "chargeghost-evse"
	wrapper_script.write_text('''#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
osascript -e "tell application \\"Terminal\\" to activate" \\
          -e "tell application \\"Terminal\\" to do script \\"'${SCRIPT_DIR}/chargeghost-evse-bin'\\""
''')
	wrapper_script.chmod(wrapper_script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main():
	if not check_icons():
		print("Icons not found. Generating icons first...")
		from chargeghost_evse.build_tools.icons import main as generate_icons
		generate_icons()
	
	print(f"Building for {current_os}...")
	
	cmd = [
		sys.executable,
		"-m", "PyInstaller",
		"--clean",
		"--noconfirm",
		str(SPEC_FILE),
	]
	
	result = subprocess.run(cmd, cwd=PROJECT_ROOT)
	
	if result.returncode == 0:
		dist_dir = PROJECT_ROOT / "dist"
		if current_os == "Darwin":
			intermediate_dir = dist_dir / "chargeghost-evse"
			if intermediate_dir.exists():
				shutil.rmtree(intermediate_dir)
			fix_macos_terminal_launch()
			app_path = dist_dir / "ChargeGhost EVSE.app"
			print("\nBuild complete!")
			print(f"  macOS app: {app_path}")
		elif current_os == "Windows":
			exe_path = dist_dir / "chargeghost-evse.exe"
			print("\nBuild complete!")
			print(f"  Binary: {exe_path}")
		else:
			exe_path = dist_dir / "chargeghost-evse"
			print("\nBuild complete!")
			print(f"  Binary: {exe_path}")
	else:
		print("Build failed!")
		sys.exit(1)


if __name__ == "__main__":
	main()
