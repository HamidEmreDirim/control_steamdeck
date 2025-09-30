#!/usr/bin/env python3
"""
Zero-lag WebSocket camera streamer (no upscale, max FPS)
- Always sends the latest frame (no backlog)
- Uses a "latest-frame stack" + asyncio.Queue(maxsize=1)
- Binary WebSocket messages = JPEG bytes
- Per-client send Hz printed every second
"""

import asyncio
import pathlib
import time
import cv2
import numpy as np
import websockets
from websockets.server import serve
from dataclasses import dataclass, field

# ───── user knobs ────────────────────────────────────────────────
DEVICE       = "/dev/video0"
SRC_W, SRC_H = 640, 480            # capture size (no further resize)
BIND_HOST    = "0.0.0.0"
BIND_PORT    = 8765
ROUTE_PATH   = "/rgb_camera"       # ws://host:8765/rgb_camera
TARGET_FPS   = 0                   # 0 or <=0 means "no throttle" (max possible)
JPEG_QUALITY = 40                  # lower = smaller & faster encode, but noisier
# ─────────────────────────────────────────────────────────────────

# ---------- utilities ----------
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

# ---------- camera producer (runs in a task) ----------
async def camera_producer(hub: FrameHub):
    cap = cv2.VideoCapture(DEVICE, cv2.CAP_V4L2)

    # Aim for low-latency capture
    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))  # faster on many UVC cams
    except Exception:
        pass
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  SRC_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, SRC_H)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # drop internal buffer

    if not cap.isOpened():
        raise SystemExit(f"Cannot open camera: {DEVICE}")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("⚠️ no frame from camera; retrying…")
                await asyncio.sleep(0.01)
                continue

            # No upscale, no crop — encode as-is
            jpg = jpeg_encode(frame, JPEG_QUALITY)

            # Publish latest
            await hub.publish(jpg)

            # Let the event loop breathe
            await asyncio.sleep(0)
    finally:
        cap.release()

# ---------- client handler ----------
async def client_sender(ws, hub: FrameHub):
    """
    Sends frames to a single client.
    - Always sends the newest available frame.
    - No throttling if TARGET_FPS <= 0 (max possible).
    - Prints the actual Hz every second.
    """
    throttle = TARGET_FPS and TARGET_FPS > 0
    frame_period = (1.0 / TARGET_FPS) if throttle else 0.0
    last_send = 0.0

    # FPS counter
    sent_frames = 0
    last_report = time.perf_counter()

    # On connect, try to give something immediately if we already have a frame
    if hub.latest_jpeg:
        await ws.send(hub.latest_jpeg)

    while True:
        # If throttling, wait for up to half a frame; otherwise don't wait at all
        timeout = frame_period * 0.5 if throttle else 0.0
        jpg = await hub.next(timeout=timeout if throttle else None)
        if jpg is None:
            # No fresh frame; avoid hot loop spin
            await asyncio.sleep(0.001)
            continue

        # Throttle send rate only if requested
        if throttle:
            now = time.perf_counter()
            if now - last_send < frame_period:
                await asyncio.sleep(frame_period - (now - last_send))

        await ws.send(jpg)   # binary JPEG
        last_send = time.perf_counter()

        # Count + report Hz every second
        sent_frames += 1
        if last_send - last_report >= 1.0:
            hz = sent_frames / (last_send - last_report)
            print(f"[client {id(ws)}] {hz:.1f} Hz")
            sent_frames = 0
            last_report = last_send

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
    asyncio.create_task(camera_producer(hub))

    # Start WS server (no message size limit; default ping keeps connections healthy)
    async with serve(lambda ws, path: ws_router(ws, path, hub),
                     BIND_HOST, BIND_PORT, max_size=None, ping_interval=20):
        print(f"✅ WebSocket up at ws://{BIND_HOST}:{BIND_PORT}{ROUTE_PATH}")
        print("   Binary messages are JPEG frames (no upscale, max FPS).")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
