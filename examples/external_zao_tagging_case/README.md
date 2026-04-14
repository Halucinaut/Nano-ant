# Zao Tagging External Case

这个 sample 用来演示 `Nano Ant` 如何通过统一 `ant.yaml` 接入外部项目 `zao-workflow`，并把 `prompts/tagging/classification.md` 作为优化目标。

评估入口不改外部项目代码，只在 `Nano Ant` 侧包装外部单测：

- 真实模式：调用 `tests/unit/test_tagging_classify&summarize.py`
- 离线模式：使用 mock 结果验证 `Nano Ant -> ExternalTask -> evaluator -> Judge` 这条链路

## 目录说明

- `ant.yaml`：统一任务定义
- `cases/tagging_cases.json`：样例评测用例
- `judge_skills/tagging_quality_skill.yaml`：示例审核 skill
- `evaluate_zao_tagging.py`：外部评估适配器

## 离线 smoke test

先设置项目路径和 mock 模式：

```bash
export ZAO_WORKFLOW_PATH=/Users/sunrx/Project/zao-workflow
export ZAO_TAGGING_EVAL_MODE=mock
```

直接验证评估器：

```bash
python3 /Users/sunrx/idea/Nano\ ant/examples/external_zao_tagging_case/evaluate_zao_tagging.py \
  --project-path "$ZAO_WORKFLOW_PATH" \
  --cases /Users/sunrx/idea/Nano\ ant/examples/external_zao_tagging_case/cases/tagging_cases.json \
  --mode mock
```

查看统一任务目录是否能被 `Nano Ant` 识别：

```bash
python3 -m nano_ant.cli /Users/sunrx/idea/Nano\ ant/examples/external_zao_tagging_case
```

## 连上内网后的真实运行

切换到真实模式：

```bash
export ZAO_TAGGING_EVAL_MODE=real
```

先单独跑评估器：

```bash
python3 /Users/sunrx/idea/Nano\ ant/examples/external_zao_tagging_case/evaluate_zao_tagging.py \
  --project-path "$ZAO_WORKFLOW_PATH" \
  --cases /Users/sunrx/idea/Nano\ ant/examples/external_zao_tagging_case/cases/tagging_cases.json \
  --mode real
```

确认外部项目链路能通后，再运行 `Nano Ant`：

```bash
ant --interactive --project /Users/sunrx/idea/Nano\ ant/examples/external_zao_tagging_case
```

进入交互界面后直接输入：

```text
/run .
```
