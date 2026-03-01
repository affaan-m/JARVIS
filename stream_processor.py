"""
WebSocket stream processor for real-time person detection.
Receives JPEG frames via WS, runs YOLO11n (ONNX) tracking, returns annotated
JPEG + broadcasts an MJPEG stream.

Endpoints:
  GET  /           — Redirect to /viewer
  GET  /viewer       — Operator page (WebRTC relay from VisionClaw glasses)
  GET  /watch        — Secondary site (MJPEG viewer)
  GET  /stream       — Raw MJPEG multipart stream
  WS   /ws/process   — Send JPEG -> receive annotated JPEG
  WS   /ws/detect    — (legacy) Send JPEG -> receive JSON detections
  GET  /api/health   — Health check
"""

import asyncio
import os
import struct
import time
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# CPU threading optimizations — set before any model imports
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
yolo_model = None

BASE_DIR = Path(__file__).parent
ONNX_WEIGHTS = BASE_DIR / "yolo11n.onnx"
PT_WEIGHTS = BASE_DIR / "yolo11n.pt"
STATIC_DIR = BASE_DIR / "static"

INPUT_SIZE = 320  # ONNX exported at 320px — 4x fewer pixels than 640
JPEG_QUALITY = 60  # Halves bandwidth vs 95, still looks fine

# MJPEG broadcast: latest annotated frame shared with all /stream viewers
mjpeg_frame: bytes = b""
mjpeg_frame_id: int = 0  # monotonic counter to detect new frames


# ---------------------------------------------------------------------------
# Drawing (ported from human_detection.py)
# ---------------------------------------------------------------------------
def draw_box(frame, x1: int, y1: int, x2: int, y2: int, label: str, color: tuple):
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 6, y1), color, -1)
    cv2.putText(frame, label, (x1 + 3, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)


# ---------------------------------------------------------------------------
# Core: decode -> YOLO .track() -> annotate -> encode JPEG
# ---------------------------------------------------------------------------
def process_and_annotate(jpeg_bytes: bytes) -> tuple[bytes, dict]:
    """Decode JPEG, run YOLO tracking, draw boxes, re-encode annotated JPEG.

    Returns (annotated_jpeg_bytes, metadata_dict).
    """
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return jpeg_bytes, {"detections": 0, "process_time_ms": 0}

    # YOLO tracking — class 0 = person, persist reuses IDs across frames
    results = yolo_model.track(
        source=frame,
        classes=[0],
        conf=0.5,
        imgsz=INPUT_SIZE,
        persist=True,
        verbose=False,
    )

    boxes = results[0].boxes
    person_count = len(boxes)

    for box in boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        conf = float(box.conf[0])
        track_id = int(box.id[0]) if box.id is not None else None

        label = "Person"
        if track_id is not None:
            label = f"Person #{track_id}"
        label += f" {conf:.0%}"

        draw_box(frame, x1, y1, x2, y2, label, (0, 255, 0))

    # HUD overlay
    cv2.putText(
        frame, f"People: {person_count}",
        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2,
    )

    # Encode annotated frame as JPEG
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    annotated_jpeg = buf.tobytes()

    meta = {"detections": person_count}
    return annotated_jpeg, meta


# ---------------------------------------------------------------------------
# Lifespan: load model once
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global yolo_model
    print("[StreamProcessor] Loading YOLO model...")
    t0 = time.time()

    from ultralytics import YOLO

    # Prefer ONNX (faster on CPU), fall back to .pt
    if ONNX_WEIGHTS.exists():
        print(f"[StreamProcessor] Using ONNX weights: {ONNX_WEIGHTS}")
        yolo_model = YOLO(str(ONNX_WEIGHTS), task="detect")
    elif PT_WEIGHTS.exists():
        print(f"[StreamProcessor] ONNX not found, using PyTorch: {PT_WEIGHTS}")
        yolo_model = YOLO(str(PT_WEIGHTS))
    else:
        raise FileNotFoundError("No YOLO weights found (yolo11n.onnx or yolo11n.pt)")

    # Warm up
    dummy = np.zeros((INPUT_SIZE, INPUT_SIZE, 3), dtype=np.uint8)
    yolo_model.track(dummy, classes=[0], conf=0.5, persist=True, verbose=False)

    print(f"[StreamProcessor] Model loaded in {time.time() - t0:.1f}s")
    yield
    print("[StreamProcessor] Shutdown complete")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (viewer.html, watch.html)
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------
@app.get("/")
async def root():
    return RedirectResponse(url="/viewer")


# ---------------------------------------------------------------------------
# HTML page endpoints
# ---------------------------------------------------------------------------
@app.get("/viewer", response_class=HTMLResponse)
async def viewer_page():
    html_path = STATIC_DIR / "viewer.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text())
    return HTMLResponse("<h1>viewer.html not found</h1>", status_code=404)


@app.get("/watch", response_class=HTMLResponse)
async def watch_page():
    html_path = STATIC_DIR / "watch.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text())
    return HTMLResponse("<h1>watch.html not found</h1>", status_code=404)


# ---------------------------------------------------------------------------
# MJPEG broadcast stream
# ---------------------------------------------------------------------------
async def mjpeg_generator():
    """Yield MJPEG frames as multipart chunks."""
    last_seen = 0
    while True:
        if mjpeg_frame_id > last_seen and mjpeg_frame:
            last_seen = mjpeg_frame_id
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + mjpeg_frame
                + b"\r\n"
            )
        await asyncio.sleep(0.03)  # ~30 Hz poll, actual rate limited by producer


@app.get("/stream")
async def mjpeg_stream():
    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ---------------------------------------------------------------------------
# WebSocket: /ws/process — receives JPEG, returns annotated JPEG + MJPEG push
# ---------------------------------------------------------------------------
@app.websocket("/ws/process")
async def ws_process(websocket: WebSocket):
    global mjpeg_frame, mjpeg_frame_id

    await websocket.accept()
    print("[WS /ws/process] Client connected")

    latest_frame: asyncio.Queue = asyncio.Queue(maxsize=1)

    async def reader():
        try:
            while True:
                data = await websocket.receive_bytes()
                # Drop stale frames — only keep the latest
                if latest_frame.full():
                    try:
                        latest_frame.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                latest_frame.put_nowait(data)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    async def processor():
        global mjpeg_frame, mjpeg_frame_id
        try:
            while True:
                jpeg_bytes = await latest_frame.get()
                t0 = time.time()
                annotated_jpeg, meta = await asyncio.to_thread(
                    process_and_annotate, jpeg_bytes
                )
                process_ms = round((time.time() - t0) * 1000, 1)

                # Push to MJPEG broadcast
                mjpeg_frame = annotated_jpeg
                mjpeg_frame_id += 1

                # Send annotated frame back to viewer as binary
                # Prefix with 8 bytes of metadata (process_ms as float, detections as int)
                header = struct.pack("<fI", process_ms, meta["detections"])
                try:
                    await websocket.send_bytes(header + annotated_jpeg)
                except Exception:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[WS /ws/process] Processor error: {e}")

    reader_task = asyncio.create_task(reader())
    processor_task = asyncio.create_task(processor())

    try:
        done, pending = await asyncio.wait(
            [reader_task, processor_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    except Exception:
        reader_task.cancel()
        processor_task.cancel()

    print("[WS /ws/process] Client disconnected")


# ---------------------------------------------------------------------------
# Legacy WebSocket: /ws/detect — returns JSON detections (kept for compat)
# ---------------------------------------------------------------------------
def process_frame_json(jpeg_bytes: bytes) -> dict:
    """Decode JPEG, run YOLO person detection, return JSON results."""
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return {"detections": [], "frame_width": 0, "frame_height": 0}

    orig_h, orig_w = frame.shape[:2]
    results = yolo_model.track(
        source=frame,
        classes=[0],
        conf=0.5,
        imgsz=INPUT_SIZE,
        persist=True,
        verbose=False,
    )

    detections = []
    boxes = results[0].boxes

    for box in boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        conf = float(box.conf[0])
        track_id = int(box.id[0]) if box.id is not None else None

        detections.append({
            "x1": x1 / orig_w,
            "y1": y1 / orig_h,
            "x2": x2 / orig_w,
            "y2": y2 / orig_h,
            "name": f"Person #{track_id}" if track_id else "Person",
            "confidence": round(conf, 2),
            "color": "#00FF00",
        })

    return {
        "detections": detections,
        "frame_width": orig_w,
        "frame_height": orig_h,
        "process_time_ms": 0,
    }


@app.websocket("/ws/detect")
async def ws_detect(websocket: WebSocket):
    await websocket.accept()
    print("[WS /ws/detect] Client connected")

    latest_frame: asyncio.Queue = asyncio.Queue(maxsize=1)

    async def reader():
        try:
            while True:
                data = await websocket.receive_bytes()
                if latest_frame.full():
                    try:
                        latest_frame.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                latest_frame.put_nowait(data)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    async def processor():
        try:
            while True:
                jpeg_bytes = await latest_frame.get()
                t0 = time.time()
                result = await asyncio.to_thread(process_frame_json, jpeg_bytes)
                result["process_time_ms"] = round((time.time() - t0) * 1000, 1)
                try:
                    await websocket.send_json(result)
                except Exception:
                    break
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    reader_task = asyncio.create_task(reader())
    processor_task = asyncio.create_task(processor())

    try:
        done, pending = await asyncio.wait(
            [reader_task, processor_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    except Exception:
        reader_task.cancel()
        processor_task.cancel()

    print("[WS /ws/detect] Client disconnected")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": yolo_model is not None,
        "weights": "onnx" if ONNX_WEIGHTS.exists() and yolo_model is not None else "pt",
    }


# ---------------------------------------------------------------------------
# Run directly: python stream_processor.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)
