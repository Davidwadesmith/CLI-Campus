"""YAML 声明式解析引擎测试。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from cli_campus.core.yaml_engine import (
    DeclarativeAdapter,
    ExtractConfig,
    YAMLAdapterConfig,
    _extract_html,
    _extract_json,
    _extract_regex,
    discover_yaml_configs,
    load_yaml_config,
)


# ---------------------------------------------------------------------------
# 配置加载测试
# ---------------------------------------------------------------------------


class TestLoadYAMLConfig:
    """YAML 配置加载测试。"""

    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        yaml_content = """
name: test_adapter
display_name: "测试适配器"
category: news
source: static_json
request:
  url: "https://example.com/api"
  method: GET
  timeout: 5
extract:
  type: json
  root: "$.data"
  mapping:
    title: "$.title"
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        config = load_yaml_config(yaml_file)

        assert config.name == "test_adapter"
        assert config.display_name == "测试适配器"
        assert config.category == "news"
        assert config.request.url == "https://example.com/api"
        assert config.request.method == "GET"
        assert config.request.timeout == 5
        assert config.extract.type == "json"
        assert config.extract.root == "$.data"

    def test_load_minimal_yaml(self, tmp_path: Path) -> None:
        yaml_content = """
name: minimal
request:
  url: "https://example.com"
extract:
  type: json
"""
        yaml_file = tmp_path / "minimal.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        config = load_yaml_config(yaml_file)

        assert config.name == "minimal"
        assert config.display_name == ""
        assert config.category == "other"
        assert config.request.method == "GET"
        assert config.request.timeout == 10
        assert config.extract.type == "json"

    def test_load_invalid_yaml(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text("not a dict", encoding="utf-8")

        with pytest.raises(Exception):
            load_yaml_config(yaml_file)


class TestDiscoverConfigs:
    """配置发现测试。"""

    def test_discover_yaml_files(self, tmp_path: Path) -> None:
        for name in ["a.yaml", "b.yaml"]:
            (tmp_path / name).write_text(
                f"name: {name.split('.')[0]}\nrequest:\n  url: https://example.com\nextract:\n  type: json\n",
                encoding="utf-8",
            )

        configs = discover_yaml_configs(tmp_path)
        assert len(configs) == 2
        assert configs[0].name == "a"
        assert configs[1].name == "b"

    def test_discover_empty_dir(self, tmp_path: Path) -> None:
        configs = discover_yaml_configs(tmp_path)
        assert configs == []

    def test_discover_nonexistent_dir(self) -> None:
        configs = discover_yaml_configs(Path("/nonexistent"))
        assert configs == []


# ---------------------------------------------------------------------------
# JSON 抽取器测试
# ---------------------------------------------------------------------------


class TestJsonExtractor:
    """JSON 抽取器测试。"""

    def test_extract_flat_array(self) -> None:
        response = json.dumps({
            "data": [
                {"title": "新闻A", "date": "2026-01-01"},
                {"title": "新闻B", "date": "2026-01-02"},
            ]
        })
        config = ExtractConfig(
            type="json",
            root="$.data",
            mapping={"title": "$.title", "date": "$.date"},
        )
        items = _extract_json(response, config)
        assert len(items) == 2
        assert items[0]["title"] == "新闻A"
        assert items[1]["date"] == "2026-01-02"

    def test_extract_no_root(self) -> None:
        response = json.dumps([{"name": "A"}, {"name": "B"}])
        config = ExtractConfig(type="json", mapping={"name": "$.name"})
        items = _extract_json(response, config)
        assert len(items) == 2
        assert items[0]["name"] == "A"

    def test_extract_single_object(self) -> None:
        response = json.dumps({"title": "单条", "count": 42})
        config = ExtractConfig(type="json", mapping={"title": "$.title", "count": "$.count"})
        items = _extract_json(response, config)
        assert len(items) == 1
        assert items[0]["title"] == "单条"
        assert items[0]["count"] == 42

    def test_extract_invalid_json(self) -> None:
        with pytest.raises(Exception, match="JSON 解析失败"):
            _extract_json("not json", ExtractConfig(type="json"))


# ---------------------------------------------------------------------------
# HTML 抽取器测试
# ---------------------------------------------------------------------------


class TestHtmlExtractor:
    """HTML 抽取器测试。"""

    def test_extract_list_items(self) -> None:
        html = """
        <ul class="news">
            <li><a href="/a.htm">新闻A</a><span class="date">2026-01-01</span></li>
            <li><a href="/b.htm">新闻B</a><span class="date">2026-01-02</span></li>
        </ul>
        """
        config = ExtractConfig(
            type="html",
            selector="ul.news li",
            mapping={
                "title": {"selector": "a", "attr": "text"},
                "url": {"selector": "a", "attr": "href"},
                "date": {"selector": "span.date", "attr": "text"},
            },
        )
        items = _extract_html(html, config)
        assert len(items) == 2
        assert items[0]["title"] == "新闻A"
        assert items[0]["url"] == "/a.htm"
        assert items[1]["date"] == "2026-01-02"

    def test_extract_no_selector(self) -> None:
        with pytest.raises(Exception, match="selector"):
            _extract_html("<html></html>", ExtractConfig(type="html"))

    def test_extract_missing_element(self) -> None:
        html = "<li><a href='/a'>A</a></li>"
        config = ExtractConfig(
            type="html",
            selector="li",
            mapping={
                "title": {"selector": "a", "attr": "text"},
                "date": {"selector": "span.date", "attr": "text"},
            },
        )
        items = _extract_html(html, config)
        assert len(items) == 1
        assert items[0]["title"] == "A"
        assert items[0]["date"] == ""


# ---------------------------------------------------------------------------
# Regex 抽取器测试
# ---------------------------------------------------------------------------


class TestRegexExtractor:
    """正则表达式抽取器测试。"""

    def test_extract_simple_pattern(self) -> None:
        text = '<td class="event">2026-01-01</td><td>期末考试</td>\n<td class="event">2026-06-15</td><td>暑假开始</td>'
        config = ExtractConfig(
            type="regex",
            pattern=r'<td class="event">(?P<date>\d{4}-\d{2}-\d{2})</td><td>(?P<title>.*?)</td>',
        )
        items = _extract_regex(text, config)
        assert len(items) == 2
        assert items[0]["date"] == "2026-01-01"
        assert items[0]["title"] == "期末考试"

    def test_extract_with_mapping(self) -> None:
        text = "name=Alice age=20\nname=Bob age=21"
        config = ExtractConfig(
            type="regex",
            pattern=r"name=(?P<n>\w+) age=(?P<a>\d+)",
            mapping={"student_name": "n", "student_age": "a"},
        )
        items = _extract_regex(text, config)
        assert len(items) == 2
        assert items[0]["student_name"] == "Alice"

    def test_extract_no_pattern(self) -> None:
        with pytest.raises(Exception, match="pattern"):
            _extract_regex("text", ExtractConfig(type="regex"))


# ---------------------------------------------------------------------------
# DeclarativeAdapter 测试
# ---------------------------------------------------------------------------


class TestDeclarativeAdapter:
    """声明式适配器测试。"""

    def test_adapter_name(self) -> None:
        config = YAMLAdapterConfig(
            name="test",
            display_name="测试",
            request={"url": "https://example.com"},
            extract={"type": "json"},
        )
        adapter = DeclarativeAdapter(config)
        assert adapter.adapter_name() == "测试"

    def test_adapter_name_fallback(self) -> None:
        config = YAMLAdapterConfig(
            name="test",
            request={"url": "https://example.com"},
            extract={"type": "json"},
        )
        adapter = DeclarativeAdapter(config)
        assert adapter.adapter_name() == "test"

    def test_check_auth(self) -> None:
        config = YAMLAdapterConfig(
            name="test",
            request={"url": "https://example.com"},
            extract={"type": "json"},
        )
        adapter = DeclarativeAdapter(config)
        import asyncio
        assert asyncio.run(adapter.check_auth()) is True

    def test_fetch_json(self) -> None:
        config = YAMLAdapterConfig(
            name="test",
            category="news",
            request={"url": "https://example.com/api"},
            extract={"type": "json", "root": "$.items", "mapping": {"title": "$.name"}},
        )
        adapter = DeclarativeAdapter(config)

        mock_response = type("Response", (), {
            "text": json.dumps({"items": [{"name": "Test News"}]}),
            "raise_for_status": lambda self: None,
        })()

        import asyncio

        async def run() -> list:
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client
                return await adapter.fetch()

        events = asyncio.run(run())
        assert len(events) == 1
        assert events[0].title == "Test News"
        assert events[0].category.value == "news"
        assert events[0].content["title"] == "Test News"

    def test_fetch_with_transform(self) -> None:
        config = YAMLAdapterConfig(
            name="test",
            category="news",
            request={"url": "https://example.com"},
            extract={"type": "json", "mapping": {"title": "$.title"}},
            transform={"title_prefix": "[公告]"},
        )
        adapter = DeclarativeAdapter(config)

        mock_response = type("Response", (), {
            "text": json.dumps([{"title": "测试"}]),
            "raise_for_status": lambda self: None,
        })()

        import asyncio

        async def run() -> list:
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client
                return await adapter.fetch()

        events = asyncio.run(run())
        assert events[0].title == "[公告] 测试"


# ---------------------------------------------------------------------------
# CLI 命令测试
# ---------------------------------------------------------------------------


class TestFetchCLI:
    """fetch / fetch-list CLI 命令测试。"""

    def test_fetch_list(self) -> None:
        from typer.testing import CliRunner
        from cli_campus.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["fetch-list"])
        assert result.exit_code == 0

    def test_fetch_list_json(self) -> None:
        from typer.testing import CliRunner
        from cli_campus.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["--json", "fetch-list"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_fetch_nonexistent(self) -> None:
        from typer.testing import CliRunner
        from cli_campus.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["fetch", "nonexistent_adapter"])
        assert result.exit_code == 1
