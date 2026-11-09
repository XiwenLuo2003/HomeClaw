"""ApiUsagePlanner（P3，次优先）：SAGE SmartThingsTool 的 api_usage_planner 等价物。

作用：给定用户意图 + 可用 methods，规划出应调用哪些 room.device.op(args)。
这里提供一个零依赖的规则版规划器（关键词 -> 操作映射），
用于在 mock 场景下产出结构化计划；接真实 LLM 时可作为 few-shot 约束。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional


class ApiUsagePlanner:
    """把自然语言意图规划为 room.device.op(args) 动作列表。"""

    def __init__(self, methods: Optional[List[Dict]] = None):
        # methods: [{room_name, device_name, operation, parameters}]
        self.index: Dict[str, set] = {}
        for m in (methods or []):
            room = m.get("room_name", "None")
            key = m["device_name"] if room in ("None", None) else f"{room}.{m['device_name']}"
            self.index.setdefault(key, set()).add(m["operation"])

    def supported_ops(self, room: str, device: str) -> set:
        return self.index.get(f"{room}.{device}", self.index.get(device, set()))

    def plan(self, room: str, device: str, intent: str) -> Optional[str]:
        """据意图关键词选择一个受支持的操作，返回动作文本或 None。"""
        ops = self.supported_ops(room, device)
        low = intent.lower()
        num = re.search(r"(-?\d+)", low)
        candidates = [
            ("turn_off", ("off", "turn off", "close", "stop")),
            ("turn_on", ("on", "turn on", "open", "start")),
            ("set_brightness", ("bright", "dim", "brightness")),
            ("set_volume", ("volume", "loud", "quiet")),
            ("set_temperature", ("temperature", "warm", "cool", "degree")),
            ("set_channel", ("channel",)),
        ]
        for op, kws in candidates:
            if op in ops and any(kw in low for kw in kws):
                if op.startswith("set_") and num:
                    return f"{room}.{device}.{op}({num.group(1)})"
                if not op.startswith("set_"):
                    return f"{room}.{device}.{op}()"
        # 兜底：若有 turn_on 且未识别，返回 turn_on
        if "turn_on" in ops:
            return f"{room}.{device}.turn_on()"
        return None
