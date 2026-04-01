# CLI-Campus 工程与开发准则

> 核心原则：约定大于配置 (Convention over Configuration)。把精力花在业务逻辑上，把格式化和依赖管理交给工具。

---

## 1. 环境与包管理

### 运行环境

- **Python 3.10+**（强制要求，以完美支持 `Typer` 和 `Pydantic` 的现代类型提示）

### 包管理与构建工具

- **`uv`**（Astral 出品的 Rust 编写的极速 Python 包管理器）
  - 解析和安装速度是 `pip` / `poetry` 的数十倍
  - 原生支持虚拟环境管理和依赖锁定
  - 让新同学在 3 秒内完成项目初始化

### 依赖声明

- 统一使用 `pyproject.toml`，摒弃传统的 `requirements.txt`

### 最小实践命令

```bash
# 克隆项目
git clone https://github.com/iplusplus-org/cli-campus.git
cd cli-campus

# 初始化开发环境
uv venv                    # 创建虚拟环境
uv sync                    # 一键安装所有依赖（包含 dev 依赖）
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate   # Windows

# 验证安装
campus --help
campus version
campus test-adapter
```

---

## 2. 代码规范与静态检查

开源项目的代码**必须**看起来像一个人写的。

### Ruff — All-in-One Linter & Formatter

彻底替换 `Black`、`Flake8`、`isort`：

```bash
# 检查代码规范
ruff check .

# 自动修复可修复的问题
ruff check --fix .

# 格式化代码
ruff format .

# 检查是否已格式化（CI 用）
ruff format --check .
```

**`pyproject.toml` 配置：**

```toml
[tool.ruff]
line-length = 88
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I"]  # 基础错误 + 逻辑错误 + import 排序
```

### Mypy — 静态类型检查

由于大量依赖 `Pydantic`，所有核心函数**必须**包含完整的 Type Hints：

```bash
mypy cli_campus/
```

### 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 变量 / 函数 / Adapter 实例 | `snake_case` | `fetch_course_data` |
| 类名 / Pydantic 模型 | `PascalCase` | `CourseInfo`, `ZhengfangAdapter` |
| 常量 | `UPPER_SNAKE_CASE` | `DEFAULT_TIMEOUT = 5` |
| 模块文件名 | `snake_case` | `seu_cas.py`, `mock_adapter.py` |
| 测试文件名 | `test_` 前缀 | `test_models.py`, `test_cli.py` |

---

## 3. Git 工作流与提交规范

采用适合开源小团队的**极简特性分支工作流 (Feature Branch Workflow)**。

### 分支策略

```
main ────────────────────────────────────── (始终可运行)
  │
  ├── feat/add-cas-login ──── PR ──── merge
  │
  ├── feat/add-bus-adapter ── PR ──── merge
  │
  └── fix/cas-token-expire ── PR ──── merge
```

- `main`：永远保持可运行、已测试的主分支
- `feat/*`：新功能开发分支（如 `feat/add-yuketang-adapter`）
- `fix/*`：Bug 修复分支
- 开发完成后通过 Pull Request (PR) 合并入 `main`

### 提交信息规范 (Conventional Commits)

**强制要求语义化提交**，方便日后自动生成 Changelog：

```
feat: 增加学习通 DDL 解析器
fix: 修复正方教务处登录验证码加载失败的问题
docs: 更新 README 中的安装指南
refactor: 重构 Adapter 基类的接口定义
test: 增加 MockAdapter 的单元测试
ci: 更新 GitHub Actions Python 版本矩阵
chore: 升级 typer 依赖至 0.12.0
```

### PR 要求

1. 标题遵循 Conventional Commits 格式
2. 描述中说明「为什么」而不仅仅是「做了什么」
3. CI 必须全绿（Ruff + pytest）
4. 至少一位 Maintainer Review

---

## 4. 目录结构

```
cli-campus/
├── cli_campus/                 # 核心代码包
│   ├── __init__.py             # 包初始化 + 版本号
│   ├── main.py                 # Typer CLI 入口（严禁包含业务逻辑）
│   ├── core/                   # 核心协议层（不允许包含具体学校逻辑）
│   │   ├── __init__.py
│   │   ├── models.py           # Pydantic Standard Types
│   │   ├── interfaces.py       # BaseCampusAdapter 抽象基类
│   │   └── config.py           # 配置加载与管理
│   └── adapters/               # 适配器层（脏活累活都在这）
│       ├── __init__.py
│       ├── mock_adapter.py     # Mock 适配器（调试 / CI 用）
│       ├── seu_cas.py          # 东大统一身份认证模块
│       └── vendors/            # 按供应商分类的第三方系统
│           ├── __init__.py
│           ├── chaoxing.py     # 超星学习通
│           └── zhengfang.py    # 正方教务处
├── tests/                      # pytest 测试
│   ├── __init__.py
│   ├── test_models.py          # 模型测试
│   ├── test_adapters.py        # 适配器测试
│   ├── test_cli.py             # CLI 命令测试
│   └── test_config.py          # 配置测试
├── docs/                       # 项目文档
├── .github/
│   └── workflows/
│       └── ci.yml              # CI 流水线
├── pyproject.toml              # 项目配置（依赖、Ruff、Mypy）
└── README.md
```

### 目录边界强制规则

| 目录 | 允许 | 禁止 |
|------|------|------|
| `core/` | Pydantic 模型、抽象基类、配置 | 任何 HTTP 请求、HTML 解析 |
| `adapters/` | 网络请求、数据清洗、Session 管理 | Rich 渲染逻辑、CLI 参数解析 |
| `main.py` | Typer 命令定义、调用 Adapter、输出格式化 | 直接发起网络请求 |
| `tests/` | pytest 测试用例 | 生产代码 |

---

## 5. 测试规范

### 工具

- **pytest** 作为测试框架
- **pytest-asyncio** 支持异步测试

### 运行测试

```bash
# 运行所有测试
pytest -v

# 运行特定测试文件
pytest tests/test_models.py -v

# 运行特定测试类或方法
pytest tests/test_cli.py::TestCLIBasics::test_help -v

# 带覆盖率（需安装 pytest-cov）
pytest --cov=cli_campus -v
```

### 测试文件命名

- 测试文件：`test_<module>.py`
- 测试类：`Test<Feature>`
- 测试方法：`test_<scenario>`

### 编写原则

1. 每个 Adapter 必须有对应的测试
2. Mock 网络请求，不在 CI 中发起真实 HTTP 调用
3. 使用 `typer.testing.CliRunner` 测试 CLI 命令
4. 异步方法使用 `asyncio.run()` 或 `pytest-asyncio`

---

## 6. CI/CD 流水线

### GitHub Actions 配置

文件位于 `.github/workflows/ci.yml`，触发条件：

- 任何推送到 `main` 分支
- 任何 Pull Request 到 `main` 分支

### 流水线步骤

1. **Checkout** — 检出代码
2. **Install uv** — 安装包管理器
3. **Setup Python** — 设置 Python 3.10/3.11/3.12 矩阵
4. **Install deps** — `uv sync`
5. **Ruff check** — 代码规范检查
6. **Ruff format** — 格式化检查
7. **pytest** — 运行单元测试

### 本地模拟 CI

```bash
# 在提交 PR 之前，在本地运行完整检查：
ruff check .
ruff format --check .
pytest -v
```
