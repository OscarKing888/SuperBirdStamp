from pathlib import Path

from PIL import Image

from birdstamp.video_export import (
    _count_contiguous_rendered_frames,
    _partial_video_output_path,
    VideoExportOptions,
    build_ffmpeg_command,
    normalize_frame_size,
    resolve_target_frame_size,
    resolve_video_render_workers,
)


def test_resolve_target_frame_size_auto_rounds_to_even() -> None:
    options = VideoExportOptions(output_path=Path("out.mp4"), frame_size_mode="auto")
    assert resolve_target_frame_size(options, (1919, 1081)) == (1920, 1082)


def test_resolve_target_frame_size_custom_uses_requested_size() -> None:
    options = VideoExportOptions(
        output_path=Path("out.mp4"),
        frame_size_mode="custom",
        frame_width=1281,
        frame_height=719,
    )
    assert resolve_target_frame_size(options, (640, 480)) == (1282, 720)


def test_build_ffmpeg_command_h265_mp4_contains_expected_flags(tmp_path) -> None:
    options = VideoExportOptions(
        output_path=tmp_path / "clip.mp4",
        container="mp4",
        codec="h265",
        fps=29.97,
        preset="slow",
        crf=18,
    )
    command = build_ffmpeg_command(Path("/tmp/ffmpeg"), tmp_path / "frames", options)
    assert command[:4] == ["/tmp/ffmpeg", "-hide_banner", "-loglevel", "error"]
    assert "-framerate" in command
    assert "29.97" in command
    assert "libx265" in command
    assert "hvc1" in command
    assert "+faststart" in command
    assert str((tmp_path / "clip.mp4").resolve()) == command[-1]


def test_resolve_video_render_workers_honors_auto_and_manual_limits() -> None:
    assert resolve_video_render_workers(0, 0) == 1
    assert resolve_video_render_workers(3, 2) == 2
    assert resolve_video_render_workers(1, 5) == 1


def test_normalize_frame_size_letterboxes_to_target_canvas() -> None:
    image = Image.new("RGB", (400, 200), "#FF0000")
    normalized = normalize_frame_size(image, (320, 240), background_color="#000000")
    assert normalized.size == (320, 240)
    assert normalized.getpixel((0, 0)) == (0, 0, 0)
    assert normalized.getpixel((160, 120)) == (255, 0, 0)


def test_count_contiguous_rendered_frames_stops_at_gap(tmp_path) -> None:
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    for name in ("frame_000001.png", "frame_000002.png", "frame_000004.png"):
        (frames_dir / name).write_bytes(b"png")
    assert _count_contiguous_rendered_frames(frames_dir, 5) == 2


def test_partial_video_output_path_marks_frame_count() -> None:
    output_path = Path("/tmp/video.mp4")
    partial_path = _partial_video_output_path(output_path, 12)
    assert partial_path.name == "video__partial_000012.mp4"
