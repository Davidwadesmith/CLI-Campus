"""CLI-Campus 主入口 — 基于 Typer 的命令行应用。

此模块只负责：
1. 接收用户命令与参数。
2. 调用对应的 Adapter 获取数据。
3. 通过 Rich 渲染终端 UI 或输出纯 JSON。

**严禁** 在此文件中编写任何网络请求、HTML 解析或数据清洗逻辑。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from cli_campus.adapters.mock_adapter import MockAdapter
from cli_campus.core.exceptions import AdapterError, AuthFailedError, AuthRequiredError
from cli_campus.core.models import CampusEvent

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="campus",
    help="CLI-Campus: Agent-Native Campus Toolkit 🎓",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()

# 全局 JSON 输出标志 — 通过 Typer callback 拦截
_json_output: bool = False


# ---------------------------------------------------------------------------
# 全局 Callback — JSON 中间件
# ---------------------------------------------------------------------------


@app.callback()
def main_callback(
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="以纯 JSON 格式输出结果（适用于 Agent / 管道调用）。",
    ),
) -> None:
    """CLI-Campus 全局参数拦截器。"""
    global _json_output  # noqa: PLW0603
    _json_output = json_output


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------


def _output_events(events: list[CampusEvent]) -> None:
    """根据全局 --json 标志决定输出格式。

    - JSON 模式：输出 minified JSON 数组（适用于管道 / Agent 调用）。
    - 默认模式：使用 Rich 渲染漂亮的终端表格。
    """
    if _json_output:
        payload = [e.model_dump(mode="json") for e in events]
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        _render_rich_table(events)


def _render_rich_table(events: list[CampusEvent]) -> None:
    """使用 Rich 将 CampusEvent 列表渲染为终端表格。"""
    if not events:
        console.print("[dim]没有数据。[/dim]")
        return

    table = Table(
        title="📋 Campus Events",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("ID", style="dim", max_width=30)
    table.add_column("类别", justify="center")
    table.add_column("标题", style="bold")
    table.add_column("来源", justify="center")
    table.add_column("时间", justify="right", style="green")

    for event in events:
        table.add_row(
            event.id,
            event.category.value,
            event.title,
            event.source.value,
            event.timestamp.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# 共享错误处理
# ---------------------------------------------------------------------------


def _handle_auth_required() -> None:
    """处理 AuthRequiredError。"""
    if _json_output:
        typer.echo(
            json.dumps(
                {"error": "auth_required", "message": "请先运行 campus auth login"}
            )
        )
    else:
        console.print(
            "[yellow]⚠[/yellow] 尚未登录。请先运行 "
            "[bold]campus auth login[/bold] 完成身份认证。"
        )
    raise typer.Exit(code=1)


def _handle_auth_failed(exc: Exception) -> None:
    """处理 AuthFailedError。"""
    if _json_output:
        typer.echo(json.dumps({"error": "auth_failed", "message": str(exc)}))
    else:
        console.print(f"[red]✗[/red] 认证失败: {exc}")
    raise typer.Exit(code=1)


def _handle_adapter_error(exc: Exception) -> None:
    """处理 AdapterError。"""
    if _json_output:
        typer.echo(json.dumps({"error": "adapter_error", "message": str(exc)}))
    else:
        console.print(f"[red]✗[/red] 请求失败: {exc}")
    raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# 命令定义
# ---------------------------------------------------------------------------


@app.command("test-adapter")
def test_adapter(
    adapter_name: Optional[str] = typer.Argument(
        default=None,
        help="要测试的适配器名称（当前仅支持 'mock'）。",
    ),
) -> None:
    """测试适配器连通性 — 初始化 Mock Adapter 并拉取示例数据。

    此命令用于验证 Adapter Protocol → CLI 输出的全链路是否正常工作。
    """
    name = adapter_name or "mock"

    if name != "mock":
        console.print(f"[red]错误：适配器 '{name}' 尚未实现。当前仅支持 'mock'。[/red]")
        raise typer.Exit(code=1)

    adapter = MockAdapter(config={"mode": "test"})

    # 运行异步方法
    auth_ok = asyncio.run(adapter.check_auth())
    if not auth_ok:
        console.print("[red]认证失败！[/red]")
        raise typer.Exit(code=1)

    events = asyncio.run(adapter.fetch())

    if not _json_output:
        console.print(
            f"[green]✓[/green] 适配器 [bold]{adapter.adapter_name()}[/bold] 认证通过"
        )
        console.print(f"[green]✓[/green] 获取到 {len(events)} 条事件\n")

    _output_events(events)


@app.command("version")
def version() -> None:
    """显示 CLI-Campus 版本信息。"""
    from cli_campus import __version__

    if _json_output:
        typer.echo(json.dumps({"version": __version__}))
    else:
        console.print(f"[bold]CLI-Campus[/bold] v{__version__}")


# ---------------------------------------------------------------------------
# Auth 子命令组
# ---------------------------------------------------------------------------

auth_app = typer.Typer(
    name="auth",
    help="身份认证管理 — 登录、状态检查、登出。",
    no_args_is_help=True,
)
app.add_typer(auth_app, name="auth")


@auth_app.command("login")
def auth_login() -> None:
    """交互式登录 — 安全存储凭证并验证 CAS 连通性。"""
    from cli_campus.adapters.seu_auth_wrapper import SEUAuthWrapper
    from cli_campus.core.auth import CampusAuthManager

    mgr = CampusAuthManager()

    # 检查是否已有凭证
    existing = mgr.get_credentials()
    if existing is not None:
        overwrite = typer.confirm(
            f"已存在凭证 (学号: {existing[0]})，是否覆盖？", default=False
        )
        if not overwrite:
            console.print("[dim]操作已取消。[/dim]")
            return

    username = typer.prompt("请输入学号 (一卡通号)")
    password = typer.prompt("请输入统一身份认证密码", hide_input=True)

    if not username or not password:
        console.print("[red]✗ 学号和密码不能为空。[/red]")
        raise typer.Exit(code=1)

    # Step 1: 回显确认输入
    if not _json_output:
        console.print(f"\n[dim]学号:[/dim] [bold]{username}[/bold]")
        console.print("[dim]密码:[/dim] [bold]********[/bold]")

    # Step 2: 保存凭证至系统密钥管理器
    mgr.save_credentials(username, password)
    if not _json_output:
        console.print("[green]✓[/green] 凭证已安全存储至系统密钥管理器")

    # Step 3: 在线验证 CAS 登录（网络请求交由 adapter 层处理）
    if not _json_output:
        console.print("[dim]正在连接统一身份认证系统验证凭证...[/dim]")

    wrapper = SEUAuthWrapper(auth_manager=mgr)
    try:
        verified = asyncio.run(wrapper.verify())
    except Exception:
        verified = False

    if _json_output:
        typer.echo(
            json.dumps(
                {
                    "status": "ok" if verified else "saved",
                    "username": username,
                    "verified": verified,
                }
            )
        )
    elif verified:
        console.print("[green]✓[/green] 认证验证通过 — 凭证有效，可正常使用所有命令。")
    else:
        console.print(
            "[yellow]⚠[/yellow] 凭证已保存，但在线验证未通过。\n"
            "  可能原因: 网络不可达 / 密码错误 / 服务端维护\n"
            "  您仍可尝试运行 [bold]campus card[/bold] 等命令。"
        )


@auth_app.command("status")
def auth_status() -> None:
    """检查本地凭证状态。"""
    from cli_campus.core.auth import CampusAuthManager

    mgr = CampusAuthManager()
    creds = mgr.get_credentials()

    if creds is None:
        if _json_output:
            typer.echo(json.dumps({"logged_in": False}))
        else:
            console.print(
                "[yellow]⚠[/yellow] 未登录。请运行 "
                "[bold]campus auth login[/bold] 进行登录。"
            )
        raise typer.Exit(code=1)

    if _json_output:
        typer.echo(json.dumps({"logged_in": True, "username": creds[0]}))
    else:
        console.print(f"[green]✓[/green] 已登录 (学号: [bold]{creds[0]}[/bold])")


@auth_app.command("logout")
def auth_logout() -> None:
    """清除本地已保存的凭证。"""
    from cli_campus.core.auth import CampusAuthManager

    mgr = CampusAuthManager()
    mgr.clear_credentials()

    if _json_output:
        typer.echo(json.dumps({"status": "ok"}))
    else:
        console.print("[green]✓[/green] 本地凭证已清除。")


# ---------------------------------------------------------------------------
# Card 命令
# ---------------------------------------------------------------------------


@app.command("card")
def card() -> None:
    """查询一卡通余额 — 自动使用已保存的凭证完成 CAS 认证。"""
    from cli_campus.adapters.card_adapter import CardAdapter

    adapter = CardAdapter()

    try:
        events = asyncio.run(adapter.fetch())
    except AuthRequiredError:
        _handle_auth_required()
    except AuthFailedError as exc:
        _handle_auth_failed(exc)
    except AdapterError as exc:
        _handle_adapter_error(exc)

    if not _json_output and events:
        card_data = events[0].content
        console.print(
            f"[green]✓[/green] 持卡人: [bold]{card_data.get('name', 'N/A')}[/bold]"
            f"  学号: {card_data.get('student_id', 'N/A')}"
        )
        balance = card_data.get("balance", 0)
        status = card_data.get("status", "N/A")
        console.print(
            f"[green]✓[/green] 余额: "
            f"[bold yellow]¥{balance:.2f}[/bold yellow]"
            f"  状态: {status}"
        )
    else:
        _output_events(events)


# ---------------------------------------------------------------------------
# Course 命令
# ---------------------------------------------------------------------------

_DAY_NAMES: dict[int, str] = {
    1: "周一",
    2: "周二",
    3: "周三",
    4: "周四",
    5: "周五",
    6: "周六",
    7: "周日",
}

# 课表时间段分组（方便渲染紧凑网格）
_PERIOD_SLOTS: list[tuple[str, range]] = [
    ("1-2", range(1, 3)),
    ("3-5", range(3, 6)),
    ("6-7", range(6, 8)),
    ("8-10", range(8, 11)),
    ("11-12", range(11, 13)),
]


def _render_timetable(
    events: list[CampusEvent], semester_code: str, *, week: int | None = None
) -> None:
    """将课程事件渲染为周历课表网格。

    行 = 节次时段，列 = 星期一 ~ 星期日，单元格 = 课程名 + 地点。
    """
    from cli_campus.adapters.course_adapter import _SEMESTER_NAMES

    # 构建 (day, period_start) → event 的索引
    grid: dict[tuple[int, int], CampusEvent] = {}
    for event in events:
        c = event.content
        day = c.get("day_of_week", 0)
        periods_str: str = c.get("periods", "")
        if "-" in periods_str:
            try:
                start = int(periods_str.split("-")[0])
            except ValueError:
                continue
        else:
            try:
                start = int(periods_str)
            except ValueError:
                continue
        grid[(day, start)] = event

    # 判断是否有周末数据
    has_weekend = any(d >= 6 for d, _ in grid)
    day_range = range(1, 8) if has_weekend else range(1, 6)
    day_count = len(day_range)

    # 学期标题
    parts = semester_code.split("-")
    if len(parts) == 3:
        sem_name = _SEMESTER_NAMES.get(parts[2], "")
        title = f"📚 {parts[0]}-{parts[1]} 学年 {sem_name}学期课程表"
    else:
        title = f"📚 {semester_code} 课程表"
    if week is not None:
        title += f" (第 {week} 周)"

    table = Table(
        title=title,
        show_header=True,
        header_style="bold cyan",
        show_lines=True,
        pad_edge=True,
        expand=True,
    )

    # 第一列：节次
    table.add_column("节次", justify="center", style="bold", width=6, no_wrap=True)
    # 星期列
    col_width = max(10, 60 // day_count)
    for d in day_range:
        table.add_column(
            _DAY_NAMES.get(d, "?"),
            justify="center",
            width=col_width,
            overflow="fold",
        )

    # 填充行
    for slot_label, slot_range in _PERIOD_SLOTS:
        # 检查这个时段是否有任何课
        has_any = any((d, s) in grid for d in day_range for s in slot_range)
        if not has_any:
            continue

        cells: list[str] = []
        for d in day_range:
            # 在这个时段中查找匹配的课程
            event = None
            for s in slot_range:
                if (d, s) in grid:
                    event = grid[(d, s)]
                    break
            if event:
                c = event.content
                name = c.get("name", "")
                location = c.get("location", "")
                weeks = c.get("weeks", "")
                # 紧凑格式：课程名\n地点\n周次
                parts_cell = [f"[bold]{name}[/bold]"]
                if location:
                    parts_cell.append(f"[dim]{location}[/dim]")
                if weeks:
                    parts_cell.append(f"[green]{weeks}[/green]")
                cells.append("\n".join(parts_cell))
            else:
                cells.append("")

        table.add_row(slot_label, *cells)

    console.print(table)


@app.command("course")
def course(
    semester: Optional[str] = typer.Option(
        None,
        "--semester",
        "-s",
        help="学年学期代码（如 2025-2026-3），默认自动推算当前学期。",
    ),
    week: Optional[int] = typer.Option(
        None,
        "--week",
        "-w",
        help="仅显示指定教学周的课程（如 --week 5 只显示第 5 周有课的课程）。",
    ),
) -> None:
    """查询本学期课程表 — 自动使用已保存的凭证完成 CAS 认证。"""
    from cli_campus.adapters.course_adapter import (
        CourseAdapter,
        compute_current_semester,
        parse_weeks,
    )

    config: dict[str, str] = {}
    if semester:
        config["semester"] = semester

    adapter = CourseAdapter(config=config if config else None)
    semester_code = semester or compute_current_semester()

    try:
        events = asyncio.run(adapter.fetch())
    except AuthRequiredError:
        _handle_auth_required()
    except AuthFailedError as exc:
        _handle_auth_failed(exc)
    except AdapterError as exc:
        _handle_adapter_error(exc)

    # --week 过滤
    if week is not None:
        events = [e for e in events if week in parse_weeks(e.content.get("weeks", ""))]

    if _json_output:
        _output_events(events)
        return

    if not events:
        if week is not None:
            console.print(f"[dim]第 {week} 周暂无课程。[/dim]")
        else:
            console.print("[dim]暂无课程数据。[/dim]")
        return

    _render_timetable(events, semester_code, week=week)


# ---------------------------------------------------------------------------
# Grade 命令
# ---------------------------------------------------------------------------


@app.command("grade")
def grade(
    semester: Optional[str] = typer.Option(
        None,
        "--semester",
        "-s",
        help="学年学期代码，留空查询全部学期成绩。",
    ),
) -> None:
    """查询成绩 — 支持按学期筛选或查看全部成绩。"""
    from cli_campus.adapters.grade_adapter import GradeAdapter

    config: dict[str, str] = {}
    if semester:
        config["semester"] = semester

    adapter = GradeAdapter(config=config if config else None)

    try:
        events = asyncio.run(adapter.fetch())
    except AuthRequiredError:
        _handle_auth_required()
    except AuthFailedError as exc:
        _handle_auth_failed(exc)
    except AdapterError as exc:
        _handle_adapter_error(exc)

    if _json_output:
        _output_events(events)
        return

    if not events:
        console.print("[dim]暂无成绩数据。[/dim]")
        return

    _render_grades(events, semester)


def _render_grades(events: list[CampusEvent], semester: str | None) -> None:
    """渲染成绩表格。"""
    title = "📊 成绩查询"
    if semester:
        from cli_campus.adapters.course_adapter import _SEMESTER_NAMES

        parts = semester.split("-")
        if len(parts) == 3:
            sem_name = _SEMESTER_NAMES.get(parts[2], "")
            title = f"📊 {parts[0]}-{parts[1]} 学年 {sem_name}学期成绩"

    table = Table(
        title=title,
        show_header=True,
        header_style="bold cyan",
        show_lines=False,
        pad_edge=True,
    )
    table.add_column("课程", style="bold", min_width=12)
    table.add_column("成绩", justify="center", min_width=6)
    table.add_column("学分", justify="center", min_width=4)
    table.add_column("绩点", justify="center", min_width=4)
    table.add_column("类型", justify="center", min_width=4)
    table.add_column("学期", justify="center", min_width=10)

    total_credit = 0.0
    weighted_gpa_sum = 0.0

    for event in events:
        c = event.content
        score = str(c.get("score", ""))
        credit = c.get("credit", 0.0)
        gpa = c.get("gpa", 0.0)
        passed = c.get("passed", True)

        score_style = (
            "red"
            if not passed
            else ("green" if score.isdigit() and int(score) >= 90 else "")
        )
        score_text = f"[{score_style}]{score}[/{score_style}]" if score_style else score

        table.add_row(
            c.get("course_name", ""),
            score_text,
            f"{credit:.1f}" if credit else "",
            f"{gpa:.1f}" if gpa else "",
            c.get("course_type", ""),
            c.get("semester", ""),
        )

        if credit > 0 and gpa > 0:
            total_credit += credit
            weighted_gpa_sum += credit * gpa

    console.print(table)

    if total_credit > 0:
        avg_gpa = weighted_gpa_sum / total_credit
        console.print(
            f"\n  总学分: [bold]{total_credit:.1f}[/bold]"
            f"  加权绩点: [bold yellow]{avg_gpa:.3f}[/bold yellow]"
        )


# ---------------------------------------------------------------------------
# Exam 命令
# ---------------------------------------------------------------------------


@app.command("exam")
def exam(
    semester: Optional[str] = typer.Option(
        None,
        "--semester",
        "-s",
        help="学年学期代码，默认自动推算当前学期。",
    ),
) -> None:
    """查询考试安排 — 显示考试时间与考场信息。"""
    from cli_campus.adapters.course_adapter import compute_current_semester
    from cli_campus.adapters.exam_adapter import ExamAdapter

    config: dict[str, str] = {}
    if semester:
        config["semester"] = semester

    adapter = ExamAdapter(config=config if config else None)
    semester_code = semester or compute_current_semester()

    try:
        events = asyncio.run(adapter.fetch())
    except AuthRequiredError:
        _handle_auth_required()
    except AuthFailedError as exc:
        _handle_auth_failed(exc)
    except AdapterError as exc:
        _handle_adapter_error(exc)

    if _json_output:
        _output_events(events)
        return

    if not events:
        console.print("[dim]暂无考试安排。[/dim]")
        return

    _render_exams(events, semester_code)


@app.command("bus")
def bus(
    route: Optional[str] = typer.Option(
        None,
        "--route",
        "-r",
        help="按线路名称筛选（模糊匹配，如 '循环' '兰台' '无线谷'）。",
    ),
    schedule_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="时刻表类型: workday / holiday / spring_festival。",
    ),
) -> None:
    """查询校车时刻表 — 显示九龙湖校区接驳车发车时间。"""
    from cli_campus.adapters.bus_adapter import BusAdapter

    adapter = BusAdapter()

    events = asyncio.run(
        adapter.fetch(route=route or "", schedule_type=schedule_type or "")
    )

    if _json_output:
        _output_events(events)
        return

    if not events:
        console.print("[dim]暂无匹配的校车时刻数据。[/dim]")
        return

    _render_bus(events, adapter)


def _render_bus(events: list[CampusEvent], adapter: "object") -> None:
    """渲染校车时刻表。"""
    from cli_campus.adapters.bus_adapter import BusAdapter

    assert isinstance(adapter, BusAdapter)

    # 按 (route_name, direction) 分组
    groups: dict[str, list[CampusEvent]] = {}
    for event in events:
        c = event.content
        key = f"{c['route_name']}|{c['departure_stop']}→{c['arrival_stop']}"
        groups.setdefault(key, []).append(event)

    for key, group_events in groups.items():
        route_name, direction = key.split("|", 1)

        # 同一组内按 schedule_type 分列
        by_type: dict[str, list[str]] = {}
        for ev in group_events:
            c = ev.content
            note = c.get("note", "")
            by_type.setdefault(note, []).append(c["departure_time"])

        table = Table(
            title=f"🚌 {route_name} ({direction})",
            show_header=True,
            header_style="bold cyan",
            pad_edge=True,
        )
        table.add_column("时段", justify="center", style="bold", width=6)
        for stype_label in by_type:
            table.add_column(stype_label, justify="left", min_width=20)

        # 按时段分组展示
        time_periods = [
            ("早间", "07", "10"),
            ("上午", "10", "12"),
            ("中午", "12", "14"),
            ("下午", "14", "17"),
            ("傍晚", "17", "19"),
            ("晚间", "19", "24"),
        ]

        for period_name, start_h, end_h in time_periods:
            row_cells: list[str] = []
            has_data = False
            for stype_label in by_type:
                times = [t for t in by_type[stype_label] if start_h <= t[:2] < end_h]
                if times:
                    has_data = True
                row_cells.append("  ".join(times) if times else "")
            if has_data:
                table.add_row(period_name, *row_cells)

        console.print(table)

    # 显示备注（仅当前展示的线路）
    displayed_routes = {k.split("|", 1)[0] for k in groups}
    notes: list[str] = []
    for rn in displayed_routes:
        notes.extend(adapter.get_notes(rn))
    if notes:
        console.print()
        for note in notes[:4]:
            console.print(f"  [dim]• {note}[/dim]")

    meta = adapter.get_meta()
    if meta.get("last_updated"):
        console.print(
            f"\n  [dim]数据更新: {meta['last_updated']}  来源: 东南大学总务处[/dim]"
        )


def _render_exams(events: list[CampusEvent], semester_code: str) -> None:
    """渲染考试安排表格。"""
    from cli_campus.adapters.course_adapter import _SEMESTER_NAMES

    parts = semester_code.split("-")
    if len(parts) == 3:
        sem_name = _SEMESTER_NAMES.get(parts[2], "")
        title = f"📝 {parts[0]}-{parts[1]} 学年 {sem_name}学期考试安排"
    else:
        title = f"📝 {semester_code} 考试安排"

    table = Table(
        title=title,
        show_header=True,
        header_style="bold cyan",
        show_lines=True,
        pad_edge=True,
    )
    table.add_column("课程", style="bold", min_width=10)
    table.add_column("考试时间", min_width=16)
    table.add_column("考场", justify="center", min_width=8)
    table.add_column("座位号", justify="center", min_width=4)
    table.add_column("学分", justify="center", min_width=4)

    for event in events:
        c = event.content
        table.add_row(
            c.get("course_name", ""),
            c.get("time_text", ""),
            c.get("location", ""),
            c.get("seat_number", ""),
            f"{c.get('credit', 0):.0f}" if c.get("credit") else "",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Fetch 命令 (YAML 声明式适配器)
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs" / "declarative"


@app.command("fetch")
def fetch(
    name: str = typer.Argument(help="YAML 声明式适配器名称（configs/declarative/ 下的文件名，不含 .yaml 后缀）。"),
) -> None:
    """运行 YAML 声明式适配器 — 根据 YAML 配置自动获取并解析数据。"""
    from cli_campus.core.yaml_engine import DeclarativeAdapter, load_yaml_config

    yaml_path = _DEFAULT_CONFIG_DIR / f"{name}.yaml"
    if not yaml_path.exists():
        yaml_path = _DEFAULT_CONFIG_DIR / f"{name}.yml"
    if not yaml_path.exists():
        if _json_output:
            typer.echo(json.dumps({"error": "not_found", "message": f"未找到配置: {name}"}))
        else:
            console.print(f"[red]✗[/red] 未找到声明式配置: [bold]{name}[/bold]")
            console.print(f"  配置目录: {_DEFAULT_CONFIG_DIR}")
        raise typer.Exit(code=1)

    try:
        yaml_config = load_yaml_config(yaml_path)
    except Exception as exc:
        if _json_output:
            typer.echo(json.dumps({"error": "config_error", "message": str(exc)}))
        else:
            console.print(f"[red]✗[/red] 配置加载失败: {exc}")
        raise typer.Exit(code=1)

    adapter = DeclarativeAdapter(yaml_config)

    try:
        events = asyncio.run(adapter.fetch())
    except AdapterError as exc:
        _handle_adapter_error(exc)

    if _json_output:
        _output_events(events)
        return

    if not events:
        console.print("[dim]暂无数据。[/dim]")
        return

    # 使用通用 news 表格渲染
    _render_declarative_events(events, yaml_config.display_name or yaml_config.name)


@app.command("fetch-list")
def fetch_list() -> None:
    """列出所有可用的 YAML 声明式适配器。"""
    from cli_campus.core.yaml_engine import discover_yaml_configs

    configs = discover_yaml_configs(_DEFAULT_CONFIG_DIR)

    if _json_output:
        payload = [{"name": c.name, "display_name": c.display_name, "category": c.category} for c in configs]
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return

    if not configs:
        console.print("[dim]暂无声明式适配器配置。[/dim]")
        console.print(f"  配置目录: {_DEFAULT_CONFIG_DIR}")
        return

    table = Table(title="📋 声明式适配器", show_header=True, header_style="bold cyan")
    table.add_column("名称", style="bold")
    table.add_column("显示名", min_width=12)
    table.add_column("类别", justify="center")

    for c in configs:
        table.add_row(c.name, c.display_name, c.category)

    console.print(table)


def _render_declarative_events(events: list[CampusEvent], title: str) -> None:
    """渲染声明式适配器返回的事件表格。"""
    table = Table(
        title=f"📰 {title}",
        show_header=True,
        header_style="bold cyan",
        show_lines=False,
        pad_edge=True,
    )
    table.add_column("标题", style="bold", min_width=20, max_width=50)
    table.add_column("日期", justify="center", min_width=10)
    table.add_column("链接", style="dim", max_width=30)

    for event in events:
        c = event.content
        table.add_row(
            c.get("title", event.title)[:50],
            c.get("date", ""),
            c.get("url", "")[:30],
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Schema 子命令组 (Phase 3: Agent-Native)
# ---------------------------------------------------------------------------

schema_app = typer.Typer(
    name="schema",
    help="Tool Schema 管理 — 导出 Function Calling JSON Schema。",
    no_args_is_help=True,
)
app.add_typer(schema_app, name="schema")


@schema_app.command("export")
def schema_export(
    pretty: bool = typer.Option(False, "--pretty", "-p", help="美化 JSON 输出。"),
    commands_filter: Optional[str] = typer.Option(
        None,
        "--commands",
        "-c",
        help="仅导出指定命令（逗号分隔，如 bus,course）。",
    ),
) -> None:
    """导出所有 CLI 命令的 Function Calling JSON Schema（OpenAI 标准）。"""
    from cli_campus.core.schema_export import export_function_calling_schema

    cmd_list = commands_filter.split(",") if commands_filter else None
    tools = export_function_calling_schema(app, commands=cmd_list)

    indent = 2 if pretty else None
    typer.echo(json.dumps(tools, ensure_ascii=False, indent=indent))


# ---------------------------------------------------------------------------
# SOP 子命令组 (Phase 3: 宏执行器)
# ---------------------------------------------------------------------------

_DEFAULT_SOP_DIR = Path(__file__).resolve().parent.parent / "sops"

sop_app = typer.Typer(
    name="sop",
    help="SOP 宏指令 — 预设任务流串联原子工具。",
    no_args_is_help=True,
)
app.add_typer(sop_app, name="sop")


@sop_app.command("list")
def sop_list() -> None:
    """列出所有可用的 SOP 宏指令。"""
    from cli_campus.core.sop_engine import discover_sops

    sops = discover_sops(_DEFAULT_SOP_DIR)

    if _json_output:
        payload = [
            {"name": s.name, "display_name": s.display_name, "description": s.description}
            for s in sops
        ]
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return

    if not sops:
        console.print("[dim]暂无可用的 SOP 宏指令。[/dim]")
        console.print(f"  SOP 目录: {_DEFAULT_SOP_DIR}")
        return

    table = Table(title="📋 SOP 宏指令", show_header=True, header_style="bold cyan")
    table.add_column("名称", style="bold")
    table.add_column("显示名", min_width=12)
    table.add_column("描述", min_width=20)

    for s in sops:
        table.add_row(s.name, s.display_name, s.description)

    console.print(table)


@sop_app.command("run")
def sop_run(
    name: str = typer.Argument(help="SOP 宏指令名称（sops/ 下的文件名，不含 .yaml 后缀）。"),
) -> None:
    """执行 SOP 宏指令 — 顺序运行预设步骤并渲染输出。"""
    from cli_campus.core.sop_engine import SOPRunner, load_sop

    sop_path = _DEFAULT_SOP_DIR / f"{name}.yaml"
    if not sop_path.exists():
        sop_path = _DEFAULT_SOP_DIR / f"{name}.yml"
    if not sop_path.exists():
        if _json_output:
            typer.echo(json.dumps({"error": "not_found", "message": f"未找到 SOP: {name}"}))
        else:
            console.print(f"[red]✗[/red] 未找到 SOP: [bold]{name}[/bold]")
            console.print(f"  SOP 目录: {_DEFAULT_SOP_DIR}")
        raise typer.Exit(code=1)

    try:
        sop = load_sop(sop_path)
    except Exception as exc:
        if _json_output:
            typer.echo(json.dumps({"error": "config_error", "message": str(exc)}))
        else:
            console.print(f"[red]✗[/red] SOP 配置加载失败: {exc}")
        raise typer.Exit(code=1)

    if not _json_output:
        console.print(f"[dim]正在执行 SOP: {sop.display_name or sop.name}...[/dim]")

    runner = SOPRunner(sop)

    if _json_output:
        result = runner.execute_json()
        typer.echo(json.dumps(result, ensure_ascii=False))
    else:
        output = runner.execute()
        # Markdown 输出直接打印
        console.print(output)


# ---------------------------------------------------------------------------
# 入口点
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
