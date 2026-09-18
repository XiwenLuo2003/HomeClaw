"""SAGE 抽象仿真场景（P2）：把 SAGE 的 SmartThings 真实设备抽象成 room.device 拓扑。

背景：SAGE 数据集用的是真实 SmartThings 设备（UUID 标识、capability/component 结构、
MongoDB 快照），与 HomeBench 的抽象 room.device.op() 完全不同。为了让两套数据集共用
同一个 SimulateExecutor、同一套动作文本格式、同一个 3D 可视化，这里仿照 HomeBench 场景
风格，为 SAGE 单独建一套抽象场景。

【本版目标：从"代表性子集"升级为"覆盖 SAGE 官方 testcases 全量设备/房间"】

依据 SAGE 官方 sage/testing/testcases.py 顶部的设备声明与全部 50+ 用例的实景引用，
SAGE 真实设备体系（UUID）全量如下，并给出到抽象 room.device 的完整映射：

  SAGE 真实设备（testcases.py UUID / 组件）          -> 抽象 room.device            实景锚点(anchor)
  ---------------------------------------------------------------------------------------------
  nightstand_light  (床头夜灯)                        -> bedroom.nightstand_light     by the bed / nightstand
  fireplace_light   (壁炉灯)                          -> living_room.fireplace_light  by the fireplace
  tv_light          (电视旁灯)                        -> living_room.tv_light         by the tv / by the light
  dining_table_light(餐桌灯)                          -> dining_room.dining_table_light  over the dining table
  main tv           (主电视, credenza 边)             -> living_room.tv               by the credenza
  frame tv          (画框电视, plant 边)              -> living_room.frame_tv         by the plant
  fridge            (冰箱, 含 fridge/freezer 温区)    -> kitchen.fridge               —
  dishwasher        (洗碗机)                          -> kitchen.dishwasher           —

SAGE 用例只涉及以上 8 台真实设备（4 灯 + 2 电视 + 冰箱 + 洗碗机），分布在
bedroom / living_room / dining_room / kitchen 四个房间。本场景**完整覆盖**这 8 台设备，
不再是"代表性子集"。设备类型均已在 device.py 的 device_map 中补齐（P2）。

注：bedroom 另放置 1 台 `air_conditioner`，它**不属于** SAGE 官方 8 台用例设备，
仅用于 3D 可视化演示多设备类型（覆盖度自检只校验 SAGE_REQUIRED_DEVICES ⊆ 场景设备，
不受这台演示 AC 影响）。因此场景实际含 9 台设备 = 8 台 SAGE 设备 + 1 台演示 AC。

与 HomeBench 场景的关键差异——**实景空间锚点（anchors）**：SAGE 的 device_resolution
维度大量依赖 "by the credenza / by the plant / by the fireplace / by the bed" 这类
自然语言空间锚点来定位具体设备（如两台 TV 靠 credenza / plant 区分）。这里把这些锚点
写进 DeviceSlot.anchors，既供 3D 可视化打标签，也供后续用例做 anchor 消歧断言。

坐标为演示用的合理布局；build_sage_scene() 确定性构建，供五维用例 + 3D 可视化复用。
"""
from __future__ import annotations

from typing import Dict, List, Set

from homeclaw.scene.schema import Scene, Room, DeviceSlot


# SAGE 抽象场景的房间网格坐标
_ROOM_W, _ROOM_D, _ROOM_H = 4.0, 3.0, 2.8

# SAGE 官方 testcases 涉及的全量真实设备（抽象名 -> 所在房间），用于覆盖度自检。
# 键为抽象 room.device 全名，值为该设备在 SAGE 里对应的真实设备语义标签。
SAGE_REQUIRED_DEVICES: Dict[str, str] = {
    "bedroom.nightstand_light": "nightstand_light",
    "living_room.fireplace_light": "fireplace_light",
    "living_room.tv_light": "tv_light",
    "dining_room.dining_table_light": "dining_table_light",
    "living_room.tv": "main tv (credenza)",
    "living_room.frame_tv": "frame tv (plant)",
    "kitchen.fridge": "fridge (fridge+freezer)",
    "kitchen.dishwasher": "dishwasher",
}


def build_sage_scene() -> Scene:
    """构建 SAGE 抽象场景（确定性），完整覆盖 SAGE testcases 的 8 台真实设备。"""
    scene = Scene(name="SAGE-Home", source="sage")

    # --- 卧室（bedroom）：床头夜灯 ---
    bedroom = Room(name="bedroom", pos=(0.0, 0.0, 0.0), size=(_ROOM_W, _ROOM_D, _ROOM_H))
    bedroom.add(DeviceSlot(
        device_type="light", name="nightstand_light", state="off",
        pos=(0.6, 0.0, 0.6), model="nightstand_lamp",
        anchors=["by the bed", "nightstand", "bedside", "bedroom light"],
        device_uuid="22e11820-64fa-4bed-ad8f-f98ef66de298",
        image="sage/images/22e11820-64fa-4bed-ad8f-f98ef66de298.jpg",
    ))
    # 演示用设备：不属于 SAGE 官方 8 台用例设备，仅用于 3D 可视化展示多设备类型
    bedroom.add(DeviceSlot(device_type="air_conditioner", name="air_conditioner",
                           state="off", pos=(3.2, 0.0, 0.5)))
    scene.add_room(bedroom)

    # --- 客厅（living_room）：壁炉灯 + 电视旁灯 + 主TV(credenza) + frame TV(plant) ---
    living = Room(name="living_room", pos=(4.3, 0.0, 0.0), size=(_ROOM_W, _ROOM_D, _ROOM_H))
    living.add(DeviceSlot(
        device_type="light", name="fireplace_light", state="off",
        pos=(1.8, 0.0, 0.5), model="fireplace_lamp",
        anchors=["by the fireplace", "fire place", "fireplace"],
        device_uuid="571f0327-6507-4674-b9cf-fe68f7d9522d",
        image="sage/images/571f0327-6507-4674-b9cf-fe68f7d9522d.jpg",
    ))
    living.add(DeviceSlot(
        device_type="light", name="tv_light", state="off",
        pos=(3.0, 0.0, 0.5), model="tv_backlight",
        anchors=["by the tv", "by the light", "tv light"],
        device_uuid="363f714d-e4fe-4052-a78c-f8c97542e709",
        image="sage/images/363f714d-e4fe-4052-a78c-f8c97542e709.jpg",
    ))
    living.add(DeviceSlot(
        device_type="tv", name="tv", state="off",
        pos=(2.0, 0.6, 0.2), model="main_tv",
        anchors=["by the credenza", "credenza", "main tv"],
        device_uuid="8e20883f-c444-4edf-86bf-64e74c1d70e2",
        image="sage/images/8e20883f-c444-4edf-86bf-64e74c1d70e2.jpg",
    ))
    living.add(DeviceSlot(
        device_type="frame_tv", name="frame_tv", state="off",
        pos=(3.2, 0.6, 0.2), model="frame_tv",
        anchors=["by the plant", "plant", "frame tv", "picture tv"],
        device_uuid="415228e4-456c-44b1-8602-70f98c67fba8",
        image="sage/images/415228e4-456c-44b1-8602-70f98c67fba8.jpg",
    ))
    scene.add_room(living)

    # --- 餐厅（dining_room）：餐桌灯 ---
    dining = Room(name="dining_room", pos=(8.6, 0.0, 0.0), size=(_ROOM_W, _ROOM_D, _ROOM_H))
    dining.add(DeviceSlot(
        device_type="light", name="dining_table_light", state="off",
        pos=(1.5, 0.9, 0.5), model="dining_table_lamp",
        anchors=["over the dining table", "dining table", "dining room"],
        device_uuid="c4b4a179-6f75-48ed-a6b3-95080be6afc6",
        image="sage/images/c4b4a179-6f75-48ed-a6b3-95080be6afc6.jpg",
    ))
    scene.add_room(dining)

    # --- 厨房（kitchen）：冰箱（含 freezer 温区）+ 洗碗机 ---
    kitchen = Room(name="kitchen", pos=(0.0, 0.0, 3.3), size=(_ROOM_W, _ROOM_D, _ROOM_H))
    kitchen.add(DeviceSlot(
        device_type="fridge", name="fridge", state="on",
        pos=(3.4, 0.0, 0.6), anchors=["fridge", "refrigerator", "freezer"],
    ))
    kitchen.add(DeviceSlot(
        device_type="dishwasher", name="dishwasher", state="off",
        pos=(3.4, 0.0, 2.0), anchors=["dishwasher"],
    ))
    scene.add_room(kitchen)

    return scene


# ---------------------------------------------------------------------------- #
# 覆盖度自检：确认场景确实覆盖了 SAGE testcases 全量设备（而非子集）
# ---------------------------------------------------------------------------- #
def scene_device_fullnames(scene: Scene) -> Set[str]:
    """返回场景中所有存在设备的 'room.device' 全名集合。"""
    names: Set[str] = set()
    for room in scene.rooms:
        for slot in room.existing_slots():
            names.add(f"{room.name}.{slot.slot_name()}")
    return names


def coverage_report() -> Dict[str, object]:
    """核对 build_sage_scene() 是否覆盖 SAGE_REQUIRED_DEVICES 全量。

    返回 {"covered": [...], "missing": [...], "full": bool}，
    供冒烟测试断言"SAGE 场景为全量而非子集"。
    """
    present = scene_device_fullnames(build_sage_scene())
    required = set(SAGE_REQUIRED_DEVICES.keys())
    covered = sorted(required & present)
    missing = sorted(required - present)
    return {"covered": covered, "missing": missing, "full": len(missing) == 0}


def assert_full_coverage() -> None:
    """若未覆盖 SAGE 全量设备则抛错（供 CI/冒烟使用）。"""
    rep = coverage_report()
    if not rep["full"]:
        raise AssertionError(
            "SAGE 场景未覆盖官方 testcases 全量设备，缺失：%s" % rep["missing"]
        )
