"""设备云适配器（M5）：把标准动作映射到真实厂商 API。

契约：所有适配器实现 DeviceCloudAdapter：
  - resolve(room, device) -> device_id
  - call(device_id, op, args) -> dict
  - get_status(device_id) -> dict  （可选）

提供三个实现：
  - MockCloudAdapter     : 离线内存模拟（M5 冒烟/CI，无需真机、无需网络）
  - SmartThingsAdapter   : SmartThings REST（借鉴 SAGE 的 SmartThingsTool 思路）
  - HomeAssistantAdapter : Home Assistant REST services

真实适配器均用标准库 urllib 实现（零第三方依赖），凭证优先取构造参数，否则读环境变量。
"""
from __future__ import annotations

import difflib
import json
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from homeclaw import data_paths


class DeviceResolveError(Exception):
    """无法把 room.device 解析为真实设备标识。"""


class DeviceCloudAdapter(ABC):
    """真实设备云适配器抽象。"""

    @abstractmethod
    def resolve(self, room: str, device: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def call(self, device_id: str, op: str, args: List) -> Dict:
        raise NotImplementedError

    def get_status(self, device_id: str) -> Dict:
        raise NotImplementedError


class MockCloudAdapter(DeviceCloudAdapter):
    """离线内存模拟适配器（M5 冒烟/CI 用）。call_log 记录所有下发调用供断言。"""

    def __init__(self, devices: Optional[Dict] = None):
        self.device_registry: Dict = devices or {
            ("living_room", "light"): "st-lr-light-01",
            ("balcony", "light"): "st-bal-light-01",
            ("garage", "garage_door"): "st-garage-door-01",
        }
        self.call_log: List[Dict] = []
        self.states: Dict[str, Dict] = {}

    def resolve(self, room: str, device: str) -> str:
        key = (room, device)
        if key in self.device_registry:
            return self.device_registry[key]
        candidates = {f"{r}.{d}": did for (r, d), did in self.device_registry.items()}
        match = difflib.get_close_matches(f"{room}.{device}", list(candidates.keys()), n=1, cutoff=0.6)
        if match:
            return candidates[match[0]]
        raise DeviceResolveError(f"未找到设备: {room}.{device}")

    def call(self, device_id: str, op: str, args: List) -> Dict:
        record = {"device_id": device_id, "op": op, "args": list(args)}
        self.call_log.append(record)
        self.states.setdefault(device_id, {})
        if op in ("turn_on", "open", "play", "start"):
            self.states[device_id]["state"] = "on"
        elif op in ("turn_off", "close", "stop"):
            self.states[device_id]["state"] = "off"
        elif op.startswith("set_") and args:
            self.states[device_id][op[4:]] = args[0]
        return {"status": "ok", "dispatched": record}

    def get_status(self, device_id: str) -> Dict:
        return self.states.get(device_id, {})


SMARTTHINGS_CAPABILITY_MAP = {
    "turn_on": ("switch", "on"),
    "turn_off": ("switch", "off"),
    "set_brightness": ("switchLevel", "setLevel"),
    "set_color": ("colorControl", "setColor"),
    "set_temperature": ("thermostatCoolingSetpoint", "setCoolingSetpoint"),
    "open": ("doorControl", "open"),
    "close": ("doorControl", "close"),
    "set_volume": ("audioVolume", "setVolume"),
    "play": ("mediaPlayback", "play"),
    "pause": ("mediaPlayback", "pause"),
    "stop": ("mediaPlayback", "stop"),
}


class SmartThingsAdapter(DeviceCloudAdapter):
    """SmartThings REST 适配器。token 取参数或环境变量 SMARTTHINGS_TOKEN。"""

    BASE_URL = "https://api.smartthings.com/v1"

    def __init__(self, token: Optional[str] = None, device_map: Optional[Dict] = None,
                 device_map_file: Optional[str] = None):
        self.token = token or os.getenv("SMARTTHINGS_TOKEN")
        # device_map: (room, device) -> device_id。
        # 优先用显式传入；否则尝试从统一落盘文件 data_paths.DEVICE_MAP_FILE 加载。
        self.device_map_file = device_map_file or data_paths.DEVICE_MAP_FILE
        self.device_map: Dict = device_map if device_map is not None else self._load_device_map()

    def _load_device_map(self) -> Dict:
        """从统一落盘文件加载 device_map（JSON: {"room.device": device_id}）。"""
        if not os.path.isfile(self.device_map_file):
            return {}
        try:
            with open(self.device_map_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return {}
        out: Dict = {}
        for k, v in raw.items():
            if "." in k:
                room, device = k.split(".", 1)
                out[(room, device)] = v
        return out

    def save_device_map(self) -> str:
        """把当前 device_map 落盘到统一路径（供跨会话复用），返回文件路径。"""
        path = data_paths.runtime_path(os.path.basename(self.device_map_file))
        serializable = {f"{r}.{d}": did for (r, d), did in self.device_map.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        return path

    def _headers(self) -> Dict:
        if not self.token:
            raise RuntimeError("缺少 SmartThings token：设置参数或环境变量 SMARTTHINGS_TOKEN")
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def resolve(self, room: str, device: str) -> str:
        key = (room, device)
        if key not in self.device_map:
            raise DeviceResolveError(f"device_map 中未登记设备: {room}.{device}")
        return self.device_map[key]

    def call(self, device_id: str, op: str, args: List) -> Dict:
        import urllib.request
        if op not in SMARTTHINGS_CAPABILITY_MAP:
            return {"status": "error", "reason": "unsupported_operation", "op": op}
        capability, command = SMARTTHINGS_CAPABILITY_MAP[op]
        body = {"commands": [{"component": "main", "capability": capability,
                              "command": command, "arguments": list(args)}]}
        req = urllib.request.Request(
            f"{self.BASE_URL}/devices/{device_id}/commands",
            data=json.dumps(body).encode("utf-8"),
            headers=self._headers(), method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"status": "ok", "response": resp.read().decode("utf-8")}

    def get_status(self, device_id: str) -> Dict:
        import urllib.request
        req = urllib.request.Request(
            f"{self.BASE_URL}/devices/{device_id}/status",
            headers=self._headers(), method="GET",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))


HOMEASSISTANT_SERVICE_MAP = {
    "turn_on": ("light", "turn_on"),
    "turn_off": ("light", "turn_off"),
    "set_brightness": ("light", "turn_on"),
    "open": ("cover", "open_cover"),
    "close": ("cover", "close_cover"),
    "set_volume": ("media_player", "volume_set"),
    "play": ("media_player", "media_play"),
    "pause": ("media_player", "media_pause"),
    "stop": ("media_player", "media_stop"),
}


class HomeAssistantAdapter(DeviceCloudAdapter):
    """Home Assistant REST services 适配器。base_url/token 取参数或环境变量。"""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None,
                 entity_map: Optional[Dict] = None):
        self.base_url = (base_url or os.getenv("HOMEASSISTANT_URL", "http://localhost:8123")).rstrip("/")
        self.token = token or os.getenv("HOMEASSISTANT_TOKEN")
        self.entity_map: Dict = entity_map or {}

    def _headers(self) -> Dict:
        if not self.token:
            raise RuntimeError("缺少 Home Assistant token：设置参数或环境变量 HOMEASSISTANT_TOKEN")
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def resolve(self, room: str, device: str) -> str:
        key = (room, device)
        if key in self.entity_map:
            return self.entity_map[key]
        return f"{device}.{room}"

    def call(self, device_id: str, op: str, args: List) -> Dict:
        import json
        import urllib.request
        if op not in HOMEASSISTANT_SERVICE_MAP:
            return {"status": "error", "reason": "unsupported_operation", "op": op}
        domain, service = HOMEASSISTANT_SERVICE_MAP[op]
        payload: Dict = {"entity_id": device_id}
        if op == "set_brightness" and args:
            payload["brightness_pct"] = args[0]
        elif op == "set_volume" and args:
            payload["volume_level"] = float(args[0]) / 100.0
        req = urllib.request.Request(
            f"{self.base_url}/api/services/{domain}/{service}",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(), method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"status": "ok", "response": resp.read().decode("utf-8")}
