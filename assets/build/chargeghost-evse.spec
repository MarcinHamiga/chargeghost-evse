# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for ChargeGhost EVSE with platform-specific icons."""

import platform
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

PROJECT_ROOT = Path(SPECPATH).parent.parent
ICONS_DIR = PROJECT_ROOT / "assets" / "icons"
SOURCE_DIR = PROJECT_ROOT / "src"

current_os = platform.system()

rich_hiddenimports = collect_submodules("rich")
textual_hiddenimports = collect_submodules("textual")
ocpp_hiddenimports = collect_submodules("ocpp")

# Collect data files for ocpp (schemas)
ocpp_datas = collect_data_files("ocpp")

# Include UI styles directory for frozen app
# Place styles at 'chargeghost_evse/ui/styles' to match module structure
styles_dir = SOURCE_DIR / "chargeghost_evse" / "ui" / "styles"
ui_datas = [(str(styles_dir), "chargeghost_evse/ui/styles")]

if current_os == "Windows":
        icon_path = ICONS_DIR / "windows" / "ChargeGhost.ico"
elif current_os == "Darwin":
        icon_path = ICONS_DIR / "macos" / "ChargeGhost.icns"
else:
        icon_path = ICONS_DIR / "linux" / "hicolor" / "256x256" / "apps" / "chargeghost-evse.png"

icon_path_str = str(icon_path) if icon_path.exists() else None

if not icon_path.exists():
        print(f"Warning: Icon not found at {icon_path}")
        print("Run 'poetry run build-icons' first to generate icons")
        icon_path_str = None

a = Analysis(
        [str(SOURCE_DIR / "chargeghost_evse" / "main.py")],
        pathex=[],
        binaries=[],
        datas=ocpp_datas + ui_datas,
        hiddenimports=[
                "chargeghost_evse",
                "chargeghost_evse.main",
                "chargeghost_evse.ui",
                "chargeghost_evse.ui.app",
                "chargeghost_evse.engine",
                "chargeghost_evse.engine.engine",
                "chargeghost_evse.engine.connector",
                "chargeghost_evse.engine.session",
                "chargeghost_evse.engine.energy_meter",
                "chargeghost_evse.ocpp_adapter",
                "chargeghost_evse.ocpp_adapter.adapter",
                "chargeghost_evse.bridge",
                "chargeghost_evse.bridge.bridge",
                "chargeghost_evse.util",
                "chargeghost_evse.util.event",
                "chargeghost_evse.util.subscriber",
                "chargeghost_evse.util.config",
                "chargeghost_evse.util.update_manager",
                "chargeghost_evse.util.handover_manager",
                "chargeghost_evse.ui.widgets",
                "chargeghost_evse.ui.widgets.update_dialog",
                "websockets",
                "websockets.client",
                "websockets.legacy",
                "websockets.legacy.client",
                "pydantic",
                "pydantic_settings",
                "yaml",
                "aiohttp",
                "asyncio",
                "threading",
                "tempfile",
                "platform",
                "subprocess",
        ] + rich_hiddenimports + textual_hiddenimports + ocpp_hiddenimports,
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[
        "assets/build/rthook_chargeghost_updater.py",
],
        excludes=[],
        noarchive=False,
        optimize=0,
)

pyz = PYZ(a.pure)

if current_os == "Darwin":
        exe = EXE(
                pyz,
                a.scripts,
                [],
                exclude_binaries=True,
                name="chargeghost-evse",
                debug=False,
                bootloader_ignore_signals=False,
                strip=False,
                upx=True,
                console=False,
                disable_windowed_traceback=False,
                argv_emulation=False,
                target_arch=None,
                codesign_identity=None,
                entitlements_file=None,
                icon=icon_path_str,
        )
        coll = COLLECT(
                exe,
                a.binaries,
                a.datas,
                strip=False,
                upx=True,
                upx_exclude=[],
                name="chargeghost-evse",
        )
        app = BUNDLE(
                coll,
                name="ChargeGhost EVSE.app",
                icon=icon_path_str,
                bundle_identifier="com.chargeghost.evse",
                version="v0.8.1",
                info_plist={
                        "CFBundleName": "ChargeGhost EVSE",
                        "CFBundleDisplayName": "ChargeGhost EVSE",
                        "CFBundleGetInfoString": "EVSE Simulator",
                        "CFBundleVersion": "v0.4.1",
                        "CFBundleShortVersionString": "v0.4.1",
                        "NSHighResolutionCapable": True,
                        "LSMinimumSystemVersion": "10.13.0",
                },
        )
elif current_os == "Windows":
        exe = EXE(
                pyz,
                a.scripts,
                a.binaries,
                a.datas,
                [],
                name="chargeghost-evse",
                debug=False,
                bootloader_ignore_signals=False,
                strip=False,
                upx=True,
                upx_exclude=[],
                console=False,
                disable_windowed_traceback=False,
                argv_emulation=False,
                target_arch=None,
                codesign_identity=None,
                entitlements_file=None,
                icon=icon_path_str,
        )
else:
        exe = EXE(
                pyz,
                a.scripts,
                a.binaries,
                a.datas,
                [],
                name="chargeghost-evse",
                debug=False,
                bootloader_ignore_signals=False,
                strip=False,
                upx=True,
                upx_exclude=[],
                console=False,
                disable_windowed_traceback=False,
                argv_emulation=False,
                target_arch=None,
                codesign_identity=None,
                entitlements_file=None,
                icon=icon_path_str,
        )
