# Campus Adapter Protocol — 适配器开发指南

本文档详细说明 CLI-Campus 的核心协议：**Campus Adapter Protocol**。所有数据源都必须通过此协议接入，不允许绕过。

---

## 1. 协议概览

```
                       ┌─────────────────────────┐
                       │  BaseCampusAdapter (ABC) │
                       ├─────────────────────────┤
                       │  + config: dict          │
                       │  + check_auth() -> bool  │
                       │  + fetch(**kw) -> [Event] │
                       │  + adapter_name() -> str  │
                       └───────────┬─────────────┘
                                   │ 继承
                 ┌─────────────────┼─────────────────┐
                 │                 │                  │
          ┌──────▼──────┐  ┌──────▼──────┐  ┌───────▼───────┐
          │ MockAdapter  │  │ SEU_CAS     │  │ ZhengfangAdp  │
          │ (调试用)      │  │ (统一认证)   │  │ (正方教务)     │
          └─────────────┘  └─────────────┘  └───────────────┘
```

---

## 2. 抽象基类定义

所有 Adapter **必须** 继承 `BaseCampusAdapter`，位于 `cli_campus/core/interfaces.py`：

```python
from abc import ABC, abstractmethod
from typing import Any
from cli_campus.core.models import CampusEvent


class BaseCampusAdapter(ABC):
    """校园数据适配器抽象基类。"""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @abstractmethod
    async def check_auth(self) -> bool:
        """验证当前凭证是否有效。返回 True/False。"""
        ...

    @abstractmethod
    async def fetch(self, **kwargs: Any) -> list[CampusEvent]:
        """拉取数据并返回标准化的 CampusEvent 列表。"""
        ...

    def adapter_name(self) -> str:
        """返回适配器名称（默认为类名）。"""
        return self.__class__.__name__
```

### 关键设计决策

1. **异步优先**：`check_auth()` 和 `fetch()` 均为 `async` 方法，为并发拉取多个数据源做好准备。
2. **config 字典注入**：不硬编码任何 URL 或密钥，所有配置通过初始化参数传入，支持多租户场景。
3. **返回值必须是 `CampusEvent` 列表**：上层调用方只认识这一个类型，不关心底层细节。

---

## 3. 统一数据模型 (Standard Types)

所有模型定义在 `cli_campus/core/models.py`，基于 Pydantic v2：

### 3.1 CampusEvent — 顶层信封

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Optional


class CampusEvent(BaseModel):
    id: str                          # 全局唯一 ID (格式: source:category:hash)
    source: AdapterSource            # 数据来源枚举
    category: EventCategory          # 业务分类枚举
    title: str                       # 人类可读标题
    content: dict[str, Any] = {}     # 结构化业务数据（领域模型的 dict 形式）
    raw_data: Optional[dict] = None  # 原始数据快照（调试用）
    timestamp: datetime              # 事件时间戳
```

**为什么用 `content: dict` 而不是泛型？**
- 序列化为 JSON 时更加直接
- 上层 Agent 不需要知道具体的领域类型
- 领域模型（CourseInfo 等）在 Adapter 内部使用，通过 `.model_dump()` 转为 dict 填入 content

### 3.2 领域模型

| 模型 | 用途 | 关键字段 |
|------|------|----------|
| `CourseInfo` | 教务课程 | name, teacher, location, day_of_week, periods, weeks |
| `BusRoute` | 校车时刻 | route_name, departure_time, departure_stop, arrival_stop |
| `TaskItem` | 作业/DDL | task_id, platform, title, deadline, is_completed |
| `CardInfo` | 一卡通 | student_id, name, balance, status |

### 3.3 枚举类型

```python
class EventCategory(str, Enum):
    COURSE = "course"
    BUS = "bus"
    DEADLINE = "deadline"
    NEWS = "news"
    FINANCE = "finance"
    ROOM = "room"
    CARD = "card"
    OTHER = "other"

class AdapterSource(str, Enum):
    SEU_CAS = "seu_cas"
    SEU_CARD = "seu_card"
    SEU_EHALL = "seu_ehall"
    ZHENGFANG = "zhengfang"
    CHAOXING = "chaoxing"
    YUKETANG = "yuketang"
    STATIC_JSON = "static_json"
    MOCK = "mock"
```

---

## 4. 编写新 Adapter 完整示例

假设要为某高校的图书馆座位查询系统编写 Adapter：

```python
# cli_campus/adapters/vendors/library_seat.py

from __future__ import annotations

from datetime import datetime
from hashlib import md5
from typing import Any

from cli_campus.core.interfaces import BaseCampusAdapter
from cli_campus.core.models import AdapterSource, CampusEvent, EventCategory


class LibrarySeatAdapter(BaseCampusAdapter):
    """图书馆座位查询适配器。

    config 参数：
        base_url: 图书馆系统 API 地址
        token: 认证令牌（由 CAS 登录后获取）
    """

    async def check_auth(self) -> bool:
        # 实际实现中应发起一个轻量 API 请求验证 token
        token = self.config.get("token")
        return token is not None and len(token) > 0

    async def fetch(self, **kwargs: Any) -> list[CampusEvent]:
        building = kwargs.get("building", "九龙湖图书馆")

        # 实际实现中应在此处发起 HTTP 请求
        # response = await self._client.get(f"{self.config['base_url']}/seats")
        # raw_seats = response.json()

        # 示例：将原始数据清洗为 CampusEvent
        raw_seats = [
            {"floor": "3F", "zone": "A区", "available": 42, "total": 120},
            {"floor": "4F", "zone": "B区", "available": 15, "total": 80},
        ]

        events: list[CampusEvent] = []
        for seat in raw_seats:
            event_id = md5(
                f"{building}:{seat['floor']}:{seat['zone']}".encode()
            ).hexdigest()[:12]

            events.append(
                CampusEvent(
                    id=f"library:room:{event_id}",
                    source=AdapterSource.MOCK,  # 正式实现时替换为正确的 source
                    category=EventCategory.ROOM,
                    title=f"{building} {seat['floor']}{seat['zone']} "
                          f"空闲 {seat['available']}/{seat['total']}",
                    content=seat,
                    timestamp=datetime.now(),
                )
            )
        return events
```

### 编写 Adapter 的检查清单

- [ ] 继承 `BaseCampusAdapter`
- [ ] 实现 `async check_auth() -> bool`
- [ ] 实现 `async fetch(**kwargs) -> list[CampusEvent]`
- [ ] 所有原始数据在 Adapter 内部完成清洗，不泄露给上层
- [ ] 函数签名有完整的 Type Hints
- [ ] 敏感信息（密码、Token）通过 `config` 传入，不硬编码
- [ ] 编写对应的 pytest 测试用例

---

## 5. 三大技术规范

### 5.1 多层级网页处理

在 Adapter 内部封装 Pipeline 并发拉取，向核心层隐藏跳转过程：

```python
async def fetch(self, **kwargs):
    # Step 1: 获取列表页
    list_page = await self._get("/list")
    # Step 2: 并发获取详情页
    detail_tasks = [self._get(f"/detail/{id}") for id in list_page.ids]
    details = await asyncio.gather(*detail_tasks)
    # Step 3: 清洗并返回
    return [self._to_event(d) for d in details]
```

### 5.2 持久化事件流（推转拉）

QQ 群通知等推送型数据，通过后台守护进程写入本地 SQLite，Adapter 将"推"转换为"拉"：

```python
async def fetch(self, **kwargs):
    import sqlite3
    conn = sqlite3.connect(self.config["db_path"])
    rows = conn.execute("SELECT * FROM notifications ORDER BY time DESC LIMIT 20")
    return [self._row_to_event(row) for row in rows]
```

### 5.3 复杂反爬场景

对于学习通等平台，在 Adapter 内置 Playwright 无头浏览器：

```python
async def fetch(self, **kwargs):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        # 利用已保存的 Cookie 恢复登录态
        await page.context.add_cookies(self._load_cookies())
        await page.goto(self.config["ddl_url"])
        # 解析页面数据...
        await browser.close()
    return events
```
