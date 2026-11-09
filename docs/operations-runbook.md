# HomeClaw Production-Ready 运行与恢复手册

本手册面向已经准备好外部依赖的部署环境。本仓库不会自动安装依赖、拉取镜像或启动服务。

## 1. 发布前门禁

1. 固定 Git commit、Skill/Tool Registry、Prompt、在线模型版本和 Grounder 模型 revision。
2. 运行仓库单测、Smoke、Router/冲突离线报告；真实基础设施按 `external-acceptance.md` 验收。
3. PostgreSQL Migration 按编号顺序执行，并备份 Workflow、Registry 和 Outbox。
4. 生产 MCP 必须配置 `AuthorizationPolicy`，禁止依赖“LLM 不会调用危险工具”。
5. Grounder 镜像必须固定模型 revision；匿名 Mosquitto 配置只能用于隔离验收网。

## 2. Agent/Host 崩溃恢复

- 以 PostgreSQL `workflow_task` 为真相源，读取 `current_node`、`revision` 和完整 state。
- `WorkflowHost.resume(task_id)` 从最后一次已提交节点继续；不要手工跳过 Verify/Confirm。
- 若崩溃发生在设备命令后，`action_attempt.idempotency_key` 找回原 `command_id`；`DurableActionDispatcher` 复用它，禁止生成新命令后盲目补发。
- 已有终态证据直接返回；只有 `DISPATCHED` 且无证据时继续等待同一命令的 ACK/状态。
- 超过全局 Deadline、最大步骤、Re-Plan 或 Token 预算时进入明确失败终态，不允许人工把数据库状态直接改为成功。

## 3. Outbox 堆积

- Checkpoint/Registry 更新与 Outbox 写入同一数据库事务；消息发布器只扫描 `published_at IS NULL`。
- Publisher Confirm 只允许填写 `published_at`，不能更新设备执行状态。
- 重放使用原 `message_id`；消费者必须按业务幂等键处理。失败消息进入 RabbitMQ DLQ，修复原因后再人工重放。

## 4. MQTT 与设备状态异常

- PUBACK 后没有匹配 `command_id` 和 `expected_state` 时保持 `UNKNOWN`。
- 设备业务拒绝为 `REJECTED`，Broker/网络故障为可重试依赖失败，二者分别统计。
- retained 状态缺时间、过期或不匹配命令时不得确认新动作。
- State Diff 重复/乱序被丢弃；出现 `GAP` 时触发权威全量读取或周期对账，不能继续拼接局部状态。
- 对 `toggle` 等非幂等动作，先转成绝对目标状态；无法转换时禁止自动重试。

## 5. 缓存与注册表

- Redis 丢失后从设备/网关权威状态和 PostgreSQL Registry 重建，不从缓存反写真相源。
- Registry 变更必须携带期望 home version；冲突时重新读取并合并，禁止 last-write-wins 静默覆盖。
- Device/Capability 快照与 `registry_outbox` 同事务；缓存仅消费已提交事件。
- Mongo 偏好保留历史和失效时间；显式偏好撤销不能物理删除审计记录。

## 6. 熔断、限流与容量

- Planner、Grounder、MCP、MQTT 分别设置超时和熔断，不能共享一个无限重试策略。
- 观察 QPS、queue_ms、在途 Token、GPU 显存和 P95；达到 SLO、错误率或 OOM 门限立即停止升压。
- 简单请求使用 Top-1，多意图或视觉消歧请求允许 Top-2；Token 紧张时退回 Top-1。
- Inverted Index 是否升级 ANN 由同数据集 Recall 和生产 P95/内存共同决定；不能只因 Skill 数量达到某个整数就切换。

## 7. 受控自进化与回滚

- 生产 Agent 无权直接写 Skill/Router。
- Candidate 必须绑定 active base version；stale candidate 直接拒绝。
- 固定集回放、安全门禁和消融通过后，仅进入小流量 Canary。
- 任一安全违规自动暂停；达到样本门限后仍需项目负责人批准。
- 回滚恢复上一个已签核版本，并保留 Evidence Pack、Canary 指标和批准人记录。

## 8. 观测与隐私

- 使用同一 `trace_id/request_id/task_id/command_id` 关联入口、Router、Planner、Verifier、MCP 和 MQTT。
- 不把 API Key、Authorization、Cookie、Prompt、完整用户画像、原始家庭图像或用户主体 ID 写入 Span 标签。
- 性能报告至少包含样本数、错误率、平均值、P50、P95 和失败分布；Mock/离线数字必须标明不能作为生产结论。
