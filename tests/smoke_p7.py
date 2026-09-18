"""P7 多模态数据层冒烟测试：3D 可视化的数据契约回归保护（纯离线、零外部依赖）。

运行：
    cd HomeClaw
    python3 tests/smoke_p7.py

覆盖（对齐 P1~P6「把契约变机器断言」的风格）：
  [P7-A] 数据契约   ：Scene.to_json 的每个设备节点含 pos/yaw/live_state/anchors/
                      image/device_uuid 六个 3D/多模态键（前端渲染依赖）。
  [P7-B] SAGE 多模态 ：sage_scene 恰好 6 台**带图**设备（4 灯 + 2 电视）携带 image/device_uuid；
                      每个 image 都能在 DATA_DIR 下找到对应 UUID.jpg；文件名 == device_uuid；
                      fridge/dishwasher 无 image（家中唯一、无需 CLIP 消歧）。
  [P7-C] 降级隔离   ：HomeBench 场景所有设备 image/device_uuid 均为 None
                      （HomeBench 无实景照片消歧能力——两套场景差异的机器化证据）。
  [P7-D] 实时叠加   ：执行动作后 to_json(live_status=...) 对应设备 live_state 正确翻转。
  [P7-E] 属性契约   ：live_attributes 以 {value:...} 嵌套结构下发（前端 num() 须按
                      .value 取数——bug#1「亮度/温度/音量 badge 全失效」的防回归护栏）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from homeclaw import data_paths  # noqa: E402
from homeclaw.executor import SimulateExecutor  # noqa: E402
from homeclaw.scene import build_homebench_scene, build_sage_scene  # noqa: E402


# SAGE 中需要 CLIP 图文消歧、因而携带实景照片的设备（4 灯 + 2 电视）。
# fridge / dishwasher 家中唯一，直接点名即可，无需实景消歧 -> 无 image。
_EXPECTED_IMAGE_DEVICES = 6
_REQUIRED_KEYS = {"pos", "yaw", "live_state", "anchors", "image", "device_uuid"}


def _assert(cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    if not cond:
        raise AssertionError(msg)


def _iter_devices(scene_json):
    for room in scene_json["rooms"]:
        for dev in room["devices"]:
            yield dev


# ============================================================================ #
# P7-A 数据契约：设备节点含 3D/多模态全部键
# ============================================================================ #
def test_p7a_contract():
    print("[P7-A] 3D 数据契约：设备节点键完整")
    data = build_sage_scene().to_json()
    for dev in _iter_devices(data):
        missing = _REQUIRED_KEYS - set(dev.keys())
        _assert(not missing, f"设备 {dev['name']} 含全部 3D/多模态键（缺: {missing}）")


# ============================================================================ #
# P7-B SAGE 多模态：恰好 6 台带图设备 + 文件真实存在 + 文件名==UUID
# ============================================================================ #
def test_p7b_sage_multimodal():
    print("[P7-B] SAGE 多模态：6 台带图，image 文件真实存在")
    data = build_sage_scene().to_json()

    imaged = [d for d in _iter_devices(data) if d["image"]]
    _assert(len(imaged) == _EXPECTED_IMAGE_DEVICES,
            f"恰好 {_EXPECTED_IMAGE_DEVICES} 台设备带 image（实得 {len(imaged)}）")

    for dev in imaged:
        # image 相对路径基于 DATA_DIR 解析，须真实存在
        abs_path = os.path.join(data_paths.DATA_DIR, dev["image"])
        _assert(os.path.isfile(abs_path),
                f"{dev['name']} 的 image 文件存在: {dev['image']}")
        # 文件名（去扩展名）== device_uuid，对齐 SAGE「文件名即 UUID」机制
        fname_uuid = os.path.splitext(os.path.basename(dev["image"]))[0]
        _assert(dev["device_uuid"] and fname_uuid == dev["device_uuid"],
                f"{dev['name']} 文件名==device_uuid（{fname_uuid}）")

    # 无图设备（fridge/dishwasher）确应无 image/uuid
    fridge = next(d for d in _iter_devices(data) if d["name"] == "fridge")
    dishwasher = next(d for d in _iter_devices(data) if d["name"] == "dishwasher")
    _assert(fridge["image"] is None and dishwasher["image"] is None,
            "fridge/dishwasher 无 image（家中唯一，无需 CLIP 消歧）")


# ============================================================================ #
# P7-C 降级隔离：HomeBench 无多模态
# ============================================================================ #
def test_p7c_homebench_no_multimodal():
    print("[P7-C] 降级隔离：HomeBench 场景无 image/device_uuid")
    data = build_homebench_scene().to_json()
    _assert(all(d["image"] is None and d["device_uuid"] is None for d in _iter_devices(data)),
            "HomeBench 所有设备 image/device_uuid 均为 None（无实景消歧能力）")


# ============================================================================ #
# P7-D 实时叠加：动作后 live_state 翻转
# ============================================================================ #
def test_p7d_live_overlay():
    print("[P7-D] 实时叠加：执行动作后 live_state 翻转")
    sage = build_sage_scene()
    ex = SimulateExecutor(sage.to_home_status())
    # 选带 image 的多模态灯（同类多实例，靠自定义 slot 名区分）验证实时联动。
    ex.execute("bedroom.nightstand_light.turn_on()")
    live = sage.to_json(live_status=ex.snapshot())
    light = next(d for d in _iter_devices(live) if d["name"] == "nightstand_light")
    _assert(light["live_state"] == "on",
            "turn_on 后 nightstand_light 的 live_state == on")
    _assert(light["image"] and light["device_uuid"],
            "该实时联动设备同时携带 image/device_uuid（多模态+联动打通）")


# ============================================================================ #
# P7-E 属性契约：live_attributes 为 {value:...} 嵌套结构
#   —— 前端 visual.ts 的 num() 须按 .value 取数（bug#1 逃逸的根因，护住防回归）
# ============================================================================ #
def test_p7e_live_attributes_nested():
    print("[P7-E] 属性契约：live_attributes 以 {value} 嵌套结构下发")
    sage = build_sage_scene()
    ex = SimulateExecutor(sage.to_home_status())
    # 开灯后设亮度，断言 live_attributes 能被 visual 层的取数逻辑读到
    ex.execute("bedroom.nightstand_light.turn_on()")
    ex.execute("bedroom.nightstand_light.set_brightness(40)")
    live = sage.to_json(live_status=ex.snapshot())
    light = next(d for d in _iter_devices(live) if d["name"] == "nightstand_light")
    b = light["live_attributes"]["brightness"]
    _assert(isinstance(b, dict) and b.get("value") == 40,
            "亮度以 {value:40} 嵌套结构下发（前端需按 .value 取，非裸数字）")


def main():
    print("== P7 多模态数据层冒烟测试 ==\n")
    test_p7a_contract()
    test_p7b_sage_multimodal()
    test_p7c_homebench_no_multimodal()
    test_p7d_live_overlay()
    test_p7e_live_attributes_nested()
    print("\n== 全部 P7 数据层冒烟用例通过 ==")


if __name__ == "__main__":
    main()
