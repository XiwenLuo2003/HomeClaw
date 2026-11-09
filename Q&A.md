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

**参考回答：** 我把主链路实现为显式状态机：`Receive → Route →（按需 Ground）→ Plan → Verify → Execute → Confirm → Complete`。如果 Router 命中设备消歧 Skill，先进入 Ground；Grounder 仍无法唯一绑定实例就直接 Reject。Verifier 或状态确认失败时进入 Re-Plan，最多再规划 2 次，超过预算进入 Fail，而不是继续循环。

状态由 `WorkflowState` 统一承载，包含当前节点、已完成节点、revision、Token/Step 消耗、错误和四级关联 ID。`WorkflowHost` 为每个节点注册强类型 Handler，每完成一个节点就把 Checkpoint 与 Outbox 放在同一事务提交。默认预算是 24 个节点步、2 次 Re-Plan、16K Token 和 120 秒全局 Deadline；当前已经用“在每个运行节点后模拟崩溃”的测试验证可恢复性。

2、在线 Planner、Skill Router、Host 和 Qwen3-VL-4B Grounder 分别部署在哪里？为什么 Grounder 只作为设备消歧 Skill 内部的工具，而不是 Agent 主模型？组件之间采用同步调用、消息队列还是 PostgreSQL Blackboard 传递信息，各自保存什么状态？

**参考回答：** Host、Router、Verifier 和 MCP Client 都是 CPU 服务，首期可以作为模块化单体部署；Planner 调用 GPT、Gemini 等在线大模型；Qwen3-VL-4B Grounder 独立部署在单 GPU Docker 服务中；MCP–MQTT Bridge 更靠近家庭网关或 Broker。Grounder 只解决“图里那盏灯是哪台物理设备”，不承担通用规划，因此不会把 4B 模型误包装成整个 Agent 的主模型。

强一致控制链路优先使用同步强类型调用，跨模块只传领域对象；Workflow、Checkpoint、动作尝试和 Outbox 以 PostgreSQL 作为 Blackboard/真相源。服务真正拆分后，RabbitMQ 只传递异步事件，使用带 `trace_id/request_id/task_id/message_id` 的 Envelope、Quorum Queue、手工 ACK 和 DLQ；它不承载当前任务真相，也不替代 PostgreSQL。

### 二、记忆和上下文

3、HomeClaw 的短期上下文、长期用户记忆以及日/月摘要分别如何实现？MongoDB 中的偏好事实如何建模版本、来源、作用域和有效期，又如何解决显式偏好、推断偏好、临时偏好及多用户偏好之间的冲突？

**参考回答：** 短期上下文保存在当前 `WorkflowState` 中，只携带完成本次任务所需的路由、候选设备、Verifier 反馈和执行证据；可恢复任务状态进入 PostgreSQL Checkpoint。长期偏好与日/月摘要进入 MongoDB，摘要记录源事件 ID 和版本，相同事件集合重复物化不会产生新版本。

偏好采用 append-only temporal fact，而不是覆盖一个 JSON：每条事实都有 `user_id/key/source/scope/confidence/valid_at/invalid_at/expires_at/supersedes`。冲突顺序是显式声明高于系统规则、高于行为推断；匹配当前查询时设备级高于房间级、房间级高于情境级、情境级高于全局；同优先级取更新且有效的事实。临时偏好到期自动失效，撤销只填写 `invalid_at`，历史仍可审计；所有查询先按 `user_id` 隔离，MongoDB 还用活跃事实唯一索引和有限重试处理并发写冲突。

4、家居环境拓扑和设备 Capability Registry 为什么适合由 PostgreSQL 这类关系数据库维护？并发更新时如何利用事务、乐观锁和 Outbox 防止丢失更新？Redis 与 RabbitMQ 分别承担什么职责，为什么没有因为“高并发”就把它们当作数据库真相源，或者随意替换成 RocketMQ？

**参考回答：** 环境拓扑和 Capability Registry 有明确实体关系、版本约束与跨表一致性，适合放在 PostgreSQL。更新时调用方携带期望的 home version，数据库用 CAS 式 `UPDATE ... WHERE version = expected_version` 做乐观锁；房间、设备、能力和拓扑变更与 `registry_outbox` 在同一事务提交。版本不匹配就重新读取并合并，不使用静默 last-write-wins。

Redis 只做带 TTL 的状态缓存、幂等去重、租约、限流和短期 Diff；丢失后可从 PostgreSQL Registry 与设备权威状态重建。RabbitMQ 用于拆分服务后的事件传播，解决削峰、重试和 DLQ，不负责事务真相。项目选择 RabbitMQ 是因为当前需要的是可靠工作队列、Quorum Queue、Publisher Confirm 和成熟 Python 异步客户端，而不是因为 RocketMQ 不可用；在规模和顺序消息需求没有证明迁移收益前，不额外引入第二套 MQ。

5、当设备状态查询较慢时，缓存、增量 State Diff、TTL 和全量对账如何协同工作？系统怎样识别重复、乱序和丢失的 Diff，并保证 Redis 缓存最终能够与真实设备状态恢复一致？

**参考回答：** 每个状态快照带 `home_id/device_id/sequence/observed_at/expires_at/source`，当前默认 TTL 为 60 秒。新 Diff 的 sequence 等于当前版本时判为 DUPLICATE，小于当前版本判为 OUT_OF_ORDER，大于当前版本加一以上且不是完整快照时判为 GAP；这三种情况都不能把不完整数据覆盖到新状态上。

正常增量只做嵌套字段合并；发生 GAP、缓存缺失或 TTL 过期时，Read-through 服务从设备/网关权威接口读取完整快照并跨版本修复。`StateReconciler` 再周期性全量对账漏失事件。MQTT retained state 还必须通过采集时间、设备在线状态和必要的主动查询，不能仅凭“是 retained message”认定仍然真实。

6、HomeClaw 的 Skill-MoE 如何缓解长上下文和全量 Tool Schema 暴露问题？请说明 Skill Registry、Top-K Router、按需加载和 Expert 内工具收缩的具体实现，并解释它与普通 Router、渐进式 Skill 披露及神经网络 MoE 的区别。

**参考回答：** 我把它定义为工程型稀疏门控。Skill Registry 保存能力域、关键词、激活短语、可用性、能力分、Tool 引用和知识资源 URI。Router 先用倒排索引召回，再按 `0.70×词法相关度 + 0.20×关键词覆盖 + 0.10×能力分` 排序，最低分默认 0.12；简单指令选 Top-1，多意图或视觉指令选 Top-2，最大不超过 Top-3，Token 余量低于 1000 时退回 Top-1。

第一层只加载命中 Skill 的说明、资源和 Tool Schema；第二层用拓扑候选设备与 Capability Registry 删除设备不支持的 Tool。公共澄清工具始终保留。它与普通 Router 的区别是多了 Expert 内的设备能力收缩，与普通渐进式披露的区别是由统一 Registry、动态 Top-K 和执行反馈控制；它不训练门控神经网络，也不把每个 Expert 强制实现成独立 LLM，因此不能称为参数级 MoE。

7、你如何量化“双层稀疏”设计的实际收益？请分别与全量 Tool Schema 的 ReAct、全量 Tool Schema 的 Plan-and-Solve、普通 Router 加渐进式披露进行对照：四组方案的平均规划步数、Prompt/Completion/总 Token、候选工具数、P50/P95、单任务成本和长程任务成功率实测值分别是多少？HomeClaw 相对各基线将规划步数和 Token 降低了百分之多少、将成功率提升了多少个百分点？实验使用什么模型、硬件、数据集、样本量、并发度和随机种子，结果是否给出方差或置信区间？

**参考回答：** 当前分支可复现的离线结果是：完整 Tool Schema 为 2406 Bytes，Top-2 Skill 后平均只暴露 928.72 Bytes，Schema 体积减少 61.4%；旧版同一复杂指令 Smoke 中，HomeClaw 懒加载 Prompt 为 182 Token，SAGE 全量注入为 523 Token，减少 65.2%。在 25 条 Router Gold 集上，Top-2 的 Skill 完整覆盖率为 100%。这些数字证明“上下文确实被收缩”，但不是在线模型任务成功率。

四策略在线对照的 Harness 已统一记录规划步数、Prompt/Completion/总 Token、工具数、P50/P95、成本和失败分布，但当前没有在线模型原始报告，因此不虚构四组完整数值。简历中“长程复杂指令成功率相对基线提升 25%”属于此前固定任务集的项目实验口径，面试时应与本分支的 61.4% Schema 收缩、65.2% Prompt 收缩分开陈述，并准备对应数据集、模型版本和原始结果。

### 三、Skill 和 Tool

8、你是如何从智能家居的业务能力、事务边界和安全策略出发抽象 Skill 与 Tool 的？一个新 Skill 或 Tool 的 Schema、前置条件、预期效果、幂等等级和验证谓词如何定义？当前设计借鉴了 SAGE 的哪些经验，又有哪些属于 HomeClaw 自己的工程重构？

**参考回答：** Tool 是最小可验证的领域动作，不是 MQTT Topic 的别名。它至少包含稳定名称、版本、参数 JSON Schema、目标设备类型、Capability、前置条件、Expected State、幂等等级、风险级别、授权策略和验证谓词。Skill 则是围绕一个能力域组织的“意图范围 + 知识资源 + 允许 Tool 集合 + 工作流约束 + 回退策略”，例如 lighting、climate、security 和 device-disambiguation。

新 Tool 先进入唯一 Tool Registry，再由多个 Skill 通过 ID 引用；新 Skill 只需注册元数据，不修改 Host 主循环。SAGE 给了我设备工具分类、用户画像和评测场景方面的参考，但 HomeClaw 自己完成了领域契约、Skill Registry、Top-K 门控、Capability 二次收缩、Verifier、MCP–MQTT 映射、幂等恢复和可观测链路，面试时应如实说明借鉴边界，而不是把已有分类换名后声称原创。

9、Skill 的边界依据能力域、上下文依赖还是执行事务划分？当多个 Skill 需要同一个 Tool 时，如何通过唯一注册、引用复用、版本和权限一致性避免重复定义及 Schema 冲突？

**参考回答：** 我用四个维度划分 Skill：业务能力域是否相同、是否共享同类知识上下文、是否属于同一安全策略、失败后能否独立回退。Skill 不等于一个设备，也不等于一个 Prompt；例如“识别图中设备”属于消歧 Skill，而识别出的灯最终仍交给 lighting Skill 执行动作。

共享 Tool 只在 Registry 定义一次，多个 Skill 保存引用，不复制 Schema。注册阶段拒绝重复 Tool ID、冲突 Schema 和循环依赖；版本、权限、风险与幂等属性跟随 Tool 本体统一升级。Router 可以同时召回多个引用同一 Tool 的 Skill，但 Host 最终对 Tool ID 去重，只暴露一份 Schema，从根源避免权限漂移和上下文重复。

10、Router 如何保证 Skill 召回率并在低置信度时安全回退？Recall@1、Recall@K、MRR、多标签完整覆盖率和 Fallback Rate 分别如何计算？HomeClaw 与普通 TF-IDF 或向量 Router 在同一测试集上的各项实测值具体是多少，Recall@K 和完整覆盖率分别提升了多少个百分点？测试集有多少条单意图、多意图、模糊及中英文样本，Top-K、模型版本和置信度阈值如何固定？

**参考回答：** Router 用倒排召回、关键词覆盖、能力分、激活短语和最低置信度门控组合保证召回；低于阈值时只返回 clarification Skill，不能猜一个设备动作。Recall@K 衡量 Gold Skill 被 Top-K 覆盖的比例，MRR 衡量第一个正确 Skill 的倒数排名，多标签完整覆盖要求一条多意图指令的全部 Gold Skill 都被找回，Fallback Rate 统计安全澄清比例。

当前同一 25 条中英文 Gold 集上，HomeClaw Top-1 Recall 为 86%、MRR 为 1.00、完整覆盖率为 72%；TF-IDF Top-1 分别为 72%、0.84、60%，即 Recall 提升 14 个百分点、完整覆盖提升 12 个百分点。Top-2 时 HomeClaw Recall 和完整覆盖均为 100%，TF-IDF 为 92% 和 88%，分别提升 8 和 12 个百分点。HomeClaw Fallback Rate 为 4%，因为唯一模糊指令被主动澄清；TF-IDF 虽为 0%，但它把该样本错路由，不能把“不回退”解释为更好。

11、当 Skill、Tool 和设备数量增长到千级甚至万级时，Router 如何维持检索准确率与延迟？在 100、1000、5000 乃至更大规模下，Recall@K、P50/P95、吞吐量、索引构建时间和峰值内存的实测值分别是多少，规模增长后准确率下降了多少？何时应从线性检索升级到领域分层路由、ANN 索引或分片，触发升级的量化阈值是什么？

**参考回答：** 当前 Router 用 token 到 Skill ID 的倒排索引，不扫描全量 Schema。离线扩展实验中：100 Skill/111 Tool 的路由 P95 为 0.037 ms、吞吐约 2.94 万 QPS、索引峰值约 0.32 MB；1000 Skill/1011 Tool 时 P95 为 0.093 ms、约 1.13 万 QPS、3.14 MB；5000 Skill/5011 Tool 时 P95 为 0.372 ms、约 2976 QPS、16.3 MB，索引构建约 98 ms。5000 个候选设备的 Tool 收缩 P95 为 1.378 ms。该扩展集保持确定性命中，不代表真实语义分布下 Recall 不下降。

我不会用“到 5000 个就必须换 ANN”这种硬编码规则。只有当真实 Gold 集 Recall@K 下降、生产 P95 超过 SLO，或索引内存超出单实例预算时，才先做领域粗路由与分片，再比较关键词、ANN、混合召回和重排；切换依据是同一数据集上的准确率—时延—内存 Pareto，而不是单一规模数字。

12、Skill-MoE 的“自进化”为什么不能让 Agent 在线直接修改生产 Skill？请说明如何借鉴 RSIAgent 和 evolver.py 的思路，构建“失败轨迹收集—候选生成—固定集回放—消融—安全门禁—Evidence Pack—人工审批—Canary—回滚”的受控离线闭环。

**参考回答：** 在线自改会把一次偶然失败、Prompt Injection 或错误反馈永久写进生产路由，且难以审计，所以生产 Agent 没有 Skill/Router 写权限。运行时只产生结构化 Failure Trace，包括输入、路由、提议、Verifier issue、执行证据、版本和关联 ID。

离线 Pipeline 根据 Trace 生成候选变更，绑定当前 base version 和内容哈希；在固定数据哈希、模型、Prompt、种子和预算上做基线/候选回放，再做消融，任一安全检查失败或 base version 已过期都默认拒绝。门禁通过只生成 Evidence Pack 并进入小流量 Canary，仍需人工批准；Canary 出现安全违规自动暂停，并可按候选版本回滚。借鉴 RSI/evolver 的是“生成—评估—保留”循环，HomeClaw 增加了智能家居所需的确定性安全门禁和不可在线自写边界。

### 四、意图识别和幻觉降低

13、基于家居环境图谱的知识锚定如何先收缩 Grounder 的候选设备？差分注意力机制在模型侧具体解决什么问题？在同类设备、遮挡和多轮指代等子集上，基线、仅知识锚定、仅差分注意力以及二者结合时的 Grounding Accuracy、Top-K Recall 和歧义消解准确率分别是多少，最终提升了多少个百分点？这些结果来自哪套自有数据、多少样本和几次重复实验，如何通过消融、方差或置信区间证明不是数据泄漏或场景偏差？

**参考回答：** 推理时先用 `home_id/room_id/capability` 在环境拓扑中过滤候选；候选只有一台就直接绑定，不调用视觉模型，候选超过一台才把受限候选 ID 与图像一起交给 Grounder。Grounder 返回的设备如果不在锚定候选集内会被拒绝，低置信度或超时保持 ambiguous，绝不猜测。差分注意力属于 Grounder 训练侧，用来放大相似设备之间有判别力的局部视觉差异，不参与 Agent 的 Verifier 奖励。

当前简历可使用的已有研究口径是细粒度物理设备实体识别准确率 84%；本分支没有 GRPO/差分注意力训练代码和原始消融表，因此不能从代码反推“仅锚定”和“仅差分注意力”各提升多少。工程侧可复现的是 5 个 Grounding Service 回归场景全部通过，包括单候选跳过模型、多候选调用、候选集外拒绝、批处理隔离和故障保持歧义。正式回答提升百分点时应引用原研究的基线、测试集和消融表，而不能临时编一个增益。

14、Proposer–Binder–Verifier 闭环具体如何工作？工程实现为什么默认不需要把 Proposer 和 Verifier 包装成两个通过 A2A 通信的独立 Agent？结构化提议、实例绑定、反例证据和重规划信息如何传递？加入 Verifier 前后的 False Done Rate、动作幻觉率、非法动作拦截率、任务成功率和平均重规划轮数具体是多少，分别下降或提升了多少个百分点，测试样本量与置信区间是什么？

**参考回答：** Proposer 只根据用户指令和被 Router 选中的 Tool 子集生成 `ActionProposal`；Binder 把语义别名绑定到唯一注册实例；Verifier 不读取 Proposer 的自然语言自证，只用 Capability Registry、拓扑、状态新鲜度、参数 Schema、风险和幂等策略检查结构化动作。失败后返回机器可读 issue，Host 最多允许 2 次 Re-Plan。它们位于同一确定性 Workflow 内即可完成认知隔离，无需为了“多 Agent”形式额外引入 A2A；只有跨进程部署时才需要把同一领域契约放到消息协议上。

当前 10 个 MQTT Bridge 场景和 6 个 Production Runtime 场景全部通过，覆盖 PUBACK 无状态证据、错误 `command_id`、过期 retained state、迟到 ACK、设备业务拒绝、Broker 故障、视觉歧义和跨家庭授权等路径；在这组代码回归集上，已覆盖的 False Done 路径拦截率为 100%。这不是现实分布下的“幻觉率”。简历中长程任务成功率相对基线提升 25% 是整个系统的既有实验结果，不能全部归因给 Verifier；若要回答 Verifier 单模块提升，必须补做关闭 Verifier 的同集消融。

15、Verifier 如何检测同一批原子动作中的设备状态冲突、环境影响冲突、资源竞争、循环依赖和冗余动作？你从 KnowDetector 的图模式思路中借鉴了什么？HomeClaw 自有冲突测试集包含多少条样本、各冲突类型占比是多少，Precision、Recall、F1、Exact Match、误报率和漏报率的实测值分别是多少？与未使用图约束或仅做 Schema 校验的基线相比提升了多少个百分点，为什么不能直接把外部论文结果当作本项目指标？

**参考回答：** 冲突检测器在动作批上构图：同一设备的相反 Expected State 形成 device conflict；不同动作对同一环境变量给出相反影响形成 environment conflict；无依赖顺序却抢占同一 exclusive resource 形成 resource conflict；前置条件被另一动作最终状态破坏形成 blocked action；DAG 再做环检测，同时识别完全相同的 redundant action。显式依赖可以把资源竞争转成合法串行。

当前仓库自有合成集共 8 条，覆盖安全独立、冗余、设备冲突、环境冲突、资源冲突、已排序资源、依赖环和阻塞动作各 1 条；离线 Precision、Recall、F1 与 Exact Match 均为 1.00，误报率和漏报率均为 0。该数字只证明 8 类规则的回归覆盖，不能包装成真实家庭冲突检测率；与仅做 Schema 校验的增益也要在扩充后的同一测试集上重新跑。KnowDetector 只提供图模式与冲突类型的设计启发，其论文数字不能归属于 HomeClaw。

### 五、MCP、MQTT 和动作执行

16、在线模型产生 Function Calling 后，Host 如何筛选允许调用的 Tool，并通过 MCP Client 请求家居领域 MCP Server？

**参考回答：** 在线模型并不直接调用设备。Proposer 先把 Function Calling 结果转成领域 `ActionProposal`，Host 只接受 Router 白名单内的 Tool；Binder 与 Verifier 通过后，`MCPActionDispatcher` 才把 `home_id/device_id` 和参数交给 `MCPHostGateway`。Gateway 在调用前校验主体、角色、家庭租户范围、策略版本和高风险人工确认，再通过官方异步 Session Adapter 或进程内 Client 请求 Domain MCP Server。这样模型只能“提议”，最终授权和执行权仍在 Host。

（1）MCP Tools 如何描述领域动作、参数 Schema、权限、风险等级、幂等性和预期状态，而不暴露底层 MQTT Topic？

**回答要点：** MCP Tool 使用领域名称、描述、版本和 `inputSchema`；风险、幂等性、Expected State 与验证谓词由 Tool Registry/ActionProposal 维护。Server 明确拒绝包含 `/` 或以 `mqtt` 开头的 Tool 名称。真正的 command/state Topic 只存在于 Bridge 的内部 Binding，既不进入 Tool Schema，也不进入 LLM 上下文。

（2）MCP Prompts 如何分别为规划、验证和故障恢复提供版本化模板，又如何避免把实时可变状态固化在 Prompt 中？

**回答要点：** Prompt 注册项包含稳定名称、描述、版本和纯渲染器，只保存规划规则、验证约束或故障解释格式。设备实时状态不写进 Prompt，而是在每次任务中通过 Resource 或经过收缩的 Context 按需读取；这样模板可以版本化缓存，状态则保持新鲜，两者不会互相污染。

（3）MCP Resources 如何向 Agent 提供聚合后的设备状态和能力快照？面对温度、传感器等高频异步事件，如何只对异常、条件达成或用户关注的变化发送更新通知，避免持续污染 LLM 上下文？

**回答要点：** Resource 使用 `home://<home_id>/devices/<device_id>/state` 这类 URI，读取时返回聚合状态、sequence、observed_at 和 stale 标记，而不是原始传感器流。每个 Diff 先更新版本化缓存，只有 `should_notify(previous,current)` 判断异常、条件达成或用户订阅命中时，才发送 Resource Updated 通知；普通高频变化只更新快照，不触发 LLM。

17、MCP–MQTT Bridge 的核心设计目的是什么？领域 Tool 如何在 Bridge 内部映射为 Topic 与 Payload？为什么 Broker PUBACK 只能证明消息已接收，系统又如何通过业务 ACK 或目标 State Evidence 判断设备是否真正执行成功？

**参考回答：** Bridge 是领域动作与设备协议之间的防腐层：MCP 暴露 `set_temperature`、`set_brightness` 等稳定能力，Bridge 内部的 `MqttToolBinding` 再映射 command topic、state topic、payload builder、超时和 Expected State。更换厂商 Topic 只改 Binding，不影响 Agent Tool Schema。

执行时先订阅状态再发布命令，Payload 带稳定 `command_id`。PUBACK 只说明 Broker 接收了消息；只有设备业务 ACK，或携带匹配 `command_id` 且状态满足 Expected State 的新状态事件，才能生成 `SUCCEEDED`。无状态证据保持 `UNKNOWN`，明确业务拒绝为 `REJECTED`，Broker/网络故障才是可重试依赖错误；迟到 ACK 可以升级 UNKNOWN，但不会重新发布同一动作。

18、Host 如何在 PostgreSQL 中持久化状态机、任务依赖 DAG、已完成步骤、当前节点、`request_id`、`command_id`、幂等键、Checkpoint 和 Outbox，并保证这些信息能够原子更新？

**参考回答：** PostgreSQL 的 Workflow 记录保存当前节点、完整序列化 State、revision、Deadline 和关联 ID；每个节点完成后用期望 revision 做乐观锁更新，并在同一连接、同一事务中写入 Outbox。DAG 依赖、已完成节点、Verifier 反馈和执行证据都属于 State；消息发布器只扫描未发布 Outbox，Publisher Confirm 只能更新 `published_at`，不能把设备动作改成成功。

（1）Agent 在任意 Workflow 节点崩溃后，如何从最后一个持久化 Checkpoint 恢复，并避免重复执行已经完成的动作？

**回答要点：** `WorkflowHost.resume(task_id)` 从最后一个已提交节点继续。动作执行前，`ActionAttempt` 以 `task_id:action_id` 作为幂等键认领并保存原 `command_id`；崩溃恢复时若已有终态证据就直接返回，若只有 DISPATCHED 则复用原 `command_id` 继续等待，绝不生成新命令盲目补发。当前已对所有运行节点逐点注入崩溃并通过恢复测试。

（2）为什么 MQTT retained message 不能直接作为最新真实状态？系统如何结合采集时间、设备在线状态、版本号和主动查询排除过期 retained state？

**回答要点：** retained 只代表 Broker 保存的最后一条消息，不代表设备此刻仍在线或状态未被线下改变。Bridge 会检查 observed_at 是否晚于命令、sequence 是否有效、availability 是否在线、`command_id` 是否匹配；缺时间、过期或离线时不能确认动作，必要时主动查询设备并用权威完整快照修复缓存。

（3）为什么 MQTT QoS 1 不等于业务上的“恰好执行一次”？系统如何利用稳定的 `command_id`、去重缓存、Action Attempt 记录和幂等动作设计，防止 `toggle_light()` 因重复投递产生相反结果？

**回答要点：** QoS 1 的语义是“至少一次”，重连或 ACK 丢失都可能重复投递。设备端或 Bridge 以 `command_id` 去重，Redis 保存短期执行证据，PostgreSQL Action Attempt 保存跨崩溃的命令身份。动作优先设计成 `set_light(on)`、`set_temperature(26)` 这类绝对目标；`toggle_light()` 无法安全转换时标记 NON_IDEMPOTENT，重试上限强制为 1。

19、接入大量 MCP 工具后，Host 如何通过 Skill Top-K、Expert 内 Tool 收缩、Schema 缓存及有限次数的二次召回控制上下文大小？工具数量持续增长时，为什么模型实际看到的 Schema 规模仍主要由被激活的 Skill 决定？

**参考回答：** MCP Server 可以注册全量工具，但 Host 从不把 `list_tools()` 的全部结果直接塞给模型。Router 先选 Top-K Skill，Host 只取这些 Skill 引用的 Tool；Tool Contractor 再按候选设备 Capability 删除不可执行 Tool，公共安全工具保留最小集合。错误路由只允许在 Re-Plan 预算内二次召回，不能无限扩展 Schema。

当前 Registry 的完整 Schema 是 2406 Bytes，Top-1 平均暴露 727.12 Bytes，减少 69.8%；Top-2 平均暴露 928.72 Bytes，减少 61.4%。因此 Tool 总数增长时，模型上下文主要随“被激活 Skill 的工具并集”增长，而不是随 Server 全量工具线性增长。

20、当 LLM、Grounder、MCP 或 MQTT 调用耗时过长或服务中断时，系统如何设置分层超时、有限重试、指数退避、熔断、并发上限、Token/Step 预算和全局 Deadline？各层的具体阈值、最大重试次数、退避区间、熔断触发失败率和恢复窗口是多少？故障注入实验中的终止率、恢复率、重复执行率和最大耗时分别是多少，哪些错误允许重试、哪些必须立即失败？

**参考回答：** 当前默认值是：Workflow 120 秒 Deadline、24 Step、2 次 Re-Plan、16K Token；LLM Client 120 秒；Grounder 单次 10 秒、健康检查 2 秒；官方 MCP Session Adapter 30 秒；MQTT Tool Binding 默认 5 秒。通用 Retry 最多 3 次，指数退避从 0.1 秒开始、上限 2 秒、抖动 10%；连续 5 次失败打开熔断，30 秒后半开探测；Planner/Grounder 排队默认最多 5 秒。

只有 `TimeoutError/ConnectionError` 等瞬态传输错误允许重试，HTTP 400、Schema、授权、业务拒绝和非幂等动作立即失败；NON_IDEMPOTENT 操作始终只尝试 1 次。当前故障注入回归验证了超预算必达明确终态、熔断可半开恢复、崩溃复用原命令且不重复产生已完成副作用；真实外部服务下的恢复率和最大耗时仍需按统一故障矩阵压测，不能用进程内单测时延代替。

21、设备命令写入后，系统如何验证 read-your-write 一致性，而不是只相信发布结果？在缓存命中、缓存过期、Diff 丢失、乱序、设备离线和 retained state 过期等场景下，缓存命中率、read-your-write 达成率、陈旧读比例、状态确认 P50/P95、未知终态比例、对账差异率和全量对账恢复时间的实测值分别是多少？测试使用多少设备、怎样的事件速率和多长的观测窗口？

**参考回答：** 写路径把 `command_id + expected_state` 作为确认条件；读路径只接受版本更新、时间新鲜且匹配 Expected State 的证据。发布成功但没有状态证据只能是 UNKNOWN。缓存缺失或陈旧时回源，Diff GAP 触发完整快照，周期 Reconciler 修复漏失更新，因而 read-your-write 的判定与缓存命中本身解耦。

当前 8 个状态缓存/Resource/一致性测试和 10 个 MQTT Bridge 测试全部通过，覆盖重复、乱序、GAP、TTL、回源、对账、离线、旧 retained 和错误命令状态；这些是场景正确率，不是生产命中率或时延。真实缓存命中率、状态确认 P50/P95、陈旧读比例和恢复时间尚未在 Redis/MQTT 实例上生成报告，面试时不能把“18 个测试全部通过”换算成“线上一致性 100%”。

22、Skill-MoE 激活多个 Expert 时，如何控制在线 LLM 的 QPS、在途 Token、并发数和成本，以及 Grounder 的批处理、队列长度和 GPU 显存占用？在不同 Top-K 和并发梯度下，系统的最大稳定 QPS、单任务 Token 与成本、成功率、排队 P50/P95、GPU 利用率、峰值显存和限流比例具体是多少？容量测试使用什么硬件、数据集、压测工具和模型版本，容量拐点及推荐并发上限是多少？

**参考回答：** Router 根据任务复杂度选择 Top-1/Top-2，最大 Top-3；在线 Planner 外层同时使用 QPS Token Bucket、并发 Semaphore、在途 Token Pool 和 5 秒排队上限，先预留 Token 再发请求。Grounder 独立限流，Docker 当前固定单 GPU Worker，并在模型内部加锁，避免多线程生成导致显存失控；批处理请求仍保留每个样本自己的候选集合。

本机只完成 CPU Router 容量测试：5000 Skill 时约 2976 QPS、路由 P95 0.372 ms；这不能代表在线 LLM 或 GPU。真实容量报告尚未运行，计划按并发 1/2/4/8/16/32、Top-K 1/2/3、Grounder Batch 1/2/4/8/16 升压，记录 Token/任务、成本、成功率、queue P95、GPU 利用率和显存，并在错误率、P95 SLO、OOM 或熔断任一触线时停止；在报告产生前不声称最大稳定 LLM QPS 或推荐 GPU 并发。

23、如何定位一条 Agent 请求的端到端性能瓶颈？`trace_id`、`request_id`、`task_id` 和 `command_id` 如何贯穿 Router、Grounder、Planner、Verifier、MCP、MQTT 与状态确认链路？在固定压测环境下，各组件及端到端的 P50/P95/P99、耗时占比、错误率、超时率、平均重试次数和吞吐量实测值分别是多少，当前第一瓶颈和第二瓶颈是什么？这些数据如何埋点、聚合并通过固定配置、样本量和原始报告复现？

**参考回答：** 入口创建 `trace_id/request_id/task_id`，每个设备动作再派生稳定 `command_id`；这组 ID 随 Workflow State、MCP 参数、MQTT Payload、执行证据和 Outbox 传播。统一 Span 包括 `agent.request`、`workflow.<node>`、`router.retrieve`、`grounder.infer`、`planner.generate`、`verifier.check`、`mcp.call`、`mqtt.publish` 和 `mqtt.wait_state`，每个 Span 记录 duration、status、retry、queue 和安全的低基数属性，敏感 Token、Prompt、用户画像和原始图像在出口前脱敏。

当前可复现的 Router Top-2 P50/P95 是 0.051/0.086 ms，5000 Skill 时为 0.331/0.372 ms；完整代码回归为 123/123 单测及 8 组 Smoke 通过。由于没有启动在线 Planner、GPU Grounder、真实 MCP/MQTT 和 OpenTelemetry Collector，目前不能给出可信的端到端 P95/P99，也不能武断认定第一瓶颈。工程上预计在线 LLM/Grounder 是计算瓶颈、MQTT 状态确认是尾延迟瓶颈，但必须用同一 trace 的耗时占比和真实压测报告确认。

