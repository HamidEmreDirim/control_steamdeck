#!/usr/bin/env python3
# joy_ws_sender_refcompat.py
import asyncio
import json
import os
import time
import websockets

# IMPORTANT: put your working GamepadReader in joystick.py (exactly as you sent)
from joystick import GamepadReader

DEFAULT_PORT = 8766
DEFAULT_RATE_HZ = 50
RECONNECT_DELAY = 2.0

def prompt_server_url() -> str:
    print("\n=== Joystick WebSocket Sender ===")
    last = os.environ.get("LAST_ROS_IP", "192.168.1.46")
    ip = input(f"Enter ROS PC IP [{last}]: ").strip() or last
    try:
        port = int(input(f"Enter port [{DEFAULT_PORT}]: ").strip() or DEFAULT_RATE_HZ and DEFAULT_PORT)
    except Exception:
        port = DEFAULT_PORT
    os.environ["LAST_ROS_IP"] = ip  # session-only memory
    url = f"ws://{ip}:{port}/"
    print(f"Connecting to: {url}\n")
    return url

async def main():
    server_ws = prompt_server_url()

    # Open joystick using your *unchanged* class
    gp = GamepadReader(device="auto", dead_zone=0.05)
    gp.open()
    print(f"[JOY] Connected: {gp.dev.name} @ {gp.dev.path}")

    # Start its own async read loop (it will keep gp.v / gp.w updated)
    reader_task = asyncio.create_task(gp.read_loop())

    send_hz = DEFAULT_RATE_HZ
    interval = 1.0 / send_hz
    print_debug = True

    try:
        while True:
            try:
                print(f"[JOY] Connecting to {server_ws} ...")
                async with websockets.connect(server_ws, ping_interval=None) as ws:
                    print("[JOY] Connected to server.")
                    last = time.time()
                    t0 = last
                    sent = 0
                    while True:
                        now = time.time()
                        if now - last >= interval:
                            # Read current values that your GamepadReader keeps updated
                            v = float(gp.v)
                            w = float(gp.w)
                            msg = {
                                "type": "joystick",
                                "timestamp": int(now * 1000),
                                "v": -v,
                                "w": -w,
                            }
                            await ws.send(json.dumps(msg, separators=(",", ":")))
                            sent += 1
                            last = now
                            if print_debug and (now - t0) >= 1.0:
                                print(f"[SEND] {sent} msgs/s  v={v:+.3f}  w={w:+.3f}")
                                sent = 0
                                t0 = now
                        await asyncio.sleep(0)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[JOY] Disconnected ({e}); retrying in {RECONNECT_DELAY}s...")
                await asyncio.sleep(RECONNECT_DELAY)
    finally:
        reader_task.cancel()
        try:
            await reader_task
        except Exception:
            pass
        # Your GamepadReader closes the device in its own code if needed

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
