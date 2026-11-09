"""执行器工厂（P5）：一键切换仿真 / 真机后端。

评测默认走 SimulateExecutor（内存仿真、可复现）。要做真机评测/演示时，只需把
backend 从 "sim" 切到 "mock_cloud" / "smartthings" / "homeassistant"，动作文本格式
（room.device.op(arg)）零改动即可下发到真实设备云。

mock_cloud 后端会依据 home_status 自动登记 (room, device) 设备表，因此其 snapshot()
可用于状态断言，让"真机链路"也能跑五维评测（不接真设备、可复现）。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from homeclaw.executor.simulate_executor import SimulateExecutor
from homeclaw.executor.real_executor import RealDeviceExecutor
from homeclaw.executor.cloud_adapter import (
    MockCloudAdapter, SmartThingsAdapter, HomeAssistantAdapter,
)

SIM = "sim"
MOCK_CLOUD = "mock_cloud"
SMARTTHINGS = "smartthings"
HOMEASSISTANT = "homeassistant"
BACKENDS = [SIM, MOCK_CLOUD, SMARTTHINGS, HOMEASSISTANT]


def _registry_from_home(home_status):
    """从 home_status 自动生成 (room, device) -> 伪 device_id 映射（供 MockCloudAdapter）。"""
    registry = {}
    if not home_status:
        return registry
    for room, room_val in home_status.items():
        if not isinstance(room_val, dict):
            continue
        for device, dev_val in room_val.items():
            if device == "room_name" or not isinstance(dev_val, dict):
                continue
            registry[(room, device)] = "mock-%s-%s" % (room, device)
    return registry


def make_executor(backend=SIM, home_status=None, methods=None, adapter=None):
    """按 backend 构造执行器。

    backend:
      - "sim"          : SimulateExecutor（默认，内存仿真）
      - "mock_cloud"   : RealDeviceExecutor + MockCloudAdapter（真机链路，离线可复现）
      - "smartthings"  : RealDeviceExecutor + SmartThingsAdapter（需 token）
      - "homeassistant": RealDeviceExecutor + HomeAssistantAdapter（需 url/token）
    adapter: 可选自定义 DeviceCloudAdapter（覆盖 backend 默认适配器）。
    """
    if backend == SIM:
        return SimulateExecutor(home_status=home_status, methods=methods)
    if adapter is None:
        if backend == MOCK_CLOUD:
            adapter = MockCloudAdapter(devices=_registry_from_home(home_status))
        elif backend == SMARTTHINGS:
            adapter = SmartThingsAdapter()
        elif backend == HOMEASSISTANT:
            adapter = HomeAssistantAdapter()
        else:
            raise ValueError("未知 executor backend: %r（可选 %s）" % (backend, BACKENDS))
    return RealDeviceExecutor(adapter=adapter, home_status=home_status, methods=methods)
