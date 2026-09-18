"""从 home_status 字典构建 device.py 对象树（M2）。

home_status 结构（HomeBench 风格）：
    {
      "living_room": {
         "room_name": "living_room",
         "light": {"state": "on", "attributes": {...}},
         ...
      },
      "VacuumRobot": {"state": "...", "attributes": {...}},   # 无 device 层的特例
      ...
    }

构建结果：
    {room: {device_name: DeviceObj}}
其中 DeviceObj 来自 devices.device_map，并用 initialize() 载入初始 state/attributes。
未在 device_map 中的设备类型将被跳过（并记录到 unsupported）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from homeclaw.devices.device import device_map


@dataclass
class BuildReport:
    """构建过程报告，便于排查数据集里 device.py 未覆盖的设备类型。"""

    unsupported: List[str] = field(default_factory=list)  # 未支持的设备类型名


def _resolve_type(device_name: str, dev_val: Dict) -> str:
    """决定用哪个 device_map 类型键实例化。

    优先取 dev_val["device_type"]（场景层 to_home_status 会带上，支持 SAGE 同类多实例
    的自定义 slot 名，如 nightstand_light/fireplace_light 均映射到 light）；
    缺失时回退到设备名本身（HomeBench 数据集设备名==类型名，行为不变）。
    """
    dt = dev_val.get("device_type")
    return dt if dt in device_map else device_name


def _instantiate(type_key: str, dev_val: Dict):
    """按 type_key（device_map 键）实例化并初始化。"""
    cls = device_map[type_key]
    state = dev_val.get("state", None)
    try:
        obj = cls(state) if state is not None else cls()
    except TypeError:
        obj = cls()
    # 用数据集提供的 state/attributes 覆盖默认值
    if "attributes" in dev_val:
        obj.initialize(state if state is not None else getattr(obj, "state", None),
                       dev_val.get("attributes"))
    return obj


def build_home(home_status: Dict) -> "tuple[Dict[str, Dict[str, object]], BuildReport]":
    """构建 {room: {device: obj}} 对象树，返回 (home, report)。"""
    home: Dict[str, Dict[str, object]] = {}
    report = BuildReport()

    for room, room_val in home_status.items():
        home[room] = {}
        # 无 device 层的特例：room_val 直接是一个设备（有 state+attributes）
        if isinstance(room_val, dict) and "attributes" in room_val and "state" in room_val \
                and not _looks_like_room(room_val):
            dev_name = room.lower()
            type_key = _resolve_type(dev_name, room_val)
            if type_key in device_map:
                home[room][dev_name] = _instantiate(type_key, room_val)
            else:
                report.unsupported.append(dev_name)
            continue

        for device_name, dev_val in room_val.items():
            if device_name == "room_name":
                continue
            if not isinstance(dev_val, dict):
                continue
            type_key = _resolve_type(device_name, dev_val)
            if type_key in device_map:
                home[room][device_name] = _instantiate(type_key, dev_val)
            else:
                report.unsupported.append(device_name)

    return home, report


def _looks_like_room(val: Dict) -> bool:
    """判断一个 dict 是否是"房间"（其值里含嵌套的设备 dict）。"""
    for k, v in val.items():
        if k in ("state", "attributes", "room_name"):
            continue
        if isinstance(v, dict) and ("attributes" in v or "state" in v):
            return True
    return False


def snapshot_home(home: Dict[str, Dict[str, object]]) -> Dict:
    """把对象树导出为可断言的纯字典状态（供 SAGE 五维评测断言）。"""
    out: Dict = {}
    for room, devices in home.items():
        out[room] = {}
        for name, obj in devices.items():
            out[room][name] = obj.get_status()
    return out
