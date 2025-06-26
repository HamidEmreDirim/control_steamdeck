#!/usr/bin/env python3
"""
Steam Deck ➜ LoRa (tank-drive, FAULTsuz)
  • Sol çubuk Y  → hız v ∈ [-1 … +1]
  • Sağ çubuk X  → dönüş ω ∈ [-1 … +1]
Her 50 ms’de "v,ω\\r\\n" gönderir.  HB (READY) ve TIMEOUT mesajlarını dinler.
"""
import os, sys, time, asyncio, threading, serial, glob
from serial.tools import list_ports
from evdev import InputDevice, list_devices, ecodes

# ---- Ayarlar ------------------------------------------------------
BAUD         = int(sys.argv[3]) if len(sys.argv) > 3 else 9600
MAX_RATE_HZ  = 20
SEND_PERIOD  = 1.0 / MAX_RATE_HZ
DEAD_ZONE    = 0.05
HB_TIMEOUT   = 15.0                      # saniye

HB_MSG           = "READY"
TIMEOUT_MSG      = "TIMEOUT"
TIMEOUT_CLR_MSG  = "TIMEOUT_CLEAR"

RIGHT_CANDS = (ecodes.ABS_RX, ecodes.ABS_Z, ecodes.ABS_RY)

# ---- Yardımcı -----------------------------------------------------
def normalize(val, info, dz=DEAD_ZONE):
    span = info.max - info.min
    if not span: return 0.0
    n = (val - info.min) / span * 2 - 1
    return 0.0 if abs(n) < dz else round(n, 3)

def auto_serial_port():
    for pref in ("/dev/ttyUSB", "/dev/ttyACM"):
        for i in range(10):
            p = f"{pref}{i}"
            if os.path.exists(p):
                return p
    for p in list_ports.comports():
        if "USB" in p.description.upper():
            return p.device
    return None

def auto_event_device():
    # 1) OpenSD symlink’i:  /dev/input/by-id/event*-OpenSD
    for path in sorted(glob.glob("/dev/input/by-id/*-OpenSD*")):
        if os.path.exists(path):          # kırık symlink ele
            return path

    # 2) Yedek: eksen özelliklerine göre en uygun gamepad’i bul
    for p in list_devices():
        dev = InputDevice(p)
        try:
            caps = [c for c, *_ in dev.capabilities().get(ecodes.EV_ABS, [])]
            if ecodes.ABS_Y in caps and any(c in caps for c in RIGHT_CANDS):
                return p
        finally:
            dev.close()

    # Hiçbiri bulunamadı
    return None

# ---- Seri okuma thread’i -----------------------------------------
def serial_reader(ser, st):
    while st["run"]:
        try:
            line = ser.readline().decode("utf-8", "ignore").strip()
        except serial.SerialException:
            st["run"] = False
            break
        if not line:
            continue
        print(f"[RX] {line}")
        now = time.time()
        if line == HB_MSG:
            st["last_hb"] = now
        elif line == TIMEOUT_MSG:
            pass
        elif line == TIMEOUT_CLR_MSG:
            pass

# ---- Ana ---------------------------------------------------------
def main():
    # — Seri —
    port = sys.argv[2] if len(sys.argv) > 2 else auto_serial_port()
    if not port:
        print("Seri port bulunamadı"); return
    try:
        ser = serial.Serial(port, BAUD, timeout=1)
    except serial.SerialException as e:
        print(e); return

    # — Gamepad —
    dev_path = sys.argv[1] if len(sys.argv) > 1 else auto_event_device()
    if not dev_path:
        print("Gamepad bulunamadı"); ser.close(); return
    dev = InputDevice(dev_path)

    caps = [c for c, *_ in dev.capabilities().get(ecodes.EV_ABS, [])]
    w_code = next((c for c in RIGHT_CANDS if c in caps), None)
    if w_code is None:
        print("Sağ X ekseni yok"); ser.close(); return
    abs_info = {c: dev.absinfo(c) for c in caps}

    print(f"* {port} @ {BAUD}  |  Gamepad: {dev.name}")

    # — Paylaşılan durum —
    st = {
        "run": True,
        "last_hb": time.time(),
        "v": 0.0,
        "w": 0.0
    }

    rx_thread = threading.Thread(target=serial_reader, args=(ser, st))
    rx_thread.start()

    # — Coroutine’ler —
    async def collect_axes():
        last = {}
        async for ev in dev.async_read_loop():
            if ev.type != ecodes.EV_ABS:
                continue
            axis = ev.code
            val  = normalize(ev.value, abs_info[axis])
            if last.get(axis) == val:
                continue
            last[axis] = val
            if axis == ecodes.ABS_Y:
                st["v"] = val
            elif axis == w_code:
                st["w"] = val

    async def sender():
        last_tx = (None, None)
        while st["run"]:
            await asyncio.sleep(SEND_PERIOD)
            # HB denetimi
            if time.time() - st["last_hb"] > HB_TIMEOUT:
                continue
            v, w = st["v"], st["w"]
            ser.write(f"{v},{w}\r\n".encode())
            if (v, w) != last_tx:
                print(f"[TX] {v},{w}")
                last_tx = (v, w)

    async def runner():
        await asyncio.gather(collect_axes(), sender())

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        pass
    finally:
        st["run"] = False
        rx_thread.join()
        ser.close()
        print("Çıkıyorum…")

if __name__ == "__main__":
    main()
