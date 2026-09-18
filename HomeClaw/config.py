"""HomeClaw 配置模块（M1）。

集中定义全局配置、LLM 配置、Coordinator 配置，以及对照组枚举 CoordinatorType。
M1 阶段仅 HOMECLAW 项可用；SAGE/SASHA/ZEROSHOT 为占位，待 M3 接入。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


@dataclass
class LLMConfig:
    """Provider 无关的 LLM 配置。

    provider 取值示例："openai" / "anthropic" / "mock"。
    M1 默认使用 "mock"，无需真实 API 即可跑通内核冒烟测试。
    """

    provider: str = "mock"
    model: str = "mock-model"
    temperature: float = 0.0
    max_tokens: int = 1024
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    # 单循环最大迭代轮数（防止无限循环；也用于统计"平均调用轮数"这一新增维度）
    max_iters: int = 5


@dataclass
class SkillConfig:
    """Skill 加载配置。"""

    # smart-home Skill 的 SKILL.md 相对/绝对路径；None 时用包内默认路径
    skill_path: Optional[str] = None
    skill_name: str = "smart-home"
    # 是否采用"两级懒加载"：system prompt 只注入 SKILL 核心速览 + read_skill 提示，
    # 模型判断需要完整领域策略时才通过 READ_SKILL 拉取全文并回传。
    # 【M6】默认 True，真正对齐 OpenClaw "Skill 懒加载省 token" 的卖点；
    # 对照组基线（Sasha/OnePrompt）会显式关闭以体现差异。
    lazy_load: bool = True


@dataclass
class CoordinatorConfig:
    """Coordinator 基础配置，各具体 Coordinator 继承。"""

    name: str = "base"
    llm_config: LLMConfig = field(default_factory=LLMConfig)
    # 执行器实例（M1 用 stub；M2 注入 SimulateExecutor）。None 表示"只输出动作文本不落地"。
    executor: object = None
    # 日志目录（可选）
    logpath: Optional[str] = None


@dataclass
class HomeClawCoordinatorConfig(CoordinatorConfig):
    """HomeClaw Coordinator 配置。"""

    name: str = "HomeClaw"
    skill_config: SkillConfig = field(default_factory=SkillConfig)


class CoordinatorType(Enum):
    """对照组枚举（M3：四系统对比）。"""

    HOMECLAW = "homeclaw"
    SAGE = "sage"        # 【M6】SageBridgeCoordinator：优先桥接 SAGE 官方实现，否则等价 ReAct 回退
    SASHA = "sasha"      # 【M6】真两阶段管线
    ONEPROMPT = "oneprompt"  # 单轮裸提示


def build_coordinator(ctype: "CoordinatorType", config: "HomeClawCoordinatorConfig" = None):
    """按 CoordinatorType 惰性实例化对应 Coordinator（避免循环导入）。"""
    from homeclaw.coordinators.homeclaw_coordinator import HomeClawCoordinator
    from homeclaw.coordinators.baselines import (
        OnePromptCoordinator,
        SashaCoordinator,
        SageBridgeCoordinator,
    )

    cfg = config or HomeClawCoordinatorConfig()
    if ctype == CoordinatorType.HOMECLAW:
        return HomeClawCoordinator(cfg)
    if ctype == CoordinatorType.SAGE:
        return SageBridgeCoordinator(cfg)
    if ctype == CoordinatorType.SASHA:
        return SashaCoordinator(cfg)
    if ctype == CoordinatorType.ONEPROMPT:
        return OnePromptCoordinator(cfg)
    raise ValueError(f"未知 CoordinatorType: {ctype}")
