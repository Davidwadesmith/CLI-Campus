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
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from cli_campus.adapters.mock_adapter import MockAdapter
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
# 入口点
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
