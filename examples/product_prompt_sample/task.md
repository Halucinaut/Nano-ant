# Product Prompt Sample

这是一个给产品同学参考的最小可运行 sample。

你可以把它理解成一个标准模板：

- `prompt.txt`：当前正在优化的 prompt
- `cases.json`：代表性业务样例
- `judge_skill.yaml`：审核标准
- `target_llm.yaml`：真正跑这个业务 prompt 的模型配置
- `eval_runner.py`：本地评估脚本

推荐使用方式：

1. 确认 `target_llm.yaml` 里的模型配置可用
2. 在当前目录下运行 `python eval_runner.py`，确认样例可以出结果
3. 运行 `ant --config ../../config.yaml`
4. 在交互界面里输入 `/optimize`

如果你要做自己的业务任务，最简单的方法就是直接复制这个目录，然后修改：

- `prompt.txt`
- `cases.json`
- `judge_skill.yaml`

如果业务 prompt 最终跑在别的模型上，直接修改 `target_llm.yaml`。
