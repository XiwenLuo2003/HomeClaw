# 外部环境验收清单

本文只描述在已有部署环境中的验收步骤。仓库默认验证不会安装依赖、启动容器、连接数据库、访问在线模型或占用 GPU。

## 1. 安全预检

以下命令只检查可选模块、Docker 命令、配置名和仓库资产是否存在；不会显示配置值，也不会连接服务：

```powershell
python scripts/external_preflight.py --output reports/external-preflight.json
```

只有部署人员准备好隔离环境后，才应自行设置连接配置并启动 `deploy/compose.infrastructure.yaml` 或组织现有服务。`deploy/mosquitto/mosquitto.conf` 允许匿名访问，仅用于隔离的本地验收网络，禁止直接作为生产 Broker 配置。

## 2. 必须分开记录的验收组

| 组 | 必需环境 | 重点证据 |
|---|---|---|
| PostgreSQL | PostgreSQL 17、psycopg | Migration、Checkpoint/Outbox 原子性、并发 revision 冲突、进程恢复 |
| Redis | Redis 7、redis-py | State Diff CAS、TTL/stale、幂等 claim、锁所有权、对账恢复 |
| MongoDB | Replica Set、pymongo | 偏好冲突事务、临时偏好过期、历史追溯、日/月摘要版本 |
| RabbitMQ | RabbitMQ 4、aio-pika | Publisher Confirm、Manual ACK、消费者失败、重复消息去重、恢复 |
| MQTT | MQTT 2.x Broker、paho-mqtt | 订阅先于发布、QoS 1 重复、业务拒绝、离线、迟到 ACK、retained 过期 |
| MCP | 官方 MCP Python SDK | Tool/Resource/Prompt 互操作、协议错误、策略版本和权限拒绝 |
| 在线 LLM | 固定模型版本与账号配额 | 四策略同数据集对比、Token、步骤、成功率、P50/P95、成本 |
| Grounder | NVIDIA GPU、固定镜像和模型 revision | readiness、批处理、超时、显存峰值、候选集约束、消歧准确率 |
| OpenTelemetry | Collector 与后端 | 关联 ID 贯通、Span 完整性、P50/P95、错误率、脱敏 |

## 3. 实验纪律

- 先按 `docs/benchmark-protocol.md` 固定数据集、模型、Prompt、预算、随机种子和硬件元数据。
- 任何服务只完成传输确认时，不得记为设备动作成功；最终成功必须绑定设备状态证据。
- 每组故障注入必须至少覆盖超时、重复、乱序、服务重启和连接中断。
- 报告写入 `reports/`，原始结果与汇总结果分开保存；不把参考仓库或论文数值写成 HomeClaw 实测。
- 未完成上述真实环境运行前，计划中的相应条目保持“待验收”。

## 4. 容量测试

已有 HTTP 服务时，可由部署人员使用仓库内无第三方依赖的负载生成器：

```powershell
python scripts/load_test_http.py --url http://127.0.0.1:8000/health --requests 200 --concurrency 8 --output reports/http-load.json
```

该命令会产生真实网络请求，本轮本地代码验收不会自动执行。Grounder、在线 LLM 和 MQTT 应分别限流，不允许用单一入口吞吐量代替各组件容量数据。
