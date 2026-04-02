"""Tests for custom exception hierarchy."""

from __future__ import annotations

from cli_campus.core.exceptions import (
    AdapterError,
    AuthFailedError,
    AuthRequiredError,
    CampusError,
)


class TestExceptions:
    """异常体系测试。"""

    def test_hierarchy(self) -> None:
        """所有自定义异常都应是 CampusError 的子类。"""
        assert issubclass(AuthRequiredError, CampusError)
        assert issubclass(AuthFailedError, CampusError)
        assert issubclass(AdapterError, CampusError)

    def test_auth_required_default_message(self) -> None:
        exc = AuthRequiredError()
        assert "campus auth login" in str(exc)

    def test_auth_failed_default_message(self) -> None:
        exc = AuthFailedError()
        assert "认证失败" in str(exc)

    def test_auth_failed_custom_message(self) -> None:
        exc = AuthFailedError("自定义错误消息")
        assert str(exc) == "自定义错误消息"

    def test_adapter_error_default_message(self) -> None:
        exc = AdapterError()
        assert "适配器" in str(exc)
