"""持久化条件监控（M4）：内存条件事件队列。

替代 SAGE 的 Trigger Server 轮询机制。SAGE 的做法是：LLM 现写一个"无参、返回
True/False 的条件检测函数"，注册到独立 Trigger Server 持续轮询，条件满足时反向
触发协调器执行动作。

HomeClaw 的仿真版：
- 用内存 ConditionMonitor 管理若干 (condition, action) 注册项；
- condition 用"设备状态谓词"表达（room/device/attr/op/value），针对 home 对象树求值，
  避免真跑 LLM 写的任意代码，保证仿真可控、可复现；
- tick() 推进：每次调用检查所有未触发的注册项，满足则执行其 action 并标记 fired。

这样 persistence 维度即可在纯内存下测试："当条件满足 → 二次执行动作"两阶段。
"""
from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


# 支持的比较运算符
_OPS: Dict[str, Callable] = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


@dataclass
class Condition:
    """设备状态谓词。

    针对 home[room][device] 求值：
      - attr=None 时比较设备的 state（如 garage_door.state == "open"）；
      - attr!=None 时比较 attributes[attr]["value"]（如 light.brightness < 20）。
    """

    room: str
    device: str
    attr: Optional[str]
    op: str
    value: object

    def evaluate(self, home: Dict[str, Dict[str, object]]) -> bool:
        room = home.get(self.room)
        if not room:
            return False
        dev = room.get(self.device)
        if dev is None:
            return False
        status = dev.get_status()
        if self.attr is None:
            current = status.get("state")
        else:
            attrs = status.get("attributes", {})
            if self.attr not in attrs:
                return False
            current = attrs[self.attr].get("value")
        cmp = _OPS.get(self.op)
        if cmp is None:
            return False
        try:
            return bool(cmp(current, self.value))
        except TypeError:
            return bool(cmp(str(current), str(self.value)))


@dataclass
class Registration:
    """一条持久化注册：满足 condition 时执行 actions。"""

    condition: Condition
    actions: List[str]
    fired: bool = False
    fire_count: int = 0
    info: str = ""


class ConditionMonitor:
    """内存条件事件队列（替代 Trigger Server）。"""

    def __init__(self, executor):
        """executor 需实现 execute(action)（用于条件满足时落地动作）。"""
        self.executor = executor
        self.registrations: List[Registration] = []
        self.tick_count = 0

    def register(self, condition: Condition, actions: List[str], info: str = "") -> int:
        """注册一条 (condition → actions)，返回其索引。"""
        reg = Registration(condition=condition, actions=list(actions), info=info)
        self.registrations.append(reg)
        return len(self.registrations) - 1

    def tick(self, home: Dict[str, Dict[str, object]]) -> List[Dict]:
        """推进一步：检查所有未触发项，满足则执行其动作。

        返回本次被触发的 [{index, actions, results}]。
        """
        self.tick_count += 1
        fired_now: List[Dict] = []
        for i, reg in enumerate(self.registrations):
            if reg.fired:
                continue
            if reg.condition.evaluate(home):
                results = [self.executor.execute(a) for a in reg.actions]
                reg.fired = True
                reg.fire_count += 1
                fired_now.append({"index": i, "actions": reg.actions, "results": results})
        return fired_now

    def pending(self) -> int:
        """尚未触发的注册项数量。"""
        return sum(1 for r in self.registrations if not r.fired)

    def all_fired(self) -> bool:
        return all(r.fired for r in self.registrations) if self.registrations else True


def parse_condition(expr: str) -> Condition:
    """解析简单条件表达式：'room.device[.attr] <op> value'。

    示例：
      "garage.garage_door state == open"        （attr 省略 → 比较 state）
      "living_room.light.brightness < 20"
      "kitchen.trash state == full"
    支持两种写法：显式 'state' 关键字或省略 attr。
    """
    parts = expr.strip().split()
    if len(parts) < 3:
        raise ValueError(f"无法解析条件: {expr!r}")
    lhs, op, value_raw = parts[0], parts[-2], parts[-1]

    # 目标形如 'room.device[.attr]'；attr 是否省略由下方按段数解析决定
    target = lhs
    attr = None

    segs = target.split(".")
    if len(segs) == 2:
        room, device = segs
        attr = None
    elif len(segs) == 3:
        room, device, attr = segs
    else:
        raise ValueError(f"无法解析目标: {target!r}")

    # value 类型推断
    if value_raw.lstrip("-").isdigit():
        value: object = int(value_raw)
    else:
        value = value_raw

    return Condition(room=room, device=device, attr=attr, op=op, value=value)
