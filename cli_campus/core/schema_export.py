"""Tool Schema 自动生成器 — 从 Typer 命令注册表导出 Function Calling JSON Schema。

利用 Typer/Click 反射机制遍历所有注册命令，自动生成符合
OpenAI / DeepSeek Function Calling 标准的 JSON Schema。
"""

from __future__ import annotations

from typing import Any

import click
import typer


def _click_type_to_json(click_type: click.ParamType) -> dict[str, Any]:
    """将 Click 参数类型映射为 JSON Schema 类型。"""
    type_name = click_type.name
    if type_name == "integer":
        return {"type": "integer"}
    elif type_name == "float":
        return {"type": "number"}
    elif type_name == "boolean":
        return {"type": "boolean"}
    else:
        return {"type": "string"}


def _extract_command_schema(
    name: str, cmd: click.Command, *, prefix: str = "campus"
) -> dict[str, Any]:
    """从单个 Click 命令中提取 Function Calling Schema。"""
    func_name = f"{prefix}_{name}".replace("-", "_")
    description = (cmd.help or "").split("\n")[0].strip()

    properties: dict[str, Any] = {}
    for param in cmd.params:
        # 跳过全局 --json 参数和 --help
        if param.name in ("json_output", "help"):
            continue

        prop: dict[str, Any] = _click_type_to_json(param.type)
        if param.help:
            prop["description"] = param.help

        # 参数名 normalize: schedule_type -> schedule_type
        param_name = param.name or ""
        properties[param_name] = prop

    schema: dict[str, Any] = {
        "type": "function",
        "function": {
            "name": func_name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
            },
        },
    }
    return schema


def export_function_calling_schema(
    app: typer.Typer,
    *,
    commands: list[str] | None = None,
) -> list[dict[str, Any]]:
    """遍历 Typer 应用的所有命令，生成 Function Calling Schema 列表。

    Args:
        app: Typer 应用实例。
        commands: 可选的命令名过滤列表，为 None 时导出全部。

    Returns:
        符合 OpenAI Function Calling 标准的 tool schema 列表。
    """
    cli = typer.main.get_command(app)
    tools: list[dict[str, Any]] = []

    for name, cmd in cli.commands.items():
        # 跳过元命令 (test-adapter, version, fetch-list, schema, sop)
        if name in ("test-adapter", "version", "fetch-list", "schema", "sop"):
            continue

        if commands and name not in commands:
            continue

        if isinstance(cmd, click.Group):
            # 子命令组 (如 auth) — 为每个子命令生成独立 schema
            for sub_name, sub_cmd in cmd.commands.items():
                if commands and f"{name}-{sub_name}" not in commands:
                    continue
                schema = _extract_command_schema(
                    f"{name}_{sub_name}", sub_cmd, prefix="campus"
                )
                tools.append(schema)
        else:
            schema = _extract_command_schema(name, cmd)
            tools.append(schema)

    return tools
