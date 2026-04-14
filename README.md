# Nano Ant

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> A lightweight iterative harness agent framework. Train your tasks like training a model.

[English](#english) | [中文](#中文)

---

## English

### What is Nano Ant?

Nano Ant is a lightweight framework that brings **training-loop thinking** to agent task execution. Instead of relying on one-shot generation, Nano Ant iteratively executes, evaluates, and improves until the task converges to a high-quality solution.

**Core Philosophy:**
```
goal → plan → action → judge → feedback → next iteration
```

### Key Features

- **Iterative Optimization**: Every execution produces a trajectory; every trajectory gets evaluated; feedback drives the next iteration
- **Checkpoint & Resume**: Full state persistence allows tasks to pause and resume at any point
- **Skill-Driven Evaluation**: Task-specific judge skills define custom evaluation criteria
- **Tool System**: Extensible tool provider architecture supporting built-in tools and MCP-style external providers
- **Multi-Role Orchestration**: Plan, Action, and Judge roles work together in a closed loop

### Installation

```bash
pip install nano-ant
```

Or install from source:

```bash
git clone https://github.com/Halucinaut/Nano-ant.git
cd Nano-ant
pip install -e .
```

### Quick Start

#### 1. Interactive Mode

```bash
ant
```

Then type your task:
```
/run ./examples/product_prompt_sample
```

#### 2. Command Line

```bash
nano-ant "Create a simple calculator with add and subtract functions"
```

#### 3. Template Mode (for Prompt Optimization)

Create a task directory with:
- `prompt.txt` - The prompt to optimize
- `cases.json` - Test cases
- `judge_skill.yaml` - Evaluation criteria

Then run:
```bash
ant ./my_task
```

### Configuration

Create `config.yaml`:

```yaml
llm:
  backend: "http"  # or "claude_code"
  default:
    model: "gpt-4"
    base_url: "https://api.openai.com/v1"
    api_key: "your-api-key"

agent:
  max_iterations: 10
  early_stop_rounds: 3
```

### Project Structure

```
my_task/
├── ant.yaml              # Task definition
├── prompt.txt            # Target to optimize
├── cases.json            # Test cases
├── judge_skill.yaml      # Evaluation criteria
└── eval_runner.py        # Custom evaluator (optional)
```

### Architecture

```
┌─────────────────────────────────────────┐
│            Orchestrator                 │
│   Controls iteration loop & state       │
└─────────────┬───────────────────────────┘
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
┌───────┐ ┌───────┐ ┌───────┐
│ Plan  │ │ Action│ │ Judge │
│ Role  │ │ Role  │ │ Role  │
└───────┘ └───────┘ └───────┘
    │         │         │
    └─────────┼─────────┘
              ▼
       Feedback / State
              │
              ▼
        Next Iteration
```

### Documentation

- [DESIGN.md](./DESIGN.md) - Architecture and design decisions
- [examples/](./examples/) - Example tasks and use cases

### Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

### License

MIT License - see [LICENSE](./LICENSE) for details.

---

## 中文

### Nano Ant 是什么？

Nano Ant 是一个轻量级 Agent 框架，将**训练循环思想**引入任务执行。不同于一次性生成，Nano Ant 通过迭代执行、评估和改进，直到任务收敛到高质量解决方案。

**核心理念：**
```
目标 → 计划 → 执行 → 评估 → 反馈 → 下一轮迭代
```

### 主要特性

- **迭代优化**: 每次执行产生轨迹，每次轨迹被评估，反馈驱动下一轮
- **检查点与恢复**: 完整状态持久化，支持任意点暂停和恢复
- **技能驱动评估**: 任务特定的评估技能定义自定义评估标准
- **工具系统**: 可扩展的工具提供者架构，支持内置工具和 MCP 风格外部提供者
- **多角色编排**: Plan、Action、Judge 角色在闭环中协同工作

### 安装

```bash
pip install nano-ant
```

或从源码安装：

```bash
git clone https://github.com/Halucinaut/Nano-ant.git
cd Nano-ant
pip install -e .
```

### 快速开始

#### 1. 交互模式

```bash
ant
```

然后输入任务：
```
/run ./examples/product_prompt_sample
```

#### 2. 命令行

```bash
nano-ant "创建一个支持加减乘除的简单计算器"
```

#### 3. 模板模式（用于 Prompt 优化）

创建任务目录，包含：
- `prompt.txt` - 待优化的 prompt
- `cases.json` - 测试用例
- `judge_skill.yaml` - 评估标准

然后运行：
```bash
ant ./my_task
```

### 配置

创建 `config.yaml`：

```yaml
llm:
  backend: "http"  # 或 "claude_code"
  default:
    model: "gpt-4"
    base_url: "https://api.openai.com/v1"
    api_key: "your-api-key"

agent:
  max_iterations: 10
  early_stop_rounds: 3
```

### 项目结构

```
my_task/
├── ant.yaml              # 任务定义
├── prompt.txt            # 优化目标
├── cases.json            # 测试用例
├── judge_skill.yaml      # 评估标准
└── eval_runner.py        # 自定义评估器（可选）
```

### 架构

```
┌─────────────────────────────────────────┐
│            Orchestrator                 │
│      控制迭代循环和状态                  │
└─────────────┬───────────────────────────┘
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
┌───────┐ ┌───────┐ ┌───────┐
│ Plan  │ │ Action│ │ Judge │
│ Role  │ │ Role  │ │ Role  │
└───────┘ └───────┘ └───────┘
    │         │         │
    └─────────┼─────────┘
              ▼
       反馈 / 状态
              │
              ▼
        下一轮迭代
```

### 文档

- [DESIGN.md](./DESIGN.md) - 架构和设计决策
- [examples/](./examples/) - 示例任务和用例

### 贡献

欢迎贡献！请随时提交 issue 和 pull request。

### 许可证

MIT 许可证 - 详见 [LICENSE](./LICENSE)
