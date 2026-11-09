"""RealDeviceExecutor（M5）：把动作文本下发到真实设备云。

与 SimulateExecutor 使用**完全相同**的动作文本格式 room.device.operation(param)，
仅把"改内存状态"替换为"通过 DeviceCloudAdapter 调真实 API"。因此实验期用
SimulateExecutor、落地期换 RealDeviceExecutor，动作格式零改动。

流程：动作文本 → parse_action → error_input 处理 → adapter.resolve → adapter.call
"""
from __future__ import annotations

from typing import Dict, List, Optional

from homeclaw.executor.base import ActionExecutor
from homeclaw.executor.parser import parse_action, ActionParseError
from homeclaw.executor.cloud_adapter import DeviceCloudAdapter, DeviceResolveError


class RealDeviceExecutor(ActionExecutor):
    """真机执行器：经 DeviceCloudAdapter 下发动作到真实设备。"""

    def __init__(self, adapter: DeviceCloudAdapter,
                 home_status: Optional[Dict] = None,
                 methods: Optional[List[Dict]] = None):
        """
        adapter     : 具体设备云适配器（Mock / SmartThings / HomeAssistant）
        home_status : 可选，用于注入 prompt（与 SimulateExecutor 属性对齐）
        methods     : 可选，用于注入 prompt
        """
        self.adapter = adapter
        self.home_status = home_status
        self.methods = methods
        self.executed: List[str] = []

    def execute(self, action: str) -> Dict:
        self.executed.append(action)

        try:
            parsed = parse_action(action)
        except ActionParseError as e:
            return {"status": "error", "reason": "parse_error", "detail": str(e), "action": action}

        # LLM 主动拒答
        if parsed is None:
            return {"status": "rejected", "reason": "error_input", "action": action}

        room = parsed.room
        if room is None:
            # 无房间前缀：以设备名作为房间占位，交由 adapter.resolve 处理
            room = parsed.device

        # 解析真实设备标识
        try:
            device_id = self.adapter.resolve(room, parsed.device)
        except DeviceResolveError as e:
            return {"status": "error", "reason": "unresolved_device", "detail": str(e), "action": action}

        # 下发调用
        try:
            resp = self.adapter.call(device_id, parsed.op, parsed.args)
        except Exception as e:  # 网络/HTTP 等异常统一兜底
            return {"status": "error", "reason": "call_failed", "detail": str(e), "action": action}

        return {
            "status": resp.get("status", "ok"),
            "action": action,
            "room": parsed.room,
            "device": parsed.device,
            "op": parsed.op,
            "device_id": device_id,
            "response": resp,
        }

    def snapshot(self) -> Dict:
        """从适配器聚合当前状态（若适配器支持 get_status）。"""
        out: Dict = {}
        registry = getattr(self.adapter, "device_registry", None)
        if not registry:
            return out
        for (room, device), device_id in registry.items():
            try:
                out.setdefault(room, {})[device] = self.adapter.get_status(device_id)
            except NotImplementedError:
                pass
        return out
