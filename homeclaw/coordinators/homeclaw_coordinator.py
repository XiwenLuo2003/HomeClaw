"""HomeClawCoordinator —— OpenClaw 单循环内核，兼容 SAGE / HomeBench 双入口（M1）。

一份内核，两个入口：
  - execute(command)                      → SAGE 五维评测（执行后落地改状态）
  - predict_actions(home_status, instr…)  → HomeBench 幻觉评测（只输出动作文本）

两者共享同一个 AgentLoop 与同一个 smart-home Skill。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from homeclaw.config import HomeClawCoordinatorConfig
from homeclaw.coordinators.base import BaseCoordinator
from homeclaw.executor import ActionExecutor, NullExecutor
from homeclaw.llm import create_llm_client
from homeclaw.loop import AgentLoop, LoopResult
from homeclaw.prompt import (
    build_system_prompt,
    build_lazy_system_prompt,
    build_user_prompt,
    load_skill_body,
    load_skill_overview,
    split_user_command,
)


@dataclass
class ExecuteResult:
    """execute() 的结构化返回（同时提供 __str__ 以兼容 SAGE 期望的字符串返回）。"""

    reply: str = ""
    actions: List[str] = field(default_factory=list)
    exec_results: List[Dict] = field(default_factory=list)
    iters: int = 0
    usage: Dict[str, int] = field(default_factory=dict)
    snapshot: Optional[Dict] = None  # 执行后设备状态快照（供 SAGE 五维断言）
    latency_ms: float = 0.0          # 【M4】端到端耗时
    skill_loaded: bool = False       # 【M6】是否触发了技能全文懒加载

    def __str__(self) -> str:
        return self.reply


class HomeClawCoordinator(BaseCoordinator):
    """HomeClaw 的核心 Coordinator。"""

    def __init__(self, config: Optional[HomeClawCoordinatorConfig] = None):
        config = config or HomeClawCoordinatorConfig()
        super().__init__(config)
        self.config: HomeClawCoordinatorConfig = config

        # 加载 Skill 正文（全文）与规则速览段（懒加载时始终注入的最短规则）
        self.skill_body = load_skill_body(
            config.skill_config.skill_path, config.skill_config.skill_name
        )
        self.skill_overview = load_skill_overview(
            config.skill_config.skill_path, config.skill_config.skill_name
        )
        # 是否启用两级懒加载（对齐 OpenClaw 省 token 卖点）
        self.lazy_load: bool = config.skill_config.lazy_load
        # LLM 客户端
        self.llm = create_llm_client(config.llm_config)
        # 单主循环：懒加载模式下注入 skill_provider（模型 READ_SKILL 时回传全文）
        self.loop = AgentLoop(
            self.llm,
            max_iters=config.llm_config.max_iters,
            skill_provider=(self._provide_skill if self.lazy_load else None),
        )
        # 执行器：未注入时默认 NullExecutor（M2 注入 SimulateExecutor）
        self.executor: ActionExecutor = config.executor or NullExecutor()

    def _provide_skill(self, name: str) -> str:
        """懒加载回调：返回技能完整正文（供 AgentLoop 在 READ_SKILL 时注入）。"""
        return self.skill_body

    # ------------------------------------------------------------------ #
    # SAGE 兼容入口：五维评测                                              #
    # ------------------------------------------------------------------ #
    def execute(self, command: str) -> ExecuteResult:
        """输入 '<user>: <command>'，单循环产出动作文本并经 executor 落地。

        返回 ExecuteResult（其 __str__ 为回复文本，兼容 SAGE 对字符串返回的期望）。
        """
        user_name, instruction = split_user_command(command)

        # M1：SAGE 场景的 home_status/method 由 executor 侧持有（M2/M3 注入），
        # 此处若 executor 暴露了 snapshot，则注入 prompt；否则仅用 Skill 正文。
        home_status = getattr(self.executor, "home_status", None)
        methods = getattr(self.executor, "methods", None)

        loop_result = self._run_loop(instruction, home_status, methods)

        # 落地执行每条动作（error_input 会被 executor 标记 rejected）
        exec_results = self.executor.execute_batch(loop_result.actions)

        # 若执行器支持状态快照（SimulateExecutor），导出供 SAGE 五维断言
        snapshot = None
        if hasattr(self.executor, "snapshot"):
            snapshot = self.executor.snapshot()

        reply = self._compose_reply(user_name, loop_result, exec_results)
        return ExecuteResult(
            reply=reply,
            actions=loop_result.actions,
            exec_results=exec_results,
            iters=loop_result.iters,
            usage=loop_result.total_usage,
            snapshot=snapshot,
            latency_ms=loop_result.latency_ms,
            skill_loaded=loop_result.skill_loaded,
        )

    # ------------------------------------------------------------------ #
    # HomeBench 兼容入口：幻觉评测                                          #
    # ------------------------------------------------------------------ #
    def predict_actions(
        self,
        home_status: Dict,
        instruction: str,
        methods: Optional[List[Dict]] = None,
    ) -> str:
        """只输出动作文本 {..., ...} / {error_input}，不落地。

        返回符合 HomeBench compute_accuracy 期望的字符串（花括号包裹）。
        """
        loop_result = self._run_loop(instruction, home_status, methods)
        if not loop_result.actions:
            return "{error_input}"
        return "{" + ", ".join(loop_result.actions) + "}"

    # ------------------------------------------------------------------ #
    # 内部：跑一次单主循环                                                  #
    # ------------------------------------------------------------------ #
    def _run_loop(
        self,
        instruction: str,
        home_status: Optional[Dict],
        methods: Optional[List[Dict]],
    ) -> LoopResult:
        # 懒加载：只注入规则速览 + read_skill 提示；否则注入全文
        if self.lazy_load:
            system_prompt = build_lazy_system_prompt(self.skill_overview, home_status, methods)
        else:
            system_prompt = build_system_prompt(self.skill_body, home_status, methods)
        user_prompt = build_user_prompt(instruction)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self.loop.run(messages)

    @staticmethod
    def _compose_reply(
        user_name: str, loop_result: LoopResult, exec_results: List[Dict]
    ) -> str:
        """把执行结果组织为一句自然语言回复（M1 简版）。"""
        ok = [r for r in exec_results if r.get("status") in ("ok", "recorded")]
        rejected = [r for r in exec_results if r.get("status") == "rejected"]
        prefix = f"[{user_name}] " if user_name else ""
        if not exec_results:
            return f"{prefix}No actionable instruction."
        parts = []
        if ok:
            parts.append(f"executed {len(ok)} action(s): " + ", ".join(a['action'] for a in ok))
        if rejected:
            parts.append(f"{len(rejected)} rejected (error_input)")
        return prefix + "; ".join(parts)
