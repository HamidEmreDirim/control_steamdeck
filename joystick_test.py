#!/usr/bin/env python3
# input_monitor.py
import argparse, asyncio, json, sys, glob, os, time
from collections import defaultdict
from evdev import InputDevice, list_devices, categorize, ecodes

# ---------- helpers ----------
def code_name(prefix: str, code: int) -> str:
    for k, v in ecodes.__dict__.items():
        if isinstance(v, int) and v == code and k.startswith(prefix):
            return k
    return f"{prefix}({code})"

def norm_axis(val: int, info, dead: float) -> float:
    if info is None:
        return 0.0
    span = info.max - info.min
    if span <= 0:
        return 0.0
    x = (val - info.min) / span * 2.0 - 1.0
    return 0.0 if abs(x) < dead else round(x, 3)

def find_default_device() -> str | None:
    # Prefer SteamDeck/OpenSD styled symlinks if present
    for p in sorted(glob.glob("/dev/input/by-id/*-OpenSD*")):
        if os.path.exists(p):
            return p
    # Else first device that has EV_KEY or EV_ABS
    for p in list_devices():
        try:
            dev = InputDevice(p)
            caps = dev.capabilities()
            if ecodes.EV_ABS in caps or ecodes.EV_KEY in caps:
                return p
        finally:
            try: dev.close()
            except: pass
    return None

def list_all_devices():
    rows = []
    for p in list_devices():
        try:
            dev = InputDevice(p)
            rows.append((p, dev.name))
        finally:
            try: dev.close()
            except: pass
    return rows

# ---------- main ----------
async def main():
    ap = argparse.ArgumentParser(
        description="Monitor ALL events from an input device (axes, buttons, hats)."
    )
    ap.add_argument("--device", default="auto",
                    help='Path like /dev/input/eventX or "auto" (default).')
    ap.add_argument("--dead-zone", type=float, default=0.05,
                    help="Dead-zone for normalized ABS values (default 0.05).")
    ap.add_argument("--rate", type=float, default=0.0,
                    help="If >0, emit ABS snapshot at this Hz (buttons print immediately).")
    ap.add_argument("--json", action="store_true",
                    help="Output JSON lines instead of human-readable text.")
    ap.add_argument("--raw", action="store_true",
                    help="Also print raw event tuples (type, code, value).")
    ap.add_argument("--list", action="store_true",
                    help="List devices and exit.")
    args = ap.parse_args()

    if args.list:
        rows = list_all_devices()
        if not rows:
            print("No /dev/input devices found.")
            return
        print("Available input devices:")
        for p, name in rows:
            print(f"  {p:<20}  {name}")
        return

    path = args.device if args.device != "auto" else find_default_device()
    if not path:
        print("[ERR] No suitable /dev/input device found.", file=sys.stderr)
        sys.exit(1)

    dev = InputDevice(path)
    print(f"* Device: {dev.name}  @ {dev.path}")
    caps = dev.capabilities(verbose=False)

    # Cache axis info and current state
    abs_infos = {}
    if ecodes.EV_ABS in caps:
        for code, *_ in caps[ecodes.EV_ABS]:
            abs_infos[code] = dev.absinfo(code)

    abs_state_raw: dict[int, int] = {}
    key_state: dict[int, int] = defaultdict(int)  # 1=down, 0=up

    # Pretty/JSON printers
    def emit_event(ev, kind, name, value, normalized=None):
        if args.json:
            obj = {
                "ts": time.time(),
                "kind": kind,           # "ABS" or "KEY" or other
                "name": name,           # e.g., "ABS_X", "BTN_SOUTH"
                "value": value,
            }
            if normalized is not None:
                obj["normalized"] = normalized
            print(json.dumps(obj), flush=True)
        else:
            if normalized is None:
                print(f"{kind:>4}  {name:<12}  val={value}", flush=True)
            else:
                print(f"{kind:>4}  {name:<12}  val={value:<6}  norm={normalized:+.3f}", flush=True)

    async def reader_loop():
        async for ev in dev.async_read_loop():
            if args.raw:
                print(f"[RAW] type={ev.type} code={ev.code} value={ev.value}", flush=True)

            if ev.type == ecodes.EV_ABS:
                abs_state_raw[ev.code] = ev.value
                nm = code_name("ABS_", ev.code)
                n = norm_axis(ev.value, abs_infos.get(ev.code), args.dead_zone)
                emit_event(ev, "ABS", nm, ev.value, n)

            elif ev.type == ecodes.EV_KEY:
                key_state[ev.code] = ev.value
                nm = code_name("BTN_", ev.code) if "BTN_" in code_name("", ev.code) else code_name("KEY_", ev.code)
                state = "DOWN" if ev.value else "UP"
                if args.json:
                    print(json.dumps({"ts": time.time(), "kind": "KEY", "name": nm, "state": state, "value": ev.value}), flush=True)
                else:
                    print(f" KEY  {nm:<12}  {state}", flush=True)

            elif ev.type == ecodes.EV_SYN:
                # sync frame; usually ignore
                pass
            else:
                # Other kinds (MSC, REL, SW, LED, etc.)
                kind = ecodes.EV[ev.type] if ev.type in ecodes.EV else f"EV({ev.type})"
                nm = code_name("", ev.code)
                emit_event(ev, kind, nm, ev.value)

    async def snapshot_loop(hz: float):
        if hz <= 0:
            return
        period = 1.0 / hz
        while True:
            # Emit one snapshot line with all current ABS (normalized)
            snap = []
            for code, info in abs_infos.items():
                raw = abs_state_raw.get(code, info.value if info else 0)
                n = norm_axis(raw, info, args.dead_zone)
                snap.append((code_name("ABS_", code), raw, n))
            if args.json:
                print(json.dumps({
                    "ts": time.time(),
                    "kind": "ABS_SNAPSHOT",
                    "axes": [{"name": nm, "raw": raw, "normalized": n} for (nm, raw, n) in snap]
                }), flush=True)
            else:
                parts = [f"{nm}=({raw},{n:+.3f})" for (nm, raw, n) in snap]
                print("ABS_SNAPSHOT  " + "  ".join(parts), flush=True)
            await asyncio.sleep(period)

    # Run
    try:
        t1 = asyncio.create_task(reader_loop())
        t2 = asyncio.create_task(snapshot_loop(args.rate)) if args.rate > 0 else None
        print("\n[INFO] Monitoring. Press Ctrl+C to quit.\n")
        await t1  # reader runs forever
        if t2: await t2
    except KeyboardInterrupt:
        pass
    finally:
        try: dev.close()
        except: pass

if __name__ == "__main__":
    asyncio.run(main())
