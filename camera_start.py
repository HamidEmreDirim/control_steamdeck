#!/usr/bin/env python3
"""
Zero-lag WebSocket camera streamer (OpenCV + FSRCNN super-res)
- Always sends the latest frame (no backlog)
- Uses both a "latest-frame stack" and an asyncio.Queue(maxsize=1)
- Binary WebSocket messages = JPEG bytes
"""

import asyncio
import pathlib
import time
import cv2
from cv2 import dnn_superres as dsr
import numpy as np
import websockets
from websockets.server import serve
from dataclasses import dataclass, field

# ───── user knobs ────────────────────────────────────────────────
DEVICE      = "/dev/video0"
SRC_W, SRC_H = 640, 480
TARGET_W, TARGET_H = 1280, 800              # Steam Deck screen
MODEL, SCALE = "fsrcnn", 2                   # 2× FSRCNN
MODELDIR    = pathlib.Path("~/superres/models").expanduser()
BIND_HOST   = "0.0.0.0"
BIND_PORT   = 8765
ROUTE_PATH  = "/stream"                      # ws://host:8765/stream
TARGET_FPS  = 30                             # throttle to ~30 FPS to clients
JPEG_QUALITY = 80                            # balance size vs. quality
# ─────────────────────────────────────────────────────────────────

# ---------- utilities ----------
def crop16x10(img: np.ndarray, tw: int, th: int) -> np.ndarray:
    h, w = img.shape[:2]
    want = tw / th  # 1.6
    if w / h > want:                 # too wide → crop width
        new_w = int(h * want)
        x0 = (w - new_w) // 2
        img = img[:, x0:x0 + new_w]
    else:                            # too tall → crop height
        new_h = int(w / want)
        y0 = (h - new_h) // 2
        img = img[y0:y0 + new_h]
    return cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA)

def jpeg_encode(img: np.ndarray, quality: int = 80) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()

# ---------- data hub (stack + queue) ----------
@dataclass
class FrameHub:
    """Holds the latest frame (stack) and an asyncio queue (size=1) for push."""
    latest_jpeg: bytes | None = None
    q: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=1))

    async def publish(self, jpg: bytes):
        """Publish: update latest, and ensure queue has only the newest frame."""
        self.latest_jpeg = jpg
        try:
            # Try to put without waiting; if full, replace the old one.
            self.q.put_nowait(jpg)
        except asyncio.QueueFull:
            try:
                _ = self.q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            await self.q.put(jpg)

    async def next(self, timeout: float | None = None) -> bytes | None:
        """Get next frame if available; otherwise fall back to 'latest' after timeout."""
        try:
            if timeout is None:
                return await self.q.get()
            else:
                return await asyncio.wait_for(self.q.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return self.latest_jpeg

# ---------- camera producer (runs in a thread-like task) ----------
async def camera_producer(hub: FrameHub):
    # Load model
    model_path = MODELDIR / "FSRCNN-small_x2.pb"
    if not model_path.exists():
        raise SystemExit(f"Model not found → {model_path}")

    sr = dsr.DnnSuperResImpl_create()
    sr.readModel(str(model_path))
    sr.setModel(MODEL, SCALE)
    # If OpenCL is available, this can help on the Deck
    try:
        sr.setPreferableTarget(cv2.dnn.DNN_TARGET_OPENCL)
    except Exception:
        pass

    cap = cv2.VideoCapture(DEVICE, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  SRC_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, SRC_H)

    if not cap.isOpened():
        raise SystemExit(f"Cannot open camera: {DEVICE}")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("⚠️ no frame from camera; retrying…")
                await asyncio.sleep(0.05)
                continue

            # Super-res → crop → JPEG
            up   = sr.upsample(frame)                   # 640x480 → 1280x960
            view = crop16x10(up, TARGET_W, TARGET_H)    # 1280x960 → 1280x800
            jpg  = jpeg_encode(view, JPEG_QUALITY)

            # Publish latest
            await hub.publish(jpg)

            # Let the loop breathe a bit; producer tries to run as fast as camera.
            await asyncio.sleep(0)
    finally:
        cap.release()

# ---------- client handler ----------
async def client_sender(ws, hub: FrameHub):
    """
    Sends frames to a single client.
    - Always sends the newest available frame.
    - Throttles to ~TARGET_FPS if frames are coming in too fast.
    """
    frame_period = 1.0 / max(1, TARGET_FPS)
    last_send = 0.0

    # On connect, try to give something immediately if we already have a frame
    if hub.latest_jpeg:
        await ws.send(hub.latest_jpeg)

    while True:
        # Pull next frame (or fallback to latest if nothing within 1/2 frame period)
        timeout = frame_period * 0.5
        jpg = await hub.next(timeout=timeout)
        if jpg is None:
            await asyncio.sleep(frame_period * 0.5)
            continue

        # Throttle send rate
        now = time.perf_counter()
        if now - last_send < frame_period:
            await asyncio.sleep(frame_period - (now - last_send))

        await ws.send(jpg)   # binary JPEG
        last_send = time.perf_counter()

async def ws_router(websocket, path, hub: FrameHub):
    # Only allow a specific route (simple guard)
    if path != ROUTE_PATH:
        await websocket.close(code=1008, reason="Invalid route")
        return
    try:
        await client_sender(websocket, hub)
    except websockets.ConnectionClosed:
        # client disconnected
        pass

# ---------- main ----------
async def main():
    hub = FrameHub()
    # Start camera producer
    cam_task = asyncio.create_task(camera_producer(hub))

    # Start WS server
    async with serve(lambda ws, path: ws_router(ws, path, hub),
                     BIND_HOST, BIND_PORT, max_size=None, ping_interval=20):
        print(f"✅ WebSocket up at ws://{BIND_HOST}:{BIND_PORT}{ROUTE_PATH}")
        print("   Binary messages are JPEG frames.")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
