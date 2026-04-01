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
```

## 项目结构

```
cli-campus/
├── cli_campus/              # 核心代码包
│   ├── main.py              # CLI 入口 (Typer)
│   ├── core/                # 核心协议层
│   │   ├── models.py        # Pydantic 数据模型
│   │   ├── interfaces.py    # Adapter 抽象基类
│   │   └── config.py        # 配置管理
│   └── adapters/            # 适配器层
│       ├── mock_adapter.py  # Mock 适配器
│       └── vendors/         # 供应商适配器
├── tests/                   # 单元测试
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
