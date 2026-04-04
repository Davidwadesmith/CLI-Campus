"""MCP Server stdio 集成测试 — 真实的客户端↔服务端通信。

通过 ``mcp.client.stdio`` 启动一个真实的 MCP Server 子进程，
用标准 MCP 客户端协议 (JSON-RPC over stdio) 进行端到端测试。
这模拟了 Claude Desktop / Cherry Studio 等 MCP 客户端的真实调用路径。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=["-m", "cli_campus.mcp_server"],
    cwd=str(Path(__file__).resolve().parent.parent),
)


async def _run_with_session(
    fn: Any,
) -> Any:
    """启动 MCP Server 子进程，执行测试函数后安全关闭。

    使用 anyio.open_process 管理的 stdio_client 在 pytest-asyncio
    teardown 时存在 cancel scope task affinity 问题，
    通过将整个生命周期包裹在单个 async 调用中规避此问题。
    """
    async with stdio_client(_SERVER_PARAMS) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            return await fn(session)


# ---------------------------------------------------------------------------
# Tool Discovery
# ---------------------------------------------------------------------------


class TestToolDiscovery:
    """MCP 工具发现测试 — 验证 list_tools 返回正确的工具集。"""

    @pytest.mark.anyio
    async def test_list_tools_returns_tools(self) -> None:
        """list_tools 应返回已注册的工具列表。"""

        async def _check(session: ClientSession) -> None:
            result = await session.list_tools()
            names = [t.name for t in result.tools]
            assert len(names) > 0

        await _run_with_session(_check)

    @pytest.mark.anyio
    async def test_context_tools_present(self) -> None:
        """Context-Aware 基础工具应存在。"""

        async def _check(session: ClientSession) -> None:
            result = await session.list_tools()
            names = [t.name for t in result.tools]
            assert "get_current_time" in names
            assert "get_semester_info" in names

        await _run_with_session(_check)

    @pytest.mark.anyio
    async def test_business_tools_present(self) -> None:
        """业务工具应存在。"""

        async def _check(session: ClientSession) -> None:
            result = await session.list_tools()
            names = [t.name for t in result.tools]
            assert "campus_bus" in names
            assert "campus_course" in names
            assert "campus_grade" in names
            assert "campus_exam" in names
            assert "campus_venue_list" in names
            assert "campus_venue_slots" in names

        await _run_with_session(_check)

    @pytest.mark.anyio
    async def test_meta_commands_absent(self) -> None:
        """元命令不应出现在工具列表中。"""

        async def _check(session: ClientSession) -> None:
            result = await session.list_tools()
            names = [t.name for t in result.tools]
            assert "campus_auth" not in names
            assert "campus_version" not in names
            assert "campus_mcp" not in names

        await _run_with_session(_check)

    @pytest.mark.anyio
    async def test_tools_have_descriptions(self) -> None:
        """所有工具应有描述文档。"""

        async def _check(session: ClientSession) -> None:
            result = await session.list_tools()
            for tool in result.tools:
                assert tool.description, f"Tool {tool.name} has no description"

        await _run_with_session(_check)


# ---------------------------------------------------------------------------
# Context-Aware Tools
# ---------------------------------------------------------------------------


class TestContextTools:
    """Context-Aware 基础工具 stdio 测试。"""

    @pytest.mark.anyio
    async def test_get_current_time(self) -> None:
        """get_current_time 应通过 stdio 正确返回 JSON。"""

        async def _check(session: ClientSession) -> None:
            result = await session.call_tool("get_current_time")
            assert not result.isError
            assert len(result.content) > 0
            data = json.loads(result.content[0].text)
            assert "date" in data
            assert "weekday" in data
            assert "weekday_number" in data

        await _run_with_session(_check)

    @pytest.mark.anyio
    async def test_get_semester_info(self) -> None:
        """get_semester_info 应通过 stdio 正确返回 JSON。"""

        async def _check(session: ClientSession) -> None:
            result = await session.call_tool("get_semester_info")
            assert not result.isError
            assert len(result.content) > 0
            data = json.loads(result.content[0].text)
            assert "semester_code" in data
            assert "semester_name" in data

        await _run_with_session(_check)


# ---------------------------------------------------------------------------
# Business Tools — Bus (无需认证)
# ---------------------------------------------------------------------------


class TestBusTool:
    """校车工具 stdio 测试 — 无需认证，可完整端到端验证。"""

    @pytest.mark.anyio
    async def test_bus_returns_data(self) -> None:
        """campus_bus 带 schedule_type 过滤应返回校车时刻数据。"""

        async def _check(session: ClientSession) -> None:
            result = await session.call_tool(
                "campus_bus", arguments={"schedule_type": "workday"}
            )
            assert not result.isError
            data = json.loads(result.content[0].text)
            assert isinstance(data, list)
            assert len(data) > 0

        await _run_with_session(_check)

    @pytest.mark.anyio
    async def test_bus_with_route_filter(self) -> None:
        """campus_bus 带路线过滤应返回匹配结果。"""

        async def _check(session: ClientSession) -> None:
            result = await session.call_tool(
                "campus_bus",
                arguments={"route": "兰台", "schedule_type": "holiday"},
            )
            assert not result.isError
            data = json.loads(result.content[0].text)
            assert isinstance(data, list)
            assert len(data) > 0
            for item in data:
                combined = json.dumps(item, ensure_ascii=False)
                assert "兰台" in combined

        await _run_with_session(_check)

    @pytest.mark.anyio
    async def test_bus_slim_output(self) -> None:
        """campus_bus 输出应已精简，仅保留 content 字段。"""

        async def _check(session: ClientSession) -> None:
            result = await session.call_tool(
                "campus_bus", arguments={"schedule_type": "workday"}
            )
            data = json.loads(result.content[0].text)
            first = data[0]
            # content 字段直接提升为顶层
            assert "route_name" in first
            assert "departure_time" in first
            # 信封字段已去除
            assert "raw_data" not in first
            assert "source" not in first
            assert "category" not in first

        await _run_with_session(_check)


# ---------------------------------------------------------------------------
# Business Tools — Venue (需认证)
# ---------------------------------------------------------------------------


class TestVenueTool:
    """场馆工具 stdio 测试。"""

    @pytest.mark.anyio
    async def test_venue_list_returns_data(self) -> None:
        """campus_venue_list 应返回场馆列表或 auth_required 错误。"""

        async def _check(session: ClientSession) -> None:
            result = await session.call_tool("campus_venue_list")
            text = result.content[0].text
            data = json.loads(text)
            if isinstance(data, list):
                assert len(data) > 0
                assert "name" in data[0]
            else:
                assert "error" in data

        await _run_with_session(_check)

    @pytest.mark.anyio
    async def test_venue_list_with_campus(self) -> None:
        """campus_venue_list 支持 campus 参数。"""

        async def _check(session: ClientSession) -> None:
            result = await session.call_tool(
                "campus_venue_list", arguments={"campus": "九龙湖"}
            )
            text = result.content[0].text
            data = json.loads(text)
            if isinstance(data, list):
                for item in data:
                    assert "九龙湖" in item.get("campus", "") or "九龙湖" in item.get(
                        "name", ""
                    )

        await _run_with_session(_check)


# ---------------------------------------------------------------------------
# Resources & Prompts
# ---------------------------------------------------------------------------


class TestResourcesAndPrompts:
    """MCP Resources 和 Prompts stdio 测试。"""

    @pytest.mark.anyio
    async def test_list_resources(self) -> None:
        """list_resources 应包含 bus-notes。"""

        async def _check(session: ClientSession) -> None:
            result = await session.list_resources()
            uris = [r.uri for r in result.resources]
            assert any("bus-notes" in str(u) for u in uris)

        await _run_with_session(_check)

    @pytest.mark.anyio
    async def test_read_bus_notes(self) -> None:
        """读取 bus-notes 资源应返回内容。"""

        async def _check(session: ClientSession) -> None:
            result = await session.read_resource("campus://info/bus-notes")
            assert len(result.contents) > 0
            text = result.contents[0].text
            assert "东南大学" in text

        await _run_with_session(_check)

    @pytest.mark.anyio
    async def test_list_prompts(self) -> None:
        """list_prompts 应包含系统提示词。"""

        async def _check(session: ClientSession) -> None:
            result = await session.list_prompts()
            names = [p.name for p in result.prompts]
            assert "campus_assistant_system_prompt" in names
            assert "campus_morning_briefing" in names

        await _run_with_session(_check)

    @pytest.mark.anyio
    async def test_get_system_prompt(self) -> None:
        """获取系统提示词应返回完整 SOP。"""

        async def _check(session: ClientSession) -> None:
            result = await session.get_prompt("campus_assistant_system_prompt")
            assert len(result.messages) > 0
            text = result.messages[0].content.text
            assert "get_current_time" in text
            assert "campus_bus" in text

        await _run_with_session(_check)
