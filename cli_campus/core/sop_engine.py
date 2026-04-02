"""SOP 宏执行器 — 预设 YAML 编排串联原子工具，确保毫秒级响应和 0 幻觉。

解析 SOP YAML 配置，逐步执行 CLI 命令（内部调用），
并通过 Jinja2 模板渲染最终输出。
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from cli_campus.core.exceptions import AdapterError

# ---------------------------------------------------------------------------
# 配置模型
# ---------------------------------------------------------------------------


class SOPStep(BaseModel):
    """SOP 执行步骤。"""

    id: str
    command: str
    description: str = ""


class SOPOutputConfig(BaseModel):
    """SOP 输出配置。"""

    format: str = "markdown"
    template: str = ""


class SOPDefinition(BaseModel):
    """SOP 完整定义。"""

    name: str
    display_name: str = ""
    description: str = ""
    steps: list[SOPStep]
    output: SOPOutputConfig = Field(default_factory=SOPOutputConfig)


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------


def load_sop(path: Path) -> SOPDefinition:
    """从 YAML 文件加载 SOP 定义。"""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise AdapterError(f"SOP 配置格式错误: {path}")
    return SOPDefinition.model_validate(raw)


def discover_sops(sop_dir: Path) -> list[SOPDefinition]:
    """扫描目录下所有 SOP YAML 文件。"""
    sops: list[SOPDefinition] = []
    if not sop_dir.is_dir():
        return sops
    for p in sorted(sop_dir.glob("*.yaml")):
        sops.append(load_sop(p))
    for p in sorted(sop_dir.glob("*.yml")):
        sops.append(load_sop(p))
    return sops


# ---------------------------------------------------------------------------
# 执行器
# ---------------------------------------------------------------------------


class SOPRunner:
    """SOP 宏执行器 — 顺序执行步骤并渲染输出。"""

    def __init__(self, sop: SOPDefinition) -> None:
        self.sop = sop
        self.results: dict[str, list[dict[str, Any]]] = {}

    def execute(self) -> str:
        """顺序执行所有步骤并渲染输出。

        Returns:
            渲染后的文本输出。
        """
        for step in self.sop.steps:
            self.results[step.id] = self._run_command(step.command)

        if self.sop.output.template:
            return self._render_template()

        # 无模板时返回原始 JSON
        return json.dumps(self.results, ensure_ascii=False, indent=2)

    def execute_json(self) -> dict[str, Any]:
        """执行所有步骤并返回 JSON 结构。"""
        for step in self.sop.steps:
            self.results[step.id] = self._run_command(step.command)

        return {
            "sop": self.sop.name,
            "timestamp": datetime.now().isoformat(),
            "steps": {
                step_id: {"data": data, "count": len(data)}
                for step_id, data in self.results.items()
            },
        }

    def _run_command(self, command: str) -> list[dict[str, Any]]:
        """执行单个 campus 命令并返回 JSON 结果。

        通过在命令中追加 --json 标志，以子进程方式调用 campus CLI，
        获取结构化的 JSON 输出。
        """
        # 解析命令: "campus bus --route 循环 --json" → 拆分参数
        parts = command.strip().split()
        if not parts:
            return []

        # 确保命令以 campus 开头并带 --json
        if parts[0] == "campus":
            parts = parts[1:]

        # 在子命令参数前插入 --json
        cmd = [sys.executable, "-m", "cli_campus.main", "--json", *parts]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(Path(__file__).resolve().parent.parent.parent),
            )
        except subprocess.TimeoutExpired:
            return [{"error": "命令执行超时", "command": command}]
        except Exception as exc:
            return [{"error": str(exc), "command": command}]

        if result.returncode != 0:
            # 返回错误信息但不中断 SOP
            stderr = result.stderr.strip()[:200] if result.stderr else ""
            return [{
                "error": f"命令执行失败 (exit={result.returncode})",
                "stderr": stderr,
            }]

        # 解析 JSON 输出
        stdout = result.stdout.strip()
        if not stdout:
            return []

        try:
            data = json.loads(stdout)
            if isinstance(data, list):
                return data
            return [data]
        except json.JSONDecodeError:
            return [{"raw_output": stdout[:500]}]

    def _render_template(self) -> str:
        """使用 Jinja2 渲染输出模板。"""
        from jinja2 import Template

        # 构建步骤结果上下文: steps.get_courses.result → list[dict]
        steps_ctx: dict[str, Any] = {}
        for step in self.sop.steps:
            steps_ctx[step.id] = type("StepResult", (), {
                "result": self.results.get(step.id, []),
                "count": len(self.results.get(step.id, [])),
            })()

        template = Template(self.sop.output.template)
        return template.render(
            steps=steps_ctx,
            date=datetime.now().strftime("%Y-%m-%d"),
            time=datetime.now().strftime("%H:%M"),
        )
