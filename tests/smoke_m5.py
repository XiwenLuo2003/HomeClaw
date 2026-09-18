"""M5 冒烟测试：真机接口 RealDeviceExecutor + DeviceCloudAdapter。

运行：
    cd HomeClaw
    python3 tests/smoke_m5.py

覆盖：
  1. MockCloudAdapter：resolve（含容错）/ call / 状态
  2. RealDeviceExecutor：合法下发 / error_input 拒答 / 未解析设备
  3. 一套动作文本"仿真/真机"一致性：同一 action 分别喂 Simulate 与 Real
  4. SmartThings/HomeAssistant 适配器可创建且缺凭证时报错清晰（不联网）
  5. Coordinator 接 RealDeviceExecutor（execute 走真机层）
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from homeclaw import HomeClawCoordinator, HomeClawCoordinatorConfig
from homeclaw.config import LLMConfig
from homeclaw.executor import (
    SimulateExecutor,
    RealDeviceExecutor,
    MockCloudAdapter,
    SmartThingsAdapter,
    HomeAssistantAdapter,
    DeviceResolveError,
)


HOME = {
    "living_room": {"room_name": "living_room",
                    "light": {"state": "on", "attributes": {
                        "brightness": {"value": 100, "lowest": "0", "highest": "100"}}}},
    "balcony": {"room_name": "balcony",
                "light": {"state": "off", "attributes": {
                    "brightness": {"value": 40, "lowest": "0", "highest": "100"}}}},
}


def _assert(cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    if not cond:
        raise AssertionError(msg)


def test_adapter():
    print("[1] MockCloudAdapter")
    ad = MockCloudAdapter()
    _assert(ad.resolve("living_room", "light") == "st-lr-light-01", "精确 resolve")
    # 容错：轻微拼写差异
    got = ad.resolve("living_room", "lightt")
    _assert(got == "st-lr-light-01", "近似匹配容错 resolve")
    r = ad.call("st-lr-light-01", "turn_off", [])
    _assert(r["status"] == "ok" and len(ad.call_log) == 1, "call 下发并记录日志")
    try:
        ad.resolve("kitchen", "oven")
        _assert(False, "不存在设备应抛错")
    except DeviceResolveError:
        _assert(True, "不存在设备抛 DeviceResolveError")


def test_real_executor():
    print("[2] RealDeviceExecutor")
    ad = MockCloudAdapter()
    ex = RealDeviceExecutor(ad, home_status=HOME)

    r = ex.execute("balcony.light.set_brightness(40)")
    _assert(r["status"] == "ok" and r["device_id"] == "st-bal-light-01", "合法动作下发到真机层")
    _assert(ad.call_log[-1]["op"] == "set_brightness" and ad.call_log[-1]["args"] == [40],
            "适配器收到正确 op/args")

    r = ex.execute("error_input")
    _assert(r["status"] == "rejected", "error_input → rejected")

    r = ex.execute("kitchen.oven.turn_on()")
    _assert(r["status"] == "error" and r["reason"] == "unresolved_device", "未登记设备 → unresolved_device")


def test_format_consistency():
    print("[3] 一套动作文本：仿真/真机一致性")
    action = "living_room.light.turn_off()"
    # 仿真
    sim = SimulateExecutor(HOME)
    rs = sim.execute(action)
    # 真机（mock）
    real = RealDeviceExecutor(MockCloudAdapter(), home_status=HOME)
    rr = real.execute(action)
    _assert(rs["status"] == "ok" and rr["status"] == "ok",
            "同一动作文本仿真与真机均成功执行（格式零改动）")
    _assert(sim.snapshot()["living_room"]["light"]["state"] == "off", "仿真状态已改")


def test_real_adapters_creatable():
    print("[4] SmartThings / HomeAssistant 适配器")
    st = SmartThingsAdapter(device_map={("living_room", "light"): "abc"})
    ha = HomeAssistantAdapter(entity_map={("living_room", "light"): "light.living_room"})
    _assert(st.resolve("living_room", "light") == "abc", "SmartThings resolve via device_map")
    _assert(ha.resolve("living_room", "light") == "light.living_room", "HomeAssistant resolve via entity_map")
    # 约定式默认
    _assert(ha.resolve("balcony", "light") == "light.balcony", "HomeAssistant 约定式默认 entity_id")
    # 缺 token 时 call 报错清晰
    try:
        st.call("abc", "turn_on", [])
        _assert(False, "缺 token 应报错")
    except RuntimeError as e:
        _assert("SMARTTHINGS_TOKEN" in str(e), "SmartThings 缺 token 提示清晰")


def test_coordinator_with_real():
    print("[5] Coordinator 接 RealDeviceExecutor")
    ad = MockCloudAdapter()
    ex = RealDeviceExecutor(ad, home_status=HOME)
    cfg = HomeClawCoordinatorConfig(llm_config=LLMConfig(provider="mock"), executor=ex)
    coord = HomeClawCoordinator(cfg)
    result = coord.execute("Amal: turn off the light in the living room")
    _assert("living_room.light.turn_off()" in result.actions, "Coordinator 产出动作")
    _assert(any(c["op"] == "turn_off" for c in ad.call_log), "动作已下发到真机适配器 call_log")


def main():
    print("== M5 冒烟测试：真机接口 RealDeviceExecutor + DeviceCloudAdapter ==\n")
    test_adapter()
    test_real_executor()
    test_format_consistency()
    test_real_adapters_creatable()
    test_coordinator_with_real()
    print("\n== 全部 M5 冒烟用例通过 ==")


if __name__ == "__main__":
    main()
