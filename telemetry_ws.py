#!/usr/bin/env python3
"""
telemetry_ws.py

A lightweight WebSocket broadcast server for robot telemetry.
- Runs on asyncio (non-blocking).
- Periodically publishes JSON snapshots with robot state, link quality,
  and placeholder sensor values.
- Designed to be consumed by UI dashboards or monitoring tools.
"""

import asyncio, json, time
from collections import deque


class TelemetryServer:
    """
    Telemetry WebSocket Server

    Responsibilities:
      • Accept connections from WebSocket clients.
      • Maintain a set of connected clients.
      • Periodically broadcast a telemetry JSON snapshot to all clients.
      • Encode robot state + link health + placeholder sensor data.
    """

    def __init__(self, state, link, hb_timeout_s=15.0, host="0.0.0.0", port=8765):
        """
        Args:
            state (dict): Shared dictionary with robot state variables
                          e.g., {"v_eff": 0.0, "w_eff": 0.0, "tx_times": deque([...])}.
            link  (object): Link-like object with .last_hb attribute (heartbeat timestamp).
            hb_timeout_s (float): Max seconds to consider link "alive".
            host (str): Interface to bind the WebSocket server (default: all interfaces).
            port (int): TCP port to bind.
        """
        self.state = state
        self.link = link
        self.hb_timeout_s = float(hb_timeout_s)
        self.host = host
        self.port = int(port)
        self.clients = set()     # Active WebSocket connections
        self._server = None      # WebSocket server object (from websockets.serve)

    # ───────────────────────────── Handlers ─────────────────────────────

    async def handler(self, websocket, path=None):
        """
        Handle a new WebSocket client connection.
        - Add to client set.
        - Immediately send a snapshot.
        - Then, just keep the connection alive (ignore client messages).
        """
        self.clients.add(websocket)
        print("New WebSocket client connected")

        try:
            # Send initial snapshot right after connection
            await websocket.send(self._snapshot_json())

            # Consume incoming messages (ignored, since telemetry is one-way)
            async for _ in websocket:
                pass

        except Exception:
            # Connection dropped / error
            pass

        finally:
            # Clean up disconnected client
            self.clients.discard(websocket)
            print("WebSocket client disconnected")

    # ───────────────────────────── Link Health ─────────────────────────────

    def _lora_connected(self) -> bool:
        """True if last heartbeat is within timeout."""
        return (time.time() - self.link.last_hb) < self.hb_timeout_s

    def _link_quality(self) -> int:
        """
        Returns a % quality estimate (0–100).
          • 100 = heartbeat is very fresh (≤ 20% of timeout).
          • 0   = heartbeat older than timeout.
          • Linear interpolation in between.
        """
        age = time.time() - self.link.last_hb
        if age <= self.hb_timeout_s * 0.2:
            return 100
        if age >= self.hb_timeout_s:
            return 0

        # Normalize linearly between [20%..100%] of timeout
        frac = (age - self.hb_timeout_s * 0.2) / (self.hb_timeout_s * 0.8)
        return max(0, min(100, int(round(100 * (1.0 - frac)))))

    def _tx_rate_hz(self) -> float:
        """
        Average TX message rate (Hz) over last 3 seconds.
        Relies on `state['tx_times']` being a deque of timestamps.
        """
        now = time.time()
        dq: deque = self.state.get("tx_times")
        if not dq:
            return 0.0

        # Drop entries older than 3s
        while dq and (now - dq[0] > 3.0):
            dq.popleft()

        return round(len(dq) / 3.0, 2)

    # ───────────────────────────── Snapshot Generation ─────────────────────────────

    def _snapshot(self) -> dict:
        """Build the current telemetry snapshot as a dict."""
        now_ms = int(time.time() * 1000)
        v = float(self.state.get("v_eff", 0.0))   # Effective forward velocity
        w = float(self.state.get("w_eff", 0.0))   # Effective angular velocity

        return {
            "type": "telemetry",
            "timestamp": now_ms,

            # Robot modes
            "sleep": bool(self.state.get("sleep", False)),
            "speed_plus": bool(self.state.get("speed_plus", False)),

            # Radio link
            "lora_connected": self._lora_connected(),
            "link_quality": self._link_quality(),
            "tx_rate_hz": self._tx_rate_hz(),
            "rx_hb_age_s": round(time.time() - self.link.last_hb, 3),

            # Motion commands
            "v": v,
            "w": w,

            # Placeholder sensors (real ones can be added later)
            "battery_pct": 100,
            "temperature_c": 25,
            "air_quality": 95
        }

    def _snapshot_json(self) -> str:
        """Return snapshot encoded as compact JSON string."""
        return json.dumps(self._snapshot(), separators=(",", ":"))

    # ───────────────────────────── Broadcast Loop ─────────────────────────────

    async def broadcaster(self, period=0.5):
        """
        Periodically send snapshots to all connected clients.
        Args:
            period (float): Interval in seconds between snapshots.
        """
        while True:
            if self.clients:
                msg = self._snapshot_json()
                await asyncio.gather(
                    *[self._safe_send(ws, msg) for ws in list(self.clients)],
                    return_exceptions=True
                )
            await asyncio.sleep(period)

    async def _safe_send(self, ws, msg: str):
        """
        Send a message to a single client.
        If sending fails, close and remove client from active set.
        """
        try:
            await ws.send(msg)
        except Exception:
            try:
                await ws.close()
            except Exception:
                pass
            self.clients.discard(ws)

    # ───────────────────────────── Lifecycle ─────────────────────────────

    async def start(self):
        """
        Start the WebSocket server.
        Call this inside an asyncio event loop.
        """
        import websockets
        print(f"* WebSocket server listening at ws://{self.host}:{self.port}")
        self._server = await websockets.serve(self.handler, self.host, self.port)
