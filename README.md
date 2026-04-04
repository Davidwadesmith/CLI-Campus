# CLI-Campus 🎓

> 让校园生活重回命令行，构建 AI 时代的数字校园基础设施。

**CLI-Campus** 是校园数字基建的"系统调用"与 Agent-Native 底层武器库。它通过鲁棒的适配器网络抹平教务处、财务处、学习通等平台的差异，向上提供干净、极速、结构化（JSON）的标准 API。

*I++ Open Source Culture Club 孵化项目*

---

## 快速开始

```bash
# 克隆项目
git clone https://github.com/iplusplus-org/cli-campus.git
cd cli-campus

# 初始化开发环境（需要 Python 3.10+）
uv venv
uv sync
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# 验证安装
campus --help
campus version
campus test-adapter
campus --json test-adapter

# 身份认证
campus auth login          # 交互式登录（凭证安全存储至系统密钥管理器）
campus auth status         # 检查登录状态

# 查询课程表
campus course              # Rich 表格输出
campus --json course       # JSON 输出（供 Agent 使用）
campus course -s 2024-2025-1  # 指定学期

# 声明式适配器 (YAML 驱动，无需写 Python)
campus fetch-list          # 列出可用配置
campus fetch seu_jwc_news  # 运行教务处通知抓取

# Tool Schema 导出 (Agent-Native)
campus schema export --pretty        # 导出 Function Calling JSON Schema
campus schema export --commands bus   # 仅导出指定命令

# SOP 宏指令 (原子工具编排)
campus sop list                      # 列出可用 SOP
campus sop run morning_briefing      # 执行早间速报 (课表 + 校车)

# 场馆预约 (羽毛球场 / 网球场 / 篮球馆 / 乒乓球台 ...)
campus venue list                    # 列出羽毛球场馆
campus venue list -t 网球场          # 列出网球场
campus venue list -c 九龙湖          # 按校区筛选
campus venue slots                   # 查看明天羽毛球场时段
campus venue slots -d 2025-07-15     # 指定日期
campus venue slots -v JLH01          # 指定场馆
campus venue book -v JLH01 -s 14:00 -e 15:00  # 预约
campus venue my                      # 查看我的预约
campus venue cancel <booking_id>     # 取消预约

# 场馆预约 AI 助手 (交互式对话)
python scripts/venue_assistant.py    # 启动 AI 助手
```

## MCP Server 使用指南

CLI-Campus 内置了标准的 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) Server，可供 Claude Desktop 或任何支持 MCP 的 AI Agent 直接调用校园数据能力。

### 前置条件

1. **完成安装**：按“快速开始”节完成 `uv sync` 安装依赖。
2. **完成登录**（可选）：如需查课表等需要认证的功能，先在终端运行 `campus auth login` 完成 CAS 登录。校车时刻表为静态数据，无需登录即可使用。

### 启动方式

CLI-Campus 提供两种方式启动 MCP Server：

```bash
# 方式一：通过 Typer CLI 命令启动
campus mcp

# 方式二：直接启动（推荐用于 MCP 客户端配置）
campus-mcp
```

两种方式均以 stdio 模式运行，持续监听 Agent 的 JSON-RPC 请求。

### 配置 Cherry Studio

在 Cherry Studio 中添加 MCP 服务器，类型选择 **STDIO**，配置如下：

| 字段 | 值 |
|------|------|
| **Command** | `uv` |
| **Arguments** | `--directory /path/to/cli-campus run campus-mcp` |

> 将 `/path/to/cli-campus` 替换为项目实际路径，Windows 示例：
> `--directory E:\Projects\CLI-Campus run campus-mcp`

### 配置 Claude Desktop

在 `claude_desktop_config.json` 中添加：

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

> 配置文件位置：
> - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
> - Windows: `%APPDATA%\Claude\claude_desktop_config.json`

### 可用能力

MCP Server 采用 **自动挂载引擎 (Auto-Discovery Tool Factory)**，会在启动时自动反射 Typer 命令树，将所有业务命令动态注册为 MCP Tools。新增 CLI 命令后无需手动修改 `mcp_server.py`。

> **Agent-Friendly 输出**: MCP 工具返回经过精简的 JSON — 自动剥离内部信封字段、按场馆分组去重嵌套结构，并施加 **16 KB 硬上限**（超出自动截断），大幅降低 LLM token 消耗。

#### Context-Aware 基础工具

| 类别 | 名称 | 说明 |
|------|------|------|
| **Tool** | `get_current_time` | 获取当前日期、时间、星期几 — 处理相对时间请求时必须首先调用 |
| **Tool** | `get_semester_info` | 获取当前学年学期代码和学期名称 — 调用课表/成绩等工具前的基准信息 |

#### 自动注册的业务工具

以下工具由 Auto-Registrar 从 CLI 命令树自动生成，参数与 `campus --json <command>` 完全一致：

| 类别 | 名称 | 说明 |
|------|------|------|
| **Tool** | `campus_bus` | 查询校车时刻表，支持按线路、时刻表类型筛选 |
| **Tool** | `campus_course` | 查询课程表，支持学期和教学周过滤 |
| **Tool** | `campus_grade` | 查询成绩，支持按学期筛选 |
| **Tool** | `campus_exam` | 查询考试安排 |
| **Tool** | `campus_card` | 查询一卡通余额 |
| **Tool** | `campus_venue_list` | 列出可预约场馆 |
| **Tool** | `campus_venue_slots` | 查询场馆时段可用情况 |
| **Tool** | `campus_venue_book` | 预约场馆 |
| **Tool** | `campus_venue_my` | 查看我的预约 |
| **Tool** | `campus_venue_cancel` | 取消预约 |

#### Resources & Prompts

| 类别 | 名称 | 说明 |
|------|------|------|
| **Resource** | `campus://info/bus-notes` | 校车特殊规则说明（节假日、短駁车等上下文） |
| **Resource** | `campus://resources` | 校园参考资料索引（列出所有可用文档） |
| **Resource** | `campus://resources/{name}` | 具体参考资料（如学生手册） |
| **Tool** | `search_resource` | 在参考资料中按关键词搜索段落，避免全文灌入上下文 |
| **Prompt** | `campus_assistant_system_prompt` | 系统提示词，建立"查时间→算参数→调业务工具"的标准 SOP |
| **Prompt** | `campus_morning_briefing` | 早间速报预设提示词，引导 Agent 组合课表+校车生成当日简报 |

### 示例对话

配置完成后，在 Claude Desktop 中可以直接说：

- "给我查一下今天的课表"（Agent 会自动先调用 `get_current_time` → `get_semester_info` → `campus_course`）
- "最近一班去四牌楼的校车几点发车？"
- "帮我生成今天的校园早报"（使用 `campus_morning_briefing` prompt）
- "查一下我的成绩"（`campus_grade`）
- "明天有没有可以预约的羽毛球场？"（`get_current_time` → `campus_venue_slots`）
- "学校奖学金有哪些？"（`search_resource` 在学生手册中检索"奖学金"相关段落）

## 项目结构

```
cli-campus/
├── cli_campus/              # 核心代码包
│   ├── main.py              # CLI 入口 (Typer)
│   ├── mcp_server.py        # MCP Server 入口 (FastMCP/stdio)
│   ├── core/                # 核心协议层
│   │   ├── models.py        # Pydantic 数据模型
│   │   ├── interfaces.py    # Adapter 抽象基类
│   │   ├── config.py        # 配置管理
│   │   ├── auth.py          # 凭证管理 (keyring)
│   │   ├── exceptions.py    # 统一异常层级
│   │   ├── yaml_engine.py   # YAML 声明式解析引擎
│   │   ├── schema_export.py # Tool Schema 自动生成器
│   │   └── sop_engine.py    # SOP 宏执行器
│   ├── adapters/            # 适配器层
│   │   ├── mock_adapter.py  # Mock 适配器
│   │   ├── seu_auth_wrapper.py  # SEU-Auth SDK 封装
│   │   ├── ehall_base.py    # ehall 三阶段认证基座
│   │   ├── card_adapter.py  # 一卡通适配器
│   │   ├── course_adapter.py# 课程表适配器 (ehall/wdkb)
│   │   ├── grade_adapter.py # 成绩查询适配器 (ehall/cjcx)
│   │   ├── exam_adapter.py  # 考试安排适配器 (ehall/wdksap)
│   │   ├── bus_adapter.py   # 校车时刻表静态适配器
│   │   └── venue_adapter.py # 场馆预约适配器 (OIDC + GraphQL)
│   └── data/
│       ├── bus_schedule.json# 校车时刻表数据 (总务处官方)
│       └── resources/       # 静态参考资料 (自动注册为 MCP Resource，支持 .md / .pdf)
│           └── student_handbook.md  # 学生手册摘要版
├── configs/declarative/     # YAML 声明式适配器配置
├── sops/                    # SOP 宏指令配置
├── scripts/                 # 工具脚本 (M2M 联调测试等)
├── tests/                   # 单元测试 (308 tests)
├── docs/                    # 项目文档
└── pyproject.toml           # 项目配置
```

## 文档

| 文档 | 说明 |
|------|------|
| [架构白皮书](docs/architecture.md) | 项目愿景、架构演进路线与核心数据流 |
| [Adapter 协议](docs/adapter-protocol.md) | 适配器开发指南与完整开发示例 |
| [开发准则](docs/contributing.md) | 环境搭建、代码规范、Git 工作流 |
| [路线图](docs/roadmap.md) | Phase 0~4 详细执行时间表 |
| [YAML 引擎](docs/yaml-engine.md) | 声明式解析引擎设计文档 |
| [SOP 设计](docs/sop-design.md) | 宏指令与原子化组合设计 |
| [Agent 集成](docs/agent-native.md) | Function Calling Schema、MCP Server 与 M2M 联调 |

## 开发

```bash
# 代码检查
ruff check .
ruff format --check .

# 运行测试
pytest -v

# 格式化代码
ruff format .
```

## 致谢 · 开源依赖

CLI-Campus 站在以下优秀开源项目的肩膀上：

| 项目 | 用途 |
|------|------|
| [Typer](https://github.com/fastapi/typer) | CLI 框架，提供类型安全的命令行参数解析 |
| [Pydantic](https://github.com/pydantic/pydantic) | 数据验证与序列化（v2） |
| [Rich](https://github.com/Textualize/rich) | 终端富文本渲染（表格、颜色、进度条） |
| [httpx](https://github.com/encode/httpx) | 异步 HTTP 客户端 |
| [keyring](https://github.com/jaraco/keyring) | 跨平台系统密钥管理器集成 |
| [SEU-Auth](https://github.com/Golevka2001/SEU-Auth) | 东南大学 CAS 统一身份认证 SDK |
| [PyYAML](https://github.com/yaml/pyyaml) | YAML 解析 |
| [jsonpath-ng](https://github.com/h2non/jsonpath-ng) | JSONPath 表达式引擎 |
| [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) | HTML 解析与数据提取 |
| [Jinja2](https://github.com/pallets/jinja) | 模板引擎（SOP 输出渲染） |
| [OpenAI Python](https://github.com/openai/openai-python) | LLM Function Calling 集成 |
| [MCP](https://github.com/modelcontextprotocol/python-sdk) | Model Context Protocol Server SDK |
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | PDF 文本提取（静态资源加载） |

开发工具链：[Ruff](https://github.com/astral-sh/ruff)（Lint + Format）· [pytest](https://github.com/pytest-dev/pytest) · [Mypy](https://github.com/python/mypy) · [uv](https://github.com/astral-sh/uv)（包管理）

## License

MIT
