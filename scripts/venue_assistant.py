#!/usr/bin/env python3
"""场馆预约 AI 助手 — 交互式对话完成场馆查询、预约与取消。

使用方法:
    # 设置 API Key (DeepSeek / OpenAI 兼容接口)
    export OPENAI_API_KEY="your-api-key"
    export OPENAI_BASE_URL="https://api.deepseek.com"  # 可选

    python scripts/venue_assistant.py

在对话中可以：
- "帮我看看明天九龙湖有没有空的羽毛球场"
- "预约 JLH01 明天 14:00-15:00"
- "查一下我的预约"
- "取消我的预约"
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import sys
from pathlib import Path

# 将项目根目录加入路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_campus.adapters.venue_adapter import VenueAdapter  # noqa: E402

# ---------------------------------------------------------------------------
# Tool 定义 — Function Calling Schema
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "venue_list",
            "description": "列出指定类型的所有可预约场馆。返回场馆名称、编号、校区、容量等信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "type_name": {
                        "type": "string",
                        "description": "场馆类型名称，如 '羽毛球场'、'网球场'、'篮球馆'、'乒乓球台'、'游泳馆'、'健身房'",
                        "default": "羽毛球场",
                    },
                    "campus": {
                        "type": "string",
                        "description": "校区筛选，如 '九龙湖'、'四牌楼'、'丁家桥'、'无锡'。留空则返回所有校区。",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "venue_slots",
            "description": "查询指定场馆在指定日期的时段可用情况。返回每个时段的开始/结束时间、可预约数量和状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "venue_id": {
                        "type": "string",
                        "description": "场馆 UUID。如果只有编号（如 JLH01），先调用 venue_list 获取 UUID。",
                    },
                    "date": {
                        "type": "string",
                        "description": "查询日期 (YYYY-MM-DD 格式)。默认明天。",
                    },
                },
                "required": ["venue_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "venue_slots_batch",
            "description": "批量查询多个场馆在指定日期的时段可用情况。适合一次性查看某个校区所有场地的空闲状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "type_name": {
                        "type": "string",
                        "description": "场馆类型名称",
                        "default": "羽毛球场",
                    },
                    "campus": {
                        "type": "string",
                        "description": "校区筛选",
                    },
                    "date": {
                        "type": "string",
                        "description": "查询日期 (YYYY-MM-DD)。默认明天。",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "venue_book",
            "description": "提交场馆预约。需要指定场馆 UUID、日期、时段。可通过编号查找场馆。",
            "parameters": {
                "type": "object",
                "properties": {
                    "venue_id": {
                        "type": "string",
                        "description": "场馆 UUID 或编号 (如 JLH01)。如果是编号，需配合 type_name 查找。",
                    },
                    "date": {
                        "type": "string",
                        "description": "预约日期 (YYYY-MM-DD)。默认明天。",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "开始时间 (HH:MM，如 '14:00')",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间 (HH:MM，如 '15:00')",
                    },
                    "event": {
                        "type": "string",
                        "description": "活动名称，默认 '运动健身'",
                        "default": "运动健身",
                    },
                    "type_name": {
                        "type": "string",
                        "description": "场馆类型（用于通过编号查找 UUID）",
                        "default": "羽毛球场",
                    },
                },
                "required": ["venue_id", "start_time", "end_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "venue_cancel",
            "description": "取消指定的预约。需要提供预约 ID。",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {
                        "type": "string",
                        "description": "要取消的预约 ID",
                    },
                    "reason": {
                        "type": "string",
                        "description": "取消原因",
                        "default": "",
                    },
                },
                "required": ["booking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "venue_my_bookings",
            "description": "查看当前用户的所有预约记录。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前时间。用于判断今天日期和可预约时段。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# ---------------------------------------------------------------------------
# Tool 执行
# ---------------------------------------------------------------------------


async def execute_tool(
    adapter: VenueAdapter, func_name: str, args: dict
) -> str:
    """执行工具调用并返回 JSON 字符串。"""
    try:
        if func_name == "venue_list":
            type_name = args.get("type_name", "羽毛球场")
            venues = await adapter.get_venues(type_name)
            campus = args.get("campus", "")
            if campus:
                venues = [
                    v for v in venues if campus in v.campus or campus in v.name
                ]
            return json.dumps(
                [v.model_dump() for v in venues], ensure_ascii=False
            )

        elif func_name == "venue_slots":
            venue_id = args["venue_id"]
            date = args.get("date") or _tomorrow()
            slots = await adapter.get_time_slots(venue_id, date)
            return json.dumps(
                [s.model_dump() for s in slots], ensure_ascii=False
            )

        elif func_name == "venue_slots_batch":
            type_name = args.get("type_name", "羽毛球场")
            campus = args.get("campus", "")
            date = args.get("date") or _tomorrow()

            venues = await adapter.get_venues(type_name)
            if campus:
                venues = [
                    v for v in venues if campus in v.campus or campus in v.name
                ]

            result = []
            for venue in venues:
                try:
                    slots = await adapter.get_time_slots(venue.venue_id, date)
                    available_slots = [s for s in slots if s.available > 0]
                    result.append(
                        {
                            "venue": venue.model_dump(),
                            "date": date,
                            "total_slots": len(slots),
                            "available_slots": len(available_slots),
                            "slots": [s.model_dump() for s in slots],
                        }
                    )
                except Exception:
                    pass
            return json.dumps(result, ensure_ascii=False)

        elif func_name == "venue_book":
            venue_id = args["venue_id"]
            date = args.get("date") or _tomorrow()
            start = args["start_time"]
            end = args["end_time"]
            event = args.get("event", "运动健身")
            type_name = args.get("type_name", "羽毛球场")

            # 如果是编号而非 UUID，先查找
            if len(venue_id) < 36:
                venues = await adapter.get_venues(type_name)
                matched = [
                    v for v in venues if v.number.upper() == venue_id.upper()
                ]
                if not matched:
                    return json.dumps(
                        {"error": f"未找到编号为 {venue_id} 的场馆"},
                        ensure_ascii=False,
                    )
                venue_id = matched[0].venue_id

            booking = await adapter.make_booking(venue_id, date, start, end, event)
            return json.dumps(booking.model_dump(), ensure_ascii=False)

        elif func_name == "venue_cancel":
            booking_id = args["booking_id"]
            reason = args.get("reason", "")
            success = await adapter.cancel_booking(booking_id, reason)
            return json.dumps(
                {"success": success, "booking_id": booking_id},
                ensure_ascii=False,
            )

        elif func_name == "venue_my_bookings":
            bookings = await adapter.get_my_bookings()
            return json.dumps(
                [b.model_dump() for b in bookings], ensure_ascii=False
            )

        elif func_name == "get_current_time":
            now = VenueAdapter.get_current_time()
            return json.dumps(
                {
                    "datetime": now.isoformat(),
                    "date": now.strftime("%Y-%m-%d"),
                    "time": now.strftime("%H:%M:%S"),
                    "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
                        now.weekday()
                    ],
                    "tomorrow": (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
                },
                ensure_ascii=False,
            )

        else:
            return json.dumps({"error": f"未知工具: {func_name}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _tomorrow() -> str:
    return (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 交互式对话
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是东南大学场馆预约助手，帮助学生完成体育场馆的查询、预约和取消。

你可以：
1. 查询可预约的场馆列表（羽毛球场、网球场、篮球馆、乒乓球台等）
2. 查看指定场馆的空闲时段
3. 帮用户预约场馆
4. 查看和取消已有预约

注意事项：
- 场馆分布在四个校区：九龙湖、四牌楼、丁家桥、无锡
- 羽毛球场编号规则：JLH01-JLH13(九龙湖)、SPL01-SPL04(四牌楼)、DJQ001/DJQ003(丁家桥)、WX02-WX10(无锡)
- 每个时段1小时，从09:00到21:00
- 预约前请先查看时段可用情况
- 回答简洁友好，使用中文
- 如果用户没有指定校区，默认九龙湖
- 如果用户没有指定日期，默认明天"""


async def chat_loop() -> None:
    """交互式对话主循环。"""
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ 请安装 openai 库: pip install openai")
        sys.exit(1)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ 请设置环境变量 OPENAI_API_KEY")
        print("  set OPENAI_API_KEY=your-api-key")
        print('  set OPENAI_BASE_URL=https://api.deepseek.com  # 可选')
        sys.exit(1)

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("OPENAI_MODEL", "deepseek-chat")

    client = OpenAI(api_key=api_key, base_url=base_url)
    adapter = VenueAdapter()

    print("🏟 东南大学场馆预约助手")
    print(f"  模型: {model} @ {base_url}")
    print("  输入 'quit' 退出\n")

    # 预认证
    try:
        ok = await adapter.check_auth()
        if ok:
            print("✅ 场馆系统认证成功\n")
        else:
            print("⚠️ 认证失败，请检查凭证\n")
    except Exception as e:
        print(f"⚠️ 认证异常: {e}\n")

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("👋 再见！")
            break

        messages.append({"role": "user", "content": user_input})

        # LLM 调用 (可能多轮 tool call)
        while True:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            msg = response.choices[0].message

            if msg.tool_calls:
                # 执行工具调用
                messages.append(msg)
                for tc in msg.tool_calls:
                    func = tc.function
                    args = json.loads(func.arguments) if func.arguments else {}
                    print(f"  🔧 {func.name}({json.dumps(args, ensure_ascii=False)[:80]})")

                    result = await execute_tool(adapter, func.name, args)
                    # 截断过长的结果
                    if len(result) > 4000:
                        result = result[:4000] + '..."}'

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        }
                    )
                # 继续循环让 LLM 处理工具结果
                continue
            else:
                # LLM 直接文本回复
                reply = msg.content or ""
                messages.append({"role": "assistant", "content": reply})
                print(f"\n🤖 {reply}\n")
                break

    await adapter.close()


def main() -> None:
    asyncio.run(chat_loop())


if __name__ == "__main__":
    main()
