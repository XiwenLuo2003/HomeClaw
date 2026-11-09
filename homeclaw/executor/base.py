"""执行器接口（M1 占位）。

M1 只交付"Skill + 单主循环内核"，因此这里仅提供：
  - ActionExecutor 抽象接口（契约定稿）；
  - NullExecutor：不落地，仅记录动作（供 predict_actions 文本模式 / 冒烟）。

完整的 SimulateExecutor（对接 HomeBench device.py，改内存状态）与
RealDeviceExecutor（真机接口）属于 M2 / M5，见设计文档 04。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class ActionExecutor(ABC):
    """动作执行器抽象。输入动作文本，负责将其落地。"""

    @abstractmethod
    def execute(self, action: str) -> Dict:
        """执行单条动作文本，返回 {status, ...}。"""
        raise NotImplementedError

    def execute_batch(self, actions: List[str]) -> List[Dict]:
        return [self.execute(a) for a in actions]


class NullExecutor(ActionExecutor):
    """空执行器：不改变任何状态，仅记录收到的动作。

    用途：
      - predict_actions() 的纯文本预测模式（HomeBench 幻觉评测只比文本）；
      - M1 冒烟测试下 execute() 也可临时用它跑通链路。

    可选地持有 home_status / methods 快照：Coordinator.execute() 会读取
    executor 的这两个属性并注入 system prompt。M2 的 SimulateExecutor 将以
    "内存设备状态"提供同名属性，从而替代 SAGE 原本的 MongoDB 快照。
    """

    def __init__(self, home_status: Optional[Dict] = None,
                 methods: Optional[List[Dict]] = None) -> None:
        self.executed: List[str] = []
        self.home_status = home_status
        self.methods = methods

    def execute(self, action: str) -> Dict:
        self.executed.append(action)
        status = "rejected" if action.strip() == "error_input" else "recorded"
        return {"status": status, "action": action}
