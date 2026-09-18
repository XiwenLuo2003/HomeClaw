"""M6 冒烟测试：四项关键局限的修复验证（离线 mock）。

运行：
    cd HomeClaw
    python3 tests/smoke_m6.py

覆盖四个缺陷的修复：
  [缺陷4] 两级懒加载：简单指令不拉全文（省 token）、复杂指令拉全文；lazy on vs off token 差。
  [缺陷1] 对照组差异化：Sasha 真两阶段(iters=2)、OnePrompt 裸提示(更短)、SAGE ReAct(更长)；
          SageBridge 官方桥接开关可用。
  [缺陷3] 五维用例集扩充：每维多用例；chaining/persistence 走 execute()/tick 而非手写动作。
  [缺陷2] MockLLM 语义化：多子句→多动作、幻觉→error_input；run_experiment 报告标注来源。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from homeclaw.config import (  # noqa: E402
    CoordinatorType, HomeClawCoordinatorConfig, LLMConfig, SkillConfig, build_coordinator,
)
from homeclaw.coordinators import (  # noqa: E402
    HomeClawCoordinator, SashaCoordinator, OnePromptCoordinator, SageBridgeCoordinator,
)
from homeclaw.eval import get_tests, SageEvalAdapter  # noqa: E402
from homeclaw.executor import NullExecutor  # noqa: E402
from homeclaw.runners import provenance_banner  # noqa: E402


HOME = {
    "living_room": {"room_name": "living_room",
                    "light": {"state": "on", "attributes": {
                        "brightness": {"value": 100, "lowest": "0", "highest": "100"}}}},
    "kitchen": {"room_name": "kitchen",
                "light": {"state": "on", "attributes": {
                    "brightness": {"value": 100, "lowest": "0", "highest": "100"}}}},
}
METHODS = [
    {"room_name": "living_room", "device_name": "light", "operation": "turn_off", "parameters": []},
    {"room_name": "kitchen", "device_name": "light", "operation": "turn_off", "parameters": []},
]


def _assert(cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    if not cond:
        raise AssertionError(msg)


def _mk(ctype):
    c = build_coordinator(ctype, HomeClawCoordinatorConfig(llm_config=LLMConfig(provider="mock")))
    c.executor = NullExecutor(home_status=HOME, methods=METHODS)
    return c


def test_lazy_loading():
    print("[缺陷4] 两级懒加载")
    hc = _mk(CoordinatorType.HOMECLAW)
    r_simple = hc.execute("Amal: turn off the light in the living room")
    _assert(r_simple.skill_loaded is False, "简单指令不拉全文（skill_loaded=False）")
    _assert(r_simple.iters == 1, "简单指令单轮完成")

    hc.executor = NullExecutor(home_status=HOME, methods=METHODS)
    r_complex = hc.execute(
        "Amal: turn off the light in the living room and turn off the light in the kitchen")
    _assert(r_complex.skill_loaded is True, "复杂指令触发 READ_SKILL 拉全文")
    _assert(len(r_complex.actions) == 2, "复杂指令产出多动作")

    # lazy on vs off 的 token 差
    cfg_off = HomeClawCoordinatorConfig(llm_config=LLMConfig(provider="mock"))
    cfg_off.skill_config = SkillConfig(lazy_load=False)
    hc_off = build_coordinator(CoordinatorType.HOMECLAW, cfg_off)
    hc_off.executor = NullExecutor(home_status=HOME, methods=METHODS)
    tok_on = _mk(CoordinatorType.HOMECLAW).execute(
        "Amal: turn off the light in the living room").usage["prompt_tokens"]
    tok_off = hc_off.execute("Amal: turn off the light in the living room").usage["prompt_tokens"]
    print(f"      lazy on={tok_on}  off={tok_off}")
    _assert(tok_on < tok_off, "懒加载简单指令 prompt token 显著小于全文注入")


def test_baseline_differentiation():
    print("[缺陷1] 对照组差异化")
    cmd = "Amal: turn off the light in the living room"
    hc = _mk(CoordinatorType.HOMECLAW).execute(cmd)
    sasha = _mk(CoordinatorType.SASHA).execute(cmd)
    op = _mk(CoordinatorType.ONEPROMPT).execute(cmd)
    sage = _mk(CoordinatorType.SAGE).execute(cmd)
    print(f"      pTok: HomeClaw={hc.usage['prompt_tokens']} SAGE={sage.usage['prompt_tokens']} "
          f"Sasha={sasha.usage['prompt_tokens']} OnePrompt={op.usage['prompt_tokens']}")
    _assert(sasha.iters == 2, "Sasha 走真两阶段（iters=2）")
    _assert(op.usage["prompt_tokens"] < sage.usage["prompt_tokens"],
            "OnePrompt 裸提示 token 少于 SAGE 全文 ReAct")
    _assert(hc.usage["prompt_tokens"] < sage.usage["prompt_tokens"],
            "HomeClaw 懒加载 token 少于 SAGE 全文注入")

    # SageBridge 官方桥接开关
    sb = SageBridgeCoordinator(HomeClawCoordinatorConfig(llm_config=LLMConfig(provider="mock")))
    _assert(sb.uses_official is False, "默认不启用 SAGE 官方实现（需 SAGE_ENABLE_OFFICIAL=1 且环境可用）")


def test_case_suite_expansion():
    print("[缺陷3] 五维用例集扩充")
    for dim in ["device_resolution", "intent_resolution", "command_chaining", "persistence"]:
        n = len(get_tests([dim]))
        print(f"      {dim}: {n} case(s)")
        _assert(n >= 2, f"{dim} 至少 2 个用例（不再是单种子）")

    # chaining 用例走 LLM（execute → 多动作），验证通过率与多动作
    adapter = SageEvalAdapter()
    hc = _mk(CoordinatorType.HOMECLAW)
    dr = adapter.run_dimension(hc, "command_chaining", "homeclaw")
    _assert(dr.total >= 2 and dr.passed == dr.total, "command_chaining 全通过（经 LLM 多步编排）")


def test_mock_semantics_and_provenance():
    print("[缺陷2] MockLLM 语义化 + 来源标注")
    hc = _mk(CoordinatorType.HOMECLAW)
    # 多子句 → 多动作
    r = hc.execute("Amal: turn off the light in the living room and turn off the light in the kitchen")
    _assert(len(r.actions) == 2, "多子句指令被拆成多动作")
    # 幻觉 → error_input
    out = hc.predict_actions(HOME, "Turn on the light in the basement.", METHODS)
    _assert("error_input" in out, "不存在房间触发 error_input")
    # 来源标注
    banner_mock = provenance_banner(LLMConfig(provider="mock"))
    banner_real = provenance_banner(LLMConfig(provider="openai", model="gpt-4o-mini"))
    _assert("非真实模型效果" in banner_mock, "mock 报告明确标注非真实效果")
    _assert("真实模型评测结果" in banner_real, "real 报告标注真实来源")


def main():
    print("== M6 冒烟测试：四项关键局限修复验证 ==\n")
    test_lazy_loading()
    test_baseline_differentiation()
    test_case_suite_expansion()
    test_mock_semantics_and_provenance()
    print("\n== 全部 M6 冒烟用例通过 ==")


if __name__ == "__main__":
    main()
