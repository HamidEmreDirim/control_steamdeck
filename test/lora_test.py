#!/usr/bin/env python3
# tests/lora_roundtrip.py
import os, sys, threading, time
import serial
from serial.tools import list_ports

PORT = None     # "auto" by default
BAUD = 9600

def auto_serial_port():
    # Prefer /dev/ttyUSB* then /dev/ttyACM*; fallback by description
    for pref in ("/dev/ttyUSB", "/dev/ttyACM"):
        for i in range(10):
            p = f"{pref}{i}"
            if os.path.exists(p):
                return p
    for p in list_ports.comports():
        if "USB" in p.description.upper():
            return p.device
    return None

def reader(ser):
    while True:
        try:
            line = ser.readline().decode("utf-8", "ignore").rstrip()
        except serial.SerialException:
            print("\n[!] Serial closed.")
            break
        if line:
            print(f"[RX] {line}")

def main():
    port = PORT or auto_serial_port()
    if not port:
        print("No serial port found."); return
    ser = serial.Serial(port, BAUD, timeout=1)
    print(f"*** Opened {port} @ {BAUD}\n"
          f"Type text and ENTER to send. Commands:\n"
          f"  /ping        → sends 'PING <epoch_ms>'\n"
          f"  /ready       → sends 'READY' (heartbeat)\n"
          f"Ctrl+C to exit.\n")

    th = threading.Thread(target=reader, args=(ser,), daemon=True)
    th.start()

    try:
        while True:
            try:
                msg = input()
            except EOFError:
                break
            if not msg:
                continue
            if msg == "/ping":
                msg = f"PING {int(time.time()*1000)}"
            elif msg == "/ready":
                msg = "READY"
            ser.write((msg + "\r\n").encode("utf-8"))
            print(f"[TX] {msg}")
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        print("\nBye.")

if __name__ == "__main__":
    main()
