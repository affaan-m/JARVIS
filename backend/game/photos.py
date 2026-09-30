"""Photo handling for the game: blur every face, then store briefly in memory.

Shared photos are taken in an office where people who are not playing walk past,
so every face is blurred before a photo is stored — the app cannot tell a player
from a passer-by, so it treats them all the same. Photos live in memory only and
are wiped when the game is reset or game mode is switched off.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from io import BytesIO
from uuid import uuid4

from loguru import logger
from PIL import Image, ImageFilter

from identification.models import FaceDetectionRequest

MAX_PHOTOS = 300
KILLCAM_FRAMES = 5
BLUR_RADIUS_DIVISOR = 6  # radius scales with face size so small faces blur too
MAX_EDGE = 1280


async def blur_faces(image_data: bytes, detector) -> tuple[bytes, int]:
    """Blur every detected face. Returns the new JPEG and how many were blurred.

    If detection fails the whole image is blurred rather than shared unblurred —
    failing closed is the only safe direction here.
    """
    def _shrink(data: bytes) -> bytes:
        image = Image.open(BytesIO(data)).convert("RGB")
        if max(image.size) > MAX_EDGE:
            image.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        return buffer.getvalue()

    try:
        image_data = await asyncio.to_thread(_shrink, image_data)
    except Exception as exc:
        logger.error("Photo could not be decoded: {}", exc)
        raise ValueError("Deze afbeelding kon niet gelezen worden") from exc

    if detector is None:
        logger.warning("No face detector — blurring the whole photo to be safe")
        return await asyncio.to_thread(_blur_everything, image_data), 0

    result = await detector.detect_faces(FaceDetectionRequest(image_data=image_data))
    if not result.success:
        logger.warning("Face detection failed ({}) — blurring the whole photo", result.error)
        return await asyncio.to_thread(_blur_everything, image_data), 0

    boxes = [face.bbox for face in result.faces]
    blurred = await asyncio.to_thread(_blur_boxes, image_data, boxes)
    logger.info("Photo shared with {} face(s) blurred", len(boxes))
    return blurred, len(boxes)


def _blur_boxes(image_data: bytes, boxes) -> bytes:
    image = Image.open(BytesIO(image_data)).convert("RGB")
    width, height = image.size
    for box in boxes:
        # Pad the box so hair, chin and ears are covered too
        pad_x = box.width * width * 0.25
        pad_y = box.height * height * 0.25
        left = max(0, int(box.x * width - pad_x))
        top = max(0, int(box.y * height - pad_y))
        right = min(width, int((box.x + box.width) * width + pad_x))
        bottom = min(height, int((box.y + box.height) * height + pad_y))
        if right <= left or bottom <= top:
            continue
        region = image.crop((left, top, right, bottom))
        radius = max(8, (right - left) // BLUR_RADIUS_DIVISOR)
        image.paste(region.filter(ImageFilter.GaussianBlur(radius)), (left, top))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def _blur_everything(image_data: bytes) -> bytes:
    image = Image.open(BytesIO(image_data)).convert("RGB")
    radius = max(12, max(image.size) // 25)
    buffer = BytesIO()
    image.filter(ImageFilter.GaussianBlur(radius)).save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


class PhotoStore:
    """Bounded in-memory photo store plus the rolling killcam buffers."""

    def __init__(self, max_photos: int = MAX_PHOTOS) -> None:
        self._photos: OrderedDict[str, bytes] = OrderedDict()
        self._killcam: dict[str, deque[str]] = {}
        self._max_photos = max_photos

    def add(self, image_data: bytes) -> str:
        photo_id = f"ph_{uuid4().hex[:12]}"
        self._photos[photo_id] = image_data
        while len(self._photos) > self._max_photos:
            dropped, _ = self._photos.popitem(last=False)
            for buffer in self._killcam.values():
                if dropped in buffer:
                    buffer.remove(dropped)
        return photo_id

    def get(self, photo_id: str) -> bytes | None:
        return self._photos.get(photo_id)

    def push_killcam(self, player_id: str, photo_id: str) -> list[str]:
        """Keep only the last few frames per player, so nothing is stored long."""
        buffer = self._killcam.setdefault(player_id, deque(maxlen=KILLCAM_FRAMES))
        buffer.append(photo_id)
        return list(buffer)

    def take_killcam(self, player_id: str) -> list[str]:
        """Hand over a player's buffered frames and clear the buffer."""
        buffer = self._killcam.pop(player_id, None)
        return list(buffer) if buffer else []

    def clear(self) -> None:
        self._photos.clear()
        self._killcam.clear()
        logger.info("Photo store cleared")

    def __len__(self) -> int:
        return len(self._photos)
