#!/usr/bin/env python3
import asyncio, time
from collections import deque
from evdev import ecodes

from config_loader import load_config
from joystick import GamepadReader
from lora import LoraLink
from telemetry_ws import TelemetryServer   # provides WebSocket telemetry

async def sender_task(link: LoraLink,
                      pad: GamepadReader,
                      period_s: float,
                      hb_timeout_s: float,
                      state: dict,
                      cfg):
    """Send v,w periodically (unless sleeping). Also record TX stats for telemetry."""
    last_tx = (None, None)
    while True:
        await asyncio.sleep(period_s)

        # Compute effective v/w for UI regardless of sleep (so dashboard shows sticks)
        v_raw, w_raw = pad.get()
        scale = cfg.modes.speed_plus_scale if state["speed_plus"] else cfg.modes.speed_default_scale
        v_eff = round(v_raw * scale, 3)
        w_eff = w_raw  # do not touch turning speed

        state["v_eff"] = v_eff
        state["w_eff"] = w_eff

        # In sleep mode, don't send velocity lines at all
        if state["sleep"]:
            continue

        # Skip TX if heartbeat too old
        if time.time() - link.last_hb > hb_timeout_s:
            continue

        # Transmit
        link.write_line(f"{v_eff},{w_eff}")
        now = time.time()
        state["last_tx_time"] = now
        state["tx_times"].append(now)

        if (v_eff, w_eff) != last_tx:
            print(f"[TX] {v_eff},{w_eff}  | mode: {'S+' if state['speed_plus'] else 'S-'}"
                  f"  sleep: {state['sleep']}")
            last_tx = (v_eff, w_eff)

def main():
    cfg = load_config("config.json")

    # ───────── Serial (LoRa) ─────────
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

    # ───────── Gamepad ─────────
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

    # ───────── Modes & state ─────────
    state = {
        "sleep": bool(cfg.modes.start_sleep),     # start in sleep mode
        "speed_plus": False,                      # Speed+ OFF initially
        "sleep_combo_t0": None, "sleep_combo_fired": False,
        "speed_combo_t0": None, "speed_combo_fired": False,
        "v_eff": 0.0, "w_eff": 0.0,
        "last_tx_time": 0.0,
        "tx_times": deque(maxlen=512),
    }
    HOLD = float(cfg.modes.combo_hold_sec)

    def handle_button(code, is_down):
        # Optional: print button transitions during testing
        # print(f"[BTN] {code} {'DOWN' if is_down else 'UP'}")
        pass

    def handle_axes(vw):
        # Optional: print axes during testing
        # v, w = vw
        # print(f"[AX] v={v} w={w}")
        pass

    async def mode_manager():
        """Toggle modes when combos held for HOLD seconds."""
        while True:
            await asyncio.sleep(0.05)
            now = time.time()

            # Sleep toggle: BTN_TL + BTN_TR
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

            # Speed+ toggle: BTN_TL2 + BTN_TR2
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

    # ───────── WebSocket telemetry ─────────
    ws = TelemetryServer(
        state=state,
        link=link,
        hb_timeout_s=hb_timeout_s,
        host=cfg.ws.host,
        port=cfg.ws.port
    )
    publish_period = 1.0 / float(cfg.ws.publish_hz)
    print(cfg.ws.host)
    async def run_all():
        await ws.start()  # start server
        await asyncio.gather(
            pad.read_loop(on_axes=handle_axes, on_button=handle_button),
            sender_task(link, pad, period_s, hb_timeout_s, state, cfg),
            mode_manager(),
            ws.broadcaster(period=publish_period),
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
