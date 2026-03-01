# RESEARCH: ultralytics/ultralytics (35k stars), YOLO11 released Jan 2026
# DECISION: Using YOLO11n (nano) for speed — ~5ms/frame on M-series Mac
# ALT: mediapipe for face-only detection (used later in pipeline)
from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

import cv2
import numpy as np
from loguru import logger
from PIL import Image
from ultralytics import YOLO


class HumanDetector:
    """Detect and track humans in frames using YOLO11n."""

    def __init__(self, model_path: str = "yolo11n.pt", confidence: float = 0.5):
        self.model = YOLO(model_path)
        self.confidence = confidence
        logger.info(f"HumanDetector initialized with model={model_path}, conf={confidence}")

    def detect_from_base64(self, frame_b64: str) -> dict[str, Any]:
        """Decode base64 JPEG frame, run YOLO person detection, return results."""
        img_bytes = base64.b64decode(frame_b64)
        img = Image.open(BytesIO(img_bytes))
        frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        # Run YOLO tracking (class 0 = person in COCO)
        results = self.model.track(
            source=frame,
            classes=[0],
            conf=self.confidence,
            persist=True,
            verbose=False,
        )

        detections = []
        if results and results[0].boxes is not None:
            boxes = results[0].boxes
            for i in range(len(boxes)):
                bbox = boxes.xyxy[i].tolist()
                conf = float(boxes.conf[i])
                track_id = int(boxes.id[i]) if boxes.id is not None else None
                detections.append({
                    "bbox": bbox,
                    "confidence": conf,
                    "track_id": track_id,
                })

        logger.info(f"Detected {len(detections)} person(s) in frame")
        return {
            "detections": detections,
            "frame_shape": list(frame.shape[:2]),
        }

    def crop_persons(self, frame_b64: str, detections: list[dict]) -> list[str]:
        """Crop detected person regions, return as base64 JPEGs for face pipeline."""
        img_bytes = base64.b64decode(frame_b64)
        img = Image.open(BytesIO(img_bytes))
        frame = np.array(img)

        h, w = frame.shape[:2]
        crops = []
        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
            # Add 30% padding around the bbox for better face detection
            bw, bh = x2 - x1, y2 - y1
            pad_x, pad_y = int(bw * 0.3), int(bh * 0.3)
            x1 = max(0, x1 - pad_x)
            y1 = max(0, y1 - pad_y)
            x2 = min(w, x2 + pad_x)
            y2 = min(h, y2 + pad_y)
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            crop_pil = Image.fromarray(crop)
            buffer = BytesIO()
            crop_pil.save(buffer, format="JPEG", quality=85)
            crops.append(base64.b64encode(buffer.getvalue()).decode())

        return crops
