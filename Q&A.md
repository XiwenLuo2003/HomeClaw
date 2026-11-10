# 项目2：智能家居Agent深度面试题库

GRPO多模态Grounder、结合Skill-MoE稀疏编排、Proposer–Verifier对抗验证、Host/MCP执行及状态管理

## 零、简历内容

基于GRPO强化学习的Agent推理对齐框架（Workflow&编排、多智能体通讯：RabbitMQ/MailBox/A2A、Skill上下文爆炸、多路召回Tool、如何抽象Tool&Skill、MCP）
1、业务背景：面向智能家居从规则式中控向自主交互式智能管家演进需求，提升复杂家庭场景下的人机交互体验。
2、技术方案：针对MLLM在高自由度指令解析中存在的逻辑幻觉问题，构建模型中心的“多模态感知—推理规划—工具调用—状态反馈”端到端Agent，并通过GRPO实现Qwen3-VL领域认知与执行策略对齐降低细粒度视觉指代模糊。
（1）多模态数据集工程与模型优化：针对同类设备、遮挡目标及多轮指代等现实歧义场景，构建万级“用户指令—场景图像—指代设备—动作序列”数据集；选用Qwen3-VL-4B-Instruct作为端到端策略模型对视觉编码器后层、Visual Merger及语言侧Attention/MLP注入LoRA微调，引入视觉感知辅助损失提升模型细粒度物理实体的消歧能力；设计设备Grounding、动作参数F1、API可执行性和格式约束的GRPO分层奖励以缓解多采样Reward Hacking。
（2）Skill-based MoE编排范式设计：针对LLM长上下文记忆依赖导致任务状态漂移问题，设计能力级门控—工具级收缩双层稀疏机制，Router结合任务语义动态激活Top-K Skill专家，各Expert基于关联拓扑、记忆锚定等注入信息缩小工具空间，Host维护任务有向依赖与局部Re-Plan，并利用Grounding反馈校准门控策略实现协同优化。
（3）Proposer–Verifier博弈均衡对齐：针对Agent调用成功即任务完成的False Done及同源推理导致动作幻觉问题，设计“语义提议—实例绑定—约束验证—工具执行”有界博弈闭环；Proposer生成语义提议候选，Verifier隔离认知并基于Topology Tree与Capability Registry校验避免自证与无效循环，结构化证据驱动Proposer限轮重规划再核验。
3、项目成果：长程复杂指令执行成功率较基线提升25%，细粒度物理设备实体识别准确率达到84%。

## 一、Agent整体架构与技术选型

1. 介绍一下你的智能家居Agent项目，现场画出整体架构图，说明用户指令如何一步步转化为设备动作。
2. 你的Agent为什么要拆成Planner、Skill Router、Expert Worker、Grounder、Verifier和Host？这些模块分别解决什么问题？
3. 为什么选择单主Planner + 多专家Worker，而不是直接使用LangGraph的多Agent架构？
4. LangGraph本身就支持状态管理、条件分支、工具调用和Checkpoint，为什么还需要独立的Host和Task State？
5. 你设计的滚动Planner具体如何工作？与ReAct、Plan-and-Execute有什么区别？
6. 你的Agent是否存在多个运行时？在线LLM、4B Grounder和MCP执行服务如何协作？为什么不统一到一个模型？

## 二、Skill-MoE稀疏门控与专家编排

1. 你为什么将传统Skill渐进式披露升级为Skill-MoE？与普通Skill Router、传统神经网络MoE分别有什么区别？
2. Skill Router具体如何实现？ Skill Registry保存哪些元数据？Embedding召回、Capability过滤、成本感知重排各自负责什么？
3. 你的Top-K如何动态确定？为什么不是固定Top-1？如何判断多激活一个Expert值得额外的Token和时延？
4. Router与Expert都会使用Capability，如何避免重复检索？ 为什么Topology、用户Memory和State Diff主要放在Expert侧？
5. 每个Expert是否对应一个独立LLM？专属Prompt、Skill文档、工具Schema如何加载和隔离？
6. 多个Expert如何通信？如何设计任务请求、结构化结果、错误码和证据引用，避免共享完整上下文？
7. 多个专家执行任务时，如何判断串行与并行？如何处理专家结果冲突以及同一设备的并发操作？
8. 多加一层Router真的能降低延迟吗？ Router的额外开销如何衡量？如果实际延迟反而增加怎么办？
9. Router选错Skill、Skill召回率下降怎么办？如何通过执行反馈优化门控策略？怎样区分路由错误和下游执行错误？

## 三、多模态Grounder与GRPO强化学习

1. 为什么选择Qwen3-VL-4B-Instruct？4B Grounder与主Planner分别承担什么任务？
2. 你的万级多模态数据集怎么构建？场景图像、指代设备、动作序列如何标注与校验？
3. 同类设备、遮挡目标和多轮模糊指代如何构造困难负样本？如何避免模型依赖文本捷径？
4. Grounder的LoRA具体微调哪些模块？ 为什么选择视觉后层、Visual Merger以及语言侧Attention/MLP？
5. SFT与GRPO分别解决什么问题？为什么不只做SFT？
6. GRPO中一个Prompt对应多少Rollout？奖励如何结合Grounding、动作参数、API可执行性和格式约束？
7. 如何防止Reward Hacking？如何保证奖励反映真实设备任务的成功，而不是模型学会迎合格式？
8. 4B Grounder推理时延多少？图像预处理、Prefill、Decode分别占多少？如何部署和优化？

## 四、Proposer–Verifier对抗验证与安全执行

1. 为什么需要Proposer–Verifier？普通Function Calling加Schema校验不能解决什么问题？
2. Proposer与Verifier之间具体如何博弈？ Proposer提出动作后，Verifier如何独立构建验收条件并寻找反例？
3. 如何实现Verifier的认知隔离？如果两个Agent共享同一个底层模型，如何避免同源错误和相互认同？
4. Verifier如何结合Topology Tree、Capability Registry和实时Observation判断动作是否合法？
5. False Done到底是怎么产生的？ 工具调用成功、设备动作执行成功与用户任务完成有什么区别？
6. Proposer被Verifier否决后，如何利用结构化反例修正动作？如何限制博弈轮数，避免双方反复争论？
7. 如果Verifier判断UNKNOWN，或者Expected State与Actual State不一致，系统如何处理？什么时候允许重试、重新规划或终止？
8. 每次动作都启动Verifier是否太慢？如何基于动作风险和证据充分性选择验证深度？

## 五、MCP工具调用、长程规划与状态恢复

1. 介绍一下你的MCP执行链路。与传统Function Calling有什么关系？为什么需要Host统一管理工具执行权限？
2. 接入大量MCP工具后，如何避免工具Schema过多导致上下文爆炸？ Skill-MoE与动态工具注册如何配合？
3. 长程任务如何通过Task DAG管理依赖、就绪节点与已完成节点？执行过程中如何实现局部Re-plan？
4. 如果工具调用耗时很长或服务中断，如何保证Agent不陷入死循环？ 超时、重试次数、Token预算及熔断如何设计？
5. MCP请求超时，但真实设备可能已经执行成功，如何避免重复开灯、重复调温等副作用？
6. Agent服务崩溃后，如何恢复上一次执行状态？对话History、完整Trajectory和Task State为什么需要分开保存？
7. 如果Agent服务部署新版本，原有Task State的Schema发生变化，未完成任务如何继续执行？
8. 你的长期记忆、任务状态和设备Capability Registry分别存在哪里？为什么选择MongoDB、MySQL/PostgreSQL和Redis等不同存储？

## 六、性能优化、部署与系统扩展

1. Agent部署在云端还是本地？Planner、Grounder、Router、Host分别部署在哪里？它们之间如何通信？
2. 多专家并行会增加LLM请求量，如何控制QPS、Token成本、并发数以及GPU资源消耗？
3. 如何定位整个Agent链路的性能瓶颈？Router、Grounder、Planner、MCP分别如何埋点和统计P50/P95？
4. 如果设备状态查询缓慢，如何利用缓存和增量State Diff优化？如何保证缓存与真实设备状态的一致性？
5. 当设备数量和Skill数量快速增加时，Router的检索效率与准确率如何保持？什么时候需要索引优化或分层路由？

## 七、实验评测与技术深挖

1. 你如何设计实验，证明Skill-MoE比普通Skill渐进式披露和Top-1 Router更好？
2. 如何衡量Skill召回率、工具调用准确率、任务成功率与非法动作拦截率？各指标怎么定义？
3. 项目中提到复杂任务成功率提升25%、Grounding准确率达到84%，具体基线、测试集与统计口径是什么？
4. 如何通过消融实验区分GRPO训练、Skill-MoE路由以及Proposer–Verifier分别带来的提升？
5. 如果让你重新设计这个项目，你会保留哪些机制、删除哪些过度设计？实际遇到的最大工程难点是什么？

## 23条建议Q&A

### 一、Workflow 和编排

1、请完整介绍 HomeClaw 的 Workflow：一条用户指令从进入 Host，到 Grounding、Routing、Planning、Verification、MCP 调用、MQTT 执行、状态确认和局部 Re-Plan，分别经过哪些节点？这套状态图是如何搭建和约束的？

**参考回答：** 我的核心取舍是把“语义不确定性”和“控制流确定性”分开：在线 LLM 只负责提出结构化动作，Host 掌握状态转移、预算、持久化和最终成功判定。这样即使模型输出漂移，执行链路仍然是有限、可恢复、可审计的，而不是让一个 ReAct 循环自行决定何时结束。状态枚举和预算定义分别见 [`WorkflowNode`](./homeclaw/workflow/state.py)（L14） 与 [`ExecutionBudget`](./homeclaw/workflow/state.py)（L33），生产组合入口见 [`ProductionRuntime`](./homeclaw/agent/runtime.py)（L184）。

#### 1）节点不是 Prompt 阶段，而是有明确输入输出的状态机

`[ProductionRuntime` 的 Handler 映射](./homeclaw/agent/runtime.py)（L216）把每个节点注册成确定性函数；LLM 只出现在 Plan 节点，其余节点都可以独立测试和恢复。

| 节点 | 核心输入与输出 | 转移及失败语义 | 对应代码 |
|---|---|---|---|
| `Receive` | 原始指令 → 规范化输入 | 不做业务判断，避免入口层偷偷改变语义 | [`_receive`](./homeclaw/agent/runtime.py)（L252） |
| `Route` | 指令、剩余 Token、Skill Registry → Top-K Skill、Tool/Resource 白名单 | 简单任务 Top-1，多意图/视觉任务 Top-2；无可靠候选进入 clarification | [`_route`](./homeclaw/agent/runtime.py)（L256）、[`SkillRouter`](./homeclaw/routing/router.py)（L27） |
| `Ground` | 图像、拓扑候选、房间/能力约束 → 唯一设备或 ambiguous | 只在命中消歧 Skill 时执行；缺上下文、超时或仍歧义直接 Reject，禁止猜测 | [`_ground`](./homeclaw/agent/runtime.py)（L302）、[`DeviceDisambiguationService`](./homeclaw/grounding/service.py)（L13） |
| `Plan` | 用户意图、被选 Tool、局部 Context、Verifier 反馈 → `ActionProposal[]` | Proposer 看不到全量工具；无安全提议直接 Reject；Token 使用量写回 Workflow | [`_plan`](./homeclaw/agent/runtime.py)（L363）、[`LLMProposer`](./homeclaw/agent/proposer.py)（L63） |
| `Verify` | 结构化提议 → 绑定后的动作或机器可读 issue | 先 Binder 唯一绑定，再校验 Capability、参数、风险、状态和批动作冲突；失败进入有限 Re-Plan | [`_verify`](./homeclaw/agent/runtime.py)（L379）、[`ActionVerifier`](./homeclaw/verification/verifier.py)（L37） |
| `Execute` | 已验证动作、允许 Tool 集 → `ExecutionEvidence[]` | 通过 MCP Dispatcher 执行；每个动作派生并持久化稳定 `command_id` | [`_execute`](./homeclaw/agent/runtime.py)（L415）、[`DurableActionDispatcher`](./homeclaw/agent/runtime.py)（L150） |
| `Confirm` | 业务 ACK/Observed State → Complete、Re-Plan 或 Fail | 只有全部 Evidence 为 `SUCCEEDED` 才完成；PUBACK 或 MCP 返回成功都不能越过此节点 | [`_confirm`](./homeclaw/agent/runtime.py)（L425） |
| `RePlan` | 上一轮结构化失败证据 → 新一轮 Plan | 不修改已经验证的事实，只把 issue 作为受控反馈；超过上限进入明确失败终态 | [`_replan`](./homeclaw/agent/runtime.py)（L411） |

主路径因此是 `Receive → Route → [Ground] → Plan → Verify → Execute → Confirm → Complete`。视觉 Grounding 是按需分支，不是每条请求都经过；Reject 表示输入、歧义或安全条件不满足，Fail 表示执行或预算耗尽，两者在业务语义上也分开。

#### 2）Workflow State 是最小可恢复状态，不是完整对话堆积

[`WorkflowState`](./homeclaw/workflow/state.py)（L47）保存当前节点、revision、已完成节点、Step/Token/Re-Plan 消耗、Deadline、结构化 data、错误和 `trace_id/request_id/task_id`。data 中只保留恢复所必需的路由结果、Grounding、提议、Verifier 反馈和执行证据，不把完整自然语言思维链当作 Blackboard。

[`WorkflowHost._run`](./homeclaw/workflow/engine.py)（L64）在每个节点结束后统一累加预算、推进节点并持久化；Checkpoint 与 Outbox 通过 [`save_with_outbox`](./homeclaw/workflow/postgres_store.py)（L64）在同一数据库事务提交，revision 充当乐观锁。因此三个典型崩溃窗口有不同处理：

1. **节点提交前崩溃**：Checkpoint 未推进，恢复后重新执行当前节点。
2. **Checkpoint 提交后、事件发布前崩溃**：Outbox 已与状态一起落库，Publisher 重放原 `message_id`，不会丢事件。
3. **设备已执行、Agent 尚未写回证据时崩溃**：Action Attempt 保存原 `command_id`；恢复时复用原命令并查询证据，不生成新命令盲目重放。

可重试 `DomainError` 会把任务留在同一节点并标记 WAITING；不可重试错误进入 Fail；未知异常也会转换成可审计的结构化错误，而不是让进程异常等同于任务消失。恢复入口见 [`WorkflowHost.resume`](./homeclaw/workflow/engine.py)（L56）。

#### 3）预算和验收证据

| 约束/证据 | 当前值 | 解决的问题 | 代码或测试 |
|---|---:|---|---|
| 最大 Workflow Step | 24 | 阻止状态图或工具调用无限循环 | [`ExecutionBudget`](./homeclaw/workflow/state.py)（L33） |
| 最大 Re-Plan | 2 | 防止 Proposer 与 Verifier 无效争论 | 同上 |
| 单任务 Token 预算 | 16,000 | 限制多轮规划成本 | 同上 |
| 全局 Deadline | 120 秒 | 给跨组件调用统一终止边界 | 同上 |
| 逐节点崩溃恢复 | 所有运行节点覆盖 | 验证从最后持久化节点继续 | [`test_every_runtime_node_can_resume...`](./tests/test_workflow.py)（L83） |
| Checkpoint/Outbox 原子性 | 同一连接上下文通过 | 排除“状态提交但事件丢失” | [`test_checkpoint_and_outbox...`](./tests/test_postgres_checkpoint.py)（L48） |
| False Done 回归 | PUBACK 无状态证据不得完成 | 确保 Confirm 独立于传输成功 | [`test_puback_without_state...`](./tests/test_production_runtime.py)（L141） |

这套设计的沉淀点不在“画了一个 DAG”，而在于每个状态都有可持久化输入输出、每个外部副作用都有幂等身份、每条失败路径都有有限终态。Host 因而既是编排器，也是执行语义和恢复语义的所有者。

2、在线 Planner、Skill Router、Host 和 Qwen3-VL-4B Grounder 分别部署在哪里？为什么 Grounder 只作为设备消歧 Skill 内部的工具，而不是 Agent 主模型？组件之间采用同步调用、消息队列还是 PostgreSQL Blackboard 传递信息，各自保存什么状态？

**参考回答：** 我没有按“一个组件等于一个 Agent、一个 Agent 等于一个进程”机械拆服务，而是先按资源特性、故障域和数据所有权划边界：CPU 上的确定性控制面保持紧凑，在线 LLM 和 GPU Grounder 作为外部推理面隔离，MCP–MQTT Bridge 靠近设备网络。这样减少不必要的分布式事务，同时又能独立扩缩最昂贵的推理资源。

#### 1）部署边界与状态所有权

| 组件 | 推荐部署 | 是否有持久状态 | 扩缩容依据 | 代码入口 |
|---|---|---|---|---|
| Host + Binder + Verifier | CPU 容器；首期模块化单体 | 自身无真相状态，状态写 PostgreSQL | Agent 请求并发、节点 P95 | [`ProductionRuntime`](./homeclaw/agent/runtime.py)（L184） |
| Skill Router | 与 Host 同进程或独立 CPU 服务 | Registry 版本化快照，可重建索引 | Skill 数、Recall@K、路由 P95/内存 | [`SkillRouter`](./homeclaw/routing/router.py)（L27） |
| Online Planner | GPT/Gemini 等远端模型 API | Provider 侧无 HomeClaw 任务真相 | QPS、在途 Token、模型配额与成本 | [`LLMProposer`](./homeclaw/agent/proposer.py)（L63） |
| Qwen3-VL-4B Grounder | 独立单 GPU Docker 服务 | 固定模型 revision；不保存 Workflow | GPU 利用率、显存、Batch、queue P95 | [`DeviceDisambiguationService`](./homeclaw/grounding/service.py)（L13）、[`compose.yaml`](./deploy/grounder/compose.yaml)（L1） |
| Domain MCP Server | 控制域 CPU 服务，可与 Host 同网段 | Tool/Prompt 版本与授权策略来自 Registry | MCP 调用 QPS、超时和错误率 | [`MCPHostGateway`](./homeclaw/mcp_runtime/host.py)（L13） |
| MCP–MQTT Bridge | 家庭边缘网关或靠近 Broker 的服务 | Topic 映射、短期去重；执行证据外存 | 设备数、消息率、状态确认 P95 | [`MqttCommandBridge`](./homeclaw/mqtt/bridge.py)（L79） |
| PostgreSQL Blackboard | 独立高可用数据服务 | Workflow、Checkpoint、Action Attempt、Registry、Outbox | 事务吞吐、锁冲突、恢复 RTO | [`PostgresCheckpointStore`](./homeclaw/workflow/postgres_store.py)（L14） |
| RabbitMQ Event Bus | 服务拆分后独立部署 | 持久消息但不拥有任务真相 | 堆积量、消费延迟、DLQ | [`AioPikaEventBus`](./homeclaw/events/rabbitmq_adapter.py)（L16） |

当前代码首先支持模块化单体，因为 Router、Verifier、MCP Client 拆成网络服务不会自动带来收益，反而增加序列化、超时和一致性窗口；Grounder 则从一开始独立部署，因为它有完全不同的 GPU 资源、冷启动和 OOM 故障域。

#### 2）为什么 Grounder 是 Skill 内部工具，而不是主 Agent

Grounder 的输入不是完整对话，而是 `image_uri + query + topology-anchored candidates`；输出是候选设备、bbox/分数、证据和是否歧义。[`DeviceDisambiguationService.resolve`](./homeclaw/grounding/service.py)（L22）先按房间和 Capability 过滤：没有候选则拒绝，只有一个候选就确定性返回，多个候选才调用视觉模型。模型超时、异常或返回候选集外 ID 时保持 ambiguous。

这个边界带来四点收益：

1. **成本**：没有视觉歧义的绝大多数指令不占 GPU。
2. **安全**：视觉模型只能在拓扑白名单中选择，不能凭图像生成任意设备 ID。
3. **可替换性**：更换 Qwen3-VL revision 不影响 Planner、Workflow 和 MCP 契约。
4. **故障隔离**：Grounder 不可用只拒绝视觉分支，不拖垮文本控制任务。

因此主 Agent 仍由在线 LLM 负责语义规划，4B 模型是受限感知工具；这也避免把 Grounder 的 GRPO 奖励与 Agent Verifier 的运行时安全规则混为一谈。

#### 3）同步调用、Blackboard 与消息队列不是三选一

我按一致性要求选择通信机制，而不是全系统统一一种协议：

| 通信类型 | 使用场景 | 选择原因 | 失败处理 |
|---|---|---|---|
| 同步强类型调用 | Route、Ground、Plan、Verify、MCP Command | 当前节点必须拿到结果才能决定下一状态；最容易传递 Deadline 和结构化错误 | 分层超时、有限重试、熔断；失败不推进 Checkpoint |
| PostgreSQL Blackboard | Workflow State、Checkpoint、动作尝试、Registry、Outbox | 这些数据决定恢复结果，必须事务化、可审计、支持 revision CAS | 提交成功才算节点完成；冲突重新读取，不做静默覆盖 |
| RabbitMQ Message | Checkpoint 后的跨服务通知、异步任务、审计和缓存失效 | 允许最终一致、需要削峰和独立消费；不应阻塞主事务 | Publisher Confirm、Quorum Queue、Manual ACK、DLX/DLQ、消费者幂等 |
| MQTT | Bridge 与物理设备/网关 | 适合弱网络和设备状态发布订阅 | QoS 只负责传输；业务成功仍由 ACK/State Evidence 确认 |

判断规则很简单：**如果消息丢失会改变任务恢复结果，就必须先写 Blackboard；如果它只是已提交事实的传播，就走 Outbox + RabbitMQ。** 这避免用 RabbitMQ 充当数据库，也避免数据库轮询承担所有实时通知。

跨服务 Envelope 使用 [`MessageEnvelope`](./homeclaw/domain/models.py)（L261），固定 `schema_version` 并传播 `trace_id/request_id/task_id/command_id/message_id`；RabbitMQ Adapter 对不兼容版本 fail-closed，并提供 Quorum Queue、手工 ACK 和 DLQ。高频传感器事件则不直接发给 LLM，只更新聚合 Resource，满足异常谓词或用户关注条件时才通知。

#### 4）关键通信时限与工程状态

| 边界 | 当前默认值 | 含义 |
|---|---:|---|
| Grounder 单次推理 | 10 秒 | 超时保持 ambiguous，不回退到猜测设备 |
| Grounder/Planner 排队 | 5 秒 | 超过容量快速失败，避免请求无限堆积 |
| 官方 MCP Session | 30 秒 | MCP 协议调用有独立 Deadline |
| MQTT Tool 执行确认 | 5 秒 | 超时进入 UNKNOWN/Re-Plan，不误报成功 |
| Workflow 全局 Deadline | 120 秒 | 所有局部调用的最终上界 |

当前分支已经实现进程内完整链路、PostgreSQL/RabbitMQ/MQTT/MCP/Grounder Adapter 和部署资产；外部基础设施、在线模型及 GPU 的真实联调仍按 [`外部验收清单`](./docs/external-acceptance.md)执行。也就是说，架构边界与失败语义已经落到代码，线上 QPS、GPU 显存和端到端 P95 仍必须以真实环境报告为准，不能拿进程内单测冒充。

### 二、记忆和上下文

3、HomeClaw 的短期上下文、长期用户记忆以及日/月摘要分别如何实现？MongoDB 中的偏好事实如何建模版本、来源、作用域和有效期，又如何解决显式偏好、推断偏好、临时偏好及多用户偏好之间的冲突？

**参考回答：** 我没有把“记忆”理解成把全部聊天记录塞进向量库，而是按生命周期、读写一致性和冲突语义拆成工作记忆、可恢复任务状态、长期偏好事实和周期摘要四层。这样能避免用户偏好、设备状态和 Agent 轨迹混在同一个检索空间里，也能明确每类信息由谁写、何时过期以及发生冲突时谁胜出。

#### 1）四层记忆模型

| 层级 | 保存内容 | 生命周期/真相源 | 为什么这样设计 | 对应代码 |
|---|---|---|---|---|
| 工作记忆 | 本轮路由、Grounding、提议、Verifier 反馈和执行证据 | 单任务；`WorkflowState.data` | 只保留后续节点和恢复必需的数据，不把完整思维链反复注入 LLM | [`WorkflowState`](./homeclaw/workflow/state.py)（L47） |
| 可恢复任务状态 | 当前节点、已完成节点、revision、预算、错误和关联 ID | 任务完成前；PostgreSQL Checkpoint | 对话历史和执行状态分离，服务重启后按状态机恢复而不是重新猜测进度 | [`WorkflowHost`](./homeclaw/workflow/engine.py)（L32） |
| 长期偏好事实 | 温度、灯光、媒体等用户偏好及作用域、来源、有效期 | 跨会话；MongoDB append-only fact | 偏好可能被覆盖、撤销或临时生效，需要时间语义和历史审计 | [`PreferenceFact`](./homeclaw/memory/preferences.py)（L42）、[`MongoPreferenceStore`](./homeclaw/memory/mongo_adapter.py)（L60） |
| 日/月摘要 | 指定周期事件的压缩文本、源事件 ID 和版本 | 跨会话；MongoDB versioned summary | 摘要是事件的派生视图；同一事件集重复运行必须幂等，源事件变化才升版 | [`SummaryService`](./homeclaw/memory/summaries.py)（L76）、[`MongoSummaryStore`](./homeclaw/memory/mongo_adapter.py)（L216） |

这里最重要的边界是：用户偏好回答“用户通常想要什么”，Workflow State 回答“这次任务执行到哪里”，设备状态回答“物理世界现在是什么”。三者不能互相覆盖，否则旧偏好可能被当成实时状态，或者一次失败轨迹被错误固化成长期偏好。

#### 2）偏好不是覆盖字段，而是带时间的事实

[`PreferenceFact`](./homeclaw/memory/preferences.py)（L42）包含 `user_id/key/value/source/scope/scope_id/confidence/valid_at/invalid_at/expires_at/supersedes`。写入新事实时，旧事实不被物理删除，而是填写 `invalid_at`，新事实记录被替代事实的 ID；撤销同样只关闭有效区间。因此系统既能解析“现在应该用哪个偏好”，也能回答“这个决策为什么使用它、此前是谁修改的”。

冲突解决分成两个阶段，避免简单的“最后写入获胜”：

| 决策阶段 | 排序规则 | 设计含义 |
|---|---|---|
| 同一 `user/key/scope/scope_id` 写冲突 | `EXPLICIT(3) > SYSTEM(2) > INFERRED(1)`，同来源再比较时间和置信度 | 行为推断不能覆盖用户明确说出的偏好；优先级定义见 [`_SOURCE_PRIORITY`](./homeclaw/memory/preferences.py)（L27） |
| 查询时跨作用域选择 | `DEVICE(3) > ROOM(2) > CONTEXT(1) > GLOBAL(0)`，再比较来源、时间和置信度 | “卧室空调 24℃”只在卧室覆盖“全屋 26℃”，不会污染其他房间；作用域定义见 [`_SCOPE_PRIORITY`](./homeclaw/memory/preferences.py)（L33） |
| 时间有效性 | `valid_at ≤ query_at < invalid_at/expires_at` | 临时睡眠偏好到期后自动退出候选，不需要后台任务物理删除 |
| 多用户隔离 | 所有写入、解析、历史和撤销都必须带 `user_id` | A 用户不能读取或撤销 B 用户的偏好 |

解析流程在 [`resolve`](./homeclaw/memory/preferences.py)（L155）和 Mongo 实现在 [`MongoPreferenceStore.resolve`](./homeclaw/memory/mongo_adapter.py)（L142）中保持相同语义。这里特意让“匹配当前设备的具体偏好”先于“全局显式偏好”，因为作用域代表适用条件而不是事实可信度；只有在同一作用域内，来源优先级才决定谁能覆盖谁。

#### 3）Mongo 并发写不是靠应用层先查后写

一次偏好更新在 Mongo Transaction 内完成：

1. 先按 `fact_id` 查询，重复请求直接返回原记录，实现 API 幂等。
2. 查询同一用户、key 和作用域下仍有效的事实。
3. 若已有更高来源优先级，新事实以“立即失效”状态留档，但不成为当前偏好。
4. 否则在同一事务中失效旧事实、插入新事实并写入 `supersedes`。

部署脚本为活跃事实建立 `(user_id,key,scope,scope_id)` 部分唯一索引，确保并发事务也不能产生两个当前事实，见 [`preferences-indexes.js`](./deploy/mongodb/preferences-indexes.js)（L8）。[`MongoPreferenceStore.add`](./homeclaw/memory/mongo_adapter.py)（L71）最多尝试 3 次，只重试 duplicate-key 11000、`TransientTransactionError` 和 `UnknownTransactionCommitResult`；Schema/数据错误立即抛出，避免把永久错误伪装成瞬时故障。

日/月摘要使用另一套幂等条件：`user_id + period + period_key` 唯一；若 `source_event_ids` 完全相同就直接返回当前版本，只有源事件集合变化才用当前 version 做 CAS 升级。这样定时任务重复触发不会制造摘要版本风暴。

#### 4）当前量化约束与回归证据

| 项目 | 当前值/结果 | 对应验证 |
|---|---:|---|
| Mongo 偏好并发最大尝试次数 | 3 | [`MongoPreferenceStore`](./homeclaw/memory/mongo_adapter.py)（L60） |
| Mongo 摘要 CAS 最大尝试次数 | 3 | [`MongoSummaryStore`](./homeclaw/memory/mongo_adapter.py)（L216） |
| 偏好冲突核心场景 | 5/5 通过 | 最新显式覆盖、低优先级拒绝、局部覆盖、临时过期、多用户隔离；见 [`test_temporal_memory.py`](./tests/test_temporal_memory.py)（L21） |
| 日/月摘要幂等与版本化 | 内存与 Mongo 两组通过 | [`test_summary_materialization...`](./tests/test_temporal_memory.py)（L146）、[`test_same_sources...`](./tests/test_mongo_summary_store.py)（L32） |
| Mongo 并发错误分类 | duplicate-key 可重试，Schema 错误不重试 | [`test_duplicate_key_race...`](./tests/test_mongo_preference_retry.py)（L35） |

这部分的个人沉淀在于：记忆冲突不能只靠 Prompt 里写一句“新偏好优先”，而要在数据模型、唯一索引、事务和查询排序四个层面保持同一语义，否则并发写入和服务恢复后会得到不同答案。

4、家居环境拓扑和设备 Capability Registry 为什么适合由 PostgreSQL 这类关系数据库维护？并发更新时如何利用事务、乐观锁和 Outbox 防止丢失更新？Redis 与 RabbitMQ 分别承担什么职责，为什么没有因为“高并发”就把它们当作数据库真相源，或者随意替换成 RocketMQ？

**参考回答：** 环境拓扑和 Capability Registry 有明确实体关系、版本约束与跨表一致性，适合放在 PostgreSQL。更新时调用方携带期望的 home version，数据库用 CAS 式 `UPDATE ... WHERE version = expected_version` 做乐观锁；房间、设备、能力和拓扑变更与 `registry_outbox` 在同一事务提交。版本不匹配就重新读取并合并，不使用静默 last-write-wins。

这里选择 PostgreSQL 不是因为 MySQL 无法实现，而是因为当前 Workflow Checkpoint、Registry 和 Outbox 都需要事务、外键、JSON Schema 与版本 CAS。把它们放在同一个 PostgreSQL 一致性边界内，可以少维护一套连接池、迁移和双写恢复流程；如果公司已有成熟 MySQL 平台，这套表和乐观锁语义同样可以迁移，关键不是数据库品牌，而是**谁是真相源、哪些字段必须一起提交**。

#### 1）关系库保存“配置真相”，Redis 不保存配置真相

| 数据对象 | 保存内容与约束 | 一致性角色 | 对应代码 |
|---|---|---|---|
| `home_registry` | 家庭聚合根、全局 `version`、元数据 | 所有房间、设备、能力和拓扑写入共享的乐观锁版本 | [`home_registry`](./deploy/postgres/002_registry.sql)（L3） |
| `room_registry` | 房间 ID、名称、独立版本，外键归属家庭 | 保证设备引用的房间属于同一家庭 | [`room_registry`](./deploy/postgres/002_registry.sql)（L10） |
| `device_registry` | 设备归属、在线标记、配置版本、最近状态版本/时间 | 保存设备目录及状态新鲜度指针；高频实时状态本体仍由设备权威源与缓存维护 | [`device_registry`](./deploy/postgres/002_registry.sql)（L19） |
| `capability_registry` | Tool 名称、Capability、参数 Schema、幂等等级、风险等级 | Verifier 与 Tool 收缩的确定性依据，不允许由 LLM 临时编造 | [`capability_registry`](./deploy/postgres/002_registry.sql)（L33）、[`ToolSpec`](./homeclaw/verification/registry.py)（L44） |
| `topology_edge` | `source-relation-target` 与关系属性 | Grounding 候选收缩、跨设备约束和冲突检测的图关系真相 | [`topology_edge`](./deploy/postgres/002_registry.sql)（L46） |
| `registry_outbox` | 与 Registry 变更同事务生成的待发布事件 | 连接数据库事务与消息系统，避免“表已改但事件丢失” | [`registry_outbox`](./deploy/postgres/003_registry_outbox.sql)（L3） |

Capability Schema 使用 JSONB 是为了容纳不同设备的参数差异，但设备、家庭和 Tool 的身份关系仍由主键、复合外键及唯一约束控制；这比把整张环境图作为一份 JSON 覆盖写入更容易做局部更新、审计和冲突定位。

#### 2）一次 Registry 更新的完整事务路径

以设备能力快照更新为例，[`upsert_device`](./homeclaw/verification/postgres_registry.py)（L79）按下面的顺序执行：

1. 调用方携带上一次读到的 `expected_home_version`，而不是只提交一份无版本的新对象。
2. [`_advance_home`](./homeclaw/verification/postgres_registry.py)（L319）首先执行 `UPDATE home_registry ... WHERE version = expected`。只有命中一行，当前事务才取得这个家庭聚合的下一版本；未命中立即抛出 `RegistryConflict`，子表还没有被修改。
3. 在同一连接、同一事务中 Upsert 设备目录。设备能力被定义为**完整快照**，因此先删除该设备旧 Capability，再逐条插入本次 Tool 集合；任一 Schema 插入失败会连同 home version 一起回滚。
4. [`_enqueue`](./homeclaw/verification/postgres_registry.py)（L335）在相同事务里写入带唯一 `message_id` 的 Registry 事件。只有设备快照和 Outbox 都成功，事务才提交。
5. 独立发布进程通过 [`pending_events`](./homeclaw/verification/postgres_registry.py)（L280）分页读取未发布事件；RabbitMQ Publisher Confirm 成功后才调用 [`mark_event_published`](./homeclaw/verification/postgres_registry.py)（L304）。当前代码提供了 Outbox 读写端和 RabbitMQ Adapter，生产组合层仍必须遵守这个“先 Confirm、后标记”的顺序。

假设写入者 A、B 都读到家庭版本 12：A 的 CAS 先成功并把版本推进到 13；B 仍以 12 更新时影响行数为 0，会在任何设备/能力变更前失败。B 必须重新读取版本 13，判断自己的更新是可合并、应覆盖还是应提示冲突，再用新版本提交。这个过程是**检测丢失更新**，而不是自动把两个业务上矛盾的配置拼在一起。

#### 3）Outbox 解决的是双写窗口，不承诺“消息恰好一次”

| 故障位置 | 数据库/消息状态 | 恢复方式 |
|---|---|---|
| Registry 或 Outbox 写入失败 | 整个数据库事务回滚 | 调用方按错误类型决定是否用同一请求重试 |
| 数据库提交成功，RabbitMQ 发布失败 | Registry 已生效，Outbox 仍为未发布 | 发布器再次扫描同一事件并重试 |
| RabbitMQ 已接收，但进程在标记 `published_at` 前崩溃 | 同一 `message_id` 可能再次投递 | 消费者按 `message_id` 幂等；不能依赖 MQ 提供业务“恰好一次” |
| 消费者处理失败 | 消息不应被 ACK | 手工 ACK 配合 DLX/DLQ，人工或自动修复后重放 |

[`AioPikaEventBus`](./homeclaw/events/rabbitmq_adapter.py)（L16）启用 Publisher Confirm、持久化 Topic Exchange、Quorum Queue、Manual ACK 和死信队列，并对未知 `schema_version` fail-closed。Quorum Queue 提高 Broker 故障下的消息可用性，但它仍不能替代数据库事务或消费端幂等。

#### 4）PostgreSQL、Redis、RabbitMQ 与 RocketMQ 的职责边界

| 组件 | 当前职责 | 明确不负责 |
|---|---|---|
| PostgreSQL | Registry/Topology 真相、版本 CAS、关系约束、Outbox 与审计 | 高频传感器热路径和毫秒级临时去重 |
| Redis | 60 秒设备状态缓存、短期命令幂等、租约及可重建的派生数据；实现见 [`RedisStateCache`](./homeclaw/state/redis_adapter.py)（L68）与 [`RedisIdempotencyStore`](./homeclaw/state/redis_adapter.py)（L140） | 家庭拓扑、能力 Schema 和不可丢的任务真相 |
| RabbitMQ | 已提交事实的跨服务传播、削峰、失败重试和 DLQ | 判断设备动作是否成功，也不作为 Registry 的唯一副本 |
| RocketMQ | 当前未引入 | 不是因为能力不足，而是当前没有用压测证明需要更高吞吐、长时间日志保留或严格分区顺序；贸然加入只会扩大运维面 |

如果后续事件量、保留周期或顺序消费需求超过 RabbitMQ 的目标 SLO，可以保留统一 `MessageEnvelope` 和 Outbox 契约，重新做 RabbitMQ/RocketMQ/Kafka 的同场压测后替换 Adapter；技术选型应由吞吐、P95、积压恢复时间和运维成本共同决定，而不是由“高并发”三个字决定。

#### 5）当前量化约束与回归证据

| 项目 | 当前值/结果 | 说明与验证 |
|---|---:|---|
| 家庭聚合并发控制 | 每次成功写入版本 +1 | 旧版本写入在子表变更前失败；见 [`test_stale_home_version...`](./tests/test_postgres_registry.py)（L74） |
| Registry Outbox 默认扫描批次 | 100 条 | 显式正数校验，防止无界加载；见 [`pending_events`](./homeclaw/verification/postgres_registry.py)（L280） |
| RabbitMQ 单消费者预取 | 16 条 | 控制在途消息与消费者内存；见 [`connect`](./homeclaw/events/rabbitmq_adapter.py)（L25） |
| Registry 事务/CAS/Outbox 场景 | 3/3 通过 | 设备快照同事务、陈旧版本零子表写入、房间/拓扑同样使用 CAS；见 [`test_postgres_registry.py`](./tests/test_postgres_registry.py)（L49） |
| 事件幂等与版本契约场景 | 2/2 通过 | 进程内 Event Bus 按 `message_id` 去重、Rabbit Envelope 拒绝未知版本；见 [`test_production_adapters.py`](./tests/test_production_adapters.py)（L90、L172） |

这些数值是事务不变量、批次上限和回归覆盖，不是外部 PostgreSQL/Redis/RabbitMQ 的生产吞吐量。没有真实部署报告之前，不能把 3/3 单测包装成“并发更新成功率 100%”。这部分设计的核心沉淀是：高并发一致性首先要划清真相源和提交边界，Redis 与 MQ 用来加速和传播，不能拿来掩盖数据库双写与业务冲突。

5、当设备状态查询较慢时，缓存、增量 State Diff、TTL 和全量对账如何协同工作？系统怎样识别重复、乱序和丢失的 Diff，并保证 Redis 缓存最终能够与真实设备状态恢复一致？

**参考回答：** 每个状态快照带 `home_id/device_id/sequence/observed_at/expires_at/source`，当前默认 TTL 为 60 秒。新 Diff 的 sequence 等于当前版本时判为 DUPLICATE，小于当前版本判为 OUT_OF_ORDER，大于当前版本加一以上且不是完整快照时判为 GAP；这三种情况都不能把不完整数据覆盖到新状态上。

正常增量只做嵌套字段合并；发生 GAP、缓存缺失或 TTL 过期时，Read-through 服务从设备/网关权威接口读取完整快照并跨版本修复。`StateReconciler` 再周期性全量对账漏失事件。MQTT retained state 还必须通过采集时间、设备在线状态和必要的主动查询，不能仅凭“是 retained message”认定仍然真实。

#### 1）缓存记录的是“带证据的状态”，不是一个无版本 JSON

| 字段 | 作用 | 关键约束 |
|---|---|---|
| `home_id + device_id` | 缓存键与租户边界 | 相同设备 ID 在不同家庭不能共享状态 |
| `sequence` | 设备/网关状态流的单调版本 | 用来识别重复、乱序和中间事件缺口 |
| `observed_at` | 物理状态实际被观测的时间 | 不能用消费者收到消息的时间代替 |
| `expires_at` | 新鲜度上界 | TTL 到期只表示“不能直接信任”，不等于设备状态被重置 |
| `source` | MQTT、主动查询或对账来源 | 冲突和故障排查时区分实时事件与权威修复 |
| `full_snapshot` | 当前消息是否包含完整设备状态 | 只有完整快照才能安全跨越 sequence GAP |

数据契约见 [`VersionedStateDiff`](./homeclaw/state/cache.py)（L22）和 [`StateSnapshot`](./homeclaw/state/cache.py)（L39）。默认 60 秒 TTL 是当前工程参数，不是所有设备统一的物理新鲜度：门锁、人体传感器应更短，固件版本等静态属性可以更长，生产配置应按 Capability 分层。

#### 2）State Diff 是一个小状态机，而不是无条件 Patch

[`InMemoryStateCache.apply`](./homeclaw/state/cache.py)（L88）和 [`RedisStateCache.apply`](./homeclaw/state/redis_adapter.py)（L77）遵守相同的 sequence 语义：

| 当前状态与输入 | 返回值 | 是否写缓存 | 原因 |
|---|---|---:|---|
| 无本地基线 | `APPLIED` | 是 | 接入协议必须保证首包是全量或字段完备；否则应先主动回源 |
| `new_seq < current_seq` | `OUT_OF_ORDER` | 否 | 迟到事件不能把新状态回滚 |
| `new_seq = current_seq` | `DUPLICATE` | 否 | QoS 1 或消息重放不重复修改状态 |
| `new_seq = current_seq + 1` | `APPLIED` | 是 | 增量字段递归合并，保留未变化的嵌套字段 |
| `new_seq > current_seq + 1` 且为增量 | `GAP` | 否 | 中间 Diff 缺失，继续 Patch 会得到残缺状态 |
| `new_seq > current_seq + 1` 且为全量 | `APPLIED` | 是 | 权威快照可以跨版本修复缺口，并整体替换旧状态 |

Redis Adapter 通过 Lua 在一个 Redis 操作内完成 sequence 比较、Hash 写入和 `PEXPIRE`，防止两个进程把较旧版本覆盖到较新版本，脚本见 [`_APPLY_STATE_LUA`](./homeclaw/state/redis_adapter.py)（L21）。

这里有一个容易被忽略的工程边界：当前 Redis 实现先在客户端读取旧 JSON、完成嵌套合并，再由 Lua 提交新版本。Lua 能保证**版本不回退**，但若同一设备允许多个消费者同时合并相邻 Diff，旧的预读状态仍可能造成字段级丢失。因此生产部署必须让同一 `device_id` 按 key 串行消费，或者把“期望前序版本 + 合并”整体移入服务端脚本；在完成这一项前，只能声称实现了 sequence CAS，不能声称任意并发下的字段合并已经线性一致。

#### 3）读路径采用“新鲜命中—权威回源—对账修复”三级策略

1. [`ReadThroughStateService`](./homeclaw/state/reconcile.py)（L57）先读取未过期缓存；命中时直接返回并记录 `state.cache=hit`。
2. 缓存不存在或已过期时，保留旧值仅作为诊断候选，再调用设备网关/平台的 Authoritative Reader。
3. 回源成功后，以 `full_snapshot=True` 写回缓存；回源失败默认抛错，只有调用方显式设置 `allow_stale_on_error` 时才允许降级返回旧快照，并单独记录 `state.stale_fallback`。这样上层知道自己拿到的是陈旧证据，而不是悄悄把它当真。
4. [`StateReconciler`](./homeclaw/state/reconcile.py)（L25）周期性读取权威全量状态，对比 sequence 和字段差异；发现漏失事件或同版本内容异常时先失效旧缓存，再用完整快照修复。

因此缓存一致性不是“TTL 一到就自动正确”，而是 TTL 负责暴露不确定性、sequence 负责阻止倒退、GAP 负责发现事件缺失、Authoritative Read/Reconcile 才负责恢复。Redis 整体丢失也不会丢掉家居真相，因为它是可重建派生层。

#### 4）命令后的 Read-Your-Write 必须依赖新状态证据

[`MqttCommandBridge.execute`](./homeclaw/mqtt/bridge.py)（L99）先检查已知离线状态并订阅 State Topic，再发布包含稳定 `command_id` 的命令；Broker PUBACK 只表示消息被接收，没有匹配设备证据时终态保持 `UNKNOWN`。确认逻辑在 [`_wait_for_confirmation`](./homeclaw/mqtt/bridge.py)（L253）中执行：

- 状态中若包含其他 `command_id`，不能确认本次命令。
- 设备明确返回 `rejected/failed` 时立即形成业务拒绝证据，不伪装成超时。
- retained 消息若没有本次 `command_id`，直接忽略；即使 ID 匹配，也必须有可解析的 `observed_at` 且年龄不超过设备映射的阈值。
- 状态还必须递归满足 `expected_state`；只要求目标字段匹配，允许设备返回额外遥测字段，规则见 [`matches_expected_state`](./homeclaw/state/cache.py)（L63）。
- Availability retained 消息同样检查采集时间；已知离线设备在命令发布前失败，避免制造无意义的等待。

严格因果一致性还有一个必须如实说明的边界：当前 Bridge 允许**非 retained** 状态在不带 `command_id` 时，仅凭 Expected State 匹配确认，也没有强制其 `observed_at` 晚于命令发送时间。它适配了部分旧设备，但在高并发同目标写入时可能把无关状态当成本次证据。生产接入应要求网关回传 `command_id + observed_at`，或在 Bridge 中记录发送时刻并拒绝更早证据；未加固前，不能把兼容模式包装成严格线性一致的 Read-Your-Write。

#### 5）高频事件只更新聚合 Resource，不持续灌入 LLM

[`StateResourcePublisher`](./homeclaw/mcp_runtime/resources.py)（L11）把 Diff 写入同一版本化缓存，MCP Resource 只暴露聚合后的 `sequence/observed_at/stale/state`。只有 `should_notify(previous,current)` 命中异常、条件达成或用户订阅时才发送 Resource Updated；普通温度波动只刷新快照。这样状态层可以处理高频流，Agent 上下文只接收对任务有意义的变化。

#### 6）当前量化约束、指标口径与回归证据

| 项目 | 当前值/结果 | 对应代码或验证 |
|---|---:|---|
| 默认状态 TTL | 60 秒 | 内存与 Redis Cache 默认值；见 [`InMemoryStateCache`](./homeclaw/state/cache.py)（L80）、[`RedisStateCache`](./homeclaw/state/redis_adapter.py)（L68） |
| Diff 判定结果 | 4 类 | `APPLIED / DUPLICATE / OUT_OF_ORDER / GAP`；见 [`ApplyResult`](./homeclaw/state/cache.py)（L14） |
| 内存缓存、Resource、回源和指标场景 | 8/8 通过 | 4 个 Cache、3 个 Resource/Reconcile、1 个一致性指标测试；见 [`test_state_cache.py`](./tests/test_state_cache.py)（L16）、[`test_state_resources.py`](./tests/test_state_resources.py)（L38）、[`test_state_consistency_metrics.py`](./tests/test_state_consistency_metrics.py)（L9） |
| Redis sequence CAS/GAP 场景 | 2/2 通过 | 较旧版本拒绝、增量缺口拒绝；见 [`test_production_adapters.py`](./tests/test_production_adapters.py)（L105、L118） |
| MQTT 确认与异常场景 | 10/10 通过 | PUBACK 非成功、正确/错误命令状态、业务拒绝、Broker 故障、离线、旧 retained、迟到 ACK 与幂等重试；见 [`test_mqtt_bridge.py`](./tests/test_mqtt_bridge.py)（L33） |
| 可聚合的一致性指标 | 8 项 | Cache Hit、Stale Read、Read-Your-Write、对账差异率、确认 P50/P95、对账 P50/P95；见 [`StateConsistencySummary`](./homeclaw/eval/state_consistency.py)（L24） |

当前仓库已经定义并测试这些判定与指标，但没有启动真实 Redis、MQTT Broker 和设备网关生成稳定观测窗口，因此还没有可信的缓存命中率、陈旧读比例、确认 P95 或对账恢复时间。面试时可以陈述“8+2+10 个确定性场景全部通过”，但不能把它换算成“线上状态一致性 100%”；生产数值必须绑定设备数、事件频率、网络故障模型、观测时长和原始报告。

6、HomeClaw 的 Skill-MoE 如何缓解长上下文和全量 Tool Schema 暴露问题？请说明 Skill Registry、Top-K Router、按需加载和 Expert 内工具收缩的具体实现，并解释它与普通 Router、渐进式 Skill 披露及神经网络 MoE 的区别。

**参考回答：** 我把 Skill-MoE 定义为**工程型条件计算与上下文稀疏化**，而不是参数级神经网络 MoE。在线 GPT/Gemini 仍是唯一主规划模型；Skill Expert 是一份可版本化的能力包，包含领域描述、召回特征、允许的 Tool 引用和知识资源 URI。只有视觉指代确实歧义时，`device-disambiguation` Skill 才会额外调用 4B Grounder，因此“激活多个 Expert”不等于并行调用多个大模型。

#### 1）Skill Registry 解决的是唯一事实来源和共享 Tool 复用

| 对象 | 当前建模内容 | 设计目的 | 对应代码 |
|---|---|---|---|
| Tool | 稳定名称、描述、Input Schema、风险等级 | Tool 只定义一次，多个 Skill 通过名称引用，避免复制 Schema 后产生版本和权限漂移 | [`ToolDefinition`](./homeclaw/routing/models.py)（L12） |
| Skill Expert | `skill_id/domain/description/keywords/tool_names/knowledge_resource_uris/activation_phrases/competence/available/version` | 把召回特征、能力边界和披露内容放进同一注册项 | [`SkillDefinition`](./homeclaw/routing/models.py)（L24） |
| Registry | Tool/Skill 唯一注册与引用校验 | 启动时拒绝重复 Tool、重复 Skill 和未知 Tool 引用，不把配置错误推迟到模型调用阶段 | [`SkillRegistry`](./homeclaw/routing/registry.py)（L12） |
| 当前实例 | 7 个 Skill、11 个 Tool | 覆盖澄清、灯光、空调、媒体、安防、家电和视觉消歧 | [`registry.json`](./homeclaw/skills/registry.json)（L2、L60） |

这里的 Expert 不是一个独立 Prompt 或独立 Agent 服务。它更接近“领域能力清单 + 最小知识入口 + Tool 白名单”；真正执行动作的仍是统一 Host、Verifier 和 MCP 链路。这样多个 Expert 可以共享 `get_device_state`，又不会为每个 Expert 复制一套实现。

#### 2）第一层稀疏：先召回 Skill，再披露 Tool

[`SkillRouter`](./homeclaw/routing/router.py)（L27）的路由过程分为五步：

1. **建索引**：启动时把 `skill_id/domain/description/keywords` 分词并建立 token→Skill 倒排索引；中文单字额外生成 bigram，查询时不扫描完整 Tool Schema。
2. **候选召回**：只取与查询 token 有交集的 Skill；指定 `required_domains` 时再加入对应领域候选。带 `activation_phrases` 的视觉消歧 Skill 必须命中明确短语，避免普通“lamp”请求无故占用 Grounder。
3. **确定性打分**：按 `0.70×归一化词法相关度 + 0.20×关键词覆盖 + 0.10×competence` 计算，低于 0.12 的候选被过滤，公式见 [`_score`](./homeclaw/routing/router.py)（L132）。
4. **动态 Top-K**：[`AdaptiveTopKPolicy`](./homeclaw/resilience/controls.py)（L195）对普通请求选 Top-1，检测到“and/then/同时/图里”等多意图或视觉标记时选 Top-2，硬上限 Top-3；剩余 Token 预算不足 1000 时退回 Top-1。
5. **安全回退**：没有候选通过阈值时，不选择得分最高的“近似 Skill”，而是进入 `clarification`，只披露 `request_clarification`。

当前所谓“动态”是基于规则标记和 Token 余量，并不是由路由置信度、历史负载或学习型 Gate 自动决定 K。它的优点是可解释和稳定；缺点是复杂度判断仍较粗，后续若引入学习型 Gate，也必须继续受最大 K、预算和安全回退约束。

#### 3）按需加载实际加载的是 Tool Schema，避免全量上下文注入

Router 将命中 Skill 的 Tool 引用求并集，同时携带对应知识资源 URI，形成 [`RouteDecision`](./homeclaw/routing/models.py)（L68）。[`ProductionRuntime._route`](./homeclaw/agent/runtime.py)（L256）把 Skill、Tool、Resource 与 Top-K 写入 Workflow State；到规划节点时，[`LLMProposer.propose`](./homeclaw/agent/proposer.py)（L76）只序列化 `route.exposed_tools` 对应的名称、描述和 Input Schema，而不是把 Registry 的 11 个 Tool 全部交给在线模型。

模型输出后还有两道白名单检查：

- `tool_name` 必须属于本次 `route.exposed_tools`；
- `source_skill` 必须属于本次 `selected_skill_ids`。

越界输出在 [`_parse_action`](./homeclaw/agent/proposer.py)（L139）直接拒绝，不能因为模型“知道”某个未披露 Tool 名称就绕过 Router。

这里需要区分**接口已存在**和**内容已注入**：Resource URI 已被 Router 选中并保存在 Workflow State，但当前 `LLMProposer` 只注入 Tool Schema 与调用方 Context，还没有根据 URI 自动读取 MCP Resource。也就是说，Tool 渐进式披露已经打通，知识 Resource 的统一 Resolver/摘要注入仍是预留边界，不能表述成“所有 Expert 知识都已按需加载”。

#### 4）第二层稀疏：在 Skill 内按真实设备能力继续收缩

第一层回答“这是什么能力域”，第二层回答“当前候选设备实际上支持哪些动作”。[`ToolSpaceContractor`](./homeclaw/routing/contraction.py)（L25）执行下面的集合运算：

```text
最终工具集 = 路由工具集
          ∩（候选设备在 Capability Registry 中的 Tool 并集
             ∪ request_clarification/get_device_state）
```

例如 lighting Skill 允许开、关和调亮度，但候选是只支持开关的普通灯，`set_light_brightness` 会在规划前被删除；Proposer 从上下文里根本看不到这个不可执行动作。设备能力来自确定性 Capability Registry，不能由模型根据设备名称猜测。

这个实现有三个细节：

1. Contractor 自身不负责全屋拓扑检索，它只消费上游已经按 `home/room/capability` 锚定的 `DeviceRef`，因此“知识锚定”和“Tool 收缩”是前后两个步骤。
2. 候选为空时当前实现保留第一层工具集，而不是收缩成空集，目的是让 Planner 仍能发起澄清；后续 Verifier 仍会阻止不存在设备的实际执行。
3. [`ProductionRuntime._route`](./homeclaw/agent/runtime.py)（L256）目前只在初始 Context 已有 `candidate_devices` 时执行二次收缩。视觉 Grounding 在之后才写入单一候选，而 [`_ground`](./homeclaw/agent/runtime.py)（L302）当前只移除 `ground_visual_device`，没有再次调用 Contractor。因此视觉路径要么由上游预先提供候选，要么还需要补一次 Ground 后收缩；现阶段不能宣称所有路径都已自动完成第二层收缩。

#### 5）它与三种相近方案的本质区别

| 方案 | 路由/披露粒度 | 是否按设备能力二次收缩 | 是否增加 LLM 数量 | 是否训练 Gate/Expert 参数 |
|---|---|---:|---:|---:|
| 全量 Tool Schema | 无，所有 Tool 一次暴露 | 否 | 通常 1 个主模型 | 否 |
| 普通 Router | 通常只选一个领域或 Tool 组 | 不一定 | 通常不增加 | 可规则、Embedding 或分类模型 |
| 渐进式 Skill 披露 | 先给 Skill 摘要，命中后再读正文/Tool | 通常停在 Skill 边界 | 可能需要一次额外读取或模型轮次 | 否 |
| HomeClaw Skill-MoE | 动态 Top-K Skill，再对候选设备做 Capability 交集 | 是，但受上述接入条件限制 | 主 Planner 仍为 1 个；Grounder 条件调用 | 当前不训练 |
| 神经网络 MoE | Token 级 Gate 选择参数 Expert | 不适用 | 一次模型前向中的稀疏参数计算 | 是 |

所以 Skill-MoE 的“MoE”借用的是**稀疏门控、条件激活和专家专长**这三个思想，不应包装成训练了 Mixtral 式 Router，也不应说每个 Skill 都是一个独立大模型。它的工程价值在于减少模型可见的无关 Schema，并在生成前把不可执行动作从候选空间删除。

#### 6）当前参数与回归证据

| 项目 | 当前值/结果 | 对应验证 |
|---|---:|---|
| Registry 规模 | 7 Skill / 11 Tool | [`registry.json`](./homeclaw/skills/registry.json)（L2、L60） |
| Router 最低分 | 0.12 | [`SkillRouter.__init__`](./homeclaw/routing/router.py)（L28） |
| Top-K 策略 | 普通 1、复杂 2、最大 3；Token <1000 时为 1 | [`AdaptiveTopKPolicy`](./homeclaw/resilience/controls.py)（L195） |
| Router 契约场景 | 7/7 通过 | 单/多意图、视觉、Fallback、共享 Tool、坏 Registry 与指标；见 [`test_skill_router.py`](./tests/test_skill_router.py)（L24） |
| Capability 二次收缩场景 | 2/2 通过 | 支持能力交集与无候选保留；见 [`test_tool_contraction.py`](./tests/test_tool_contraction.py)（L20） |

这部分的核心思考是：上下文治理不只是“把 Prompt 写短”，而是把可见能力空间变成一个逐层收敛的集合；同时每一层都必须保留明确回退路径，否则收缩率越高，漏召回和误拒绝的风险也越大。

7、你如何量化“双层稀疏”设计的实际收益？请分别与全量 Tool Schema 的 ReAct、全量 Tool Schema 的 Plan-and-Solve、普通 Router 加渐进式披露进行对照：四组方案的平均规划步数、Prompt/Completion/总 Token、候选工具数、P50/P95、单任务成本和长程任务成功率实测值分别是多少？HomeClaw 相对各基线将规划步数和 Token 降低了百分之多少、将成功率提升了多少个百分点？实验使用什么模型、硬件、数据集、样本量、并发度和随机种子，结果是否给出方差或置信区间？

**参考回答：** 我把量化证据分为三层：第一层是当前 production-ready Router 的可复现离线报告；第二层是 Capability Contractor 的合成规模实验；第三层才是在线模型四策略端到端实验。前两层可以证明“候选空间被收缩且召回没有在现有 Gold 集上丢失”，但不能替代规划步数、真实 Token、成本和最终设备状态成功率。

#### 1）当前离线路由报告的实验边界

| 项目 | 当前记录 |
|---|---|
| 数据集 | [`router_gold.jsonl`](./data/eval/router_gold.jsonl)（L1），25 条中英文指令；18 条单标签、7 条多标签 |
| Registry | 7 Skill、11 Tool |
| 对照 | HomeClaw 确定性 Router 与普通 TF-IDF 向量空间 Router，分别跑 Top-1/Top-2 |
| 运行环境 | Python 3.10.22、Windows 10；见 [`报告 provenance`](./reports/router-eval-2026-11-09.json)（L2） |
| 在线模型/GPU | 未调用；这是 CPU 进程内确定性路由实验 |
| 并发与随机种子 | 单进程顺序执行；算法无随机采样，因此没有 seed |
| 重复与区间 | 每条 Query 在主评测中执行一次，未报告方差或置信区间；CPU 型号也未记录 |

因此下面的亚毫秒 P50/P95 只用于同机代码路径对比，不能作为生产 SLO。评测逻辑与 Schema 序列化口径在 [`evaluate`](./scripts/evaluate_router.py)（L60）中固定，完整原始决策保留在 [`router-eval-2026-11-09.json`](./reports/router-eval-2026-11-09.json)。

#### 2）第一层 Skill Router 的实测结果

平均 Tool 数由报告中的 Tool Contraction Ratio 和 Registry 的 11 个 Tool 推导；Schema Bytes 是把模型实际可见的 Tool 名称、描述和 Input Schema 做紧凑 UTF-8 JSON 序列化后的字节数。

| 策略 | 平均暴露 Tool | 平均 Schema Bytes | 相对全量收缩 | Recall@K | MRR | 多标签完整覆盖 | Fallback | P50/P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 全量 Schema | 11.00 | 2406.00 | 0% | — | — | — | — | — |
| TF-IDF Top-1 | 2.76 | 585.56 | 75.7% | 72% | 0.84 | 60% | 0% | 0.0356/0.0485 ms |
| HomeClaw Top-1 | 3.48 | 727.12 | 69.8% | 86% | 1.00 | 72% | 4% | 0.0458/0.0867 ms |
| TF-IDF Top-2 | 4.44 | 958.28 | 60.2% | 92% | 0.90 | 88% | 0% | 0.0343/0.0511 ms |
| HomeClaw Top-2 | 4.40 | 928.72 | 61.4% | 100% | 1.00 | 100% | 4% | 0.0511/0.0859 ms |

原始结果分别见 [`HomeClaw Top-1`](./reports/router-eval-2026-11-09.json)（L10）、[`HomeClaw Top-2`](./reports/router-eval-2026-11-09.json)（L286）、[`TF-IDF Top-1`](./reports/router-eval-2026-11-09.json)（L572）和 [`TF-IDF Top-2`](./reports/router-eval-2026-11-09.json)（L848）。

可直接计算出三组有意义的差值：

- 相对全量 Schema，HomeClaw Top-2 将平均 Tool 数从 11 降到 4.40，减少 **60.0%**；Schema 从 2406 降到 928.72 Bytes，减少 **61.4%**。
- 相对 TF-IDF Top-2，HomeClaw Top-2 的 Recall 提升 **8 个百分点**，多标签完整覆盖提升 **12 个百分点**，MRR 提升 **0.10**；同时 Schema Bytes 再减少 **3.1%**。
- HomeClaw Top-2 的 P95 比 TF-IDF 多约 **0.0348 ms**，相对增加约 **68.1%**，但绝对值仍小于 0.1 ms。这里应同时讲绝对值与相对值，不能只挑有利指标。

TF-IDF Top-1 的 Schema 更小并不代表更好，因为它以漏掉正确 Skill 换取了更高收缩率；其 Fallback 为 0% 也不是优势，模糊样本被错误路由而不是安全澄清。对智能家居而言，收缩率必须和 Recall、完整覆盖及正确拒答一起看。

#### 3）第二层 Capability 收缩目前只有合成场景证据

[`device_scale_benchmark`](./scripts/evaluate_router.py)（L150）固定一条 lighting Route：第一层暴露 5 个 Tool，候选设备只支持绝对开灯动作；Capability Contractor 最终保留 `request_clarification/get_device_state/turn_light_on` 共 3 个 Tool，即该合成场景第二层再减少 **40%**。

| 候选设备数 | 收缩后 Tool | Contractor P50 | Contractor P95 |
|---:|---:|---:|---:|
| 100 | 3 | 0.0283 ms | 0.0367 ms |
| 1000 | 3 | 0.2555 ms | 0.2940 ms |
| 5000 | 3 | 1.3005 ms | 1.3779 ms |

原始数据见 [`device_scale`](./reports/router-eval-2026-11-09.json)（L1174）。这证明 Contractor 能按 Capability 过滤且当前实现随候选设备数近似线性增长，但它不是 25 条 Gold 集上的平均二次收缩，也没有经过在线 Planner。特别要注意：前面的 **61.4% 只属于第一层 Top-2 Skill Router**，不能包装成双层稀疏的总 Token 降幅。

#### 4）Bytes 不能直接改写成真实 Token

Bytes 是与模型无关、可完全复现的 Schema 体积；Token 取决于 GPT/Gemini 的具体 tokenizer、消息封装和服务端版本。当前 Router 报告没有调用模型 tokenizer，因此 928.72 Bytes 不能直接换算成某个 Token 数。

旧 Coordinator 的 M6 Smoke 在同一简单指令上得到下表：

| 旧版策略 | Prompt 计数 |
|---|---:|
| OnePrompt | 105 |
| HomeClaw 概览懒加载 | 182 |
| HomeClaw 关闭懒加载、注入全文 | 493 |
| SAGE 全文 ReAct | 523 |
| Sasha 两阶段 | 1033 |

对应测试见 [`test_lazy_loading`](./tests/smoke_m6.py)（L58）和 [`test_baseline_differentiation`](./tests/smoke_m6.py)（L83）。182 相对 493 减少 **63.1%**，相对 SAGE 的 523 减少 **65.2%**。但 [`MockLLM._usage`](./homeclaw/llm.py)（L85）实际使用 `len(text.split())` 统计空白分词，它只是 Prompt 长度代理，不是真实 GPT/Gemini Token；而且这套旧实验验证的是 `SKILL.md` 概览/全文懒加载，不是当前 Top-K + Capability 双层收缩。面试时可以把它作为机制 Smoke，不应把 182 写成线上 Token 成本。

#### 5）四策略在线实验的当前完成度

[`StrategyName`](./homeclaw/eval/strategy_benchmark.py)（L16）已经固定四个对照组；[`BenchmarkConfig`](./homeclaw/eval/strategy_benchmark.py)（L49）记录模型、Prompt 版本、温度、Seed、Token/Step 上限、数据集和价格，并生成配置哈希；[`run_strategy_benchmark`](./homeclaw/eval/strategy_benchmark.py)（L95）统一聚合成功率、规划步数、Prompt/Completion/总 Token、成本、Tool/Schema 数、P50/P95 和失败分布。

| 四策略 | 当前可复现证据 | 平均规划步数/真实 Token/成本/成功率 |
|---|---|---|
| 全量 Tool ReAct | 只有策略枚举与 Harness 接口 | **N/A：尚无在线 Runner 和原始报告** |
| 全量 Tool Plan-and-Solve | 只有策略枚举与 Harness 接口 | **N/A：尚无在线 Runner 和原始报告** |
| 普通 Router + 渐进式披露 | 有 TF-IDF Router 离线结果 | **N/A：未执行在线 Planner 与设备终态验收** |
| HomeClaw 双层收缩 | 有第一层 Router 报告、第二层合成 Contractor 报告和单测 | **N/A：尚未形成端到端四策略报告** |

测试 [`test_strategy_benchmark.py`](./tests/test_strategy_benchmark.py)（L24）证明 Harness 会拒绝缺少任一策略的实验，并能正确聚合固定 Observation；它没有实现四个真实 Runner。仓库中也没有 strategy benchmark JSON 报告，因此不能把测试里的 `2 steps/120 tokens/100% success` 当成项目结果。

#### 6）要得到可写入简历的四策略结论，实验必须这样控制

1. **任务成功口径**：以最终设备状态满足 Gold Goal 为准，而不是“模型输出了 Tool”或“MQTT 发布成功”；False Done 单独统计。
2. **规划步数口径**：一次 Planner 模型生成为一步，Re-Plan 另记次数；Router、Verifier 等确定性函数不混入“LLM 规划步数”。
3. **完全同场**：四组共享数据哈希、模型精确版本、Prompt 版本、Tool Registry、温度、Seed、Token/Step/Re-Plan 预算和网络区域。先以并发 1 做质量对照，再单独做容量实验。
4. **分层数据**：至少区分单动作、多意图长程、视觉歧义、设备不存在、Capability 不支持和冲突动作，防止简单样本比例掩盖长程收益。
5. **重复与统计**：随机模型至少跑多个 Seed；成功率报告样本数和置信区间，Token、步骤和延迟使用配对样本的均值/P50/P95及 Bootstrap 95% CI。当前 Harness 尚未自动计算 CI，需要在正式报告层补充。
6. **成本口径**：只使用服务端返回的 Prompt/Completion Token 和当次模型价格；延迟从请求进入 Host 计到设备 State Evidence 确认，不能只量模型响应时间。

仓库已经把这些可比性要求写入 [`benchmark-protocol.md`](./docs/benchmark-protocol.md)（L3、L21），但当前 Router 报告没有记录 CPU 型号，Strategy Harness 也没有把硬件、并发和置信区间纳入结构化配置，这是正式在线实验前还要补齐的证据链。

#### 7）目前最稳妥的项目表述

当前分支能够被代码和原始报告支撑的结论是：

> 在 25 条中英文 Router Gold 集上，HomeClaw Top-2 实现 100% Skill 完整覆盖；相较全量 11 Tool Schema，平均暴露 4.40 个 Tool，Schema 由 2406 降至 928.72 Bytes，减少 61.4%；相较 TF-IDF Top-2，完整覆盖率提升 12 个百分点。

“规划步数降低多少、真实 Token 降低多少、单任务成本和长程成功率提升多少”目前都应回答 **尚待四策略在线报告**。简历中的“长程复杂指令成功率相对基线提升 25%”只能作为既有实验口径，必须能同时拿出原任务集、基线、模型版本和逐样本结果；它不能由当前 25 条 Router 评测或 123 个单测反推，也不能全部归因给 Skill-MoE。

### 三、Skill 和 Tool

8、你是如何从智能家居的业务能力、事务边界和安全策略出发抽象 Skill 与 Tool 的？一个新 Skill 或 Tool 的 Schema、前置条件、预期效果、幂等等级和验证谓词如何定义？当前设计借鉴了 SAGE 的哪些经验，又有哪些属于 HomeClaw 自己的工程重构？

**参考回答：** 我把 Tool 定义为**最小的、可独立授权、可独立判定重试策略并能由物理状态证据验收的领域动作**；Skill 则是围绕一类用户意图组织召回特征、知识入口和允许 Tool 的能力包。Skill 本身不拥有物理副作用，真正的事务与幂等边界落在 Tool/Action 上。

#### 1）Tool 的边界由“可验证副作用”决定

| 设计问题 | HomeClaw 的判断规则 | 示例 |
|---|---|---|
| 名称是否稳定 | 使用厂商无关的领域动词，不暴露 Broker/Topic/REST 路径 | `set_light_brightness`，而不是 `mqtt/home/light/set` |
| 动作是否足够原子 | 一次调用只修改一个明确目标，能单独形成成功或失败证据 | 设置一盏灯的亮度是 Tool；“全屋晚安”通常是多 Tool Workflow |
| 效果是否可观测 | 必须能构造 Expected State，并从 ACK 或新状态中验证 | `set_temperature(26)` → `{"temperature":26}` |
| 重试是否安全 | 优先使用绝对目标动作；相对/翻转动作必须显式标为非幂等 | `set_light(on)` 优于 `toggle_light()` |
| 安全策略是否明确 | 风险、角色、家庭租户范围和是否二次确认由确定性策略检查 | 开灯低风险；开门锁高风险且需要授权/确认 |
| 是否跨事务边界 | 多设备任务拆成多个 Action，由 Host DAG 管依赖与局部重规划 | 不把多个物理设备包装成一个无法判断部分成功的“大 Tool” |

物理设备通常不支持数据库式跨设备回滚，所以“晚安场景”即使在业务上是一个 Skill，也不应假装成天然原子事务。除非底层平台本身提供带事务语义的 Scene API，否则 Host 必须保存每个原子动作的独立证据；当前代码还没有通用补偿事务引擎，因此不能承诺多设备全有或全无。

#### 2）一个领域 Tool 在当前代码里有四个契约投影

| 投影 | 保存内容 | 谁消费 | 对应代码 |
|---|---|---|---|
| 路由/LLM 投影 | 名称、描述、Input JSON Schema、粗粒度风险 | Skill Router 与在线 Proposer，只把命中 Tool 暴露给模型 | [`ToolDefinition`](./homeclaw/routing/models.py)（L12）、[`registry.json`](./homeclaw/skills/registry.json)（L2） |
| 设备 Capability 投影 | Capability、`ParameterSpec`、幂等等级、风险等级 | Tool Contractor 与确定性 Verifier；这是“该设备能否执行”的真相 | [`ParameterSpec`](./homeclaw/verification/registry.py)（L14）、[`ToolSpec`](./homeclaw/verification/registry.py)（L44） |
| MCP 协议投影 | 领域名称、版本、Input Schema、Handler | MCP Client/Server 的发现与调用 | [`MCPTool`](./homeclaw/mcp_runtime/server.py)（L13） |
| MQTT 执行投影 | Expected-State Builder、超时、内部 command/state Topic | MCP–MQTT Bridge；Topic 永不进入模型上下文 | [`MqttToolBinding`](./homeclaw/mcp_runtime/home_server.py)（L14）、[`CommandMapping`](./homeclaw/mqtt/bridge.py)（L25） |

这四层不是四个不同 Tool，而是同一个领域契约面对不同消费者的投影。它们通过稳定 `tool_name` 关联：模型只看到业务 Schema，Verifier 查询设备 Capability，MCP Server 负责协议暴露，Bridge 最后才把领域动作翻译成 MQTT Topic。

需要如实说明的是：当前仓库还没有一个 Canonical Tool Manifest 自动生成这四种投影，也没有启动时比较 Schema Hash。因此 Routing JSON、`ToolSpec` 和 `MCPTool` 仍可能被人工改出漂移。现阶段真正的安全判断以设备 Capability Registry 和 Host Authorization 为准；把多层定义统一生成/校验，是生产加固项而不是已经完成的能力。

#### 3）新 Tool 的完整接入流程

以新增 `set_fan_speed` 为例，我会按下面顺序接入，而不是先写 Prompt：

1. **定义领域语义**：确定它是绝对目标动作，参数是有界枚举或数值，禁止把厂商 Topic 放进名称。
2. **注册 LLM Schema**：在 [`registry.json`](./homeclaw/skills/registry.json)（L2）增加唯一 ToolDefinition，再由一个或多个 Skill 只保存名称引用。[`SkillRegistry.register_skill`](./homeclaw/routing/registry.py)（L30）会拒绝未知 Tool 引用。
3. **声明设备能力**：为实际支持该动作的设备写入 `ToolSpec`，包括 Capability、必填参数、类型、范围/枚举、`IdempotencyClass` 和 `RiskLevel`；不支持的设备不注册该 Tool。
4. **定义效果契约**：在 `MqttToolBinding.expected_state_builder` 中把参数转换为权威 Expected State，例如 `{"fan_speed":"high"}`。Bridge 只在新状态满足该效果时确认成功。
5. **绑定协议**：MCP Server 注册领域 Tool，Bridge 内部再配置 command/state/availability Topic。[`DomainMCPServer.register_tool`](./homeclaw/mcp_runtime/server.py)（L48）会拒绝带 `/` 或以 `mqtt` 开头的原始 Topic 名称。
6. **配置安全策略**：在 [`AuthorizationPolicy`](./homeclaw/security/authorization.py)（L28）为 Tool 配置角色、家庭租户范围和高风险确认；启用该策略后，没有匹配规则的 Tool 会 fail-closed。
7. **增加回归**：至少覆盖合法参数、缺失/未知/越界参数、不支持设备、离线/陈旧状态、权限拒绝、重复 `command_id`、发布成功但无状态证据和业务拒绝。

这种流程把“模型会不会调用”与“系统允不允许执行”分开：前者由 Skill/Router/Schema 提供候选，后者由 Registry、Verifier、Authorization 和物理状态证据共同决定。

#### 4）前置条件、Expected State、幂等和风险如何落地

[`ActionProposal`](./homeclaw/domain/models.py)（L177）是 Proposer 与 Verifier 的有界契约，包含目标设备、参数、来源 Skill、`preconditions`、`expected_state`、`verification`、幂等等级和风险等级：

- **参数 Schema**：[`ActionVerifier._validate_tool`](./homeclaw/verification/verifier.py)（L113）拒绝未知参数、缺少必填参数、类型错误、越界值和非法枚举。
- **Expected State**：Proposal 创建时强制非空；执行侧由 `expected_state_builder` 重新从可信 Binding 构造，并由 MQTT State Evidence 验收，模型不能用“我认为成功”替代状态。
- **幂等等级**：[`IdempotencyClass`](./homeclaw/domain/models.py)（L73）区分原生幂等、带 Key 幂等和非幂等；Proposal 与设备 `ToolSpec` 不一致时拒绝。非幂等动作在领域契约层还必须提供显式 verification。
- **风险等级**：Verifier 取 Proposal 与设备 ToolSpec 的较高风险，模型不能通过输出 `low` 降低高风险 Tool；Host 再执行 RBAC、租户隔离、策略版本和显式确认。
- **状态新鲜度**：设备离线或状态超龄会产生机器可读、可重试 Issue，而不是让 Planner 基于旧状态继续执行。

当前边界同样要讲清：`preconditions` 和 `verification` 已进入结构化 Proposal，但通用谓词解释器尚未实现；Verifier 目前没有逐条执行这两个字段，只校验参数、设备、状态新鲜度、幂等和风险。另一个限制是当前 `MqttToolBinding` 没有独立的幂等/风险字段，内部重建 Proposal 时使用默认的 `IDEMPOTENT_WITH_KEY + LOW`；因此非幂等 Tool 接入前必须扩展 Binding 或传递已验证契约，不能直接照搬默认路径。

#### 5）SAGE 经验与 HomeClaw 工程工作的边界

| 来源 | 可以如实归因的内容 |
|---|---|
| SAGE 经验 | 智能家居领域知识，以及 Personalization、Intent Resolution、Device Resolution、Persistence、Command Chaining 等问题拆分；早期 Skill 明确标注“迁移自 SAGE”，见 [`SKILL.md`](./homeclaw/skills/smart-home/SKILL.md)（L102） |
| HomeBench 经验 | 合法/非法设备与方法、单动作/多动作混合、不可执行请求拒绝等评测和输出约束 |
| HomeClaw 工程重构 | 类型化 `ActionProposal`、Skill/Tool Registry、Top-K 与 Capability 二次收缩、Proposer–Verifier 隔离、MCP–MQTT 防腐层、状态证据验收、Checkpoint/Outbox/幂等恢复及统一可观测链路 |

我不会把 SAGE 已有的设备分类换个名字就说成原创，也不会声称 MCP、Outbox、RBAC 这些通用工程模式由项目发明。可以主张的是：我把已有领域 Know-how 重新抽象成可路由、可验证、可恢复的执行契约，并完成了这些模式在智能家居 Agent 闭环里的组合与边界设计。

#### 6）当前回归证据

| 契约层 | 场景数 | 覆盖内容 |
|---|---:|---|
| Domain Contract | 6/6 | Proposal 序列化、非幂等 verification、Grounding 约束、成功证据和关联 ID；见 [`test_domain_contracts.py`](./tests/test_domain_contracts.py)（L30） |
| Verifier | 4/4 | 合法动作、参数/设备、离线/陈旧状态、风险与幂等；见 [`test_verifier.py`](./tests/test_verifier.py)（L45） |
| MCP Tool 边界 | 5/5 | Skill Tool 白名单、版本、Resource/Prompt、禁止原始 Topic、版本化 RBAC/租户；见 [`test_mcp_runtime.py`](./tests/test_mcp_runtime.py)（L54） |

这 15 个确定性场景证明了契约与安全边界的代码行为，不代表所有厂商设备 Schema 都已完成认证，也不能替代真实 MQTT 网关的互操作测试。

9、Skill 的边界依据能力域、上下文依赖还是执行事务划分？当多个 Skill 需要同一个 Tool 时，如何通过唯一注册、引用复用、版本和权限一致性避免重复定义及 Schema 冲突？

**参考回答：** Skill 边界不按房间、设备数量或厂商划分，而是按“用户意图是否内聚、是否共享知识上下文、是否服从同类安全策略、失败后能否独立回退”划分。事务边界是重要约束，但它落在原子 Tool 上；一个 Skill 可以编排多个 Tool，多个 Skill 也可以安全复用同一个 Tool。

#### 1）Skill 边界的五个判断维度

| 维度 | 适合放在同一 Skill | 应拆成不同 Skill |
|---|---|---|
| 意图与词汇 | 用户表达、Capability 和 Tool 经常共同出现 | 召回词汇与目标效果基本无关 |
| 知识上下文 | 共享同一类拓扑、状态字段和领域规则 | 需要完全不同的知识资源或模型 |
| 安全策略 | 风险等级、授权和确认流程接近 | 一个是普通控制，另一个需要高风险确认 |
| 故障与回退 | 失败后可以使用同一澄清/重规划策略 | 一个故障不应阻塞另一个能力域 |
| 资源与部署 | 延迟、依赖和算力特征相近 | 需要独立 GPU、隔离故障域或不同容量控制 |

例如 lighting 内部的开、关、亮度共享设备状态和语义，可以作为一个 Skill；security 虽然也控制设备，但门锁具有不同风险与授权规则，应独立；`device-disambiguation` 是横切能力，却因为需要拓扑候选、可能调用 GPU Grounder、失败时必须保持歧义而独立成 Skill，识别结果再交还 lighting/media 等领域执行。

#### 2）Skill 不是设备、Prompt 或物理事务

- **不按单台设备拆分**：一百盏灯仍属于 lighting，具体设备差异由 Capability Registry 处理，否则 Skill 数会随设备数爆炸。
- **不按厂商拆分**：厂商差异留在 MCP–MQTT Binding；Skill 使用稳定领域 Tool，避免模型学习 Topic。
- **不把一个 Prompt 当 Skill**：Skill 至少要有明确的意图范围、Tool 引用、知识入口、版本和回退语义。
- **不创建全能巨型 Skill**：把灯光、空调、门锁和媒体全部放在一个 Skill 会让 Router 失去意义，并把不同风险策略混在一起。
- **不假装跨设备原子**：用户的一条长指令可以同时激活多个 Skill，Host 用 DAG 保存每个 Action 的状态；Skill 边界不能替代物理设备缺少分布式事务这一事实。

当前 [`SkillDefinition`](./homeclaw/routing/models.py)（L24）保存领域、关键词、Tool 引用、Resource URI、激活短语、能力分、可用性和版本，足够支持路由边界；但它没有声明 Skill-to-Skill 依赖，因此当前不存在循环依赖，也没有所谓“循环依赖检查”。如果未来加入前置 Skill 或组合 Skill，必须新增 DAG 校验，不能沿用现在的注册逻辑后声称已防环。

#### 3）多个 Skill 共享 Tool 时只共享引用，不复制定义

当前 Registry 中 `get_device_state` 只定义 **1 次**，却被 lighting、climate、media、security、appliance 和 device-disambiguation 共 **6 个 Skill** 引用；`request_clarification` 也只定义 **1 次**，由 clarification 与 device-disambiguation 两个 Skill 引用，并作为全局最小安全 Tool 保留。

代码路径如下：

1. [`SkillRegistry.register_tool`](./homeclaw/routing/registry.py)（L25）以 Tool 名为键，重复定义立即失败。
2. [`register_skill`](./homeclaw/routing/registry.py)（L30）只接受已经存在的 Tool 名称，Skill 不能内嵌一份私有 Schema。
3. [`SkillRouter._route`](./homeclaw/routing/router.py)（L70）把多个命中 Skill 的 `tool_names` 放入 Set 求并集并排序，因此同名 Tool 最终只出现一次。
4. [`LLMProposer.propose`](./homeclaw/agent/proposer.py)（L76）按去重后的名称回查唯一 Schema，模型不会收到六份 `get_device_state`。
5. [`MCPHostGateway.call`](./homeclaw/mcp_runtime/host.py)（L28）再次检查本次 Route 的 Tool 白名单；共享 Tool 被哪个 Skill 召回，都不能绕过同一授权策略。
6. 最后由设备 `ToolSpec` 判断目标实例是否真的支持该 Tool，避免“Skill 允许”被误解成“所有设备都支持”。

这样共享的是领域能力身份，不是权限副本。权限、风险和幂等语义不应该跟着每个 Skill 复制，否则同一个 `get_device_state` 可能在 lighting 中可调用、在 security 中却意外绕过租户规则。

#### 4）版本与权限目前分别由哪些层负责

| 层级 | 当前版本/一致性机制 | 能保证什么 | 当前缺口 |
|---|---|---|---|
| Skill Registry | `SkillDefinition.version`，同一 `skill_id` 只允许一个活动定义 | 防止进程内重复 Skill；可标识当前 Skill 元数据版本 | 不支持多版本并存、兼容性协商或热升级 |
| Routing Tool | `ToolDefinition` 以唯一名称注册 | 同一 Registry 内不会出现两个冲突 Schema | 当前没有 Tool version/schema hash |
| Capability Registry | 设备 ToolSpec 与 PostgreSQL 行版本；家庭聚合 CAS | 确保设备能力快照并发更新不丢失 | 没有自动核对 Routing JSON/MCP Schema |
| MCP Tool | 必须携带非空 `version`，Server 拒绝同名重复注册 | MCP 发现结果可标识接口版本 | 未与 Skill Registry 的内容哈希绑定 |
| Authorization | 独立 [`AuthorizationPolicy.version`](./homeclaw/security/authorization.py)（L28） | 角色、确认、家庭租户和陈旧策略版本 fail-closed | 策略部署与 Tool Schema 部署仍需发布流程协调 |

权限刻意不放在 Skill 中：Host 按 Tool 名查统一策略，并校验认证主体、角色、家庭范围和确认状态。Verifier 又取 Proposal Risk 与设备 ToolSpec Risk 的较高者，见 [`effective_risk`](./homeclaw/verification/verifier.py)（L158），所以模型或某个 Skill 不能把高风险门锁降级为低风险动作。

#### 5）同名 Schema 冲突的现有保障与生产加固

在**同一个 Routing Registry 内**，Skill 只能引用唯一 ToolDefinition，因此不存在“lighting 复制一份 Schema、security 再复制另一份”的冲突；MCP Server 同样拒绝同名重复 Tool。当前测试已覆盖重复 Tool 与未知引用拒绝。

但 Routing Definition、设备 `ToolSpec`、MCP Tool 和 MQTT Binding 仍由不同代码/配置创建，跨层冲突尚未自动检测。真正工程化的解决方案应增加一份 Canonical Tool Manifest，至少包含：

```text
tool_id / semantic_version / input_schema_hash / capability
effect_schema / idempotency / risk / authorization_policy_key
```

然后从 Manifest 生成或在启动时核对四种投影。兼容升级可以遵循：

- 增加可选字段、放宽描述等向后兼容修改升 Minor；
- 新增必填参数、修改单位、改变副作用或幂等语义必须升 Major；
- 滚动升级期间以不同的版本化 Tool ID（或新增协议协商）同时暴露两个 Major，Skill 明确引用目标 Major；
- Capability Registry 完成设备迁移并通过 Outbox 通知缓存失效后，才能删除旧版本；
- 权限收紧独立提升 Policy Version，旧策略版本请求立即 fail-closed。

这套 Manifest/双版本发布流程目前尚未落到代码，因此面试时应说“当前已解决单 Registry 重复定义，跨层 Schema 一致性是已识别的生产加固项”，而不是声称版本和权限已经自动全链路同步。

#### 6）当前量化不变量与回归证据

| 项目 | 当前值/结果 | 说明 |
|---|---:|---|
| Tool 名称唯一性 | 11/11 唯一 | Registry 中 11 个条目对应 11 个不同名称 |
| Skill ID 唯一性 | 7/7 唯一 | 当前 7 个 Skill 无重复 ID |
| `get_device_state` 复用 | 1 个定义 / 6 个 Skill 引用 | 共享 Tool 不复制 Schema |
| `request_clarification` 复用 | 1 个定义 / 2 个 Skill 引用 | 同时由 Router 作为最小安全 Tool 保留 |
| 共享/坏 Registry 回归 | 2/2 通过 | 唯一共享引用、重复 Tool 与未知引用拒绝；见 [`test_skill_router.py`](./tests/test_skill_router.py)（L52、L58） |
| MCP 白名单与授权主路径 | 2/2 通过 | Tool 子集暴露、版本化 RBAC/租户/确认；见 [`test_mcp_runtime.py`](./tests/test_mcp_runtime.py)（L54、L96） |

这部分真正要守住的是：Skill 可以共享 Tool，但不能拥有 Tool 的私有真相。Tool 的 Schema、风险、权限和效果契约必须最终收敛到统一身份；否则上下文虽然去重了，运行时语义仍可能漂移。

10、Router 如何保证 Skill 召回率并在低置信度时安全回退？Recall@1、Recall@K、MRR、多标签完整覆盖率和 Fallback Rate 分别如何计算？HomeClaw 与普通 TF-IDF 或向量 Router 在同一测试集上的各项实测值具体是多少，Recall@K 和完整覆盖率分别提升了多少个百分点？测试集有多少条单意图、多意图、模糊及中英文样本，Top-K、模型版本和置信度阈值如何固定？

**参考回答：** Router 不能从理论上“保证”召回率，只能通过候选召回、确定性重排、动态 Top-K、安全回退和固定 Gold 集回归把漏召回风险变成可观测、可阻断的工程指标。智能家居场景宁可在低证据时澄清，也不能为了降低 Fallback Rate 强行选择一个设备能力域。

#### 1）召回链路如何同时控制漏召回和误路由

[`SkillRouter`](./homeclaw/routing/router.py)（L27）的召回链路是：

1. **双语分词**：英文统一小写并保留下划线 Token；中文字符额外生成 bigram，避免只靠单字匹配。
2. **倒排候选**：索引 `skill_id/domain/description/keywords`，查询只访问命中 Token 对应的 Skill，不扫描全量 Tool Schema。
3. **硬门禁**：不可用 Skill 被删除；带 `activation_phrases` 的视觉消歧 Skill 必须命中明确短语，避免普通灯光请求误触发 GPU Grounder。
4. **确定性重排**：按 `0.70×词法相关度 + 0.20×关键词覆盖 + 0.10×competence` 排序，最低分 0.12；同分再按 Skill ID 排序，结果可复现，见 [`_score`](./homeclaw/routing/router.py)（L132）。
5. **动态 K**：普通请求 Top-1，多意图/视觉标记 Top-2，最大 Top-3；Token 余量不足 1000 时收缩到 Top-1，见 [`AdaptiveTopKPolicy`](./homeclaw/resilience/controls.py)（L195）。
6. **Fail-closed Fallback**：没有候选过阈值时只选择 `clarification`，暴露最小澄清 Tool，而不是返回“分最高但仍不可信”的动作 Skill。

激活短语与最低分存在 Recall—Precision 权衡：词表过窄会漏掉新表达，阈值过低又会引入无关 Skill。因此阈值 0.12 只是当前工程默认值，不是经过大规模概率校准得到的置信度；任何调整都必须在同一 Gold 集和安全集上重跑。

#### 2）五个指标的计算口径

对样本 `i`，Gold Skill 集为 `Gᵢ`，Router 前 K 个结果为 `Rᵢ@K`：

| 指标 | 当前计算方式 | 解决的问题 | 不能说明什么 |
|---|---|---|---|
| Recall@K | 对每条样本计算 `|Gᵢ∩Rᵢ@K| / |Gᵢ|`，再取平均 | Gold Skill 找回了多少 | 不惩罚额外召回的无关 Skill |
| MRR | 第一个 Gold Skill 排名的倒数，再取平均；未命中为 0 | 正确 Skill 是否排在前面 | 多标签任务只看第一个正确项 |
| 完整覆盖率 | `Gᵢ ⊆ Rᵢ@K` 的样本比例 | 多意图所需 Skill 是否全部被找回 | 仍不惩罚额外 Skill |
| Fallback Rate | `decision.fallback=True` 的样本比例 | Router 多常进入澄清 | 不区分正确澄清和错误澄清 |
| Tool Contraction | `1 - 暴露 Tool / 全量 Tool` | 召回后上下文缩小程度 | 不能代替路由正确性 |

实现见 [`evaluate_router`](./homeclaw/eval/routing_metrics.py)（L29）。例如当前 18 条单标签与 7 条双标签样本中，HomeClaw Top-1 每条都把至少一个正确 Skill 放在首位，所以 MRR=1.00；但双标签只能找回一半，平均 Recall 为 `(18×1 + 7×0.5)/25 = 0.86`，完整覆盖率则是 `18/25 = 72%`。这说明 MRR=1.00 绝不等于多意图路由已经 100% 完成。

#### 3）Gold 集、对照组与固定条件

| 维度 | 当前设置 |
|---|---|
| 样本量 | 25 条：18 条单标签、7 条双标签 |
| 语言 | 16 条英文、9 条中文 |
| 特殊场景 | 3 条视觉消歧、1 条明确模糊澄清；类别与单双标签有重叠 |
| Registry | 同一份 7 Skill / 11 Tool [`registry.json`](./homeclaw/skills/registry.json)（L60） |
| HomeClaw | 倒排召回 + 组合打分，最低分 0.12 |
| Baseline | 同 Registry 的普通 [`TfidfVectorRouter`](./homeclaw/eval/baseline_router.py)（L27），余弦相似度、无 HomeClaw 激活短语门禁 |
| Top-K | 分别固定为 1 和 2；不是把两个 K 的最佳结果混在一起 |
| 模型/Seed | 不调用 LLM，无模型版本与随机 Seed；Python 3.10.22、Windows 10 单进程顺序运行 |

数据见 [`router_gold.jsonl`](./data/eval/router_gold.jsonl)（L1），评测入口见 [`evaluate_router.py`](./scripts/evaluate_router.py)（L60），报告包含逐样本决策而非只有汇总值。

#### 4）同场实测结果

| Router | K | Recall@K | MRR | 完整覆盖率 | Fallback Rate | 平均 Tool 收缩 |
|---|---:|---:|---:|---:|---:|---:|
| TF-IDF | 1 | 72% | 0.84 | 60% | 0% | 74.9% |
| HomeClaw | 1 | 86% | 1.00 | 72% | 4% | 68.4% |
| TF-IDF | 2 | 92% | 0.90 | 88% | 0% | 59.6% |
| HomeClaw | 2 | 100% | 1.00 | 100% | 4% | 60.0% |

原始结果见 [`HomeClaw Top-1/Top-2`](./reports/router-eval-2026-11-09.json)（L10、L286）和 [`TF-IDF Top-1/Top-2`](./reports/router-eval-2026-11-09.json)（L572、L848）。相对 TF-IDF：

- Top-1 Recall 提升 **14 个百分点**，完整覆盖提升 **12 个百分点**，MRR 提升 **0.16**；
- Top-2 Recall 提升 **8 个百分点**，完整覆盖提升 **12 个百分点**，MRR 提升 **0.10**；
- HomeClaw 的 4% Fallback 对应唯一模糊样本的正确澄清；TF-IDF 的 0% 是因为它把该样本错误路由到视觉消歧，不能解释为更安全。

Top-1 的 HomeClaw Tool 收缩率低于 TF-IDF，是因为它多保留了正确领域能力；这体现了“更小上下文”与“足够召回”之间的真实权衡，不能只挑收缩率更高的一组。

#### 5）错误分析与当前不能过度承诺的地方

- 25 条数据规模很小，且只跑一次，没有方差或置信区间；它适合回归，不足以代表真实用户分布。
- Top-2 的 100% 是**完整覆盖率**，不是 Precision@2。报告中部分单意图样本会额外召回第二个 Skill，当前评测尚未统计 Precision@K、Over-routing Rate 或额外 Schema 成本。
- Baseline 与 HomeClaw 都依赖人工 Registry 文本；遇到完全无词面重叠的同义表达时，倒排召回可能在重排前就漏掉候选。
- 当前 [`ProductionRuntime._replan`](./homeclaw/agent/runtime.py)（L412）直接回到 PLAN，并不会依据 Verifier 的“缺 Tool”反馈重新执行 ROUTE；因此第一次漏召回不能靠现有 Re-Plan 自动修复。
- Fallback Rate 只统计“是否回退”，后续应拆成 Correct Fallback、False Fallback 和 Unsafe Non-Fallback。

生产上应把低分/空候选、越界 Tool、Verifier 的 `capability_not_found` 和用户改口轨迹沉淀为离线标注集；先扩充关键词与激活短语，再比较关键词、向量、混合召回和重排。任何候选改动只能通过离线回放与安全门禁，不能在线自动写回生产 Registry。

11、当 Skill、Tool 和设备数量增长到千级甚至万级时，Router 如何维持检索准确率与延迟？在 100、1000、5000 乃至更大规模下，Recall@K、P50/P95、吞吐量、索引构建时间和峰值内存的实测值分别是多少，规模增长后准确率下降了多少？何时应从线性检索升级到领域分层路由、ANN 索引或分片，触发升级的量化阈值是什么？

**参考回答：** 当前 Router 的扩展性来自倒排索引，而不是把每个 Skill 的完整描述和 Tool Schema 逐一交给模型。但“能放下 5000 个合成 Skill”不等于“5000 个真实 Skill 仍有相同语义准确率”，所以我会分别评估索引成本、查询成本、召回质量和设备 Capability 收缩，不能只报一个 P95。

#### 1）当前索引结构与复杂度

[`SkillRouter._build_index`](./homeclaw/routing/router.py)（L47）维护三份核心数据：

- `token -> set(skill_id)` 的倒排索引，用于从查询词直接拿候选；
- `skill_id -> Counter(token)`，用于候选重排；
- Token Document Frequency，用于给稀有词更高权重。

| 阶段 | 当前主要复杂度 | 随规模增长的风险 |
|---|---|---|
| 索引构建 | 与所有 Skill 文本 Token 总量近似线性 | 全量重建时间和常驻内存 |
| 候选召回 | 与 Query Token 的 posting list 总长度相关 | 高频通用词会让候选集接近全量 |
| 候选打分 | `O(C × query/document overlap)` | 候选 C 过大时 CPU 增长 |
| 排序 | 当前对全部 Match 排序，约 `O(C log C)` | K 很小时仍为全排序，可改 Top-K Heap |
| Tool Schema 注入 | 与最终 Top-K Skill 的 Tool 并集相关 | 不随全量 Tool 数直接线性注入 LLM |

路由代码当前使用 [`matches.sort`](./homeclaw/routing/router.py)（L98），并非专门的 Top-K 选择算法。Skill 数继续增长时，第一步优化通常是提高索引选择性、缓存规范化查询和使用 `heapq.nlargest`，而不是立即上 ANN。

#### 2）规模实验是怎样构造的

[`scale_benchmark`](./scripts/evaluate_router.py)（L100）分别生成 100、1000、5000 个合成 Skill：

- 每个 Skill 有唯一 `unique_keyword_n`，分布到 20 个合成 Domain；
- 每个 Skill 对应一个独立合成 Tool，并保留原 Registry 的 11 个 Tool；
- 索引构建用 `tracemalloc` 记录 Python 峰值内存；
- 每个规模最多顺序执行 100 条唯一关键词查询；
- 报告中的“QPS”是 `1000 / 平均单次毫秒耗时`，即单线程理论吞吐，不是多客户端并发压测结果。

因此该实验适合回答“数据结构随条目数如何增长”，不适合回答“线上并发能扛多少”或“真实自然语言 Recall 是否不变”。报告没有记录 CPU 型号、并发数、预热轮次和多次重复区间，数值只能在当前同机环境内比较。

#### 3）Skill/Tool 扩展实测

| Skill / Tool 数 | 索引构建 | Route P50 | Route P95 | 理论单线程 QPS | 索引峰值 |
|---:|---:|---:|---:|---:|---:|
| 100 / 111 | 2.13 ms | 0.033 ms | 0.037 ms | 29,413 | 0.32 MB |
| 1000 / 1011 | 17.31 ms | 0.087 ms | 0.093 ms | 11,317 | 3.14 MB |
| 5000 / 5011 | 98.10 ms | 0.331 ms | 0.372 ms | 2,976 | 16.32 MB |

原始数据见 [`scale`](./reports/router-eval-2026-11-09.json)（L1145）。从 100 到 5000 Skill，索引峰值约增长 50.8 倍，符合近似线性预期；Route P95 增长约 10 倍，说明查询时间更多受 Python 对象、候选集合和固定开销共同影响，而不是简单等于 Skill 数增长倍数。

当前 5000 Skill P95 仍低于 0.4 ms，但不能由此宣称生产 Router 一定有 2976 QPS：真实服务还包含请求解析、Telemetry、跨进程调用、并发锁、容器限额和更复杂的 posting list。

#### 4）设备数量增长与 Tool 收缩是另一条复杂度曲线

[`ToolSpaceContractor.contract`](./homeclaw/routing/contraction.py)（L34）逐个候选设备查询 Capability，再对 Tool 求并集和交集。内存 Registry 下的合成结果为：

| 候选设备数 | 收缩后 Tool | P50 | P95 | 理论单线程 QPS |
|---:|---:|---:|---:|---:|
| 100 | 3 | 0.028 ms | 0.037 ms | 34,136 |
| 1000 | 3 | 0.255 ms | 0.294 ms | 3,690 |
| 5000 | 3 | 1.301 ms | 1.378 ms | 758 |

原始数据见 [`device_scale`](./reports/router-eval-2026-11-09.json)（L1174）。该脚本每个规模运行 20 次，Capability 查询是进程内字典读取；生产 [`PostgresCapabilityRegistry.get_device`](./homeclaw/verification/postgres_registry.py)（L230）若被逐候选调用，会形成明显的 N+1 查询。因此真实工程应先用拓扑把候选收缩到少量设备，并为批量候选增加 `get_devices(home_id, ids)` 或预加载快照，而不是把 5000 次数据库往返包装成“Tool 收缩”。

#### 5）当前没有“规模增长后的 Recall 下降值”

合成 Skill 使用互不冲突的唯一关键词，脚本没有构造同义词、近义领域、长描述噪声或多标签 Gold，也没有在 100/1000/5000 三档记录 Recall@K。当前 25 条真实 Router Gold 只对应基础 7 Skill Registry。

所以可以回答：

- **已有**：索引构建、内存、Route P50/P95、理论单线程吞吐和内存 Capability 收缩时延；
- **没有**：100/1000/5000 真实语义分布上的 Recall、Precision、完整覆盖率及其下降百分点。

如果面试官追问“5000 Skill 准确率掉了多少”，正确回答是“现有规模实验没有这个口径”，而不是把唯一关键词命中冒充 Recall 不下降。正式实验需要为各规模生成带语义重叠、同义改写和多意图组合的 Gold，并保持每档难度分布一致。

#### 6）什么时候升级分层路由、ANN 或分片

我不会把 Skill 数量本身作为唯一开关，而会设置准确率—时延—内存联合门禁。下面是建议的生产触发线，属于待落地 SLO，不是当前报告的既有结论：

| 观测项 | 建议触发条件 | 优先动作 |
|---|---|---|
| 真实 Gold 完整覆盖 | Recall@2/完整覆盖低于业务目标，或较已批准基线下降超过 2 个百分点 | 增加同义样本，比较关键词、Embedding、混合召回与重排 |
| Router 延迟 | P95 连续超出 5 ms，或超过端到端预算的 5% | 优化 posting list、Top-K Heap、缓存；再考虑分层 |
| 候选选择性 | 候选数 P95 超过全量 Skill 的 10%，或通用词频繁召回上千项 | 先做 Domain 粗路由/分片，再在分片内重排 |
| 索引内存 | 超过 Router Pod 内存预算的 25% | 压缩表示、只读共享索引或按 Domain 分片 |
| 构建/发布 | 全量重建超过发布就绪时间，或更新频率高于可接受重建频率 | 增量索引、双版本构建与原子切换 |

具体演进顺序是：

1. **词法优化**：停用词、字段权重、Top-K Heap、热查询缓存；
2. **领域分层**：先按 lighting/climate/security 等粗领域路由，再访问局部索引；
3. **混合召回**：倒排保证精确关键词，ANN 补完全无词面重叠的同义表达，最后用确定性规则/轻量模型重排；
4. **分片与副本**：索引超过单实例内存或 QPS 预算后，按 Domain/租户分片并保留只读副本。

当前 Router 在构造时一次性建索引，没有热更新或原子换版机制；Registry 若在 Router 创建后继续注册 Skill，索引不会自动刷新。生产升级应构建新的 `Registry + Router` 版本，跑完 Recall/安全回归后再原子切流，不能原地修改活动索引。

12、Skill-MoE 的“自进化”为什么不能让 Agent 在线直接修改生产 Skill？请说明如何借鉴 RSIAgent 和 evolver.py 的思路，构建“失败轨迹收集—候选生成—固定集回放—消融—安全门禁—Evidence Pack—人工审批—Canary—回滚”的受控离线闭环。

**参考回答：** 我更愿意把它称为**受治理的离线演进**，而不是让 Agent 递归改写自己的在线 RSI。生产 Agent 只产生失败证据，没有 Skill/Router 写权限；候选必须经过可复现回放、安全门禁、人工审批和可回滚发布。这样牺牲了“实时自改”的速度，但换来了智能家居执行所必需的可审计性和故障隔离。

#### 1）为什么不能根据一次失败在线改 Skill

| 在线自改风险 | 在智能家居中的后果 |
|---|---|
| 偶然噪声或网络故障被误归因为 Router | 把无关关键词永久加入 Skill，扩大错误召回 |
| Prompt Injection/恶意反馈进入“经验” | 攻击者可能污染 Tool 白名单或安全规则 |
| Proposer 与 Evaluator 同源 | 模型用自己的偏差证明自己的修改正确，形成自证闭环 |
| 测试集与模型版本变化 | 无法判断提升来自 Patch 还是评测条件改变 |
| 多个候选并发覆盖 | 基于旧版本生成的 Patch 覆盖新生产配置 |
| 没有版本化证据 | 出现误开门锁等事故时无法解释、复现和回滚 |

因此运行时与演进面分离：Runtime 对 Registry 只读；演进 Pipeline 只生成 Candidate 和 Evidence Pack，不直接写生产 Registry。

#### 2）当前离线闭环的代码路径

| 阶段 | 当前实现 | 失败语义 | 对应代码 |
|---|---|---|---|
| 失败表示 | `trace_id/task_id/component/error_code/input_text/metadata` 的结构化记录 | 非目标组件或信息不完整时不生成候选 | [`FailureTrace`](./homeclaw/evolution/pipeline.py)（L22） |
| 候选生成 | 只处理 Router `skill_miss`，从 `missing_terms` 生成可审查的 `add_keywords` Patch；同批重复候选去重 | 不满足 target/base/terms 时跳过 | [`KeywordMissCandidateGenerator`](./homeclaw/evolution/pipeline.py)（L54） |
| 版本绑定 | Candidate 保存 target、base version、candidate version、Patch 与 SHA-256 内容哈希 | Base Version 不等于活动版本时，回放前直接拒绝 | [`CandidateChange`](./homeclaw/evolution/models.py)（L30） |
| 固定集回放 | `ReplayEvaluator` 返回候选 Evaluation 与可选消融 Snapshot | Evaluator 异常当前会向上抛出，不会静默晋级 | [`ReplayEvaluator`](./homeclaw/evolution/pipeline.py)（L41） |
| 安全门禁 | 比较数据、模型、Prompt、Seed、预算、主指标、受保护指标与安全检查 | 任一缺失或不一致都 fail-closed | [`EvolutionGate`](./homeclaw/evolution/gates.py)（L26） |
| Evidence Pack | 保存候选哈希、Baseline、Candidate、门禁原因、消融与状态 | 先写临时文件，再原子替换正式 JSON | [`EvidencePack`](./homeclaw/evolution/models.py)（L64）、[`EvidenceStore`](./homeclaw/evolution/store.py)（L12） |
| Canary 准备 | 门禁通过后创建确定性流量分桶 Controller | 安全违规立即暂停；指标达标也只进入待审批 | [`CanaryController`](./homeclaw/evolution/canary.py)（L32） |
| 人工晋级/回滚 | 只有 `READY_FOR_APPROVAL` 才能记录非空审批人；支持状态回滚 | 未到待审批状态不能 Promote | [`approve/rollback`](./homeclaw/evolution/canary.py)（L77、L85） |

[`OfflineEvolutionPipeline.run`](./homeclaw/evolution/pipeline.py)（L107）把上述阶段串起来，但它的终点是 Evidence Pack 和 Canary Controller，不是生产 Registry 写入。

#### 3）如何保证 Baseline 与 Candidate 可比较

[`EvaluationSnapshot`](./homeclaw/evolution/models.py)（L51）记录数据集、数据哈希、模型、Prompt、Seed、Token 预算、指标、安全检查和样本数。Gate 强制以下 **6 个字段完全一致**：

1. `dataset_id`
2. `dataset_hash`
3. `model_id`
4. `prompt_version`
5. `seed`
6. `token_budget`

随后再检查：

- Candidate 样本数是否达到 `minimum_sample_count`；
- 主指标是否存在且提升达到 `minimum_improvement`；
- Token Cost、Recall、安全率等受保护指标是否超过允许退化；
- `no_raw_mqtt`、`no_false_done` 等必需安全检查是否明确为 `True`。

这避免“换了更容易的数据集”“用了更强模型”或“放大 Token 预算”后仍把收益归因给 Skill Patch。`GatePolicy` 没有内置统一业务阈值，阈值必须由部署环境显式配置；测试中的提升 1 个百分点、最少 50 样本只是 Test Fixture，不是生产默认标准。

#### 4）Evidence Pack、消融与 Canary 的具体语义

Candidate Hash 对 `target/base_version/candidate_version/patch` 做 SHA-256，Evidence Pack 同时保存 Baseline、Candidate Evaluation、Gate Reasons 和 Ablations。文件写入使用 `.tmp + os.replace`，可以避免进程中断留下半份 JSON。

但“原子文件”不等于“不可篡改账本”：当前本地 Evidence JSON 没有数字签名、对象锁、数据库唯一约束或审批审计链，文件仍可被人工修改。生产环境应把 Pack 存入只追加、带内容摘要和访问审计的 Artifact Store，并由 CI/审批身份签名。

Canary 默认策略为：

| 参数 | 默认值 | 含义 |
|---|---:|---|
| 流量比例 | 5% | `candidate_id + stable_key` 哈希稳定分桶，同一 Key 保持一致变体 |
| 最小样本 | 100 | 样本不足时不能进入待审批 |
| 最大失败率 | 5% | Canary 绝对失败率上限 |
| 相对 Baseline 最大增加 | 1 个百分点 | 实际允许值取绝对上限与 `baseline+1pp` 中更严格者 |
| 安全违规容忍 | 0 | 任意一次 Safety Violation 立即 `PAUSED` |

数值来自 [`CanaryPolicy`](./homeclaw/evolution/canary.py)（L19）。即使通过 100 个样本，也只进入 `READY_FOR_APPROVAL`，仍需人工 `approve()`；这避免“指标刚过线就自动改生产”。

#### 5）借鉴 RSI/evolver 的内容与没有实现的内容

借鉴的是抽象循环：

```text
失败证据 -> 生成候选 -> 固定条件评估 -> 选择保留
         -> 小流量观察 -> 晋级或淘汰
```

HomeClaw 在这个循环外增加了智能家居特有的安全约束：生产只读、版本绑定、False-Done/原始 Topic 等硬门禁、人工审批和可回滚状态。

当前没有实现、也不应包装成已经实现的部分包括：

- 没有多 Agent 蜂群、种群交叉、并行候选竞争或递归代码改写；
- Candidate Generator 目前只会根据结构化 Router Miss 增加关键词，不会自动改 Tool、Verifier 或执行代码；
- `ReplayEvaluator` 只有 Protocol，仓库没有连接在线模型与真实任务集的生产实现；
- Ablation 会被保存，但 Gate 当前不读取 Ablation 结果做晋级判定；
- 没有从 Runtime 自动采集 FailureTrace 的持久化链路；
- Canary 的 `selected/record` 尚未接入真实请求流量；
- `approve()` 只改变内存状态，没有认证审批服务，也不会提交 Registry；
- `rollback()` 只改变 Controller 状态，没有把生产流量指针切回旧 Artifact；
- `active_versions` 是 Pipeline 构造时传入的静态映射，正式晋级前还必须事务性重查当前活动版本。

因此它是一个“安全演进骨架 + 可执行状态机”，不是自主递归改进系统。

#### 6）还需要防止演进链路本身被投毒

Failure Trace 的 `input_text/missing_terms` 都来自运行数据，应视为不可信输入。当前 Generator 会把 `missing_terms` 直接标准化后放入 Keyword Patch，但没有 PII 脱敏、Prompt Injection 检测、词表上限或人工语义审查。

生产化时至少需要：

1. 采集前删除用户身份、地址、完整对话与图像，只保留最小失败特征；
2. 按同类失败聚类，达到最小频次后才生成候选，不能由单条 Trace 驱动；
3. 候选关键词限制长度、字符集和数量，并进入人工 Diff Review；
4. Replay 使用独立 Holdout，Evaluator 不读取 Candidate 的自然语言自证；
5. 安全集包含门锁、租户隔离、原始 MQTT Topic、False Done 和 Prompt Injection；
6. Promotion 通过版本化 Artifact/PR 完成，部署平台原子切换活动版本并保存旧版本指针。

#### 7）当前量化约束与回归证据

| 项目 | 当前值/结果 | 说明 |
|---|---:|---|
| Candidate 完整内容哈希 | SHA-256，64 个十六进制字符 | Keyword Generator 另用一段 12 位摘要构造可读候选版本名 |
| Gate 强制可比字段 | 6 个 | 数据 ID/Hash、模型、Prompt、Seed、Token Budget |
| 默认 Canary | 5% 流量、100 样本 | 达标后仍需人工审批 |
| 失败率门限 | 绝对 5%，且不高于 Baseline +1pp | 两个限制取更严格者 |
| Safety Violation | 1 次即暂停 | 不等待达到最小样本 |
| 演进回归场景 | 6/6 通过 | 可比提升、安全/数据失败、原子 Evidence、人工 Canary、消融记录、Stale Base 拒绝；见 [`test_evolution.py`](./tests/test_evolution.py)（L52） |

测试证明门禁状态机按设计工作，但没有产生真实线上“自进化后成功率提升多少”的结果。简历中更准确的说法是“设计并实现受控离线 Skill 演进与 Canary 治理骨架”，而不是“Agent 已实现自主 RSI 自我改写”。

### 四、意图识别和幻觉降低

13、SALK（Structure-Anchored LLM with Knowledge Synchronization）如何利用家居环境图谱先锚定与当前指令相关的设备和能力子图，再通过差分注意力剔除无关图谱知识，最终收缩每个 Skill Expert 内部的子工具空间？Structure Anchor、Knowledge Synchronization 和 Differential Attention 分别如何实现？与全量图谱/全量 Tool、仅结构锚定、仅差分注意力相比，相关设备与知识召回率、无关知识抑制率、Tool Recall、Tool/Schema 收缩率、Token 和任务成功率分别是多少，实验如何排除数据泄漏与场景偏差？

**参考回答：** SALK 的核心不是简单做一次关键词检索，而是把“图谱检索—知识过滤—工具投影”设计成逐层收敛的集合运算。Structure Anchor 先提供不可越过的结构边界，Differential Attention 再从锚定子图中压低与当前任务无关的知识，最后把保留下来的设备、能力和状态证据投影成 Skill Expert 的最小 Tool Mask。这样 LLM 看到的不是整屋知识和全量 Tool，而是完成当前任务所需的局部可执行空间。

#### 1）SALK 的完整收缩链路

设当前指令为 `q`，时刻 `t` 的家庭图谱为 `G_t=(V_t,E_t)`，Router 已激活 Skill `s`，其静态 Tool 白名单为 `T_s`。完整链路可以表示为：

```text
q + versioned G_t + T_s
        │
        ▼
Structure Anchor：定位房间、设备、能力及其局部关系
        │                         得到 G_anchor / D_q
        ▼
Knowledge Synchronization：读取当前版本的能力、状态与拓扑事实
        │                         得到 K_sync
        ▼
Differential Attention：保留任务相关知识，抵消全局背景知识
        │                         得到 K_relevant
        ▼
Capability-to-Tool Projection：设备能力映射并与 T_s 求交
        │
        ▼
T_final：本轮只向 Planner 暴露的子工具空间
```

最终工具集合可抽象为：

```text
T_final = (T_s
         ∩ Union(CapabilityTools(d), d ∈ D_q)
         ∩ ToolsSupportedBy(K_relevant))
         ∪ T_safe
```

其中 `T_safe` 只保留 `request_clarification/get_device_state` 这类澄清和状态查询能力，防止过度收缩后系统既不能执行，也无法恢复。

#### 2）Structure Anchor：先用图结构给出硬边界

结构锚定不是把整张图谱序列化进 Prompt，而是从指令中的房间、设备别名、能力和空间关系出发，定位锚点节点，再沿 `contains/located_in/adjacent_to/supports` 等有类型的边扩展有限跳数，得到与任务相关的局部子图：

```text
Anchor(q, G_t) -> {相关房间、候选设备、设备能力、必要邻接关系}
```

例如“把客厅沙发旁的灯调暗”首先锚定 `living-room`，再利用“沙发旁”定位候选灯具，最后只保留支持 Brightness 的设备；其他房间的灯、电视、门锁和家电不会进入后续知识集合。

当前工程中的简化实现是 [`TopologyCandidateFilter.candidates`](./homeclaw/topology/grounding.py)（L24）：它按 `room_id/capability/text_hint` 对设备节点做确定性过滤，并返回稳定的设备 ID、别名和能力。底层 [`InMemoryTopologyStore`](./homeclaw/topology/graph.py)（L30）保存节点、关系边和单调版本；更新时通过 `expected_version` 乐观锁拒绝旧写入，见 [`apply`](./homeclaw/topology/graph.py)（L60）。这为锚定结果绑定具体图谱版本提供了基础；当前 `CandidateAnchor` 尚未携带 `topology_version`，完整链路还需要把该版本写入 Context 和 Evidence。

Structure Anchor 解决的是 Recall 的搜索边界：它应尽量包含完成任务所需的设备和能力，但不能在这一层过早依赖单个 Tool 名称，否则一旦实体解析错误，后续注意力没有机会纠正。

#### 3）Knowledge Synchronization：同步的是当前事实，不是静态长 Prompt

家庭图谱会持续变化：设备可能上下线、Capability 可能升级、房间归属和状态也可能变化。Knowledge Synchronization 的作用是让锚定子图与当前 Registry/State Snapshot 对齐：

- 拓扑版本决定“设备在哪里、与谁关联”；
- Capability Registry 决定“设备此刻允许执行哪些 Tool”；
- State Snapshot 决定“当前值、采集时间和是否陈旧”；
- Planner 只消费这次任务的局部快照，不把旧图谱事实固化进长期 Prompt。

工程上，[`DeviceRecord/ToolSpec`](./homeclaw/verification/registry.py)（L43、L52）给出设备到 Tool 的权威映射，Topology 的乐观版本阻止并发写覆盖。真正执行前，Verifier 会重新检查设备在线性与状态新鲜度，并在决策中记录当前 Registry Version，因此“检索时相关”不等于“执行时仍然合法”。

#### 4）Differential Attention：在锚定子图内继续剔除知识噪声

结构锚定解决“去哪个局部区域找”，但锚定子图中仍可能包含同房间的无关设备、共享属性、历史状态和邻接节点。如果将这些知识等权注入，LLM 仍可能被高频但无关的图谱事实干扰。

SALK 的差分注意力可以抽象为两路知识权重：一路计算 Query 对锚定知识的任务相关响应，另一路估计全局图谱或结构背景产生的公共响应，再做差分抑噪：

```text
A_task = Attention(q, K_anchor)
A_bg   = Attention(q, K_background)
A_diff = Normalize(ReLU(A_task - λ · A_bg))
K_relevant = TopM_or_Threshold(A_diff, K_anchor)
```

被两路共同激活的泛化背景知识会被抵消，只有对当前任务具有额外解释力的设备、能力、状态和关系得到较高权重。差分结果是**请求级知识掩码**，不会从家庭图谱中永久删除节点；下一条指令到来时会基于新的 Query 和图谱版本重新计算。

例如 Anchor 已经把范围缩到客厅，但其中仍有灯、电视和空调；对于“调暗沙发旁的灯”，差分注意力应保留 `floor-lamp—supports—brightness` 及其当前亮度，压低电视音量、空调温度和无关历史状态。随后能力投影只留下 `set_light_brightness` 及必要查询/澄清 Tool。

#### 5）从相关知识到子工具空间如何落地

研究侧输出的不是一段更长的知识文本，而是 `相关设备集合 + 相关能力集合 + 证据权重`。工程侧再做确定性交集，避免让 LLM 自己根据知识描述猜 Tool：

| SALK 产物 | 工程投影 | 对应实现 |
|---|---|---|
| 锚定设备集合 `D_q` | 只查询这些设备的 Capability | [`TopologyCandidateFilter`](./homeclaw/topology/grounding.py)（L20） |
| Skill 静态白名单 `T_s` | Router 选中 Skill 后形成 `route.exposed_tools` | [`ProductionRuntime._route`](./homeclaw/agent/runtime.py)（L256） |
| 相关能力/知识掩码 | 与候选设备实际 Tool 并集求交 | [`ToolSpaceContractor.contract`](./homeclaw/routing/contraction.py)（L34） |
| 最终 `T_final` | 只序列化这些 Tool Schema 给在线 Planner | [`LLMProposer.propose`](./homeclaw/agent/proposer.py)（L85） |
| 越界防护 | 模型输出 Tool 必须仍属于本轮白名单 | [`LLMProposer._parse_action`](./homeclaw/agent/proposer.py)（L139） |

[`ToolSpaceContractor`](./homeclaw/routing/contraction.py)（L25）的实际集合运算是：将候选设备在 Capability Registry 中注册的 Tool 求并集，加上最小安全 Tool，再与 Router 的 Tool 集合求交。因此结构锚定提高设备相关性，差分注意力提高知识相关性，Capability Projection 则把“相关”变成不可绕过的 Tool 白名单。

当前 production-ready 分支实现了结构过滤、版本化图谱和确定性 Capability 交集；SALK 的差分权重计算仍属于研究侧机制，工程中尚未以独立 Attention/Knowledge Mask 模块接入。并且 [`ProductionRuntime._route`](./homeclaw/agent/runtime.py)（L264）只有在调用方 Context 已提供 `candidate_devices` 时才执行二次收缩；完整落地还需要让 Anchor/Differential Attention 的结果直接写入这一字段，并携带图谱版本和知识证据。

#### 6）当前能够由代码和报告支撑的收缩结果

| 评测层次 | 当前结果 | 正确解释 |
|---|---:|---|
| Skill Router Gold 集 | 25 条指令上 Top-2 Recall 与多标签完整覆盖均为 100% | 第一层没有在当前小型 Gold 集漏掉目标 Skill |
| 第一层 Tool 收缩 | 全量 11 Tool → 平均 4.40 Tool，减少 60.0% | Top-2 Skill Router 的平均 Tool 数 |
| 第一层 Schema 收缩 | 2406 → 928.72 Bytes，减少 61.4% | 可复现的模型无关 Schema 体积，不等于真实 Token |
| Lighting 合成链路 | 全量 11 → Skill 内 5 → 设备能力 3 Tool | 第二层相对 5 Tool 再减少 40%；相对全量最终减少 72.7% |
| 拓扑锚定 Fixture | 候选设备 2 → 1，减少 50% | 单个规则场景，不是全数据集平均值 |
| Tool Contractor 回归 | 2/2 通过 | 验证能力交集和无候选时的澄清回退 |

Router 原始结果见 [`router-eval-2026-11-09.json`](./reports/router-eval-2026-11-09.json)（L286），Lighting 二次收缩见同一报告的 [`device_scale`](./reports/router-eval-2026-11-09.json)（L1174）；拓扑与 Contractor 断言见 [`test_topology.py`](./tests/test_topology.py)（L63）和 [`test_tool_contraction.py`](./tests/test_tool_contraction.py)（L20）。

这些数字证明 HomeClaw 的工程映射确实能缩小 Tool/Schema 空间，但不能代替 SALK 论文中“全量图谱、仅 Anchor、仅 Differential Attention、两者结合”的四组消融。原论文表未随当前仓库提供，因此这里不重写未经核对的知识 Recall、噪声抑制率、Token 和任务成功率数值；正式引用时应直接绑定 SALK 的数据集、表格编号、样本数和实验配置。

#### 7）SALK 消融应该如何量化，避免只追求“越小越好”

| 指标 | 建议定义 | 防止的误导 |
|---|---|---|
| Device Recall | Gold 相关设备被 `D_q` 覆盖的比例 | 候选变少但删掉正确设备 |
| Knowledge Recall/Precision | Gold 相关图谱事实的召回与纯度 | 只报无关知识抑制率 |
| Noise Suppression | 被移除的 Gold 无关事实 / 全部无关事实 | 把简单场景当成强过滤能力 |
| Tool Recall | Gold 动作所需 Tool 是否仍在 `T_final` | 子工具空间小但任务不可执行 |
| Tool/Schema Contraction | `1 - final/full` | 不同 Registry 规模无法比较 |
| Token/Step/Cost | 同一模型与 Prompt 下的服务端 Token、规划步数和价格 | 用 Bytes 冒充 Token |
| End-state Success | 最终设备状态满足 Gold Goal | 把 Tool 调用成功当任务完成 |

四组消融必须使用相同的图谱快照、Tool Registry、任务集、模型版本、Prompt、Token/Step 预算和随机种子，只切换 Anchor 与 Differential Attention。数据集应按家庭或拓扑模板分组切分，避免同一设备别名、房间结构和近重复任务同时出现在训练与测试中；另外人为注入 25%/50%/100% 无关设备与图谱事实，观察 Noise 增长时 Tool Recall 和任务成功率是否稳定。

成功率使用配对任务结果与 Bootstrap 95% CI，Tool Recall 报告分子/分母，Token 和步骤报告均值、P50/P95。SALK 的核心目标不是获得最小 `T_final`，而是在维持高 Tool Recall 和终态成功率的前提下，最大化无关知识与 Tool Schema 的收缩。

面试时可以用一句话概括：**Structure Anchor 用图结构确定“哪些设备可能相关”，Differential Attention 在局部图中确定“哪些知识真正有用”，Knowledge Synchronization 保证这些事实属于当前版本，Capability Projection 再把相关知识转成 Planner 不可越界的最小 Tool Mask。**

14、Proposer–Binder–Verifier 闭环具体如何工作？工程实现为什么默认不需要把 Proposer 和 Verifier 包装成两个通过 A2A 通信的独立 Agent？结构化提议、实例绑定、反例证据和重规划信息如何传递？加入 Verifier 前后的 False Done Rate、动作幻觉率、非法动作拦截率、任务成功率和平均重规划轮数具体是多少，分别下降或提升了多少个百分点，测试样本量与置信区间是什么？

**参考回答：** 这里的“博弈”不是两个聊天 Agent 自由辩论，更不是已经求得 Nash 均衡，而是一个有明确动作空间、反例接口和轮数上限的 Proposal–Check–Revise 闭环。在线 LLM 只有提议权，Binder 和 Verifier 掌握实例绑定与准入权，设备状态证据掌握最终完成判定权。

#### 1）四层职责为什么必须分开

| 层次 | 输入与输出 | 信任边界 | 关键实现 |
|---|---|---|---|
| Proposer | 用户指令、局部 Context、Router Tool 子集、上轮反馈 → `ActionProposal[]` | LLM 输出全部视为不可信候选 | [`LLMProposer.propose`](./homeclaw/agent/proposer.py)（L76） |
| Binder | 语义设备名 → 唯一注册设备 ID | 0 个或多个实例都不猜；只有唯一注册候选才绑定 | [`InstanceBinder.bind`](./homeclaw/agent/binder.py)（L36） |
| Verifier | 结构化 Proposal + Capability Registry → `VerificationDecision` | 不读取模型 Chain-of-Thought，只相信 Registry 与确定性规则 | [`ActionVerifier.verify`](./homeclaw/verification/verifier.py)（L42） |
| Executor/Confirm | 已验证 Proposal → `ExecutionEvidence` → Workflow 终态 | “请求已发出”不等于“设备已完成” | [`_execute/_confirm`](./homeclaw/agent/runtime.py)（L415、L425） |

Proposer 看到的 Tool Schema 仅来自 `route.exposed_tools`；解析时还会再次检查 `tool_name` 是否在 Tool 白名单、`source_skill` 是否在已选 Skill 中，见 [`_parse_action`](./homeclaw/agent/proposer.py)（L139）。[`ActionProposal`](./homeclaw/domain/models.py)（L176）包含目标、参数、来源 Skill、Expected State、验证规则、幂等等级和风险等级，其中 Expected State 必填；非幂等动作若没有显式验证规则，领域对象本身就无法构造。

Binder 先查精确 `home_id + device_id`；精确实例不存在时，才通过房间、能力和别名查拓扑，并再次要求候选存在于 Capability Registry。唯一候选可绑定，零候选返回 `binding_not_found`，多候选返回 `binding_ambiguous`，对应代码见 [`InstanceBinder`](./homeclaw/agent/binder.py)（L25）。

Verifier 随后独立读取 Registry，逐项检查：

- 设备存在、在线且状态未超过默认 60 秒新鲜度；
- 设备是否真正注册了该 Tool；
- 未知参数、必填参数、类型、范围和枚举值；
- Proposal 的幂等等级是否与 Registry 一致；
- Proposal 与 Tool 中较高的风险是否得到授权。

规则集中在 [`ActionVerifier._verify`](./homeclaw/verification/verifier.py)（L59）和 [`_validate_tool`](./homeclaw/verification/verifier.py)（L113）。拒绝结果不是一段自然语言评论，而是带 `code/rule/retryable/metadata` 的 [`VerificationIssue`](./homeclaw/domain/models.py)（L204），可以稳定回放、聚合和测试。

#### 2）组件之间实际通过 Checkpoint Blackboard 通信，而不是 A2A 对话

[`ProductionRuntime`](./homeclaw/agent/runtime.py)（L184）把组件装配成固定 Workflow。节点不互相直接发聊天消息，而是通过带 Revision 的 `WorkflowState.data` 传递结构化状态：

```text
route
  -> proposals[]
  -> bound proposals[] / verifier_feedback[]
  -> execution_evidence[]
  -> COMPLETE / REPLAN / FAIL
```

[`_plan`](./homeclaw/agent/runtime.py)（L363）读取 `verifier_feedback` 并写入 `proposals`；[`_verify`](./homeclaw/agent/runtime.py)（L379）把 Binder、Verifier 和批内冲突 Issue 合并为反例；[`_replan`](./homeclaw/agent/runtime.py)（L411）再把控制权交回 PLAN。每个节点结束后，[`WorkflowHost`](./homeclaw/workflow/engine.py)（L64）将新状态、Revision 和 Outbox 原子 Checkpoint，因此这是一块可恢复的结构化 Blackboard，而不是临时 Prompt 对话。

同进程部署并不破坏认知隔离：隔离的关键是 Verifier 的输入只包含结构化 Proposal，规则证据来自独立 Registry，而不是进程数。只有在团队边界、扩缩容或故障域要求 Proposer/Verifier 跨服务时，才需要把同一 `ActionProposal/VerificationDecision` 契约放到 A2A、RPC 或消息队列上。此时也不应传递模型私有推理，只传版本、关联 ID、结构化 Issue 和 Evidence。

当前仓库没有实现 A2A 协议；把同进程函数调用包装成 A2A 只会增加序列化、超时、重试和幂等问题，不会自动提高验证独立性。

#### 3）“有界博弈”的边界在哪里

一次交互可以表示为：

```text
Proposer 给出候选动作
    -> Binder 给出实例反例
    -> Verifier/Conflict Detector 给出约束反例
    -> Proposer 根据结构化反例修正
    -> 达到预算后停止，不允许无限自证
```

默认 [`ExecutionBudget`](./homeclaw/workflow/state.py)（L32）限制 24 个节点、2 次 Re-Plan、16K Token 和 120 秒 Deadline；[`WorkflowHost`](./homeclaw/workflow/engine.py)（L138）在执行 REPLAN 节点时计数，超过上限直接进入失败终态。这样不会出现 Proposer 与 Verifier 无限来回争论。

同时要说明两个实现边界：

- 当前 `_replan` 只回到 PLAN，不会重新 ROUTE；如果根因是第一次漏召回 Skill/Tool，现有反馈无法扩大 Tool 子集。
- `VerificationIssue.retryable` 已进入契约，但 Runtime 当前没有按 retryable/non-retryable 分流，所有验证 Issue 都进入同一种 Re-Plan。生产版应让参数修正进入 PLAN、状态过期触发 Refresh、权限拒绝直接终止、能力缺失在预算内重新 ROUTE。

#### 4）False Done 不是只靠前置 Verifier 解决的

前置 Verifier 只能回答“这个动作现在是否允许尝试”，不能证明设备已经执行。因此完整闭环还需要后置 Evidence Gate：[`ExecutionEvidence`](./homeclaw/domain/models.py)（L236）规定 `SUCCEEDED` 必须包含 Observed State；[`ProductionRuntime._confirm`](./homeclaw/agent/runtime.py)（L425）只有在所有动作都是 `SUCCEEDED` 时才进入 COMPLETE。PUBACK、MCP 返回或无证据超时都不能直接完成任务。

所以面试时应把两类幻觉分开：

| 类型 | 阻断位置 | 示例 |
|---|---|---|
| Action Hallucination | Router 白名单、Binder、Verifier、Conflict Detector | 编造 Tool、虚构设备、参数越界、风险越权、批内冲突 |
| False Done | MQTT 状态证据与 Confirm 节点 | Broker 接收消息但设备未改变、旧 retained 状态、错误 command_id |

把两者都笼统归因给“Verifier”会掩盖真正的信任边界。

#### 5）当前量化证据及其统计边界

| 验收对象 | 当前可复现结果 | 对应代码/测试 | 正确解释 |
|---|---:|---|---|
| Verifier 规则 | 4/4 测试方法通过 | [`test_verifier.py`](./tests/test_verifier.py)（L18） | 覆盖合法动作、非法参数/设备、离线/过期和风险授权；幂等校验有实现，但该文件未单独构造 mismatch |
| Binder | 2/2 通过 | [`test_instance_binder.py`](./tests/test_instance_binder.py)（L11） | 唯一别名绑定、未注册实体拒绝 |
| Production Runtime | 6/6 通过 | [`test_production_runtime.py`](./tests/test_production_runtime.py)（L55） | 覆盖成功闭环、显式 False-Done、Tool 收缩、视觉成功/歧义、跨家庭授权 |
| PUBACK 无状态证据 | 1/1 被阻断 | [`test_puback_without_state_never_becomes_false_done`](./tests/test_production_runtime.py)（L141） | 证明该分支按设计工作，不能称为现实 False Done Rate=0% |
| 视觉歧义 | 1/1 在执行前拒绝 | [`test_ambiguous_visual_grounding_rejects_before_device_execution`](./tests/test_production_runtime.py)（L224） | 证明 fail-closed 路径，不是模型幻觉率 |

仓库没有“Verifier 开/关”的同集实验，因此以下数值目前都**没有可信答案**：Verifier 前后 False Done Rate、动作幻觉率、非法动作拦截率、任务成功率、平均 Re-Plan 轮数及置信区间。现有测试是分支正确性断言，不能把 `1/1` 或 `6/6` 包装成生产分布上的 100%。

简历里的“长程复杂指令成功率相对基线提升 25%”是系统级既有结果，包含 Router、Grounder、Skill 收缩、Verifier 和执行闭环的共同影响，不能全部归因给 Verifier。正式单模块消融应在同一任务集上至少比较 `无 Verifier`、`仅 Schema`、`完整 Binder+Verifier`、`完整闭环+Evidence` 四组，并逐样本报告成功、非法动作、False Done 和 Re-Plan 次数；只有这样才能给出提升百分点和配对置信区间。

15、Verifier 如何检测同一批原子动作中的设备状态冲突、环境影响冲突、资源竞争、循环依赖和冗余动作？你从 KnowDetector 的图模式思路中借鉴了什么？HomeClaw 自有冲突测试集包含多少条样本、各冲突类型占比是多少，Precision、Recall、F1、Exact Match、误报率和漏报率的实测值分别是多少？与未使用图约束或仅做 Schema 校验的基线相比提升了多少个百分点，为什么不能直接把外部论文结果当作本项目指标？

**参考回答：** 我借鉴 KnowDetector 的核心不是复制某几个 if/else，而是把自动化行为正规化为“动作—设备—环境变量—资源—依赖”的关系，再用可解释的局部模式识别干扰。但 HomeClaw 当前实现是轻量的结构化规则检测器：设备、环境和资源冲突主要通过动作批扫描完成，只有依赖环使用显式 DAG/DFS；它还不是一个完整知识图谱子图匹配引擎。

#### 1）六类规则具体检查什么

[`ActionConflictDetector.detect`](./homeclaw/verification/conflicts.py)（L19）按固定顺序运行六类规则：

| Issue Code | 判定条件 | 证据输出 | 主要复杂度 |
|---|---|---|---:|
| `redundant_action` | 同一设备、同一 Tool、Arguments 完全相同 | 两个 `action_id` | `O(n²)` |
| `device_conflict` | 同一设备的 Expected State 有同名字段但目标值不同 | 冲突字段与动作对 | `O(n²)` |
| `environment_conflict` | 两个动作对同一 `environment_effects` 变量给出不同方向/值 | 环境变量与动作对 | 近似 `O(e)` |
| `resource_conflict` | 两个动作占用同一 `exclusive_resources`，且没有显式先后关系 | 资源名与动作对 | 近似 `O(r)` |
| `blocked_action` | 一个动作产生的最终状态与另一个动作的 Preconditions 矛盾 | 阻塞设备、字段和被阻塞动作 | 近似 `O(n+p)` |
| `dependency_cycle` | 动作依赖图出现回边 | 完整 Cycle Path | `O(V+E)` |

设备冲突和冗余逻辑见 [`_duplicates_and_device_conflicts`](./homeclaw/verification/conflicts.py)（L42）；环境与资源规则见 [`_environment_conflicts`](./homeclaw/verification/conflicts.py)（L76）和 [`_resource_conflicts`](./homeclaw/verification/conflicts.py)（L99）；阻塞和 DFS 环检测见 [`_blocked_actions`](./homeclaw/verification/conflicts.py)（L126）与 [`_dependency_cycle`](./homeclaw/verification/conflicts.py)（L157）。

例如，“开加热器”和“开空调”单独看都通过参数 Schema，但两者的 `temperature_direction` 分别为 `up/down`，批内检测会返回 `environment_conflict`；洗衣机和洗碗机同时占用 `water-line` 会返回 `resource_conflict`，如果 DAG 明确其中一个依赖另一个，则视为合法串行。

#### 2）从 KnowDetector 借鉴了什么，又没有借鉴什么

KnowDetector 的思路是把多个 IoT 自动化规则及设备语义组织成图，再匹配 Device Loop、Blocked Action、Redundancy、Environment Loop、Device Conflict 和 Environment Conflict 等子图模式。HomeClaw 借鉴了三点：

1. 冲突是**动作之间的关系问题**，不能靠逐个 Tool Schema 校验发现；
2. 环境变量和共享资源必须成为一等语义，而不能只看设备 ID；
3. 检测结果要保留涉及动作和证据字段，才能支持 Re-Plan，而不是只返回布尔值。

HomeClaw 没有复制 KnowDetector 的 Java 实现、知识图谱数据或论文标签，也没有复现它的完整模式库。当前 detector 直接消费 `ActionProposal`，没有把家庭拓扑构造成持久化 KG，也没有通用子图查询 DSL。因此更准确的表述是“借鉴图模式思想实现动作批静态冲突规则”，不能说“复现了 KnowDetector”。

#### 3）Runtime 中还有三处重要工程缺口

- [`ProductionRuntime._verify`](./homeclaw/agent/runtime.py)（L400）调用 `detect(bound_proposals)` 时没有传 `dependencies`。所以依赖环和“有序资源不冲突”虽然在 Detector API 与离线数据中实现，当前在线 Runtime 实际看到的是空 DAG。
- `environment_effects` 与 `exclusive_resources` 当前来自 Proposal 的 `verification` 字段；[`ToolSpec`](./homeclaw/verification/registry.py)（L43）还没有权威的环境影响和资源声明，Verifier 也没有校验这两项。也就是说 LLM 可以漏写或写错冲突元数据。生产版应由版本化 Capability Registry 补全这些属性，而不是信任 Proposer 自报。
- 资源规则只判断直接依赖，没有计算传递可达性；环境变量也没有独立的 `home_id/room_id` Scope，如果变量名没有编码空间范围，两个不同房间可能被误判为冲突。Blocked Action 目前按设备保留一个最终状态，多次写同一设备时也可能丢失中间关系。

因此当前结果适合作为确定性规则骨架，不能包装成已经完成全量图推理。

#### 4）自有数据集组成与指标口径

[`conflict_gold.jsonl`](./data/eval/conflict_gold.jsonl)（L1）共有 8 个仓库自有合成 Case：

| 类别 | Case 数 | 占全部样本 | Gold 语义 |
|---|---:|---:|---|
| 安全独立动作 | 1 | 12.5% | 无冲突负例 |
| 已排序资源共享 | 1 | 12.5% | 有依赖顺序的无冲突负例 |
| 冗余动作 | 1 | 12.5% | `redundant_action` |
| 设备状态冲突 | 1 | 12.5% | `device_conflict` |
| 环境影响冲突 | 1 | 12.5% | `environment_conflict` |
| 无序资源竞争 | 1 | 12.5% | `resource_conflict` |
| 依赖环 | 1 | 12.5% | `dependency_cycle` |
| 前置条件阻塞 | 1 | 12.5% | `blocked_action` |

其中 6 条是冲突正例、2 条是无冲突负例，每个正例只含一种 Issue Code，没有多冲突组合。评测器按**Issue Code 集合**累计 Micro TP/FP/FN，Exact Match 是“预测 Code 集合与 Gold Code 集合完全相同”，见 [`evaluate_conflict_detector`](./homeclaw/eval/conflict_metrics.py)（L28）。它不会评价动作对、边或冲突次数是否定位正确；相同 Code 出现多次也会被集合去重。

#### 5）实测结果与 Schema-only 对照

| 方法 | Precision | Recall | F1 | Exact Match | Case 误报率 | Case 漏报率 |
|---|---:|---:|---:|---:|---:|---:|
| 仅单动作 Schema、批内始终输出空冲突集 | 无预测正例；当前公式记 0% | 0% | 0% | 25% | 0/2 = 0% | 6/6 = 100% |
| HomeClaw Conflict Detector | 100% | 100% | 100% | 100% | 0/2 = 0% | 0/6 = 0% |

HomeClaw 原始报告见 [`conflict-eval-2026-11-09.json`](./reports/conflict-eval-2026-11-09.json)（L18），执行入口见 [`evaluate_conflicts.py`](./scripts/evaluate_conflicts.py)（L61）。Schema-only 行没有单独报告文件，它是根据“只校验每个动作、不产生任何批冲突 Code”的定义和同一 Gold 标签确定性推导出来的，不能冒充一次独立模型实验。

按这个极小集合的表面数值，HomeClaw 相对空预测基线 Recall、F1 各增加 100 个百分点，Exact Match 增加 75 个百分点，漏报率下降 100 个百分点；Precision 因基线没有预测正例而不可作有意义的百分点比较。

但小样本不确定性非常大：对 6/6 的 Precision/Recall 使用 Wilson 95% 区间约为 **61.0%～100%**，对 8/8 Exact Match 约为 **67.6%～100%**；0/2 误报率的 Wilson 上界仍约为 **65.8%**。这说明“表面 100%”只能证明 8 个手工规则样例没有回归，不能证明真实家庭也接近 100%。当前 JSON 报告没有保存这些区间，以上只是根据计数补充的统计解释。

#### 6）为什么外部论文指标不能直接写进简历

KnowDetector 与 HomeClaw 的检测对象、图构造、模式库、数据来源、正负样本比例和统计单位都不同。外部论文可能按 Automation App、Rule Pair 或 Graph Pattern 统计，HomeClaw 当前按 8 个合成 Case 的 Issue Code 集合统计；即使指标名称都叫 Precision/F1，分母也不相同。直接借用论文数字等于把别人的模型、数据和实验条件归到本项目，技术上无法复现，面试中也经不起追问。

正式生产评测至少应增加：真实家庭与仿真混合场景、跨房间负例、多冲突组合、同设备多次写、传递依赖、缺失/错误元数据及人工双人标注；指标同时报告 Code、Action Pair 和 Evidence Edge 三个层次。工程上还应把环境影响与资源声明迁入 Registry，将 Workflow DAG 传给 Detector，并对依赖图做可达性和强连通分量分析。届时才能把冲突检测率作为项目成果，而不只是规则回归覆盖率。

### 五、MCP、MQTT 和动作执行

16、在线模型产生 Function Calling 或结构化动作提议后，Host 如何把它收敛为 `ActionProposal`，筛选允许调用的 Tool，并通过 MCP Client 请求家居领域 MCP Server？MCP Tools、Prompts 和 Resources 分别如何实现，当前代码真正接通到了哪一层？

**参考回答：** MCP 在 HomeClaw 中是 Host 与家居领域服务之间的协议边界，不是让在线模型直接获得设备执行权。模型只能提交结构化候选；Router、Binder、Verifier、Host Authorization 和 MCP Server 逐层收窄权限，最终返回的也不是一句“调用成功”，而是可进入状态确认链路的 `ExecutionEvidence`。

#### 1）从模型提议到 MCP 调用的完整时序

```text
Online LLM
   │  strict JSON / future native tool_calls
   ▼
ActionProposal
   │  Router Tool 白名单 + Binder + Verifier
   ▼
ProductionRuntime._execute
   │  生成 command_id，携带本轮 allowed_tools
   ▼
MCPActionDispatcher
   │  home_id/device_id/arguments/action_id
   ▼
MCPHostGateway
   │  allowlist + RBAC + tenant + policy version + confirmation
   ▼
MCP Client ──> Domain MCP Server ──> Domain Tool Handler
                                      │
                                      ▼
                                  MQTT Bridge
                                      │
                                      ▼
                              ExecutionEvidence
```

当前 [`LLMProposer`](./homeclaw/agent/proposer.py)（L63）把本轮允许的 Tool Schema 放进 Prompt，并解析严格 JSON；它还没有直接消费 OpenAI/Gemini SDK 的原生 `tool_calls` 对象。无论输入来自原生 Function Calling 还是 JSON，进入执行面的统一边界都应是 [`ActionProposal`](./homeclaw/domain/models.py)（L176）。解析阶段再次拒绝未路由的 Tool 和 Skill，见 [`_parse_action`](./homeclaw/agent/proposer.py)（L139）。

验证通过后，[`ProductionRuntime._execute`](./homeclaw/agent/runtime.py)（L415）为每个动作派生 `command_id`，并把本轮 `route.tools` 作为 Allowlist 传给 [`MCPActionDispatcher`](./homeclaw/agent/runtime.py)（L68）。Dispatcher 只添加 `home_id/device_id/_homeclaw_action_id` 等受控字段，再调用 [`MCPHostGateway.call`](./homeclaw/mcp_runtime/host.py)（L28）。

Gateway 在实际 Client 调用前重新检查 Tool 是否仍在本轮 Allowlist；若配置了 Authorization Policy，还会检查认证主体、角色、家庭租户、策略版本和显式确认。规则见 [`AuthorizationPolicy.authorize`](./homeclaw/security/authorization.py)（L42）。因此模型即使猜到一个未披露 Tool 名称，也无法绕过 Host。

#### 2）MCP Tools：领域契约与设备协议必须分层

| 层次 | 保存内容 | 不应该保存什么 | 对应代码 |
|---|---|---|---|
| Skill/Tool Registry | Tool 名称、描述、Input Schema、风险 | 厂商 Topic、Broker 地址 | [`ToolDefinition`](./homeclaw/routing/models.py)（L12） |
| MCP Tool | 领域名称、描述、`inputSchema`、版本、Handler | 原始 MQTT Topic | [`MCPTool`](./homeclaw/mcp_runtime/server.py)（L12） |
| MCP–MQTT Binding | 来源 Skill、Expected State Builder、超时 | 面向 LLM 的自由文本执行逻辑 | [`MqttToolBinding`](./homeclaw/mcp_runtime/home_server.py)（L13） |
| MQTT Command Mapping | Command/State/Availability Topic、QoS、新鲜度 | Agent Prompt 与 Tool Schema | [`CommandMapping`](./homeclaw/mqtt/bridge.py)（L24） |

[`register_mqtt_tool`](./homeclaw/mcp_runtime/home_server.py)（L23）把领域 Tool 注册到 Server。Handler 会删除 `_homeclaw_*` 内部字段、校验绑定家庭、提取设备 ID，并使用服务端 `expected_state_builder` 重新构造 Expected State。这样最终状态目标不只依赖模型自报，Bridge 可以依据服务端规则判断执行结果。

[`DomainMCPServer.register_tool`](./homeclaw/mcp_runtime/server.py)（L48）拒绝名称包含 `/` 或以 `mqtt` 开头的 Tool，避免直接把 `home/+/command` 暴露成模型能力。但这只是最小命名门禁：当前代码没有递归扫描 `inputSchema` 是否夹带 Topic，也没有在 `DomainMCPServer.call_tool` 内执行通用 JSON Schema 校验。生产注册流水线仍应审计 Schema，且所有调用必须先经过 Host Verifier。

风险和幂等性目前由 `ActionProposal/ToolSpec` 在 Host 侧校验，并未进入 `MCPTool` 或 `MqttToolBinding`。Server 重建 Proposal 时会使用领域对象默认幂等/风险值，因此当前 Binding 只适合绝对设值类 Tool；若要支持门锁或非幂等动作，必须把权威 `risk/idempotency/verification` 加入 Binding，不能依赖默认值。

#### 3）MCP Host 的授权是第二道门，而不是替代 Router/Verifier

[`MCPHostGateway.exposed_tools`](./homeclaw/mcp_runtime/host.py)（L24）只返回 Skill 选中的 Tool；`call()` 又做一次调用时校验。Authorization 启用后采用版本化 Fail-closed RBAC：

- Tool 没有策略规则时拒绝；
- 角色不满足时拒绝；
- `home_id` 不属于 Principal 时拒绝；
- 高风险 Tool 未显式确认时拒绝；
- 调用方携带的策略版本与活动版本不一致时拒绝。

但认证本身不在该模块内完成，`Principal` 必须由 API Gateway/mTLS/OIDC 等部署边界注入；而且 `authorization=None` 时 Gateway 会跳过授权。因此生产 Composition Root 必须强制配置策略，不能把“支持授权”写成“所有部署天然已授权”。

#### 4）MCP Prompts：稳定规则与实时状态分离

[`MCPPrompt`](./homeclaw/mcp_runtime/server.py)（L32）包含稳定名称、描述、版本和纯 Renderer；[`DomainMCPServer.get_prompt`](./homeclaw/mcp_runtime/server.py)（L139）只根据参数渲染模板。合理的 Prompt 划分是：

| Prompt | 只包含 | 不包含 |
|---|---|---|
| `plan_device_action@vN` | 规划格式、Tool 使用约束、Expected State 要求 | 实时温度、设备在线状态 |
| `verify_device_action@vN` | 验证规则、证据格式、拒绝语义 | 某次请求的可变状态 |
| `recover_failed_action@vN` | 故障分类、是否允许重试、恢复输出格式 | 已过期的执行结果 |

实时状态通过 Resource 或本轮 Context 按需读取，这样 Prompt 可缓存和版本化，状态则按 TTL/Sequence 保持新鲜。

当前仓库只实现了 Prompt 注册、列举和渲染语义；实际 Prompt 只出现在 [`test_mcp_runtime.py`](./tests/test_mcp_runtime.py)（L42），Production Runtime 没有调用 MCP `get_prompt()`。因此这里是可执行协议骨架，还不是已经上线的规划/验证/恢复 Prompt Catalog。

#### 5）MCP Resources：聚合状态，而不是把传感器流持续塞给 LLM

[`StateResourcePublisher`](./homeclaw/mcp_runtime/resources.py)（L11）把设备状态暴露为：

```text
home://<home_id>/devices/<device_id>/state
```

Resource Reader 返回 `available/stale/sequence/observed_at/state`，数据来自版本化状态缓存；它不会返回原始 MQTT Event 流。每个 [`VersionedStateDiff`](./homeclaw/state/cache.py)（L21）先经过 Sequence 合并，只有 `APPLIED` 且调用方提供的 `should_notify(previous,current)` 命中时，才调用 `notify_resource_updated()`。普通温度波动只更新快照，异常、阈值达成或用户订阅命中才产生通知。

测试中连续写入温度 `20→21→31`，缓存最终 Sequence 为 3，但只在达到 30℃ 阈值时发出 1 次通知，见 [`test_high_frequency_updates_are_aggregated_and_only_anomalies_notify`](./tests/test_state_resources.py)（L38）。通知本身只携带 URI，Agent 若关心变化再读取聚合 Resource，避免把高频 Payload 直接污染上下文。

当前 `should_notify` 是注入的业务函数，没有内置异常模型或用户订阅存储；Subscriber 也是进程内 Callback。官方 Session Adapter 支持 `subscribe_resource`，见 [`AsyncMCPClientAdapter`](./homeclaw/mcp_runtime/sdk_adapter.py)（L9），但尚未接通远程 Resource Updated 事件消费。此外 Resource Read 目前没有独立的租户授权门，生产环境必须在 URI 解析层校验 Principal 的 `home_id`。

#### 6）当前 MCP 实现到底到哪一步

[`DomainMCPServer`](./homeclaw/mcp_runtime/server.py)（L40）实现了可测试的 Tools/Resources/Prompts 语义和进程内 Client；[`AsyncMCPClientAdapter`](./homeclaw/mcp_runtime/sdk_adapter.py)（L9）适配官方异步 `ClientSession` 形状并统一 30 秒超时。但当前同步 `MCPHostGateway` 没有直接装配这个异步 Adapter，仓库也没有独立 stdio/HTTP MCP Server 启动入口。因此：

- 模块化单体路径可以通过 `InProcessMCPClient` 执行；
- 官方 SDK 的 Client 形状和超时已测试；
- 真正的跨进程 MCP Server Transport、异步 Gateway 以及生产启动/鉴权链路仍需接通。

#### 7）量化验收与不能过度承诺的指标

| 验收范围 | 当前结果 | 覆盖内容 |
|---|---:|---|
| MCP Runtime | 5/5 测试方法通过 | Tool Allowlist、Resource、Prompt、原始 Topic 名拒绝、版本化租户授权 |
| 授权分支 | 1 次允许、4 类拒绝断言通过 | 缺 Principal、旧策略、缺确认、跨家庭 |
| 官方 Session Adapter | 2/2 通过 | Tool/Resource/Prompt 形状映射与超时 |
| State Resource | 3/3 通过 | 选择性通知、权威对账、Read-through |

对应测试见 [`test_mcp_runtime.py`](./tests/test_mcp_runtime.py)（L18）、[`test_production_adapters.py`](./tests/test_production_adapters.py)（L158、L188）和 [`test_state_resources.py`](./tests/test_state_resources.py)（L37）。这些是协议与分支正确性，不是跨进程 MCP 的吞吐、P95 或可用性；当前没有真实 MCP Server 进程和网络压测报告。

17、MCP–MQTT Bridge 的核心设计目的是什么？领域 Tool 如何映射为内部 Topic、Payload 和 Expected State？为什么 Broker PUBACK 只能证明消息已被 Broker 接收，系统又如何通过业务拒绝或目标 State Evidence 判断设备是否真正执行成功？

**参考回答：** Bridge 是领域语义与设备协议之间的防腐层。上层只认识 `set_temperature/set_light_brightness` 和 Expected State；下层才认识厂商 Topic、QoS、Availability、Payload Envelope 和状态回报。更换 Broker 或设备 Topic 不应改变模型看到的 Tool Schema。

#### 1）领域 Tool 到 MQTT 的四层映射

| 层次 | 示例 | 责任 |
|---|---|---|
| MCP Tool | `set_light_brightness(brightness=40)` | 面向 Agent 的稳定领域接口 |
| `MqttToolBinding` | Expected State=`{"brightness":40}`、Timeout=5s | 把领域参数转换为可验证目标 |
| `CommandMapping` | Command/State/Availability Topic、QoS=1、状态最大年龄=60s | 保存内部 MQTT 路由 |
| Bridge Payload | `command_id/action_id/device_id/arguments` | 形成设备网关可去重的通用命令信封 |

`MqttToolBinding` 见 [`home_server.py`](./homeclaw/mcp_runtime/home_server.py)（L13），Topic 映射见 [`CommandMapping`](./homeclaw/mqtt/bridge.py)（L24）。[`MqttCommandBridge.execute`](./homeclaw/mqtt/bridge.py)（L99）构造的 Payload 是固定 Envelope，原始 Topic 只传给 `MqttTransport.publish()`，不会返回 Host 或进入 LLM Context。

当前 `CommandMapping` 以 `tool_name` 为唯一 Key，且 Topic 是固定字符串；这更适合单设备 Binding 或“每个设备一个 Bridge 实例”。大规模设备接入应改为 `(home_id, device_id, tool_name) -> mapping` 的 Resolver，并提供厂商 Payload Builder。否则同一个 `set_light_brightness` 无法在一个 Bridge 中安全映射到上千设备，当前代码也不能宣称已经完成多厂商动态 Topic 路由。

#### 2）执行时序为什么要先订阅再发布

```text
查 command_id 去重记录
  -> claim(command_id)
  -> 检查 Tool Mapping 与已知 Offline 状态
  -> ensure_subscription(state_topic)
  -> publish(command_topic, payload)
  -> 等待同一 state_topic 上的终态证据
  -> 写 State Cache 与 Idempotency Evidence
```

先完成 State Subscription 再 Publish，可以避免设备响应很快而 Host 尚未订阅造成 ACK/State 丢失。真实 Paho Adapter 还会等待 SUBACK，见 [`PahoMqttTransport.ensure_subscription`](./homeclaw/mqtt/paho_adapter.py)（L76）。

发布阶段经过有限重试和 Circuit Breaker；[`retry_call`](./homeclaw/resilience/controls.py)（L40）对 `NON_IDEMPOTENT` 动作强制只有 1 次，对其余动作才使用默认最多 3 次重试。所有重试复用相同 `command_id`，而不是每次生成新业务命令。

#### 3）PUBACK、业务拒绝和设备成功是三种不同证据

[`PahoMqttTransport.publish`](./homeclaw/mqtt/paho_adapter.py)（L61）等待 `wait_for_publish()`，这最多证明 Broker 按对应 QoS 接收/确认了 Publish。Broker 不知道灯是否真的变亮，也不知道设备是否离线、物理童锁是否开启。

| 观察结果 | Bridge 终态 | 业务解释 |
|---|---|---|
| Broker 拒绝、网络异常或 Circuit Open | `FAILED`，可重试依赖错误 | 命令没有获得可靠传输确认 |
| 没有 Tool Mapping | `REJECTED` | 领域能力没有设备协议实现 |
| 设备返回匹配 `command_id` 的 `rejected/failed` | `REJECTED`，不可重试 | 设备明确拒绝，例如童锁开启 |
| Publish 被接受但超时前无目标状态 | `UNKNOWN` | 不能判断设备是否执行，绝不报成功 |
| 收到满足 Expected State 的状态 | `SUCCEEDED` | 有设备状态证据，可以进入 Workflow Confirm |

当前实现并不把只有 `status=succeeded`、却没有目标 State 的正向 ACK 当作成功；成功必须通过 [`matches_expected_state`](./homeclaw/state/cache.py)（L63）。这比“收到业务 ACK 就完成”更严格，而负向 ACK 可以立即终止等待并保留拒绝原因。

#### 4）状态证据的匹配规则与当前缺口

[`_wait_for_confirmation`](./homeclaw/mqtt/bridge.py)（L253）执行以下检查：

- 若消息携带其他 `command_id`，拒绝；
- Retained 消息若没有当前 `command_id`，拒绝；
- Retained 消息必须带可解析且未超过默认 60 秒的 `observed_at`；
- 状态必须递归包含 Expected State，允许额外字段；
- 明确 `rejected/failed` 只接受当前 `command_id`。

这里需要如实说明两个安全缺口：

1. 非 Retained State 当前允许缺少 `command_id`，只要状态值匹配就可能确认；严格生产模式应要求 `command_id`，或至少要求 `observed_at >= command_started_at` 且 Sequence 高于命令前快照。
2. 收到匹配状态后虽然会把 Sequence 写入 Cache，但 Bridge 不检查 `cache.apply()` 是否返回 `OUT_OF_ORDER/GAP` 就生成成功 Evidence。生产版应先通过版本门禁，再允许 `SUCCEEDED`。

因此当前代码已经挡住“旧 retained 状态直接冒充成功”，但尚未形成最严格的因果状态证明。

#### 5）UNKNOWN、迟到证据与幂等重试

Bridge 先按 `command_id` 查询 Idempotency Store：已有终态直接返回；已有 `UNKNOWN` 时只继续等待状态，不重新 Publish。测试中第一次超时得到 UNKNOWN，随后注入迟到状态，第二次调用升级为 SUCCEEDED，Publish 数仍为 1，见 [`test_late_ack_can_upgrade_unknown_without_republishing`](./tests/test_mqtt_bridge.py)（L164）。

发布重试也复用同一个 `command_id`，见 [`test_idempotent_publish_retry_reuses_same_command_id`](./tests/test_mqtt_bridge.py)（L181）。内存实现只适用于单进程；生产可替换为 [`RedisIdempotencyStore`](./homeclaw/state/redis_adapter.py)（L140），默认保留 86400 秒并用 `SET NX` Claim。

但“同一 ID”只有在设备网关也按 `command_id` 去重时才能阻止重复物理执行；MQTT 自身不会理解业务 ID。Bridge 的去重存储、PostgreSQL Action Attempt 和设备端去重必须共同工作。

#### 6）当前回归证据

| 场景 | 当前结果 |
|---|---:|
| PUBACK 无状态证据 | 1/1 保持 UNKNOWN |
| 匹配状态与重复调用 | 1/1 成功，第二次未重复发布 |
| 错误 `command_id` | 1/1 未确认 |
| 缺失 Mapping | 1/1 拒绝且未发布 |
| 设备业务拒绝 | 1/1 返回 REJECTED 与原因 |
| Broker 不可用 | 1/1 返回可重试 FAILED，按测试策略发布 2 次 |
| 已知设备离线 | 1/1 发布前失败 |
| 陈旧 Retained | 1/1 未确认 |
| 迟到状态 | 1/1 UNKNOWN 升级成功且不重发 |
| 幂等 Publish 重试 | 1/1 两次使用相同 `command_id` |

10 个场景见 [`test_mqtt_bridge.py`](./tests/test_mqtt_bridge.py)（L11）。它们使用进程内 Transport 和毫秒级测试超时，证明状态机分支而非真实 Broker 性能；Paho Adapter 尚未在仓库报告中给出 Mosquitto 断网、重连、QoS 重复率、状态确认 P50/P95 或长期稳定性结果。

18、Host 如何在 PostgreSQL 中持久化固定 Workflow 状态机、已完成节点、关联 ID、Checkpoint、Action Attempt 和 Outbox，并保证节点状态与 Outbox 原子更新？当前是否真的保存了任务依赖 DAG，崩溃恢复和业务幂等又分别由哪一层负责？

**参考回答：** 当前 Host 持久化的是固定节点状态机及其完整 JSON State，不是已经实现的任意任务 DAG。Workflow Checkpoint 解决“从哪个节点恢复”，Action Attempt 解决“这个动作是否已经派发/完成”，`command_id` 和设备端去重解决“重复消息是否产生重复副作用”，Outbox 解决“数据库提交后事件最终能否发出”。这四类一致性问题不能用一个 QoS 或一个事务替代。

#### 1）PostgreSQL 中四张表分别保存什么

| 表 | 关键字段 | 作用 |
|---|---|---|
| `workflow_task` | `task_id/request_id/trace_id/status/current_node/revision/deadline/state` | 保存任务最新快照，支持按 Task 恢复 |
| `workflow_checkpoint` | `task_id/revision/node/state` | 保存每个 Revision 的历史 Checkpoint |
| `action_attempt` | `command_id/task_id/action_id/idempotency_key/status/request/evidence/attempt_count` | 保存跨崩溃的动作身份与执行证据 |
| `workflow_outbox` | `message_id/task_id/topic/payload/created_at/published_at` | 与状态提交同事务保存待发布事件 |

DDL 见 [`001_workflow.sql`](./deploy/postgres/001_workflow.sql)（L3）。[`WorkflowState`](./homeclaw/workflow/state.py)（L46）还在 State JSON 中保存 `step_count/replan_count/tokens_used/completed_nodes/errors/data`；Route、Proposal、Verifier Feedback 和 Execution Evidence 都可随 Checkpoint 持久化。

当前 Workflow 图是代码中固定的 `RECEIVE→ROUTE/GROUND→PLAN→VERIFY→EXECUTE→CONFIRM` 状态机，节点注册见 [`ProductionRuntime`](./homeclaw/agent/runtime.py)（L216）。仓库没有独立的 Action DAG 数据模型或 PostgreSQL 依赖边表，而且 Runtime 调用 Conflict Detector 时也没有传动作依赖。因此不能回答成“任务 DAG 已持久化”；现阶段只有固定控制流和 `completed_nodes`，任意 DAG 仍需增加 `workflow_node/workflow_edge/node_attempt` 等持久化模型。

#### 2）Checkpoint、Revision 和 Outbox 如何保持原子

[`WorkflowHost._run`](./homeclaw/workflow/engine.py)（L64）在每个节点 Handler 成功返回后：

1. 合并节点输出到 `state.data`；
2. 累加 Token、Step、Re-Plan 和 Completed Node；
3. 设置下一个节点与状态；
4. 使用旧 Revision 调用 `save_with_outbox()`。

[`PostgresCheckpointStore.save_with_outbox`](./homeclaw/workflow/postgres_store.py)（L64）在同一 Connection Context 中完成三件事：

- `UPDATE workflow_task ... WHERE revision=expected_revision RETURNING revision`；
- 追加一条 `workflow_checkpoint`；
- 插入同节点产生的 `workflow_outbox`。

Revision CAS 防止两个 Worker 覆盖同一任务；任一 SQL 抛错时 Connection Transaction 应整体回滚，避免“状态成功但事件丢失”。Outbox 的 `message_id` 主键又让重复插入变为 No-op。

需要说明：仓库实现了 `pending()/mark_published()` 存储接口，但没有 Outbox Publisher Worker、RabbitMQ Publisher Confirm 处理或多 Worker 的 `FOR UPDATE SKIP LOCKED` Claim。当前只能证明事务写入语义，不能宣称事件投递服务已经生产化。

#### 3）崩溃发生在不同时间点，恢复语义并不相同

| 崩溃位置 | 持久状态 | Resume 行为 | 防重复条件 |
|---|---|---|---|
| 节点执行前/纯计算中 | Checkpoint 仍指向当前节点 | 重新执行当前节点 | 节点应确定性或无副作用 |
| 节点返回后、Checkpoint 前 | 仍是旧 Revision | 重跑节点 | 外部副作用必须另有幂等层 |
| Action Attempt Claim 后、Publish 前 | `DISPATCHED`，原 `command_id` 已保存 | 复用原 ID 再进入 Dispatcher | 相同 Idempotency Key |
| Publish 后、Evidence 写入前 | 数据库仍可能只有 `DISPATCHED` | 可能再次发送同一 `command_id` | Redis/设备端必须按 ID 去重 |
| Evidence 已写、Workflow Checkpoint 前 | Action Attempt 已含终态证据 | 直接返回旧 Evidence，不再调用设备 | 持久 Evidence |

[`WorkflowHost.resume`](./homeclaw/workflow/engine.py)（L56）从 `workflow_task.state.current_node` 继续。执行节点若配置了 `PostgresActionAttemptStore`，Production Runtime 会用 [`DurableActionDispatcher`](./homeclaw/agent/runtime.py)（L150）包装实际 Dispatcher；Idempotency Key 固定为 `task_id:action_id`。重复 Claim 时：

- 已有 Evidence：直接反序列化返回；
- 只有未完成 Attempt：复用原 `command_id`，记录 Retry 后再次进入底层 Dispatcher。

所以当前实现保证“不生成新的业务命令身份”，但不能单靠 PostgreSQL 保证“绝不重新 Publish”。如果崩溃窗口发生在 Publish 后、Evidence 前，恢复仍可能重发相同 ID；真正的 Exactly-once Effect 还要求 Redis Claim 或设备网关持久去重。

另外，`DurableActionDispatcher` 只有显式传入 `attempt_store` 才启用，见 [`ProductionRuntime.__init__`](./homeclaw/agent/runtime.py)（L197、L204）。未配置时只有 Bridge 进程内去重，进程重启后无法恢复。

#### 4）Outbox 解决的是事件不丢，不代表设备执行成功

Workflow 到达 COMPLETE 时会把 `workflow.completed` 与最终 Checkpoint 同事务写入 Outbox，见 [`ProductionRuntime._confirm`](./homeclaw/agent/runtime.py)（L425）。Publisher 后续读取 `published_at IS NULL` 的记录，Broker Confirm 后只更新 `published_at`。

这仍然是 At-least-once 事件投递：Publisher 可能在 Broker 已确认、数据库尚未标记时崩溃，恢复后再次发送相同 `message_id`，因此下游 Consumer 也必须去重。更重要的是，Outbox/Pub Confirm 只说明“工作流事件进入消息系统”；设备成功必须已经由 `ExecutionEvidence` 和 Expected State 确认，二者不能互换。

#### 5）Retained State 为什么不能当作实时真相

Retained Message 只表示 Broker 保存的最后一条 Payload。设备可能已经离线、被本地按键改变、重置 Sequence，或者 Retained 根本没有采集时间。因此 Bridge 对 Retained State 至少检查：当前 `command_id`、可解析的 `observed_at`、默认 60 秒新鲜度和 Expected State，见 [`_wait_for_confirmation`](./homeclaw/mqtt/bridge.py)（L253）；已知新鲜的 Availability=offline 会在 Publish 前失败，见 [`_known_offline`](./homeclaw/mqtt/bridge.py)（L220）。

状态缓存再用 Sequence 把更新分为 `APPLIED/DUPLICATE/OUT_OF_ORDER/GAP`，见 [`InMemoryStateCache.apply`](./homeclaw/state/cache.py)（L88）。Gap 不能继续增量合并，必须通过完整 Snapshot 修复；[`StateReconciler`](./homeclaw/state/reconcile.py)（L25）和 [`ReadThroughStateService`](./homeclaw/state/reconcile.py)（L57）提供权威回源与缓存修复抽象。

当前 Bridge 没有在确认失败时自动调用 Authoritative Reader，Reconciler 也没有定时调度器；所以代码证明“可以拒绝旧 retained、可以做对账”，不能说“所有可疑状态都会自动主动查询并恢复”。

#### 6）为什么 QoS 1/2 都不等于业务 Exactly-once

QoS 解决 Client 与 Broker 间的消息交付；它不理解设备是否已经执行过 `toggle_light()`。即使 QoS 2 降低协议层重复，应用重试、网关重启和跨服务恢复仍可能重复产生同一业务动作。

HomeClaw 的业务幂等分四层：

1. **稳定命令身份**：同一 Action 始终复用 `command_id`；
2. **短期去重**：[`RedisIdempotencyStore`](./homeclaw/state/redis_adapter.py)（L140）用 `SET NX` Claim 并缓存 Evidence；
3. **跨崩溃审计**：[`PostgresActionAttemptStore`](./homeclaw/workflow/action_attempts.py)（L28）以唯一 `idempotency_key` 保存 Attempt；
4. **幂等动作语义**：优先暴露 `set_light(on)`、`set_temperature(26)` 等绝对目标，设备网关按 `command_id` 去重。

`retry_call()` 对 `NON_IDEMPOTENT` 强制单次尝试，但当前 MCP Server 重建 Proposal 时没有从 Binding 恢复原始幂等等级。因此 `toggle_light()` 不应直接注册为当前 Binding：更安全的做法是先读取新鲜状态，将它转换为带 Expected State 的 `set_light(on/off)`；若状态陈旧或无法确定，则澄清/拒绝。无法转换时必须扩展 Binding 保存 `NON_IDEMPOTENT`、要求确认并禁止自动重试。

#### 7）当前回归证据及其边界

| 验收范围 | 当前结果 | 证据边界 |
|---|---:|---|
| Workflow 状态机 | 9/9 测试方法通过 | 含预算、等待、异常、CAS、SQLite 重开恢复 |
| 节点崩溃恢复 | 7 个节点位置逐点通过 | 使用合成 Handler，不包含真实外部副作用 |
| PostgreSQL Checkpoint/Outbox | 1/1 SQL 契约测试通过 | Fake DB-API，仅验证同一 Connection Context 与 SQL，不是真实 PostgreSQL 集成 |
| Durable Dispatcher | 3/3 通过 | 新 Claim、未完成复用旧 ID、完成后不重发 |
| Action Attempt Store | 1/1 SQL 契约测试通过 | 验证唯一 Claim 与 Evidence Update |
| MQTT Bridge | 10/10 通过 | 进程内 Transport 场景，不是 Broker 压测 |
| State Cache/Resource | 7/7 通过 | 4 个 Cache + 3 个 Resource/Reconcile 场景 |
| Redis 状态与幂等 | 3/3 相关适配器场景通过 | Sequence CAS、GAP、Evidence Round-trip；使用 Fake Client |

对应测试见 [`test_workflow.py`](./tests/test_workflow.py)（L26）、[`test_postgres_checkpoint.py`](./tests/test_postgres_checkpoint.py)（L47）、[`test_durable_dispatcher.py`](./tests/test_durable_dispatcher.py)（L47）、[`test_action_attempt_store.py`](./tests/test_action_attempt_store.py)（L41）及 [`test_production_adapters.py`](./tests/test_production_adapters.py)（L105、L118、L136）。

目前没有启动真实 PostgreSQL、Redis、Mosquitto 和 Outbox Publisher 进行跨进程 Kill/Restart 测试，也没有重复副作用率、恢复时间、状态确认 P95 或消息投递延迟报告。面试中可以说明一致性协议和确定性回归已经实现，但不能把这些单测换算成“线上 Exactly-once 100%”。

19、接入大量 MCP 工具后，Host 如何通过 Skill Top-K 和 Expert 内 Tool 收缩控制上下文？当前是否实现了 Schema 缓存与有限次数的二次召回？工具持续增长时，模型实际可见的 Schema、Router 召回率和 Prompt Token 分别如何量化？

**参考回答：** 核心不是让 MCP Server 少注册工具，而是把“服务端全量能力”和“本轮模型可见能力”分离。MCP Server 可以维护完整 Tool Catalog，但每轮请求都经过 `Skill 粗门控 → Capability 细收缩 → Planner Schema 注入 → MCP Allowlist 复核`，因此大模型只看到当前任务可能用到的工具，不能直接遍历或调用全量 MQTT 能力。

#### 1）两级稀疏不是只做一次关键词过滤

第一层是 Skill 级门控。[`SkillRouter.route`](./homeclaw/routing/router.py)（L56）先用倒排索引召回候选 Skill，再计算词项相关性、关键词覆盖和 Expert competence，最终只保留 Top-K；Tool 和 Knowledge Resource 都由这些 Skill 的并集产生。公共的 `request_clarification` 作为最小安全工具始终保留，而不是把所有领域工具作为兜底。

第二层是设备能力级收缩。[`ProductionRuntime._route`](./homeclaw/agent/runtime.py)（L256）拿到场景中的候选设备后，调用 [`ToolSpaceContractor.contract`](./homeclaw/routing/contraction.py)（L34），只保留至少一个候选设备真实支持的 Tool。知识锚定先缩小相关设备，Capability Registry 再缩小这些设备的子工具空间，这样被激活的是“任务相关 Skill × 当前设备可执行能力”，而不是一个固定领域工具包。

最后还有两道执行约束：

1. [`LLMProposer.propose`](./homeclaw/agent/proposer.py)（L76）只把 `route.exposed_tools` 对应的 Schema 序列化进 Prompt；
2. [`MCPHostGateway.call`](./homeclaw/mcp_runtime/host.py)（L28）再次检查 `tool_name ∈ allowed_tools`，即使模型凭记忆生成了未披露工具，也会在 MCP 边界被拒绝。

所以“模型没看到”与“模型即使猜到也不能执行”是两套约束，不能只依赖 Prompt 自觉。

#### 2）动态 Top-K 如何兼顾召回与成本

[`AdaptiveTopKPolicy`](./homeclaw/resilience/controls.py)（L195）对简单单意图请求选 Top-1，对包含多动作、顺序关系或视觉指代的请求选 Top-2，硬上限为 Top-3；当剩余 Workflow Token Budget 低于 1000 时强制降为 Top-1。它控制的是 Schema 广度，不直接改变 MCP Server 的注册数量。

离线报告使用 25 条 [`router_gold.jsonl`](./data/eval/router_gold.jsonl) Gold 指令，同一 Registry、同一序列化函数和同一机器得到以下结果，原始数据见 [`router-eval-2026-11-09.json`](./reports/router-eval-2026-11-09.json)（L1）：

| 路由策略 | Recall@K | 多标签完整覆盖率 | 平均可见 Schema | 相对全量 2406 Bytes 的收缩 | 路由 P50/P95 |
|---|---:|---:|---:|---:|---:|
| Top-1 | 86% | 72% | 727.12 Bytes | 69.8% | 0.046/0.087 ms |
| Top-2 | 100% | 100% | 928.72 Bytes | 61.4% | 0.051/0.086 ms |

这个表体现了真正的取舍：Top-1 更省上下文，但会丢失多 Skill 指令；当前 Gold 集上 Top-2 才达到完整覆盖。Schema Bytes 是与模型供应商无关的可复现载荷指标，不能机械换算成 Token，因为 GPT、Gemini 等 tokenizer 不同。真实 Prompt Token 应读取在线模型返回的 `prompt_tokens`，仓库已在 [`ProposalResult`](./homeclaw/agent/proposer.py)（L22）和 [`StrategyObservation`](./homeclaw/eval/strategy_benchmark.py)（L32）保留该指标，但尚未生成四策略在线 Token 报告。

#### 3）工具规模增长时，为什么上下文不随全量工具线性增长

[`evaluate_router.py`](./scripts/evaluate_router.py)（L100）把 Registry 合成扩展到 100、1000、5000 个 Skill；5000 Skill/5011 Tool 时，离线路由 P50/P95 为 0.331/0.372 ms，约 2976 QPS，索引峰值约 16.3 MB。另一个测试把候选设备扩到 5000 台，能力收缩后仍只留下 3 个 Tool，收缩 P95 为 1.38 ms，见同脚本的 [`device_scale_benchmark`](./scripts/evaluate_router.py)（L150）。

因此当前复杂度可以拆成：

- Router 计算量随命中词项对应的候选 Skill 增长，而不是每次扫描全部 Tool Schema；
- Prompt 大小主要随“被选 Skill 的 Tool 并集”增长；
- 设备数量影响 Capability 收缩耗时，但不会直接把每台设备的全部 Schema 注入模型。

这些是单进程 CPU 离线结果，不包含网络、数据库、在线模型或 MCP 序列化开销。

#### 4）当前 Schema 缓存和二次召回的真实边界

当前 [`SkillRegistry`](./homeclaw/routing/registry.py)（L12）在进程内持有 Tool/Skill 定义，可视为启动期静态缓存；但 [`MCPHostGateway.exposed_tools`](./homeclaw/mcp_runtime/host.py)（L24）每次仍调用 Client 的 `list_tools()` 后过滤，没有实现带 `registry_version/ETag/TTL` 的 MCP Schema Cache。更重要的是，Planner 当前直接从本地 Skill Registry 取 Schema，而不是从 MCP Discovery 结果构建，两者若独立升级存在版本漂移风险。

“有限二次召回”也没有在当前 Runtime 中完成。[`_replan`](./homeclaw/agent/runtime.py)（L411）只是带着 Verifier Feedback 回到 PLAN，继续复用原来的 Skill/Tool 子集；它不会重新进入 ROUTE，也不会自动把 Top-1 扩为 Top-2。现有 `max_replans=2` 只限制重规划轮数，不等价于二次路由召回。

生产化时应把这两项补成明确协议：以 Registry Version 为缓存键；Tool Catalog 变更时失效；只有错误属于 `missing_capability/route_miss` 且仍有 Re-Plan Budget 时，才允许 `Top-K + 1` 重路由一次；权限、参数非法和业务拒绝不得通过扩大工具集绕过。面试中可以说明双层收缩和离线规模评测已经实现，但不能说 MCP Schema 热更新缓存或二次召回已经落地。

---

20、当 LLM、Grounder、MCP 或 MQTT 调用超时或服务中断时，系统如何设置分层超时、有限重试、退避、熔断、并发上限及全局预算？当前各阈值实际落在哪一层，哪些错误可重试，故障注入又能证明到什么程度？

**参考回答：** 防死循环不能只设置一个 HTTP Timeout，而要形成从外到内的约束：`Workflow Deadline/Step/Token/Re-Plan Budget > 组件调用超时 > 排队超时 > 有限重试 > 熔断`。外层保证任务最终离开运行态，内层保证单个依赖不会长期占住资源；重试还必须受动作幂等等级约束。

#### 1）当前默认阈值和实际接线情况

| 层级 | 当前默认值 | 已实现语义 | 当前边界 |
|---|---:|---|---|
| Workflow | 120 s、24 Step、2 次 Re-Plan、16000 Token | 每个节点前检查 Deadline/Step/Token，超限转明确失败终态 | Deadline 只在节点边界检查，尚未把“剩余时间”逐层传给依赖或主动取消在途请求 |
| 在线 LLM Client | 120 s、单次最大输出 1024 Token | HTTP Client 使用 Provider 超时；Planner 记录 Prompt/Completion Token | [`LLMConfig.max_iters`](./homeclaw/config.py)（L29）属于旧 Coordinator 循环，Production Runtime 主要由 Workflow Budget 限轮 |
| Planner 容量层 | 排队最多 5 s | QPS Token Bucket、并发 Gate、在途 Token Pool，任一不足即 Fail-closed | 具体 QPS、并发和 Token Pool 容量由部署者注入，没有仓库级生产默认值 |
| Grounder | 单请求 10 s、Batch 30 s、Health 2 s、排队 5 s | 超时/服务错误返回“保持歧义”，不会猜设备 | 没有 Grounder 专用重试和熔断接线；Batch 最大 16 |
| MCP SDK Adapter | 30 s | `asyncio.wait_for` 包住 Initialize/List/Call/Resource/Prompt | 只有 Timeout；Host Gateway 尚无 MCP Retry/Circuit Breaker |
| MQTT Tool | 状态确认 5 s | Publish 有有限重试与熔断，等待不到匹配状态则 `UNKNOWN` | 5 s 是 Binding 默认，可按设备覆盖；不能因为超时就断言设备未执行 |

Workflow 默认预算见 [`ExecutionBudget`](./homeclaw/workflow/state.py)（L32），节点边界检查见 [`WorkflowHost._run`](./homeclaw/workflow/engine.py)（L64）；Grounder 超时见 [`GrounderClient`](./homeclaw/grounding/client.py)（L37），MCP 超时见 [`AsyncMCPClientAdapter`](./homeclaw/mcp_runtime/sdk_adapter.py)（L9），MQTT Binding 默认值见 [`MqttToolBinding`](./homeclaw/mcp_runtime/home_server.py)（L13）。

#### 2）Retry 与 Circuit Breaker 为什么必须识别错误类型

[`RetryPolicy`](./homeclaw/resilience/controls.py)（L20）的默认策略是最多 3 次，指数退避从 0.1 s 开始、封顶 2 s，并加入 ±10% Jitter。`retry_call()` 默认只捕获 `TimeoutError/ConnectionError`：

- 可重试：网络中断、连接拒绝、Provider 5xx/临时不可用、Broker 临时拒绝；
- 不应盲重试：JSON/Schema 错误、HTTP 400/404/409/422、鉴权失败、策略拒绝、设备业务拒绝；
- 非幂等动作：无论策略配置几次，`NON_IDEMPOTENT` 都强制为 1 次；
- 带稳定 Idempotency Key 的绝对状态动作：允许重试，但每次必须复用原 `command_id`。

[`CircuitBreaker`](./homeclaw/resilience/controls.py)（L70）默认累计 5 次失败后 OPEN，30 s 后允许 HALF_OPEN 探测；探测成功回 CLOSED，失败重新 OPEN。Planner 的 [`ResilientProposer`](./homeclaw/agent/capacity.py)（L94）将 Transport Retry 和 Circuit 组合，MQTT Bridge 也在每次 Publish 外包熔断，见 [`MqttCommandBridge.execute`](./homeclaw/mqtt/bridge.py)（L99）。

一个容易被忽视的细节是：Circuit 统计的是跨调用连续失败，而不是“某次请求失败率达到多少”。当前实现没有滑动窗口失败率，也没有按 Provider、租户或 Tool 隔离的熔断桶；如果所有设备共用同一 Bridge 实例，一个故障域可能扩大影响范围。

#### 3）并发与 Token Budget 如何阻止排队雪崩

[`CapacityControlledProposer`](./homeclaw/agent/capacity.py)（L17）按顺序执行：QPS 令牌检查 → 预留固定数量的在途 Token → 等待 Semaphore → 调用 LLM → 释放 Token。排队超过 5 s 转为可重试的 `TIMEOUT`，Token Pool 不足转为 `BUDGET_EXHAUSTED`，不会无限排队。

Grounder 使用独立的 [`CapacityControlledGrounderClient`](./homeclaw/grounding/capacity.py)（L14）；Batch N 会按 N 个 Rate Token 计费，再竞争一个 Grounder 并发槽，避免把批量请求伪装成一次免费调用。Planner 与 Grounder 分池的意义是：视觉流量激增时不能耗尽主 Agent 的所有并发配额。

这些 Wrapper 已有实现，但 [`ProductionRuntime.__init__`](./homeclaw/agent/runtime.py)（L184）不会自动创建它们，必须在 Composition Root 中先包装 Proposer/Grounder 再注入。未包装时，只有 Workflow 总预算和底层 Client Timeout 生效。

#### 4）失败如何结束，而不是在 Agent 内自旋

Workflow 对不可重试 `DomainError` 直接 FAIL；对可重试错误将任务保存为 WAITING 并返回调用方，见 [`WorkflowHost._run`](./homeclaw/workflow/engine.py)（L118）。它不会在同一请求中无限 while-retry。后续恢复由外部调度器再次调用 `resume(task_id)`，同时仍受原 Deadline 和 Revision 约束。

MQTT 的 Publish 成功但状态确认超时会返回 `UNKNOWN`，而不是继续让 LLM猜测或不断重发；迟到状态可用同一 `command_id` 将 UNKNOWN 升级为成功，见 [`MqttCommandBridge.execute`](./homeclaw/mqtt/bridge.py)（L108）。这也是“控制死循环”和“防 False Done”必须一起设计的原因。

#### 5）当前故障回归证据不能替代真实恢复率

| 回归范围 | 当前结果 | 能证明什么 | 不能证明什么 |
|---|---:|---|---|
| Retry/Circuit/限流/预算原语 | 5/5 | 幂等退避、非幂等不重试、半开恢复、QPS/Token/并发拒绝 | 多实例一致熔断、真实时钟下恢复率 |
| Planner/Grounder Capacity Wrapper | 3/3 | QPS、在途 Token、Batch 成本和 Transport Retry 分支 | 在线 Provider/GPU 的最大稳定吞吐 |
| MCP 超时 | 1/1 | Async Session 超时会被终止 | MCP Server 重启后的恢复时间 |
| MQTT Bridge | 10/10 | PUBACK 非成功、离线、迟到状态、重试复用 ID 等 | 真实 Broker 重连、重复副作用率 |
| Workflow | 9/9 测试方法 | 预算终止、WAITING/Resume、节点 Checkpoint 恢复 | 跨进程调度延迟和真实依赖故障恢复率 |

对应测试见 [`test_resilience.py`](./tests/test_resilience.py)（L31）、[`test_capacity_wrappers.py`](./tests/test_capacity_wrappers.py)（L57）、[`test_production_adapters.py`](./tests/test_production_adapters.py)（L188）、[`test_mqtt_bridge.py`](./tests/test_mqtt_bridge.py)（L33）和 [`test_workflow.py`](./tests/test_workflow.py)（L26）。

因此可以回答“所有受控场景都进入预期分支”，但不能把单测写成真实故障注入的 100% 恢复率、0% 重复执行率或 120 s 最大耗时。仓库已经在 [`benchmark-protocol.md`](./docs/benchmark-protocol.md)（L67）定义 Broker 拒绝、ACK 迟到、乱序/丢失、Redis 丢失、节点崩溃和 MCP 中断矩阵；真实数值必须在固定外部环境运行后再填。

---

21、设备命令写入后，系统如何验证 Read-your-write 一致性，而不是只相信发布结果？缓存过期、Diff 丢失/乱序、设备离线和 Retained State 过期如何处理？当前缓存命中率、陈旧读比例、状态确认 P50/P95、UNKNOWN 比例和对账恢复时间是否已有可信实测？

**参考回答：** Read-your-write 的业务含义不是“刚写进 Redis 就能读到”，而是“对某个 `command_id` 发出的目标状态，后续读到的设备证据既属于这次命令，又满足 `expected_state`，并且版本和时间仍可信”。Broker PUBACK、缓存命中和设备成功是三个不同事件。

#### 1）写路径：以设备状态证据闭环

Host 为每个 Action 生成稳定 `command_id`，Proposal 同时携带 `expected_state`。MQTT Bridge 订阅状态后再发布命令，并等待状态事件；只有状态满足递归的 [`matches_expected_state`](./homeclaw/state/cache.py)（L63）才生成 `SUCCEEDED` Evidence。发布已接受但超时则为 `UNKNOWN`，业务拒绝则为 `REJECTED`，对应实现见 [`_wait_for_confirmation`](./homeclaw/mqtt/bridge.py)（L253）。

Read-your-write 因而由下面的合取条件决定：

```text
command correlation ∧ expected-state match ∧ freshness ∧ acceptable sequence
```

它不等价于“Redis 有值”，也不等价于“MQTT QoS 1 已送达 Broker”。

#### 2）读路径：Fresh Cache、Read-through 和 Reconcile 分工

[`InMemoryStateCache.apply`](./homeclaw/state/cache.py)（L88）按单设备单调 Sequence 处理 State Diff：

| 输入关系 | 结果 | 处理 |
|---|---|---|
| `seq == current` | `DUPLICATE` | 丢弃重复事件 |
| `seq < current` | `OUT_OF_ORDER` | 拒绝乱序旧状态 |
| `seq > current + 1` 且不是全量快照 | `GAP` | 停止增量合并，要求权威快照 |
| 连续 Diff 或更新的全量快照 | `APPLIED` | 合并或整体替换，并刷新 TTL |

Redis 版本在 [`RedisStateCache.apply`](./homeclaw/state/redis_adapter.py)（L77）用 Lua CAS 将“版本比较、写 Hash、设置 TTL”放在一次原子操作中，避免多个消费者先读后写互相覆盖。

读操作由 [`ReadThroughStateService.read`](./homeclaw/state/reconcile.py)（L70）完成：Fresh Cache 命中直接返回；Miss/Stale 时读取权威设备网关并写入 Full Snapshot；只有调用方明确设置 `allow_stale_on_error=True` 时，权威源故障才允许降级返回旧值，并单独记录 `state.stale_fallback`。因此陈旧数据不是默认成功路径。

周期对账由 [`StateReconciler.reconcile`](./homeclaw/state/reconcile.py)（L30）比较缓存与权威源的 Sequence 和字段差异，发现差异时失效旧缓存并写入完整快照。它解决的是“事件流永久漏了一条”，不是每次读请求都同步扫描所有设备。

#### 3）Retained、离线和迟到状态如何处理

- 已知且新鲜的 Availability=offline：Publish 前失败；
- Retained State：必须包含可解析的 `observed_at`、不超过默认 60 s，并关联当前 `command_id`，否则不能确认新命令；
- 错误 `command_id`：忽略，继续等待；
- 状态迟到：第一次返回 UNKNOWN，后续使用相同 ID 查询时只等待证据，不重复 Publish；
- 缓存过期：普通读视为 Miss，回源修复；不能因为旧快照曾匹配目标就判成功。

代码入口分别见 [`_known_offline`](./homeclaw/mqtt/bridge.py)（L220）、[`_wait_for_confirmation`](./homeclaw/mqtt/bridge.py)（L253）和 [`ReadThroughStateService`](./homeclaw/state/reconcile.py)（L57）。

#### 4）当前仍有两个会削弱一致性的实现缺口

第一，Bridge 目前允许“不带 `command_id` 的非 Retained 状态”在 Expected State 匹配时确认；这适用于部分只上报状态、不回传命令 ID 的旧设备，但严格 Read-your-write 下存在把外部并发变化误认作本次执行的风险。生产上应按设备协议能力分级：支持 Correlation 的设备必须强校验 ID；不支持的设备只能使用“Publish 后时间窗 + 单调 Sequence + 无并发写 Lease”的弱确认策略，并在 Evidence 中标记置信等级。

第二，[`MqttCommandBridge._wait_for_confirmation`](./homeclaw/mqtt/bridge.py)（L315）调用 `state_cache.apply()` 后没有检查返回的 `OUT_OF_ORDER/GAP`，仍会生成成功 Evidence。也就是说，缓存组件能识别异常版本，但 Bridge 尚未把识别结果纳入成功判定。修复方向是：只有 `APPLIED/DUPLICATE-of-same-command` 可以确认；`GAP` 进入 Authoritative Read，`OUT_OF_ORDER` 继续等待或返回 UNKNOWN。

此外，Reconciler 与 Read-through 目前是可调用抽象，尚未由 Runtime 自动调度；Redis 适配器也没有直接接入 `StateReconciler` 的类型边界。面试中不能说“GAP 已自动触发全量查询”或“后台对账任务已经在线运行”。

#### 5）指标如何定义，当前数据到哪一步

[`summarize_state_consistency`](./homeclaw/eval/state_consistency.py)（L36）已经定义统一聚合口径：

| 指标 | 计算口径 | 当前可信结果 |
|---|---|---|
| Cache Hit Rate | Fresh Cache Hit / 全部读请求 | 尚无真实 Redis 流量报告 |
| Stale Read Rate | 返回 Stale Snapshot / 全部读请求 | 尚无真实流量报告 |
| Read-your-write Rate | 命令样本中读到匹配目标证据的比例 | 尚无真实设备报告 |
| Confirmation P50/P95 | 从 Publish 到终态 Evidence 的时间 | 尚无真实 MQTT 报告 |
| UNKNOWN Rate | 确认窗口内无可信终态 / 命令总数 | 尚未接入该 Summary 字段，需在外部报告补充 |
| Reconciliation Difference Rate | 对账发现缓存与权威源不同的比例 | 尚无周期对账报告 |
| Reconciliation P50/P95 | 回源、比较并修复缓存的耗时 | 尚无真实设备/Redis 报告 |

当前确定性回归为：4 个 Cache 场景、3 个 Resource/Read-through/Reconcile 场景、2 个 Fake Redis Sequence 场景和 10 个 MQTT Bridge 场景全部通过；另有 1 个 Summary 数学口径测试。测试见 [`test_state_cache.py`](./tests/test_state_cache.py)（L16）、[`test_state_resources.py`](./tests/test_state_resources.py)（L38）、[`test_production_adapters.py`](./tests/test_production_adapters.py)（L105）、[`test_mqtt_bridge.py`](./tests/test_mqtt_bridge.py)（L33）及 [`test_state_consistency_metrics.py`](./tests/test_state_consistency_metrics.py)（L9）。

这些测试多数只有单设备、少量手工事件、进程内 Transport 或 Fake Redis，没有固定事件速率和长时间观察窗口。因此可以量化为 19/19 个一致性行为场景通过，不能写成“缓存命中率 99%”“Read-your-write 100%”或某个虚构 P95。真实验收至少要记录设备数、事件/秒、读写比、观察时长、Broker/Redis 版本和故障注入比例。

---

22、Skill-MoE 激活多个 Expert 时是否真的会并行调用多个 LLM？系统如何控制在线 Planner 的 QPS、在途 Token、并发和成本，以及 Grounder 的 Batch、队列与 GPU 显存？当前最大稳定 QPS、容量拐点和推荐并发上限有何实测依据？

**参考回答：** 当前 HomeClaw 的“多 Expert 激活”是路由与上下文层面的稀疏组合，不是每个 Expert 各起一个在线 LLM。Top-K Skill 的 Tool/Resource 被合并后，只调用一次共享 [`LLMProposer`](./homeclaw/agent/proposer.py)（L63）；只有 Verifier/执行反馈触发 Re-Plan 时才会再次调用。因此多 Skill 主要增加 Prompt Schema，而不是把在线模型 QPS 直接乘以 K。

#### 1）一次任务实际会产生多少在线模型调用

正常链路为 `Route once → optional Grounder once → Planner once → Verify → Execute`。当前 Re-Plan 仍复用原 Route，默认最多 2 次，所以单任务 Planner 理论上最多是 1 次初始规划 + 2 次重规划；视觉 Grounder 只有命中消歧 Skill 且知识锚定后仍有多个候选设备时才调用，若只剩 1 个候选，[`DeviceDisambiguationService.resolve`](./homeclaw/grounding/service.py)（L52）直接确定性返回，节省一次 GPU 推理。

这比“Top-2 就并发请求两个 Planner”更适合工程落地：Expert 负责收缩知识与工具边界，在线大模型负责在收缩后的联合空间规划，避免多模型答案合并、冲突仲裁和 QPS 翻倍。

#### 2）Planner 四道容量门

[`CapacityControlledProposer`](./homeclaw/agent/capacity.py)（L17）提供四个正交控制面：

1. **QPS Token Bucket**：按持续补充速率和突发容量拒绝过量请求；
2. **Concurrency Semaphore**：限制同时占用在线模型连接的任务数；
3. **In-flight Token Pool**：调用前预留 `reservation_tokens`，避免大量长 Prompt 同时进入 Provider；
4. **Queue Timeout**：默认最多等待 5 s，超时返回可观察的容量错误，而不是让请求堆积到 Workflow Deadline。

Planner 返回的 Prompt/Completion Token 会进入 [`ProposalResult`](./homeclaw/agent/proposer.py)（L22）和 Workflow `tokens_used`；四策略实验再用 [`BenchmarkConfig`](./homeclaw/eval/strategy_benchmark.py)（L49）中的输入/输出单价计算每任务模型成本。成本计算使用 Provider 实际 Token，不用 Schema Bytes 冒充 Token。

当前 Token Pool 预留的是固定估算值，调用结束后也按同一数值释放，尚未根据实际 Prompt 长度动态预估、按真实 Usage 对账或设置租户级配额；Rate Limiter 也是单进程内存实现，不是 Redis/网关级分布式限流。这些是从“代码有控制原语”走向“多副本生产容量治理”仍需补齐的部分。

#### 3）Grounder 的并发和 Batch 实际语义

Grounder 使用独立 [`CapacityControlledGrounderClient`](./homeclaw/grounding/capacity.py)（L14），单请求消耗 1 个 Rate Token，Batch N 消耗 N 个 Token，并通过单独的 Semaphore 与 5 s Queue Timeout 隔离 GPU 流量。HTTP Client 把 Batch 限制为 1～16，见 [`HttpGrounderClient.ground_batch`](./homeclaw/grounding/client.py)（L75）。

部署侧 [`compose.yaml`](./deploy/grounder/compose.yaml)（L16）申请 1 张 GPU，[`Dockerfile`](./deploy/grounder/Dockerfile)（L21）固定 1 个 Uvicorn Worker；模型推理又受 [`Engine.lock`](./deploy/grounder/app.py)（L73、L128）保护，避免多个线程同时 `generate()` 抢显存。

但这里要准确描述：当前 `/v1/ground:batch` 是在一个 HTTP 请求里逐条循环 `engine.ground()`，见 [`ground_batch`](./deploy/grounder/app.py)（L223），并不是真正把多张图组成 Tensor Batch，也不是动态微批。因此它降低 HTTP 往返，却没有证明 GPU 吞吐随 Batch 增长；同一进程内实际生成仍串行。代码也没有显存水位采样、OOM 降级、队列长度 Gauge 或跨请求 Dynamic Batcher。

#### 4）当前可复现容量数值

| 组件/规模 | 当前结果 | 实验性质 |
|---|---:|---|
| Router，25 条 Gold，Top-2 | P50/P95=0.051/0.086 ms | 本机单进程 CPU 离线 |
| Router，5000 Skill/5011 Tool | P50/P95=0.331/0.372 ms，约 2976 QPS | 100 个合成查询，不含在线模型 |
| Tool 收缩，5000 候选设备 | P50/P95=1.301/1.378 ms，约 758 QPS | 内存 Registry，不含 MySQL/网络 |
| Planner Capacity Wrapper | 3/3 相关场景通过 | 只证明拒绝、预留和重试分支 |
| 在线 GPT/Gemini | 无最大稳定 QPS/Token 成本报告 | 尚未连接固定模型与账号配额压测 |
| Qwen3-VL Grounder | 无吞吐、GPU 利用率和峰值显存报告 | 尚未运行固定 GPU/镜像容量实验 |

前三项原始数值见 [`router-eval-2026-11-09.json`](./reports/router-eval-2026-11-09.json)（L1），生成脚本见 [`evaluate_router.py`](./scripts/evaluate_router.py)（L60）；容量 Wrapper 回归见 [`test_capacity_wrappers.py`](./tests/test_capacity_wrappers.py)（L57）。2976 QPS 只能回答 Router CPU 检索能力，不能写成“整个 Agent 2976 QPS”。

#### 5）如何得到可写入简历的容量拐点

仓库的 [`benchmark-protocol.md`](./docs/benchmark-protocol.md)（L95）要求按并发 1/2/4/8/16/32、Top-K 1/2/3、Grounder Batch 1/2/4/8/16 逐级升压。每个点固定 Git Commit、数据集哈希、模型 Revision、Prompt/Registry Version、Token Budget、硬件与网络区域，并记录：

- 成功率、限流率、超时率和熔断次数；
- QPS、端到端及 Queue P50/P95；
- Prompt/Completion Token、单任务成本、Re-Plan 次数；
- GPU Utilization、Peak VRAM、OOM 和 Grounder Batch Throughput。

[`load_test_http.py`](./scripts/load_test_http.py)（L53）可以生成并发 HTTP 报告，但 GPU 指标需要同时采集 DCGM 或 `nvidia-smi dmon`。容量拐点定义为继续加压后吞吐不再近似增长，同时 P95/错误率/显存任一越过 SLO 的前一个稳定点。由于真实报告尚不存在，当前不能给出在线 LLM 或 GPU 的推荐并发上限；硬填一个数字反而经不起机器型号、Provider 配额和 Prompt 长度变化。

---

23、如何定位一条 Agent 请求的端到端性能瓶颈？`trace_id/request_id/task_id/command_id` 当前如何贯穿 Router、Grounder、Planner、Verifier、MCP、MQTT 和状态确认？各组件 P50/P95/P99、耗时占比、错误率、重试与吞吐量已经实现到什么程度，现阶段能否断言第一、第二瓶颈？

**参考回答：** 性能定位必须把“一次用户请求”“一个可恢复 Workflow”和“一个设备命令”分成不同关联粒度，再用同一 Trace 串起计算耗时、排队耗时和外部等待耗时。只看总耗时无法区分是 LLM 慢、GPU 排队、MCP 传输慢，还是设备状态迟迟未回报。

#### 1）四类 ID 的职责和生命周期

[`CorrelationIds`](./homeclaw/domain/models.py)（L87）在入口一次性创建 `trace_id/request_id/task_id`：

| ID | 粒度 | 主要用途 |
|---|---|---|
| `trace_id` | 一次端到端调用链 | 关联所有 Span 与跨组件耗时 |
| `request_id` | 一次 API/用户请求 | 去重入口请求、定位调用方重试 |
| `task_id` | 一个可 Checkpoint/Resume 的 Workflow | 查询 PostgreSQL State、Checkpoint、Outbox |
| `command_id` | 一个设备原子动作 | MQTT 幂等、迟到状态匹配、Action Attempt 恢复 |

`WorkflowState` 持久化前三个 ID；进入 Execute 时 [`for_command()`](./homeclaw/domain/models.py)（L100）为每个 Action 派生 `command_id`。同一对象随后传入 MCP Gateway、MQTT Bridge 和 Execution Evidence，MQTT Payload 至少携带 `command_id`，因此进程内链路和设备动作可以关联。

当前还不是完整的分布式 Trace Context：自定义 `trace_id` 只是 OTel Span Attribute，并未映射为 W3C `traceparent`；Async MCP Adapter 的方法签名没有传 Correlation IDs；MQTT Payload 也没有携带 `trace_id/request_id/task_id`，只有 `command_id/action_id/device_id`。所以现在能证明单进程链路贯通，不能声称跨独立 MCP Server、Broker Consumer 和设备网关仍保持同一 OTel Parent/Child Trace。

#### 2）现有 Span 和指标覆盖

| 阶段 | Span/Metric | 关键属性 | 代码 |
|---|---|---|---|
| Agent 总入口 | `agent.request` | status、steps、tokens、输入长度 | [`ProductionRuntime.execute`](./homeclaw/agent/runtime.py)（L232） |
| Workflow 节点 | `workflow.<node>` | node、step、status/error | [`WorkflowHost._run`](./homeclaw/workflow/engine.py)（L110） |
| Router | `router.retrieve` | Top-K、候选/选中 Skill、暴露 Tool、fallback | [`SkillRouter.route`](./homeclaw/routing/router.py)（L56） |
| Grounder | `grounder.infer`、`grounder.queue_ms` | candidates、model、ambiguous、model latency | [`DeviceDisambiguationService.resolve`](./homeclaw/grounding/service.py)（L68） |
| Planner | `planner.generate`、`planner.queue_ms` | Skill/Tool 数、模型、Prompt/Completion Token | [`LLMProposer.propose`](./homeclaw/agent/proposer.py)（L112） |
| Instance Binder | `binder.resolve` | 候选和绑定结果 | [`InstanceBinder.bind`](./homeclaw/agent/binder.py)（L36） |
| Verifier | `verifier.check` | Tool、accepted、issue count | [`ActionVerifier.verify`](./homeclaw/verification/verifier.py)（L42） |
| MCP | `mcp.call` | Tool、Policy Version、Principal 状态 | [`MCPHostGateway.call`](./homeclaw/mcp_runtime/host.py)（L28） |
| MQTT | `mqtt.publish`、`mqtt.wait_state` | Tool、QoS、确认窗口、是否确认 | [`MqttCommandBridge.execute`](./homeclaw/mqtt/bridge.py)（L155） |
| 状态读 | `state.cache`、`state.stale_fallback` | hit/stale/miss | [`ReadThroughStateService.read`](./homeclaw/state/reconcile.py)（L70） |

排队时间与服务时间分开记录很重要：`planner.queue_ms` 高说明本地并发不足或 Provider 配额受限；`planner.generate` 高而 Queue 低说明模型本身慢；`mqtt.wait_state` 高说明设备/网关确认构成长尾，而不是 MCP Function Calling 慢。

#### 3）P50/P95 如何聚合，当前还缺什么

[`summarize_spans`](./homeclaw/eval/performance.py)（L32）按 Span Name 聚合 `count/error_count/error_rate/average/P50/P95`；[`OpenTelemetryAdapter`](./homeclaw/observability/otel_adapter.py)（L13）可把 Span、Counter 和 Histogram 接到部署环境的 OTel Provider。In-memory Sink 用于确定性测试，线程安全地保存 Span 与观测值，见 [`InMemoryTelemetry`](./homeclaw/observability/telemetry.py)（L106）。

但当前本地聚合器没有 P99、Timeout Rate、Retry Count、Throughput 和跨 Span Critical-path 占比；这些需要在 Collector/Prometheus/Tempo 等后端按固定窗口计算。仓库也没有配置 OTel Exporter、Collector 或 Dashboard，Adapter 使用的是进程已有的全局 Provider。

还有一个实现细节：组件在 Span 打开后追加的 `planner.prompt_tokens` 等属性会保存在 `SpanRecord`，但当前 OTel Adapter 没有在退出前把新增属性再次 `set_attributes()` 到真实 OTel Span；InMemory 测试能看到，Exporter 未必能看到。生产化前应同步动态属性，并给 Counter/Histogram 明确单位和低基数标签。

#### 4）脱敏与高基数控制不能只做字符串替换

[`redact_attributes`](./homeclaw/observability/telemetry.py)（L26）会按 Key 名屏蔽 API Key、Authorization、Cookie、Password、Secret、Token；Agent 入口只记录输入长度，不记录原 Prompt 或图像。

当前仍存在 `verifier.device_id` 这类高基数属性，而且脱敏是浅层 Key 匹配，不会检查嵌套对象和敏感 Value。生产侧应把 Home/User/Device ID 从 Metric Label 中删除或做稳定哈希，只在受控 Trace/Log 中保存；Prompt、用户画像、原始图像和完整 MQTT Payload 不进入 Span。否则设备规模增长会导致指标时序爆炸，也会扩大隐私面。

#### 5）当前性能数据能回答什么

| 范围 | P50/P95 或结果 | 样本与边界 |
|---|---:|---|
| Router Top-2 | 0.051/0.086 ms | 25 条 Gold，本机单进程 CPU |
| Router 5000 Skill | 0.331/0.372 ms，约 2976 QPS | 100 条合成查询；不含网络/LLM |
| 5000 候选设备 Tool 收缩 | 1.301/1.378 ms | 20 次内存 Registry 测量 |
| Span 汇总与错误率 | 2/2 测试通过 | 合成 Span + Router/MQTT ID 传播 |
| Telemetry 基础语义 | 4/4 测试通过 | Duration、Error、脱敏、Metric 分组 |
| 完整代码回归 | 123/123 单测通过 | 正确性回归，不是性能压测 |
| 在线 Planner/GPU/MCP/MQTT/端到端 | 无可信 P50/P95/P99 | 未启动固定外部服务和 Collector |

Router 原始报告见 [`router-eval-2026-11-09.json`](./reports/router-eval-2026-11-09.json)（L1）；观测测试见 [`test_performance_observability.py`](./tests/test_performance_observability.py)（L13）、[`test_telemetry.py`](./tests/test_telemetry.py)（L9）以及端到端 Trace 断言 [`test_production_runtime.py`](./tests/test_production_runtime.py)（L117）。

#### 6）如何确定第一和第二瓶颈，而不是凭经验猜

固定同一 Commit、模型 Revision、数据集哈希、Prompt/Registry Version、Top-K、Token/Step Budget、硬件和并发梯度后，对每个 Trace 计算：

1. 各 Span 的 Inclusive/Exclusive Duration 及其占端到端 Critical Path 的比例；
2. Queue Time 与 Service Time 的比例；
3. 成功/超时/限流/重试分别分桶的 P50/P95/P99；
4. 吞吐提升与并发提升的斜率，以及错误率和资源利用率；
5. 按“纯文本、视觉消歧、单设备、长程多动作”任务类型分层，避免平均值掩盖长尾。

如果 `planner.generate` 占比最高，它才是第一计算瓶颈；如果 `mqtt.wait_state` 的 P95/P99 最高但均值不高，它是尾延迟瓶颈；如果 `queue_ms` 随并发陡增而服务时间稳定，则容量门或下游配额才是真瓶颈。当前只能把在线 LLM/Grounder 和 MQTT 状态确认列为重点怀疑对象，不能在没有同一 Trace 的真实报告时宣布第一、第二瓶颈。复现实验必须遵循 [`benchmark-protocol.md`](./docs/benchmark-protocol.md)（L5）记录的可比性元数据，并把原始 Observations 与汇总结果一并保留。

