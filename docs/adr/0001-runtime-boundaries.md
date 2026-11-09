# ADR-0001：运行时组件边界

- 状态：Accepted
- 日期：2026-11-09

## 决策

HomeClaw 首先采用模块化单体，而不是立即拆成全量微服务。

- Host、Router、Planner 编排和 Verifier 默认运行在同一个 Python 服务中。
- Planner 调用 GPT、Gemini 等在线大模型，不在 HomeClaw 进程中加载主模型。
- Qwen3-VL-4B Grounder 是设备消歧 Skill 的按需工具，以独立 GPU 推理服务部署。
- MCP-MQTT Bridge 独立部署在能够访问家庭 MQTT Broker 的边缘或网关环境。
- RabbitMQ 只在跨进程异步任务、故障隔离或吞吐需求出现后启用，不参与进程内函数调用。

## 通信约束

- 所有跨模块请求使用版本化领域契约，不传递供应商 SDK 对象。
- 每条链路传播 `trace_id`、`request_id`、`task_id`；设备命令还必须传播 `command_id`。
- 持久任务状态写入 Blackboard；消息本身不作为任务状态的唯一真相源。
- 高频传感器数据不直接进入 LLM 上下文，只通过聚合 Resource 或异常事件暴露。

## 后果

该方案优先保证单机可测和接口稳定。未来拆分服务时可以复用相同契约，但需要增加消息序列化、认证、限流和部署配置。
