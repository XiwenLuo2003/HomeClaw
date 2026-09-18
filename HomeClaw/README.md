# HomeClaw 代码实现（里程碑进度）

本目录为 HomeClaw 的**代码实现**（区别于上层设计文档 `../*.md`）。

## 当前进度

| 里程碑 | 状态 | 交付物 |
|---|---|---|
| **M1 · Skill + 单主循环内核** | ✅ 完成 | `smart-home/SKILL.md`、`HomeClawCoordinator`（`execute` / `predict_actions`）、单主循环 `AgentLoop`、LLM 抽象层、prompt 构建、冒烟测试 |
| **M2 · 执行器 + 仿真** | ✅ 完成 | `ActionExecutor`、`SimulateExecutor`、`parse_action`、`build_home`、迁移 `device.py`（16 类设备）、冒烟测试 |
| **M3 · 双评测 + 对比** | ✅ 完成 | `metrics`（EM/P/R/F1+新增维度）、`homebench_adapter`（六型）、`sage_adapter`（五维+新增维度）、`HomeBenchRunner`/`SageRunner`（四系统）、真实 LLM Provider（OpenAI/Anthropic）、冒烟测试 |
| **M4 · 持久化 + 新增维度** | ✅ 完成 | `condition_monitor`（内存条件事件队列，替代 Trigger Server）、`SimulateExecutor.register_persistent`/`tick`、persistence & command_chaining 维度用例、latency 统计、冒烟测试 |
| M5 · 真机接口（可选） | ✅ 完成 | `RealDeviceExecutor`、`DeviceCloudAdapter`（`MockCloudAdapter`/`SmartThingsAdapter`/`HomeAssistantAdapter`）、仿真/真机一套格式一致性、冒烟测试 |

---

## M1 目录结构

```
homeclaw/
├── __init__.py                     # 包入口，导出 HomeClawCoordinator
├── config.py                       # LLMConfig / SkillConfig / CoordinatorConfig / CoordinatorType
├── llm.py                          # LLM 抽象层 + MockLLMClient（离线冒烟）
├── prompt.py                       # SKILL 加载、home_status/method 序列化、system prompt 拼装
├── loop.py                         # 单主循环内核 AgentLoop + 动作提取 extract_actions
├── skills/
│   └── smart-home/
│       └── SKILL.md                # 领域知识 + 动作格式 + error_input 规则
├── coordinators/
│   ├── base.py                     # BaseCoordinator（execute / predict_actions 契约）
│   └── homeclaw_coordinator.py     # HomeClawCoordinator（双入口内核）
├── devices/                        # 【M2】设备仿真类
│   └── device.py                   # 迁移自 HomeBench，16 类设备 + device_map
├── executor/
│   ├── base.py                     # ActionExecutor 抽象 + NullExecutor
│   ├── parser.py                   # 【M2】parse_action（动作文本解析 + 参数类型推断）
│   ├── home_builder.py             # 【M2】build_home / snapshot_home（对象树构建/导出）
│   ├── simulate_executor.py        # 【M2】SimulateExecutor（内存仿真）+【M4】持久化 tick
│   ├── condition_monitor.py        # 【M4】ConditionMonitor 内存条件事件队列（替代 Trigger Server）
│   └── __init__.py
├── eval/                           # 【M3】双评测适配器
│   ├── metrics.py                  # EM/P/R/F1 + 新增维度（error_input 准确率/过度执行/拒答）
│   ├── homebench_adapter.py        # 幻觉六型评测（加载数据集 + 分型统计）
│   ├── sage_adapter.py             # 五维评测（@register/get_tests + 新增维度）
│   └── __init__.py
├── runners/                        # 【M3】四系统对比调度
│   └── __init__.py                 # HomeBenchRunner / SageRunner
└── coordinators/baselines.py       # 【M3】OnePromptCoordinator / SashaCoordinator（对照组）
tests/
├── smoke_m1.py                     # M1 冒烟测试
├── smoke_m2.py                     # 【M2】执行器 + 仿真冒烟测试
├── smoke_m3.py                     # 【M3】双评测 + 四系统对比冒烟测试
└── smoke_m4.py                     # 【M4】持久化条件监控 + 新增维度冒烟测试
```

运行 M4 冒烟：

```bash
cd HomeClaw
python3 tests/smoke_m4.py    # 条件解析/求值/tick 闭环 + persistence 维度 + latency 采集
```

### M4 用法：持久化条件监控

```python
from homeclaw.executor import SimulateExecutor

ex = SimulateExecutor(home_status)
# 注册："当 balcony 灯变为 on 时，关闭 living_room 灯"
ex.register_persistent("balcony.light state == on", ["living_room.light.turn_off()"])

ex.tick()  # 条件未满足 → 不触发
ex.execute("balcony.light.turn_on()")
fired = ex.tick()    # 条件满足 → 触发二次执行，living_room 灯被关闭
```

> 内存 `ConditionMonitor` 替代 SAGE 的 Trigger Server 轮询：注册 (condition→actions)，
> 由 `tick()` 推进检查并触发，实现 persistence 维度"条件触发→二次执行"两阶段的纯内存仿真。

运行 M3 冒烟：

```bash
cd HomeClaw
python3 tests/smoke_m3.py    # metrics / 数据加载 / 四系统 HomeBench+SAGE 对比 / Provider 工厂
```

### M3 用法：四系统对比评测

```python
from homeclaw.config import LLMConfig
from homeclaw.runners import HomeBenchRunner, SageRunner

# —— HomeBench 幻觉六型：四系统对比 ——
hb = HomeBenchRunner(limit=100, llm_config=LLMConfig(provider="mock"))  # 真实实验换 provider
results = hb.run()
print(HomeBenchRunner.render_overall(results))   # OVERALL 对比表
print(HomeBenchRunner.render_by_type(results))   # 按六型分别对比

# —— SAGE 五维 + 新增维度：四系统对比 ——
sg = SageRunner(llm_config=LLMConfig(provider="mock"))
print(SageRunner.render(sg.run()))
```

### 接入真实 LLM（M3）

```python
from homeclaw.config import LLMConfig

# OpenAI 兼容（含本地 vLLM / DeepSeek 等，改 base_url 即可）
LLMConfig(provider="openai", model="gpt-4o-mini")          # 读环境变量 OPENAI_API_KEY
# Anthropic
LLMConfig(provider="anthropic", model="claude-3-5-sonnet") # 读环境变量 ANTHROPIC_API_KEY
```

> 说明：mock 模式下四系统输出一致（mock 不真正读 Skill 正文），用于验证评测链路；
> 系统间的真实差异（如 HomeClaw 完整 Skill vs OnePrompt 裸提示）需接入真实 LLM 才会显现。
> 但**新增维度里的 token 成本差异在 mock 下已可见**（OnePrompt 的 prompt token 远低于 HomeClaw）。

运行 M2 冒烟：

```bash
cd HomeClaw
python3 tests/smoke_m2.py    # 解析 / 构建 / 仿真执行 / 幻觉校验 全链路
python3 tests/smoke_m1.py    # M1 回归
```

### M2 用法：接入仿真执行器

```python
from homeclaw import HomeClawCoordinator, HomeClawCoordinatorConfig
from homeclaw.config import LLMConfig
from homeclaw.executor import SimulateExecutor

home_status = {"living_room": {"room_name": "living_room",
    "light": {"state": "on", "attributes": {"brightness": {"value": 100, "lowest": "0", "highest": "100"}}}}}

ex = SimulateExecutor(home_status)   # 内存仿真，替代 SAGE 的 MongoDB
cfg = HomeClawCoordinatorConfig(llm_config=LLMConfig(provider="mock"), executor=ex)
coord = HomeClawCoordinator(cfg)

res = coord.execute("Amal: turn off the living room light")
print(res.snapshot["living_room"]["light"]["state"])   # → off（SAGE 五维可直接断言）
```

单独使用执行器：

```python
from homeclaw.executor import SimulateExecutor, parse_action

parse_action("balcony.light.set_brightness(40)")   # → ParsedAction(room='balcony', ...)
parse_action("error_input")                          # → None（幻觉拒答）

ex = SimulateExecutor(home_status)
ex.execute("living_room.light.turn_off()")           # {"status": "ok", ...}，改内存状态
ex.execute("kitchen.light.turn_on()")                # {"status": "error", "reason": "unexist_room"}
```

---

## 快速开始

M1 内核默认使用 **MockLLMClient**，无需任何真实 API Key 即可跑通：

```bash
cd HomeClaw
python3 tests/smoke_m1.py
```

预期输出全部 `[PASS]`，覆盖：Skill 加载 → 序列化 → 合法指令预测 → 幻觉拒答 → SAGE 执行入口。

### 代码用法

```python
from homeclaw import HomeClawCoordinator, HomeClawCoordinatorConfig
from homeclaw.config import LLMConfig
from homeclaw.executor import NullExecutor

home_status = {"living_room": {"room_name": "living_room",
    "light": {"state": "on", "attributes": {"brightness": {"value": 100, "lowest": "0", "highest": "100"}}}}}
methods = [{"room_name": "living_room", "device_name": "light", "operation": "turn_off", "parameters": []}]

cfg = HomeClawCoordinatorConfig(
    llm_config=LLMConfig(provider="mock"),          # M3 起可换 "openai"/"anthropic"
    executor=NullExecutor(home_status, methods),    # M2 起换 SimulateExecutor
)
coord = HomeClawCoordinator(cfg)

# HomeBench 入口（只输出动作文本，供幻觉评测）
print(coord.predict_actions(home_status, "Turn off the living room light.", methods))
# → {living_room.light.turn_off()}

# SAGE 入口（执行后落地，供五维评测）
res = coord.execute("Amal: turn off the living room light")
print(res.actions, res.iters, res.usage)
```

---

## M1 设计要点与边界

1. **一份内核，两个入口**：`execute()`（SAGE 五维）与 `predict_actions()`（HomeBench 幻觉）共享同一 `AgentLoop` 与同一 `smart-home` Skill。
2. **Provider 无关**：`llm.py` 抽象出 `BaseLLMClient`，M1 提供 `MockLLMClient` 做离线冒烟；真实 provider（openai/anthropic）在 M3 接入。
3. **动作格式对齐 HomeBench**：`{room.device.operation(param)}`，非法输出 `error_input`，与 `HomeBench/code/example.txt` 完全一致。
4. **单主循环语义对齐 OpenClaw**：`AgentLoop.run()` 为单一 while 循环，保留 `tool_calls` → `toolResult` 回传分支（用于 read SKILL 正文等），并统计 `iters`/`usage` 供"效率维度"评测。
5. **里程碑边界**：
   - `MockLLMClient` 仅做极简规则匹配，**非真实意图识别**——真实推理靠 M3 的真实 LLM Provider；
   - ✅ 内存仿真已在 **M2** 落地（`SimulateExecutor` 对接 `device.py`），替代 SAGE 的 MongoDB；`NullExecutor` 仍保留用于纯文本预测（HomeBench 幻觉评测）；
   - 两级检索（摘要 + 按需 read 正文）当前简化为直接注入正文，完整实现随 M3 对接 OpenClaw Runtime。


---

## M5 · 真机接口用法

同一套动作文本格式 `room.device.operation(param)`，把执行器从 `SimulateExecutor`
换成 `RealDeviceExecutor` 即可下发真实设备，**格式零改动**。

```python
from homeclaw.executor import RealDeviceExecutor, MockCloudAdapter, SmartThingsAdapter

# 实验/CI：Mock 适配器（离线、内存，call_log 可断言）
ex = RealDeviceExecutor(MockCloudAdapter(), home_status=home_status)
ex.execute("balcony.light.set_brightness(40)")   # 下发到适配器，不碰真机

# 落地：SmartThings（token 走环境变量 SMARTTHINGS_TOKEN）
st = SmartThingsAdapter(device_map={("living_room", "light"): "<real-device-id>"})
ex = RealDeviceExecutor(st, home_status=home_status)
ex.execute("living_room.light.turn_off()")        # → SmartThings REST 命令

# Home Assistant（HOMEASSISTANT_URL / HOMEASSISTANT_TOKEN）
from homeclaw.executor import HomeAssistantAdapter
ha = HomeAssistantAdapter(entity_map={("living_room", "light"): "light.living_room"})
ex = RealDeviceExecutor(ha, home_status=home_status)
```

设备云适配器契约（`DeviceCloudAdapter`）：`resolve(room, device) -> device_id`、
`call(device_id, op, args) -> dict`、`get_status(device_id)`（可选）。
`RealDeviceExecutor` 复用与仿真相同的 `parse_action`，`error_input` 同样识别为拒答，
未登记设备返回 `unresolved_device`——与 `SimulateExecutor` 的 `error_input` 语义对齐。

> 至此 M1–M5 全部完成：实验期 `SimulateExecutor` 降难度，落地期 `RealDeviceExecutor`
> 换适配器即可，动作文本、评测口径、幻觉语义全程一致。
