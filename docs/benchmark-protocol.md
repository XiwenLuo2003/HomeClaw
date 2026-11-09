# Production-Ready 实验与容量验收协议

该协议用于生成可以写入项目报告或简历的 HomeClaw 自有指标。参考仓库和论文中的数值不得作为 HomeClaw 结果。

## 1. 可比性元数据

每次实验必须记录：

- Git commit、工作区是否干净；
- 数据集 ID、内容哈希、样本数；
- 在线模型名称和服务端返回的固定版本；
- Prompt/Skill/Tool Registry 版本；
- 温度、随机种子、最大输入/输出 Token、最大步骤和 Re-Plan 次数；
- Router Top-K、置信度阈值、Embedding/重排模型；
- CPU、内存、GPU 型号、显存、CUDA、驱动、容器镜像摘要；
- PostgreSQL、Redis、RabbitMQ、MongoDB、MQTT Broker 和 MCP SDK 版本；
- 网络区域及测试时间。

任何一项关键条件不同，应作为新实验组，不能直接做“提升百分比”。

## 2. Skill-MoE 四策略对比

必须使用 `homeclaw.eval.strategy_benchmark` 的同一 `BenchmarkConfig` 跑四组：

1. 全量 Tool Schema 的 ReAct；
2. 全量 Tool Schema 的 Plan-and-Solve；
3. 普通 Router + Skill 渐进式披露；
4. HomeClaw Top-K Skill + 候选设备 Capability 二次收缩。

每个样本记录：

- 是否完成最终设备状态目标；
- 规划步骤和 Re-Plan 次数；
- Prompt、Completion 和总 Token；
- 暴露 Tool 数及 Schema 字节数；
- 端到端延迟与模型调用成本；
- False Done、无效 Tool、参数错误和冲突动作。

汇总报告至少包含平均值、P50、P95、失败类型分布和样本数。

## 3. Router

仓库内离线入口：

```powershell
python scripts/evaluate_router.py --output reports/router-eval.json
```

报告包含 Recall@K、MRR、多标签完整覆盖率、Fallback Rate、Tool 收缩率、Schema 字节减少和 100/1000/5000 Skill 的索引/路由延迟。该结果只证明确定性 Router，不等同于在线 LLM 任务成功率。

如启用向量召回，必须在同一 Gold 集上增加“关键词、纯向量、混合召回、混合加重排”四组消融。

## 4. Grounder

Grounder 数据集必须包含：

- 同类型设备；
- 遮挡和小目标；
- 多轮指代；
- 图中不存在目标；
- 拓扑候选为 1、2、5、10 个的分层结果。

报告设备实体准确率、bbox IoU/Recall、歧义拒答率、候选集外幻觉率、P50/P95、GPU 利用率、显存峰值和批量吞吐。Grounder GRPO/LoRA 训练不在本仓库执行，训练奖励也不得混入 Agent Verifier 指标。

部署后可手工执行：

```powershell
python scripts/load_test_http.py `
  --url http://127.0.0.1:8088/v1/ground `
  --payload data/eval/grounder-request.json `
  --requests 200 --concurrency 8 `
  --output reports/grounder-load.json
```

运行压测时另行采集 `nvidia-smi dmon` 或 DCGM 指标，并把原始文件与报告放在同一实验目录。仓库不会自动运行该命令。

## 5. MCP、MQTT 与状态一致性

故障矩阵至少覆盖：

- Broker 拒绝发布；
- QoS 1 重复投递；
- 发布成功但设备离线；
- ACK 迟到；
- 旧 retained 状态；
- 状态事件乱序、重复和丢失；
- Redis 缓存丢失；
- Agent 在每个 Workflow 节点崩溃；
- PostgreSQL 已提交但事件尚未发布；
- MCP Server 超时、中断和恢复。

报告执行成功率、False Done、重复副作用、read-your-write 达成率、陈旧读比例、确认延迟、对账恢复时间和崩溃恢复时间。

## 6. 多专家与在线模型容量

逐步提高：

- 并发：1、2、4、8、16、32；
- Top-K：1、2、3；
- 单任务 Token 预算；
- Grounder 批量：1、2、4、8、16。

记录 QPS、排队时间、P50/P95、超时、Token/任务、GPU 利用率和显存。达到以下任一条件时停止加压：错误率超过门限、P95 超出 SLO、GPU OOM、熔断打开或安全检查失败。

## 7. OpenTelemetry 验收

单次请求应能按同一 `trace_id` 查到：

```text
workflow.receive -> router.retrieve -> planner.generate -> binder.resolve
-> verifier.check -> mcp.call -> mqtt.publish -> mqtt.wait_state
```

确认日志和 Span 中不存在 API Key、Authorization、Cookie、用户完整画像和原始家庭图像。指标标签禁止使用无限基数的自然语言指令、完整 Device UUID 或 Prompt 文本。

## 8. 自进化门禁

- Baseline 与 Candidate 必须共享数据哈希、模型、Prompt、种子和预算。
- 任一安全检查失败立即拒绝。
- 离线门禁通过后才能进入小流量 Canary。
- Canary 出现安全违规立即自动暂停。
- 达到最小样本且无退化后仍需要项目负责人明确批准。
- 所有晋级必须有 Evidence Pack；支持按候选版本回滚。
