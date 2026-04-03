"""CLI-Campus MCP Server — 自动挂载引擎 (Auto-Discovery Tool Factory)。

通过 FastMCP 将底层 CLI 命令能力自动暴露为标准 MCP Tools / Resources / Prompts，
使 Claude Desktop 或通用 Agent 可直接调用校园数据能力。

**核心设计**:
- 模块一：Context-Aware 基础感知工具（时间、学期），无需凭证。
- 模块二：Auto-Registrar 引擎，反射 Typer 命令树，动态生成 MCP Tools。
  彻底消灭手动编写 ``@mcp.tool()`` 包裹函数的体力活。

**技术要点**:
- 动态函数通过 ``exec()`` 构建，拥有正确的 ``__signature__``、
  ``__annotations__`` 和 ``__doc__``，确保 FastMCP 能推导出完整的 JSON Schema。
- 业务工具统一捕获 ``AuthRequiredError`` / ``AuthFailedError`` / ``AdapterError``，
  将异常转化为结构化 JSON 错误信息返回给大模型。
"""

from __future__ import annotations

import json
import logging
import textwrap
from datetime import datetime
from typing import Any, Optional

import click
import typer
from mcp.server.fastmcp import FastMCP

from cli_campus.core.models import CampusEvent

logger = logging.getLogger(__name__)

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
# 模块一：Context-Aware 基础感知工具
# ---------------------------------------------------------------------------

_DAY_NAMES: dict[int, str] = {
    0: "周一",
    1: "周二",
    2: "周三",
    3: "周四",
    4: "周五",
    5: "周六",
    6: "周日",
}


@mcp.tool()
async def get_current_time() -> str:
    """获取当前系统的准确日期、时间和星期几。

    在处理包含"今天"、"明天"、"这周"、"下周"等相对时间的请求时，
    **必须先调用此工具**以获取准确的时间锚点，避免因缺少时间上下文
    而产生错误推断。

    Returns:
        JSON 字符串，包含以下字段:
        - date: 日期 (YYYY-MM-DD)
        - time: 时间 (HH:MM:SS)
        - weekday: 星期几 (如 "周三")
        - weekday_number: 星期几数字 (1=周一, 7=周日)
        - timestamp: ISO 8601 完整时间戳
    """
    now = datetime.now()
    weekday_num = now.isoweekday()  # 1=Monday, 7=Sunday
    return json.dumps(
        {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday": _DAY_NAMES.get(now.weekday(), ""),
            "weekday_number": weekday_num,
            "timestamp": now.isoformat(),
        },
        ensure_ascii=False,
    )


@mcp.tool()
async def get_semester_info() -> str:
    """获取当前的学年学期代码和学期名称。

    在调用课程表 (get_course_schedule)、成绩 (get_grade)、
    考试安排 (get_exam) 等涉及学期参数的工具之前，
    **建议先调用此工具**获取当前学期的基准信息作为默认参数。

    Returns:
        JSON 字符串，包含以下字段:
        - semester_code: 学年学期代码 (如 "2025-2026-3")
        - academic_year: 学年 (如 "2025-2026")
        - semester_name: 学期中文名 (如 "春季")
        - semester_number: 学期编号 (1=暑期学校, 2=秋季, 3=春季)
    """
    from cli_campus.adapters.course_adapter import (
        _SEMESTER_NAMES,
        compute_current_semester,
    )

    code = compute_current_semester()
    parts = code.split("-")
    academic_year = f"{parts[0]}-{parts[1]}" if len(parts) == 3 else code
    sem_num = parts[2] if len(parts) == 3 else ""
    sem_name = _SEMESTER_NAMES.get(sem_num, "")

    return json.dumps(
        {
            "semester_code": code,
            "academic_year": academic_year,
            "semester_name": sem_name,
            "semester_number": sem_num,
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# 模块二：MCP Tool 自动挂载引擎 (Auto-Registrar)
# ---------------------------------------------------------------------------

# 不应暴露为 MCP Tool 的元命令
_SKIP_COMMANDS: set[str] = {
    "auth",
    "test-adapter",
    "version",
    "fetch-list",
    "schema",
    "sop",
    "mcp",
}

# Click 类型 → Python 类型注解映射
_CLICK_TYPE_MAP: dict[str, type] = {
    "integer": int,
    "float": float,
    "boolean": bool,
    "string": str,
}


def _click_param_to_python_type(param: click.Parameter) -> type:
    """将 Click 参数类型映射为 Python 类型注解。"""
    return _CLICK_TYPE_MAP.get(param.type.name, str)


def _build_tool_docstring(cmd: click.Command, params: list[click.Parameter]) -> str:
    """从 Click 命令的 help 和参数 help 构建 MCP 工具的 docstring。"""
    lines: list[str] = []

    # 主描述
    help_text = (cmd.help or "").strip()
    if help_text:
        lines.append(help_text)
    else:
        lines.append(f"执行 campus {cmd.name} 命令。")

    # 如需认证的提示
    lines.append("")
    lines.append(
        "如果返回包含 error 字段，说明操作失败，"
        "请根据 error 类型提示用户（如 auth_required 需先登录）。"
    )

    # 参数文档
    param_docs = [p for p in params if p.name not in ("json_output", "help")]
    if param_docs:
        lines.append("")
        lines.append("Args:")
        for p in param_docs:
            desc = p.help or ""
            lines.append(f"    {p.name}: {desc}")

    return "\n".join(lines)


def _invoke_cli_json(cmd_path: list[str], params: dict[str, Any]) -> str:
    """在进程内以 --json 模式调用 Typer 命令并捕获 stdout。

    通过 ``typer.testing.CliRunner`` 调用，避免启动子进程，
    复用已有的 CLI 逻辑（含错误处理和 JSON 序列化）。
    """
    from typer.testing import CliRunner

    from cli_campus.main import app as cli_app

    runner = CliRunner()

    # 构建参数列表: ["--json", "bus", "--route", "循环"]
    args: list[str] = ["--json"] + cmd_path

    for key, value in params.items():
        if value is None:
            continue
        # 将 Python 参数名转回 CLI flag: semester → --semester
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                args.append(flag)
        else:
            args.extend([flag, str(value)])

    result = runner.invoke(cli_app, args)

    # CLI 的 JSON 模式已经处理了所有异常并输出 JSON
    output = result.stdout.strip()
    if not output:
        return json.dumps(
            {"error": "empty_response", "message": "命令未返回数据"},
            ensure_ascii=False,
        )
    return output


def _make_tool_function(
    tool_name: str,
    cmd_path: list[str],
    params: list[click.Parameter],
    docstring: str,
) -> Any:
    """动态生成一个具有正确类型注解的 async 包装函数。

    FastMCP 通过 ``inspect.signature()`` 和 ``__annotations__``
    来推导 JSON Schema，因此动态函数必须拥有完整的签名。

    策略：使用 ``exec()`` 在局部命名空间中定义函数，
    确保每个参数都有准确的类型注解和默认值。
    """
    # 收集有效参数（过滤掉全局 --json 和 --help）
    valid_params = [
        p for p in params if p.name and p.name not in ("json_output", "help")
    ]

    # 构建函数签名的参数列表
    sig_parts: list[str] = []
    annotations: dict[str, Any] = {}
    for p in valid_params:
        py_type = _click_param_to_python_type(p)
        param_name = p.name or ""

        # 确定默认值
        if p.default is not None and p.default != ():
            if isinstance(p.default, str):
                default_repr = repr(p.default)
            elif isinstance(p.default, bool):
                default_repr = repr(p.default)
            else:
                default_repr = repr(p.default)
        else:
            # 对 Optional 参数赋 None 默认值
            default_repr = "None"
            # 用 Optional 包裹
            py_type = Optional[py_type]  # type: ignore[assignment]

        sig_parts.append(f"{param_name} = {default_repr}")
        annotations[param_name] = py_type

    sig_str = ", ".join(sig_parts)
    # 闭包捕获: cmd_path
    captured_cmd_path = list(cmd_path)

    func_code = textwrap.dedent(f"""\
        async def {tool_name}({sig_str}) -> str:
            # 收集非 None 参数
            _locals = dict(locals())
            _params = {{k: v for k, v in _locals.items() if v is not None}}
            return _invoke(_cmd_path, _params)
    """)

    local_ns: dict[str, Any] = {
        "_invoke": _invoke_cli_json,
        "_cmd_path": captured_cmd_path,
    }
    exec(func_code, local_ns)  # noqa: S102

    func = local_ns[tool_name]
    func.__doc__ = docstring
    func.__annotations__ = {**annotations, "return": str}
    func.__module__ = __name__

    return func


def _register_command(
    name: str,
    cmd: click.Command,
    *,
    cmd_path: list[str] | None = None,
    prefix: str = "campus",
) -> None:
    """将单个 Click 命令动态注册为 MCP Tool。"""
    path = cmd_path or [name]
    tool_name = f"{prefix}_{'_'.join(path)}".replace("-", "_")

    # 提取参数
    params: list[click.Parameter] = cmd.params

    # 构建 docstring
    docstring = _build_tool_docstring(cmd, params)

    # 动态生成函数
    func = _make_tool_function(tool_name, path, params, docstring)

    # 注册到 FastMCP
    mcp.tool()(func)

    logger.debug("Auto-registered MCP tool: %s → %s", tool_name, path)


def auto_register_tools() -> int:
    """遍历 Typer 命令树，将业务命令自动注册为 MCP Tools。

    Returns:
        成功注册的工具数量。
    """
    from cli_campus.main import app as cli_app

    cli = typer.main.get_command(cli_app)
    count = 0

    for name, cmd in cli.commands.items():
        if name in _SKIP_COMMANDS:
            continue

        if isinstance(cmd, click.Group):
            # 子命令组 (如 venue) — 为每个子命令生成独立 tool
            for sub_name, sub_cmd in cmd.commands.items():
                _register_command(
                    f"{name}_{sub_name}",
                    sub_cmd,
                    cmd_path=[name, sub_name],
                )
                count += 1
        else:
            _register_command(name, cmd, cmd_path=[name])
            count += 1

    logger.info("Auto-registered %d MCP tools from CLI commands", count)
    return count


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
async def campus_assistant_system_prompt() -> str:
    """校园助手系统提示词 — 指导大模型正确使用 CLI-Campus 工具。

    建立标准 SOP: 查时间 → 算参数 → 调业务工具。
    """
    return (
        "你是一个东南大学校园助手，可以通过 CLI-Campus 工具集查询校园信息。\n"
        "\n"
        "## 核心工作流 (SOP)\n"
        "\n"
        "处理任何校园查询请求时，请严格遵循以下步骤：\n"
        "\n"
        "### Step 1: 获取时间锚点\n"
        "- 调用 `get_current_time` 获取当前日期、星期几。\n"
        '- 如果用户说"今天"、"明天"、"这周"等相对时间，\n'
        "  必须先确定绝对日期再进行后续查询。\n"
        "\n"
        "### Step 2: 获取学期基准 (如需)\n"
        "- 如果要查课表、成绩、考试，先调用 `get_semester_info`\n"
        "  获取当前学期代码 (如 2025-2026-3)。\n"
        "- 将学期代码作为参数传给后续业务工具。\n"
        "\n"
        "### Step 3: 调用业务工具\n"
        "- 根据用户意图选择对应的业务工具:\n"
        "  - 校车: `campus_bus` (无需登录)\n"
        "  - 课表: `campus_course` (需登录)\n"
        "  - 成绩: `campus_grade` (需登录)\n"
        "  - 考试: `campus_exam` (需登录)\n"
        "  - 一卡通: `campus_card` (需登录)\n"
        "  - 场馆: `campus_venue_*` 系列 (需登录)\n"
        "\n"
        "### 错误处理\n"
        "- 如果工具返回 `auth_required` 错误，友善提醒用户先在终端运行\n"
        "  `campus auth login` 完成登录。\n"
        "- 如果返回 `adapter_error`，告知用户系统暂时不可用。\n"
        "\n"
        "### 注意事项\n"
        "- 所有工具返回 JSON 格式数据，请据此生成人类可读的回复。\n"
        "- 不要编造任何数据，一切以工具返回结果为准。\n"
        "- 校车数据为静态数据，无需登录即可查询。\n"
    )


@mcp.prompt()
async def campus_morning_briefing() -> str:
    """生成校园早间速报的预设提示词。

    包含系统级指令，引导大模型使用工具为用户生成一份当日校园简报。
    """
    return (
        "你是一个东南大学校园助手。请按照以下步骤为用户生成今天的校园早报：\n"
        "\n"
        "1. 使用 get_current_time 工具获取今天的准确日期和星期几。\n"
        "2. 使用 get_semester_info 工具获取当前学期代码。\n"
        "3. 使用 campus_course 工具查询今天的课程安排。\n"
        "   - 如果返回中包含 auth_required 错误，友善地提醒用户先在终端运行 "
        "`campus auth login` 登录。\n"
        "4. 使用 campus_bus 工具查询校车时刻"
        "（建议筛选 schedule_type='workday'）。\n"
        "5. 综合以上信息，用简洁友好的中文生成一份早间速报，包括：\n"
        "   - 今天有哪些课程，上课时间和地点\n"
        "   - 推荐的通勤校车班次（根据第一节课时间推荐合适的出发班次）\n"
        "   - 如果有晚课，也提示返程校车班次\n"
        "\n"
        "请确保信息准确，不要编造任何课程或校车数据，一切以工具返回结果为准。"
    )


# ---------------------------------------------------------------------------
# 启动时自动注册
# ---------------------------------------------------------------------------

auto_register_tools()


# ---------------------------------------------------------------------------
# 独立入口 — 绕过 Typer，供 MCP 客户端直接调用
# ---------------------------------------------------------------------------


def main() -> None:
    """以 stdio 模式启动 MCP Server。"""
    mcp.run()


if __name__ == "__main__":
    main()
