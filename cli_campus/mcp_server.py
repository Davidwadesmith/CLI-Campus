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

import asyncio
import json
import logging
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import click
import typer
from mcp.server.fastmcp import FastMCP

from cli_campus.core.models import CampusEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 设计准则 (Design Guidelines)
# ---------------------------------------------------------------------------
# 1. 任何 MCP Tool 的单次返回 **必须 ≤ _MAX_RESPONSE_KB**。超出部分自动截断并
#    附加 truncated 标记。这是防止 LLM 上下文爆炸的硬性红线。
# 2. Adapter 返回的 JSON 应尽可能精简——去掉 raw_data、UUID、内部 ID 等对
#    大模型推理无价值的字段。_slim_for_agent() 是最后一道防线，但 Adapter 本身
#    也应遵循最小数据原则。
# 3. 嵌套/重复结构（如 venue slots 每个 slot 重复完整的 venue 对象）必须在
#    _slim_for_agent 中去重压平。
# 4. 静态资源 (data/resources/) 不应直接灌入 Tool 返回，而是通过
#    MCP Resource + search_resource 工具按需检索。
# ---------------------------------------------------------------------------

# 单次 Tool 返回的硬上限 (KB)。超出后自动截断并标记 truncated。
_MAX_RESPONSE_KB: int = 16

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


# 需要从嵌套 dict 中剥离的内部字段
_STRIP_KEYS: set[str] = {
    "raw_data",
    "id",
    "source",
    "category",
    "timestamp",
    "venue_id",
    "slot_id",
    "state",
}


def _slim_for_agent(raw: str) -> str:
    """精简 CLI JSON 输出并强制执行大小上限。

    处理流程:
    1. CampusEvent 信封 → 仅保留 ``title`` + ``content``
    2. VenueSlot 嵌套 → 按场馆分组，去重 venue 对象（约 **90%** 压缩）
    3. 通用列表 → 删除 ``_STRIP_KEYS`` 中的内部字段
    4. 全局硬截断 → 超过 ``_MAX_RESPONSE_KB`` 时截断并标记 ``truncated``
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return _enforce_size_limit(raw)

    # 仅处理列表格式
    if not isinstance(data, list) or not data:
        return _enforce_size_limit(raw)

    first = data[0]

    # ── CampusEvent 信封格式 (title + content + raw_data) ──
    if isinstance(first, dict) and "title" in first and "content" in first:
        slim = []
        for item in data:
            content = item.get("content")
            if isinstance(content, dict):
                # content 已包含业务字段，title 是冗余合成文本
                slim.append(content)
            else:
                slim.append({"title": item.get("title", "")})
        return _enforce_size_limit(json.dumps(slim, ensure_ascii=False))

    # ── VenueSlot 嵌套格式 ({venue: {...}, slot: {...}}) ──
    if (
        isinstance(first, dict)
        and "venue" in first
        and "slot" in first
        and isinstance(first["venue"], dict)
    ):
        return _enforce_size_limit(_slim_venue_slots(data))

    # ── 通用列表: 剥离内部字段 ──
    if isinstance(first, dict):
        stripped = [
            {k: v for k, v in item.items() if k not in _STRIP_KEYS} for item in data
        ]
        return _enforce_size_limit(json.dumps(stripped, ensure_ascii=False))

    return _enforce_size_limit(raw)


def _slim_venue_slots(data: list[dict[str, Any]]) -> str:
    """将重复的 venue+slot 扁平列表按场馆分组，去重 venue 信息。

    输入:  [{venue: {...}, slot: {...}}, ...]
    输出:  [{venue: "JLH01 ...", slots: [...]}, ...]
    """
    from collections import OrderedDict

    grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for item in data:
        venue = item.get("venue", {})
        slot = item.get("slot", {})
        key = venue.get("number", "") or venue.get("name", "")
        if key not in grouped:
            label = f"{venue.get('number', '')} {venue.get('name', '')}".strip()
            grouped[key] = {
                "venue": label,
                "campus": venue.get("campus", ""),
                "slots": [],
            }
        avail = slot.get("available", 0)
        status = slot.get("status_text", "")
        grouped[key]["slots"].append(
            {
                "time": f"{slot.get('start_time', '')}-{slot.get('end_time', '')}",
                "available": avail,
                "status": status,
            }
        )
    return json.dumps(list(grouped.values()), ensure_ascii=False)


def _enforce_size_limit(text: str) -> str:
    """如果文本超过 _MAX_RESPONSE_KB，截断并附加 truncated 标记。"""
    max_bytes = _MAX_RESPONSE_KB * 1024
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    # 截断到安全边界（避免截断多字节 UTF-8）
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    msg = (
        f"数据量过大 ({len(encoded) // 1024}KB)，"
        f"已截断至 {_MAX_RESPONSE_KB}KB。"
        "建议使用更精确的筛选参数缩小范围。"
    )
    return json.dumps(
        {
            "truncated": True,
            "message": msg,
            "partial_data": truncated,
        },
        ensure_ascii=False,
    )


def _invoke_cli_json(
    cmd_path: list[str],
    params: dict[str, Any],
    flag_map: dict[str, str] | None = None,
) -> str:
    """在进程内以 --json 模式调用 Typer 命令并捕获 stdout。

    通过 ``typer.testing.CliRunner`` 调用，避免启动子进程，
    复用已有的 CLI 逻辑（含错误处理和 JSON 序列化）。
    返回前会经过 ``_slim_for_agent`` 精简，去除 ``raw_data`` 等冗余字段。

    Args:
        cmd_path: 子命令路径，如 ``["venue", "list"]``。
        params: 参数名→值映射（Python 参数名作为 key）。
        flag_map: 参数名→实际 CLI flag 映射（如 ``{"type_name": "--type"}``）。
            由 ``_make_tool_function`` 从 Click 参数的 ``opts`` 中提取，
            确保即使 Typer 自定义了 flag 名，也能正确传递。
            若未提供则 fallback 到 ``--{name.replace('_', '-')}``。
    """
    from typer.testing import CliRunner

    from cli_campus.main import app as cli_app

    runner = CliRunner()

    # 构建参数列表: ["--json", "bus", "--route", "循环"]
    args: list[str] = ["--json"] + cmd_path
    _map = flag_map or {}

    for key, value in params.items():
        if value is None:
            continue
        # 优先使用注册时收集的真实 flag，fallback 到朴素转换
        flag = _map.get(key, f"--{key.replace('_', '-')}")
        if isinstance(value, bool):
            if value:
                args.append(flag)
        else:
            args.extend([flag, str(value)])

    result = runner.invoke(cli_app, args)

    # CLI 的 JSON 模式已经处理了所有异常并输出 JSON
    output = result.stdout.strip()
    if output:
        return _slim_for_agent(output)

    # stdout 为空 — 尝试从异常中提取信息
    if result.exception:
        return json.dumps(
            {
                "error": "cli_error",
                "message": str(result.exception),
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {"error": "empty_response", "message": "命令未返回数据"},
        ensure_ascii=False,
    )


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

    # 构建参数名→实际 CLI flag 映射 (e.g. {"type_name": "--type"})
    captured_flag_map: dict[str, str] = {}
    for p in valid_params:
        if p.name and hasattr(p, "opts") and p.opts:
            # opts[0] 是长 flag (如 "--type")，优先使用
            captured_flag_map[p.name] = p.opts[0]

    func_code = textwrap.dedent(f"""\
        async def {tool_name}({sig_str}) -> str:
            # 收集非 None 参数
            _locals = dict(locals())
            _params = {{k: v for k, v in _locals.items() if v is not None}}
            return await _to_thread(_invoke, _cmd_path, _params, _flag_map)
    """)

    local_ns: dict[str, Any] = {
        "_invoke": _invoke_cli_json,
        "_to_thread": asyncio.to_thread,
        "_cmd_path": captured_cmd_path,
        "_flag_map": captured_flag_map,
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
# 模块三：静态资源系统 (Static Resource Context)
# ---------------------------------------------------------------------------

# 资源目录
_RESOURCES_DIR = Path(__file__).parent / "data" / "resources"

# 缓存: stem → (标题, 全文)
_resource_cache: dict[str, tuple[str, str]] = {}


def _load_resources() -> None:
    """扫描 data/resources/ 目录，将 .md 和 .pdf 文件载入缓存。

    - ``.md`` 文件直接读取原文。
    - ``.pdf`` 文件通过 pymupdf 提取文本；若为纯扫描件（无可提取文本），
      则生成占位说明，引导 Agent 使用同名 .md 摘要或 search_resource 检索。
    """
    if _resource_cache:
        return  # 已加载
    if not _RESOURCES_DIR.is_dir():
        return
    for p in sorted(_RESOURCES_DIR.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        first_line = text.split("\n", 1)[0].strip()
        if first_line.startswith("#"):
            title = first_line.lstrip("# ").strip()
        else:
            title = p.stem
        _resource_cache[p.stem] = (title, text)
    # PDF 支持 (需 pymupdf)
    for p in sorted(_RESOURCES_DIR.glob("*.pdf")):
        try:
            import pymupdf  # noqa: F811

            doc = pymupdf.open(str(p))
            pages_text = [page.get_text() for page in doc]
            full_text = "\n".join(pages_text).strip()
            doc.close()
            if len(full_text) < 100:
                # 纯扫描件，无可提取文本
                full_text = (
                    f"# {p.stem}\n\n"
                    f"本文档为扫描版 PDF（{len(pages_text)} 页），"
                    "无法直接提取文本。\n"
                    "请使用 search_resource 工具搜索同名的文字摘要版，"
                    "或向用户说明需要查阅原始 PDF 文件。"
                )
            title = p.stem
            _resource_cache[p.stem] = (title, full_text)
        except ImportError:
            logger.debug("pymupdf not installed, skipping PDF: %s", p.name)
        except Exception:
            logger.warning("Failed to load PDF: %s", p.name, exc_info=True)


def auto_register_resources() -> int:
    """将 data/resources/*.md 注册为 MCP Resources。

    Returns:
        注册的资源数量。
    """
    _load_resources()

    for stem, (title, _text) in _resource_cache.items():
        # 用闭包捕获 stem — 注意 Python late-binding 陷阱，
        # 须通过工厂函数立即绑定
        def _make_reader(s: str) -> Any:
            async def _reader() -> str:
                return _resource_cache[s][1]

            return _reader

        mcp.resource(
            f"campus://resources/{stem}",
            name=stem,
            title=title,
            description=f"校园参考资料: {title}",
            mime_type="text/markdown",
        )(_make_reader(stem))

    count = len(_resource_cache)
    if count:
        logger.info("Auto-registered %d static resources", count)
    return count


@mcp.resource(
    "campus://resources",
    name="resource_index",
    title="校园参考资料索引",
    description="列出所有可用的校园参考文档，供 Agent 选择读取。",
    mime_type="application/json",
)
async def resource_index() -> str:
    """返回所有已注册静态资源的索引列表。"""
    _load_resources()
    items = [
        {
            "name": stem,
            "title": title,
            "uri": f"campus://resources/{stem}",
        }
        for stem, (title, _) in _resource_cache.items()
    ]
    return json.dumps(items, ensure_ascii=False)


@mcp.tool()
async def search_resource(query: str, resource_name: str = "") -> str:
    """在校园参考资料中搜索包含关键词的段落。

    用于快速检索学生手册、校规校纪等长文档中的相关内容，
    避免将整篇文档填入上下文。返回所有匹配段落（按 ## 标题分段）。

    Args:
        query: 搜索关键词（如"奖学金"、"补考"、"宿舍"）。
        resource_name: 限定在某个资源中搜索（如"student_handbook"）。
            留空则搜索全部资源。
    """
    _load_resources()
    if not _resource_cache:
        return json.dumps(
            {"error": "no_resources", "message": "暂无可用参考资料"},
            ensure_ascii=False,
        )

    targets = (
        {resource_name: _resource_cache[resource_name]}
        if resource_name and resource_name in _resource_cache
        else _resource_cache
    )

    results: list[dict[str, str]] = []
    for stem, (title, text) in targets.items():
        # 按 ## 切分段落
        sections = text.split("\n## ")
        for i, section in enumerate(sections):
            if query.lower() in section.lower():
                # 还原 ## 前缀（第一段是文件头部）
                heading = section.split("\n", 1)[0].strip().lstrip("# ")
                body = section.strip()
                if i > 0:
                    body = "## " + body
                results.append({"resource": stem, "section": heading, "content": body})

    if not results:
        return json.dumps(
            {"matches": 0, "message": f"未找到包含 '{query}' 的内容"},
            ensure_ascii=False,
        )

    return json.dumps(
        {"matches": len(results), "results": results},
        ensure_ascii=False,
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
auto_register_resources()


# ---------------------------------------------------------------------------
# 独立入口 — 绕过 Typer，供 MCP 客户端直接调用
# ---------------------------------------------------------------------------


def main() -> None:
    """以 stdio 模式启动 MCP Server。"""
    mcp.run()


if __name__ == "__main__":
    main()
