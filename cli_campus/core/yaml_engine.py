"""YAML 声明式解析引擎 — 通过 YAML 配置文件自动生成 Adapter。

本模块允许贡献者仅通过编写 YAML 配置文件就能接入新的数据源，
而无需编写任何 Python 代码。引擎自动处理 HTTP 请求和数据抽取。

支持三种抽取模式:
- **json**: JSONPath 表达式从 JSON 响应中抽取字段
- **html**: CSS 选择器从 HTML 页面中抽取字段
- **regex**: 正则表达式从纯文本中抽取字段
"""

from __future__ import annotations

import re
from datetime import datetime
from hashlib import md5
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import BaseModel, Field

from cli_campus.core.exceptions import AdapterError
from cli_campus.core.interfaces import BaseCampusAdapter
from cli_campus.core.models import AdapterSource, CampusEvent, EventCategory

# ---------------------------------------------------------------------------
# 配置模型
# ---------------------------------------------------------------------------


class RequestConfig(BaseModel):
    """HTTP 请求配置。"""

    url: str
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    body: dict[str, Any] = Field(default_factory=dict)
    timeout: int = 10


class FieldMapping(BaseModel):
    """HTML 抽取时的字段映射（支持 selector + attr）。"""

    selector: str = ""
    attr: str = "text"


class ExtractConfig(BaseModel):
    """数据抽取配置。"""

    type: str = "json"  # "json" | "html" | "regex"
    root: str = "$"
    selector: str = ""
    pattern: str = ""
    mapping: dict[str, Any] = Field(default_factory=dict)


class TransformConfig(BaseModel):
    """可选的转换规则。"""

    date_format: str = ""
    title_prefix: str = ""


class YAMLAdapterConfig(BaseModel):
    """完整的 YAML 适配器配置。"""

    name: str
    display_name: str = ""
    category: str = "other"
    source: str = "static_json"
    request: RequestConfig
    extract: ExtractConfig
    transform: TransformConfig = Field(default_factory=TransformConfig)


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------


def load_yaml_config(path: Path) -> YAMLAdapterConfig:
    """从 YAML 文件加载适配器配置。"""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise AdapterError(f"YAML 配置格式错误: {path}")
    return YAMLAdapterConfig.model_validate(raw)


def discover_yaml_configs(config_dir: Path) -> list[YAMLAdapterConfig]:
    """扫描目录下所有 .yaml / .yml 文件并加载配置。"""
    configs: list[YAMLAdapterConfig] = []
    if not config_dir.is_dir():
        return configs
    for p in sorted(config_dir.glob("*.yaml")):
        configs.append(load_yaml_config(p))
    for p in sorted(config_dir.glob("*.yml")):
        configs.append(load_yaml_config(p))
    return configs


# ---------------------------------------------------------------------------
# 数据抽取器
# ---------------------------------------------------------------------------


def _extract_json(response_text: str, config: ExtractConfig) -> list[dict[str, Any]]:
    """使用 JSONPath 从 JSON 响应中抽取数据。"""
    import json

    from jsonpath_ng.ext import parse as jp_parse

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise AdapterError(f"JSON 解析失败: {exc}") from exc

    # 先定位数据根节点
    if config.root and config.root != "$":
        root_expr = jp_parse(config.root)
        matches = root_expr.find(data)
        if not matches:
            return []
        root_data = matches[0].value
    else:
        root_data = data

    # 如果根节点是列表，对每个元素应用 mapping
    items = root_data if isinstance(root_data, list) else [root_data]

    results: list[dict[str, Any]] = []
    for item in items:
        row: dict[str, Any] = {}
        for field_name, jsonpath_expr in config.mapping.items():
            if isinstance(jsonpath_expr, str) and jsonpath_expr.startswith("$"):
                # 相对于当前 item 的 JSONPath（去掉 $. 前缀）
                rel_path = jsonpath_expr.lstrip("$").lstrip(".")
                if rel_path:
                    expr = jp_parse(rel_path)
                    found = expr.find(item)
                    row[field_name] = found[0].value if found else ""
                else:
                    row[field_name] = item
            else:
                # 直接作为 key 访问
                row[field_name] = item.get(jsonpath_expr, "") if isinstance(item, dict) else ""
        results.append(row)

    return results


def _extract_html(response_text: str, config: ExtractConfig) -> list[dict[str, Any]]:
    """使用 CSS 选择器从 HTML 响应中抽取数据。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(response_text, "html.parser")

    if not config.selector:
        raise AdapterError("HTML 抽取模式需要配置 selector")

    elements = soup.select(config.selector)
    results: list[dict[str, Any]] = []

    for el in elements:
        row: dict[str, Any] = {}
        for field_name, field_config in config.mapping.items():
            if isinstance(field_config, dict):
                sel = field_config.get("selector", "")
                attr = field_config.get("attr", "text")
                target = el.select_one(sel) if sel else el
            else:
                target = el.select_one(str(field_config)) if field_config else el
                attr = "text"

            if target is None:
                row[field_name] = ""
            elif attr == "text":
                row[field_name] = target.get_text(strip=True)
            else:
                row[field_name] = target.get(attr, "")
        results.append(row)

    return results


def _extract_regex(response_text: str, config: ExtractConfig) -> list[dict[str, Any]]:
    """使用正则表达式从文本中抽取数据。"""
    if not config.pattern:
        raise AdapterError("Regex 抽取模式需要配置 pattern")

    results: list[dict[str, Any]] = []
    for match in re.finditer(config.pattern, response_text, re.DOTALL):
        row = match.groupdict()
        # 如果有 mapping 则重命名字段
        if config.mapping:
            mapped: dict[str, Any] = {}
            for field_name, group_name in config.mapping.items():
                mapped[field_name] = row.get(str(group_name), "")
            results.append(mapped)
        else:
            results.append(row)

    return results


_EXTRACTORS = {
    "json": _extract_json,
    "html": _extract_html,
    "regex": _extract_regex,
}


# ---------------------------------------------------------------------------
# 声明式适配器
# ---------------------------------------------------------------------------


class DeclarativeAdapter(BaseCampusAdapter):
    """由 YAML 配置自动生成的声明式适配器。"""

    def __init__(self, yaml_config: YAMLAdapterConfig) -> None:
        super().__init__(config=yaml_config.model_dump())
        self._yaml = yaml_config

    def adapter_name(self) -> str:
        return self._yaml.display_name or self._yaml.name

    async def check_auth(self) -> bool:
        return True

    async def fetch(self, **kwargs: Any) -> list[CampusEvent]:
        req = self._yaml.request

        # 发起 HTTP 请求
        async with httpx.AsyncClient(
            timeout=req.timeout, follow_redirects=True
        ) as client:
            try:
                if req.method.upper() == "POST":
                    resp = await client.post(
                        req.url,
                        headers=req.headers,
                        params=req.params,
                        json=req.body if req.body else None,
                    )
                else:
                    resp = await client.get(
                        req.url,
                        headers=req.headers,
                        params=req.params,
                    )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise AdapterError(
                    f"[{self._yaml.name}] 请求失败: {exc}"
                ) from exc

        # 选择抽取器
        extract_type = self._yaml.extract.type
        extractor = _EXTRACTORS.get(extract_type)
        if extractor is None:
            raise AdapterError(f"不支持的抽取类型: {extract_type}")

        raw_items = extractor(resp.text, self._yaml.extract)

        # 转换为 CampusEvent
        category = EventCategory(self._yaml.category)
        try:
            source = AdapterSource(self._yaml.source)
        except ValueError:
            source = AdapterSource.STATIC_JSON

        transform = self._yaml.transform
        events: list[CampusEvent] = []
        for item in raw_items:
            # 应用转换规则
            title = item.get("title", "")
            if transform.title_prefix:
                title = f"{transform.title_prefix} {title}"

            event_hash = md5(
                f"{self._yaml.name}:{title}".encode()
            ).hexdigest()[:12]

            events.append(
                CampusEvent(
                    id=f"{self._yaml.name}:{category.value}:{event_hash}",
                    source=source,
                    category=category,
                    title=title,
                    content=item,
                    timestamp=datetime.now(),
                )
            )

        return events
