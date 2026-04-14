# Nano Ant

一个尽可能轻量级的 harness agent 框架，用训练式迭代的思想驱动 Agent 自我优化。当前默认内部 LLM 后端是 HTTP，默认模型是 `Qwen3-30B-A3B`。

## 简介

Nano Ant 的目标不是做一个“多角色写代码 demo”，而是构建一个足够轻、足够清晰、足够可控的 Agent Harness。

它借鉴深度学习训练流程中的核心思想：

- 每轮执行都产生一条任务轨迹
- 每轮轨迹都要被评估
- 评估结果要反馈到下一轮
- 通过多轮迭代，让任务执行策略逐步收敛

这里优化的不是模型参数，而是任务求解过程本身。

换句话说，Nano Ant 想解决的问题是：

如何让 Agent 不依赖一次性生成，而是像训练一样，在反复执行、评估、修正中持续变好。

## 项目定位

Nano Ant 是一个面向通用任务的轻量级 Agent Runtime / Harness，重点在于：

- 编排任务迭代闭环
- 管理状态、反馈与 checkpoint
- 抽象执行动作，而不是只抽象“写代码”
- 支持评估驱动的自我改进
- 保持整体架构尽量薄，避免过早平台化

它当前仍然偏向代码任务，但长期目标不是 `Coding Agent`，而是 `Action Agent`。

当前主干已经具备两个关键扩展点：

- 规范化的 `tool system`：工具带有 `name / description / input_schema / result_schema / risk_level`，并支持 provider 抽象
- skill-driven 的 `Judge`：可以为具体任务加载不同审核 skill，而不是永远用一套通用打分逻辑

## 核心理念

### 1. 训练式而不是单次式

传统 Agent 常常依赖一次 prompt 尽量把任务做完。  
Nano Ant 更接近训练循环：

`goal -> plan -> action -> judge -> feedback -> next iteration`

一轮做不好没有关系，关键是下一轮是否能利用反馈变得更好。

### 2. Harness 优先

Nano Ant 更关注“如何组织 Agent 的执行过程”，而不是“如何塑造一个人格化助手”。

因此它的重点是：

- orchestration
- iteration control
- evaluation
- checkpoint
- observability
- reproducibility

### 3. 通用动作，而不只是写代码

当前实现里主要是 `Coding Role`，但更合理的目标是 `Action Role`：

- 写文件
- 改文件
- 执行命令
- 调用工具
- 读取环境
- 做外部交互

也就是说，Nano Ant 最终希望面向的是“通用任务执行”，而不是仅仅“代码生成”。

## 目标架构

```text
┌─────────────────────────────────────────────┐
│                Orchestrator                 │
│      控制主循环、状态推进、停止条件、恢复      │
└──────────────────┬──────────────────────────┘
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
   ┌────────┐  ┌────────┐  ┌────────┐
   │  Plan  │  │ Action │  │ Judge  │
   │  Role  │  │  Role  │  │  Role  │
   └────────┘  └────────┘  └────────┘
       │           │           │
       └───────────┼───────────┘
                   ▼
            Feedback / State
                   │
                   ▼
             Next Iteration
```

推荐的最小闭环只有四个核心部件：

- `Orchestrator`：驱动迭代闭环
- `Plan Role`：决定这一轮做什么
- `Action Role`：执行动作
- `Judge Role`：评估结果并给出反馈

其他能力都应作为增强层，而不是侵入主干。

## 当前代码现状

当前仓库已经实现了一个可运行的迭代式多角色框架，主线能力包括：

- 命令行启动任务
- `Leader / Plan / Action / Judge` 主循环
- 基于 workspace 的 action 执行与 observation 收集
- 本地测试执行
- Judge 评分、结构化反馈、task-specific skill 注入
- checkpoint 保存与恢复
- 基础 sandbox 执行
- telemetry / effect tracking / structured feedback 等工程化模块
- tool provider 抽象，可接入内建工具或外部 MCP 风格 provider

但从“目标定位”看，当前代码仍处于过渡态：

- 主流程仍偏 `coding loop`
- `Coding Role` 还没有升级为通用 `Action Role`
- `Leader` 的存在感强于必要性，未来可能收敛到更轻的状态机或规则控制
- `harness` 模块里有些能力已经具备，但还没有被统一成最小、稳定、清晰的主架构

因此，这个项目现在更适合被理解为：

一个正在从“多角色 coding agent”演进为“轻量级通用 harness agent”的框架原型。

## 当前主循环

当前主循环大致如下：

1. 接收用户目标
2. 初始化上下文、LLM client、角色、checkpoint 管理器
3. Leader 分析当前状态
4. Plan 生成本轮计划
5. Action 执行计划中的工具动作
6. 系统记录 observation、写入产物并执行验证命令
7. Judge 基于审核 skill 评分、给反馈、决定是否通过
8. 保存 checkpoint 与上下文
9. 若通过则结束，否则进入下一轮

长期目标则应收敛成更抽象的通用版本：

1. 接收目标 `goal`
2. 生成计划 `plan`
3. 执行动作 `action`
4. 收集观察 `observation`
5. 评估结果 `judge`
6. 生成反馈 `feedback`
7. 更新状态并继续迭代

## 为什么要从 Coding Role 走向 Action Role

如果框架把执行层固定成“写代码”，它的能力边界会被过早锁死。

而 `Action Role` 的抽象更自然：

- 对于代码任务，它可以写代码、改文件、跑测试
- 对于运维任务，它可以执行命令、检查环境、修复配置
- 对于研究任务，它可以收集资料、归纳结果、生成产物
- 对于工作流任务，它可以组合多个工具完成操作链

因此，`Action Role` 更符合 Nano Ant 作为通用 Harness 的长期方向。

## 设计原则

- 轻量优先：先保证闭环清晰，再考虑增强能力
- 反馈驱动：每轮都必须从 Judge 获得可利用反馈
- 状态可恢复：任何长任务都应支持断点续跑
- 结构化优先：反馈、轨迹、动作、结果尽量结构化
- 工具解耦：Action 与具体工具实现解耦
- 观测内建：系统需要知道自己为什么成功、为什么失败
- 面向通用任务：不要把核心抽象绑死在代码生成

## Tool System

Nano Ant 现在的工具层已经从“内建命令集合”升级成了更规范的抽象：

- `ToolSpec`：描述工具的名称、输入 schema、输出 schema、风险等级
- `ToolProvider`：提供一组工具并负责执行
- `BuiltinToolProvider`：当前默认 provider
- `MCPToolProvider`：外部 MCP 风格 client 的适配层

这意味着后续如果你要接 Claude 风格的外部 tool / MCP server，框架本体不需要再改主循环，只需要增加 provider 适配器。

## Judge Skill

Judge 不再被设计成“一套 prompt 打天下”的角色，而是一个可以加载审核 skill 的 evaluator。

每个 `JudgeSkill` 可以定义：

- `description`
- `audit_focus`
- `rubric`
- `required_checks`
- `pass_threshold`
- `applies_to`

这让框架可以逐步把产品、运营、QA 等不同任务的审核标准沉淀成 skill，再让 Judge 在运行时按任务类型选择合适的审核规则。

## 仓库结构

```text
main.py                    # CLI 入口
config.yaml                # 基础配置
nano_ant/
├── agent/
│   ├── orchestrator.py    # 主控制器
│   └── roles/
│       ├── base.py
│       ├── leader.py
│       ├── plan.py
│       ├── action.py
│       ├── coding.py
│       └── judge.py
├── checkpoint/
│   └── manager.py         # checkpoint 管理
├── harness/
│   ├── effect_tracker.py
│   ├── feedback_artifact.py
│   ├── prompt_registry.py
│   ├── sandbox_pool.py
│   ├── telemetry.py
│   └── workflow_state_machine.py
├── judge/
│   └── skills.py          # Judge skill registry
├── llm/
│   ├── client.py
│   └── claude_code_client.py
├── memory/
│   └── context.py
├── tools/
│   ├── base.py
│   ├── provider.py
│   ├── registry.py
│   ├── builtin.py
│   └── executor.py
├── prompts/
│   ├── leader.txt
│   ├── plan.txt
│   ├── action.txt
│   ├── coding.txt
│   └── judge.txt
└── sandbox/
    └── executor.py
```

## 快速开始

### 安装

```bash
pip install .
```

安装后可以直接使用命令行入口：

```bash
nano-ant "创建一个简单的计算器，支持加减乘除"
```

也可以进入交互式 shell：

```bash
ant
```

进入后会看到一个更接近 Claude CLI 风格的终端界面：

- 左侧是像素风 ant logo、当前配置、template mode 状态和常用命令
- 右侧是当前任务摘要和实时滚动的执行事件流
- 底部保留输入提示

你可以直接输入任务，或者使用：

```text
/help
/config
/template
/template init ./prompt-task
/optimize
/run 帮我完成一个任务
/resume 3
/set workspace ./workspace
/set judge-model deepseek-chat
/exit
```

如果你只是本地开发，也可以继续使用：

```bash
python main.py "创建一个简单的计算器，支持加减乘除"
```

### 配置

默认配置现在优先走 HTTP 模式，默认模型是 `Qwen3-30B-A3B`，默认地址是 ``。

可以基于 [config.example.yaml](/Users/sunrx/idea/Nano%20ant/config.example.yaml) 创建你自己的配置文件。

如果你之后想切回 `Claude Code CLI`，再把 `llm.backend` 改成 `claude_code`，并确认本机可直接执行 `claude --version`。

框架支持两层 LLM 配置：

- 全局默认配置
- role 级覆盖配置：`leader / plan / action / judge`

## 统一任务目录

现在推荐的使用方式是统一任务目录，而不是分别记 internal / external 两套命令。

每个任务目录至少包含：

- `ant.yaml`：任务定义
- `judge_skill.yaml`：审核标准
- 目标文件或外部目标路径
- 评估脚本或默认评估配置

最小 `ant.yaml` 示例：

```yaml
name: my_task
type: internal_prompt
goal: 优化当前 prompt，在样例 case 上提高通过率。

target:
  type: file
  path: prompt.txt

judge:
  skill: judge_skill.yaml

evaluation:
  command: python3 eval_runner.py
  cwd: .
  report:
    format: nano_ant_eval_v1
    path: eval_report.json
```

评估脚本最终必须产出统一 JSON。推荐格式：

```json
{
  "meta": {
    "task_name": "my_task",
    "resource_path": "/abs/path/to/target",
    "evaluator": "eval_runner.py"
  },
  "summary": {
    "passed": false,
    "overall_score": 62,
    "total_cases": 3,
    "successful_cases": 2,
    "success_rate": 0.67,
    "text": "2/3 cases passed"
  },
  "case_results": [
    {
      "name": "case_1",
      "success": true,
      "score": 100,
      "passed_checks": [],
      "failed_checks": [],
      "input": {},
      "expected": {},
      "actual": {},
      "error": ""
    }
  ],
  "errors": [],
  "artifacts": []
}
```

交互模式下，进入 `ant` 后只需要输入项目路径：

```text
/run ./examples/product_prompt_sample
/run ./examples/external_zao_tagging_case
```

命令行也可以直接运行任务目录：

```bash
ant ./examples/product_prompt_sample
ant --interactive --project ./examples/external_zao_tagging_case
```

## Template Mode

`template mode` 是面向产品同学的 prompt 优化模式。它假设用户不会写 Python，只需要准备：

- `prompt.txt`
- `cases.json`
- `judge_skill.yaml`
- `target_llm.yaml`

Nano Ant 会提供通用的 `eval_runner.py`，让用户只改内容和配置，不需要自己写评估脚本。

### 初始化模板

```bash
nano-ant --init-template ./prompt-task
```

生成的目录里会包含：

- `prompt.txt`：待优化 prompt
- `cases.json`：代表性测试样例
- `judge_skill.yaml`：审核标准
- `target_llm.yaml`：实际跑业务 prompt 的目标模型配置
- `eval_runner.py`：模板内置的通用评估脚本
- `task.md`：使用说明

### 产品同学的推荐流程

1. 在 `target_llm.yaml` 里填好要评估的目标模型
2. 补全 `cases.json`
3. 根据业务审核标准调整 `judge_skill.yaml`
4. 运行 `ant`
5. 在交互界面里输入 `/optimize`

`/optimize` 会自动把当前模板目录转换成一个明确的优化任务，重点围绕：

- 修改 `prompt.txt`
- 运行 `python eval_runner.py`
- 读取 `eval_report.json`
- 基于 `judge_skill.yaml` 的审核标准反复迭代

### 本地 sample

仓库里已经附带了一个可直接模仿的产品同学 sample，在 [examples/product_prompt_sample/README.md](/Users/sunrx/idea/Nano%20ant/examples/product_prompt_sample/README.md)。

你可以直接这样试：

```bash
cd examples/product_prompt_sample
python eval_runner.py
ant --interactive --project .
```

进入后输入：

```text
/run .
```

## Unified Task Interface

现在框架已经开始收敛到统一的 `TaskContext` 抽象：

- `InternalTask`：资源和评估都放在 Nano Ant 内部
- `ExternalTask`：已有外部项目通过适配器接入

当前推荐直接使用统一任务目录：

```bash
ant ./examples/product_prompt_sample
ant --interactive --project ./examples/product_prompt_sample
ant --interactive --project /Users/sunrx/Project/zao-workflow/test_tagging_classify_summarize_ant
```

### 运行

```bash
python main.py "创建一个简单的计算器，支持加减乘除"
```

对应的已安装 CLI 用法是：

```bash
nano-ant "创建一个简单的计算器，支持加减乘除"
```

如果你只输入：

```bash
ant
```

就会进入交互式界面，在里面逐条输入任务并实时查看每一轮输出。

如果当前目录本身就是一个 prompt template，也可以直接：

```bash
cd ./prompt-task
ant
```

然后输入：

```text
/optimize
```

也可以在命令行临时覆盖默认 LLM：

```bash
python main.py "完成任务" \
  --backend http \
  --model deepseek-v3 \
  --base-url https://your-endpoint.example/v1 \
  --api-key sk-xxx
```

安装后的 CLI 写法：

```bash
nano-ant "完成任务" \
  --backend http \
  --model deepseek-v3 \
  --base-url https://your-endpoint.example/v1 \
  --api-key sk-xxx
```

如果你希望不同 role 使用不同模型或不同服务：

```bash
python main.py "完成任务" \
  --backend http \
  --plan-model deepseek-v3 \
  --action-model claude-sonnet \
  --judge-model deepseek-chat \
  --judge-base-url https://judge-endpoint.example/v1 \
  --judge-api-key sk-judge-xxx
```

### 恢复运行

```bash
python main.py "继续完成任务" --resume 5
```

## 发布打包

仓库已经提供了一键打包脚本：

```bash
./scripts/package.sh
```

这个脚本会执行：

- 清理旧的 `dist/` 和构建产物
- 跑测试
- 构建 `sdist` 和 `wheel`

如果环境里有 `build`，它会优先使用 `python -m build`。  
如果没有 `build`，会自动回退到 `python setup.py sdist bdist_wheel`。

打包完成后，产物会在 `dist/` 目录下。

## 下一步重点

当前更值得继续推进的方向是：

1. 丰富 tool provider 的接入方式和安全分级
2. 把更多审核标准沉淀成可复用 Judge skill
3. 继续强化 iteration report / state delta / best trajectory 的记忆能力
3. 把工具调用抽象成统一 Action 接口
4. 让 Judge 输出更稳定的结构化反馈
5. 把 checkpoint、telemetry、effect tracking 真正服务于迭代优化

更完整的构建路线见 [todo.md](/Users/sunrx/idea/Nano ant/todo.md)。

## License

MIT
