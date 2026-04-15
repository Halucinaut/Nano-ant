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

[中文 README](./README.md)

## Where This Project Came From

Many tasks look like generation problems on the surface, but the hard part is iteration. A prompt rarely works well on the first pass; a workflow node breaks on new samples; a script that already ships still needs repeated correction to stay stable. Teams handle these problems in a simple loop: run once, inspect the result, identify the failure, revise, and run again.

`Nano Ant` was built around that loop. It does not try to absorb the business system, and it does not try to turn every task into a large autonomous platform. It focuses on one narrow runtime problem: given a clear optimization target, let an agent execute, evaluate, revise, and improve across iterations.

The idea came from the same pattern showing up in different domains: prompt tuning in news production, script refinement in workflow systems, quality stabilization in review pipelines, regression fixing in existing task scripts. These tasks all need the same thing: a lightweight shell around “execution result drives the next revision.”

## Vision

`Nano Ant` is built for any task that benefits from iterative optimization. The long-term goal is to make self-improvement feel operational: execute, evaluate, feed back, revise, and repeat. The optimization target can be a prompt, a rule set, or a workflow fragment today, and broader editable task assets later. The framework stays intentionally small and only asks for a target, a runnable loop, and a judging rule.

## Who It Is For

Product teams can use it to improve prompts and workflow nodes. Application engineers can connect existing scripts and existing projects into an optimization loop. Agent builders can use it as a compact runtime for harness, judging, and self-improvement experiments.

## How It Works

You give `Nano Ant` a task directory. The directory contains the task description, the current `prompt_use.md`, a `judge_skill.yaml`, and an existing run script. On each iteration, `Nano Ant` edits the optimization target, calls the existing run script, reads a structured result file, and lets the Judge decide what should change next. The external project keeps its own execution logic. `Nano Ant` owns the iterative loop.

## How It Differs From Other Frameworks

| Project | Public Positioning | Difference From Nano Ant |
| --- | --- | --- |
| Voyager | An open-ended embodied lifelong learning agent for Minecraft, centered on automatic curriculum, skill library, and iterative prompting from environment feedback | `Nano Ant` does not target embodied exploration or open-world skill accumulation. It targets local optimization loops inside business tasks |
| Reflexion | A framework that improves language agents through verbal feedback and episodic memory across repeated trials | `Nano Ant` borrows the iterative spirit, but focuses on task directories, result protocols, JudgeSkill, and integration with existing runnable systems |
| AgentVerse | A multi-agent framework organized around task-solving and simulation | `Nano Ant` does not optimize for social multi-agent coordination. Its main path is single-task, multi-iteration optimization |
| Hermes Agent | A persistent self-improving agent with learning loop, scheduling, skill creation, multi-platform messaging, and a full terminal product surface | `Nano Ant` keeps a narrower boundary. It focuses on convergence inside one task directory instead of acting as a general personal agent |
| EvoMap | Infrastructure for AI self-evolution with GEP, agent-to-agent capability inheritance, and shared evolution assets | `Nano Ant` does not build a protocol network or capability marketplace. It focuses on making one local task improve across iterations |

The short version: many frameworks expand the operating surface of agents; `Nano Ant` reduces the integration cost of iterative optimization.

## What Is Supported Now

| Version | User-Facing Capability | Status |
| --- | --- | --- |
| v0.3.x | Internal task directories, external project integration, multi-round prompt optimization through `prompt_use.md`, JudgeSkill, checkpoints, interactive `ant` CLI, local config isolation | Available |
| v0.4.x | More task templates for product teams, more optimization target types, standardized task-pack distribution | Planned |
| v0.5.x | Stronger cross-task strategy reuse, deeper self-improvement accumulation, broader workflow optimization coverage | Planned |

## Installation

```bash
git clone https://github.com/Halucinaut/Nano-ant.git
cd "Nano ant"
pip install -e .
```

After installation:

```bash
ant
```

## Local Configuration

Tracked config files keep placeholders only. Real `base_url` and `api_key` should stay in a local file outside git history. The recommended pattern is a local `config.local.yaml`, passed explicitly to the CLI.

```yaml
llm:
  backend: "http"
  default:
    model: "Qwen3-30B-A3B"
    base_url: "${NANO_ANT_BASE_URL}"
    api_key: "${NANO_ANT_API_KEY}"
```

Run with:

```bash
ant --config config.local.yaml
```

## Where To Start

The shortest path is to open the interactive shell and run a task directory.

```bash
ant --config config.local.yaml
```

Then inside the shell:

```text
/run ./examples/product_prompt_sample
```

If you want to connect an external project, start with these samples:

- [Internal task sample](./examples/product_prompt_sample/README.md)
- [External task sample](./examples/external_zao_tagging_case/README.md)

Detailed task protocols and integration instructions live inside each sample directory rather than on the homepage.

## Reference Projects

- [Voyager](https://voyager.minedojo.org/)
- [Reflexion](https://proceedings.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html)
- [AgentVerse](https://github.com/OpenBMB/AgentVerse)
- [Hermes Agent](https://github.com/nousresearch/hermes-agent)
- [EvoMap](https://evomap.ai/)
