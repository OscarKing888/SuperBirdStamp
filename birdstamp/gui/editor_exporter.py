"""editor_exporter.py – _BirdStampExporterMixin

export_current / export_all / _save_image.
Mixed into BirdStampEditorWindow via multiple inheritance.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from birdstamp.gui import editor_options

OUTPUT_FORMAT_OPTIONS = editor_options.OUTPUT_FORMAT_OPTIONS


class _BirdStampExporterMixin:
    """Mixin: export_current, export_all, _save_image."""

    def export_current(self) -> None:
        if not self.current_path or self._is_placeholder_active():
            self._set_status("没有可导出的照片。")
            return

        try:
            rendered = self._render_for_path(self.current_path, prefer_current_ui=True)
        except Exception as exc:
            self._show_error("导出失败", str(exc))
            return

        suffix = self._selected_output_suffix()
        default_name = f"{self.current_path.stem}__birdstamp.{suffix}"
        remembered_dir = getattr(self, "_image_export_last_output_dir", None)
        fallback_dir = remembered_dir if isinstance(remembered_dir, Path) and remembered_dir.is_dir() else self.current_path.parent
        default_path = fallback_dir / default_name
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出当前照片",
            str(default_path),
            "PNG (*.png);;JPG (*.jpg);;All Files (*.*)",
        )
        if not file_path:
            return

        target = Path(file_path)
        if target.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            target = target.with_suffix(f".{suffix}")

        try:
            self._save_image(rendered, target)
        except Exception as exc:
            self._show_error("导出失败", str(exc))
            return

        remembered_target_dir = target.parent.resolve(strict=False)
        self._image_export_last_output_dir = remembered_target_dir
        self._save_image_export_last_output_dir(remembered_target_dir)
        self._set_status(f"导出完成: {target}")

    def export_all(self) -> None:
        paths = self._list_photo_paths()
        if not paths:
            self._set_status("照片列表为空。")
            return

        remembered_dir = getattr(self, "_batch_export_last_output_dir", None)
        if not isinstance(remembered_dir, Path) or not remembered_dir.is_dir():
            remembered_dir = getattr(self, "_image_export_last_output_dir", None)
        if not isinstance(remembered_dir, Path) or not remembered_dir.is_dir():
            remembered_dir = paths[0].parent if paths else None
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "选择批量导出目录",
            str(remembered_dir) if isinstance(remembered_dir, Path) else "",
        )
        if not output_dir:
            return

        suffix = self._selected_output_suffix()
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        remembered_output_dir = out_dir.resolve(strict=False)
        self._batch_export_last_output_dir = remembered_output_dir
        self._save_batch_export_last_output_dir(remembered_output_dir)

        stem_counter: dict[str, int] = {}
        ok_count = 0
        failed: list[str] = []

        for path in paths:
            try:
                rendered = self._render_for_path(path, prefer_current_ui=False)
                stem = f"{path.stem}__birdstamp"
                count = stem_counter.get(stem, 0)
                stem_counter[stem] = count + 1
                if count > 0:
                    file_name = f"{stem}_{count + 1}.{suffix}"
                else:
                    file_name = f"{stem}.{suffix}"
                target = out_dir / file_name
                self._save_image(rendered, target)
                ok_count += 1
            except Exception as exc:
                failed.append(f"{path.name}: {exc}")

        if failed:
            preview = "\n".join(failed[:8])
            if len(failed) > 8:
                preview += f"\n... 另有 {len(failed) - 8} 项失败"
            QMessageBox.warning(self, "批量导出", f"成功 {ok_count}，失败 {len(failed)}\n\n{preview}")
        self._set_status(f"批量导出完成: 成功 {ok_count}，失败 {len(failed)}")

    def _save_image(self, image: Image.Image, path: Path) -> None:
        suffix = path.suffix.lower()
        if suffix == ".png":
            image.save(path, format="PNG", optimize=True)
            return

        if suffix not in {".jpg", ".jpeg"}:
            path = path.with_suffix(".jpg")
        image.save(path, format="JPEG", quality=92, optimize=True, progressive=True)


def launch_gui(startup_file: Path | None = None) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window_icon_path, _ = _app_icon_paths()
    if window_icon_path.exists():
        app.setWindowIcon(QIcon(str(window_icon_path)))
    window = BirdStampEditorWindow(startup_file=startup_file)
    window.showMaximized()
    app.exec()
