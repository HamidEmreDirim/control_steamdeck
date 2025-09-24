# lora.py
import os, time, threading
import serial
from serial.tools import list_ports

class LoraLink:
    """
    Handles serial open, background RX, heartbeat tracking, and line sends.
    """
    def __init__(self, port: str, baud: int, hb_msg="READY",
                 timeout_msg="TIMEOUT", timeout_clear_msg="TIMEOUT_CLEAR"):
        self.port = port
        self.baud = baud
        self.hb_msg = hb_msg
        self.timeout_msg = timeout_msg
        self.timeout_clear_msg = timeout_clear_msg

        self.ser: serial.Serial | None = None
        self.run = False
        self.last_hb = time.time()
        self._rx_thread: threading.Thread | None = None

    # ---------- Discovery ----------
    @staticmethod
    def auto_serial_port() -> str | None:
        for pref in ("/dev/ttyUSB", "/dev/ttyACM"):
            for i in range(10):
                p = f"{pref}{i}"
                if os.path.exists(p):
                    return p
        for p in list_ports.comports():
            if "USB" in p.description.upper():
                return p.device
        return None

    # ---------- Open/close ----------
    def open(self):
        self.ser = serial.Serial(self.port, self.baud, timeout=1)

    def start_reader(self, on_line=None):
        if self.ser is None:
            raise RuntimeError("Serial not open. Call open() first.")
        self.run = True
        def _reader():
            while self.run:
                try:
                    line = self.ser.readline().decode("utf-8", "ignore").strip()
                except serial.SerialException:
                    self.run = False
                    break
                if not line:
                    continue
                # Heartbeat book-keeping
                if line == self.hb_msg:
                    self.last_hb = time.time()
                elif line == self.timeout_clear_msg:
                    pass
                elif line == self.timeout_msg:
                    pass
                if on_line:
                    on_line(line)
        self._rx_thread = threading.Thread(target=_reader, daemon=True)
        self._rx_thread.start()

    def write_line(self, line: str):
        if self.ser is None:
            raise RuntimeError("Serial not open.")
        # Ensure CRLF for the peer if needed
        if not line.endswith("\r\n"):
            line += "\r\n"
        self.ser.write(line.encode("utf-8"))

    def close(self):
        self.run = False
        if self._rx_thread is not None:
            self._rx_thread.join(timeout=1.5)
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
