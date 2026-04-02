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
```

## 项目结构

```
cli-campus/
├── cli_campus/              # 核心代码包
│   ├── main.py              # CLI 入口 (Typer)
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
│   │   └── bus_adapter.py   # 校车时刻表静态适配器
│   └── data/
│       └── bus_schedule.json# 校车时刻表数据 (总务处官方)
├── configs/declarative/     # YAML 声明式适配器配置
├── sops/                    # SOP 宏指令配置
├── scripts/                 # 工具脚本 (M2M 联调测试等)
├── tests/                   # 单元测试 (211 tests)
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
| [Agent 集成](docs/agent-native.md) | Function Calling Schema 与 M2M 联调 |

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

## License

MIT
