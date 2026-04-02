# CLI-Campus 落地路线图 (The Execution Playbook)

本文档是 CLI-Campus 从 Phase 0 到 Phase 4 的详细执行时间表，可直接转化为 GitHub Projects 任务板。

---

## 阶段零：基础设施与标准确立 (Phase 0: Foundation) — Week 1

> 目标：搭好台子，定好规矩，让后续贡献者有法可依。

### 工程脚手架

- [x] 使用 `uv` 初始化现代 Python 项目结构
- [x] 配置 `pyproject.toml`（依赖声明、构建系统）
- [x] 配置 `Ruff` 进行极速代码格式化与 Linting
- [x] 配置基本的 GitHub Actions CI

### 定义核心协议

- [x] 编写 `core/models.py`：Pydantic Standard Types（CampusEvent、CourseInfo、BusRoute、TaskItem）
- [x] 编写 `core/interfaces.py`：抽象基类 `BaseCampusAdapter`
- [x] 编写 `core/config.py`：配置加载逻辑

### 基础 CLI 骨架

- [x] 基于 `Typer` 跑通 `campus --help` 命令
- [x] 全局植入 `--json` 参数拦截中间件
- [x] 实现 `campus test-adapter` 验证全链路
- [x] 实现 `campus version` 命令

---

## 阶段一：单点突破与核心鉴权 (Phase 1: The Auth Blocker) — Week 2~3

> 目标：啃下最硬的骨头，跑通第一个完整的业务闭环。

### 攻坚统一身份认证 (CAS Engine)

- [x] ~~抓包逆向东南大学 CAS 登录加密流~~ → 集成 SEU-Auth SDK 代替手动逆向
- [x] 集成 `keyring` 库实现凭证安全存储
- [x] 实现 `campus auth login` 命令（交互式引导输入学号密码）
- [x] 实现 `campus auth status` 命令（检查 Token/Cookie 有效性）
- [x] 实现 `campus auth logout` 命令（清除本地凭证）

```python
# 预期 CAS 登录流程伪代码
async def cas_login(username: str, password: str) -> CASSession:
    # 1. GET /cas/login 获取登录页面
    # 2. 解析隐藏字段 (lt, execution, _eventId)
    # 3. RSA 加密密码
    # 4. POST /cas/login 提交表单
    # 5. 跟踪重定向，获取 TGT/ST
    # 6. 存入 keyring
    ...
```

### 实现静态适配器 — 校车模块

- [x] ~~编写 GitHub Actions 脚本：每周抓取学校校车 PDF~~ → 从总务处官方页面转录时刻表至 `bus_schedule.json`
- [x] CLI 端从本地 JSON 加载时刻表并用 Rich 渲染漂亮表格
- [x] 实现 `campus bus` 命令（支持 `--route`、`--type` 过滤参数）

```python
# 实际命令示例
$ campus bus --route 循环 --type workday
┌──────────────────────────────────────────────────────┐
│ 🚌 九龙湖校园循环巴士 (图书馆北→循环线路)              │
├──────────┬───────────────────────────────────────────┤
│  时段    │ 工作日                                     │
├──────────┼───────────────────────────────────────────┤
│  早间    │ 07:00  07:10  07:20  ...                  │
│  上午    │ 10:00  10:30  11:00  ...                  │
│  ...     │ ...                                       │
└──────────┴───────────────────────────────────────────┘

# 数据来源: 东南大学总务处 (zwc.seu.edu.cn)
# 覆盖线路: 校园循环巴士(72趟/工作日), 兰台接驳车, 无线谷班线
```

### 实现首个动态适配器

- [x] 一卡通余额查询 `campus card`（CardAdapter）
- [x] 课程表查询 `campus course`（CourseAdapter — ehall 教务接口）
- [x] 验证全链路：CAS Token → API 请求 → Pydantic 校验 → Rich/JSON 输出

---

## 阶段二：配置化与复杂场景 (Phase 2: YAML & Stateful Adapters) — Week 4~6

> 目标：降低扩展门槛，处理极其复杂的反爬场景。

### YAML 声明式解析引擎

- [x] 编写读取 `.yaml` 配置并自动生成标准 HTTP 请求的引擎（`cli_campus/core/yaml_engine.py`）
- [x] 集成 `JSONPath`（jsonpath-ng）、CSS 选择器（BeautifulSoup）和正则表达式三种抽取模式
- [x] 验证能否仅靠写 YAML 就把信息门户的通知公告爬下来 → `configs/declarative/seu_jwc_news.yaml` 成功抓取教务处通知
- [x] 实现 `campus fetch <name>` 运行声明式适配器
- [x] 实现 `campus fetch-list` 列出所有可用配置
- [x] 24 项单元测试全部通过

```yaml
# 示例 YAML 配置
name: seu_finance_news
url: http://cwc.seu.edu.cn/api/news
method: GET
extract:
  type: json
  mapping:
    title: $.data[*].title
    date: $.data[*].publish_time
```

### 复杂状态适配器 — 学习通/雨课堂 DDL

- [ ] 引入 `Playwright` 构建无头浏览器池
- [ ] 实现 Token 失效时的自动静默重认证
- [ ] 抓取作业 DDL 并洗成 `TaskItem` 模型
- [ ] 落入本地 SQLite 缓存
- [ ] 实现 `campus ddl` 命令

---

## 阶段三：Agent-Native 改造 (Phase 3: The AI Infrastructure) — Week 7~8

> 目标：让 CLI-Campus 正式成为上层 AI 的"武器库"。

### Tool Schema 自动生成器

- [x] 实现 `campus schema export` 命令（`cli_campus/core/schema_export.py`）
- [x] 利用 Typer/Click 反射遍历所有命令及参数类型
- [x] 自动生成 OpenAI / DeepSeek Function Calling 标准的 JSON Schema
- [x] 支持 `--pretty` 美化输出和 `--commands` 过滤
- [x] 12 项单元测试全部通过

```json
{
  "name": "campus_bus",
  "description": "查询校车时刻表",
  "parameters": {
    "type": "object",
    "properties": {
      "from": {"type": "string", "description": "出发校区"},
      "to": {"type": "string", "description": "到达校区"},
      "time": {"type": "string", "description": "时间段"}
    }
  }
}
```

### SOP 宏执行器

- [x] 实现预设任务流 YAML 解析器（`cli_campus/core/sop_engine.py`）
- [x] 支持串联原子工具（通过 subprocess 调用 CLI 命令获取 JSON 结果）
- [x] 支持 Jinja2 模板渲染 Markdown 输出
- [x] 实现 `campus sop list` / `campus sop run <name>` 命令
- [x] 创建 `sops/morning_briefing.yaml` 示例 SOP（课表 + 校车）
- [x] 15 项单元测试全部通过

### M2M 联调测试

- [x] 编写 M2M 联调测试脚本（`scripts/m2m_test.py`，~160 行）
- [x] 支持 DeepSeek / OpenAI 兼容接口，通过环境变量配置
- [x] 自动加载 Tool Schema → LLM 调用 → 执行 CLI → 返回结果 → LLM 回答

---

## 阶段四：生态繁荣与多校共建 (Phase 4: Open Ecosystem) — Month 3+

> 目标：将项目推向全校甚至全国。

### 多租户架构重构

- [ ] 实现 `campus init` 初始化配置
- [ ] 重组 Adapter 目录结构：`adapters/vendors/zhengfang`（按供应商）和 `adapters/schools/seu`（按学校）
- [ ] 建立 Adapter Registry 接受全网高校开发者提 PR

### 文档与主页

- [ ] 使用 VitePress 编写官方文档
- [ ] 部署至 I++ OSS Hub (dmajor.top)

### 状态监控台

- [ ] GitHub Actions Cron Job 每天运行所有核心命令
- [ ] 抓取失败时自动告警
- [ ] 开源主页展示"当前服务健康状态"
