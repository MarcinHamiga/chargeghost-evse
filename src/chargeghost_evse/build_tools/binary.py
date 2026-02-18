#!/usr/bin/env python3
"""Build binary using PyInstaller with platform-specific icons."""

import platform
import shutil
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
        icon_path = (
            ICONS_DIR
            / "linux"
            / "hicolor"
            / "256x256"
            / "apps"
            / "chargeghost-evse.png"
        )

    return icon_path.exists()


def main():
    if not check_icons():
        print("Icons not found. Generating icons first...")
        from chargeghost_evse.build_tools.icons import main as generate_icons

        generate_icons()

    print(f"Building for {current_os}...")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
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
