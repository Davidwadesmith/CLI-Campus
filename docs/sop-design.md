# SOP 宏指令与原子化组合设计文档

> 针对核心高频指令，摒弃 LLM 现场推理带来的高延迟（>5s），采用预设 YAML SOP 串联原子工具，确保毫秒级响应和 0 幻觉。

---

## 1. 为什么需要 SOP？

在 Agent-Native 架构中，面临两种指令执行模式：

| 模式 | 延迟 | 准确率 | 适用场景 |
|------|------|--------|----------|
| LLM 动态编排 | 3~10s | ~90% | 长尾、模糊需求 |
| 预设 SOP | <100ms | 100% | 高频、确定性操作 |

**80% 的校园查询需求是确定性的**（查课表、查校车、查余额），不需要 LLM 参与。SOP 让这些操作达到"系统调用"级别的速度和可靠性。

---

## 2. SOP 配置格式

```yaml
# sops/morning_briefing.yaml
name: morning_briefing
display_name: "早间速报"
description: "每天早上推送今日课表 + 待办 DDL + 校车时间"

# 执行步骤（顺序执行）
steps:
  - id: get_courses
    command: campus course --today --json
    description: "获取今日课表"

  - id: get_deadlines
    command: campus ddl --due-within 3d --json
    description: "获取 3 天内到期的 DDL"

  - id: get_bus
    command: campus bus --from 九龙湖 --next 3 --json
    description: "获取最近 3 班校车"

# 输出模板（Jinja2 语法）
output:
  format: markdown
  template: |
    ## 📅 {{ date }} 早间速报

    ### 📚 今日课程
    {% for c in steps.get_courses.result %}
    - {{ c.content.name }} | {{ c.content.location }} | 第 {{ c.content.start_period }}-{{ c.content.end_period }} 节
    {% endfor %}

    ### ⏰ 即将到期的 DDL
    {% for d in steps.get_deadlines.result %}
    - [{{ d.content.platform }}] {{ d.content.title }} — 截止: {{ d.content.deadline }}
    {% endfor %}

    ### 🚌 最近校车
    {% for b in steps.get_bus.result %}
    - {{ b.content.departure_time }} {{ b.content.route_name }}
    {% endfor %}
```

---

## 3. SOP 引擎架构

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│ YAML SOP 文件│────▶│ SOP Parser    │────▶│  Step Executor    │
│  (流程声明)   │     │ (解析 + 校验)  │     │ (逐步执行命令)     │
└─────────────┘     └──────────────┘     └──────────────────┘
                                                  │
                                                  ▼
                                         ┌──────────────────┐
                                         │ Template Renderer │
                                         │ (Jinja2 输出渲染)  │
                                         └──────────────────┘
```

### 3.1 核心类设计（伪代码）

```python
# cli_campus/core/sop_engine.py (Phase 3 实现)

from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class SOPStep:
    id: str
    command: str
    description: str
    result: Any = None


@dataclass
class SOPDefinition:
    name: str
    display_name: str
    description: str
    steps: list[SOPStep]
    output_template: str


class SOPRunner:
    """SOP 宏执行器。"""

    def __init__(self, sop: SOPDefinition) -> None:
        self.sop = sop

    async def execute(self) -> str:
        """顺序执行所有步骤并渲染输出。"""
        for step in self.sop.steps:
            step.result = await self._run_command(step.command)

        return self._render_output()

    async def _run_command(self, command: str) -> list[dict]:
        """执行单个 campus 命令并返回 JSON 结果。"""
        # 内部调用 Typer 命令，而不是启动子进程
        ...

    def _render_output(self) -> str:
        """使用 Jinja2 渲染输出模板。"""
        from jinja2 import Template
        template = Template(self.sop.output_template)
        return template.render(
            steps={s.id: s for s in self.sop.steps},
            date="2026-04-01",
        )
```

---

## 4. 原子化工具设计原则

每个 CLI 命令都应该是**最小粒度**的原子操作：

```
campus auth login       # 原子：仅登录
campus auth status      # 原子：仅检查状态
campus course --today   # 原子：仅查今日课表
campus course --week 5  # 原子：仅查第 5 周课表
campus bus --next 3     # 原子：仅查最近 3 班车
campus ddl --due 3d     # 原子：仅查 3 天内 DDL
campus card balance     # 原子：仅查一卡通余额
```

**组合由上层完成**：
- SOP 宏指令：预设的 YAML 流程编排
- LLM Agent：动态理解用户意图并组合工具
- Shell 脚本：`campus course --json | jq '.[] | .title'`

---

## 5. SOP 文件存放位置

```
cli-campus/
└── sops/
    ├── morning_briefing.yaml    # 早间速报
    ├── exam_countdown.yaml      # 考试倒计时
    └── weekly_summary.yaml      # 周报汇总
```

---

## 6. 使用示例

```bash
# 执行预设 SOP
campus sop run morning_briefing

# 列出所有可用 SOP
campus sop list

# JSON 输出（供 Agent 消费）
campus sop run morning_briefing --json
```

SOP 宏执行器计划在 **Phase 3 (Week 7~8)** 正式实现。
