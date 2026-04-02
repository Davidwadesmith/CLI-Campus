"""Tests for SEUAuthWrapper."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cli_campus.adapters.seu_auth_wrapper import SEUAuthWrapper
from cli_campus.core.auth import CampusAuthManager
from cli_campus.core.exceptions import AuthFailedError, AuthRequiredError


class TestSEUAuthWrapper:
    """SEU-Auth SDK 包装器测试。"""

    def test_raises_auth_required_when_no_credentials(self) -> None:
        """本地无凭证时应抛出 AuthRequiredError。"""
        mock_mgr = MagicMock(spec=CampusAuthManager)
        mock_mgr.get_credentials.return_value = None

        wrapper = SEUAuthWrapper(auth_manager=mock_mgr)

        with pytest.raises(AuthRequiredError):
            asyncio.run(wrapper.get_authenticated_client("https://example.com"))

    @patch("src.seu_auth.SEUAuthManager")
    def test_raises_auth_failed_when_login_returns_none(
        self, mock_sdk_cls: MagicMock
    ) -> None:
        """SDK 登录返回 (None, None) 时应抛出 AuthFailedError。"""
        mock_mgr = MagicMock(spec=CampusAuthManager)
        mock_mgr.get_credentials.return_value = ("213000001", "secret")

        mock_sdk = AsyncMock()
        mock_sdk.__aenter__ = AsyncMock(return_value=mock_sdk)
        mock_sdk.__aexit__ = AsyncMock(return_value=False)
        mock_sdk.login = AsyncMock(return_value=(None, None))
        mock_sdk_cls.return_value = mock_sdk

        wrapper = SEUAuthWrapper(auth_manager=mock_mgr)

        with pytest.raises(AuthFailedError, match="登录失败"):
            asyncio.run(wrapper.get_authenticated_client("https://example.com"))

    @patch("src.seu_auth.SEUAuthManager")
    def test_returns_client_on_success(self, mock_sdk_cls: MagicMock) -> None:
        """登录成功时应返回 (client, redirect_url)。"""
        mock_mgr = MagicMock(spec=CampusAuthManager)
        mock_mgr.get_credentials.return_value = ("213000001", "secret")

        mock_client = MagicMock()
        mock_sdk = AsyncMock()
        mock_sdk.__aenter__ = AsyncMock(return_value=mock_sdk)
        mock_sdk.__aexit__ = AsyncMock(return_value=False)
        mock_sdk.login = AsyncMock(return_value=(mock_client, "https://redirect.url"))
        mock_sdk_cls.return_value = mock_sdk

        wrapper = SEUAuthWrapper(auth_manager=mock_mgr)

        client, url = asyncio.run(
            wrapper.get_authenticated_client("https://example.com")
        )

        assert client is mock_client
        assert url == "https://redirect.url"
        mock_sdk_cls.assert_called_once_with(username="213000001", password="secret")

    @patch("src.seu_auth.SEUAuthManager")
    def test_raises_auth_failed_on_sdk_exception(self, mock_sdk_cls: MagicMock) -> None:
        """SDK 抛出异常时应封装为 AuthFailedError。"""
        mock_mgr = MagicMock(spec=CampusAuthManager)
        mock_mgr.get_credentials.return_value = ("213000001", "secret")

        mock_sdk = AsyncMock()
        mock_sdk.__aenter__ = AsyncMock(return_value=mock_sdk)
        mock_sdk.__aexit__ = AsyncMock(return_value=False)
        mock_sdk.login = AsyncMock(side_effect=RuntimeError("network error"))
        mock_sdk_cls.return_value = mock_sdk

        wrapper = SEUAuthWrapper(auth_manager=mock_mgr)

        with pytest.raises(AuthFailedError, match="CAS 登录失败"):
            asyncio.run(wrapper.get_authenticated_client("https://example.com"))

    def test_close_without_open(self) -> None:
        """未打开连接时 close 不应抛异常。"""
        wrapper = SEUAuthWrapper()
        asyncio.run(wrapper.close())  # should not raise

    @patch("src.seu_auth.SEUAuthManager")
    def test_verify_returns_true_on_success(self, mock_sdk_cls: MagicMock) -> None:
        """凭证有效时 verify() 应返回 True。"""
        mock_mgr = MagicMock(spec=CampusAuthManager)
        mock_mgr.get_credentials.return_value = ("213000001", "secret")

        mock_client = MagicMock()
        mock_sdk = AsyncMock()
        mock_sdk.__aenter__ = AsyncMock(return_value=mock_sdk)
        mock_sdk.__aexit__ = AsyncMock(return_value=False)
        mock_sdk.login = AsyncMock(return_value=(mock_client, None))
        mock_sdk_cls.return_value = mock_sdk

        wrapper = SEUAuthWrapper(auth_manager=mock_mgr)
        assert asyncio.run(wrapper.verify()) is True

    def test_verify_returns_false_when_no_credentials(self) -> None:
        """本地无凭证时 verify() 应返回 False。"""
        mock_mgr = MagicMock(spec=CampusAuthManager)
        mock_mgr.get_credentials.return_value = None

        wrapper = SEUAuthWrapper(auth_manager=mock_mgr)
        assert asyncio.run(wrapper.verify()) is False

    @patch("src.seu_auth.SEUAuthManager")
    def test_verify_returns_false_on_auth_failed(self, mock_sdk_cls: MagicMock) -> None:
        """CAS 登录失败时 verify() 应返回 False。"""
        mock_mgr = MagicMock(spec=CampusAuthManager)
        mock_mgr.get_credentials.return_value = ("213000001", "wrong")

        mock_sdk = AsyncMock()
        mock_sdk.__aenter__ = AsyncMock(return_value=mock_sdk)
        mock_sdk.__aexit__ = AsyncMock(return_value=False)
        mock_sdk.login = AsyncMock(return_value=(None, None))
        mock_sdk_cls.return_value = mock_sdk

        wrapper = SEUAuthWrapper(auth_manager=mock_mgr)
        assert asyncio.run(wrapper.verify()) is False
