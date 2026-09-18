"""HomeClaw 一键实验入口。

用途：在同一套指标下对比多个系统（HomeClaw / SAGE / Sasha / OnePrompt）在
HomeBench（幻觉六型）与 SAGE（五维 + 新增维度）两套数据集上的表现。

通用格式
--------
    python3 run_experiment.py \\
        --dataset {both|homebench|sage} \\
        --split {test|valid|train_part1|train_part2} \\
        --limit N | --sample N [--seed S] \\
        --provider {mock|openai|anthropic|openai_compatible|local} \\
   --model <name> [--base-url URL] \\
        --systems {all|homeclaw,sage,...} \\
        --executor {sim|mock_cloud|smartthings|homeassistant} \\
    [--no-lazy-report]

参数说明
--------
    --dataset   跑哪个数据集：both（默认）/ homebench（仅幻觉）/ sage（仅五维）
    --split     HomeBench 数据划分（默认 test）
    --limit     HomeBench 顺序取前 N 条（默认 60）
    --sample    HomeBench 从全量随机抽 N 条（优先于 --limit，适合大数据集快速看效果）
    --seed   随机抽样种子（默认 42，保证可复现）
    --provider  模型来源：mock=离线规则；openai/anthropic=云端 API；local=本地 transformers；
openai_compatible + --base-url = 本地 vLLM/Ollama
    --model 模型名 / 本地权重 sub_dir / HF repo id
    --systems   参与对比的系统子集，逗号分隔（如 homeclaw,sage）；all=四系统全上
    --executor  SAGE 五维执行后端：sim（默认）/ mock_cloud / smartthings / homeassistant
    --no-lazy-report  跳过懒加载省 token 量化段

具体示例
--------
    # 离线冒烟（无需 API）
    python3 run_experiment.py --provider mock --limit 60

    # 云端 API 主路径，两套数据集全跑，HomeBench 随机抽 300 条
    export OPENAI_API_KEY=sk-...
    python3 run_experiment.py --provider openai --model gpt-4o-mini --dataset both --sample 300

  # 只在 HomeBench 上快速看幻觉效果（随机 200 条，只比 HomeClaw 与 SAGE）
    python3 run_experiment.py --provider openai --model gpt-4o-mini \\
        --dataset homebench --sample 200 --systems homeclaw,sage

    # 只跑 SAGE 五维
    python3 run_experiment.py --provider anthropic --model <model> --dataset sage

    # 本地开源模型（先 python download_models.py）
    python3 run_experiment.py --provider local --model Qwen2.5-7B-Instruct --sample 200

    # 让 SAGE 位走官方实现
    SAGE_ENABLE_OFFICIAL=1 python3 run_experiment.py --provider openai --model gpt-4o-mini

说明：
  - --provider mock 的所有数字仅为链路验证/可复现下界，不能作为论文结论；
  - 真实 provider 下，系统间差异（幻觉抑制、五维通过率、懒加载省 token）才会拉开；
  - 报告顶部会标注数据来源（mock/real）。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from homeclaw.config import CoordinatorType, HomeClawCoordinatorConfig, LLMConfig, build_coordinator  # noqa: E402
from homeclaw.runners import HomeBenchRunner, SageRunner, provenance_banner  # noqa: E402


def measure_lazy_saving(llm_config: LLMConfig) -> str:
    """对比同为 HomeClaw 内核、但懒加载 on/off 两种配置在简单指令上的 prompt token，
    量化"懒加载省 token"卖点（省的是 SKILL 完整领域策略正文那部分）。"""
    from homeclaw.config import SkillConfig
    from homeclaw.executor import NullExecutor

    simple_cmd = "Amal: turn off the light in the living room"
    home = {
        "living_room": {"room_name": "living_room",
                        "light": {"state": "on", "attributes": {
                            "brightness": {"value": 100, "lowest": "0", "highest": "100"}}}},
    }
    methods = [{"room_name": "living_room", "device_name": "light",
                "operation": "turn_off", "parameters": []}]

    # 懒加载开（默认）
    cfg_on = HomeClawCoordinatorConfig(llm_config=llm_config)
    cfg_on.skill_config = SkillConfig(lazy_load=True)
    hc_on = build_coordinator(CoordinatorType.HOMECLAW, cfg_on)
    hc_on.executor = NullExecutor(home_status=home, methods=methods)

    # 懒加载关（全文注入）——同一 HomeClaw 内核
    cfg_off = HomeClawCoordinatorConfig(llm_config=llm_config)
    cfg_off.skill_config = SkillConfig(lazy_load=False)
    hc_off = build_coordinator(CoordinatorType.HOMECLAW, cfg_off)
    hc_off.executor = NullExecutor(home_status=home, methods=methods)

    r_on = hc_on.execute(simple_cmd)
    r_off = hc_off.execute(simple_cmd)
    on_tok = r_on.usage.get("prompt_tokens", 0)
    off_tok = r_off.usage.get("prompt_tokens", 0)
    saved = (1 - on_tok / off_tok) * 100 if off_tok else 0.0
    lines = [
        "== 懒加载省 token（同一 HomeClaw 内核，简单指令，prompt_tokens）==",
        f"  lazy_load=on  (仅注入 CORE 速览): {on_tok}  (skill_loaded={r_on.skill_loaded})",
        f"  lazy_load=off (注入 SKILL 全文): {off_tok}",
        f"  节省: {saved:.1f}%（简单指令无需完整领域策略，故省去全文）",
    ]
    return "\n".join(lines)


def _parse_systems(spec):
    """把 --systems 逗号分隔字符串解析为 CoordinatorType 列表；all/空=四系统全上。"""
    if not spec or spec.strip().lower() == "all":
        return None
    mapping = {c.value: c for c in CoordinatorType}
    out = []
    for name in spec.split(","):
        key = name.strip().lower()
        if key not in mapping:
            raise SystemExit(f"unknown system: {name!r}; choices: {list(mapping)} or all")
        out.append(mapping[key])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description="HomeClaw multi-system experiment",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--dataset", default="both", choices=["both", "homebench", "sage"],
        help="which dataset: both / homebench(hallucination) / sage(5-dim)")
    ap.add_argument("--split", default="test",
        choices=["test", "valid", "train_part1", "train_part2"], help="HomeBench split")
    ap.add_argument("--limit", type=int, default=60, help="HomeBench take first N (None=all)")
    ap.add_argument("--sample", type=int, default=None,
        help="HomeBench random N from full set (overrides --limit)")
    ap.add_argument("--seed", type=int, default=42, help="random sample seed")
    ap.add_argument("--provider", default="mock",
        choices=["mock", "openai", "openai_compatible", "anthropic", "local"],
        help="mock/openai/anthropic/local/openai_compatible")
    ap.add_argument("--model", default="mock-model", help="model name or local sub_dir/repo id")
    ap.add_argument("--base-url", default=None, help="openai_compatible service url")
    ap.add_argument("--systems", default="all",
        help="comma list e.g. homeclaw,sage ; all=four systems")
    ap.add_argument("--executor", default="sim",
        choices=["sim", "mock_cloud", "smartthings", "homeassistant"], help="SAGE exec backend")
    ap.add_argument("--no-lazy-report", action="store_true", help="skip lazy-load token section")
    args = ap.parse_args()

    if args.provider == "local":
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

    llm_config = LLMConfig(provider=args.provider, model=args.model, base_url=args.base_url)
    systems = _parse_systems(args.systems)

    print(provenance_banner(llm_config))
    print("[config] dataset=%s split=%s limit=%s sample=%s seed=%s systems=%s executor=%s" % (args.dataset, args.split, args.limit, args.sample, args.seed, args.systems, args.executor))
    print()

    run_hb = args.dataset in ("both", "homebench")
    run_sage = args.dataset in ("both", "sage")
    n_steps = int(run_hb) + int(run_sage) + (0 if args.no_lazy_report else 1)
    step = 0

    if run_hb:
        step += 1
        print("### %d/%d HomeBench hallucination 6-type - systems" % (step, n_steps))
        hb = HomeBenchRunner(split=args.split, limit=args.limit, sample=args.sample,
            seed=args.seed, llm_config=llm_config, systems=systems)
        hb_results = hb.run()
        print(HomeBenchRunner.render_overall(hb_results))
        print()
        print(HomeBenchRunner.render_by_type(hb_results))
        print()

    if run_sage:
        step += 1
        print("### %d/%d SAGE 5-dim + extra - systems" % (step, n_steps))
        if args.executor != "sim":
            print("[exec backend] executor=%s" % args.executor)
        sage = SageRunner(llm_config=llm_config, systems=systems, exec_backend=args.executor)
        print(SageRunner.render(sage.run()))
        print()

    if not args.no_lazy_report:
        step += 1
        print("### %d/%d lazy-load token saving" % (step, n_steps))
        print(measure_lazy_saving(llm_config))


if __name__ == "__main__":
    main()
