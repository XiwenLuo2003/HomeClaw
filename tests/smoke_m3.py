"""M3 冒烟测试：双评测适配器 + 四系统对比（离线 mock）。

运行：
    cd HomeClaw
    python3 tests/smoke_m3.py

覆盖：
  1. metrics：EM/P/R/F1 + 归一化 + 新增维度（error_input 准确率等）
  2. HomeBench 数据集加载 + 六型分类
  3. HomeBenchRunner：四系统在 HomeBench（前 N 条）上跑通并出对比表
  4. SageRunner：四系统在五维用例上跑通并出对比表
  5. 真实 Provider 工厂可创建（不实际联网）
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from homeclaw.config import LLMConfig, CoordinatorType, build_coordinator  # noqa: E402
from homeclaw.eval import (  # noqa: E402
    compute_metrics,
    normalize_output,
    classify_type,
    load_homebench_dataset,
    HomeBenchEvalAdapter,
)
from homeclaw.llm import create_llm_client  # noqa: E402
from homeclaw.runners import HomeBenchRunner, SageRunner  # noqa: E402


def _assert(cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    if not cond:
      raise AssertionError(msg)


def test_metrics():
    print("[1] metrics")
    toks = normalize_output("{living_room.light.turn_off(), error_input}")
    _assert(toks == ["living_room.light.turn_off()", "error_input"], "归一化提取花括号内并切分")
    _assert(normalize_output("'''balcony.light.turn_on()'''") == ["balcony.light.turn_on()"],
            "gold ''' 包裹被清洗")

    gen = ["{a.b.c()}", "{error_input}", "{x.y.z(1),error_input}"]
    gold = ["'''a.b.c()'''", "'''error_input'''", "'''x.y.z(1),m.n.o()'''"]
    m = compute_metrics(gen, gold)
    _assert(m.n == 3, "样本数=3")
    _assert(0.0 <= m.em <= 1.0 and 0.0 <= m.f1 <= 1.0, "指标在合法区间")
    _assert(m.error_input_accuracy == 1.0, "error_input 准确率=1（两处期望均命中）")
    print(f"    EM={m.em:.3f} P={m.precision:.3f} R={m.recall:.3f} "
          f"F1={m.f1:.3f} errAcc={m.error_input_accuracy:.3f}")


def test_classify():
    print("[2] 六型分类")
    _assert(classify_type("normal") == "normal_single", "normal→normal_single")
    _assert(classify_type("unexist_device") == "unexist_device", "unexist_device")
    _assert(classify_type("multi8_mix") == "mix_multi", "multi8_mix→mix_multi")
    _assert(classify_type("multi7_normal") == "normal_multi", "multi7_normal→normal_multi")
    _assert(classify_type("multi9_error") == "error_multi", "multi9_error→error_multi")


def test_dataset_load():
    print("[3] HomeBench 数据集加载")
    samples, home_index = load_homebench_dataset(limit=20)
    _assert(len(samples) == 20, "加载前 20 条样本")
    _assert(all(s.home_id in home_index for s in samples), "所有样本 home_id 均可关联")
    types = set(s.type6 for s in samples)
    print(f" 样本类型分布: {types}")


def test_homebench_runner():
    print("[4] HomeBenchRunner 四系统对比（前 30 条，mock）")
    runner = HomeBenchRunner(limit=30, llm_config=LLMConfig(provider="mock"))
    results = runner.run()
    _assert(set(results.keys()) == {"homeclaw", "sage", "sasha", "oneprompt"}, "四系统均有结果")
    for name, r in results.items():
        _assert(r.overall.n == 30, f"{name} 评测了 30 条")
    print()
    print(HomeBenchRunner.render_overall(results))


def test_sage_runner():
    print("\n[5] SageRunner 四系统五维对比（mock）")
    runner = SageRunner(llm_config=LLMConfig(provider="mock"))
    results = runner.run()
    _assert(set(results.keys()) == {"homeclaw", "sage", "sasha", "oneprompt"}, "四系统均有结果")
    print()
    print(SageRunner.render(results))


def test_provider_factory():
    print("\n[6] 真实 Provider 工厂")
    c1 = create_llm_client(LLMConfig(provider="openai", model="gpt-4o-mini", api_key="dummy"))
    c2 = create_llm_client(LLMConfig(provider="anthropic", model="claude-x", api_key="dummy"))
    c3 = create_llm_client(LLMConfig(provider="gemini", model="gemini-x", api_key="dummy"))
    _assert(c1.__class__.__name__ == "OpenAICompatibleClient", "openai → OpenAICompatibleClient")
    _assert(c2.__class__.__name__ == "AnthropicClient", "anthropic → AnthropicClient")
    _assert(c3.__class__.__name__ == "GeminiCompatibleClient", "gemini → GeminiCompatibleClient")


def main():
    print("== M3 冒烟测试：双评测 + 四系统对比 ==\n")
    test_metrics()
    test_classify()
    test_dataset_load()
    test_homebench_runner()
    test_sage_runner()
    test_provider_factory()
    print("\n== 全部 M3 冒烟用例通过 ==")


if __name__ == "__main__":
    main()
