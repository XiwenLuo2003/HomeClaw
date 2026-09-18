"""M4 冒烟测试：持久化条件监控 + 新增维度完善。

运行：
    cd HomeClaw
    python3 tests/smoke_m4.py

覆盖：
  1. parse_condition：解析条件表达式
  2. Condition.evaluate：针对 home 对象树求值
  3. ConditionMonitor / SimulateExecutor.tick：条件触发→二次执行闭环
  4. SAGE persistence 维度用例通过
  5. 新增维度：latency_ms 采集 + DimensionResult 含 avg_latency_ms
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from homeclaw.config import LLMConfig  # noqa: E402
from homeclaw.executor import (  # noqa: E402
    SimulateExecutor,
    parse_condition,
    Condition,
)
from homeclaw.eval import SageEvalAdapter, get_tests  # noqa: E402
from homeclaw.runners import SageRunner  # noqa: E402


HOME = {
    "living_room": {"room_name": "living_room",
                    "light": {"state": "on", "attributes": {
                        "brightness": {"value": 100, "lowest": "0", "highest": "100"}}}},
    "balcony": {"room_name": "balcony",
                "light": {"state": "off", "attributes": {
                    "brightness": {"value": 40, "lowest": "0", "highest": "100"}}}},
    "garage": {"room_name": "garage",
               "garage_door": {"state": "closed", "attributes": {}}},
}


def _assert(cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    if not cond:
        raise AssertionError(msg)


def test_parse_condition():
    print("[1] parse_condition")
    c = parse_condition("balcony.light state == on")
    _assert(c.room == "balcony" and c.device == "light" and c.attr is None
            and c.op == "==" and c.value == "on", "state 条件解析")
    c2 = parse_condition("living_room.light.brightness < 20")
    _assert(c2.attr == "brightness" and c2.op == "<" and c2.value == 20, "属性数值条件解析")


def test_evaluate():
    print("[2] Condition.evaluate")
    ex = SimulateExecutor(HOME)
    c_on = Condition("balcony", "light", None, "==", "on")
    _assert(c_on.evaluate(ex.home) is False, "初始 balcony 灯 off，条件不满足")
    ex.execute("balcony.light.turn_on()")
    _assert(c_on.evaluate(ex.home) is True, "打开后条件满足")

    c_door = parse_condition("garage.garage_door state == open")
    _assert(c_door.evaluate(ex.home) is False, "车库门初始 closed")


def test_monitor_tick():
    print("[3] ConditionMonitor / tick 闭环")
    ex = SimulateExecutor(HOME)
    ex.register_persistent("balcony.light state == on",
                           ["living_room.light.turn_off()"],
                           info="demo")
    _assert(ex.pending_conditions() == 1, "有 1 条待触发规则")

    fired0 = ex.tick()
    _assert(len(fired0) == 0, "条件未满足，tick 不触发")

    ex.execute("balcony.light.turn_on()")
    fired1 = ex.tick()
    _assert(len(fired1) == 1, "条件满足，tick 触发 1 条")
    _assert(ex.snapshot()["living_room"]["light"]["state"] == "off",
            "二次执行：living_room 灯被关闭")
    _assert(ex.pending_conditions() == 0, "触发后无待触发规则")

    # 已触发不重复
    fired2 = ex.tick()
    _assert(len(fired2) == 0, "已触发规则不重复触发")


def test_persistence_dimension():
    print("[4] SAGE persistence 维度用例")
    tests = get_tests(["persistence"])
    _assert(len(tests) >= 1, "persistence 维度已注册用例")
    # 用例内部自建执行器，coordinator 传 None 也可运行
    results = [t(None) for t in tests]
    _assert(all(r.passed for r in results), "persistence 用例全部通过")
    for r in results:
        print(f"      {r.name}: {r.detail}")


def test_new_dimensions():
    print("[5] 新增维度：latency 采集 + 聚合")
    runner = SageRunner(llm_config=LLMConfig(provider="mock"))
    results = runner.run()
    hc = results["homeclaw"]
    _assert("persistence" in hc, "五维含 persistence")
    _assert("command_chaining" in hc, "五维含 command_chaining")
    # latency 字段存在且非负
    for dim, r in hc.items():
        _assert(r.avg_latency_ms >= 0.0, f"{dim} 有 avg_latency_ms")
    print()
    print(SageRunner.render({"homeclaw": hc}))


def main():
    print("== M4 冒烟测试：持久化条件监控 + 新增维度 ==\n")
    test_parse_condition()
    test_evaluate()
    test_monitor_tick()
    test_persistence_dimension()
    test_new_dimensions()
    print("\n== 全部 M4 冒烟用例通过 ==")


if __name__ == "__main__":
    main()
