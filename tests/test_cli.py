"""Tests for CLI entrypoint and JSON middleware."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from cli_campus.main import app

runner = CliRunner()


class TestCLIBasics:
    """CLI 基础功能测试。"""

    def test_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "CLI-Campus" in result.stdout

    def test_version(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "CLI-Campus" in result.stdout

    def test_version_json(self) -> None:
        result = runner.invoke(app, ["--json", "version"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "version" in data


class TestTestAdapterCommand:
    """test-adapter 命令测试。"""

    def test_default_mock_adapter(self) -> None:
        result = runner.invoke(app, ["test-adapter"])
        assert result.exit_code == 0
        assert "MockAdapter" in result.stdout
        assert "认证通过" in result.stdout

    def test_explicit_mock_adapter(self) -> None:
        result = runner.invoke(app, ["test-adapter", "mock"])
        assert result.exit_code == 0
        assert "1 条事件" in result.stdout

    def test_unknown_adapter(self) -> None:
        result = runner.invoke(app, ["test-adapter", "nonexistent"])
        assert result.exit_code == 1
        assert "尚未实现" in result.stdout

    def test_json_output(self) -> None:
        result = runner.invoke(app, ["--json", "test-adapter"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["source"] == "mock"
        assert data[0]["category"] == "course"

    def test_json_event_has_required_fields(self) -> None:
        result = runner.invoke(app, ["--json", "test-adapter"])
        data = json.loads(result.stdout)
        event = data[0]
        required_fields = {"id", "source", "category", "title", "content", "timestamp"}
        assert required_fields.issubset(event.keys())
