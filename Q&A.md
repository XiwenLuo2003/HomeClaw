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

