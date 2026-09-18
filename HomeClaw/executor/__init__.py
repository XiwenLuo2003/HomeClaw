"""executor 包。

导出：
- ActionExecutor / NullExecutor        : 执行器抽象与空实现
- SimulateExecutor                     : 【M2】内存仿真执行器（+【M4】持久化 tick）
- parse_action / build_home / snapshot_home
- ConditionMonitor / Condition / parse_condition : 【M4】持久化条件监控
- RealDeviceExecutor                   : 【M5】真机执行器
- DeviceCloudAdapter / MockCloudAdapter / SmartThingsAdapter / HomeAssistantAdapter : 【M5】设备云适配器
"""
from homeclaw.executor.base import ActionExecutor, NullExecutor
from homeclaw.executor.parser import parse_action, ParsedAction, ActionParseError
from homeclaw.executor.home_builder import build_home, snapshot_home, BuildReport
from homeclaw.executor.simulate_executor import SimulateExecutor
from homeclaw.executor.condition_monitor import (
    ConditionMonitor,
    Condition,
    Registration,
    parse_condition,
)
from homeclaw.executor.cloud_adapter import (
    DeviceCloudAdapter,
    DeviceResolveError,
    MockCloudAdapter,
    SmartThingsAdapter,
    HomeAssistantAdapter,
)
from homeclaw.executor.real_executor import RealDeviceExecutor
from homeclaw.executor.factory import (
    make_executor,
    BACKENDS,
    SIM,
    MOCK_CLOUD,
    SMARTTHINGS,
    HOMEASSISTANT,
)

__all__ = [
    "ActionExecutor", "NullExecutor", "SimulateExecutor",
    "parse_action", "ParsedAction", "ActionParseError",
    "build_home", "snapshot_home", "BuildReport",
    "ConditionMonitor", "Condition", "Registration", "parse_condition",
    "RealDeviceExecutor",
    "DeviceCloudAdapter", "DeviceResolveError",
    "MockCloudAdapter", "SmartThingsAdapter", "HomeAssistantAdapter",
    "make_executor", "BACKENDS", "SIM", "MOCK_CLOUD", "SMARTTHINGS", "HOMEASSISTANT",
]
