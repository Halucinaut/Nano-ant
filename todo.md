# Nano Ant TODO

> 目标：把 Nano Ant 从“偏 coding 的多角色原型”逐步收敛成“轻量级、训练式、面向通用任务的 harness agent 框架”。

## 0. 总体原则

- 优先构建最小闭环，不先做大而全平台
- 优先抽象 `Action`，不再把执行层绑定在 `Coding`
- 优先结构化反馈，而不是依赖长文本 feedback
- 优先可恢复、可观测、可验证
- 优先让每个模块有清晰边界，避免 orchestrator 无限膨胀

## 1. 先定义清楚系统边界

### Step 1.1 明确 Nano Ant 的一句话定位

输出一版稳定定义，后续所有设计都围绕这句话展开：

`Nano Ant 是一个借鉴深度学习训练闭环、通过多轮执行与评估实现任务轨迹自我优化的轻量级 harness agent 框架。`

### Step 1.2 明确不做什么

需要显式写入文档并持续约束实现：

- 不先做重型平台
- 不先做复杂 UI
- 不先做多租户任务中心
- 不先做过多角色扩张
- 不把执行层局限在 coding

### Step 1.3 定义最小成功标准

Nano Ant 的第一阶段完成标准应至少包括：

1. 能接收一个目标
2. 能形成一个 plan
3. 能执行一个或多个 action
4. 能获得 judge 反馈
5. 能进入下一轮并利用上轮反馈
6. 能保存和恢复中间状态
7. 能在达到停止条件时正确退出

## 2. 收敛核心抽象

### Step 2.1 重命名执行角色

把 `Coding Role` 改造为 `Action Role`，至少完成下面几件事：

1. 代码命名层改造
2. prompt 语义改造
3. orchestrator 调用逻辑改造
4. metadata 字段改造

目标不是简单重命名，而是职责升级。

### Step 2.2 定义 Action 的统一抽象

需要新增统一动作模型，例如：

- `action_type`
- `tool`
- `input`
- `expected_output`
- `side_effects`
- `status`
- `observation`

建议最少先支持以下动作类型：

- `write_file`
- `edit_file`
- `run_command`
- `read_file`
- `search_text`
- `call_llm`
- `custom_tool`

### Step 2.3 明确 Observation 的结构

Action 执行完后，不应只回传原始文本。需要结构化 observation，例如：

- 标准输出
- 标准错误
- 修改了哪些文件
- 命令是否成功
- 产物路径
- 环境状态摘要

### Step 2.4 明确 Judge 的输入格式

Judge 未来不该只看“代码片段”，而应看：

- 目标
- 当前 plan
- action 列表
- action 结果
- observation
- 上一轮反馈
- 当前工作区状态摘要

## 3. 重构最小主循环

### Step 3.1 把主循环收敛为 4 个阶段

推荐统一为：

1. `Plan`
2. `Action`
3. `Judge`
4. `State Update`

`Leader` 可以先降级为可选组件，不应成为最小主链路的必须项。

### Step 3.2 精简 Orchestrator 职责

Orchestrator 应该只负责：

- 初始化运行上下文
- 驱动角色调用
- 控制循环次数
- 处理 checkpoint
- 判断停止条件
- 聚合结果

Orchestrator 不应继续承担过多业务逻辑解析。

### Step 3.3 明确迭代数据模型

建议统一每轮数据结构，例如：

- `goal`
- `iteration`
- `plan`
- `actions`
- `observations`
- `judge_result`
- `feedback_artifact`
- `state_delta`
- `score`

这样 checkpoint、telemetry、trace 都能复用同一套数据模型。

## 4. 重构角色设计

### Step 4.1 Plan Role

目标：

- 只负责“下一轮怎么做”
- 输出结构化 plan
- 不越权做执行
- 能根据反馈调整策略

Plan 的输出建议至少包括：

- 本轮目标
- 任务拆解
- action 列表
- 每个 action 的预期结果
- 本轮成功判据

### Step 4.2 Action Role

目标：

- 把 plan 转换成对环境的真实动作
- 支持多工具
- 返回结构化 observation
- 保留 side effect trace

第一阶段建议先让 Action Role 仍可兼容代码任务，但底层接口设计必须通用。

### Step 4.3 Judge Role

目标：

- 从“代码评审器”变成“任务结果评估器”
- 更偏 evaluator / reward model，而不是 reviewer

Judge 应输出：

- `passed`
- `score`
- `summary`
- `issues`
- `fix_actions`
- `confidence`
- `stop_recommendation`

当前状态：

- 已支持 `JudgeSkillRegistry`
- 已支持任务级 `JudgeSkill`
- 已支持 `pass_threshold / rubric / required_checks` 注入 Judge prompt
- 下一步重点应转向“如何蒸馏审核 skill”而不是继续扩充 Judge 主逻辑

### Step 4.4 Leader Role

决定是否保留：

- 如果保留，定位应变成策略协调器
- 如果删除，使用状态机和规则替代

建议优先简化：  
第一阶段可以弱化 Leader，避免角色层过重。

## 5. 设计统一工具层

### Step 5.1 建立 Tool Interface

设计统一接口，例如：

- `name`
- `description`
- `input_schema`
- `execute()`
- `result_schema`

当前状态：

- 已完成 `ToolSpec / ToolProvider / ToolRegistry / ActionToolExecutor`
- 已支持 `BuiltinToolProvider`
- 已支持 `MCPToolProvider` 适配外部 MCP 风格 client
- 下一步重点应转向 provider 生命周期、权限分级与远端错误恢复

### Step 5.2 内置基础工具

第一批工具建议包含：

1. 文件读写工具
2. 文本搜索工具
3. shell 命令工具
4. Python 执行工具
5. HTTP 请求工具
6. LLM 调用工具

### Step 5.3 区分安全级别

工具层需要提前区分：

- 只读工具
- 可写工具
- 高风险工具
- 外部网络工具

这样 Judge、Sandbox、策略层才有机会利用这些信息。

### Step 5.4 设计工具结果标准化

所有工具结果尽量统一为：

- `success`
- `message`
- `output`
- `artifacts`
- `side_effects`
- `error`

## 6. 重构状态与记忆系统

### Step 6.1 Context 只保存关键状态

当前 `Context` 已有雏形，后续需要更明确地分层：

- 运行级状态
- 迭代级状态
- 工作区摘要
- 最优轨迹信息
- 停止条件统计

### Step 6.2 引入 State Delta

每轮都应该明确记录这轮带来了什么变化：

- 文件变化
- 环境变化
- 分数变化
- 计划变化
- 新失败类型

### Step 6.3 恢复能力标准化

恢复不应只是“恢复上下文对象”，而应明确：

- 恢复到哪一轮
- 恢复哪些文件状态
- 是否恢复工具状态
- 是否恢复 sandbox 状态
- 是否恢复 prompt / feedback 版本信息

## 7. 重构反馈体系

### Step 7.1 把 FeedbackArtifact 变成一等公民

现在已有 `FeedbackArtifact`，后续要做的是：

- 让 Judge 稳定输出它
- 让 Plan 直接消费它
- 让 Action 直接使用其中的 fix instructions

### Step 7.2 区分反馈层级

建议反馈分三层：

- `summary`：给人看
- `metrics`：给系统算分
- `fix_actions`：给下一轮执行

### Step 7.3 让 fix action 面向 Action Role

现在 fix action 偏代码修复语义。后续要扩展为通用任务语义，例如：

- 重新执行某命令
- 补充某文件
- 调整某配置
- 重新读取某上下文
- 新增某工具调用

## 8. 设计评分与停止机制

### Step 8.1 定义 Score 组成

建议把 score 拆成可解释维度：

- 目标完成度
- 正确性
- 稳定性
- 代价控制
- 可用性

### Step 8.2 定义停止条件

至少支持以下几类：

- 成功停止
- 最大轮次停止
- 连续无提升停止
- 连续低分短路停止
- 连续错误类型重复停止
- 外部中断停止

### Step 8.3 区分“失败”和“值得继续”

不是所有失败都该停止。  
Judge 需要给出：

- 当前是否成功
- 当前是否失败
- 当前是否值得继续

## 9. 把可观测性真正接到主闭环

### Step 9.1 Telemetry 保留，但降复杂度

Telemetry 的目标应是帮助判断：

- 哪一轮出了问题
- 哪个模块导致失败
- 为什么会短路

而不是为了堆工程能力。

### Step 9.2 Effect Tracker 成为轨迹记录器

Effect Tracker 应服务于：

- 审计
- 回放
- 失败分析
- 最优轨迹提取

### Step 9.3 设计 Iteration Report

每轮结束输出统一报告，建议包含：

- plan 摘要
- action 摘要
- observation 摘要
- judge 结果
- score 变化
- checkpoint 位置

## 10. 重构 Sandbox 与执行环境

### Step 10.1 明确 Sandbox 的职责

Sandbox 只做环境隔离和动作执行，不承担策略职责。

### Step 10.2 支持 Action 级执行

后续 sandbox 需要支持的不应只是：

- 跑 Python 文件
- 执行命令

还应支持：

- 执行工具动作
- 捕获 side effects
- 返回结构化 observation

### Step 10.3 决定 Sandbox Pool 的地位

如果保留 pool，应把它作为性能增强层。  
不要让它成为主闭环的前置依赖。

## 11. 重构 Prompt 体系

### Step 11.1 Prompt 与角色职责对齐

需要重写 prompts：

- `coding.txt` -> `action.txt`
- `judge.txt` 从代码评审器升级为任务评估器
- `plan.txt` 更强调 action plan，而不是文件计划

### Step 11.2 Prompt Registry 延后

Prompt Registry 是增强项。  
第一阶段不应阻塞核心闭环。

### Step 11.3 控制 Prompt 复杂度

Prompt 应尽量短、稳定、结构化。  
不要把系统行为过多依赖在长提示词魔法上。

## 12. 统一配置模型

### Step 12.1 拆分配置域

建议把配置明确分成：

- llm
- orchestrator
- action
- judge
- sandbox
- checkpoint
- telemetry

### Step 12.2 去掉过于 coding-specific 的配置命名

例如：

- `coding_tool` 需要重构成更通用的执行器或 action backend 配置

### Step 12.3 支持最小配置运行

理想状态下，最小配置只需要：

- 一个 LLM backend
- 一个 workspace
- 一个 goal

## 13. 建立测试策略

### Step 13.1 先测主循环，不先测边角

优先测试：

1. 单轮成功
2. 多轮迭代
3. judge 失败后进入下一轮
4. checkpoint 保存与恢复
5. 停止条件生效

### Step 13.2 为核心数据结构写测试

需要测试：

- context
- checkpoint manager
- feedback artifact
- telemetry short-circuit
- action result schema

### Step 13.3 做最小集成测试

设计一个假的 Action 执行器和假的 Judge，用确定性方式验证闭环逻辑。

## 14. 构建第一阶段里程碑

### Milestone A: 最小通用闭环

完成标准：

- 移除对 coding-only 语义的强依赖
- 主循环变成 `plan -> action -> judge`
- 能在一个简单通用任务上稳定多轮运行

### Milestone B: 结构化反馈闭环

完成标准：

- Judge 稳定输出结构化反馈
- Plan 能消费反馈重规划
- Action 能消费 fix actions

### Milestone C: 可恢复与可观测

完成标准：

- checkpoint 稳定
- effect trace 可查
- iteration report 可读
- 停止条件可靠

### Milestone D: 工具化扩展

完成标准：

- Action Role 支持多工具
- 至少支持文件、命令、HTTP、LLM 四类动作

## 15. 推荐实施顺序

严格建议按这个顺序推进：

1. 更新项目叙事与目标文档
2. 收敛最小架构
3. 把 Coding Role 改成 Action Role
4. 统一 action / observation 数据模型
5. 重构 Judge 输出
6. 打通 feedback 到下一轮 plan
7. 清理 orchestrator 逻辑
8. 再决定是否保留 Leader
9. 补齐测试
10. 最后再做 prompt registry、sandbox pool 等增强能力

## 16. 近期可直接开干的任务

### P0

1. 把 `Coding Role` 重命名并升级为 `Action Role`
2. 重写 `coding.txt` 为 `action.txt`
3. 修改 orchestrator，使其使用 action 语义
4. 统一 action result / observation schema
5. 修改 Judge，让其评估通用任务结果而不只是代码

### P1

1. 精简或弱化 Leader
2. 把反馈工件稳定接入 Plan
3. 输出统一 iteration report
4. 补齐主循环测试

### P2

1. 接入统一 Tool Interface
2. 重构 telemetry / effect tracking 的接入点
3. 评估 workflow state machine 是否替代 Leader
4. 设计 prompt registry 的真实使用路径

## 17. 最终验收标准

当下面这些问题都能回答“是”时，Nano Ant 的第一阶段才算真的成立：

1. 它是否已经是一个通用任务 harness，而不是 coding demo？
2. 它是否能通过多轮反馈显著改进任务结果？
3. 它是否能清楚解释每一轮做了什么、为什么这么做？
4. 它是否能在中断后恢复？
5. 它是否能稳定停止，而不是盲目循环？
6. 它是否足够轻，核心主链路仍然容易理解？

如果这些还做不到，就继续围绕最小闭环收敛，不要过早扩张。
