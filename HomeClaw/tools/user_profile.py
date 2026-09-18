"""UserProfileTool（P3，最高优先）：个性化维度的核心工具。

职责：
  1. 汇聚某用户的结构化偏好（sage_dataset.load_user_preferences）+ 画像 profile；
  2. 通过 MemoryBank 检索与当前指令最相关的历史记忆；
  3. 产出一段"个性化上下文"文本，可注入 system prompt，让 LLM 据此个性化执行；
  4. 提供 query(key) 便捷接口，供五维用例做个性化断言（如偏好红色助眠灯光）。

这是把 personalization 从"占位（只会开灯）"变"真测（据偏好选色温/频道）"的关键。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from homeclaw.eval import sage_dataset
from homeclaw.tools.memory_bank import MemoryBank


class UserProfileTool:
    """用户画像 + 记忆检索工具。"""

    def __init__(self, user: str = "amal"):
        self.user = user
        data = sage_dataset.get_user_profile(user)
        self.preferences: Dict[str, Any] = data.get("preferences", {}) or {}
        self.profile: Dict[str, Any] = data.get("profile", {}) or {}
        self.memory = MemoryBank(user)

    def query(self, key: str, default: Optional[Any] = None) -> Any:
        """按键查偏好/画像（先查 preferences，再查 profile）。"""
        if key in self.preferences:
            return self.preferences[key]
        if key in self.profile:
            return self.profile[key]
        return default

    def relevant_memories(self, instruction: str, k: int = 3) -> List[str]:
        """检索与指令相关的历史记忆文本。"""
        return [e["text"] for e in self.memory.retrieve(instruction, k=k)]

    def personalization_context(self, instruction: str) -> str:
        """构造可注入 system prompt 的个性化上下文段。"""
        lines: List[str] = ["<user_profile>", f"user: {self.user}"]
        if self.profile:
            for k, v in self.profile.items():
                lines.append(f"  {k}: {v}")
        mems = self.relevant_memories(instruction)
        if mems:
            lines.append("  relevant_history:")
            for m in mems:
                lines.append(f"    - {m}")
        lines.append("</user_profile>")
        return "\n".join(lines)
