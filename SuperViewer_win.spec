# -*- mode: python ; coding: utf-8 -*-
# Windows 打包用：SuperBirdStamp（根据 requirements.txt 与 birdstamp/app_common 结构）

from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


# spec 在项目根时 SPECPATH 即为项目根
project_root = Path(SPECPATH).resolve()
entry_script = project_root / "main.py"
runtime_hook = project_root / "scripts_dev" / "pyi_rthook_cwd.py"
icon_path = project_root / "icons" / "app_icon.ico"


def collect_tree(src_relative: str, dest_relative: str | None = None) -> list[tuple[str, str]]:
    src_path = project_root / src_relative
    if not src_path.exists():
        return []

    dest_root = Path(dest_relative or src_relative)
    if src_path.is_file():
        return [(str(src_path), str(dest_root.parent).replace("\\", "/"))]

    items: list[tuple[str, str]] = []
    for child in src_path.rglob("*"):
        if not child.is_file():
            continue
        relative_parent = child.parent.relative_to(src_path)
        target_dir = dest_root / relative_parent
        items.append((str(child), str(target_dir).replace("\\", "/")))
    return items


datas: list[tuple[str, str]] = []
datas.extend(collect_tree("config"))
datas.extend(collect_tree("images"))
datas.extend(collect_tree("models"))
datas.extend(collect_tree("icons"))
datas.extend(collect_data_files("birdstamp"))
datas.extend(collect_data_files("app_common"))

hiddenimports = []
hiddenimports.extend(collect_submodules("birdstamp"))
hiddenimports.extend(collect_submodules("app_common"))


a = Analysis(
    [str(entry_script)],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(runtime_hook)],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SuperBirdStamp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=str(icon_path) if icon_path.exists() else None,
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
