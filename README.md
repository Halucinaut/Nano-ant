```text
            ██      ██
          ████    ████
        ████████████████
      ████  ████████  ████
    ████  ████████████  ████
      ██  ██  ████  ██  ██
          ██  ████  ██
        ████  ████  ████
      ████    ████    ████
```

# Nano Ant

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[English README](./README_EN.md)

## 这个项目是怎么来的

很多任务表面上在做生成，真正难的是迭代。一个 prompt 第一次写出来通常只能跑通一部分样本；一个工作流节点在新数据上总会暴露新的边界问题；一个已经上线的脚本，稳定性往往来自反复修改、反复运行、反复审查。团队平时处理这类问题的方法很朴素：先试一次，拿结果，找问题，修，再跑一轮。

`Nano Ant` 就是沿着这个思路做出来的。它不试图吞掉业务系统，也不试图把一切任务包装成一个庞大的自治平台。它只包住那条最关键的闭环：给定一个明确的优化对象，让 Agent 能连续执行、连续评估、连续修正，把一次性生成变成可迭代优化。

这个想法来自对很多领域共通问题的观察：新闻生产里的 prompt 调优、客服工作流的话术修正、内容审核节点的输出稳定性、已有脚本在新样本上的回归问题。这些任务都在重复同一件事：它们需要一个轻量的外壳，去承载“执行结果驱动下一轮改进”的过程。

## 项目愿景

`Nano Ant` 面向所有需要迭代优化的任务。它希望把“自我进化”的感觉落到可运行的工程闭环里：执行、评估、反馈、下一轮修正。优化对象可以是 prompt、规则、局部流程，也可以继续扩展到更多可编辑的任务资产。框架本身保持轻量，只要求用户提供一个可优化对象、一个可运行回路、一个评审标准。

## 适合谁用

产品同学可以用它优化 prompt 和工作流节点；应用工程师可以把已有项目、已有脚本、已有流程接进来做迭代优化；Agent 工程研究者可以把它当作一个专注在 harness、judge 和自我进化的小型运行时。

## 它怎么工作

你给 `Nano Ant` 一个任务目录。目录里放任务描述、当前使用的 `prompt_use.md`、评审用的 `judge_skill.yaml`，以及一个现成的运行脚本。每一轮里，`Nano Ant` 修改优化对象，调用现有运行脚本，读取结构化结果文件，再让 Judge 基于结果和评审规则给出下一轮修正方向。外部项目继续保留自己的执行逻辑，`Nano Ant` 只负责迭代优化。

## 和其他框架的差异

| 项目 | 公开定位 | 与 Nano Ant 的差异 |
| --- | --- | --- |
| [Voyager](https://voyager.minedojo.org/) | 面向 Minecraft 的开放世界长期学习代理，核心模块是自动课程、技能库和基于环境反馈的迭代提示 | `Nano Ant` 不做具身探索，不维护开放世界技能树，主目标是业务任务里的局部优化闭环 |
| [Reflexion](https://proceedings.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html) | 通过 verbal feedback 和 episodic memory 让语言代理在多次试错中持续改进 | `Nano Ant` 受它启发，但重点放在任务目录、结果协议、JudgeSkill 和可接已有流程的工程运行时 |
| [AgentVerse](https://github.com/OpenBMB/AgentVerse) | 面向多 Agent 协作与 simulation 的框架，公开提供 task-solving 和 simulation 两条主线 | `Nano Ant` 当前不追求多 Agent 社会化协作，主线是单任务、多轮优化 |
| [Hermes Agent](https://github.com/nousresearch/hermes-agent) | 长期运行、自学习、跨平台常驻代理，包含学习闭环、调度、技能生成、消息网关和完整终端界面 | `Nano Ant` 的边界更窄，聚焦单个任务目录里的迭代收敛，不承担全能个人代理的职责 |
| [EvoMap](https://evomap.ai/) | 面向 AI self-evolution 的基础设施，强调 GEP、agent-to-agent capability inheritance、资产评分和共享 | `Nano Ant` 当前不做协议网络和能力市场，只关心本地任务怎样一轮轮变好 |

一句话概括差异：很多框架在扩张 Agent 的能力边界，`Nano Ant` 在压缩迭代优化的接入成本。

## 当前支持与版本路线

| 版本 | 用户可见能力 | 状态 |
| --- | --- | --- |
| v0.3.x | 内部任务目录运行、外部项目接入、基于 `prompt_use.md` 的多轮 prompt 优化、JudgeSkill、checkpoint、交互式 `ant` CLI、本地配置隔离 | 已支持 |
| v0.4.x | 更多面向产品同学的任务模板、更多可优化对象、统一任务包分发方式 | 计划中 |
| v0.5.x | 更强的跨任务策略复用、更完整的自我进化沉淀、更广的 workflow 优化场景 | 计划中 |

## 安装

```bash
git clone https://github.com/Halucinaut/Nano-ant.git
cd "Nano ant"
pip install -e .
```

安装完成后可以直接使用：

```bash
ant
```

## 本地配置

推荐做法是新建本地的 `config.local.yaml`，再显式传给 CLI。

```yaml
llm:
  backend: "http"
  default:
    model: "Qwen3-30B-A3B"
    base_url: "${NANO_ANT_BASE_URL}"
    api_key: "${NANO_ANT_API_KEY}"
```

运行时使用：

```bash
ant --config config.local.yaml
```

## 从哪里开始

最短路径是直接进入交互界面，然后运行一个任务目录：

```bash
ant --config config.local.yaml
```

进入后：

```text
/run ./examples/product_prompt_sample
```

如果你要接外部项目，可以看这里：

- [内部任务 sample](./examples/product_prompt_sample/README.md)
- [外部任务 sample](./examples/external_zao_tagging_case/README.md)

详细的任务协议、sample 目录结构和接入方式都放在各自 sample 目录里，不写在首页。

## 开源协议

本项目当前采用 [MIT License](./LICENSE)。

## 仓库状态

当前仓库处于快速迭代阶段。主路径已经稳定在 `ant + 任务目录` 这套使用方式上；sample、任务协议和部分运行细节还会继续收敛。
