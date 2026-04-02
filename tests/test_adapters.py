"""Tests for BaseCampusAdapter interface and MockAdapter."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from cli_campus.adapters.mock_adapter import MockAdapter
from cli_campus.core.interfaces import BaseCampusAdapter
from cli_campus.core.models import AdapterSource, CampusEvent, EventCategory


class TestBaseCampusAdapter:
    """适配器抽象基类测试。"""

    def test_cannot_instantiate_abstract(self) -> None:
        """抽象基类不允许直接实例化。"""
        with pytest.raises(TypeError):
            BaseCampusAdapter(config={})  # type: ignore[abstract]

    def test_concrete_adapter_must_implement(self) -> None:
        """缺少 check_auth 或 fetch 的子类不允许实例化。"""

        class IncompleteAdapter(BaseCampusAdapter):
            async def check_auth(self) -> bool:
                return True

            # fetch 未实现

        with pytest.raises(TypeError):
            IncompleteAdapter(config={})  # type: ignore[abstract]

    def test_adapter_name_default(self) -> None:
        """adapter_name() 默认返回类名。"""

        class DummyAdapter(BaseCampusAdapter):
            async def check_auth(self) -> bool:
                return True

            async def fetch(self, **kwargs: Any) -> list[CampusEvent]:
                return []

        adapter = DummyAdapter(config={"key": "value"})
        assert adapter.adapter_name() == "DummyAdapter"
        assert adapter.config == {"key": "value"}


class TestMockAdapter:
    """MockAdapter 测试。"""

    def test_mock_auth(self) -> None:
        adapter = MockAdapter(config={})
        result = asyncio.run(adapter.check_auth())
        assert result is True

    def test_mock_fetch_returns_events(self) -> None:
        adapter = MockAdapter(config={})
        events = asyncio.run(adapter.fetch())
        assert len(events) == 1
        assert isinstance(events[0], CampusEvent)

    def test_mock_fetch_event_structure(self) -> None:
        adapter = MockAdapter(config={})
        events = asyncio.run(adapter.fetch())
        event = events[0]
        assert event.source == AdapterSource.MOCK
        assert event.category == EventCategory.COURSE
        assert "name" in event.content
        assert event.content["name"] == "高等数学 A"
        assert event.content["day_of_week"] == 1
        assert event.content["periods"] == "1-2"

    def test_mock_adapter_name(self) -> None:
        adapter = MockAdapter(config={})
        assert adapter.adapter_name() == "MockAdapter"
