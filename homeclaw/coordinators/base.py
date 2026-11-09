"""Coordinator 抽象基类（M1）。

对齐 SAGE 的 Coordinator 契约：核心是 execute(command) 接口，
使得 HomeClaw 能无缝接入 SAGE 的 test_runner.py（M3）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from homeclaw.config import CoordinatorConfig


class BaseCoordinator(ABC):
    """所有 Coordinator 的抽象基类。"""

    def __init__(self, config: CoordinatorConfig):
        self.config = config

    @abstractmethod
    def execute(self, command: str) -> str:
        """SAGE 兼容入口：输入 '<user>: <command>'，执行并返回回复文本。

        用于五维评测（执行后由 executor 落地改状态，供状态断言）。
        """
        raise NotImplementedError

    @abstractmethod
    def predict_actions(
        self, home_status: Dict, instruction: str, methods: Optional[List[Dict]] = None
    ) -> str:
        """HomeBench 兼容入口：只输出动作文本，不落地。

        用于幻觉六型评测（静态文本比对 EM/P/R/F1）。
        """
        raise NotImplementedError
