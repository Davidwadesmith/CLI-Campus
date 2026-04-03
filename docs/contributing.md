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

### Pre-commit Hook（推荐）

项目已配置 `.pre-commit-config.yaml`，在每次 `git commit` 前自动运行 Ruff lint + format：

```bash
pip install pre-commit
pre-commit install
```

安装后每次提交会自动格式化并检查代码，避免 CI 因格式问题失败。

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
│   ├── mcp_server.py           # MCP Server 入口 (FastMCP/stdio)
│   ├── core/                   # 核心协议层（不允许包含具体学校逻辑）
│   │   ├── __init__.py
│   │   ├── models.py           # Pydantic Standard Types
│   │   ├── interfaces.py       # BaseCampusAdapter 抽象基类
│   │   ├── config.py           # 配置加载与管理
│   │   ├── auth.py             # 凭证管理 (keyring)
│   │   ├── exceptions.py       # 统一异常层级
│   │   ├── yaml_engine.py      # YAML 声明式解析引擎
│   │   ├── schema_export.py    # Tool Schema 自动生成器
│   │   └── sop_engine.py       # SOP 宏执行器
│   ├── adapters/               # 适配器层（脏活累活都在这）
│   │   ├── __init__.py
│   │   ├── mock_adapter.py     # Mock 适配器（调试 / CI 用）
│   │   ├── seu_auth_wrapper.py # SEU-Auth SDK 封装层
│   │   ├── ehall_base.py       # ehall 教务应用基座（三阶段 CAS 认证）
│   │   ├── card_adapter.py     # 一卡通适配器
│   │   ├── course_adapter.py   # 课程表适配器 (ehall/wdkb)
│   │   ├── grade_adapter.py    # 成绩查询适配器 (ehall/cjcx)
│   │   ├── exam_adapter.py     # 考试安排适配器 (ehall/studentWdksapApp)
│   │   └── bus_adapter.py      # 校车时刻表静态适配器 (总务处/JSON)
│   └── data/
│       └── bus_schedule.json   # 校车时刻表数据 (总务处官方)
├── configs/declarative/        # YAML 声明式适配器配置
├── sops/                       # SOP 宏指令配置 (Jinja2 模板)
├── scripts/                    # 工具脚本 (M2M 联调测试等)
├── tests/                      # pytest 测试 (236 tests)
│   ├── test_models.py          # 模型测试
│   ├── test_adapters.py        # 适配器测试
│   ├── test_cli.py             # CLI 命令测试
│   ├── test_config.py          # 配置测试
│   ├── test_card_adapter.py    # 一卡通适配器测试
│   ├── test_course_adapter.py  # 课程表适配器测试
│   ├── test_grade_adapter.py   # 成绩查询适配器测试
│   ├── test_exam_adapter.py    # 考试安排适配器测试
│   ├── test_bus_adapter.py     # 校车适配器测试 (30 tests)
│   ├── test_yaml_engine.py     # YAML 引擎测试 (24 tests)
│   ├── test_schema_export.py   # Schema 导出测试 (12 tests)
│   ├── test_sop_engine.py      # SOP 执行器测试 (15 tests)
│   └── test_auth*.py           # 认证相关测试
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
| `core/` | Pydantic 模型、抽象基类、配置、引擎 | 具体学校逻辑、Rich 渲染 |
| `adapters/` | 网络请求、数据清洗、Session 管理 | Rich 渲染逻辑、CLI 参数解析 |
| `main.py` | Typer 命令定义、调用 Adapter、输出格式化 | 直接发起网络请求 |
| `mcp_server.py` | MCP Tools/Resources/Prompts、调用 Adapter | Typer 解析逻辑、Rich 渲染 |
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

---

## 7. 凭证安全与 .gitignore 规范

### 绝对红线

**严禁将任何个人凭证、会话文件、Token 提交到 Git 仓库。** 违反此规则的 PR 一律拒绝。

### 已纳入 .gitignore 的敏感文件

| 文件 / 模式 | 来源 | 说明 |
|-------------|------|------|
| `auth_session.json` | SEU-Auth SDK | SDK 本地持久化的 TGT、fingerprint 等会话数据 |
| `*.tgt` | CAS 会话 | 认证票据缓存文件 |
| `*.session` | 通用 | 各类本地会话文件 |
| `.env` / `.env.*` | 环境变量 | 可能包含密码、API Key 等敏感配置 |

### 凭证存储机制

- 用户密码通过 `keyring` 安全存储在**操作系统原生密钥管理器**中（macOS Keychain / Windows Credential Manager / Linux Secret Service），不以明文或任何形式落盘到项目目录。
- SEU-Auth SDK 会在项目根目录生成 `auth_session.json` 用于 TGT 缓存复用，该文件已被 `.gitignore` 排除。

### 开发者自查清单

在每次 `git add` 之前，请确认：

```bash
# 检查是否有敏感文件被暂存
git diff --cached --name-only | grep -iE '(session|auth|\.env|\.tgt)'
```

---

## 8. 校园网络环境与 ehall 访问

### 网络要求

`campus course` 等依赖 `ehall.seu.edu.cn` 的命令**必须在校园网络环境下运行**。校外网络会被 DNS/网关拦截并重定向至 `vpn.seu.edu.cn`（webVPN 门户），导致 API 返回 HTML 而非 JSON。

### 可用的网络接入方式

| 方式 | 说明 |
|------|------|
| 校园 WiFi（`seu-wlan`） | 在校内直接连接即可 |
| Sangfor/EasyConnect VPN | 校外通过学校 VPN 客户端接入校园网 |
| 有线网络 | 校内宿舍 / 实验室有线接入 |

### ehall 适配器的认证流程

ehall 平台的 API 需要**三步 Session 初始化**。此流程已封装在 `EhallBaseAdapter`（`ehall_base.py`）基类中，所有 ehall 教务适配器（课表、成绩、考试）均继承该基类：

1. **CAS → ehall 平台认证**：`manager.login(service="http://ehall.seu.edu.cn/login?service=...")` — 注意 service URL 必须使用 `http://`（非 `https://`），后者不在 CAS 白名单中。获取平台级 `JSESSIONID` / `asessionid`。
2. **appShow 应用授权**：GET `https://ehall.seu.edu.cn/appShow?appId=<APP_ID>`，ehall 返回 302 重定向到带 `gid_` 授权令牌的 `http://` URL。**必须截取第一步重定向的 `http://` URL**，不能使用后续自动升级的 `https://`（同样不在 CAS 白名单中）。**每个 ehall 应用有独立的 appId，不同应用之间 Session 不互通（跨应用访问返回 403）。**
3. **CAS → 应用认证**：以 Step 2 获取的 URL 为 service，执行**第二次 CAS 登录**。SDK 复用已存储的 TGT 自动完成 SSO。访问 redirect_url 后获取应用级 `GS_SESSIONID` / `_WEU`。
4. **API 调用**：POST 到 `modules/<module>/<endpoint>.do` 获取 JSON 数据。

### ehall 应用 ID 与 API 端点映射

| 功能 | appId | 模块名 | API 端点 | Adapter 类 |
|------|-------|--------|----------|-----------|
| 课程表 | `4770397878132218` | `wdkb` | `xskcb/xskcb.do` | `CourseAdapter` |
| 成绩查询 | `4768574631264620` | `cjcx` | `cjcx/xscjcx.do` | `GradeAdapter` |
| 考试安排 | `4768687067472349` | `studentWdksapApp` | `wdksap/wdksap.do` | `ExamAdapter` |

新增 ehall 教务适配器只需继承 `EhallBaseAdapter`，设置 `_APP_ID`、`_API_PATH`，实现 `_module_name()` 和 `_parse_response()` 方法。

> **SDK headers 清理**：SEU-Auth SDK 返回的 httpx 客户端携带 CAS 专用的 `Content-Type: application/json`、`Origin`、`Referer` 头。这些头对 ehall 业务请求有害（触发 403），CourseAdapter 在每次 CAS 登录后自动清理。

### VPN 重定向检测

CourseAdapter 在每步请求后检查响应 URL 是否包含 `vpn.seu.edu.cn`，若检测到则立即抛出带有网络环境提示的 `AdapterError`，避免模糊的 JSON 解析错误。

### 学期自动推断

ehall 课表 API（`xskcb.do`）要求传入 `XNXQDM` 学期代码参数（格式：`YYYY1-YYYY2-T`）。**注意 SEU 的学期编号与自然时间顺序不同**（已通过 `xnxq/xnxqcx.do` 端点的 41 条历史学期记录验证）：

- T=1：暑期学校（归入下一学年）
- T=2：秋季学期
- T=3：春季学期

ehall **没有**提供服务端"当前学期"查询接口（`curdqxnxq.do` 返回 403），因此采用本地日期推算：

| 月份 | 学期 | 学年代码示例（假设当前年份为 Y） |
|------|------|----------------------------------|
| 7 ~ 8 | 暑期学校 (T=1)，归入下一学年 | `Y-(Y+1)-1` |
| 9 ~ 12 | 秋季 (T=2) | `Y-(Y+1)-2` |
| 1 | 秋季 (T=2)（考试周仍属上学期） | `(Y-1)-Y-2` |
| 2 ~ 6 | 春季 (T=3) | `(Y-1)-Y-3` |

实现位于 `course_adapter.py` 的 `compute_current_semester()` 函数，用户也可通过 `--semester` 参数手动指定。

### 课表网格渲染

`campus course` 使用 Rich Table 渲染周视图课表网格：

- **行**：节次分组（1-2 / 3-5 / 6-7 / 8-10 / 11-12），空行自动省略
- **列**：周一至周五（若检测到周末课程自动扩展为七列）
- **单元格**：课程名（粗体）+ 教室（暗色）+ 周次（绿色）
- **标题**：动态显示学年和学期名称，如 "📚 2025-2026 学年 春季学期课程表"
- **`--week N`**：按教学周筛选，仅显示第 N 周有课的课程（基于 `ZCMC` 字段的周次范围解析）

### 成绩查询

`campus grade` 查询成绩，使用 `GradeAdapter`（appId=`4768574631264620`）。

- 默认查询全部学期成绩，`--semester` 可指定学期
- 渲染包含课程名、成绩、学分、绩点、类型、学期的表格
- 底部显示总学分和加权绩点

### 考试安排

`campus exam` 查询考试安排，使用 `ExamAdapter`（appId=`4768687067472349`）。

- 默认查询当前学期考试，`--semester` 可指定学期
- 渲染包含课程名、考试时间、考场、座位号、学分的表格

### 校车时刻表

`campus bus` 查询校车时刻表，使用 `BusAdapter`（静态适配器，数据来源: 东南大学总务处）。

- **数据来源**: `zwc.seu.edu.cn` 官方公告页面的时刻表图片，手动转录为 `cli_campus/data/bus_schedule.json`
- **不需要认证**: 与其他 ehall 适配器不同，BusAdapter 直接读取本地 JSON，无需 CAS 登录
- `--route` 按线路名筛选（模糊匹配，如 `--route 循环`、`--route 兰台`、`--route 无线谷`）
- `--type` 按时刻表类型筛选: `workday`（工作日）/ `holiday`（节假日）/ `spring_festival`（春节）
- 渲染按时段分组的表格（早间/上午/中午/下午/傍晚/晚间），底部显示备注和数据更新时间
- 覆盖 3 条线路: 九龙湖校园循环巴士（72趟/工作日、23趟/节假日、11趟/春节）、兰台接驳车、无线谷班线
- **更新数据**: 修改 `cli_campus/data/bus_schedule.json`，时间格式 `HH:MM`，按线路和方向分组
