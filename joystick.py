# joystick.py
import os, glob, asyncio
from evdev import InputDevice, list_devices, ecodes

class GamepadReader:
    """
    Reads a gamepad:
      • v from ABS_Y
      • w from first available right-axis candidate
      • buttons: BTN_TL, BTN_TR, BTN_TL2, BTN_TR2
    Normalizes to [-1..+1] with dead-zone. Calls optional callbacks.
    """
    WATCH_BTNS = (ecodes.BTN_TL, ecodes.BTN_TR, ecodes.BTN_TL2, ecodes.BTN_TR2)

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

        # button states
        self.buttons = {code: False for code in self.WATCH_BTNS}

    # ---------- Discovery ----------
    def _auto_event_device(self) -> str | None:
        for path in sorted(glob.glob("/dev/input/by-id/*-OpenSD*")):
            if os.path.exists(path):
                return path
        for p in list_devices():
            dev = InputDevice(p)
            try:
                caps_abs = [c for c, *_ in dev.capabilities().get(ecodes.EV_ABS, [])]
                caps_key = [c for c, *_ in dev.capabilities().get(ecodes.EV_KEY, [])]
                if ecodes.ABS_Y in caps_abs:
                    for nm in self.right_axis_names:
                        code = getattr(ecodes, nm, None)
                        if code in caps_abs:
                            return p
            finally:
                dev.close()
        return None

    def open(self):
        path = self.device if self.device != "auto" else self._auto_event_device()
        if not path:
            raise RuntimeError("Gamepad not found (no suitable /dev/input/* device).")
        self.dev = InputDevice(path)
        caps_abs = [c for c, *_ in self.dev.capabilities().get(ecodes.EV_ABS, [])]
        if ecodes.ABS_Y not in caps_abs:
            self.dev.close()
            raise RuntimeError("Gamepad found but ABS_Y axis missing.")

        for nm in self.right_axis_names:
            code = getattr(ecodes, nm, None)
            if code in caps_abs:
                self.w_code = code
                break
        if self.w_code is None:
            for code in (ecodes.ABS_RX, ecodes.ABS_Z, ecodes.ABS_RY):
                if code in caps_abs:
                    self.w_code = code
                    break
        if self.w_code is None:
            self.dev.close()
            raise RuntimeError("Right axis not found among candidates.")

        self.abs_info = {c: self.dev.absinfo(c) for c in caps_abs}
        print(f"* Gamepad: {self.dev.name}  @ {self.dev.path}")
        print(f"  Using ABS_Y for v and {self._code_name(self.w_code)} for w")

    def _code_name(self, code: int) -> str:
        for k, v in ecodes.__dict__.items():
            if isinstance(v, int) and v == code and (k.startswith("ABS_") or k.startswith("BTN_")):
                return k
        return f"CODE({code})"

    # ---------- Normalization ----------
    def _normalize(self, val, info) -> float:
        span = info.max - info.min
        if not span:
            return 0.0
        n = (val - info.min) / span * 2.0 - 1.0
        if abs(n) < self.dead_zone:
            return 0.0
        return round(n, 3)

    # ---------- Async read loop ----------
    async def read_loop(self, on_axes=None, on_button=None):
        """
        Reads events forever.
        on_axes((v,w)) called when either axis changes.
        on_button(code:int, is_down:bool) called on button transitions.
        """
        last_v, last_w = None, None
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
                if (self.v, self.w) != (last_v, last_w):
                    if on_axes:
                        on_axes((self.v, self.w))
                    last_v, last_w = self.v, self.w

            elif ev.type == ecodes.EV_KEY and ev.code in self.buttons:
                is_down = (ev.value != 0)
                if self.buttons[ev.code] != is_down:
                    self.buttons[ev.code] = is_down
                    if on_button:
                        on_button(ev.code, is_down)

    def get(self):
        return self.v, self.w

    def get_button(self, code: int) -> bool:
        return bool(self.buttons.get(code, False))

    def close(self):
        if self.dev is not None:
            try: self.dev.close()
            except Exception: pass
