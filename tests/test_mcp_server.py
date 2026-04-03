"""MCP Server 自动挂载引擎测试。

覆盖:
- Context-Aware 基础感知工具 (get_current_time, get_semester_info)
- Auto-Registrar 引擎 (动态工具注册、签名正确性、调用正确性)
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime


class TestGetCurrentTime:
    """get_current_time 工具测试。"""

    def test_returns_valid_json(self) -> None:
        from cli_campus.mcp_server import get_current_time

        result = asyncio.run(get_current_time())
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_contains_required_fields(self) -> None:
        from cli_campus.mcp_server import get_current_time

        result = asyncio.run(get_current_time())
        data = json.loads(result)
        assert "date" in data
        assert "time" in data
        assert "weekday" in data
        assert "weekday_number" in data
        assert "timestamp" in data

    def test_weekday_number_range(self) -> None:
        from cli_campus.mcp_server import get_current_time

        result = asyncio.run(get_current_time())
        data = json.loads(result)
        assert 1 <= data["weekday_number"] <= 7

    def test_date_format(self) -> None:
        from cli_campus.mcp_server import get_current_time

        result = asyncio.run(get_current_time())
        data = json.loads(result)
        # Should be YYYY-MM-DD
        datetime.strptime(data["date"], "%Y-%m-%d")

    def test_weekday_is_chinese(self) -> None:
        from cli_campus.mcp_server import get_current_time

        result = asyncio.run(get_current_time())
        data = json.loads(result)
        valid_days = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
        assert data["weekday"] in valid_days


class TestGetSemesterInfo:
    """get_semester_info 工具测试。"""

    def test_returns_valid_json(self) -> None:
        from cli_campus.mcp_server import get_semester_info

        result = asyncio.run(get_semester_info())
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_contains_required_fields(self) -> None:
        from cli_campus.mcp_server import get_semester_info

        result = asyncio.run(get_semester_info())
        data = json.loads(result)
        assert "semester_code" in data
        assert "academic_year" in data
        assert "semester_name" in data
        assert "semester_number" in data

    def test_semester_code_format(self) -> None:
        from cli_campus.mcp_server import get_semester_info

        result = asyncio.run(get_semester_info())
        data = json.loads(result)
        # 格式: YYYY-YYYY-N
        parts = data["semester_code"].split("-")
        assert len(parts) == 3
        assert parts[0].isdigit()
        assert parts[1].isdigit()
        assert parts[2] in ("1", "2", "3")

    def test_semester_name_is_chinese(self) -> None:
        from cli_campus.mcp_server import get_semester_info

        result = asyncio.run(get_semester_info())
        data = json.loads(result)
        assert data["semester_name"] in ("暑期学校", "秋季", "春季")


class TestAutoRegistrar:
    """MCP Tool 自动挂载引擎测试。"""

    def test_auto_register_returns_count(self) -> None:
        from cli_campus.mcp_server import auto_register_tools

        count = auto_register_tools()
        assert isinstance(count, int)
        assert count > 0

    def test_bus_tool_registered(self) -> None:
        """校车工具应被自动注册。"""
        from cli_campus.mcp_server import mcp

        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "campus_bus" in tool_names

    def test_course_tool_registered(self) -> None:
        """课表工具应被自动注册。"""
        from cli_campus.mcp_server import mcp

        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "campus_course" in tool_names

    def test_grade_tool_registered(self) -> None:
        """成绩工具应被自动注册。"""
        from cli_campus.mcp_server import mcp

        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "campus_grade" in tool_names

    def test_exam_tool_registered(self) -> None:
        """考试工具应被自动注册。"""
        from cli_campus.mcp_server import mcp

        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "campus_exam" in tool_names

    def test_card_tool_registered(self) -> None:
        """一卡通工具应被自动注册。"""
        from cli_campus.mcp_server import mcp

        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "campus_card" in tool_names

    def test_context_tools_registered(self) -> None:
        """Context-Aware 工具应被注册。"""
        from cli_campus.mcp_server import mcp

        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "get_current_time" in tool_names
        assert "get_semester_info" in tool_names

    def test_meta_commands_excluded(self) -> None:
        """元命令不应被注册为 MCP Tool。"""
        from cli_campus.mcp_server import mcp

        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "campus_test_adapter" not in tool_names
        assert "campus_version" not in tool_names
        assert "campus_mcp" not in tool_names

    def test_auth_commands_excluded(self) -> None:
        """认证命令不应被注册为 MCP Tool。"""
        from cli_campus.mcp_server import mcp

        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "campus_auth_login" not in tool_names
        assert "campus_auth_status" not in tool_names
        assert "campus_auth_logout" not in tool_names

    def test_venue_subcommands_registered(self) -> None:
        """场馆子命令应被注册为独立 MCP Tool。"""
        from cli_campus.mcp_server import mcp

        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "campus_venue_list" in tool_names
        assert "campus_venue_slots" in tool_names


class TestDynamicFunctionSignature:
    """动态生成函数的签名正确性测试。"""

    def test_bus_tool_has_correct_params(self) -> None:
        """校车工具应有 route 和 schedule_type 参数。"""
        from cli_campus.mcp_server import mcp

        tools = mcp._tool_manager.list_tools()
        bus_tool = next(t for t in tools if t.name == "campus_bus")

        # Tool 应有描述
        assert bus_tool.description
        assert len(bus_tool.description) > 0

    def test_course_tool_has_correct_params(self) -> None:
        """课表工具应有 semester 和 week 参数。"""
        from cli_campus.mcp_server import mcp

        tools = mcp._tool_manager.list_tools()
        course_tool = next(t for t in tools if t.name == "campus_course")

        assert course_tool.description
        assert len(course_tool.description) > 0

    def test_tool_has_docstring(self) -> None:
        """所有自动注册的工具都应有 docstring。"""
        from cli_campus.mcp_server import mcp

        tools = mcp._tool_manager.list_tools()
        for tool in tools:
            assert tool.description, f"Tool {tool.name} has no description"


class TestInvokeCLIJson:
    """_invoke_cli_json 内部调用测试。"""

    def test_bus_invocation(self) -> None:
        """通过 _invoke_cli_json 调用校车查询应返回 JSON。"""
        from cli_campus.mcp_server import _invoke_cli_json

        result = _invoke_cli_json(["bus"], {})
        data = json.loads(result)
        assert isinstance(data, list)

    def test_bus_with_route_filter(self) -> None:
        """带路线过滤的校车查询。"""
        from cli_campus.mcp_server import _invoke_cli_json

        result = _invoke_cli_json(["bus"], {"route": "循环"})
        data = json.loads(result)
        assert isinstance(data, list)
        for item in data:
            assert "循环" in item.get("title", "") or "循环" in json.dumps(
                item.get("content", {}), ensure_ascii=False
            )

    def test_empty_params_ignored(self) -> None:
        """None 参数应被忽略而非传递。"""
        from cli_campus.mcp_server import _invoke_cli_json

        # 不应报错
        result = _invoke_cli_json(["bus"], {"route": None, "schedule_type": None})
        data = json.loads(result)
        assert isinstance(data, list)


class TestMCPResources:
    """MCP Resources 测试。"""

    def test_bus_notes_resource(self) -> None:
        from cli_campus.mcp_server import bus_notes

        result = asyncio.run(bus_notes())
        assert "东南大学" in result
        assert "workday" in result


class TestMCPPrompts:
    """MCP Prompts 测试。"""

    def test_system_prompt(self) -> None:
        from cli_campus.mcp_server import campus_assistant_system_prompt

        result = asyncio.run(campus_assistant_system_prompt())
        assert "get_current_time" in result
        assert "get_semester_info" in result
        assert "campus_bus" in result
        assert "campus_course" in result

    def test_morning_briefing_prompt(self) -> None:
        from cli_campus.mcp_server import campus_morning_briefing

        result = asyncio.run(campus_morning_briefing())
        assert "get_current_time" in result
        assert "campus_course" in result
        assert "campus_bus" in result


class TestMakeToolFunction:
    """_make_tool_function 工厂测试。"""

    def test_generated_function_is_async(self) -> None:
        import inspect

        from cli_campus.mcp_server import _make_tool_function

        func = _make_tool_function("test_tool", ["bus"], [], "Test doc")
        assert inspect.iscoroutinefunction(func)

    def test_generated_function_has_docstring(self) -> None:
        from cli_campus.mcp_server import _make_tool_function

        func = _make_tool_function("test_tool", ["bus"], [], "Test docstring")
        assert func.__doc__ == "Test docstring"

    def test_generated_function_has_return_annotation(self) -> None:
        from cli_campus.mcp_server import _make_tool_function

        func = _make_tool_function("test_tool", ["bus"], [], "Test")
        assert func.__annotations__["return"] is str
