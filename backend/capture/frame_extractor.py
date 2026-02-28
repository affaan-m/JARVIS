from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path

from loguru import logger
from PIL import Image

# Image MIME types that can be handled directly (no frame extraction needed)
IMAGE_TYPES = frozenset({
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/tiff",
})

# Video MIME types that require ffmpeg frame extraction
VIDEO_TYPES = frozenset({
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/webm",
    "video/x-matroska",
})


def extract_frames(
    data: bytes,
    content_type: str,
    *,
    max_frames: int = 5,
    fps: float = 1.0,
) -> list[bytes]:
    """Extract frames from uploaded media.

    For images: returns the image bytes directly (single-element list).
    For videos: uses ffmpeg to extract frames at the given fps.

    Args:
        data: Raw file bytes.
        content_type: MIME type of the uploaded file.
        max_frames: Maximum number of frames to extract from video.
        fps: Frames per second to extract from video.

    Returns:
        List of JPEG-encoded frame bytes.
    """
    if content_type in IMAGE_TYPES:
        return _handle_image(data)

    if content_type in VIDEO_TYPES:
        return _handle_video(data, max_frames=max_frames, fps=fps)

    logger.warning("Unsupported content type: {}, treating as image", content_type)
    return _handle_image(data)


def _handle_image(data: bytes) -> list[bytes]:
    """Validate and normalize an image to JPEG bytes."""
    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return [buf.getvalue()]
    except Exception:
        logger.exception("Failed to decode image, returning raw bytes")
        return [data]


def _handle_video(
    data: bytes,
    *,
    max_frames: int = 5,
    fps: float = 1.0,
) -> list[bytes]:
    """Extract frames from video using ffmpeg."""
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = Path(tmpdir) / "input.mp4"
        video_path.write_bytes(data)

        output_pattern = Path(tmpdir) / "frame_%04d.jpg"

        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", f"fps={fps}",
            "-frames:v", str(max_frames),
            "-q:v", "2",
            str(output_pattern),
            "-y",
            "-loglevel", "error",
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        except FileNotFoundError:
            logger.error("ffmpeg not found — cannot extract video frames")
            return []
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg timed out extracting frames")
            return []
        except subprocess.CalledProcessError as exc:
            logger.error("ffmpeg failed: {}", exc.stderr.decode(errors="replace"))
            return []

        frame_files = sorted(Path(tmpdir).glob("frame_*.jpg"))
        frames = [f.read_bytes() for f in frame_files[:max_frames]]
        logger.info("Extracted {} frames from video", len(frames))
        return frames
