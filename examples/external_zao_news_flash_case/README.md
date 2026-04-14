# Zao Workflow External Case

这是一个较早的 external 样例。当前更推荐统一任务目录模式，而不是继续使用旧的 `--external-task-config` 入口。

目标不是在 Nano Ant 内部优化 prompt，而是直接优化外部项目 [zao-workflow](/Users/sunrx/Project/zao-workflow) 里的快讯文稿 prompt：

- 外部 prompt 路径：`prompts/script/news_flash.md`
- 外部执行入口：`scripts/run_script.py`
- 外部处理器：`core/script/processor.py`

## 使用前提

先设置外部项目路径：

```bash
export ZAO_WORKFLOW_PATH=/Users/sunrx/Project/zao-workflow
```

然后确认外部项目自己的 `config.yaml` 已经填好了真实可用的模型配置。  
如果外部项目还是默认的 `https://api.example.com/v1`，这个 case 无法真正跑通。

## 运行方式

如果你只是参考旧适配方式，可以继续这样运行：

```bash
ant --external-task-config examples/external_zao_news_flash_case/config.yaml --resource-id script/news_flash --max-iter 0
```

真正开始迭代优化：

```bash
ant --external-task-config examples/external_zao_news_flash_case/config.yaml --resource-id script/news_flash
```

## 这个 case 会做什么

1. 把外部项目里的 `prompts/script/news_flash.md` 作为待优化目标
2. 每轮保存修改后的 prompt 到外部项目
3. 调用本目录下的 `evaluate_zao_news_flash.py`
4. `evaluate_zao_news_flash.py` 再调用外部项目的 `scripts/run_script.py`
5. 用 `cases/news_flash_cases.json` 检查输出是否符合快讯口播要求
6. Judge 再基于 `judge_skills/news_flash_skill.yaml` 做更高层的审核

## 重点边界

- 这是 external mode，不会把外部项目迁移进 Nano Ant
- Nano Ant 只负责迭代优化循环
- 外部项目继续保持自己的结构、processor 和执行方式
