# Nano Ant - 通用迭代优化框架设计

## Context

**Problem**: 用户希望用 Nano Ant 框架来优化 Zao Workflow 项目中的 prompt，同时让 Nano Ant 成为一个通用的、面向所有人可用的框架。

**Core Insight**: Nano Ant 的本质是 **迭代优化循环**，而不是"prompt 优化工具"。任何"评估→改进→迭代"的任务都可以用 Nano Ant 来完成。

**Goal**: 将 Nano Ant 打造成通用的迭代优化框架，支持两种使用模式。

---

## 核心架构：两种使用模式

### 模式一：内部模式 (Internal Mode)

**场景**：用户把优化目标、测试用例、执行脚本都放在 Nano Ant 内部。

**特点**：
- Nano Ant 控制一切：资源加载、执行、评估、迭代
- 用户按照 Nano Ant 的规范准备材料
- 类似于现有的 Template Mode，但更通用

```
┌─────────────────────────────────────────────────────────────────┐
│                     Nano Ant Workspace                           │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  tasks/my_optimization_task/                            │   │
│   │   ├── target.md          # 待优化的目标（prompt/代码等） │   │
│   │   ├── cases.json         # 测试用例                      │   │
│   │   ├── judge_skill.yaml   # 评估标准                      │   │
│   │   ├── eval_runner.py     # 评估脚本（可选，有默认实现）  │   │
│   │   └── config.yaml        # 任务配置                      │   │
│   └─────────────────────────────────────────────────────────┘   │
│                             │                                    │
│                             ▼                                    │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              Nano Ant Orchestrator                       │   │
│   │   Plan → Action → Judge → Feedback → Iterate             │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 模式二：外部模式 (External Mode)

**场景**：用户外部已有成熟的项目、执行流程和评估体系，只想借用 Nano Ant 的迭代优化能力。

**特点**：
- 外部项目保持独立，有自己的结构和依赖
- Nano Ant 只负责迭代优化循环
- 通过适配器对接外部项目

```
┌─────────────────────────────────────────────────────────────────┐
│               External Project (e.g. Zao Workflow)              │
│   - prompts/script/*.md          # 外部的 prompt 文件           │
│   - core/script/processor.py     # 外部的执行逻辑               │
│   - tests/                       # 外部的测试                   │
└────────────────────────────┬────────────────────────────────────┘
                             │ 通过适配器对接
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Nano Ant External Adapter                      │
│   - ExternalResourceLoader: 加载外部资源                         │
│   - ExternalExecutor: 调用外部执行逻辑                           │
│   - ExternalEvaluator: 获取外部评估结果                          │
└────────────────────────────┬────────────────────────────────────┘
                             │ 提供标准化接口
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Nano Ant Orchestrator                          │
│   Plan → Action → Judge → Feedback → Iterate                     │
│   (复用现有逻辑，不区分内部/外部)                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 共同点：JudgeSkill

无论内部模式还是外部模式，都需要 **JudgeSkill** 来定义评估标准。JudgeSkill 是用户与 Nano Ant 评估系统的核心接口。

---

## 详细设计

### 一、内部模式设计

内部模式是现有 Template Mode 的泛化和标准化。

#### 1.1 任务目录结构

```
nano_ant_workspace/
├── tasks/
│   ├── prompt_optimization/           # 任务示例：prompt 优化
│   │   ├── target.md                  # 待优化的 prompt
│   │   ├── cases.json                 # 测试用例
│   │   ├── judge_skill.yaml           # 评估标准
│   │   ├── eval_runner.py             # 评估脚本（可选，有默认实现）
│   │   └── config.yaml                # 任务配置
│   │
│   └── code_refactor/                 # 任务示例：代码重构
│       ├── target.py                  # 待优化的代码
│       ├── test_cases.py              # 测试用例
│       ├── judge_skill.yaml           # 评估标准
│       └── config.yaml
```

#### 1.2 核心接口

**InternalTask** - 内部任务的抽象

```python
@dataclass
class InternalTask:
    """内部模式的任务定义"""
    
    # 任务标识
    task_type: str              # "prompt_optimization" | "code_refactor" | ...
    task_name: str              # 具体任务名
    
    # 资源路径
    task_dir: str               # 任务目录路径
    target_file: str            # 待优化的目标文件
    cases_file: str             # 测试用例文件
    judge_skill_file: str       # 评估标准文件
    eval_runner_file: str       # 评估脚本（可选）
    
    # 配置
    config: TaskConfig          # 任务配置
    
    # 运行时
    current_state: dict         # 当前状态
    best_state: dict            # 最佳状态
    
    def load_target(self) -> str:
        """加载待优化目标"""
    
    def save_target(self, content: str):
        """保存优化后的目标"""
    
    def load_cases(self) -> list[dict]:
        """加载测试用例"""
    
    def load_judge_skill(self) -> JudgeSkill:
        """加载评估标准"""
    
    def run_evaluation(self, target_content: str) -> EvalReport:
        """运行评估"""
    
    def build_user_goal(self) -> str:
        """构建用户目标，传给 Orchestrator"""
    
    def build_plan_context(self) -> str:
        """构建 PlanRole 的上下文"""
    
    @classmethod
    def from_dir(cls, task_dir: str) -> "InternalTask":
        """从任务目录加载"""
```

#### 1.3 默认 eval_runner 设计

Nano Ant 提供内置的默认评估器，用户无需编写 eval_runner.py：

```python
# nano_ant/tasks/default_eval_runner.py

class DefaultEvalRunner:
    """内置默认评估器 - 无需用户编写 eval_runner.py"""
    
    def __init__(self, llm_config: dict):
        self.llm_config = llm_config
    
    def evaluate(
        self,
        prompt: str,
        cases: list[dict],
    ) -> EvalReport:
        """默认评估逻辑：
        1. 遍历每个 case
        2. 用 target_llm + prompt 处理 case.input
        3. 检查输出是否包含 expected_contains
        4. 检查输出是否不包含 must_not_contain
        5. 汇总结果
        """
        results = []
        for case in cases:
            output = self._call_llm(prompt, case.get("input", ""))
            case_result = self._check_case(output, case)
            results.append(case_result)
        
        return EvalReport(
            total_cases=len(cases),
            successful_cases=sum(1 for r in results if r["success"]),
            success_rate=sum(1 for r in results if r["success"]) / len(cases),
            overall_score=self._calculate_score(results),
            case_results=results,
        )
    
    def _call_llm(self, prompt: str, case_input: str) -> str:
        """调用目标 LLM - 支持多种后端：HTTP API、Claude Code CLI"""
        ...
    
    def _check_case(self, output: str, case: dict) -> dict:
        """检查单个 case"""
        expected = case.get("expected_contains", [])
        forbidden = case.get("must_not_contain", [])
        
        passed = []
        failed = []
        
        for phrase in expected:
            if phrase in output:
                passed.append(f"contains: {phrase}")
            else:
                failed.append(f"missing: {phrase}")
        
        for phrase in forbidden:
            if phrase in output:
                failed.append(f"forbidden: {phrase}")
            else:
                passed.append(f"not_contains: {phrase}")
        
        return {
            "name": case.get("name", "unnamed"),
            "success": len(failed) == 0,
            "passed_checks": passed,
            "failed_checks": failed,
        }
```

**cases.json 格式（默认评估器支持）**：

```json
[
  {
    "name": "basic_test",
    "input": "用户输入内容",
    "expected_contains": ["必须包含的关键词1", "必须包含的关键词2"],
    "must_not_contain": ["禁止出现的词1", "禁止出现的词2"]
  }
]
```

用户也可以提供自定义 eval_runner.py，框架会优先使用自定义版本。

#### 1.4 使用方式

```python
from nano_ant import Orchestrator
from nano_ant.tasks import InternalTask

# 加载任务（无需 eval_runner.py，使用默认评估器）
task = InternalTask.from_dir("tasks/prompt_optimization")

# 运行优化
orchestrator = Orchestrator.from_config_file("config.yaml")
result = orchestrator.run(
    user_goal=task.build_user_goal(),
    task_context=task,
)
```

#### 1.5 CLI 命令

```bash
# 创建新任务
ant task create prompt_optimization --name my_prompt_task

# 运行任务
ant task run tasks/my_prompt_task

# 查看任务状态
ant task status tasks/my_prompt_task
```

---

### 二、外部模式设计

外部模式通过适配器对接已有项目。

#### 2.1 两层适配器架构

```
ExternalAdapter (抽象基类)
    │
    ├── GenericFileAdapter      # 通用文件适配器：读写文件系统
    │   │
    │   ├── ZaoWorkflowAdapter  # Zao Workflow：继承，定制执行逻辑
    │   └── OtherProjectAdapter # 其他项目：类似继承
    │
    └── GenericAPIAdapter       # 通用 API 适配器：通过 HTTP 对接
        │
        └── RemoteServiceAdapter # 远程服务：继承
```

**层级职责**：

| 层级 | 职责 | 示例 |
|------|------|------|
| **ExternalAdapter** | 定义抽象接口 | `load_resource()`, `save_resource()`, `execute()`, `evaluate()` |
| **GenericFileAdapter** | 实现文件系统操作 | 读写 `.md`, `.py`, `.json` 文件 |
| **ZaoWorkflowAdapter** | 定制项目特定的执行逻辑 | 调用 `ScriptProcessor._generate_script()` |

#### 2.2 适配器接口

**ExternalAdapter** - 外部适配器的抽象基类

```python
class ExternalAdapter(ABC):
    """外部模式适配器的抽象基类"""
    
    @abstractmethod
    def load_resource(self, resource_id: str) -> str:
        """加载外部资源"""
    
    @abstractmethod
    def save_resource(self, resource_id: str, content: str):
        """保存资源到外部"""
    
    @abstractmethod
    def execute(self, resource_content: str, context: dict) -> dict:
        """调用外部执行逻辑"""
    
    @abstractmethod
    def evaluate(self, execution_result: dict) -> EvalReport:
        """获取外部评估结果"""
```

**GenericFileAdapter** - 通用文件适配器

```python
class GenericFileAdapter(ExternalAdapter):
    def __init__(self, project_path: str, resources_dir: str = ""):
        self.project_path = project_path
        self.resources_dir = resources_dir
    
    def load_resource(self, resource_id: str) -> str:
        path = self._resolve_path(resource_id)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    
    def save_resource(self, resource_id: str, content: str):
        path = self._resolve_path(resource_id)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    
    def _resolve_path(self, resource_id: str) -> str:
        # resource_id: "script/news_flash" -> "prompts/script/news_flash.md"
        return os.path.join(self.project_path, self.resources_dir, f"{resource_id}.md")
    
    # execute() 和 evaluate() 由子类实现
```

**ZaoWorkflowAdapter** - Zao Workflow 适配器

```python
class ZaoWorkflowAdapter(GenericFileAdapter):
    def __init__(self, project_path: str):
        super().__init__(project_path, resources_dir="prompts")
        self.integration_dir = os.path.join(project_path, "integration")
    
    def execute(self, resource_content: str, context: dict) -> dict:
        """调用 Zao Workflow 的 processor"""
        import sys
        sys.path.insert(0, self.project_path)
        from core.script.processor import ScriptProcessor
        
        processor = ScriptProcessor()
        return processor._generate_script(
            integrated_data=context.get("integrated_data"),
            content_type=context.get("content_type"),
        )
    
    def evaluate(self, execution_result: dict) -> EvalReport:
        """运行 Zao Workflow 的评估脚本"""
        eval_script = os.path.join(self.integration_dir, "eval_runner.py")
        # 执行并解析结果
        ...
```

#### 2.3 外部任务封装

```python
@dataclass
class ExternalTask:
    """外部模式的任务定义"""
    
    # 任务标识
    task_type: str = "external"
    task_name: str = ""
    
    # 外部项目信息
    project_path: str = ""
    resource_id: str = ""           # 如 "script/news_flash"
    
    # 适配器
    adapter: ExternalAdapter
    
    # 评估标准
    judge_skill: JudgeSkill
    
    # 配置
    config: TaskConfig
    
    # 运行时
    current_state: dict = field(default_factory=dict)
    best_state: dict = field(default_factory=dict)
    
    def load_target(self) -> str:
        return self.adapter.load_resource(self.resource_id)
    
    def save_target(self, content: str):
        self.adapter.save_resource(self.resource_id, content)
    
    def execute(self, target_content: str, context: dict) -> dict:
        return self.adapter.execute(target_content, context)
    
    def evaluate(self, execution_result: dict) -> EvalReport:
        return self.adapter.evaluate(execution_result)
    
    @classmethod
    def from_config(cls, config_path: str) -> "ExternalTask":
        """从配置文件加载"""
```

#### 2.4 外部项目的集成目录

外部项目需要提供最小的集成信息：

```
zao-workflow/
├── prompts/                       # 外部项目原有的 prompt
│   └── script/
│       ├── news_flash.md
│       └── ...
│
├── integration/                   # 新增：Nano Ant 集成配置
│   ├── config.yaml                # 集成配置
│   ├── judge_skills/              # JudgeSkill 定义
│   │   └── news_flash_skill.yaml
│   └── eval_runner.py             # 评估脚本（可选）
```

**config.yaml** 示例:

```yaml
project:
  name: zao-workflow
  type: external
  
adapter:
  type: zao_workflow               # 使用预置的适配器类型

resources:
  - id: script/news_flash
    skill: judge_skills/news_flash_skill.yaml
    pass_threshold: 82
    
  - id: script/classification
    skill: judge_skills/classification_skill.yaml
    pass_threshold: 85
```

#### 2.5 使用方式

```python
from nano_ant import Orchestrator
from nano_ant.integration import ExternalTask

# 加载外部任务
task = ExternalTask.from_config(
    "/path/to/zao-workflow/integration/config.yaml",
    resource_id="script/news_flash",
)

# 运行优化
orchestrator = Orchestrator.from_config_file("config.yaml")
result = orchestrator.run(
    user_goal=task.build_user_goal(),
    task_context=task,
)
```

---

### 三、统一接口：TaskContext

两种模式最终都通过 **TaskContext** 与 Orchestrator 交互：

```python
class TaskContext(ABC):
    """任务上下文的统一接口 - Orchestrator 只认识这个"""
    
    @abstractmethod
    def load_target(self) -> str:
        """加载待优化目标"""
    
    @abstractmethod
    def save_target(self, content: str):
        """保存优化后的目标"""
    
    @abstractmethod
    def evaluate(self) -> EvalReport:
        """运行评估"""
    
    @abstractmethod
    def get_judge_skill(self) -> JudgeSkill:
        """获取评估标准"""
    
    @abstractmethod
    def build_user_goal(self) -> str:
        """构建用户目标"""
    
    @abstractmethod
    def build_plan_context(self) -> str:
        """构建 PlanRole 上下文"""


# InternalTask 和 ExternalTask 都实现 TaskContext
class InternalTask(TaskContext): ...
class ExternalTask(TaskContext): ...
```

**Orchestrator 的修改**：

```python
class Orchestrator:
    def run(
        self,
        user_goal: str,
        task_context: TaskContext | None = None,  # 新增参数
    ):
        # 如果提供了 task_context，使用它来获取资源
        if task_context:
            self.task_context = task_context
            user_goal = task_context.build_user_goal()
        
        # 后续逻辑不变，PlanRole/ActionRole/JudgeRole 通过 task_context 获取所需信息
        ...
```

---

## 模块结构

```
nano_ant/
├── core/                          # 核心（现有）
│   ├── orchestrator.py
│   └── ...
│
├── tasks/                         # 新增：内部模式
│   ├── __init__.py
│   ├── base.py                    # TaskContext 抽象
│   ├── internal_task.py           # InternalTask 实现
│   ├── default_eval_runner.py     # 默认评估器
│   └── templates/                 # 任务模板
│       ├── prompt_optimization/
│       └── code_refactor/
│
├── integration/                   # 新增：外部模式
│   ├── __init__.py
│   ├── external_task.py           # ExternalTask 实现
│   ├── adapter_base.py            # ExternalAdapter 抽象
│   └── adapters/                  # 预置适配器
│       ├── __init__.py
│       ├── generic_file_adapter.py
│       ├── generic_api_adapter.py
│       └── zao_workflow_adapter.py
│
├── judge/                         # 评估（现有 + 增强）
│   ├── skills.py                  # JudgeSkill
│   └── skill_templates/           # 新增：预置 skill 模板
│       ├── json_output_skill.yaml
│       └── content_quality_skill.yaml
│
└── cli.py                         # CLI（增强）
```

---

## 使用场景对比

| 场景 | 推荐模式 | 理由 |
|------|----------|------|
| 从零开始优化一个 prompt | 内部模式 | 所有资源都在 Nano Ant 内，简单直接 |
| 优化 Zao Workflow 的 prompt | 外部模式 | 项目已成熟，有现成的 processor 和流程 |
| 优化一个独立代码文件 | 内部模式 | 把文件放进 tasks/ 目录即可 |
| 接入公司的 AI 平台 | 外部模式 | 平台有现成的评估体系，用适配器对接 |
| 批量优化多个项目 | 外部模式 | 为每个项目写一个适配器 |

---

## TODO List

### Phase 1: 核心抽象（同时实现两种模式的基础）

- [ ] `nano_ant/tasks/__init__.py` - tasks 模块入口
- [ ] `nano_ant/tasks/base.py` - TaskContext 抽象接口（内部/外部模式统一接口）
- [ ] `nano_ant/tasks/internal_task.py` - 内部模式实现
- [ ] `nano_ant/tasks/default_eval_runner.py` - 默认评估器实现
- [ ] `nano_ant/integration/__init__.py` - integration 模块入口
- [ ] `nano_ant/integration/adapter_base.py` - ExternalAdapter 抽象基类
- [ ] `nano_ant/integration/external_task.py` - 外部模式实现

### Phase 2: 通用适配器（层级 2）

- [ ] `nano_ant/integration/adapters/__init__.py` - 适配器模块入口
- [ ] `nano_ant/integration/adapters/generic_file_adapter.py` - 通用文件适配器
- [ ] `nano_ant/integration/adapters/generic_api_adapter.py` - 通用 API 适配器（可选）

### Phase 3: 项目适配器（层级 3）

- [ ] `nano_ant/integration/adapters/zao_workflow_adapter.py` - Zao Workflow 适配器

### Phase 4: Orchestrator 适配

- [ ] 修改 `Orchestrator.run()` 支持 `task_context` 参数
- [ ] 确保 PlanRole/ActionRole/JudgeRole 能从 task_context 获取信息

### Phase 5: Zao Workflow 集成

- [ ] 在 Zao Workflow 创建 `integration/` 目录
- [ ] 编写 JudgeSkill YAML 文件（5个）
- [ ] 编写测试用例 JSON 文件
- [ ] 编写集成配置 config.yaml

### Phase 6: CLI & 测试

- [ ] 新增 `ant task` 命令组
- [ ] 编写集成测试
- [ ] 更新文档

---

## 关键文件清单

### Nano Ant (框架侧)

| Action | File Path | Description |
|--------|-----------|-------------|
| CREATE | `nano_ant/tasks/__init__.py` | tasks 模块入口 |
| CREATE | `nano_ant/tasks/base.py` | TaskContext 抽象接口 |
| CREATE | `nano_ant/tasks/internal_task.py` | 内部模式实现 |
| CREATE | `nano_ant/tasks/default_eval_runner.py` | 默认评估器（内置，无需用户编写） |
| CREATE | `nano_ant/integration/__init__.py` | integration 模块入口 |
| CREATE | `nano_ant/integration/adapter_base.py` | ExternalAdapter 抽象基类 (层级 1) |
| CREATE | `nano_ant/integration/external_task.py` | 外部模式实现 |
| CREATE | `nano_ant/integration/adapters/__init__.py` | 适配器模块入口 |
| CREATE | `nano_ant/integration/adapters/generic_file_adapter.py` | 通用文件适配器 (层级 2) |
| CREATE | `nano_ant/integration/adapters/zao_workflow_adapter.py` | Zao Workflow 适配器 (层级 3) |
| CREATE | `nano_ant/judge/skill_templates/__init__.py` | Skill 模板入口 |
| CREATE | `nano_ant/judge/skill_templates/json_output_skill.yaml` | JSON 输出验证模板 |
| CREATE | `nano_ant/judge/skill_templates/content_quality_skill.yaml` | 内容质量评估模板 |
| MODIFY | `nano_ant/__init__.py` | 导出新的类 |
| MODIFY | `nano_ant/agent/orchestrator.py` | 支持 task_context 参数 |
| MODIFY | `nano_ant/cli.py` | 新增 task 命令组 |

### Zao Workflow (外部项目侧)

| Action | File Path | Description |
|--------|-----------|-------------|
| CREATE | `integration/config.yaml` | 集成配置 |
| CREATE | `integration/judge_skills/news_flash_skill.yaml` | 快讯评估标准 |
| CREATE | `integration/judge_skills/classification_skill.yaml` | 分类评估标准 |
| CREATE | `integration/cases/news_flash_cases.json` | 测试用例 |

---

## 已确认决策

| 问题 | 决策 |
|------|------|
| 两种模式的实现顺序 | 同时实现 |
| 适配器粒度 | 两层：通用适配器 + 项目适配器 |
| 内部模式的 eval_runner | 提供默认实现，用户无需编写；也支持自定义 |

---

## 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Nano Ant 框架                             │
├─────────────────────────────────────────────────────────────────┤
│  内部模式                              外部模式                   │
│  (InternalTask)                        (ExternalTask)            │
│       │                                     │                    │
│       │                              两层适配器                   │
│       │                                     │                    │
│       │                    ┌────────────────┼────────────────┐   │
│       │                    ▼                ▼                ▼   │
│       │            GenericFileAdapter  GenericAPIAdapter  ...    │
│       │                    │                                     │
│       │            ┌───────┴───────┐                            │
│       │            ▼               ▼                            │
│       │    ZaoWorkflowAdapter  OtherAdapter                     │
│       │                                                          │
│       └────────────────────┬─────────────────────────────────────┤
│                            ▼                                     │
│                     TaskContext (统一接口)                       │
│                            │                                     │
│                            ▼                                     │
│                      Orchestrator                                │
│               Plan → Action → Judge → Iterate                    │
└─────────────────────────────────────────────────────────────────┘
```