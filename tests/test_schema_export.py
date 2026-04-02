"""Tool Schema 自动生成器测试。"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from cli_campus.core.schema_export import export_function_calling_schema
from cli_campus.main import app

runner = CliRunner()


class TestSchemaExport:
    """Schema 导出功能测试。"""

    def test_export_all_commands(self) -> None:
        tools = export_function_calling_schema(app)
        assert isinstance(tools, list)
        assert len(tools) > 0

        # 每个 tool 都有标准结构
        for tool in tools:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]

    def test_export_has_bus_command(self) -> None:
        tools = export_function_calling_schema(app)
        names = [t["function"]["name"] for t in tools]
        assert "campus_bus" in names

    def test_export_bus_has_route_param(self) -> None:
        tools = export_function_calling_schema(app)
        bus_tool = next(t for t in tools if t["function"]["name"] == "campus_bus")
        props = bus_tool["function"]["parameters"]["properties"]
        assert "route" in props
        assert props["route"]["type"] == "string"

    def test_export_course_week_is_integer(self) -> None:
        tools = export_function_calling_schema(app)
        course_tool = next(
            t for t in tools if t["function"]["name"] == "campus_course"
        )
        props = course_tool["function"]["parameters"]["properties"]
        assert props["week"]["type"] == "integer"

    def test_export_filter_by_commands(self) -> None:
        tools = export_function_calling_schema(app, commands=["bus"])
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "campus_bus"

    def test_export_auth_subcommands(self) -> None:
        tools = export_function_calling_schema(app)
        names = [t["function"]["name"] for t in tools]
        assert "campus_auth_login" in names
        assert "campus_auth_status" in names
        assert "campus_auth_logout" in names

    def test_export_excludes_meta_commands(self) -> None:
        tools = export_function_calling_schema(app)
        names = [t["function"]["name"] for t in tools]
        assert "campus_test_adapter" not in names
        assert "campus_version" not in names
        assert "campus_fetch_list" not in names

    def test_export_json_serializable(self) -> None:
        tools = export_function_calling_schema(app)
        # 确保可以序列化为 JSON
        output = json.dumps(tools, ensure_ascii=False)
        parsed = json.loads(output)
        assert len(parsed) == len(tools)


class TestSchemaCLI:
    """Schema CLI 命令测试。"""

    def test_schema_export_command(self) -> None:
        result = runner.invoke(app, ["schema", "export"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_schema_export_pretty(self) -> None:
        result = runner.invoke(app, ["schema", "export", "--pretty"])
        assert result.exit_code == 0
        # Pretty output has newlines and indentation
        assert "\n" in result.stdout
        assert "  " in result.stdout

    def test_schema_export_filter(self) -> None:
        result = runner.invoke(app, ["schema", "export", "--commands", "bus"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["function"]["name"] == "campus_bus"

    def test_schema_help(self) -> None:
        result = runner.invoke(app, ["schema", "--help"])
        assert result.exit_code == 0
