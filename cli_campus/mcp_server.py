"""CLI-Campus MCP Server — 将 Adapter 能力暴露为 MCP Tools / Resources / Prompts。

通过 FastMCP 将底层 Adapter 封装为标准 MCP 协议，
使 Claude Desktop 或通用 Agent 可直接调用校园数据能力。

**本模块不依赖 Typer 解析逻辑，直接调用 Adapter 层。**
"""

from __future__ import annotations

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP

from cli_campus.core.exceptions import AdapterError, AuthFailedError, AuthRequiredError
from cli_campus.core.models import CampusEvent

# ---------------------------------------------------------------------------
# Server 初始化
# ---------------------------------------------------------------------------

mcp = FastMCP("CLI-Campus")

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _events_to_json(events: list[CampusEvent]) -> str:
    """将 CampusEvent 列表序列化为 JSON 字符串。"""
    return json.dumps(
        [e.model_dump(mode="json") for e in events],
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_campus_bus(route: str = "", schedule_type: str = "") -> str:
    """查询校车时刻表。

    返回东南大学校区接驳车发车时间，支持按线路和时刻表类型筛选。

    Args:
        route: 按线路名称模糊筛选，如 "循环"、"兰台"。
            留空返回全部线路。
        schedule_type: 时刻表类型，可选值: "workday"(工作日)、
            "holiday"(节假日)、"spring_festival"(寒假)。
            留空返回全部类型。

    Returns:
        JSON 格式的校车时刻数据数组。
        每条记录包含线路名、发车时间、出发站、到达站等信息。
    """
    from cli_campus.adapters.bus_adapter import BusAdapter

    adapter = BusAdapter()
    events = await adapter.fetch(route=route, schedule_type=schedule_type)
    return _events_to_json(events)


@mcp.tool()
async def get_course_schedule(semester: str = "", week: Optional[int] = None) -> str:
    """查询本学期课程表。

    通过东南大学 ehall 教务系统获取学生课程安排，
    需要用户事先通过 campus auth login 登录。

    Args:
        semester: 学年学期代码，格式如 "2025-2026-3"。
            留空则自动推算当前学期。
        week: 仅返回指定教学周有课的课程。
            留空返回全部课程。

    Returns:
        JSON 格式的课程数据数组。每条记录包含课程名、
        教师、教室、星期、节次、周次等信息。
        如果凭证缺失或失效，返回包含错误提示的 JSON。
    """
    from cli_campus.adapters.course_adapter import (
        CourseAdapter,
        parse_weeks,
    )

    config: dict[str, str] = {}
    if semester:
        config["semester"] = semester

    adapter = CourseAdapter(config=config if config else None)

    try:
        events = await adapter.fetch()
    except AuthRequiredError:
        return json.dumps(
            {
                "error": "auth_required",
                "message": (
                    "凭证未找到或已失效，"
                    "请用户先在终端运行 "
                    "`campus auth login` 完成登录。"
                ),
            },
            ensure_ascii=False,
        )
    except AuthFailedError as exc:
        return json.dumps(
            {"error": "auth_failed", "message": str(exc)},
            ensure_ascii=False,
        )
    except AdapterError as exc:
        return json.dumps(
            {"error": "adapter_error", "message": str(exc)},
            ensure_ascii=False,
        )

    # --week 过滤
    if week is not None:
        events = [e for e in events if week in parse_weeks(e.content.get("weeks", ""))]

    return _events_to_json(events)


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------


@mcp.resource("campus://info/bus-notes")
async def bus_notes() -> str:
    """校车时刻表特殊规则说明。

    提供东南大学校车系统的背景知识，帮助大模型理解节假日、
    短驳车、循环巴士等局部上下文。
    """
    return (
        "【东南大学校车时刻表特殊规则】\n"
        "\n"
        "1. 时刻表类型:\n"
        "   - workday: 工作日时刻表（学期中周一至周五）\n"
        "   - holiday: 节假日/周末时刻表（班次较少）\n"
        "   - spring_festival: 寒假时刻表（仅保留最基本班次）\n"
        "\n"
        "2. 主要线路:\n"
        "   - 九龙湖校园循环巴士: 校内接驳，途经图书馆、教学楼、宿舍区\n"
        "   - 九龙湖—四牌楼: 连接主校区与老校区，约 40 分钟车程\n"
        "   - 九龙湖—丁家桥: 连接主校区与医学院校区\n"
        "\n"
        "3. 注意事项:\n"
        "   - 发车时间为从始发站出发时间，非到站时间\n"
        "   - 法定节假日和学校调休日参照 holiday 时刻表\n"
        "   - 恶劣天气或特殊活动可能临时调整班次\n"
        "   - 循环巴士在高峰期（上下课时段）班次最密集\n"
        "   - 数据来源: 东南大学总务处 (zwc.seu.edu.cn)\n"
    )


# ---------------------------------------------------------------------------
# MCP Prompts
# ---------------------------------------------------------------------------


@mcp.prompt()
async def campus_morning_briefing() -> str:
    """生成校园早间速报的预设提示词。

    包含系统级指令，引导大模型使用 get_course_schedule 和 get_campus_bus 工具
    为用户生成一份当日校园简报。
    """
    return (
        "你是一个东南大学校园助手。请按照以下步骤为用户生成今天的校园早报：\n"
        "\n"
        "1. 使用 get_course_schedule 工具查询今天的课程安排。\n"
        "   - 如果返回中包含 auth_required 错误，友善地提醒用户先在终端运行 "
        "`campus auth login` 登录。\n"
        "2. 使用 get_campus_bus 工具查询校车时刻"
        "（建议筛选 schedule_type='workday'）。\n"
        "3. 综合以上信息，用简洁友好的中文生成一份早间速报，包括：\n"
        "   - 今天有哪些课程，上课时间和地点\n"
        "   - 推荐的通勤校车班次（根据第一节课时间推荐合适的出发班次）\n"
        "   - 如果有晚课，也提示返程校车班次\n"
        "\n"
        "请确保信息准确，不要编造任何课程或校车数据，一切以工具返回结果为准。"
    )


# ---------------------------------------------------------------------------
# 独立入口 — 绕过 Typer，供 MCP 客户端直接调用
# ---------------------------------------------------------------------------


def main() -> None:
    """以 stdio 模式启动 MCP Server。"""
    mcp.run()


if __name__ == "__main__":
    main()
