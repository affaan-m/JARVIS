"""
WebSocket stream processor for real-time person detection.
Receives JPEG frames via WS, runs YOLO11n (ONNX) tracking, returns JSON
detections. Browser overlays boxes on live video via canvas.

Endpoints:
  GET  /           — Redirect to /viewer
  GET  /viewer       — Operator page (WebRTC relay from VisionClaw glasses)
  GET  /watch        — Secondary site (MJPEG viewer)
  GET  /stream       — Raw MJPEG multipart stream
  WS   /ws/process   — Send JPEG -> receive annotated JPEG (MJPEG clients)
  WS   /ws/detect    — Send JPEG -> receive JSON detections (primary path)
  GET  /api/health   — Health check
"""

import asyncio
import logging
import os
import struct
import time
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
LOG_FORMAT = "[%(asctime)s] %(levelname)s %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATEFMT)
logger = logging.getLogger("stream_processor")

_file_handler = logging.FileHandler("/tmp/server-app.log")
_file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT))
logger.addHandler(_file_handler)

# CPU threading optimizations — 1 thread avoids context-switch overhead on 1-vCPU
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("ORT_NUM_THREADS", "1")

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
yolo_model = None

BASE_DIR = Path(__file__).parent
ONNX_WEIGHTS = BASE_DIR / "yolo11n.onnx"
PT_WEIGHTS = BASE_DIR / "yolo11n.pt"
STATIC_DIR = BASE_DIR / "static"

INPUT_SIZE = int(os.environ.get("YOLO_INPUT_SIZE", "320"))  # 192 after ONNX re-export, 320 default
CONF_THRESHOLD = 0.4
JPEG_QUALITY = 60  # For MJPEG annotated stream

# MJPEG broadcast: latest annotated frame shared with all /stream viewers
mjpeg_frame: bytes = b""
mjpeg_frame_id: int = 0
mjpeg_client_count: int = 0  # Only generate annotated frames when > 0

# Frame skip: run YOLO every Nth frame, return cached detections on skips
DETECT_EVERY_N = 2  # Run YOLO every 2nd frame
_cached_detections: dict = {"detections": [], "frame_width": 0, "frame_height": 0, "process_time_ms": 0, "skipped": False}
_frame_counter: int = 0

# Stats tracking
_server_start_time: float = 0.0
_total_frames_processed: int = 0
_total_process_time_ms: float = 0.0
_active_ws_connections: int = 0


# ---------------------------------------------------------------------------
# Drawing (for MJPEG annotated stream only)
# ---------------------------------------------------------------------------
def draw_box(frame, x1: int, y1: int, x2: int, y2: int, label: str, color: tuple):
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 6, y1), color, -1)
    cv2.putText(frame, label, (x1 + 3, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)


# ---------------------------------------------------------------------------
# Core: decode -> YOLO .track() -> annotate -> encode JPEG (MJPEG path)
# ---------------------------------------------------------------------------
def process_and_annotate(jpeg_bytes: bytes) -> tuple[bytes, dict]:
    """Decode JPEG, run YOLO tracking, draw boxes, re-encode annotated JPEG."""
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return jpeg_bytes, {"detections": 0, "process_time_ms": 0}

    results = yolo_model.track(
        source=frame,
        classes=[0],
        conf=CONF_THRESHOLD,
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
        label = f"Person #{track_id}" if track_id is not None else "Person"
        label += f" {conf:.0%}"
        draw_box(frame, x1, y1, x2, y2, label, (0, 255, 0))

    cv2.putText(
        frame, f"People: {person_count}",
        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2,
    )

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buf.tobytes(), {"detections": person_count}


# ---------------------------------------------------------------------------
# Core: decode -> YOLO .track() -> JSON detections (primary fast path)
# ---------------------------------------------------------------------------
def process_frame_json(jpeg_bytes: bytes, force_detect: bool = False) -> dict:
    """Decode JPEG, run YOLO person detection, return JSON results.

    With frame skipping: runs YOLO every DETECT_EVERY_N frames, returns
    cached detections on skip frames (costs only ~5ms for decode).
    """
    global _frame_counter, _cached_detections

    _frame_counter += 1
    run_yolo = force_detect or (_frame_counter % DETECT_EVERY_N == 0)

    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return {"detections": [], "frame_width": 0, "frame_height": 0,
                "process_time_ms": 0, "skipped": True}

    orig_h, orig_w = frame.shape[:2]

    if not run_yolo:
        # Return cached detections without running YOLO
        cached = _cached_detections.copy()
        cached["frame_width"] = orig_w
        cached["frame_height"] = orig_h
        cached["skipped"] = True
        cached["process_time_ms"] = 0
        return cached

    results = yolo_model.track(
        source=frame,
        classes=[0],
        conf=CONF_THRESHOLD,
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

    result = {
        "detections": detections,
        "frame_width": orig_w,
        "frame_height": orig_h,
        "process_time_ms": 0,
        "skipped": False,
    }
    _cached_detections = result.copy()

    # Lazily generate annotated MJPEG frame when /stream has viewers
    if mjpeg_client_count > 0:
        _generate_mjpeg_frame(frame, boxes, len(detections))

    return result


def _generate_mjpeg_frame(frame, boxes, person_count: int):
    """Draw boxes on frame and update MJPEG broadcast buffer."""
    global mjpeg_frame, mjpeg_frame_id

    for box in boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        conf = float(box.conf[0])
        track_id = int(box.id[0]) if box.id is not None else None
        label = f"Person #{track_id}" if track_id is not None else "Person"
        label += f" {conf:.0%}"
        draw_box(frame, x1, y1, x2, y2, label, (0, 255, 0))

    cv2.putText(
        frame, f"People: {person_count}",
        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2,
    )

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    mjpeg_frame = buf.tobytes()
    mjpeg_frame_id += 1


# ---------------------------------------------------------------------------
# Lifespan: load model once
# ---------------------------------------------------------------------------
async def _periodic_stats():
    """Log server stats every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        avg_ms = (
            round(_total_process_time_ms / _total_frames_processed, 1)
            if _total_frames_processed > 0
            else 0
        )
        uptime = round(time.time() - _server_start_time)
        logger.info(
            "Stats: frames=%d avg_ms=%.1f ws_conns=%d mjpeg_clients=%d uptime=%ds",
            _total_frames_processed, avg_ms, _active_ws_connections, mjpeg_client_count, uptime,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global yolo_model, _server_start_time
    _server_start_time = time.time()
    logger.info("Loading YOLO model...")
    t0 = time.time()

    from ultralytics import YOLO

    if ONNX_WEIGHTS.exists():
        logger.info("Using ONNX weights: %s", ONNX_WEIGHTS)
        yolo_model = YOLO(str(ONNX_WEIGHTS), task="detect")
    elif PT_WEIGHTS.exists():
        logger.info("ONNX not found, using PyTorch: %s", PT_WEIGHTS)
        yolo_model = YOLO(str(PT_WEIGHTS))
    else:
        raise FileNotFoundError("No YOLO weights found (yolo11n.onnx or yolo11n.pt)")

    # Warm up
    dummy = np.zeros((INPUT_SIZE, INPUT_SIZE, 3), dtype=np.uint8)
    yolo_model.track(dummy, classes=[0], conf=CONF_THRESHOLD, persist=True, verbose=False)

    logger.info("Model loaded in %.1fs (input_size=%d, conf=%.2f)", time.time() - t0, INPUT_SIZE, CONF_THRESHOLD)

    stats_task = asyncio.create_task(_periodic_stats())
    yield
    stats_task.cancel()
    logger.info("Shutdown complete")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - t0) * 1000, 1)
    # Skip noisy health checks from watchdog
    if request.url.path != "/api/health":
        logger.info("%s %s %d %.1fms", request.method, request.url.path, response.status_code, duration_ms)
    return response


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
# MJPEG broadcast stream (with client counting)
# ---------------------------------------------------------------------------
async def mjpeg_generator():
    """Yield MJPEG frames as multipart chunks."""
    global mjpeg_client_count
    mjpeg_client_count += 1
    last_seen = 0
    try:
        while True:
            if mjpeg_frame_id > last_seen and mjpeg_frame:
                last_seen = mjpeg_frame_id
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + mjpeg_frame
                    + b"\r\n"
                )
            await asyncio.sleep(0.03)
    finally:
        mjpeg_client_count -= 1


@app.get("/stream")
async def mjpeg_stream():
    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ---------------------------------------------------------------------------
# WebSocket: /ws/process — receives JPEG, returns annotated JPEG + MJPEG push
# (Kept for /watch and /stream MJPEG consumers)
# ---------------------------------------------------------------------------
@app.websocket("/ws/process")
async def ws_process(websocket: WebSocket):
    global mjpeg_frame, mjpeg_frame_id, _active_ws_connections

    await websocket.accept()
    _active_ws_connections += 1
    connect_time = time.time()
    frame_count = 0
    logger.info("[WS /ws/process] Client connected (active=%d)", _active_ws_connections)

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
        nonlocal frame_count
        global mjpeg_frame, mjpeg_frame_id, _total_frames_processed, _total_process_time_ms
        try:
            while True:
                jpeg_bytes = await latest_frame.get()
                t0 = time.time()
                annotated_jpeg, meta = await asyncio.to_thread(
                    process_and_annotate, jpeg_bytes
                )
                process_ms = round((time.time() - t0) * 1000, 1)
                frame_count += 1
                _total_frames_processed += 1
                _total_process_time_ms += process_ms

                mjpeg_frame = annotated_jpeg
                mjpeg_frame_id += 1

                header = struct.pack("<fI", process_ms, meta["detections"])
                try:
                    await websocket.send_bytes(header + annotated_jpeg)
                except Exception:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("[WS /ws/process] Processor error: %s", e)

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

    _active_ws_connections -= 1
    duration = round(time.time() - connect_time, 1)
    logger.info("[WS /ws/process] Client disconnected (frames=%d, duration=%.1fs, active=%d)", frame_count, duration, _active_ws_connections)


# ---------------------------------------------------------------------------
# WebSocket: /ws/detect — PRIMARY path: returns JSON detections
# Viewer overlays boxes on live video via canvas (no server re-encode)
# ---------------------------------------------------------------------------
@app.websocket("/ws/detect")
async def ws_detect(websocket: WebSocket):
    global _active_ws_connections, _total_frames_processed, _total_process_time_ms
    await websocket.accept()
    _active_ws_connections += 1
    connect_time = time.time()
    frame_count = 0
    logger.info("[WS /ws/detect] Client connected (active=%d)", _active_ws_connections)

    # Request-response flow: client sends frame, waits for response, then sends next
    try:
        while True:
            jpeg_bytes = await websocket.receive_bytes()
            t0 = time.time()
            result = await asyncio.to_thread(process_frame_json, jpeg_bytes)
            process_ms = round((time.time() - t0) * 1000, 1)
            result["process_time_ms"] = process_ms
            frame_count += 1
            _total_frames_processed += 1
            _total_process_time_ms += process_ms
            await websocket.send_json(result)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("[WS /ws/detect] Error: %s", e)

    _active_ws_connections -= 1
    duration = round(time.time() - connect_time, 1)
    logger.info("[WS /ws/detect] Client disconnected (frames=%d, duration=%.1fs, active=%d)", frame_count, duration, _active_ws_connections)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    uptime = round(time.time() - _server_start_time) if _server_start_time else 0
    return {
        "status": "ok",
        "model_loaded": yolo_model is not None,
        "weights": "onnx" if ONNX_WEIGHTS.exists() and yolo_model is not None else "pt",
        "ws_connections": _active_ws_connections,
        "mjpeg_clients": mjpeg_client_count,
        "total_frames": _total_frames_processed,
        "uptime_seconds": uptime,
    }


# ---------------------------------------------------------------------------
# Run directly: python stream_processor.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)
