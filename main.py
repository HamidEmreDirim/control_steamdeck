#!/usr/bin/env python3
# unified main.py — telemetry + camera on the same WebSocket port
import asyncio, time, pathlib
from collections import deque

import cv2
import numpy as np
import websockets
from websockets.server import serve
from evdev import ecodes

from config_loader import load_config
from joystick import GamepadReader
from lora import LoraLink

# ───────────────────── Camera helpers (from camera_start.py) ─────────────────────
DEVICE       = "/dev/video0"   # override here if desired; or keep as-is
SRC_W, SRC_H = 640, 480
JPEG_QUALITY = 40              # 40 is a nice speed/size balance

def jpeg_encode(img: np.ndarray, quality: int = 80) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()

class FrameHub:
    """Holds the latest JPEG frame and a size-1 queue for push semantics."""
    def __init__(self):
        self.latest_jpeg: bytes | None = None
        self.q: asyncio.Queue = asyncio.Queue(maxsize=1)

    async def publish(self, jpg: bytes):
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
        try:
            if timeout is None:
                return await self.q.get()
            else:
                return await asyncio.wait_for(self.q.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return self.latest_jpeg

async def camera_producer(hub: FrameHub, device: str = DEVICE, w: int = SRC_W, h: int = SRC_H):
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    except Exception:
        pass
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        raise SystemExit(f"Cannot open camera: {device}")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("⚠️ no frame from camera; retrying…")
                await asyncio.sleep(0.01)
                continue
            jpg = jpeg_encode(frame, JPEG_QUALITY)
            await hub.publish(jpg)
            await asyncio.sleep(0)  # yield
    finally:
        cap.release()

async def camera_client_sender(ws, hub: FrameHub, target_fps: float | int = 0):
    throttle = bool(target_fps and target_fps > 0)
    frame_period = (1.0 / float(target_fps)) if throttle else 0.0
    last_send = 0.0

    sent_frames = 0
    last_report = time.perf_counter()

    if hub.latest_jpeg:
        await ws.send(hub.latest_jpeg)

    while True:
        timeout = frame_period * 0.5 if throttle else None
        jpg = await hub.next(timeout=timeout)
        if jpg is None:
            await asyncio.sleep(0.001)
            continue
        if throttle:
            now = time.perf_counter()
            if now - last_send < frame_period:
                await asyncio.sleep(frame_period - (now - last_send))
        await ws.send(jpg)
        last_send = time.perf_counter()

        sent_frames += 1
        if last_send - last_report >= 1.0:
            hz = sent_frames / (last_send - last_report)
            print(f"[camera -> {id(ws)}] {hz:.1f} Hz")
            sent_frames = 0
            last_report = last_send

# ───────────────────── Telemetry / control tasks (from your main.py) ─────────────────────
async def sender_task(link: LoraLink,
                      pad: GamepadReader,
                      period_s: float,
                      hb_timeout_s: float,
                      state: dict,
                      cfg):
    last_tx = (None, None)
    while True:
        await asyncio.sleep(period_s)

        v_raw, w_raw = pad.get()
        scale = cfg.modes.speed_plus_scale if state["speed_plus"] else cfg.modes.speed_default_scale
        v_eff = round(v_raw * scale, 3)
        w_eff = w_raw

        state["v_eff"] = v_eff
        state["w_eff"] = w_eff

        if state["sleep"]:
            continue
        if time.time() - link.last_hb > hb_timeout_s:
            continue

        link.write_line(f"{v_eff},{w_eff}")
        now = time.time()
        state["last_tx_time"] = now
        state["tx_times"].append(now)

        if (v_eff, w_eff) != last_tx:
            print(f"[TX] {v_eff},{w_eff}  | mode: {'S+' if state['speed_plus'] else 'S-'}"
                  f"  sleep: {state['sleep']}")
            last_tx = (v_eff, w_eff)

# Small helpers that mirror telemetry_ws.py snapshot logic
def lora_connected(link: LoraLink, hb_timeout_s: float) -> bool:
    return (time.time() - link.last_hb) < hb_timeout_s

def link_quality(link: LoraLink, hb_timeout_s: float) -> int:
    age = time.time() - link.last_hb
    if age <= hb_timeout_s * 0.2:
        return 100
    if age >= hb_timeout_s:
        return 0
    frac = (age - hb_timeout_s * 0.2) / (hb_timeout_s * 0.8)
    return max(0, min(100, int(round(100 * (1.0 - frac)))))

def tx_rate_hz(state_tx_times: deque) -> float:
    now = time.time()
    while state_tx_times and (now - state_tx_times[0] > 3.0):
        state_tx_times.popleft()
    return round(len(state_tx_times) / 3.0, 2)

def telemetry_snapshot_json(state: dict, link: LoraLink, hb_timeout_s: float) -> str:
    now_ms = int(time.time() * 1000)
    obj = {
        "type": "telemetry",
        "timestamp": now_ms,
        "sleep": bool(state.get("sleep", False)),
        "speed_plus": bool(state.get("speed_plus", False)),
        "lora_connected": lora_connected(link, hb_timeout_s),
        "link_quality": link_quality(link, hb_timeout_s),
        "tx_rate_hz": tx_rate_hz(state.get("tx_times", deque())),
        "rx_hb_age_s": round(time.time() - link.last_hb, 3),
        "v": float(state.get("v_eff", 0.0)),
        "w": float(state.get("w_eff", 0.0)),
        "battery_pct": 100,
        "temperature_c": 25,
        "air_quality": 95,
    }
    import json
    return json.dumps(obj, separators=(",", ":"))

# ───────────────────── Unified WebSocket server (one port, two routes) ─────────────────────
async def run_unified_ws(host, port, routes):
    """
    routes: dict like {
        "/telemetry": telemetry_handler,
        "/rgb_camera": camera_handler,
    }
    """
    async def router(ws, path):
        handler = routes.get(path)
        if not handler:
            await ws.close(code=1008, reason="Invalid route")
            return
        await handler(ws)

    async with serve(router, host, port, max_size=None, ping_interval=20):
        print(f"✅ WS up on ws://{host}:{port}  "
              f"(routes: {', '.join(routes.keys())})")
        await asyncio.Future()

# ───────────────────── Main ─────────────────────
def main():
    cfg = load_config("config.json")

    # ─── Serial (LoRa)
    port = cfg.serial.port
    if port == "auto":
        port = LoraLink.auto_serial_port()
    if not port:
        print("Seri port bulunamadı.")
        return

    link = LoraLink(
        port=port,
        baud=cfg.serial.baud,
        hb_msg=cfg.protocol.hb_msg,
        timeout_msg=cfg.protocol.timeout_msg,
        timeout_clear_msg=cfg.protocol.timeout_clear_msg
    )
    try:
        link.open()
    except Exception as e:
        print(f"Seri port açılamadı: {e}")
        return
    print(f"* Serial: {port} @ {cfg.serial.baud}")

    def on_rx(line: str):
        print(f"[RX] {line}")
    link.start_reader(on_line=on_rx)

    # ─── Gamepad
    pad = GamepadReader(
        device=cfg.joystick.device,
        dead_zone=cfg.joystick.dead_zone,
        right_axis_candidates=tuple(cfg.joystick.right_axis_candidates),
        invert_v=cfg.joystick.invert_v,
        invert_w=cfg.joystick.invert_w
    )
    try:
        pad.open()
    except Exception as e:
        print(f"Gamepad açılamadı: {e}")
        link.close()
        return

    period_s = 1.0 / float(cfg.tx.max_rate_hz)
    hb_timeout_s = float(cfg.tx.hb_timeout_sec)

    # ─── State & mode manager
    state = {
        "sleep": bool(cfg.modes.start_sleep),
        "speed_plus": False,
        "sleep_combo_t0": None, "sleep_combo_fired": False,
        "speed_combo_t0": None, "speed_combo_fired": False,
        "v_eff": 0.0, "w_eff": 0.0,
        "last_tx_time": 0.0,
        "tx_times": deque(maxlen=512),
    }
    HOLD = float(cfg.modes.combo_hold_sec)

    def handle_button(code, is_down):
        pass  # keep quiet unless debugging

    def handle_axes(vw):
        pass  # keep quiet unless debugging

    async def mode_manager():
        while True:
            await asyncio.sleep(0.05)
            now = time.time()
            tl = pad.get_button(ecodes.BTN_TL)
            tr = pad.get_button(ecodes.BTN_TR)
            if tl and tr:
                if state["sleep_combo_t0"] is None:
                    state["sleep_combo_t0"] = now
                    state["sleep_combo_fired"] = False
                elif not state["sleep_combo_fired"] and (now - state["sleep_combo_t0"] >= HOLD):
                    state["sleep"] = not state["sleep"]
                    state["sleep_combo_fired"] = True
                    print(f"[MODE] Sleep {'ON' if state['sleep'] else 'OFF'}")
            else:
                state["sleep_combo_t0"] = None
                state["sleep_combo_fired"] = False

            tl2 = pad.get_button(ecodes.BTN_TL2)
            tr2 = pad.get_button(ecodes.BTN_TR2)
            if tl2 and tr2:
                if state["speed_combo_t0"] is None:
                    state["speed_combo_t0"] = now
                    state["speed_combo_fired"] = False
                elif not state["speed_combo_fired"] and (now - state["speed_combo_t0"] >= HOLD):
                    state["speed_plus"] = not state["speed_plus"]
                    state["speed_combo_fired"] = True
                    print(f"[MODE] Speed+ {'ON' if state['speed_plus'] else 'OFF'}")
            else:
                state["speed_combo_t0"] = None
                state["speed_combo_fired"] = False

    # ─── Camera producer + hub
    hub = FrameHub()

    # ─── Telemetry broadcaster handler
    telemetry_clients = set()
    publish_period = 1.0 / float(cfg.ws.publish_hz)

    async def telemetry_handler(ws):
        telemetry_clients.add(ws)
        # send an initial snapshot immediately
        await ws.send(telemetry_snapshot_json(state, link, hb_timeout_s))
        try:
            async for _ in ws:
                pass  # ignore incoming
        finally:
            telemetry_clients.discard(ws)

    async def telemetry_broadcaster():
        while True:
            if telemetry_clients:
                msg = telemetry_snapshot_json(state, link, hb_timeout_s)
                # best-effort fanout
                send_tasks = []
                for ws in list(telemetry_clients):
                    async def _send_one(client):
                        try:
                            await client.send(msg)
                        except Exception:
                            try:
                                await client.close()
                            except Exception:
                                pass
                            telemetry_clients.discard(client)
                    send_tasks.append(_send_one(ws))
                if send_tasks:
                    await asyncio.gather(*send_tasks, return_exceptions=True)
            await asyncio.sleep(publish_period)

    # ─── Camera route handler wrapper (so it matches telemetry handler signature)
    async def rgb_camera_handler(ws):
        await camera_client_sender(ws, hub, target_fps=0)  # 0 = max possible

    # ─── Route map (single port)
    routes = {
        "/telemetry": telemetry_handler,
        "/rgb_camera": rgb_camera_handler,
    }

    async def run_all():
        return await asyncio.gather(
            pad.read_loop(on_axes=handle_axes, on_button=handle_button),
            sender_task(link, pad, period_s, hb_timeout_s, state, cfg),
            mode_manager(),
            camera_producer(hub, DEVICE, SRC_W, SRC_H),
            telemetry_broadcaster(),
            run_unified_ws(cfg.ws.host, cfg.ws.port, routes),
        )

    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        pass
    finally:
        pad.close()
        link.close()
        print("Çıkıyorum…")

if __name__ == "__main__":
    main()
