"""HomeBench 仿真场景（P2）：仿照 HomeBench visual_home/visualHome.py 的房间-设备布局。

迁移要点：
  - 保留 visualHome 的 12 个房间与"每间该有哪些设备/哪些是干扰(unexist)设备"约束；
  - 用 scene.schema 的 Scene/Room/DeviceSlot 表达，并补齐 3D 坐标（楼层网格布局）；
  - 支持确定性构建（默认）与随机构建（seed），确定性版便于 3D 可视化与复现。

房间-设备候选约束对齐 HomeBench 原始 *CandiateRoom 列表。
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

from homeclaw.scene.schema import Scene, Room, DeviceSlot


# HomeBench 12 房间（原 AllCandiateRoom，下划线命名以对齐 SimulateExecutor）
ALL_ROOMS = [
    "master_bedroom", "guest_bedroom", "living_room", "dining_room", "study_room",
    "kitchen", "bathroom", "foyer", "corridor", "balcony", "garage", "store_room",
]

# 房间 -> 该房间可出现的设备类型（对齐 HomeBench *CandiateRoom 约束）
ROOM_DEVICES: Dict[str, List[str]] = {
    "master_bedroom": ["light", "air_conditioner", "curtain", "air_purifiers", "humidifier", "aromatherapy", "trash", "media_player", "bed"],
    "guest_bedroom": ["light", "heating", "fan", "curtain", "air_purifiers", "dehumidifiers", "aromatherapy", "trash", "bed"],
    "living_room": ["light", "air_conditioner", "curtain", "air_purifiers", "humidifier", "aromatherapy", "media_player", "tv"],
    "dining_room": ["light", "fan", "blinds", "air_purifiers", "dehumidifiers", "trash"],
    "study_room": ["light", "air_conditioner", "curtain", "air_purifiers", "humidifier", "trash", "bed"],
    "kitchen": ["light", "fan", "blinds", "trash", "water_heater", "fridge", "dishwasher"],
    "bathroom": ["light", "blinds", "heating", "trash", "water_heater"],
    "foyer": ["light", "aromatherapy", "switch"],
    "corridor": ["light", "aromatherapy"],
    "balcony": ["light", "curtain", "aromatherapy", "trash", "media_player"],
    "garage": ["light", "garage_door", "trash", "air_purifiers", "blinds", "switch"],
    "store_room": ["light", "air_purifiers", "humidifier", "dehumidifiers"],
}

# 每间房必有的核心设备（其余为可选/干扰）
CORE_DEVICES: Dict[str, List[str]] = {
    "master_bedroom": ["light", "air_conditioner"],
    "guest_bedroom": ["light", "heating"],
    "living_room": ["light", "air_conditioner", "tv"],
    "dining_room": ["light"],
    "study_room": ["light", "air_conditioner"],
    "kitchen": ["light", "fridge"],
    "bathroom": ["light"],
    "foyer": ["light"],
    "corridor": ["light"],
    "balcony": ["light"],
    "garage": ["light", "garage_door"],
    "store_room": ["light"],
}

# 楼层网格布局（4 列 x 3 行），用于给房间分配 3D 坐标
_GRID_COLS = 4
_ROOM_W, _ROOM_D, _ROOM_H = 4.0, 3.0, 2.8


def _room_pos(index: int):
    col = index % _GRID_COLS
    row = index // _GRID_COLS
    return (col * (_ROOM_W + 0.3), 0.0, row * (_ROOM_D + 0.3))


def _device_pos(slot_index: int):
    """在房间内沿墙均匀摆放设备的简单局部坐标。"""
    x = 0.5 + (slot_index % 3) * 1.2
    z = 0.5 + (slot_index // 3) * 1.0
    return (x, 0.0, z)


def build_homebench_scene(seed: Optional[int] = 42, randomize: bool = False) -> Scene:
    """构建 HomeBench 12 房间场景。

    randomize=False（默认）：确定性——每间放 CORE 设备 + 其余候选设备（exists=True），
        并为每个可选设备补一个 exists=False 的干扰项（对齐 HomeBench unexist_device）。
    randomize=True：按 seed 随机决定可选设备是否存在（更接近原 visualHome 行为）。
    """
    rng = random.Random(seed)
    scene = Scene(name="HomeBench-Home", source="homebench")
    for r_idx, room_name in enumerate(ALL_ROOMS):
        room = Room(name=room_name, pos=_room_pos(r_idx), size=(_ROOM_W, _ROOM_D, _ROOM_H))
        core = set(CORE_DEVICES.get(room_name, ["light"]))
        candidates = ROOM_DEVICES.get(room_name, ["light"])
        slot_i = 0
        for dev in candidates:
            is_core = dev in core
            if is_core:
                exists = True
            elif randomize:
                exists = rng.random() > 0.5
            else:
                exists = True
            room.add(DeviceSlot(device_type=dev, exists=exists, pos=_device_pos(slot_i)))
            slot_i += 1
            # 非核心设备补一个干扰(unexist)副本（确定性模式下用于幻觉测试）
            if not is_core and not randomize:
                room.add(DeviceSlot(device_type=dev, name=f"{dev}_ghost", exists=False, pos=_device_pos(slot_i)))
                slot_i += 1
        scene.add_room(room)
    return scene
