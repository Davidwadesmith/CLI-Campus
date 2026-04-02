"""Tests for CardAdapter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cli_campus.adapters.card_adapter import CardAdapter
from cli_campus.core.exceptions import AdapterError, AuthRequiredError
from cli_campus.core.models import AdapterSource, EventCategory


class TestCardAdapter:
    """一卡通适配器测试。"""

    @patch("cli_campus.adapters.card_adapter.SEUAuthWrapper")
    def test_fetch_success(self, mock_wrapper_cls: MagicMock) -> None:
        """正常流程：认证成功 + API 返回有效数据。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "student_id": "213000001",
            "name": "张三",
            "balance": 128.50,
            "status": "正常",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        mock_wrapper = AsyncMock()
        mock_wrapper.get_authenticated_client = AsyncMock(
            return_value=(mock_client, "https://redirect.url")
        )
        mock_wrapper.close = AsyncMock()
        mock_wrapper_cls.return_value = mock_wrapper

        adapter = CardAdapter()
        events = asyncio.run(adapter.fetch())

        assert len(events) == 1
        event = events[0]
        assert event.source == AdapterSource.SEU_CARD
        assert event.category == EventCategory.CARD
        assert event.content["student_id"] == "213000001"
        assert event.content["balance"] == 128.50
        assert "128.50" in event.title

    @patch("cli_campus.adapters.card_adapter.SEUAuthWrapper")
    def test_fetch_no_credentials(self, mock_wrapper_cls: MagicMock) -> None:
        """无凭证时抛出 AuthRequiredError。"""
        mock_wrapper = AsyncMock()
        mock_wrapper.get_authenticated_client = AsyncMock(
            side_effect=AuthRequiredError()
        )
        mock_wrapper.close = AsyncMock()
        mock_wrapper_cls.return_value = mock_wrapper

        adapter = CardAdapter()

        with pytest.raises(AuthRequiredError):
            asyncio.run(adapter.fetch())

    @patch("cli_campus.adapters.card_adapter.SEUAuthWrapper")
    def test_fetch_api_error(self, mock_wrapper_cls: MagicMock) -> None:
        """API 请求失败时抛出 AdapterError。"""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("Connection refused"))

        mock_wrapper = AsyncMock()
        mock_wrapper.get_authenticated_client = AsyncMock(
            return_value=(mock_client, None)
        )
        mock_wrapper.close = AsyncMock()
        mock_wrapper_cls.return_value = mock_wrapper

        adapter = CardAdapter()

        with pytest.raises(AdapterError, match="一卡通 API 请求失败"):
            asyncio.run(adapter.fetch())

    def test_adapter_name(self) -> None:
        adapter = CardAdapter()
        assert adapter.adapter_name() == "CardAdapter"

    def test_custom_config(self) -> None:
        adapter = CardAdapter(
            config={
                "service_url": "https://custom.seu.edu.cn",
                "api_url": "https://custom.seu.edu.cn/api",
            }
        )
        assert adapter._service_url == "https://custom.seu.edu.cn"
        assert adapter._api_url == "https://custom.seu.edu.cn/api"
