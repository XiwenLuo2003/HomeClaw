"""HomeClaw：SAGE 学术资产在 OpenClaw 现代 Skill 范式下的重建。

里程碑 M1 交付：smart-home Skill + 单主循环内核（HomeClawCoordinator）。

模块结构：
- config      : 全局与 Coordinator 配置（含 CoordinatorType 枚举预留）
- skills      : 能力单元（smart-home/SKILL.md）
- llm         : LLM 抽象层（Provider 无关）
- prompt      : system prompt 拼装 + home_status/method 序列化
- loop        : 单主循环内核（agent_loop）
- coordinators: HomeClawCoordinator（execute / predict_actions 双入口）
- executor    : 执行器接口（M1 仅提供 stub，完整仿真见 M2）
"""

__version__ = "0.1.0-m1"

from homeclaw.coordinators.homeclaw_coordinator import (
    HomeClawCoordinator,
    HomeClawCoordinatorConfig,
)

__all__ = ["HomeClawCoordinator", "HomeClawCoordinatorConfig", "__version__"]
