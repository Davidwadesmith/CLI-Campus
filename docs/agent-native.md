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

### 4.3 作为 MCP Server（已实现 — Auto-Discovery Tool Factory）

CLI-Campus 实现了基于 **MCP Auto-Registrar** 的自动挂载引擎，在启动时自动反射 Typer 命令树，将所有业务命令动态注册为 MCP Tools。新增 CLI 命令后**无需手动修改** `mcp_server.py`。

#### 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│  mcp_server.py — Auto-Discovery Tool Factory                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  模块一: Context-Aware 基础感知工具                           │
│  ├── get_current_time()     → 日期/时间/星期几               │
│  └── get_semester_info()    → 学年学期代码/学期名称           │
│                                                             │
│  模块二: Auto-Registrar 引擎                                 │
│  ├── auto_register_tools()  → 遍历 Typer 命令树              │
│  ├── _make_tool_function()  → 动态生成带类型注解的 async 函数  │
│  └── _invoke_cli_json()     → 进程内 --json 模式调用 CLI     │
│                                                             │
│  模块三: 静态资源系统                                         │
│  ├── auto_register_resources() → 扫描 data/resources/*.md    │
│  ├── campus://resources/{name} → 逐篇读取参考文档             │
│  └── search_resource()         → 按关键词检索段落             │
│                                                             │
│  Resources & Prompts                                        │
│  ├── campus://info/bus-notes                                │
│  ├── campus://resources (索引) / campus://resources/{name}   │
│  ├── campus_assistant_system_prompt (查时间→算参数→调工具)    │
│  └── campus_morning_briefing                                │
└─────────────────────────────────────────────────────────────┘
```

#### 技术难点: 动态函数类型推导

FastMCP 依赖 `inspect.signature()` 和 `__annotations__` 推导 JSON Schema。Auto-Registrar 通过以下方式确保动态生成的函数拥有正确签名:

1. 从 Click 命令的 `params` 提取参数名、类型和默认值
2. 使用 `exec()` 构建具有正确 Python 类型注解的 `async def` 函数
3. 设置 `__annotations__`、`__doc__` 和 `__module__` 属性
4. 通过 `mcp.tool()()` 注册，FastMCP 即可生成完整的 JSON Schema

```python
# Auto-Registrar 核心流程 (伪代码)
for name, cmd in cli.commands.items():
    if name in _SKIP_COMMANDS:
        continue
    # 提取 Click 参数 → Python 类型
    params = cmd.params  # [route: str, schedule_type: str, ...]
    # 动态生成: async def campus_bus(route: str = None, ...) -> str
    func = _make_tool_function("campus_bus", ["bus"], params, docstring)
    # 注册到 FastMCP
    mcp.tool()(func)
```

#### 大模型标准调用 SOP

Agent 收到用户查询后，应遵循内置系统提示词 (`campus_assistant_system_prompt`) 中的标准流程:

```
Step 1: get_current_time()        → 获取时间锚点 (今天周几? 几月几号?)
Step 2: get_semester_info()       → 获取学期代码 (如需)
Step 3: campus_<tool>(params)     → 调用业务工具
Step 4: 将 JSON 结果整理为人类可读的回复
```

#### 已注册的 MCP 能力

| 类别 | 名称 | 说明 |
|------|------|------|
| **Tool** | `get_current_time` | 获取日期/时间/星期几 (处理相对时间请求前必须调用) |
| **Tool** | `get_semester_info` | 获取当前学年学期代码 |
| **Tool** | `campus_bus` | 查询校车时刻表 |
| **Tool** | `campus_course` | 查询课程表 |
| **Tool** | `campus_grade` | 查询成绩 |
| **Tool** | `campus_exam` | 查询考试安排 |
| **Tool** | `campus_card` | 查询一卡通余额 |
| **Tool** | `campus_venue_list` | 列出可预约场馆 |
| **Tool** | `campus_venue_slots` | 查询场馆时段 |
| **Tool** | `campus_venue_book` | 预约场馆 |
| **Tool** | `campus_venue_my` | 查看我的预约 |
| **Tool** | `campus_venue_cancel` | 取消预约 |
| **Tool** | `campus_fetch` | 运行 YAML 声明式适配器 |
| **Resource** | `campus://info/bus-notes` | 校车特殊规则说明（节假日、短驳车等上下文） |
| **Resource** | `campus://resources` | 校园参考资料索引（列出所有可用文档） |
| **Resource** | `campus://resources/{name}` | 具体参考资料（如学生手册） |
| **Tool** | `search_resource` | 在参考资料中按关键词搜索（避免全文填入上下文） |
| **Prompt** | `campus_assistant_system_prompt` | 系统提示词 (查时间→算参数→调工具 SOP) |
| **Prompt** | `campus_morning_briefing` | 早间速报预设提示词 |

> **注意**: 业务工具列表由 Auto-Registrar 自动生成，新增 Typer 命令后自动可用。

#### 启动 MCP Server

```bash
# 方式一：通过 Typer CLI 启动
campus mcp

# 方式二：独立入口（推荐，绕过 Typer，适合 MCP 客户端配置）
campus-mcp

# 方式三：Python 模块启动
python -m cli_campus.mcp_server
```

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

- **零维护成本**：Auto-Registrar 自动发现新命令，无需手动编写 `@mcp.tool()` 包裹函数
- **Context-Aware**：`get_current_time` + `get_semester_info` 提供时间锚点，解决大模型缺乏校历上下文的痛点
- **完整的类型注解**：动态函数拥有正确的 `__signature__` 和 `__annotations__`，FastMCP 自动生成 JSON Schema
- **独立入口点**：`campus-mcp` 绕过 Typer 直接启动，避免 CLI 框架干扰 stdio JSON-RPC 通信
- **Worker Thread 隔离**：动态工具通过 `asyncio.to_thread()` 在独立线程中执行 CliRunner，避免 FastMCP event loop 内嵌套 `asyncio.run()` 导致死锁
- **硬性体积上限**：`_MAX_RESPONSE_KB = 16` — 任何 MCP Tool 的单次返回不得超过 16 KB。超出部分自动截断并附加 `truncated` 标记，防止 LLM 上下文爆炸
- **Agent-Friendly 精简输出**：`_slim_for_agent()` 多层精简策略：
  - **CampusEvent**：剥离外层信封，仅保留 `content` 业务字典
  - **Venue Slots**：`_slim_venue_slots()` 按场馆分组去重（336 条 × 重复 venue 对象 → 按场馆聚合，136 KB → 22 KB）
  - **通用列表**：自动移除 `_STRIP_KEYS`（`raw_data`、`id`、`venue_id`、`slot_id`、`state` 等内部字段）
  - **兜底截断**：`_enforce_size_limit()` 确保最终输出不超过硬上限
- **静态资源系统**：`data/resources/` 中的参考文档（`.md`、`.pdf`）自动注册为 MCP Resources，配合 `search_resource` 工具按关键词精准检索段落，避免全文灌入上下文。扫描版 PDF 自动检测并引导 Agent 查找文字摘要版
- **智能 Flag 映射**：Auto-Registrar 从 Click 参数的 `opts` 属性提取真实 CLI flag（如 `--type`），而非朴素的 `--{param_name}` 转换，确保自定义 flag 命令正确调用
- **进程内 CLI 调用**：通过 `typer.testing.CliRunner` 在进程内以 `--json` 模式调用，复用 CLI 完整的错误处理逻辑
- **复用 OS Keyring 鉴权**：MCP 基于 stdio 本地运行，自动继承用户已保存的 CAS 凭证
- **友好的错误降级**：当凭证缺失时，Tool 返回结构化错误提示而非抛出异常

---

## 5. 安全考虑

- **凭证隔离**：Agent 调用时，CAS 凭证始终通过 OS Keyring 获取，不通过命令行参数传递
- **输出过滤**：`--json` 模式下不输出任何 Rich 渲染的颜色控制字符
- **速率限制**：Agent 高频调用时，Adapter 层内置请求节流，避免触发学校反爬

Tool Schema 自动生成器与 M2M 联调已在 **Phase 3** 实现。MCP Server 已于 Phase 3 落地，支持 `campus mcp` 和 `campus-mcp` 两种启动方式。
