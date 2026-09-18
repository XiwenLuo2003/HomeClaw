"""单主循环内核（agent_loop）—— HomeClaw 的"心脏"（M1）。

对标 OpenClaw 的 agent-loop：单一 while 循环调用 LLM，若产出工具调用则执行、
把 toolResult 回传后继续循环，直到不再有工具调用或达到 max_iters。

M1 的简化取舍：
  - 智能家居动作以"动作文本 {room.device.op(param)}"形式承载，属于本 Skill 的
    最终产物，因此主循环的常规终止条件是"LLM 输出了动作文本 / 无进一步工具调用"。
  - 保留 tool_calls 分支与 toolResult 回传机制（用于 read SKILL 正文等），
    与 OpenClaw 语义一致；真实 Function-Calling 工具注册在 M3 完善。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from homeclaw.llm import BaseLLMClient, LLMResponse


# 匹配 {...} 内的机器指令
_BRACE_RE = re.compile(r"\{(.*?)\}", re.S)
# 【M6】懒加载：匹配模型请求加载完整技能正文的文本工具调用
_READ_SKILL_RE = re.compile(r"READ_SKILL:\s*([\w-]+)", re.I)


def wants_skill(text: str) -> Optional[str]:
    """若模型输出请求加载技能全文（READ_SKILL: <name>），返回技能名，否则 None。"""
    m = _READ_SKILL_RE.search(text or "")
    return m.group(1) if m else None


def extract_actions(text: str) -> List[str]:
    """从 LLM 输出中提取动作文本列表。

    - 优先取 {} 内内容，按逗号切分；
    - 去空白、去空项；
    - 保留 'error_input' 原样。
    对齐 HomeBench compute_accuracy 的清洗逻辑（去空格/换行、取花括号内内容）。
    """
    cleaned = text.replace("<Machine instructions:>", "")
    matches = _BRACE_RE.findall(cleaned)
    if not matches:
        # 没有花括号时，尝试把整行当作单条动作（容错）
        body = cleaned.strip()
        return [body] if body else []
    # 合并所有花括号内内容
    body = ",".join(matches)
    body = body.replace("\n", "")
    items = [seg.strip() for seg in body.split(",")]
    return [it for it in items if it]


@dataclass
class LoopResult:
    """单主循环的运行结果。"""

    actions: List[str] = field(default_factory=list)  # 提取到的动作文本
    final_text: str = ""                               # LLM 最终原始输出
    iters: int = 0                                      # 实际迭代轮数（评测维度）
    total_usage: Dict[str, int] = field(default_factory=dict)  # 累计 token
    messages: List[Dict] = field(default_factory=list)         # 完整对话轨迹
    latency_ms: float = 0.0                             # 【M4】端到端耗时（毫秒）
    skill_loaded: bool = False                          # 【M6】本轮是否触发了技能全文懒加载


class AgentLoop:
    """OpenClaw 式单主循环。"""

    def __init__(
        self,
        llm: BaseLLMClient,
        max_iters: int = 5,
        tool_handler: Optional[Callable[[dict], str]] = None,
        skill_provider: Optional[Callable[[str], str]] = None,
    ):
        """
        llm            : LLM 客户端
        max_iters      : 最大迭代轮数（防死循环 + 统计调用轮数）
        tool_handler   : 可选的结构化工具调用处理器（Function-Calling）
        skill_provider : 【M6】懒加载技能全文提供者，输入技能名返回完整正文文本。
                         当模型输出 "READ_SKILL: <name>" 时被调用，用于两级懒加载。
        """
        self.llm = llm
        self.max_iters = max_iters
        self.tool_handler = tool_handler
        self.skill_provider = skill_provider

    def run(self, messages: List[Dict]) -> LoopResult:
        """执行主循环。messages 为初始对话（system + user）。"""
        import time

        convo = list(messages)
        result = LoopResult(messages=convo)
        total_usage: Dict[str, int] = {}
        _start = time.perf_counter()

        for i in range(1, self.max_iters + 1):
            result.iters = i
            resp: LLMResponse = self.llm.chat(convo)
            _accumulate_usage(total_usage, resp.usage)

            # 记录助手消息
            convo.append({"role": "assistant", "content": resp.text})

            # —— 分支 0：懒加载技能全文（READ_SKILL: <name>）——
            skill_name = wants_skill(resp.text) if self.skill_provider else None
            if skill_name and not result.skill_loaded:
                skill_full = self.skill_provider(skill_name)
                convo.append(
                    {
                        "role": "tool",
                        "tool_call_id": f"read_skill:{skill_name}",
                        "content": (
                            f"<skill name=\"{skill_name}\">\n{skill_full}\n</skill>\n"
                            "Now produce the final machine instructions."
                        ),
                    }
                )
                result.skill_loaded = True
                continue

            # —— 分支 1：有结构化工具调用（如 read SKILL 正文）——
            if resp.tool_calls and self.tool_handler is not None:
                for call in resp.tool_calls:
                    tool_result = self.tool_handler(call)
                    convo.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id", ""),
                            "content": tool_result,
                        }
                    )
                # 回传 toolResult 后继续下一轮（重新调用 LLM）
                continue

            # —— 分支 2：无工具调用 → 视为产出最终动作文本，终止循环 ——
            result.final_text = resp.text
            result.actions = extract_actions(resp.text)
            break

        result.total_usage = total_usage
        result.latency_ms = (time.perf_counter() - _start) * 1000.0
        return result


def _accumulate_usage(acc: Dict[str, int], usage: Dict[str, int]) -> None:
    for k, v in (usage or {}).items():
        acc[k] = acc.get(k, 0) + v
