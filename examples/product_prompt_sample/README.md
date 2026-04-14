# Product Prompt Sample

这是一个给产品同学直接模仿的 sample。统一入口是 `ant.yaml`。

## 快速开始

先在 sample 目录里跑一次本地评估：

```bash
cd examples/product_prompt_sample
python eval_runner.py
```

如果评估脚本能正常生成 `eval_report.json`，再进入 Nano Ant：

```bash
ant --interactive --project .
```

进入后输入：

```text
/run .
```

## 这个 sample 适合模仿什么

适合模仿以下场景：

- 客服回复 prompt 优化
- 工作流节点 prompt 优化
- 结构化输出 prompt 优化
- 某类常见业务问答 prompt 优化

## 产品同学只需要改哪些文件

- `prompt.txt`
- `cases.json`
- `judge_skill.yaml`

大多数情况下，这三个文件改完就够了。

如果最终业务模型不是当前默认模型，再修改：

- `target_llm.yaml`
