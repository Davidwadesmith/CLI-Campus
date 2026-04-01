# YAML 声明式解析引擎设计文档

> 拒绝为每一个信息门户页面手写 Python 代码。通过极简的 YAML 配置文件定义数据抽取逻辑。

---

## 1. 设计目标

传统的爬虫开发模式中，每一个数据源都需要编写独立的 Python 模块来处理 HTTP 请求和数据解析。这给维护带来了巨大的成本。

**YAML 声明式引擎**的目标是：让贡献者仅通过编写 YAML 配置文件就能接入新的数据源，而无需编写任何 Python 代码。

---

## 2. 配置格式规范

### 2.1 基本结构

```yaml
# 适配器元数据
name: seu_finance_news          # 适配器标识符
display_name: "财务处新闻"       # 人类可读名称
category: news                   # 对应 EventCategory 枚举
source: static_json              # 对应 AdapterSource 枚举

# 请求配置
request:
  url: "http://cwc.seu.edu.cn/api/news"
  method: GET                    # GET / POST
  headers:
    User-Agent: "CLI-Campus/0.1"
  params:                        # URL 查询参数
    pageSize: 20
    pageNo: 1
  timeout: 10                   # 秒

# 数据抽取配置
extract:
  type: json                    # json / html / regex
  root: "$.data"                # JSONPath: 数据根节点
  mapping:                      # 字段映射
    title: "$.title"
    date: "$.publish_time"
    url: "$.link"
    summary: "$.abstract"

# 转换规则（可选）
transform:
  date_format: "%Y-%m-%d %H:%M:%S"
  title_prefix: "[财务处]"
```

### 2.2 HTML 类型抽取

```yaml
name: seu_nic_notice
display_name: "网络与信息中心通知"
category: news

request:
  url: "https://nic.seu.edu.cn/tzgg/list.htm"
  method: GET

extract:
  type: html
  selector: "div.news-list ul li"     # CSS 选择器
  mapping:
    title:
      selector: "a"
      attr: "text"
    url:
      selector: "a"
      attr: "href"
    date:
      selector: "span.date"
      attr: "text"
```

### 2.3 正则表达式抽取

```yaml
name: seu_calendar
display_name: "校历"
category: other

request:
  url: "https://example.seu.edu.cn/calendar"
  method: GET

extract:
  type: regex
  pattern: '<td class="event">(?P<date>\d{4}-\d{2}-\d{2})</td>\s*<td>(?P<title>.*?)</td>'
  mapping:
    date: date
    title: title
```

---

## 3. 引擎架构

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  YAML 文件   │────▶│ YAMLConfigLoader │────▶│  DeclarativeAdp   │
│  (配置声明)   │     │  (解析 + 校验)    │     │  (自动生成 Adapter)│
└─────────────┘     └─────────────────┘     └──────────────────┘
                                                     │
                                                     ▼
                                            ┌──────────────────┐
                                            │  Extractor        │
                                            │  (JSON/HTML/Regex)│
                                            └──────────────────┘
```

### 3.1 核心类设计

```python
# cli_campus/core/yaml_engine.py (Phase 2 实现)

from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel


class RequestConfig(BaseModel):
    url: str
    method: str = "GET"
    headers: dict[str, str] = {}
    params: dict[str, Any] = {}
    timeout: int = 10


class ExtractConfig(BaseModel):
    type: str  # "json" | "html" | "regex"
    root: str = "$"
    selector: str = ""
    pattern: str = ""
    mapping: dict[str, Any] = {}


class YAMLAdapterConfig(BaseModel):
    name: str
    display_name: str = ""
    category: str = "other"
    source: str = "static_json"
    request: RequestConfig
    extract: ExtractConfig


def load_yaml_config(path: Path) -> YAMLAdapterConfig:
    """从 YAML 文件加载适配器配置。"""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return YAMLAdapterConfig.model_validate(raw)
```

### 3.2 自动生成 Adapter

```python
class DeclarativeAdapter(BaseCampusAdapter):
    """由 YAML 配置自动生成的声明式适配器。"""

    def __init__(self, yaml_config: YAMLAdapterConfig) -> None:
        super().__init__(config=yaml_config.model_dump())
        self._yaml = yaml_config

    async def check_auth(self) -> bool:
        return True  # 声明式适配器通常不需要认证

    async def fetch(self, **kwargs: Any) -> list[CampusEvent]:
        # 1. 发起请求
        response = await self._make_request()
        # 2. 根据 type 选择抽取器
        extractor = self._get_extractor()
        # 3. 抽取数据
        raw_items = extractor.extract(response)
        # 4. 转换为 CampusEvent
        return [self._to_event(item) for item in raw_items]
```

---

## 4. YAML 配置文件存放位置

```
cli-campus/
└── configs/
    └── declarative/
        ├── seu_finance_news.yaml
        ├── seu_nic_notice.yaml
        └── seu_calendar.yaml
```

---

## 5. 使用示例

```bash
# 使用声明式配置抓取数据
campus fetch --config configs/declarative/seu_finance_news.yaml

# JSON 输出
campus fetch --config configs/declarative/seu_finance_news.yaml --json
```

---

## 6. JSONPath 快速参考

| 表达式 | 含义 |
|--------|------|
| `$` | 根节点 |
| `$.store.book[*]` | 所有书籍 |
| `$.store.book[0]` | 第一本书 |
| `$.store.book[*].author` | 所有作者 |
| `$..price` | 所有价格（递归搜索） |
| `$.store.book[?(@.price<10)]` | 价格小于 10 的书 |

YAML 声明式引擎计划在 **Phase 2 (Week 4~6)** 正式实现。
