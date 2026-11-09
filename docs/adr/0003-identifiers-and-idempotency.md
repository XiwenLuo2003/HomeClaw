# ADR-0003：关联标识、幂等和成功语义

- 状态：Accepted
- 日期：2026-11-09

## 标识职责

- `trace_id`：一次端到端链路，可跨服务和重试。
- `request_id`：一次用户/API 请求。
- `task_id`：一个可恢复的 Workflow 实例。
- `action_id`：Proposer 产生的一个语义动作。
- `command_id`：一次可去重的设备命令；安全重试必须复用原值。
- `message_id`：一条消息实例，用于消费端去重和审计。

## 幂等分类

- `IDEMPOTENT`：重复设置同一目标值不会改变业务语义。
- `IDEMPOTENT_WITH_KEY`：借助 `command_id` 和去重记录实现业务幂等。
- `NON_IDEMPOTENT`：例如 `toggle`；必须先转换为目标状态动作，或提供显式验证规则并禁止盲目重试。

## 成功语义

HTTP 2xx、MCP 返回、RabbitMQ Publisher Confirm 和 MQTT PUBACK 都只代表对应传输阶段成功。只有观察到与动作绑定的设备状态证据，并满足 `expected_state`/验证谓词时，动作才能进入 `SUCCEEDED`。
