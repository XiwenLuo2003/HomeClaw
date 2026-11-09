"""四系统对比 Runner（M3 / M6）。

- HomeBenchRunner : 在 HomeBench 数据集上跑四系统的幻觉六型评测，输出对比表。
- SageRunner      : 在 SAGE 五维用例上跑四系统评测 + 新增维度，输出对比表。

四系统：HomeClaw / SAGE / Sasha / One Prompt（见 config.CoordinatorType）。
默认使用 mock provider，可通过 llm_config 切换真实 LLM。

【M6】所有渲染输出附带"数据来源声明"（provider=mock/real），
避免把链路验证值误当作真实模型效果。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from homeclaw.config import (
    CoordinatorType,
    HomeClawCoordinatorConfig,
    LLMConfig,
    build_coordinator,
)
from homeclaw.eval import (
    HomeBenchEvalAdapter,
    HomeBenchEvalResult,
    SageEvalAdapter,
    DimensionResult,
    MetricResult,
    format_metric_table,
)


DEFAULT_SYSTEMS = [
    CoordinatorType.HOMECLAW,
    CoordinatorType.SAGE,
    CoordinatorType.SASHA,
    CoordinatorType.ONEPROMPT,
]


def provenance_banner(llm_config: LLMConfig) -> str:
    """生成数据来源声明横幅（标注 provider 是否为真实模型）。"""
    if llm_config.provider == "mock":
        return ("[数据来源] provider=mock（规则模拟器）：以下数字仅为链路验证/可复现下界，"
                "非真实模型效果，不能作为论文结论。真实效果请用 run_experiment.py 接入真实 LLM。")
    return (f"[数据来源] provider={llm_config.provider} model={llm_config.model}：真实模型评测结果。")


def _make(ctype: CoordinatorType, llm_config: LLMConfig):
    cfg = HomeClawCoordinatorConfig(llm_config=llm_config)
    return build_coordinator(ctype, cfg)


class HomeBenchRunner:
    """在 HomeBench 数据集上对比四系统的幻觉抑制能力。"""

    def __init__(
        self,
        dataset_dir: Optional[str] = None,
        split: str = "test",
        limit: Optional[int] = None,
        sample: Optional[int] = None,
        seed: int = 42,
        llm_config: Optional[LLMConfig] = None,
        systems: Optional[List[CoordinatorType]] = None,
    ):
        self.adapter = HomeBenchEvalAdapter(dataset_dir, split, limit, sample=sample, seed=seed)
        self.llm_config = llm_config or LLMConfig(provider="mock")
        self.systems = systems or DEFAULT_SYSTEMS

    def run(self) -> Dict[str, HomeBenchEvalResult]:
        results: Dict[str, HomeBenchEvalResult] = {}
        for ctype in self.systems:
            coord = _make(ctype, self.llm_config)
            results[ctype.value] = self.adapter.evaluate(coord, system_name=ctype.value)
        return results

    def report(self) -> str:
        """带数据来源声明的完整报告（OVERALL 对比）。"""
        results = self.run()
        return provenance_banner(self.llm_config) + "\n\n" + self.render_overall(results)

    @staticmethod
    def render_overall(results: Dict[str, HomeBenchEvalResult]) -> str:
        """四系统 OVERALL 对比表。"""
        rows = {name: r.overall for name, r in results.items()}
        return format_metric_table(rows, title="HomeBench 幻觉评测 · 四系统 OVERALL 对比")

    @staticmethod
    def render_by_type(results: Dict[str, HomeBenchEvalResult]) -> str:
        """按六型分别输出四系统对比。"""
        from homeclaw.eval import SIX_TYPES
        out: List[str] = []
        for t in SIX_TYPES:
            rows = {}
            for name, r in results.items():
                if t in r.by_type:
                    rows[name] = r.by_type[t]
            if rows:
                out.append(format_metric_table(rows, title=f"HomeBench 类型={t} · 四系统对比"))
        return "\n\n".join(out)


class SageRunner:
    """在 SAGE 五维用例上对比四系统 + 新增维度。

    exec_backend（P5 真机评测开关）：
      - "sim"（默认）→ 内存仿真评测（可复现）
      - "mock_cloud" → 真机链路评测（离线可复现，验证动作正确下发）
      - "smartthings"/"homeassistant" → 真实设备云（需凭证，谨慎在真设备上跑）
    """

    def __init__(
        self,
        llm_config: Optional[LLMConfig] = None,
        systems: Optional[List[CoordinatorType]] = None,
        exec_backend: str = "sim",
    ):
        self.adapter = SageEvalAdapter()
        self.llm_config = llm_config or LLMConfig(provider="mock")
        self.systems = systems or DEFAULT_SYSTEMS
        self.exec_backend = exec_backend

    def run(self) -> Dict[str, Dict[str, DimensionResult]]:
        """返回 {system_name: {dimension: DimensionResult}}。"""
        results: Dict[str, Dict[str, DimensionResult]] = {}
        for ctype in self.systems:
            coord = _make(ctype, self.llm_config)
            # 注入真机/仿真后端开关，供 sage_cases._run 读取
            coord._exec_backend = self.exec_backend
            results[ctype.value] = self.adapter.run_all(coord, system_name=ctype.value)
        return results

    def report(self) -> str:
        """带数据来源声明的完整五维对比报告。"""
        results = self.run()
        return provenance_banner(self.llm_config) + "\n\n" + self.render(results)

    @staticmethod
    def render(results: Dict[str, Dict[str, DimensionResult]]) -> str:
        out: List[str] = []
        for system_name, dims in results.items():
            out.append(SageEvalAdapter.render(dims, system_name=system_name))
        return "\n\n".join(out)
