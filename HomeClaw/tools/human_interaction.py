"""HumanInteractionTool（P3，次优先）：追问澄清工具。

SAGE 用它在指令歧义时向用户提问。评测/离线场景没有真人，因此支持两种模式：
  - 回调模式：构造时传入 answer_fn(question)->str，由外部（测试夹具/UI）应答；
  - 自动模式：无回调时，记录问题并返回预设默认答复（保证链路不阻塞、可复现）。
所有提问都记入 asked，便于断言"是否正确触发了澄清"。
"""
from __future__ import annotations

from typing import Callable, List, Optional


class HumanInteractionTool:
    """向用户追问澄清。"""

    def __init__(self, answer_fn: Optional[Callable[[str], str]] = None,
                        default_answer: str = "yes"):
        self.answer_fn = answer_fn
        self.default_answer = default_answer
        self.asked: List[str] = []

    def ask(self, question: str) -> str:
        """提出澄清问题并返回答复（回调优先，否则默认答复）。"""
        self.asked.append(question)
        if self.answer_fn is not None:
            return self.answer_fn(question)
        return self.default_answer

    def clarification_count(self) -> int:
        return len(self.asked)
