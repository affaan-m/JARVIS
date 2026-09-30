from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import MagicMock

import pytest

from capture.frame_handler import FrameHandler


def _handler(detect_delay: float = 0.0) -> tuple[FrameHandler, MagicMock]:
    detector = MagicMock()
    calls: list[str] = []

    def detect(frame_b64: str) -> dict:
        calls.append(threading.current_thread().name)
        if detect_delay:
            time.sleep(detect_delay)
        return {"detections": [{"bbox": [0, 0, 10, 10], "confidence": 0.9, "track_id": 1}]}

    detector.detect_from_base64.side_effect = detect
    detector.crop_persons.return_value = []
    handler = FrameHandler()
    handler.detector = detector
    detector.thread_names = calls
    return handler, detector


@pytest.mark.asyncio
async def test_detection_runs_off_the_event_loop() -> None:
    handler, detector = _handler()
    await handler.process_frame("frame", timestamp=1)
    assert detector.thread_names == ["MainThread"] or "asyncio" in detector.thread_names[0]


@pytest.mark.asyncio
async def test_event_loop_stays_responsive_during_detection() -> None:
    handler, _ = _handler(detect_delay=0.3)

    ticks = 0

    async def heartbeat() -> None:
        nonlocal ticks
        for _ in range(20):
            await asyncio.sleep(0.01)
            ticks += 1

    beat = asyncio.create_task(heartbeat())
    await handler.process_frame("frame", timestamp=1)
    await beat

    # A blocking detection would freeze the loop and leave ticks at ~0
    assert ticks >= 10


@pytest.mark.asyncio
async def test_polling_frames_are_dropped_while_a_detection_runs() -> None:
    handler, detector = _handler(detect_delay=0.2)

    results = await asyncio.gather(*(handler.process_frame("f", timestamp=i) for i in range(5)))

    # Only the first frame is detected; the rest return the last known result
    # instead of queueing behind it (here still empty, nothing detected yet).
    assert detector.detect_from_base64.call_count == 1
    assert results[0]["detections"] == [{"bbox": [0, 0, 10, 10], "confidence": 0.9, "track_id": 1}]
    assert all(r["detections"] == [] for r in results[1:])

    # A later frame reuses the detections from the finished run
    later = await handler.process_frame("f", timestamp=99)
    assert later["detections"] == results[0]["detections"]


@pytest.mark.asyncio
async def test_target_frames_are_never_dropped() -> None:
    handler, detector = _handler(detect_delay=0.1)
    handler._face_detector = None  # identification not configured; detection still runs

    await asyncio.gather(
        handler.process_frame("f", timestamp=1),
        handler.process_frame("f", timestamp=2, target=True),
    )

    assert detector.detect_from_base64.call_count == 2
