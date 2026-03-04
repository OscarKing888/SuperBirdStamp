# -*- mode: python ; coding: utf-8 -*-
# BirdStamp Windows PyInstaller spec
# Run from project root: pyinstaller BirdStamp_win.spec
#
# Prerequisites:
#   pip install pyinstaller pyinstaller-hooks-contrib
#
# Output: dist\SuperBirdStamp\  (onedir bundle)
#         dist\SuperBirdStamp\SuperBirdStamp.exe

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
    # Built-in YAML templates
    ("birdstamp/templates", "birdstamp/templates"),
    # YOLO bird-detection model
    ("models", "models"),
    # Placeholder preview image (includes default.jpg)
    ("icons", "icons"),
    # Config and JSON templates (birdstamp.cfg, config/templates/*.json)
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
        # Windows-specific: ensure win32 timezone support for datetime
        "win32timezone",
    ]
    + ultralytics_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["scripts_dev/pyi_rthook_cwd.py"],
    excludes=[
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
    # UPX MUST remain False for Torch/CUDA apps on Windows.
    # UPX corrupts CUDA DLLs and causes runtime failures in packaged builds.
    upx=False,
    console=False,  # Windowed app; set True temporarily for debugging crashes
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icons/app_icon.ico",
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
