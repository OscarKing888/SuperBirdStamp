# -*- mode: python ; coding: utf-8 -*-
# BirdStamp macOS PyInstaller spec
# Run from project root: pyinstaller BirdStamp_mac.spec
#
# Prerequisites:
#   pip install pyinstaller pyinstaller-hooks-contrib
#
# Output: dist/SuperBirdStamp.app

from __future__ import annotations

from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# --------------------------------------------------------------------------- #
# Collect complex packages that rely on dynamic imports / native extensions
# --------------------------------------------------------------------------- #
ultralytics_datas, ultralytics_binaries, ultralytics_hiddenimports = collect_all("ultralytics")

# --------------------------------------------------------------------------- #
# Project-specific data files
# --------------------------------------------------------------------------- #
project_datas = [
    # YOLO bird-detection model
    ("models", "models"),
    # App window icon (app_icon.icns / app_icon.png)
    ("icons", "icons"),
    # Placeholder preview image (default.jpg)
    ("images", "images"),
    # Config and JSON data (birdstamp.cfg, config/templates/*.json, editor options, context routes)
    ("config", "config"),
]

# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=ultralytics_binaries,
    datas=project_datas + ultralytics_datas,
    hiddenimports=[
        # PyQt6
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtPrintSupport",
        "PyQt6.QtSvg",
        # Pillow plugins that may not be auto-detected
        "PIL.ImageDraw",
        "PIL.ImageFont",
        "PIL.ImageFilter",
        "PIL.ExifTags",
        "PIL.TiffImagePlugin",
        "PIL.JpegImagePlugin",
        "PIL.PngImagePlugin",
        "PIL.WebPImagePlugin",
        # Optional decoders
        "rawpy",
        "pillow_heif",
        # YAML / CLI
        "yaml",
        "typer",
        "click",
        # app_common shared UI components
        "app_common",
        "app_common.about_dialog",
        "app_common.about_dialog.dialog",
        "app_common.about_dialog.config",
        "app_common.app_info_bar",
        "app_common.app_info_bar.widget",
        "app_common.ui_style",
        "app_common.ui_style.styles",
        # birdstamp internal
        "birdstamp.subprocess_utils",
    ]
    + ultralytics_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["scripts_dev/pyi_rthook_cwd.py"],
    excludes=[
        # Keep out IPython / notebook cruft that ultralytics may pull in
        "IPython",
        "notebook",
        "nbformat",
        "matplotlib",
        "tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SuperBirdStamp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # Keep False: UPX can corrupt Torch/MPS native libs
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # None = native arch; set "universal2" for fat binary
    codesign_identity=None,
    entitlements_file=None,
    icon="icons/app_icon.icns",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SuperBirdStamp",
)

app = BUNDLE(
    coll,
    name="SuperBirdStamp.app",
    icon="icons/app_icon.icns",
    bundle_identifier="com.birdstamp.app",
    info_plist={
        "NSPrincipalClass": "NSApplication",
        "NSHighResolutionCapable": True,
        "NSCameraUsageDescription": "BirdStamp does not require camera access.",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "12.0",
        # Allow opening images via Finder drag-and-drop / open-with
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "Image",
                "CFBundleTypeRole": "Viewer",
                "LSItemContentTypes": [
                    "public.jpeg",
                    "public.png",
                    "public.tiff",
                    "public.heic",
                    "com.adobe.raw-image",
                ],
            }
        ],
    },
)
