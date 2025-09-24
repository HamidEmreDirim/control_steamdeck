# joystick.py
import os, glob, asyncio
from evdev import InputDevice, list_devices, ecodes

class GamepadReader:
    """
    Reads a gamepad's left Y (forward/back) and a chosen right-axis for turn (ω).
    Normalizes to [-1..+1] with dead-zone. Async iterator updates internal v,w.
    """
    def __init__(self, device="auto", dead_zone=0.05,
                 right_axis_candidates=("ABS_RX", "ABS_Z", "ABS_RY"),
                 invert_v=False, invert_w=False):
        self.device = device
        self.dead_zone = float(dead_zone)
        self.right_axis_names = tuple(right_axis_candidates)
        self.invert_v = invert_v
        self.invert_w = invert_w

        self.dev: InputDevice | None = None
        self.abs_info = {}
        self.w_code = None
        self.v = 0.0
        self.w = 0.0

    # ---------- Discovery ----------
    def _auto_event_device(self) -> str | None:
        # Prefer OpenSD/SteamDeck devices if present
        for path in sorted(glob.glob("/dev/input/by-id/*-OpenSD*")):
            if os.path.exists(path):
                return path
        # Fallback: any input that has ABS_Y + any right-axis candidate
        for p in list_devices():
            dev = InputDevice(p)
            try:
                caps = [c for c, *_ in dev.capabilities().get(ecodes.EV_ABS, [])]
                if ecodes.ABS_Y in caps:
                    for nm in self.right_axis_names:
                        code = getattr(ecodes, nm, None)
                        if code in caps:
                            return p
            finally:
                dev.close()
        return None

    def open(self):
        path = self.device if self.device != "auto" else self._auto_event_device()
        if not path:
            raise RuntimeError("Gamepad not found (no suitable /dev/input/* device).")
        self.dev = InputDevice(path)
        caps = [c for c, *_ in self.dev.capabilities().get(ecodes.EV_ABS, [])]
        if ecodes.ABS_Y not in caps:
            self.dev.close()
            raise RuntimeError("Gamepad found but ABS_Y axis missing.")

        # Map right-axis by preference
        for nm in self.right_axis_names:
            code = getattr(ecodes, nm, None)
            if code in caps:
                self.w_code = code
                break
        if self.w_code is None:
            # last-resort fallback
            for code in (ecodes.ABS_RX, ecodes.ABS_Z, ecodes.ABS_RY):
                if code in caps:
                    self.w_code = code
                    break
        if self.w_code is None:
            self.dev.close()
            raise RuntimeError("Right axis not found among candidates.")

        self.abs_info = {c: self.dev.absinfo(c) for c in caps}
        print(f"* Gamepad: {self.dev.name}  @ {self.dev.path}")
        print(f"  Using ABS_Y for v and {self._code_name(self.w_code)} for w")

    def _code_name(self, code: int) -> str:
        # reverse-lookup name when printing
        for k, v in ecodes.__dict__.items():
            if isinstance(v, int) and v == code and k.startswith("ABS_"):
                return k
        return f"ABS({code})"

    # ---------- Normalization ----------
    def _normalize(self, val, info) -> float:
        span = info.max - info.min
        if not span:
            return 0.0
        n = (val - info.min) / span * 2.0 - 1.0
        if abs(n) < self.dead_zone:
            return 0.0
        # round a bit to keep TX tidy
        return round(n, 3)

    # ---------- Async read loop ----------
    async def read_loop(self, on_change=None):
        """
        Continuously reads events. If on_change is provided, it's called as
        on_change((v, w)) whenever either value changes.
        """
        last_v, last_w = None, None
        async for ev in self.dev.async_read_loop():
            if ev.type != ecodes.EV_ABS:
                continue

            if ev.code == ecodes.ABS_Y:
                v = self._normalize(ev.value, self.abs_info[ev.code])
                if self.invert_v:
                    v = -v
                self.v = v

            elif ev.code == self.w_code:
                w = self._normalize(ev.value, self.abs_info[ev.code])
                if self.invert_w:
                    w = -w
                self.w = w

            if (self.v, self.w) != (last_v, last_w):
                if on_change:
                    on_change((self.v, self.w))
                last_v, last_w = self.v, self.w

    def get(self):
        return self.v, self.w

    def close(self):
        if self.dev is not None:
            try:
                self.dev.close()
            except Exception:
                pass
