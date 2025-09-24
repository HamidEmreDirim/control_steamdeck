# config_loader.py
from dataclasses import dataclass
from typing import List, Optional
import json, os

@dataclass
class SerialCfg:
    port: str = "auto"       # "auto" or "/dev/ttyUSB0"
    baud: int = 9600

@dataclass
class JoystickCfg:
    device: str = "auto"     # "auto" or "/dev/input/eventX"
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
class Config:
    serial: SerialCfg
    joystick: JoystickCfg
    tx: TxCfg
    protocol: ProtocolCfg

def _deep_update(d, u):
    for k, v in u.items():
        if isinstance(v, dict):
            d[k] = _deep_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d

def load_config(path: str = "config.json") -> Config:
    # Defaults:
    base = {
        "serial": {"port": "auto", "baud": 9600},
        "joystick": {
            "device": "auto",
            "dead_zone": 0.05,
            "invert_v": False,
            "invert_w": False,
            "right_axis_candidates": ["ABS_RX", "ABS_Z", "ABS_RY"]
        },
        "tx": {"max_rate_hz": 10.0, "hb_timeout_sec": 15.0},
        "protocol": {"hb_msg": "READY", "timeout_msg": "TIMEOUT", "timeout_clear_msg": "TIMEOUT_CLEAR"}
    }

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            user = json.load(f)
        base = _deep_update(base, user)

    serial = SerialCfg(**base["serial"])
    joystick = JoystickCfg(**base["joystick"])
    tx = TxCfg(**base["tx"])
    protocol = ProtocolCfg(**base["protocol"])
    return Config(serial=serial, joystick=joystick, tx=tx, protocol=protocol)
