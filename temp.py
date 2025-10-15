#!/usr/bin/env python3
import asyncio, os, glob
from evdev import InputDevice, list_devices, ecodes

class GamepadReader:
    def __init__(self, device="auto", dead_zone=0.05,
                 right_axis_candidates=("ABS_RX", "ABS_Z", "ABS_RY"),
                 invert_v=False, invert_w=False):
        self.device = device
        self.dead_zone = dead_zone
        self.right_axis_candidates = right_axis_candidates
        self.invert_v = invert_v
        self.invert_w = invert_w
        self.dev = None
        self.abs_info = {}
        self.w_code = None
        self.v = 0.0
        self.w = 0.0

    def _auto_event_device(self):
        for path in sorted(glob.glob("/dev/input/by-id/*-OpenSD*")):
            if os.path.exists(path):
                return path
        for p in list_devices():
            dev = InputDevice(p)
            caps_abs = [c for c, *_ in dev.capabilities().get(ecodes.EV_ABS, [])]
            if ecodes.ABS_Y in caps_abs:
                for nm in self.right_axis_candidates:
                    code = getattr(ecodes, nm, None)
                    if code in caps_abs:
                        dev.close()
                        return p
            dev.close()
        return None

    def open(self):
        path = self.device if self.device != "auto" else self._auto_event_device()
        if not path:
            raise RuntimeError("No joystick found.")
        self.dev = InputDevice(path)
        caps_abs = [c for c, *_ in self.dev.capabilities().get(ecodes.EV_ABS, [])]
        for nm in self.right_axis_candidates:
            code = getattr(ecodes, nm, None)
            if code in caps_abs:
                self.w_code = code
                break
        self.abs_info = {c: self.dev.absinfo(c) for c in caps_abs}
        print(f"* Gamepad: {self.dev.name} @ {self.dev.path}")
        print(f"  Using ABS_Y for v and {self._code_name(self.w_code)} for w")

    def _code_name(self, code):
        for k, v in ecodes.__dict__.items():
            if v == code and k.startswith("ABS_"):
                return k
        return str(code)

    def _normalize(self, val, info):
        span = info.max - info.min
        if span == 0:
            return 0.0
        n = (val - info.min) / span * 2.0 - 1.0
        if abs(n) < self.dead_zone:
            n = 0.0
        return round(n, 3)

    async def read_loop(self):
        async for ev in self.dev.async_read_loop():
            if ev.type == ecodes.EV_ABS:
                if ev.code == ecodes.ABS_Y:
                    v = self._normalize(ev.value, self.abs_info[ev.code])
                    if self.invert_v: v = -v
                    self.v = v
                elif ev.code == self.w_code:
                    w = self._normalize(ev.value, self.abs_info[ev.code])
                    if self.invert_w: w = -w
                    self.w = w
                print(f"v={self.v:+.3f}, w={self.w:+.3f}")

async def main():
    gp = GamepadReader()
    gp.open()
    await gp.read_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
