# Agent-Native 集成与 Function Calling Schema 设计

> 让 CLI-Campus 正式成为上层 AI Agent 的"武器库"。

---

## 1. Agent-Native 定位

CLI-Campus 在 AI 生态中的定位是**领域工具层**，而非通用 Agent：

```
┌─────────────────────────────────────────────────┐
│  用户 ("帮我查明天下午去丁家桥的校车")             │
└───────────────────────┬─────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────┐
│  通用 Agent (CLI-Anything / ChatGPT / DeepSeek)  │
│  自然语言理解 → 意图识别 → 工具选择               │
└───────────────────────┬─────────────────────────┘
                        ▼ Function Calling
┌─────────────────────────────────────────────────┐
│  CLI-Campus (领域工具层)                          │
│  campus bus --to dingjiaqiao --time tomorrow_pm  │
│  → 返回结构化 JSON                                │
└─────────────────────────────────────────────────┘
```

---

## 2. Tool Schema 自动生成

### 2.1 `campus schema export` 命令

利用 Python 反射机制遍历所有注册的 Typer 命令和 Pydantic 模型，自动生成标准的 Function Calling JSON Schema：

```python
# cli_campus/core/schema_export.py (Phase 3 实现)

from __future__ import annotations
import json
from typing import Any

import typer
from cli_campus.main import app


def export_function_calling_schema() -> list[dict[str, Any]]:
    """遍历所有 Typer 命令，生成 Function Calling Schema。"""
    tools: list[dict[str, Any]] = []

    for command_name, command_info in app.registered_commands:
        # 从 Typer 命令的参数注解中提取 schema
        params = extract_params(command_info)
        tools.append({
            "type": "function",
            "function": {
                "name": f"campus_{command_name.replace('-', '_')}",
                "description": command_info.help or "",
                "parameters": {
                    "type": "object",
                    "properties": params,
                },
            },
        })

    return tools
```

### 2.2 生成的 Schema 示例

```json
[
  {
    "type": "function",
    "function": {
      "name": "campus_bus",
      "description": "查询校车时刻表",
      "parameters": {
        "type": "object",
        "properties": {
          "from_stop": {
            "type": "string",
            "description": "出发校区",
            "enum": ["九龙湖", "四牌楼", "丁家桥"]
          },
          "to_stop": {
            "type": "string",
            "description": "到达校区",
            "enum": ["九龙湖", "四牌楼", "丁家桥"]
          },
          "time": {
            "type": "string",
            "description": "时间段过滤",
            "enum": ["morning", "afternoon", "evening"]
          },
          "next": {
            "type": "integer",
            "description": "显示最近 N 班车"
          }
        }
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "campus_course",
      "description": "查询课程表",
      "parameters": {
        "type": "object",
        "properties": {
          "today": {
            "type": "boolean",
            "description": "仅显示今日课程"
          },
          "week": {
            "type": "integer",
            "description": "指定教学周"
          },
          "weekday": {
            "type": "integer",
            "description": "指定星期几 (1-7)",
            "minimum": 1,
            "maximum": 7
          }
        }
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "campus_ddl",
      "description": "查询作业截止日期",
      "parameters": {
        "type": "object",
        "properties": {
          "due_within": {
            "type": "string",
            "description": "截止时间范围 (如 3d, 1w)"
          },
          "platform": {
            "type": "string",
            "description": "平台过滤",
            "enum": ["学习通", "雨课堂", "all"]
          }
        }
      }
    }
  }
]
```

### 2.3 使用方式

```bash
# 导出到文件
campus schema export > tools.json

# 导出并美化
campus schema export --pretty

# 仅导出特定命令的 Schema
campus schema export --commands bus,course
```

---

## 3. M2M 联调测试示例

以下是一个仅 ~50 行的 Python 脚本，用于测试 LLM 能否正确调用 CLI-Campus 工具：

```python
#!/usr/bin/env python3
"""M2M 联调测试 — 测试 LLM 能否正确调用 CLI-Campus 工具。"""

import json
import subprocess
from openai import OpenAI

# 1. 加载 CLI-Campus 的 Tool Schema
with open("tools.json") as f:
    tools = json.load(f)

# 2. 初始化 LLM 客户端（以 DeepSeek 为例）
client = OpenAI(
    api_key="your-api-key",
    base_url="https://api.deepseek.com",
)

# 3. 发送用户请求
response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "你是东南大学的校园助手。使用提供的工具回答问题。"},
        {"role": "user", "content": "查一下明天下午去丁家桥的校车"},
    ],
    tools=tools,
    tool_choice="auto",
)

# 4. 解析 LLM 的工具调用
message = response.choices[0].message
if message.tool_calls:
    for tc in message.tool_calls:
        func = tc.function
        print(f"LLM 调用: {func.name}({func.arguments})")

        # 5. 执行对应的 CLI 命令
        args = json.loads(func.arguments)
        cmd = ["campus", func.name.replace("campus_", ""), "--json"]
        for k, v in args.items():
            cmd.extend([f"--{k.replace('_', '-')}", str(v)])

        result = subprocess.run(cmd, capture_output=True, text=True)
        print(f"结果: {result.stdout}")
else:
    print(f"LLM 直接回答: {message.content}")
```

---

## 4. 与上层 Agent 的集成模式

### 4.1 作为 CLI 工具调用

最简单的集成方式 — Agent 通过 `subprocess` 调用 `campus` 命令：

```python
result = subprocess.run(
    ["campus", "bus", "--to", "丁家桥", "--json"],
    capture_output=True, text=True,
)
data = json.loads(result.stdout)
```

### 4.2 作为 Python 库调用

Agent 直接 import CLI-Campus 的 Adapter：

```python
from cli_campus.adapters.mock_adapter import MockAdapter
import asyncio

adapter = MockAdapter(config={})
events = asyncio.run(adapter.fetch())
for event in events:
    print(event.model_dump_json())
```

### 4.3 作为 MCP Server（已实现）

CLI-Campus 已实现标准的 Model Context Protocol Server，让任何支持 MCP 的 Agent（如 Claude Desktop）直接调用校园工具：

```python
# cli_campus/mcp_server.py
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("CLI-Campus")

@mcp.tool()
async def get_campus_bus(route: str = "", schedule_type: str = "") -> str:
    """查询校车时刻表。"""
    from cli_campus.adapters.bus_adapter import BusAdapter
    adapter = BusAdapter()
    events = await adapter.fetch(route=route, schedule_type=schedule_type)
    return _events_to_json(events)

@mcp.tool()
async def get_course_schedule(semester: str = "", week: int = None) -> str:
    """查询本学期课程表。"""
    from cli_campus.adapters.course_adapter import CourseAdapter
    adapter = CourseAdapter(config={"semester": semester} if semester else None)
    events = await adapter.fetch()
    return _events_to_json(events)
```

#### 启动 MCP Server

```bash
# 方式一：通过 Typer CLI 启动
campus mcp

# 方式二：独立入口（推荐，绕过 Typer，适合 MCP 客户端配置）
campus-mcp

# 方式三：Python 模块启动
python -m cli_campus.mcp_server
```

#### 已注册的 MCP 能力

| 类别 | 名称 | 说明 |
|------|------|------|
| **Tool** | `get_campus_bus` | 查询校车时刻表，支持线路和类型筛选 |
| **Tool** | `get_course_schedule` | 查询课程表，支持学期和教学周过滤 |
| **Resource** | `campus://info/bus-notes` | 校车特殊规则说明（节假日、短驳车等上下文） |
| **Prompt** | `campus_morning_briefing` | 早间速报预设提示词（引导 Agent 生成当日简报） |

#### MCP 客户端配置示例

**Cherry Studio** (STDIO 类型)：

| 字段 | 值 |
|------|------|
| Command | `uv` |
| Arguments | `--directory /path/to/cli-campus run campus-mcp` |

**Claude Desktop** (`claude_desktop_config.json`)：

```json
{
  "mcpServers": {
    "cli-campus": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/cli-campus",
        "run", "campus-mcp"
      ]
    }
  }
}
```

> **关键**：使用 `uv --directory` 确保 MCP 客户端能正确定位项目虚拟环境。
> `campus-mcp` 是独立入口，不经过 Typer，避免 CLI 框架干扰 stdio 通信。

#### 设计要点

- **独立入口点**：`campus-mcp` 绕过 Typer 直接启动，避免 CLI 框架干扰 stdio JSON-RPC 通信
- **直接复用 Adapter 层**：MCP Tool 绕过 Typer 解析逻辑，直接调用底层 Adapter，零冗余
- **复用 OS Keyring 鉴权**：MCP 基于 stdio 本地运行，自动继承用户已保存的 CAS 凭证
- **友好的错误降级**：当凭证缺失时，Tool 返回结构化错误提示而非抛出异常
- **完整的类型注解与 Docstring**：FastMCP 据此自动生成 JSON Schema，Agent 可自动发现能力

---

## 5. 安全考虑

- **凭证隔离**：Agent 调用时，CAS 凭证始终通过 OS Keyring 获取，不通过命令行参数传递
- **输出过滤**：`--json` 模式下不输出任何 Rich 渲染的颜色控制字符
- **速率限制**：Agent 高频调用时，Adapter 层内置请求节流，避免触发学校反爬

Tool Schema 自动生成器与 M2M 联调已在 **Phase 3** 实现。MCP Server 已于 Phase 3 落地，支持 `campus mcp` 和 `campus-mcp` 两种启动方式。
