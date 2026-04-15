# Zao Tagging External Case

这个 sample 用来演示 `Nano Ant` 如何通过统一 `ant.yaml` 接入外部项目 `zao-workflow`，并把 `prompts/tagging/classification.md` 作为优化目标。

当前协议只有三件事：`prompt_use.md`、现成外部脚本、结果 JSON。

- `prompt_use.md` 是 Nano Ant 每轮直接修改的工作副本
- 运行前会同步到 `${ZAO_WORKFLOW_PATH}/prompts/tagging/classification.md`
- 然后直接执行外部项目已有脚本 `tests/unit/test_tagging_classify&summarize.py`
- 最后读取 `${ZAO_WORKFLOW_PATH}/logs/test_tagging_result_*.json`

## 目录说明

- `ant.yaml`：统一任务定义
- `prompt_use.md`：工作副本 prompt
- `judge_skills/tagging_quality_skill.yaml`：示例审核 skill

## 运行

```bash
export ZAO_WORKFLOW_PATH=/Users/sunrx/Project/zao-workflow
ant --interactive --project /Users/sunrx/idea/Nano\ ant/examples/external_zao_tagging_case
```

进入交互界面后直接输入：

```text
/run .
```
