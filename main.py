# main.py
#!/usr/bin/env python3
import asyncio, time, sys
from config_loader import load_config
from joystick import GamepadReader
from lora import LoraLink

async def sender_task(link: LoraLink, pad: GamepadReader, period_s: float, hb_timeout_s: float):
    last_tx = (None, None)
    while True:
        await asyncio.sleep(period_s)
        # Skip TX until heartbeat is seen recently
        if time.time() - link.last_hb > hb_timeout_s:
            continue
        v, w = pad.get()
        link.write_line(f"{v},{w}")
        if (v, w) != last_tx:
            print(f"[TX] {v},{w}")
            last_tx = (v, w)

def main():
    cfg = load_config("config.json")

    # ----- Serial (LoRa) -----
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

    # ----- Gamepad -----
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

    async def run_all():
        # Optional: react to changes
        def on_axes(vw):
            v, w = vw
            # Uncomment for verbose axis updates:
            # print(f"[AX] v={v}  w={w}")
            pass

        await asyncio.gather(
            pad.read_loop(on_change=on_axes),
            sender_task(link, pad, period_s, hb_timeout_s)
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
