"""M2 冒烟测试：验证执行器 + 仿真全链路。

运行：
    cd HomeClaw
    python3 tests/smoke_m2.py

覆盖：
  1. parse_action：无参 / 整数参 / 字符串参 / 颜色元组 / 无房间前缀 / error_input / 非法文本
  2. build_home：从 home_status 构建对象树 + snapshot 导出
  3. SimulateExecutor：合法执行改状态、各类 error_input（房间/设备/属性不存在）、拒答
  4. Coordinator.execute 接 SimulateExecutor：状态断言（SAGE 五维口径）
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from homeclaw import HomeClawCoordinator, HomeClawCoordinatorConfig  # noqa: E402
from homeclaw.config import LLMConfig  # noqa: E402
from homeclaw.executor import (  # noqa: E402
    parse_action,
    ActionParseError,
    build_home,
    SimulateExecutor,
)


HOME_STATUS = {
    "living_room": {
        "room_name": "living_room",
        "light": {"state": "on", "attributes": {
            "brightness": {"value": 100, "lowest": "0", "highest": "100"},
            "color": {"value": (255, 255, 255)},
        }},
        "media_player": {"state": "stopped", "attributes": {
            "volume": {"value": 50, "lowest": "0", "highest": "100"}}},
    },
    "balcony": {
        "room_name": "balcony",
        "light": {"state": "on", "attributes": {
            "brightness": {"value": 80, "lowest": "0", "highest": "100"}}},
    },
}

METHODS = [
    {"room_name": "balcony", "device_name": "light", "operation": "set_brightness",
     "parameters": [{"name": "brightness", "type": "int"}]},
]


def _assert(cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    if not cond:
        raise AssertionError(msg)


def test_parser():
    print("[1] parse_action")
    p = parse_action("balcony.light.set_brightness(40)")
    _assert(p.room == "balcony" and p.device == "light" and p.op == "set_brightness"
            and p.args == [40], "整数参数解析")

    p = parse_action("living_room.light.turn_off()")
    _assert(p.args == [], "无参解析")

    p = parse_action("living_room.light.set_color((255,255,255))")
    _assert(p.args == [(255, 255, 255)], "颜色元组解析")

    p = parse_action("living_room.air_conditioner.set_fan_speed(low)")
    _assert(p.args == ["low"], "字符串参数解析")

    p = parse_action("media_player.play()")
    _assert(p.room is None and p.device == "media_player", "无房间前缀解析")

    _assert(parse_action("error_input") is None, "error_input → None")
    _assert(parse_action("{error_input}") is None, "花括号包裹 error_input → None")

    try:
        parse_action("this is not an action")
        _assert(False, "非法文本应抛错")
    except ActionParseError:
        _assert(True, "非法文本抛 ActionParseError")


def test_build_home():
    print("[2] build_home + snapshot")
    home, report = build_home(HOME_STATUS)
    _assert("living_room" in home and "light" in home["living_room"], "对象树含 living_room.light")
    _assert(home["balcony"]["light"].get_status()["state"] == "on", "初始状态载入正确")
    _assert(report.unsupported == [], "无未支持设备")


def test_simulate_executor():
    print("[3] SimulateExecutor")
    ex = SimulateExecutor(HOME_STATUS, METHODS)

    # 合法执行：balcony 灯亮度调到 40
    r = ex.execute("balcony.light.set_brightness(40)")
    _assert(r["status"] == "ok", "合法动作 status=ok")
    _assert(ex.home["balcony"]["light"].get_status()["attributes"]["brightness"]["value"] == 40,
            "内存状态被改为 40")

    # 合法执行：关灯
    r = ex.execute("living_room.light.turn_off()")
    _assert(ex.home["living_room"]["light"].get_status()["state"] == "off", "关灯生效")

    # error_input：房间不存在
    r = ex.execute("kitchen.light.turn_on()")
    _assert(r["status"] == "error" and r["reason"] == "unexist_room", "不存在房间 → unexist_room")

    # error_input：设备不存在
    r = ex.execute("balcony.fan.turn_on()")
    _assert(r["reason"] == "unexist_device", "不存在设备 → unexist_device")

    # error_input：操作/属性不存在
    r = ex.execute("balcony.light.set_temperature(20)")
    _assert(r["reason"] == "unexist_attribute", "不存在操作 → unexist_attribute")

    # 拒答标记
    r = ex.execute("error_input")
    _assert(r["status"] == "rejected", "error_input → rejected")

    # snapshot
    snap = ex.snapshot()
    _assert(snap["balcony"]["light"]["attributes"]["brightness"]["value"] == 40,
            "snapshot 反映最新状态")


def test_coordinator_with_simulator():
    print("[4] Coordinator.execute 接 SimulateExecutor（SAGE 五维口径）")
    ex = SimulateExecutor(HOME_STATUS, METHODS)
    cfg = HomeClawCoordinatorConfig(llm_config=LLMConfig(provider="mock"), executor=ex)
    coord = HomeClawCoordinator(cfg)

    result = coord.execute("Amal: turn off the light in the living room")
    print(f"      → reply: {result}")
    print(f"      → actions: {result.actions}")
    _assert("living_room.light.turn_off()" in result.actions, "产出关灯动作")
    _assert(result.snapshot is not None, "execute 返回状态快照")
    _assert(result.snapshot["living_room"]["light"]["state"] == "off",
            "SAGE 断言：living_room 灯已关闭")


def main():
    print("== M2 冒烟测试：执行器 + 仿真 ==\n")
    test_parser()
    test_build_home()
    test_simulate_executor()
    test_coordinator_with_simulator()
    print("\n== 全部 M2 冒烟用例通过 ==")


if __name__ == "__main__":
    main()
