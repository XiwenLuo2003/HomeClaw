"""SimulateExecutor（M2）：默认执行器，对接 device.py 仿真，改内存状态。

流程：
    动作文本 → parse_action → 合法性校验 → 调 device.operations[op](*args) → 改内存状态

合法性校验对齐 error_input 语义：
    - 房间不存在        → status=error, reason=unexist_room
    - 设备不存在        → status=error, reason=unexist_device
    - 操作/属性不存在   → status=error, reason=unexist_attribute
    - LLM 主动拒答      → status=rejected, reason=error_input

SimulateExecutor 暴露 home_status / methods 属性，供 HomeClawCoordinator.execute()
注入 system prompt；执行后可用 snapshot() 导出状态供 SAGE 五维断言。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from homeclaw.executor.base import ActionExecutor
from homeclaw.executor.parser import parse_action, ActionParseError
from homeclaw.executor.home_builder import build_home, snapshot_home
from homeclaw.executor.condition_monitor import (
    ConditionMonitor,
    Condition,
    parse_condition,
)


class SimulateExecutor(ActionExecutor):
    """内存仿真执行器（替代 SAGE 的 MongoDB 状态存储）。"""

    def __init__(
        self,
        home_status: Optional[Dict] = None,
        methods: Optional[List[Dict]] = None,
    ):
        """
        home_status : HomeBench 风格的初始设备状态字典
        methods     : 设备方法清单（注入 prompt 用；执行侧以 device.operations 为准）
        """
        self.home_status = home_status
        self.methods = methods
        self.executed: List[str] = []
        # 构建仿真对象树
        if home_status is not None:
            self.home, self.build_report = build_home(home_status)
        else:
            self.home, self.build_report = {}, None
        # 【M4】持久化条件监控（内存事件队列，替代 Trigger Server）
        self.monitor = ConditionMonitor(self)

    # ------------------------------------------------------------------ #
    def execute(self, action: str) -> Dict:
        """执行单条动作文本，返回结构化结果。"""
        self.executed.append(action)

        try:
            parsed = parse_action(action)
        except ActionParseError as e:
            return {"status": "error", "reason": "parse_error", "detail": str(e), "action": action}

        # LLM 主动拒答
        if parsed is None:
            return {"status": "rejected", "reason": "error_input", "action": action}

        # —— 合法性校验（幻觉检测）——
        room = parsed.room
        # 定位设备：优先按 room 定位；room 为空时在所有房间里找该设备
        device_obj, resolve_reason = self._resolve_device(room, parsed.device)
        if device_obj is None:
            return {"status": "error", "reason": resolve_reason, "action": action}

        if parsed.op not in getattr(device_obj, "operations", {}):
            return {"status": "error", "reason": "unexist_attribute", "action": action}

        # —— 真正执行仿真 ——
        try:
            device_obj.operations[parsed.op](*parsed.args)
        except TypeError as e:
            return {"status": "error", "reason": "bad_arguments", "detail": str(e), "action": action}

        return {
            "status": "ok",
            "action": action,
            "room": room,
            "device": parsed.device,
            "op": parsed.op,
            "state": device_obj.get_status(),
        }

    # ------------------------------------------------------------------ #
    def _resolve_device(self, room: Optional[str], device: str):
        """按 room/device 定位仿真对象；返回 (obj|None, reason)。"""
        if room is not None:
            if room not in self.home:
                return None, "unexist_room"
            if device not in self.home[room]:
                return None, "unexist_device"
            return self.home[room][device], "ok"
        # 无房间前缀：在所有房间里找同名设备（取第一个）
        for _room, devices in self.home.items():
            if device in devices:
                return devices[device], "ok"
        return None, "unexist_device"

    # ------------------------------------------------------------------ #
    def snapshot(self) -> Dict:
        """导出当前内存状态（供 SAGE 五维断言）。"""
        return snapshot_home(self.home)

    # ------------------------------------------------------------------ #
    # 【M4】持久化条件监控 API                                             #
    # ------------------------------------------------------------------ #
    def register_persistent(self, condition, actions: List[str], info: str = "") -> int:
        """注册一条持久化规则：condition 满足时执行 actions。

        condition 可为：
          - Condition 对象；
          - 字符串表达式（形如 "garage.garage_door state == open"），自动解析。
        返回注册索引。
        """
        if isinstance(condition, str):
            condition = parse_condition(condition)
        return self.monitor.register(condition, actions, info=info)

    def tick(self) -> List[Dict]:
        """推进一步：检查所有已注册条件，满足则触发其动作。返回本次触发列表。"""
        return self.monitor.tick(self.home)

    def pending_conditions(self) -> int:
        """尚未触发的持久化规则数量。"""
        return self.monitor.pending()
