"""editor_renderer.py – _BirdStampRendererMixin

Preview caching, render-settings building, image processing pipeline,
and the render_preview entry point.
Mixed into BirdStampEditorWindow via multiple inheritance.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from PIL import Image
from PyQt6.QtGui import QPixmap

from birdstamp.decoders.image_decoder import decode_image
from birdstamp.gui import editor_core, editor_options, editor_template, editor_utils, template_context as _template_context
from birdstamp.gui.editor_preview_canvas import EditorPreviewOverlayOptions, EditorPreviewOverlayState

_pil_to_qpixmap                     = editor_utils.pil_to_qpixmap
_path_key                           = editor_utils.path_key
_safe_color                         = editor_utils.safe_color
_build_metadata_context             = editor_utils.build_metadata_context
_default_placeholder_path           = editor_utils._default_placeholder_path
_extract_focus_box                  = editor_core.extract_focus_box
_extract_focus_box_for_display      = editor_core.extract_focus_box_for_display
_resolve_focus_camera_type_from_metadata = editor_core.resolve_focus_camera_type_from_metadata
_transform_source_box_after_crop_padding = editor_core.transform_source_box_after_crop_padding
_normalize_center_mode              = editor_core.normalize_center_mode
_parse_bool_value                   = editor_core.parse_bool_value
_parse_ratio_value                  = editor_core.parse_ratio_value
_parse_padding_value                = editor_core.parse_padding_value
_pad_image                          = editor_core.pad_image
_resize_fit                         = editor_core.resize_fit
_crop_image_by_normalized_box       = editor_core.crop_image_by_normalized_box
_crop_box_has_effect                = editor_core.crop_box_has_effect
_normalized_box_to_pixel_box        = editor_core.normalized_box_to_pixel_box
_normalize_template_payload         = editor_template.normalize_template_payload
_deep_copy_payload                  = editor_template.deep_copy_payload
_default_template_payload           = editor_template.default_template_payload
_load_template_payload              = editor_template.load_template_payload
render_template_overlay             = editor_template.render_template_overlay
_render_template_overlay_in_crop_region = editor_template.render_template_overlay_in_crop_region
_DEFAULT_TEMPLATE_CENTER_MODE       = editor_template.DEFAULT_TEMPLATE_CENTER_MODE
_DEFAULT_TEMPLATE_MAX_LONG_EDGE     = editor_template.DEFAULT_TEMPLATE_MAX_LONG_EDGE
_DEFAULT_CROP_PADDING_PX            = editor_core.DEFAULT_CROP_PADDING_PX
OUTPUT_FORMAT_OPTIONS               = editor_options.OUTPUT_FORMAT_OPTIONS


class _BirdStampRendererMixin:
    """Mixin: preview-cache, render-settings, image processing pipeline, render_preview."""

    @staticmethod
    def _padding_widget_value(widget: Any) -> int:
        """兼容 QSpinBox / 可编辑 QComboBox 读取边界填充值。"""
        if widget is None:
            return _DEFAULT_CROP_PADDING_PX
        value_attr = getattr(widget, "value", None)
        if callable(value_attr):
            try:
                return int(value_attr())
            except Exception:
                pass
        current_text_attr = getattr(widget, "currentText", None)
        if callable(current_text_attr):
            return _parse_padding_value(current_text_attr(), _DEFAULT_CROP_PADDING_PX)
        text_attr = getattr(widget, "text", None)
        if callable(text_attr):
            return _parse_padding_value(text_attr(), _DEFAULT_CROP_PADDING_PX)
        return _DEFAULT_CROP_PADDING_PX

    def _build_preview_overlay_options(self) -> EditorPreviewOverlayOptions:
        """Build editor preview overlay options from the current toolbar UI state."""
        return EditorPreviewOverlayOptions(
            show_focus_box=bool(self.show_focus_box_check.isChecked()),
            show_bird_box=bool(self.show_bird_box_check.isChecked()),
            show_crop_effect=bool(self.show_crop_effect_check.isChecked()),
            crop_effect_alpha=int(self.crop_effect_alpha_slider.value()),
        )

    def _apply_preview_overlay_options_from_ui(self) -> None:
        """Apply preview overlay options to the preview canvas/composite."""
        self.preview_label.apply_overlay_options(self._build_preview_overlay_options())

    def _source_signature(self, path: Path) -> str:
        try:
            stat = path.stat()
            return f"{_path_key(path)}:{stat.st_size}:{stat.st_mtime_ns}"
        except Exception:
            return _path_key(path)

    def _preview_cache_file_for_source(self, path: Path, signature: str) -> Path:
        digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]
        preview_dir = path.parent / ".preview"
        return preview_dir / f"{path.stem}.{digest}.png"

    def _invalidate_original_mode_cache(self) -> None:
        self._original_mode_signature = None
        self._original_mode_pixmap = None

    def _original_mode_cache_key(self) -> str:
        """原尺寸图缓存键：含源图与裁切/填充设置，任一变化即失效。"""
        if self.current_path is None:
            return ""
        base = self._source_signature(self.current_path)
        template_name = str(self.template_combo.currentText() or "default").strip() or "default"
        draw_overlay = f"{self.draw_banner_check.isChecked()}|{self.draw_text_check.isChecked()}"
        r = self._selected_ratio()
        cm = self._selected_center_mode()
        pt = self._padding_widget_value(self.crop_padding_top)
        pb = self._padding_widget_value(self.crop_padding_bottom)
        pl = self._padding_widget_value(self.crop_padding_left)
        pr = self._padding_widget_value(self.crop_padding_right)
        fill = getattr(self, "crop_padding_fill_combo", None)
        fill_val = fill.currentData() if fill is not None and fill.currentData() else "#FFFFFF"
        return f"{base}|{template_name}|{draw_overlay}|{r}|{cm}|{pt}_{pb}_{pl}_{pr}|{fill_val}"

    def _preview_render_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """预览固定按原图尺寸渲染，避免 Banner 在预览阶段被二次缩放。"""
        preview_settings = self._clone_render_settings(settings)
        preview_settings["max_long_edge"] = 0
        return preview_settings

    def _load_original_mode_pixmap(self) -> QPixmap | None:
        if self.current_path is None or self.current_source_image is None:
            return None

        signature = self._original_mode_cache_key()
        if not signature:
            return None
        if (
            self._original_mode_signature == signature
            and self._original_mode_pixmap is not None
            and not self._original_mode_pixmap.isNull()
        ):
            return self._original_mode_pixmap

        settings = self._render_settings_for_path(self.current_path, prefer_current_ui=True)
        original_settings = self._preview_render_settings(settings)
        try:
            # 原尺寸模式显示未裁切预览源，仅保持原始分辨率。
            raw_metadata = dict(self.current_raw_metadata)
            crop_box, _outer_pad = self._compute_crop_plan_for_image(
                path=self.current_path,
                image=self.current_source_image,
                raw_metadata=raw_metadata,
                settings=original_settings,
            )
            img = self._build_processed_image(
                self.current_source_image.copy(),
                raw_metadata,
                settings=original_settings,
                source_path=self.current_path,
                apply_ratio_crop=False,
            )
            img = self._render_overlay_for_preview_frame(
                preview_base=img,
                raw_metadata=raw_metadata,
                metadata_context=dict(self.current_metadata_context),
                photo_info=self.current_photo_info,
                settings=original_settings,
                crop_box=crop_box,
            )
            direct_pixmap = _pil_to_qpixmap(img)
            if not direct_pixmap.isNull():
                self._original_mode_signature = signature
                self._original_mode_pixmap = direct_pixmap
                return direct_pixmap
        except Exception:
            pass

        # 处理失败时退回原图，避免界面无预览。
        try:
            direct_pixmap = _pil_to_qpixmap(self.current_source_image)
            if not direct_pixmap.isNull():
                self._original_mode_signature = signature
                self._original_mode_pixmap = direct_pixmap
                return direct_pixmap
        except Exception:
            pass
        return None

    def _current_focus_box_after_processing(self, *, apply_ratio_crop: bool = True) -> tuple[float, float, float, float] | None:
        if self.current_path is None or self.current_source_image is None:
            return None

        source_width, source_height = self.current_source_image.size
        focus_camera_type = _resolve_focus_camera_type_from_metadata(self.current_raw_metadata)
        focus_box_source = _extract_focus_box_for_display(
            self.current_raw_metadata,
            source_width,
            source_height,
            camera_type=focus_camera_type,
        )
        if focus_box_source is None:
            return None

        settings = self._render_settings_for_path(self.current_path, prefer_current_ui=True)
        crop_box, outer_pad = self._compute_crop_plan_for_image(
            path=self.current_path,
            image=self.current_source_image,
            raw_metadata=self.current_raw_metadata,
            settings=settings,
        )
        pad_top, pad_bottom, pad_left, pad_right = outer_pad
        focus_box = _transform_source_box_after_crop_padding(
            focus_box_source,
            crop_box=None,
            source_width=source_width,
            source_height=source_height,
            pt=pad_top,
            pb=pad_bottom,
            pl=pad_left,
            pr=pad_right,
        )
        if not apply_ratio_crop or focus_box is None or crop_box is None:
            return focus_box
        return _transform_source_box_after_crop_padding(
            focus_box,
            crop_box=crop_box,
            source_width=source_width + pad_left + pad_right,
            source_height=source_height + pad_top + pad_bottom,
            pt=0,
            pb=0,
            pl=0,
            pr=0,
        )

    def _current_bird_box(self) -> tuple[float, float, float, float] | None:
        if self.current_path is None or self.current_source_image is None:
            return None
        return self._bird_box_for_path(self.current_path, source_image=self.current_source_image)

    def _show_placeholder_preview(self) -> None:
        """激活 images/default.jpg 作为当前图像，走与真实照片完全相同的渲染流程。
        不将其加入照片列表，self.placeholder_path 标记当前处于占位状态。
        若 default.jpg 不存在则回退到裸 PIL 占位图。
        """
        src = _default_placeholder_path()
        if src.exists():
            try:
                image = decode_image(src, decoder="auto")
                self.placeholder_path: "Path | None" = src
                self.current_path = src
                self.current_source_image = image
                self._invalidate_original_mode_cache()
                self.current_raw_metadata = self._load_raw_metadata(src)
                self.current_photo_info = _template_context.ensure_photo_info(src, raw_metadata=self.current_raw_metadata)
                self.current_metadata_context = _build_metadata_context(self.current_photo_info, self.current_raw_metadata)
                # 走正常渲染流程（current_path 已设置，不会再次调用本函数）
                self.render_preview()
                return
            except Exception:
                pass
        # 回退：default.jpg 不可用，显示裸 PIL 占位图
        self.placeholder_path = None
        self.current_path = None
        self.current_photo_info = None
        self.current_source_image = None
        self.current_raw_metadata = {}
        self.current_metadata_context = {}
        self.preview_pixmap = _pil_to_qpixmap(self.placeholder)
        self.preview_overlay_state = EditorPreviewOverlayState()
        self._invalidate_original_mode_cache()
        self._refresh_preview_label(reset_view=True)

    def _refresh_preview_label(
        self,
        *,
        reset_view: bool = False,
        preserve_view: bool = False,
        force_fit: bool = False,
    ) -> None:
        self._apply_preview_overlay_options_from_ui()

        display_pixmap: QPixmap | None = self.preview_pixmap
        source_mode = "原图"

        self.preview_label.apply_overlay_state(
            self.preview_overlay_state if self.preview_pixmap else EditorPreviewOverlayState()
        )
        if self.current_source_image is not None:
            self.preview_label.set_original_size(self.current_source_image.size[0], self.current_source_image.size[1])
        else:
            self.preview_label.set_original_size(None, None)
        self.preview_label.set_source_mode(source_mode)
        self.preview_label.set_source_pixmap(
            display_pixmap,
            reset_view=reset_view,
            preserve_view=preserve_view,
            preserve_scale=preserve_view,
        )

    def _selected_center_mode(self) -> str:
        return _normalize_center_mode(self.center_mode_combo.currentData())

    def _should_draw_template_overlay(self, settings: dict[str, Any]) -> bool:
        draw_banner = _parse_bool_value(settings.get("draw_banner"), True)
        draw_text = _parse_bool_value(settings.get("draw_text"), True)
        return draw_banner or draw_text

    def _build_current_render_settings(self) -> dict[str, Any]:
        template_name = str(self.template_combo.currentText() or "default").strip() or "default"
        template_payload = _normalize_template_payload(self.current_template_payload, fallback_name=template_name)
        return {
            "template_name": template_name,
            "template_payload": _deep_copy_payload(template_payload),
            "draw_banner": bool(self.draw_banner_check.isChecked()),
            "draw_text": bool(self.draw_text_check.isChecked()),
            "ratio": self._selected_ratio(),
            "center_mode": self._selected_center_mode(),
            "max_long_edge": self._selected_max_long_edge(),
            "crop_padding_top": self._padding_widget_value(self.crop_padding_top),
            "crop_padding_bottom": self._padding_widget_value(self.crop_padding_bottom),
            "crop_padding_left": self._padding_widget_value(self.crop_padding_left),
            "crop_padding_right": self._padding_widget_value(self.crop_padding_right),
            "crop_padding_fill": _safe_color(
                str(self.crop_padding_fill_combo.currentData() or "#FFFFFF"),
                "#FFFFFF",
            ),
        }

    def _clone_render_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        template_name = str(settings.get("template_name") or "default").strip() or "default"
        template_payload_raw = settings.get("template_payload")
        if isinstance(template_payload_raw, dict):
            template_payload = _normalize_template_payload(template_payload_raw, fallback_name=template_name)
        else:
            template_payload = _default_template_payload(name=template_name)

        ratio: float | None
        ratio_raw = settings.get("ratio")
        if ratio_raw is None:
            ratio = None
        else:
            try:
                ratio = float(ratio_raw)
            except Exception:
                ratio = None
            if ratio is not None and ratio <= 0:
                ratio = None

        max_long_edge = 0
        try:
            max_long_edge = int(settings.get("max_long_edge", 0))
        except Exception:
            max_long_edge = 0
        max_long_edge = max(0, max_long_edge)

        def _pad_px(key: str) -> int:
            return _parse_padding_value(settings.get(key, _DEFAULT_CROP_PADDING_PX), _DEFAULT_CROP_PADDING_PX)

        fill = _safe_color(str(settings.get("crop_padding_fill", "#FFFFFF")), "#FFFFFF")

        return {
            "template_name": template_name,
            "template_payload": _deep_copy_payload(template_payload),
            "draw_banner": _parse_bool_value(settings.get("draw_banner"), True),
            "draw_text": _parse_bool_value(settings.get("draw_text"), True),
            "ratio": ratio,
            "center_mode": _normalize_center_mode(settings.get("center_mode")),
            "max_long_edge": max_long_edge,
            "crop_padding_top": _pad_px("crop_padding_top"),
            "crop_padding_bottom": _pad_px("crop_padding_bottom"),
            "crop_padding_left": _pad_px("crop_padding_left"),
            "crop_padding_right": _pad_px("crop_padding_right"),
            "crop_padding_fill": fill,
        }

    def _normalize_render_settings(self, raw: Any, fallback: dict[str, Any]) -> dict[str, Any]:
        settings = self._clone_render_settings(fallback)
        if not isinstance(raw, dict):
            return settings

        template_name = str(raw.get("template_name") or settings["template_name"]).strip() or settings["template_name"]
        settings["template_name"] = template_name
        payload_raw = raw.get("template_payload")
        if isinstance(payload_raw, dict):
            settings["template_payload"] = _normalize_template_payload(payload_raw, fallback_name=template_name)
        if "draw_banner" in raw:
            settings["draw_banner"] = _parse_bool_value(raw.get("draw_banner"), settings["draw_banner"])
        if "draw_text" in raw:
            settings["draw_text"] = _parse_bool_value(raw.get("draw_text"), settings["draw_text"])
        if "draw_template_overlay" in raw and "draw_banner" not in raw and "draw_text" not in raw:
            legacy = _parse_bool_value(raw.get("draw_template_overlay"), True)
            settings["draw_banner"] = legacy
            settings["draw_text"] = legacy

        ratio_raw = raw.get("ratio")
        if ratio_raw is None or ratio_raw == "":
            settings["ratio"] = None
        else:
            try:
                ratio = float(ratio_raw)
            except Exception:
                ratio = settings["ratio"]
            else:
                settings["ratio"] = ratio if ratio > 0 else None

        if "center_mode" in raw:
            settings["center_mode"] = _normalize_center_mode(raw.get("center_mode"))

        if "max_long_edge" in raw:
            try:
                parsed_max_edge = int(raw.get("max_long_edge"))
            except Exception:
                parsed_max_edge = int(settings["max_long_edge"])
            settings["max_long_edge"] = max(0, parsed_max_edge)

        def _parse_pad(key: str) -> int:
            return _parse_padding_value(raw.get(key, settings[key]), settings[key])

        for key in ("crop_padding_top", "crop_padding_bottom", "crop_padding_left", "crop_padding_right"):
            if key in raw:
                settings[key] = _parse_pad(key)
        if "crop_padding_fill" in raw:
            settings["crop_padding_fill"] = _safe_color(str(raw.get("crop_padding_fill", "#FFFFFF")), "#FFFFFF")
        return settings

    def _render_settings_for_path(self, path: Path | None, *, prefer_current_ui: bool) -> dict[str, Any]:
        fallback = self._build_current_render_settings()
        if path is None:
            return fallback
        key = _path_key(path)
        if prefer_current_ui and self.current_path is not None and key == _path_key(self.current_path):
            return fallback
        return self._normalize_render_settings(self.photo_render_overrides.get(key), fallback=fallback)

    def _ratio_combo_index_for_value(self, ratio: float | None) -> int:
        for idx in range(self.ratio_combo.count()):
            data = self.ratio_combo.itemData(idx)
            if data is None and ratio is None:
                return idx
            if data is None or ratio is None:
                continue
            try:
                if abs(float(data) - float(ratio)) <= 0.0001:
                    return idx
            except Exception:
                continue
        return -1

    def _ensure_max_edge_option(self, max_edge: int) -> int:
        edge = max(0, int(max_edge))
        idx = self.max_edge_combo.findData(edge)
        if idx >= 0:
            return idx
        label = "不限制" if edge == 0 else str(edge)
        self.max_edge_combo.addItem(label, edge)
        return self.max_edge_combo.findData(edge)

    def _apply_render_settings_to_ui(self, settings: dict[str, Any]) -> None:
        normalized = self._clone_render_settings(settings)
        template_name = str(normalized["template_name"])

        widgets_to_block = [
            self.template_combo, self.draw_banner_check, self.draw_text_check,
            self.ratio_combo, self.center_mode_combo,
            self.max_edge_combo,
        ]
        for w in widgets_to_block:
            w.blockSignals(True)
        try:
            template_idx = self.template_combo.findText(template_name)
            if template_idx >= 0:
                self.template_combo.setCurrentIndex(template_idx)
            self.draw_banner_check.setChecked(bool(normalized.get("draw_banner", True)))
            self.draw_text_check.setChecked(bool(normalized.get("draw_text", True)))

            ratio_idx = self._ratio_combo_index_for_value(normalized["ratio"])
            if ratio_idx >= 0:
                self.ratio_combo.setCurrentIndex(ratio_idx)

            center_idx = self.center_mode_combo.findData(normalized["center_mode"])
            if center_idx >= 0:
                self.center_mode_combo.setCurrentIndex(center_idx)

            max_edge_idx = self._ensure_max_edge_option(int(normalized["max_long_edge"]))
            if max_edge_idx >= 0:
                self.max_edge_combo.setCurrentIndex(max_edge_idx)

            self._crop_padding_widget.set_values(
                top=_parse_padding_value(normalized.get("crop_padding_top", _DEFAULT_CROP_PADDING_PX), _DEFAULT_CROP_PADDING_PX),
                bottom=_parse_padding_value(normalized.get("crop_padding_bottom", _DEFAULT_CROP_PADDING_PX), _DEFAULT_CROP_PADDING_PX),
                left=_parse_padding_value(normalized.get("crop_padding_left", _DEFAULT_CROP_PADDING_PX), _DEFAULT_CROP_PADDING_PX),
                right=_parse_padding_value(normalized.get("crop_padding_right", _DEFAULT_CROP_PADDING_PX), _DEFAULT_CROP_PADDING_PX),
                fill=_safe_color(str(normalized.get("crop_padding_fill", "#FFFFFF")), "#FFFFFF"),
            )
        finally:
            for w in reversed(widgets_to_block):
                w.blockSignals(False)

        self.current_template_payload = _normalize_template_payload(
            normalized["template_payload"],
            fallback_name=template_name,
        )

    def _compose_preview_with_crop_aligned_overlay(
        self,
        *,
        preview_base: Image.Image,
        rendered_crop: Image.Image,
        crop_box: tuple[float, float, float, float] | None,
    ) -> Image.Image:
        if not _crop_box_has_effect(crop_box):
            return rendered_crop

        crop_px = _normalized_box_to_pixel_box(crop_box, preview_base.width, preview_base.height)
        if crop_px is None:
            return preview_base
        left, top, right, bottom = crop_px
        target_w = max(1, right - left)
        target_h = max(1, bottom - top)

        patch = rendered_crop.convert("RGB")
        if patch.width != target_w or patch.height != target_h:
            patch = patch.resize((target_w, target_h), Image.Resampling.LANCZOS)

        merged = preview_base.copy()
        merged.paste(patch, (left, top))
        return merged

    def _resolve_template_payload_for_render(self, settings: dict[str, Any]) -> dict[str, Any]:
        template_name = str(settings.get("template_name") or "default").strip() or "default"
        payload_raw = settings.get("template_payload")
        if isinstance(payload_raw, dict):
            payload = _normalize_template_payload(payload_raw, fallback_name=template_name)
        else:
            payload = _default_template_payload(name=template_name)

        # 主预览和导出的模板内容始终跟随模板文件配置。
        template_path = self.template_paths.get(template_name)
        if template_path and template_path.is_file():
            try:
                payload = _load_template_payload(template_path)
            except Exception:
                pass
        return payload

    def _render_overlay_for_preview_frame(
        self,
        *,
        preview_base: Image.Image,
        raw_metadata: dict[str, Any],
        metadata_context: dict[str, str],
        photo_info: _template_context.PhotoInfo | None,
        settings: dict[str, Any],
        crop_box: tuple[float, float, float, float] | None,
    ) -> Image.Image:
        if not self._should_draw_template_overlay(settings):
            return preview_base

        template_payload = self._resolve_template_payload_for_render(settings)
        # 直接在当前预览帧的裁切区域绘制模板，避免先按输出尺寸渲染再缩放导致 Banner 预览偏差。
        return _render_template_overlay_in_crop_region(
            preview_base,
            raw_metadata=raw_metadata,
            metadata_context=metadata_context,
            photo_info=photo_info,
            template_payload=template_payload,
            crop_box=crop_box,
            draw_banner=_parse_bool_value(settings.get("draw_banner"), True),
            draw_text=_parse_bool_value(settings.get("draw_text"), True),
        )

    def _build_processed_image(
        self,
        image: Image.Image,
        raw_metadata: dict[str, Any],
        *,
        settings: dict[str, Any],
        source_path: Path | None,
        apply_ratio_crop: bool = True,
    ) -> Image.Image:
        crop_box, outer_pad = self._compute_crop_plan_for_image(
            path=source_path,
            image=image,
            raw_metadata=raw_metadata,
            settings=settings,
        )
        top, bottom, left, right = outer_pad
        if top or bottom or left or right:
            fill = str(settings.get("crop_padding_fill") or "#FFFFFF").strip() or "#FFFFFF"
            image = _pad_image(image, top=top, bottom=bottom, left=left, right=right, fill=fill)

        if apply_ratio_crop:
            image = _crop_image_by_normalized_box(image, crop_box)

        max_long_edge = max(0, int(settings.get("max_long_edge") or 0))
        image = _resize_fit(image, max_long_edge)
        return image

    def _render_for_path(self, path: Path, *, prefer_current_ui: bool) -> Image.Image:
        settings = self._render_settings_for_path(path, prefer_current_ui=prefer_current_ui)
        if self.current_path and path == self.current_path and self.current_source_image is not None:
            source_image = self.current_source_image.copy()
            raw_metadata = dict(self.current_raw_metadata)
        else:
            source_image = decode_image(path, decoder="auto")
            raw_metadata = self._load_raw_metadata(path)

        processed = self._build_processed_image(
            source_image,
            raw_metadata,
            settings=settings,
            source_path=path,
            apply_ratio_crop=True,
        )
        if not self._should_draw_template_overlay(settings):
            return processed

        template_payload = self._resolve_template_payload_for_render(settings)
        if self.current_path and path == self.current_path and self.current_source_image is not None:
            context = dict(self.current_metadata_context)
            photo_info = self.current_photo_info
        else:
            photo_info = _template_context.ensure_photo_info(path, raw_metadata=raw_metadata)
            context = _build_metadata_context(photo_info, raw_metadata)
        return render_template_overlay(
            processed,
            raw_metadata=raw_metadata,
            metadata_context=context,
            photo_info=photo_info,
            template_payload=template_payload,
            draw_banner=_parse_bool_value(settings.get("draw_banner"), True),
            draw_text=_parse_bool_value(settings.get("draw_text"), True),
        )

    def render_preview(self, *_args: Any) -> None:
        if not self.current_path:
            # default.jpg 不可用时的降级路径；正常情况由 _show_placeholder_preview 负责激活占位图
            self._set_status("请选择照片后再预览。")
            return

        crop_box: tuple[float, float, float, float] | None = None
        outer_pad: tuple[int, int, int, int] = (0, 0, 0, 0)
        try:
            if self.current_source_image is None:
                raise RuntimeError("缺少当前原图数据")
            settings = self._render_settings_for_path(self.current_path, prefer_current_ui=True)
            preview_settings = self._preview_render_settings(settings)
            source_image = self.current_source_image.copy()
            raw_metadata = dict(self.current_raw_metadata)
            crop_box, outer_pad = self._compute_crop_plan_for_image(
                path=self.current_path,
                image=self.current_source_image,
                raw_metadata=raw_metadata,
                settings=preview_settings,
            )
            # 预览保持完整画面，仅通过“显示裁切效果”遮罩提示最终裁切范围。
            processed = self._build_processed_image(
                source_image,
                raw_metadata,
                settings=preview_settings,
                source_path=self.current_path,
                apply_ratio_crop=False,
            )
            rendered = self._render_overlay_for_preview_frame(
                preview_base=processed,
                raw_metadata=raw_metadata,
                metadata_context=dict(self.current_metadata_context),
                photo_info=self.current_photo_info,
                settings=preview_settings,
                crop_box=crop_box,
            )
        except Exception as exc:
            self.preview_overlay_state = EditorPreviewOverlayState()
            self._show_error("预览失败", str(exc))
            self._set_status(f"预览失败: {exc}")
            return

        self.last_rendered = rendered
        pad_top, pad_bottom, pad_left, pad_right = outer_pad
        focus_camera_type = _resolve_focus_camera_type_from_metadata(raw_metadata)
        # 注意：预览图是经过 EXIF Orientation 纠正后的显示坐标，不能直接用当前图像尺寸调用
        # extract_focus_box()。这里必须走 extract_focus_box_for_display()，否则“显示对焦点”会再次错位。
        preview_focus_box = _transform_source_box_after_crop_padding(
            _extract_focus_box_for_display(
                raw_metadata,
                self.current_source_image.width,
                self.current_source_image.height,
                camera_type=focus_camera_type,
            ),
            crop_box=None,
            source_width=self.current_source_image.width,
            source_height=self.current_source_image.height,
            pt=pad_top,
            pb=pad_bottom,
            pl=pad_left,
            pr=pad_right,
        )
        preview_bird_box = _transform_source_box_after_crop_padding(
            self._bird_box_for_path(self.current_path, source_image=self.current_source_image),
            crop_box=None,
            source_width=self.current_source_image.width,
            source_height=self.current_source_image.height,
            pt=pad_top,
            pb=pad_bottom,
            pl=pad_left,
            pr=pad_right,
        )
        self.preview_overlay_state = EditorPreviewOverlayState(
            focus_box=preview_focus_box,
            bird_box=preview_bird_box,
            crop_effect_box=crop_box,
        )

        self.preview_pixmap = _pil_to_qpixmap(rendered)
        fit_reset = self._pending_preview_fit_reset
        self._pending_preview_fit_reset = False
        self._refresh_preview_label(reset_view=True, force_fit=fit_reset)
        if pad_top or pad_bottom or pad_left or pad_right:
            self._set_status(
                f"预览完成: {rendered.width}x{rendered.height} | 外填充 上{pad_top}px 下{pad_bottom}px 左{pad_left}px 右{pad_right}px"
            )
        else:
            self._set_status(f"预览完成: {rendered.width}x{rendered.height}")
