#!/usr/bin/env python3
"""Generate platform-specific icon sets from a source PNG."""

import platform
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow is required. Install with: poetry install --with dev")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
SOURCE_ICON = PROJECT_ROOT / "assets" / "ChargeGhost.png"
ICONS_DIR = PROJECT_ROOT / "assets" / "icons"

WINDOWS_SIZES = [16, 24, 32, 48, 64, 128, 256]
MACOS_SIZES = [16, 32, 64, 128, 256, 512, 1024]
LINUX_SIZES = [16, 22, 24, 32, 48, 64, 128, 256, 512]


def generate_windows_icons(source_img: Image.Image) -> Path:
    windows_dir = ICONS_DIR / "windows"
    windows_dir.mkdir(parents=True, exist_ok=True)

    ico_path = windows_dir / "ChargeGhost.ico"

    images = []
    for size in WINDOWS_SIZES:
        resized = source_img.resize((size, size), Image.Resampling.LANCZOS)
        images.append(resized)

    source_img.save(
        ico_path,
        format="ICO",
        sizes=[(img.width, img.height) for img in images],
        append_images=images[1:],
    )
    print(f"  [Windows] Created {ico_path.relative_to(PROJECT_ROOT)}")
    return ico_path


def generate_macos_icons(source_img: Image.Image) -> Path:
    macos_dir = ICONS_DIR / "macos" / "ChargeGhost.iconset"
    macos_dir.mkdir(parents=True, exist_ok=True)

    for size in MACOS_SIZES:
        resized = source_img.resize((size, size), Image.Resampling.LANCZOS)
        filename = f"icon_{size}x{size}.png"
        resized.save(macos_dir / filename, format="PNG")

        if size <= 512:
            retina_size = size * 2
            retina_resized = source_img.resize(
                (retina_size, retina_size), Image.Resampling.LANCZOS
            )
            retina_filename = f"icon_{size}x{size}@2x.png"
            retina_resized.save(macos_dir / retina_filename, format="PNG")

    icns_path = ICONS_DIR / "macos" / "ChargeGhost.icns"

    if platform.system() == "Darwin":
        if icns_path.exists():
            icns_path.unlink()
        result = subprocess.run(
            ["iconutil", "-c", "icns", "-o", str(icns_path), str(macos_dir)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"  [macOS] Created {icns_path.relative_to(PROJECT_ROOT)}")
        else:
            print(f"  [macOS] iconutil failed: {result.stderr}")
            print(f"  [macOS] iconset created at {macos_dir.relative_to(PROJECT_ROOT)}")
    else:
        print(f"  [macOS] iconset created at {macos_dir.relative_to(PROJECT_ROOT)}")
        print(
            "  [macOS] Run 'iconutil -c icns assets/icons/macos/ChargeGhost.iconset' on macOS to create .icns"
        )

    return icns_path


def generate_linux_icons(source_img: Image.Image) -> Path:
    linux_dir = ICONS_DIR / "linux" / "hicolor"

    for size in LINUX_SIZES:
        size_dir = linux_dir / f"{size}x{size}" / "apps"
        size_dir.mkdir(parents=True, exist_ok=True)

        resized = source_img.resize((size, size), Image.Resampling.LANCZOS)
        icon_path = size_dir / "chargeghost-evse.png"
        resized.save(icon_path, format="PNG")

    scalable_dir = linux_dir / "scalable" / "apps"
    scalable_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(SOURCE_ICON, scalable_dir / "chargeghost-evse.png")

    print(f"  [Linux] Created icons in {linux_dir.relative_to(PROJECT_ROOT)}")
    return linux_dir


def main():
    print(f"Generating icons from {SOURCE_ICON.relative_to(PROJECT_ROOT)}")

    if not SOURCE_ICON.exists():
        print(f"Error: Source icon not found at {SOURCE_ICON}")
        sys.exit(1)

    source_img = Image.open(SOURCE_ICON)
    print(f"  Source image: {source_img.width}x{source_img.height}")

    if source_img.mode != "RGBA":
        source_img = source_img.convert("RGBA")

    generate_windows_icons(source_img)
    generate_macos_icons(source_img)
    generate_linux_icons(source_img)

    print("\nIcon generation complete!")


if __name__ == "__main__":
    main()
