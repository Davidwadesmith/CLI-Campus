"""SOP 宏执行器测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli_campus.core.sop_engine import (
    SOPDefinition,
    SOPRunner,
    SOPStep,
    discover_sops,
    load_sop,
)
from cli_campus.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# SOP 配置加载测试
# ---------------------------------------------------------------------------


class TestLoadSOP:
    """SOP 配置加载测试。"""

    def test_load_valid_sop(self, tmp_path: Path) -> None:
        yaml_content = """
name: test_sop
display_name: "测试 SOP"
description: "测试用 SOP"
steps:
  - id: step1
    command: campus version
    description: "获取版本"
output:
  format: markdown
  template: "版本: {{ steps.step1.result }}"
"""
        sop_file = tmp_path / "test.yaml"
        sop_file.write_text(yaml_content, encoding="utf-8")

        sop = load_sop(sop_file)
        assert sop.name == "test_sop"
        assert sop.display_name == "测试 SOP"
        assert len(sop.steps) == 1
        assert sop.steps[0].id == "step1"
        assert sop.steps[0].command == "campus version"
        assert sop.output.template

    def test_load_minimal_sop(self, tmp_path: Path) -> None:
        yaml_content = """
name: minimal
steps:
  - id: s1
    command: campus version
"""
        sop_file = tmp_path / "minimal.yaml"
        sop_file.write_text(yaml_content, encoding="utf-8")

        sop = load_sop(sop_file)
        assert sop.name == "minimal"
        assert sop.display_name == ""
        assert sop.output.template == ""

    def test_load_invalid_sop(self, tmp_path: Path) -> None:
        sop_file = tmp_path / "bad.yaml"
        sop_file.write_text("not a dict", encoding="utf-8")

        with pytest.raises(Exception):
            load_sop(sop_file)


class TestDiscoverSOPs:
    """SOP 发现测试。"""

    def test_discover_sops(self, tmp_path: Path) -> None:
        for name in ["a.yaml", "b.yaml"]:
            (tmp_path / name).write_text(
                f"name: {name.split('.')[0]}\nsteps:\n  - id: s1\n    command: campus version\n",
                encoding="utf-8",
            )
        sops = discover_sops(tmp_path)
        assert len(sops) == 2

    def test_discover_empty(self, tmp_path: Path) -> None:
        assert discover_sops(tmp_path) == []

    def test_discover_nonexistent(self) -> None:
        assert discover_sops(Path("/nonexistent")) == []


# ---------------------------------------------------------------------------
# SOPRunner 测试
# ---------------------------------------------------------------------------


class TestSOPRunner:
    """SOP 执行器测试。"""

    def test_execute_version_command(self) -> None:
        """测试执行 campus version 命令。"""
        sop = SOPDefinition(
            name="test",
            steps=[SOPStep(id="ver", command="campus version")],
        )
        sop_runner = SOPRunner(sop)
        result = sop_runner.execute()
        # Should contain version info as JSON
        assert "version" in result or "0.1.0" in result

    def test_execute_json(self) -> None:
        """测试 JSON 输出。"""
        sop = SOPDefinition(
            name="test",
            steps=[SOPStep(id="ver", command="campus version")],
        )
        sop_runner = SOPRunner(sop)
        result = sop_runner.execute_json()
        assert result["sop"] == "test"
        assert "timestamp" in result
        assert "ver" in result["steps"]

    def test_execute_with_template(self) -> None:
        """测试 Jinja2 模板渲染。"""
        from cli_campus.core.sop_engine import SOPOutputConfig

        sop = SOPDefinition(
            name="test",
            steps=[SOPStep(id="ver", command="campus version")],
            output=SOPOutputConfig(
                format="markdown",
                template="Today is {{ date }}. Got {{ steps.ver.count }} results.",
            ),
        )
        sop_runner = SOPRunner(sop)
        result = sop_runner.execute()
        assert "Today is" in result
        assert "Got 1 results" in result

    def test_execute_bus_command(self) -> None:
        """测试执行 campus bus 命令 — 静态数据无需认证。"""
        sop = SOPDefinition(
            name="test",
            steps=[SOPStep(id="bus", command="campus bus --route 循环")],
        )
        sop_runner = SOPRunner(sop)
        result = sop_runner.execute_json()
        assert result["steps"]["bus"]["count"] > 0


# ---------------------------------------------------------------------------
# SOP CLI 命令测试
# ---------------------------------------------------------------------------


class TestSOPCLI:
    """SOP CLI 命令测试。"""

    def test_sop_list(self) -> None:
        result = runner.invoke(app, ["sop", "list"])
        assert result.exit_code == 0

    def test_sop_list_json(self) -> None:
        result = runner.invoke(app, ["--json", "sop", "list"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_sop_run_nonexistent(self) -> None:
        result = runner.invoke(app, ["sop", "run", "nonexistent"])
        assert result.exit_code == 1

    def test_sop_help(self) -> None:
        result = runner.invoke(app, ["sop", "--help"])
        assert result.exit_code == 0

    def test_sop_run_morning_briefing(self) -> None:
        """测试执行真实 SOP — morning_briefing。"""
        result = runner.invoke(app, ["sop", "run", "morning_briefing"])
        assert result.exit_code == 0
        assert "早间速报" in result.stdout
