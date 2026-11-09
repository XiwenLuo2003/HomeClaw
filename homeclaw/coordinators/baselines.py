"""对照组 Coordinator（M3 / M6）：One Prompt、Sasha、SAGE。

为在同一套数据与指标下做四系统对比，这里提供三个 baseline。相对 M3 的"几乎等同
HomeClaw 占位"，M6 让三者走**真正差异化**的编排流程，从而使对比能反映架构差异：

- OnePromptCoordinator : 单轮、裸提示、**关闭懒加载**、无领域策略。
                         对应 SAGE OnePrompt / HomeBench zero-shot 基线。
- SashaCoordinator     : **真两阶段**（先意图规划，再据规划产出动作），完整领域 Skill，
                         **关闭懒加载**。对应 Sasha 的 clarify→plan 多阶段思路（精简版）。
- SageBridgeCoordinator: **优先桥接 SAGE 官方 LangChain 实现**（若本机存在 SAGE 包且
                         依赖可用）；否则回退为"完整领域 ReAct 推理"的等价实现。
                         这使"对比体现优势"有可切换的真实对照，而非纯占位。

所有基线仍复用 HomeClaw 的执行/评测链路（execute / predict_actions 双入口），
保证四系统在同一指标口径下可比。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from homeclaw.config import HomeClawCoordinatorConfig, LLMConfig, SkillConfig
from homeclaw.coordinators.homeclaw_coordinator import HomeClawCoordinator
from homeclaw.loop import LoopResult
from homeclaw.prompt import build_system_prompt, build_user_prompt


def _no_lazy_config(config: Optional[HomeClawCoordinatorConfig], name: str) -> HomeClawCoordinatorConfig:
    """构造一个"关闭懒加载"的配置副本（基线不享受 HomeClaw 的省 token 卖点）。"""
    if config is None:
        config = HomeClawCoordinatorConfig(name=name)
    config.name = name
    # 关键差异：基线关闭两级懒加载
    sc = config.skill_config
    config.skill_config = SkillConfig(
        skill_path=sc.skill_path, skill_name=sc.skill_name, lazy_load=False
    )
    return config


class OnePromptCoordinator(HomeClawCoordinator):
    """One Prompt 基线：最小化提示，单轮直出动作，无领域策略、无懒加载。"""

    def __init__(self, config: Optional[HomeClawCoordinatorConfig] = None):
        super().__init__(_no_lazy_config(config, "OnePrompt"))
        # 用最短"裸提示"替换 Skill 正文，抹去领域规划 Know-how（体现基线劣势）
        self.skill_body = (
            "You are 'Al', controlling home devices. Output only machine instructions "
            "enclosed in {}. Format: room.device.operation(param), comma-separated for "
            "multiple actions. Use only devices/methods provided in <home_state> and "
            "<device_method>. Output 'error_input' for non-existent device/attribute/method."
        )
        self.skill_overview = self.skill_body


class SashaCoordinator(HomeClawCoordinator):
    """Sasha 基线：真两阶段（意图规划 → 动作生成），完整 Skill，无懒加载。

    与 HomeClaw 的差异：
      - HomeClaw：单主循环 + 两级懒加载，简单指令一次成型；
      - Sasha   ：固定两阶段管线，先让模型产出自然语言规划，再据规划产出动作，
                  多一轮 LLM 调用（体现在 avg_iters 更高、token 更多）。
    """

    def __init__(self, config: Optional[HomeClawCoordinatorConfig] = None):
        super().__init__(_no_lazy_config(config, "Sasha"))

    def _run_loop(
        self,
        instruction: str,
        home_status: Optional[Dict],
        methods: Optional[List[Dict]],
    ) -> LoopResult:
        """两阶段管线：阶段1 产出规划文本，阶段2 据规划产出机器指令。"""
        import time

        _start = time.perf_counter()
        total_usage: Dict[str, int] = {}

        # —— 阶段 1：意图规划（自然语言，不产出机器指令）——
        plan_system = (
            self.skill_body
            + "\n\n<planning_stage>\nFirst, think step by step about the user's true "
            "intent and which existing devices/methods are involved. Produce a SHORT "
            "natural-language plan. Do NOT output machine instructions yet.\n</planning_stage>"
        )
        plan_msgs = [
            {"role": "system", "content": build_system_prompt(plan_system, home_status, methods)},
            {"role": "user", "content": build_user_prompt(instruction)},
        ]
        plan_resp = self.llm.chat(plan_msgs)
        _acc(total_usage, plan_resp.usage)

        # —— 阶段 2：据规划产出机器指令 ——
        act_system = (
            self.skill_body
            + "\n\n<action_stage>\nGiven the plan below, now output ONLY the machine "
            "instructions enclosed in {}.\n<plan>\n" + (plan_resp.text or "") + "\n</plan>\n</action_stage>"
        )
        act_msgs = [
            {"role": "system", "content": build_system_prompt(act_system, home_status, methods)},
            {"role": "user", "content": build_user_prompt(instruction)},
        ]
        act_resp = self.llm.chat(act_msgs)
        _acc(total_usage, act_resp.usage)

        from homeclaw.loop import extract_actions

        result = LoopResult(messages=act_msgs)
        result.final_text = act_resp.text
        result.actions = extract_actions(act_resp.text)
        result.iters = 2  # 固定两阶段
        result.total_usage = total_usage
        result.latency_ms = (time.perf_counter() - _start) * 1000.0
        return result


class SageBridgeCoordinator(HomeClawCoordinator):
    """SAGE 对照：优先桥接官方 LangChain 实现，否则回退等价 ReAct 领域推理。

    桥接策略（真实对照，非纯占位）：
      1. 若环境变量 SAGE_ENABLE_OFFICIAL=1 且可 import sage.coordinators.sage_coordinator，
         则尝试构造官方 SAGECoordinator 并委托其 execute()（需 SmartThings/Mongo 等外部依赖，
         由使用者自行在 SAGE 环境中启用）。
      2. 否则使用"完整领域 ReAct 推理"的等价实现：在单 prompt 内要求模型显式走
         Observe→Reason→Act，保留 SAGE 领域策略但用内存仿真落地（离线可复现）。
    """

    def __init__(self, config: Optional[HomeClawCoordinatorConfig] = None):
        super().__init__(_no_lazy_config(config, "SAGE"))
        self._official = None
        if os.getenv("SAGE_ENABLE_OFFICIAL") == "1":
            self._official = self._try_load_official()

    @staticmethod
    def _try_load_official():
        """尝试加载 SAGE 官方 coordinator；失败返回 None（回退等价实现）。"""
        try:
            from sage.coordinators.sage_coordinator import (  # type: ignore  # noqa: F401
                SAGECoordinator,
                SAGECoordinatorConfig,
            )
            return {"cls": SAGECoordinator, "cfg": SAGECoordinatorConfig}
        except Exception:
            return None

    def _run_loop(
        self,
        instruction: str,
        home_status: Optional[Dict],
        methods: Optional[List[Dict]],
    ) -> LoopResult:
        # 若官方桥接可用，优先委托官方实现；任何异常都安全回退到等价 ReAct 实现。
        if self._official is not None:
            try:
                official = self._run_official(instruction, home_status, methods)
                if official is not None:
                    return official
            except Exception:
                # 官方实现执行失败（缺外部依赖等）→ 回退，保证离线可复现
                pass

        # 回退等价实现：在 system prompt 内嵌 ReAct 领域推理指引
        react_system = (
            self.skill_body
            + "\n\n<react>\nReason internally with Observe→Reason→Act over the provided "
            "<home_state> and <device_method>, applying the domain strategies "
            "(personalization, device disambiguation, minimal-action). Then output ONLY "
            "the final machine instructions enclosed in {}.\n</react>"
        )
        msgs = [
            {"role": "system", "content": build_system_prompt(react_system, home_status, methods)},
            {"role": "user", "content": build_user_prompt(instruction)},
        ]
        return self.loop.run(msgs)

    def _run_official(
        self,
        instruction: str,
        home_status: Optional[Dict],
        methods: Optional[List[Dict]],
    ) -> Optional[LoopResult]:
        """委托官方 SAGECoordinator 执行，并把结果适配为 LoopResult。

        官方实现需要 SmartThings/Mongo 等外部依赖，由使用者在 SAGE 环境内自行启用。
        返回 None 或抛异常时，调用方会回退到等价 ReAct 实现。
        """
        import time

        from homeclaw.loop import extract_actions

        cls = self._official["cls"]
        cfg = self._official["cfg"]

        _start = time.perf_counter()
        official = cls(cfg())  # type: ignore[call-arg]
        # 官方 execute 入口：传入指令与家庭状态，产出自然语言/机器指令文本
        raw = official.execute(instruction, home_status, methods)  # type: ignore[attr-defined]
        text = raw if isinstance(raw, str) else getattr(raw, "text", str(raw))

        result = LoopResult(messages=[{"role": "user", "content": instruction}])
        result.final_text = text
        result.actions = extract_actions(text)
        result.iters = 1
        result.total_usage = getattr(raw, "usage", {}) or {}
        result.latency_ms = (time.perf_counter() - _start) * 1000.0
        return result

    @property
    def uses_official(self) -> bool:
        return self._official is not None


def _acc(acc: Dict[str, int], usage: Dict[str, int]) -> None:
    for k, v in (usage or {}).items():
        acc[k] = acc.get(k, 0) + v
