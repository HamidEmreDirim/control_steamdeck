# config_loader.py
from dataclasses import dataclass
from typing import List
import json, os

# ─────────────────── Dataclasses ───────────────────

@dataclass
class SerialCfg:
    port: str = "auto"     # e.g. "/dev/ttyUSB0" or "auto"
    baud: int = 9600

@dataclass
class JoystickCfg:
    device: str = "auto"   # e.g. "/dev/input/event7" or "auto"
    dead_zone: float = 0.05
    invert_v: bool = False
    invert_w: bool = False
    right_axis_candidates: List[str] = None
    def __post_init__(self):
        if self.right_axis_candidates is None:
            self.right_axis_candidates = ["ABS_RX", "ABS_Z", "ABS_RY"]

@dataclass
class TxCfg:
    max_rate_hz: float = 10.0
    hb_timeout_sec: float = 15.0

@dataclass
class ProtocolCfg:
    hb_msg: str = "READY"
    timeout_msg: str = "TIMEOUT"
    timeout_clear_msg: str = "TIMEOUT_CLEAR"

@dataclass
class ModeCfg:
    start_sleep: bool = True           # start in sleep mode
    combo_hold_sec: float = 3.0        # hold time for combo toggles
    speed_default_scale: float = 0.70  # v scale when Speed+ is OFF
    speed_plus_scale: float = 1.00     # v scale when Speed+ is ON

@dataclass
class WSCfg:
    host: str = "0.0.0.0"
    port: int = 8765
    publish_hz: float = 2.0            # broadcast rate to UI

@dataclass
class Config:
    serial: SerialCfg
    joystick: JoystickCfg
    tx: TxCfg
    protocol: ProtocolCfg
    modes: ModeCfg
    ws: WSCfg

# ─────────────────── Utils ───────────────────

def _deep_update(d, u):
    """Recursively update dict d with dict u (like a shallow merge with nested dicts)."""
    for k, v in u.items():
        if isinstance(v, dict):
            d[k] = _deep_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d

# ─────────────────── Loader ───────────────────

def load_config(path: str = "config.json") -> Config:
    defaults = {
        "serial": {"port": "auto", "baud": 9600},
        "joystick": {
            "device": "auto",
            "dead_zone": 0.05,
            "invert_v": False,
            "invert_w": False,
            "right_axis_candidates": ["ABS_RX", "ABS_Z", "ABS_RY"]
        },
        "tx": {"max_rate_hz": 10.0, "hb_timeout_sec": 15.0},
        "protocol": {
            "hb_msg": "READY",
            "timeout_msg": "TIMEOUT",
            "timeout_clear_msg": "TIMEOUT_CLEAR"
        },
        "modes": {
            "start_sleep": True,
            "combo_hold_sec": 3.0,
            "speed_default_scale": 0.70,
            "speed_plus_scale": 1.00
        },
        "ws": {"host": "0.0.0.0", "port": 8765, "publish_hz": 2.0}
    }

    cfg_dict = defaults
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        cfg_dict = _deep_update(cfg_dict, user_cfg)

    return Config(
        serial=SerialCfg(**cfg_dict["serial"]),
        joystick=JoystickCfg(**cfg_dict["joystick"]),
        tx=TxCfg(**cfg_dict["tx"]),
        protocol=ProtocolCfg(**cfg_dict["protocol"]),
        modes=ModeCfg(**cfg_dict["modes"]),
        ws=WSCfg(**cfg_dict["ws"]),
    )
