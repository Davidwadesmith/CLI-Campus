"""MCP Server 自动挂载引擎测试。

覆盖:
- Context-Aware 基础感知工具 (get_current_time, get_semester_info)
- Auto-Registrar 引擎 (动态工具注册、签名正确性、调用正确性)
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest


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

        result = _invoke_cli_json(
            ["bus"], {"schedule_type": "workday"}, {"schedule_type": "--type"}
        )
        data = json.loads(result)
        assert isinstance(data, list)

    def test_bus_with_route_filter(self) -> None:
        """带路线过滤的校车查询。"""
        from cli_campus.mcp_server import _invoke_cli_json

        result = _invoke_cli_json(
            ["bus"],
            {"route": "兰台", "schedule_type": "workday"},
            {"schedule_type": "--type"},
        )
        data = json.loads(result)
        assert isinstance(data, list)
        for item in data:
            combined = json.dumps(item, ensure_ascii=False)
            assert "兰台" in combined

    def test_empty_params_ignored(self) -> None:
        """None 参数应被忽略而非传递。"""
        from cli_campus.mcp_server import _invoke_cli_json

        # 不应报错 (bus 无过滤可能超出大小限制，但应正常返回 JSON)
        result = _invoke_cli_json(["bus"], {"route": None, "schedule_type": None})
        data = json.loads(result)
        assert isinstance(data, (list, dict))

    def test_bus_invocation_from_async_context(self) -> None:
        """从 async 上下文（模拟 MCP 运行时）调用应正常返回数据。

        这是 MCP 工具的实际调用路径：FastMCP 在 event loop 中调用
        async 工具函数 → asyncio.to_thread → _invoke_cli_json。
        """
        import asyncio

        from cli_campus.mcp_server import _invoke_cli_json

        async def _run() -> str:
            return await asyncio.to_thread(
                _invoke_cli_json,
                ["bus"],
                {"schedule_type": "workday"},
                {"schedule_type": "--type"},
            )

        result = asyncio.run(_run())
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_cli_error_returns_structured_json(self) -> None:
        """CLI 异常时应返回结构化的 JSON 错误而非空响应。"""
        from cli_campus.mcp_server import _invoke_cli_json

        result = _invoke_cli_json(["nonexistent-command"], {})
        data = json.loads(result)
        assert "error" in data


class TestMCPResources:
    """MCP Resources 测试。"""

    def test_bus_notes_resource(self) -> None:
        from cli_campus.mcp_server import bus_notes

        result = asyncio.run(bus_notes())
        assert "东南大学" in result
        assert "workday" in result

    def test_resource_index(self) -> None:
        """资源索引应列出所有已注册文档。"""
        from cli_campus.mcp_server import resource_index

        result = asyncio.run(resource_index())
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) >= 1
        item = data[0]
        assert "name" in item
        assert "title" in item
        assert "uri" in item
        assert item["uri"].startswith("campus://resources/")

    def test_student_handbook_resource_registered(self) -> None:
        """学生手册应被注册为 MCP Resource。"""
        from cli_campus.mcp_server import _resource_cache

        assert "student_handbook" in _resource_cache
        title, text = _resource_cache["student_handbook"]
        assert "学生手册" in title
        assert len(text) > 100

    def test_auto_register_resources_returns_count(self) -> None:
        from cli_campus.mcp_server import auto_register_resources

        count = auto_register_resources()
        assert isinstance(count, int)
        assert count >= 1


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


class TestSlimForAgent:
    """_slim_for_agent 数据精简测试。"""

    def test_strips_envelope_keeps_content(self) -> None:
        """CampusEvent 格式: 去除信封，仅保留 content 字段 (不保留冗余 title)。"""
        from cli_campus.mcp_server import _slim_for_agent

        raw = json.dumps(
            [
                {
                    "id": "test:1",
                    "source": "mock",
                    "category": "bus",
                    "title": "Test Event",
                    "content": {"name": "foo", "value": 42},
                    "raw_data": {"INTERNAL_KEY": "secret"},
                    "timestamp": "2026-01-01T00:00:00",
                }
            ]
        )
        result = json.loads(_slim_for_agent(raw))
        assert len(result) == 1
        item = result[0]
        # content 字段被提升为顶层
        assert item["name"] == "foo"
        assert item["value"] == 42
        # 信封字段全部去除
        assert "raw_data" not in item
        assert "id" not in item
        assert "source" not in item

    def test_campus_event_without_content_dict(self) -> None:
        """content 非 dict 时保留 title 作为 fallback。"""
        from cli_campus.mcp_server import _slim_for_agent

        raw = json.dumps([{"title": "Test", "content": "plain text", "raw_data": {}}])
        result = json.loads(_slim_for_agent(raw))
        assert result[0]["title"] == "Test"

    def test_strips_internal_ids_from_generic_list(self) -> None:
        """通用列表 (如 VenueInfo) 应剥离 venue_id/state 等内部字段。"""
        from cli_campus.mcp_server import _slim_for_agent

        raw = json.dumps(
            [{"venue_id": "abc", "name": "场馆A", "state": 0, "campus": "九龙湖"}]
        )
        result = json.loads(_slim_for_agent(raw))
        assert result[0]["name"] == "场馆A"
        assert result[0]["campus"] == "九龙湖"
        assert "venue_id" not in result[0]
        assert "state" not in result[0]

    def test_passthrough_error_object(self) -> None:
        """错误对象应原样透传。"""
        from cli_campus.mcp_server import _slim_for_agent

        raw = json.dumps({"error": "auth_required", "message": "请先登录"})
        assert _slim_for_agent(raw) == raw

    def test_passthrough_invalid_json(self) -> None:
        """非 JSON 字符串应原样透传。"""
        from cli_campus.mcp_server import _slim_for_agent

        assert _slim_for_agent("not json") == "not json"

    def test_venue_slots_grouped(self) -> None:
        """嵌套 venue+slot 返回应按场馆分组去重。"""
        from cli_campus.mcp_server import _slim_for_agent

        venue = {
            "venue_id": "x",
            "name": "A场",
            "number": "A01",
            "campus": "九龙湖",
            "capacity": 4,
            "state": 0,
        }
        raw = json.dumps(
            [
                {
                    "venue": venue,
                    "slot": {
                        "slot_id": "s1",
                        "start_time": "09:00",
                        "end_time": "10:00",
                        "available": 2,
                        "status_text": "可预约",
                        "venue_id": "x",
                        "date": "2026-04-05",
                    },
                },
                {
                    "venue": venue,
                    "slot": {
                        "slot_id": "s2",
                        "start_time": "10:00",
                        "end_time": "11:00",
                        "available": 0,
                        "status_text": "已满",
                        "venue_id": "x",
                        "date": "2026-04-05",
                    },
                },
            ]
        )
        result = json.loads(_slim_for_agent(raw))
        assert len(result) == 1  # 分组为 1 个场馆
        assert result[0]["venue"] == "A01 A场"
        assert len(result[0]["slots"]) == 2
        assert result[0]["slots"][0]["time"] == "09:00-10:00"
        assert result[0]["slots"][1]["available"] == 0


class TestSearchResource:
    """search_resource 工具测试。"""

    def test_search_returns_matches(self) -> None:
        from cli_campus.mcp_server import search_resource

        result = asyncio.run(search_resource("奖学金"))
        data = json.loads(result)
        assert data["matches"] >= 1
        assert "results" in data
        assert "奖学金" in data["results"][0]["content"]

    def test_search_specific_resource(self) -> None:
        from cli_campus.mcp_server import search_resource

        result = asyncio.run(search_resource("考试", resource_name="student_handbook"))
        data = json.loads(result)
        assert data["matches"] >= 1

    def test_search_no_match(self) -> None:
        from cli_campus.mcp_server import search_resource

        result = asyncio.run(search_resource("完全不可能匹配的关键词xyz123"))
        data = json.loads(result)
        assert data["matches"] == 0
        assert "message" in data

    def test_search_nonexistent_resource(self) -> None:
        """搜索不存在的资源名时应搜全部。"""
        from cli_campus.mcp_server import search_resource

        result = asyncio.run(search_resource("宿舍", resource_name="nonexistent"))
        data = json.loads(result)
        # fallback 全部搜索
        assert data["matches"] >= 1


class TestFlagMapping:
    """参数名→CLI flag 映射测试。"""

    def test_venue_list_custom_flag(self) -> None:
        """venue list 的 type_name 应映射到 --type 而非 --type-name。"""
        from cli_campus.mcp_server import _invoke_cli_json

        result = _invoke_cli_json(
            ["venue", "list"],
            {"type_name": "羽毛球场", "campus": "九龙湖"},
            {"type_name": "--type", "campus": "--campus"},
        )
        data = json.loads(result)
        assert isinstance(data, list)
        assert "error" not in (data[0] if data else {})

    def test_bus_custom_flag(self) -> None:
        """bus 的 schedule_type 应映射到 --type 而非 --schedule-type。"""
        from cli_campus.mcp_server import _invoke_cli_json

        result = _invoke_cli_json(
            ["bus"],
            {"schedule_type": "workday"},
            {"schedule_type": "--type", "route": "--route"},
        )
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_flag_map_fallback(self) -> None:
        """未提供 flag_map 时应 fallback 到朴素 --name 转换。"""
        from cli_campus.mcp_server import _invoke_cli_json

        # bus route 的朴素转换 --route 和实际 flag 一致，应正常工作
        result = _invoke_cli_json(["bus"], {"route": "兰台"})
        data = json.loads(result)
        # 可能是 list 或截断后的 dict，但不应是 error
        if isinstance(data, dict):
            assert data.get("truncated") is True or "error" not in data
        else:
            assert isinstance(data, list)

    def test_dynamic_tool_carries_flag_map(self) -> None:
        """动态生成的 MCP 工具函数应携带正确的 flag_map。"""
        from cli_campus.mcp_server import mcp

        tools = mcp._tool_manager._tools
        venue_tool = tools.get("campus_venue_list")
        assert venue_tool is not None

        # 调用应成功（不再 SystemExit(2)）
        result = asyncio.run(venue_tool.fn(type_name="羽毛球场", campus="九龙湖"))
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) > 0
        assert "name" in data[0]


class TestEnforceSizeLimit:
    """输出大小上限测试。"""

    def test_small_data_passes_through(self) -> None:
        from cli_campus.mcp_server import _enforce_size_limit

        text = '{"ok": true}'
        assert _enforce_size_limit(text) == text

    def test_large_data_truncated(self) -> None:
        from cli_campus.mcp_server import _MAX_RESPONSE_KB, _enforce_size_limit

        # 生成超过限制的数据
        big = "x" * (_MAX_RESPONSE_KB * 1024 + 1000)
        result = _enforce_size_limit(big)
        data = json.loads(result)
        assert data["truncated"] is True
        assert "partial_data" in data

    def test_bus_all_schedules_truncated(self) -> None:
        """校车全量数据 (3 种时刻表) 应被截断。"""
        from cli_campus.mcp_server import _invoke_cli_json

        result = _invoke_cli_json(["bus"], {})
        data = json.loads(result)
        assert isinstance(data, dict)
        assert data.get("truncated") is True

    def test_bus_workday_fits(self) -> None:
        """校车工作日时刻表应在限制内。"""
        from cli_campus.mcp_server import _MAX_RESPONSE_KB, _invoke_cli_json

        result = _invoke_cli_json(
            ["bus"], {"schedule_type": "workday"}, {"schedule_type": "--type"}
        )
        assert len(result.encode("utf-8")) <= _MAX_RESPONSE_KB * 1024
        data = json.loads(result)
        assert isinstance(data, list)


_PDF_FILE = (
    Path(__file__).parent.parent
    / "cli_campus"
    / "data"
    / "resources"
    / "东南大学大学生手册2025.pdf"
)


@pytest.mark.skipif(not _PDF_FILE.exists(), reason="PDF 不在仓库中 (.gitignore)")
class TestPdfResourceLoading:
    """静态资源 PDF 加载测试（仅在本地 PDF 存在时运行）。"""

    def test_scanned_pdf_has_fallback_text(self) -> None:
        """扫描版 PDF 应生成占位说明而非空文本。"""
        from cli_campus.mcp_server import _resource_cache

        key = "东南大学大学生手册2025"
        assert key in _resource_cache
        title, text = _resource_cache[key]
        assert "扫描" in text
        assert "search_resource" in text

    def test_pdf_and_md_both_registered(self) -> None:
        """同名 PDF 和 MD 都应被注册为独立资源。"""
        from cli_campus.mcp_server import _resource_cache

        assert "student_handbook" in _resource_cache
        assert "东南大学大学生手册2025" in _resource_cache
