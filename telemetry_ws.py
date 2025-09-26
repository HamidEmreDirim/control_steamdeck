# telemetry_ws.py
import asyncio, json, time
from collections import deque

class TelemetryServer:
    """
    Simple broadcast WebSocket for robot status.
    Publishes a JSON snapshot every `period` seconds to all clients.
    """
    def __init__(self, state, link, hb_timeout_s=15.0, host="0.0.0.0", port=8765):
        self.state = state
        self.link = link
        self.hb_timeout_s = float(hb_timeout_s)
        self.host = host
        self.port = int(port)
        self.clients = set()
        self._server = None

    async def handler(self, websocket, path=None):
        # Accept any path; immediately send a snapshot on connect
        self.clients.add(websocket)
        try:
            await websocket.send(self._snapshot_json())
            async for _ in websocket:
                # We don't expect incoming messages—ignore them.
                pass
        except Exception:
            pass
        finally:
            self.clients.discard(websocket)

    def _lora_connected(self) -> bool:
        return (time.time() - self.link.last_hb) < self.hb_timeout_s

    def _link_quality(self) -> int:
        """0..100. 100 when HB age <= 20% of timeout; 0 when >= timeout."""
        age = time.time() - self.link.last_hb
        if age <= self.hb_timeout_s * 0.2:
            return 100
        if age >= self.hb_timeout_s:
            return 0
        frac = (age - self.hb_timeout_s * 0.2) / (self.hb_timeout_s * 0.8)
        return max(0, min(100, int(round(100 * (1.0 - frac)))))

    def _tx_rate_hz(self) -> float:
        """Avg TX rate over last 3 s, taken from state['tx_times'] deque."""
        now = time.time()
        dq: deque = self.state.get("tx_times")
        if not dq:
            return 0.0
        # Drop entries older than 3 s
        while dq and (now - dq[0] > 3.0):
            dq.popleft()
        return round(len(dq) / 3.0, 2)

    def _snapshot(self) -> dict:
        now_ms = int(time.time() * 1000)
        v = float(self.state.get("v_eff", 0.0))
        w = float(self.state.get("w_eff", 0.0))
        d = {
            "type": "telemetry",
            "timestamp": now_ms,

            # Modes
            "sleep": bool(self.state.get("sleep", False)),
            "speed_plus": bool(self.state.get("speed_plus", False)),

            # Link
            "lora_connected": self._lora_connected(),
            "link_quality": self._link_quality(),          # 0..100
            "tx_rate_hz": self._tx_rate_hz(),             # msgs/sec (avg 3 s)
            "rx_hb_age_s": round(time.time() - self.link.last_hb, 3),

            # Motion (what you're sending)
            "v": v,
            "w": w,

            # Placeholders (no sensors yet)
            "battery_pct": 100,
            "temperature_c": 25,
            "air_quality": 95
        }
        return d

    def _snapshot_json(self) -> str:
        return json.dumps(self._snapshot(), separators=(",", ":"))

    async def broadcaster(self, period=0.5):
        """Send snapshots to all clients at a fixed cadence."""
        while True:
            if self.clients:
                msg = self._snapshot_json()
                await asyncio.gather(
                    *[self._safe_send(ws, msg) for ws in list(self.clients)],
                    return_exceptions=True
                )
            await asyncio.sleep(period)

    async def _safe_send(self, ws, msg: str):
        try:
            await ws.send(msg)
        except Exception:
            try:
                await ws.close()
            except Exception:
                pass
            self.clients.discard(ws)

    async def start(self):
        import websockets
        self._server = await websockets.serve(self.handler, self.host, self.port)
        print(f"* WebSocket up: ws://{self.host}:{self.port}  (subscribers: {len(self.clients)})")
