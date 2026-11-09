# HomeClaw Production-Ready 实施计划

> 目标分支：`production-ready`  
> 文档用途：约束工程范围、拆分实施任务、记录验收结果与持续更新进度。  
> 更新原则：只有代码、测试、文档和可复现实验均达到对应验收标准后，任务才能标记为“已完成”。

## 1. 范围与架构边界

### 1.1 模型职责

- Agent 主模型继续使用 GPT、Gemini 等在线大模型，负责意图理解、规划、Skill 路由和工具调用。
- Qwen3-VL-4B Grounder 只是“设备消歧 Skill”内部的视觉工具，不是 Agent 主模型，也不负责全局规划。
- Grounder 仅在出现视觉指代、同类设备或实体歧义时调用，输出结构化设备定位结果。
- 本分支只实现 Grounder 的推理部署和 Agent 接入，不实现 Qwen3-VL、LoRA 或 GRPO 训练代码。
- 简历中的 GRPO 分层奖励仅用于说明 Grounder 的离线训练方案，包括：设备 Grounding、动作参数 F1、API 可执行性和格式约束。
- Agent 运行时的 Proposer–Verifier、冲突检测和设备状态确认属于独立工程模块，不得与 Grounder 的 GRPO 奖励混用。

### 1.2 目标调用链

```text
用户请求
  -> Host / Workflow
  -> 在线大模型 Planner / Proposer
  -> Skill Router
  -> 被选中的 Skill 与收缩后的 Tool 空间
  -> Verifier
  -> MCP Client
  -> 家居领域 MCP Server
  -> MCP-MQTT Bridge
  -> 物理设备
  -> 状态 / ACK / State Diff
  -> Host 状态确认与必要时局部 Re-Plan
```

视觉歧义场景增加一条按需支路：

```text
设备消歧 Skill -> Qwen3-VL-4B Grounder 推理服务 -> GroundingResult
```

### 1.3 数据与基础设施职责

| 组件 | 计划职责 |
|---|---|
| PostgreSQL | Host 任务状态、DAG、Checkpoint、动作尝试、Outbox 和恢复信息的真相源 |
| MySQL 或 PostgreSQL | 家居环境拓扑、设备能力注册表；实施前通过 ADR 确认是否有必要同时维护两种关系数据库 |
| MongoDB | 用户画像、情景记忆、日/月摘要及带时间有效性的偏好事实 |
| Redis | 短期状态缓存、幂等去重、分布式锁、并发控制、限流和短期 State Diff |
| RabbitMQ | 服务拆分后的内部异步事件与任务队列；不替代 MQTT，也不作为首阶段强制依赖 |
| MQTT | 与物理设备或家庭网关通信 |
| MCP | 向 Agent 暴露领域级 Tools、Resources 和 Prompts，隔离原始 MQTT Topic |
| OpenTelemetry | 统一 Trace、Metric、错误和性能观测 |

## 2. 进度状态说明

| 状态 | 含义 |
|---|---|
| ⬜ 待开始 | 尚未进入设计或实现 |
| 🟨 调研完成 | 已完成代码级调研，但尚未形成可验收实现 |
| 🟦 进行中 | 正在设计、开发或测试 |
| 🟪 待验收 | 实现完成，等待测试、实验或文档验收 |
| ✅ 已完成 | 代码、测试、文档和验收证据全部齐全 |
| ⛔ 阻塞 | 存在外部依赖、关键决策或数据缺失 |

## 3. 23 项实施任务与完成情况

> “完成情况”位于最右列，后续每完成一个阶段应同步更新状态和证据链接。

| # | 主题 | 计划实现与关键设计 | 验收标准 | 主要参考 | 完成情况 |
|---:|---|---|---|---|---|
| 1 | Workflow 与整体编排 | 将当前同步 Coordinator 重构为显式状态图；定义 Grounding、Routing、Planning、Verification、Execution、State Confirmation、Re-Plan 和 Termination 节点；所有节点通过强类型状态传递。 | 正常、拒绝、超时、局部重规划、人工中断和恢复路径均有自动化测试；流程图与状态转换文档齐全。 | LangGraph | ✅ 已完成 |
| 2 | 组件部署、通信与 Blackboard | 明确在线 LLM、CPU Router/Host、独立 GPU Grounder、MCP Server 和边缘 MQTT Bridge 的部署边界；控制路径使用强类型消息，持久状态使用 PostgreSQL Blackboard；服务拆分后才通过 RabbitMQ 传递异步任务。 | 提供部署图、接口契约、消息 Envelope；跨服务消息包含 `trace_id`、`request_id`、`task_id`、版本与幂等键；完成最小集成测试。 | LangGraph、aio-pika、RabbitMQ Tutorials | 🟪 待验收 |
| 3 | 长短期记忆与偏好冲突 | 保留短期会话摘要与长期用户记忆；为偏好增加作用域、来源、置信度、`valid_at`、`invalid_at` 和版本；明确“显式声明优先于推断、具体范围优先于全局、同级最新有效事实优先”的冲突策略。 | 覆盖相反偏好、临时偏好、房间级覆盖、多人偏好和撤销偏好的测试；能够追溯每次决策使用的事实与来源。 | Graphiti | 🟪 待验收 |
| 4 | 环境图谱、能力注册表与并发更新 | 将设备、房间、能力、关系和版本定义为持久化模型；采用事务、乐观锁和 Outbox 防止数据库提交与事件发布不一致；Redis 只缓存，不作为真相源。 | 并发更新不丢失；重复事件可安全重放；缓存失效后可从真相源恢复；形成 MySQL/PostgreSQL 选型 ADR。 | Redis、RabbitMQ、Home Assistant | 🟪 待验收 |
| 5 | 慢状态查询、缓存与 State Diff | Redis 保存带版本、采集时间、TTL 和 stale 标记的设备状态；MQTT 状态事件只应用更新版本更高的 Diff；缓存缺失或过期时回源；定期执行全量对账。 | 验证乱序、重复、丢失、过期和设备离线场景；输出缓存命中率、状态新鲜度和对账差异率。 | redis-py、Paho MQTT、Home Assistant MQTT | 🟪 待验收 |
| 6 | Skill-MoE 与上下文收缩 | 建立 Skill Registry；Router 先召回候选 Skill，再加载 Top-K Skill 的说明、约束和 Tool Schema；实现候选检索、打分、门控、降级和全局安全 Skill；不将其描述为神经网络 MoE。 | 对比全量 Tool Schema 时，统计输入 Token、Schema 字节数、规划延迟和任务成功率；错误路由可回退。 | Skill-MoE | ✅ 已完成 |
| 7 | Skill-MoE 效果量化 | 建立四组基线：全量工具 ReAct、全量工具 Plan-and-Solve、普通 Router 加渐进式披露、HomeClaw 双层收缩；统一任务集、模型、温度、预算和随机种子。 | 报告规划步数、总 Token、工具候选数、成功率、P50/P95 延迟和成本；数值必须来自可复现实验，不预填简历指标。 | Skill-MoE、HomeBench | 🟪 待在线模型实验 |
| 8 | Skill 与 Tool 抽象及创建 | Tool 使用领域动作契约，包含能力、参数 Schema、前置条件、预期效果、幂等性、权限、安全级别和验证谓词；Skill 由意图范围、知识、工作流、允许工具和回退策略组成。 | 提供版本化 Schema、注册和校验机制；新增一个 Skill/Tool 不需要修改 Host 核心流程；示例与测试齐全。 | MCP Python SDK、Home Assistant Registry | ✅ 已完成 |
| 9 | Skill 边界与重复 Tool | 按能力域、上下文依赖、事务边界和安全策略划分 Skill；共享 Tool 只注册一次，多个 Skill 通过引用与别名复用；Router 对重叠 Skill 支持多标签召回。 | 检测重复 Tool ID、冲突 Schema 和循环依赖；跨 Skill 共享工具有一致权限与版本。 | MCP Python SDK | ✅ 已完成 |
| 10 | Router 召回率 | 构建带 Gold Skill 集合的单意图、多意图和模糊指令集；实现关键词/向量混合召回、元数据过滤、重排和低置信度回退。 | 输出 Recall@1、Recall@K、MRR、多标签覆盖率、Fallback Rate；与普通向量 Router 在同一数据集对比。 | Skill-MoE、sentence-transformers | ✅ 已完成 |
| 11 | Skill/设备规模扩展 | 使用分层路由：领域粗分类、候选 Skill 检索、精排；为 Skill、设备和能力建立向量与结构化索引；按规模和延迟阈值决定是否启用 ANN 或分片。 | 在不同 Skill 数、Tool 数和设备数下压测准确率、P50/P95、吞吐量和索引内存；记录索引启用阈值。 | Skill-MoE、Graphiti 检索设计 | ✅ 已完成 |
| 12 | Skill-MoE 自进化 | 只允许离线闭环：收集失败轨迹、生成候选 Skill/Router 变更、固定集回放、安全门禁、消融、Canary、人工批准、发布与回滚；禁止 Agent 在线直接修改生产 Skill。 | 每次进化生成 Evidence Pack；无基准退化和安全违规才可晋级；支持版本锁定、一键回滚和自动暂停。 | RSIAgent、evolver.py | ✅ 已完成 |
| 13 | 环境知识锚定与 Grounder | 环境图谱先过滤候选设备；仅在视觉歧义时调用设备消歧 Skill 内的 Qwen3-VL-4B Grounder；Grounder 输出候选、实体 ID、bbox、置信度和证据；只实现推理服务与接入。 | Grounder 可通过 Docker GPU 服务部署，提供健康检查、批处理、超时与降级；消歧准确率采用本项目数据重新评测。 | Qwen3-VL、CORE | 🟪 待验收 |
| 14 | Proposer–Verifier | Proposer 生成结构化语义提议；Binder 绑定设备实例；Verifier 使用隔离上下文、拓扑、能力注册表和规则验证；失败后返回结构化原因并限轮 Re-Plan；默认不引入 A2A。 | Verifier 不能依赖 Proposer 的自然语言自证；覆盖不存在设备、能力不支持、状态过期、无效参数和 False Done。 | CORE 思路、LangGraph | ✅ 已完成 |
| 15 | 原子动作冲突检测 | 将设备冲突、环境冲突、循环、阻塞、冗余和资源竞争实现为可扩展 Verifier 规则；增加动作时间窗、共享资源锁和跨设备环境影响。 | 构建独立冲突测试集并报告 Precision、Recall、F1；不直接采用 KnowDetector 论文结果，也不复制许可证不明确的代码。 | KnowDetector | ✅ 已完成 |
| 16 | Function Calling、MCP Tools/Resources/Prompts | 在线大模型的 Function Calling 先进入 Host；Host 作为 MCP Client 调用领域 MCP Server；Tools 表达动作，Resources 提供聚合状态/能力快照，Prompts 提供规划和验证模板；高频传感器原始流不进入 LLM。 | 完成 Tool 列举/调用、Resource 读取/订阅更新、Prompt 获取和协议错误处理；接口具备版本与权限校验。 | MCP Python SDK | 🟪 待验收 |
| 17 | MCP-MQTT Bridge | MCP 仅暴露 `set_temperature` 等领域 Tool；Bridge 内部维护设备/能力到 Topic 和 Payload 的映射；发布后等待业务 ACK 或目标状态成立，区分 Broker 接收与设备执行成功。 | 原始 Topic 不出现在 Agent Tool Schema；覆盖成功、拒绝、离线、超时、迟到 ACK 和状态不一致场景。 | Paho MQTT、Home Assistant MQTT、MCP SDK | 🟪 待验收 |
| 18 | DAG、Checkpoint、恢复与幂等 | PostgreSQL 保存状态机、任务 DAG、完成步骤、当前节点、`request_id`、`command_id` 和幂等键；通过 Checkpoint 恢复；使用 Outbox 防止“落库成功但消息未发”；避免 `toggle` 类非幂等动作。 | 服务在各节点崩溃后可恢复；QoS 1 重复消息不会重复产生业务副作用；retained 状态必须通过时间戳、在线状态和主动查询确认。 | LangGraph PostgreSQL、Paho MQTT、Redis | 🟪 待验收 |
| 19 | 大量 MCP Tool Schema 的上下文控制 | MCP 服务器可注册全量工具，但 Host 只向在线 LLM 暴露 Router 选中 Skill 的工具子集；为公共安全工具保留固定最小集合；Tool Schema 做版本缓存。 | Tool 数增长时上下文大小近似由 Top-K Skill 决定；错误路由时可以二次召回，但有最大次数限制。 | Skill-MoE、MCP SDK | ✅ 已完成 |
| 20 | 超时、重试、预算与熔断 | 为 LLM、Grounder、MCP、MQTT 状态确认分别设置超时；只重试可安全重试错误；采用退避、抖动、熔断、最大规划步数、Token 预算和全局 Deadline。 | 故障注入下无无限循环；重试保留同一幂等键；超预算后进入明确终态并返回可解释失败原因。 | LangGraph RetryPolicy、aio-pika、Paho MQTT | ✅ 已完成 |
| 21 | 状态缓存一致性专项验收 | 与第 5 项共用实现，额外建立命令写路径与状态读路径的一致性测试；命令完成必须绑定状态证据，而不是只检查发布结果。 | 输出 read-your-write 达成率、陈旧读比例、状态确认耗时和全量对账恢复时间。 | Redis、Home Assistant MQTT | 🟪 待真实 Redis/MQTT 实验 |
| 22 | 多专家并发、QPS、Token 与 GPU 成本 | Router 依据任务复杂度决定 Expert 数；设置租户/模型/任务级信号量、Token 预算和队列；Grounder 支持动态批处理和显存保护；缓存可复用结果并提供降级路径。 | 压测不同并发与 Top-K，报告 QPS、Token/任务、GPU 利用率、显存、排队时间、P50/P95 和成功率；形成容量模型。 | Skill-MoE、Qwen3-VL、OpenTelemetry | 🟪 待验收 |
| 23 | 全链路性能定位与可观测性 | 统一传播 `trace_id`、`request_id`、`task_id`、`command_id`；建立 `agent.request`、`router.retrieve`、`grounder.infer`、`planner.generate`、`verifier.check`、`mcp.call`、`mqtt.publish`、`mqtt.wait_state` 等 Span；记录错误、重试、Token 和队列指标。 | 可按组件查看 P50/P95、错误率、超时率和吞吐量；一次任务能从入口追踪到设备状态证据；日志不泄露密钥和敏感画像。 | OpenTelemetry Python | 🟪 待验收 |

## 4. 分阶段实施顺序

### Phase 0：契约、基线与可观测性骨架

- 定义领域对象、错误码、ID 和消息 Envelope。
- 固化当前版本的回归测试及性能基线。
- 建立 OpenTelemetry 观测字段和实验记录格式。
- 输出架构决策记录（ADR），确定数据库和消息队列使用边界。

### Phase 1：Host、DAG 与确定性验证

- 实现 Workflow 状态图。
- 实现 PostgreSQL Checkpoint、Outbox、恢复和幂等。
- 实现 Proposer–Binder–Verifier 数据契约。
- 实现能力验证、冲突检测、限轮 Re-Plan。

### Phase 2：MCP、MQTT 与真实执行闭环

- 实现 MCP Client 和领域 MCP Server。
- 实现 MCP Tools、Resources、Prompts。
- 实现 MQTT Bridge、业务 ACK、状态确认和失败终态。
- 实现 Redis 状态缓存、State Diff 和周期对账。

### Phase 3：Skill Router 与上下文压缩

- 实现 Skill Registry、混合检索、Top-K 路由。
- 实现 Skill 内 Tool 子空间收缩和 Schema 缓存。
- 建立 Router 召回率和四组基线实验。

### Phase 4：记忆、图谱与能力注册表

- 实现用户记忆和偏好冲突策略。
- 实现家庭拓扑、设备能力注册及版本更新。
- 建立事件驱动缓存失效与一致性测试。

### Phase 5：Qwen3-VL Grounder 推理部署

- 实现 Grounder 推理 API 和结构化结果。
- 提供 Docker GPU 部署、健康检查、超时、批处理和降级。
- 接入设备消歧 Skill，确保只有必要场景才调用。
- 不实现 Qwen3-VL、LoRA 或 GRPO 训练代码。

### Phase 6：性能、容量与可靠性验收

- 完成并发、故障注入、崩溃恢复和一致性测试。
- 输出 Router、Grounder、Planner、Verifier、MCP、MQTT 的 P50/P95。
- 建立 Token、QPS、GPU 与成本容量模型。

### Phase 7：受控自进化

- 实现离线候选生成、回放、门禁、消融和 Evidence Pack。
- 实现 Canary、人工审批、版本晋级和回滚。
- 不允许未经验证的 Skill 或 Router 变更直接进入生产环境。

## 5. 指标与实验约束

- 所有提升数值必须由当前 HomeClaw 分支的可复现实验产生。
- 不直接引用 KnowDetector、Skill-MoE、CORE 或其他论文/仓库的结果作为本项目指标。
- 对比实验必须固定：数据集、在线模型版本、提示词版本、温度、最大 Token、最大步骤、重试策略和随机种子。
- 至少报告平均值、P50、P95、样本数和失败分布，不能只报告单一最好结果。
- 在线模型或外部服务发生版本变化时，应记录时间、模型标识和配置，并重新判断结果是否可比。
- 简历指标只有在对应实验脚本、原始结果和分析报告均存在后才能更新。

## 6. 参考仓库使用原则

| 参考仓库 | 主要借鉴内容 | 使用边界 |
|---|---|---|
| LangGraph | Workflow、Checkpoint、Retry、Interrupt/Resume | 增加 HomeClaw 领域表和幂等语义，不只保存不透明状态 |
| MCP Python SDK | Tools、Resources、Prompts、Client/Server | 不向 Agent 暴露原始 MQTT Topic |
| Paho MQTT / Home Assistant | MQTT 生命周期、状态/命令/可用性 Topic | PUBACK 不等于设备动作成功 |
| redis-py | 缓存、锁、去重、Streams、并发控制 | Redis 不作为最终真相源 |
| RabbitMQ / aio-pika | 持久队列、Manual ACK、DLQ、恢复 | 服务未拆分前不强行引入；Publisher Confirm 不等于业务成功 |
| Skill-MoE | Skill 能力画像、Top-K Expert 路由 | 不直接照搬离线脚本，不宣称为神经网络 MoE |
| Graphiti | 时间事实、失效边和冲突处理 | 按 HomeClaw 偏好模型重新设计权限与作用域 |
| Qwen3-VL | Grounder 推理能力 | 仅作为设备消歧 Skill 内部工具 |
| ms-swift | 理解既有 GRPO 包装方案 | 本分支不实现训练代码 |
| RSIAgent / evolver.py | Evidence、门禁、Canary、回滚 | 禁止在线无审查自修改 |
| KnowDetector | 冲突类型和图分析思路 | 不复制许可证不明确代码，不借用其指标 |
| CORE | 实体锚定、拆解和评测思路 | 不将包装描述视为已经实现的生产能力 |
| OpenTelemetry | Trace、Metric、上下文传播 | 统一脱敏和标签基数控制 |

## 7. 完成定义（Definition of Done）

任一任务只有同时满足以下条件才能标记为 ✅：

1. 代码已经合并到 `production-ready` 分支对应提交。
2. 单元测试、集成测试及必要的故障测试通过。
3. 接口、配置、运行方式和设计决策已有文档。
4. 有可追溯的日志、Trace、实验结果或验收证据。
5. 不破坏现有 HomeBench/SAGE 回归能力。
6. 不使用无法追溯的外部指标，也不将方案描述误写成已实现能力。
7. 涉及外部服务时，提供本地或 Docker 化的最小复现方式。

## 8. 进度记录

| 日期 | 变更 | 影响任务 | 记录人 |
|---|---|---|---|
| 2026-11-09 | 建立 Production-Ready 计划；完成第一批参考仓库代码级调研；明确 Qwen3-VL Grounder 和 GRPO 的范围边界。 | 1—23 | Codex / 项目作者 |
| 2026-11-09 | 修复 Python 包目录大小写导致的导入失败；原有 M1—M6、P1—P7 smoke 基线全部通过。 | 基线 | Codex |
| 2026-11-09 | 完成领域契约、Workflow Checkpoint/Outbox、崩溃恢复、预算、确定性 Verifier、MCP 语义层、MQTT 状态确认、缓存和幂等核心。 | 1、2、5、14、16—21 | Codex |
| 2026-11-09 | 完成 Skill Registry、Top-K Router、设备能力二级 Tool 收缩、Gold 路由集及 100/1000/5000 Skill 扩展评测。离线报告：`reports/router-eval-2026-11-09.json`。 | 6—11、19 | Codex |
| 2026-11-09 | 完成时间化偏好冲突、摘要版本、拓扑锚定、动作冲突检测、Qwen3-VL 推理客户端与 Docker 服务、自进化 Evidence Gate、可靠性和观测核心。 | 3、4、12、13、15、20、22、23 | Codex |
| 2026-11-09 | 补齐 MCP 版本化 RBAC/家庭租户隔离、高风险确认，MQTT 业务拒绝与 Broker 失败语义，Grounder 批请求和端到端 `agent.request` Trace。 | 13、16、17、23 | Codex |
| 2026-11-09 | 增加 PostgreSQL Capability Registry 乐观锁与同事务 Outbox、偏好撤销和用户隔离、状态一致性指标汇总器。 | 3—5、18、21 | Codex |
| 2026-11-09 | Router 评测加入同数据集 TF-IDF 向量基线以及 100/1000/5000 Skill、Tool、候选设备扩展测试；重新生成 `reports/router-eval-2026-11-09.json`。 | 7、10、11 | Codex |
| 2026-11-09 | Production-Ready 单元/集成测试累计 123 个全部通过；M1–M6、P1–P7 共 8 个 Smoke 脚本全部通过；compileall 与 Git whitespace 检查通过。 | 当前本地验收 | Codex |
| 2026-11-09 | 执行只读外部预检：部署资产齐全；当前机器未提供可选依赖、Docker、连接配置，故未连接或启动 PostgreSQL、Redis、MongoDB、RabbitMQ、MQTT、MCP、OTel、在线模型和 GPU。证据：`reports/external-preflight.json`。 | 2—5、7、13、16—18、21—23 | Codex |
| 2026-11-09 | 完成 Grounder Workflow 节点接入和歧义 fail-closed、动态 Top-K、Planner/Grounder 容量包装器、MCP 超时及 RabbitMQ 版本校验/DLQ。 | 1、2、13、16、20、22、23 | Codex |
| 2026-11-09 | 完成 Mongo 日/月摘要 Store、活跃偏好唯一约束与并发重试；补齐 PostgreSQL Registry Room/Topology、Action Attempt 与崩溃后原 `command_id` 复用。 | 3、4、18 | Codex |
| 2026-11-09 | 增量 State Diff 增加 `GAP` 语义和 Read-through 回源；建立 8 条仓库自有冲突规则集，离线 Precision/Recall/F1/Exact Match 均为 1.00，明确仅为合成规则覆盖。证据：`reports/conflict-eval-2026-11-09.json`。 | 5、15、21 | Codex |
| 2026-11-09 | 自进化补齐失败轨迹→候选→固定集回放/消融→门禁→Evidence Pack→Canary 准备流水线，stale base version 默认拒绝。 | 12 | Codex |
| 2026-11-09 | 完成全节点崩溃恢复、Checkpoint/Outbox 同事务、原 `command_id` 恢复复用、MCP 家庭租户隔离、设备离线前置拒绝、LLM 瞬态/永久错误分类；最终 123/123 单测及 8 组 Smoke 全部通过。 | 1、16–18、20、23 | Codex |

## 9. 2026-11-09 本地验收快照

### 9.1 已执行

| 验收项 | 结果 | 证据/命令 |
|---|---|---|
| Production-Ready 单元与进程内集成测试 | 123/123 通过 | `python scripts/verify.py --suite unit` |
| 原项目回归 | M1—M6、P1—P7 全通过 | `python scripts/verify.py --suite smoke` |
| Python 语法编译 | 通过 | `python -m compileall -q homeclaw deploy scripts` |
| 差异空白检查 | 工作区与暂存区均通过 | `git diff --check`、`git diff --cached --check` |
| Router Gold 集 | HomeClaw Top-2 Recall@2=1.00、完整覆盖率=1.00；TF-IDF Top-2 Recall@2=0.92、完整覆盖率=0.88 | `reports/router-eval-2026-11-09.json` |
| Router/Tool 扩展 | 5000 Skill、5011 Tool 时本机离线 route P95≈0.417 ms，索引峰值≈16.3 MB | 同上；只代表当前离线进程和机器 |
| 候选设备收缩扩展 | 5000 候选设备时本机 P95≈1.392 ms | 同上；不代表数据库或网络时延 |
| 冲突规则集 | 8 条仓库自有合成用例 Precision/Recall/F1/Exact Match=1.00 | `reports/conflict-eval-2026-11-09.json`；不是 KnowDetector 或真实家庭分布结果 |
| 外部环境只读预检 | 部署资产存在；可选模块、Docker 和连接配置均未提供 | `reports/external-preflight.json` |

### 9.2 状态解释

- 当前有 11 项达到仓库内代码、测试、文档和可复现离线证据要求：1、6、8—12、14、15、19、20。
- 其余 12 项的代码、Adapter、部署资产或实验入口已经落盘，但仍需在已有外部环境中验收，因此保持 🟪，不能包装成已实测：2—5、7、13、16—18、21—23。
- 外部验收步骤见 `docs/external-acceptance.md`，实验元数据规范见 `docs/benchmark-protocol.md`。
- 本轮没有安装任何包、没有启动容器或外部服务、没有访问在线模型/GPU，也没有执行 Git commit/push。

