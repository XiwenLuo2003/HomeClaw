# ADR-0002：数据所有权与一致性边界

- 状态：Accepted
- 日期：2026-11-09

## 决策

| 数据 | 真相源 | 缓存或传播 |
|---|---|---|
| 任务 DAG、节点状态、Checkpoint、动作尝试、Outbox | PostgreSQL | Redis / RabbitMQ |
| 设备、房间、能力、拓扑及其版本 | 首阶段优先 PostgreSQL | Redis / MCP Resource |
| 用户画像、情景记忆、日月摘要、偏好事实 | MongoDB | 进程内检索索引 |
| 设备最新状态和 State Diff | 设备/网关状态事件；持久快照用于审计 | Redis |
| MQTT 命令映射 | 版本化 Capability Registry | Bridge 进程缓存 |

## 一致性规则

- 数据库提交和事件发布使用 Transactional Outbox，不允许双写。
- Redis 不是最终真相源；缓存丢失后必须能够从持久库或设备重新构建。
- 状态事件必须携带设备版本或可比较时间，过期事件不得覆盖新状态。
- MQTT retained message 只能作为候选快照，仍需检查时间、设备在线状态或主动查询。
- 首阶段不同时引入 MySQL 和 PostgreSQL；只有明确的组织或存量系统约束出现时才新增 MySQL Adapter。
