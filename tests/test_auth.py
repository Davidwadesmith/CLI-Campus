"""Tests for CampusAuthManager (keyring-based credential vault)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cli_campus.core.auth import CampusAuthManager


class TestCampusAuthManager:
    """凭证管理器测试 — 使用 mock 替代真实 keyring 调用。"""

    @patch("cli_campus.core.auth.keyring")
    def test_save_credentials(self, mock_keyring: MagicMock) -> None:
        mgr = CampusAuthManager(service_name="test-service")
        mgr.save_credentials("213000001", "secret123")

        assert mock_keyring.set_password.call_count == 2
        mock_keyring.set_password.assert_any_call(
            "test-service", "cli-campus-username", "213000001"
        )
        mock_keyring.set_password.assert_any_call(
            "test-service", "213000001", "secret123"
        )

    @patch("cli_campus.core.auth.keyring")
    def test_get_credentials_exist(self, mock_keyring: MagicMock) -> None:
        mock_keyring.get_password.side_effect = lambda svc, key: {
            "cli-campus-username": "213000001",
            "213000001": "secret123",
        }.get(key)

        mgr = CampusAuthManager(service_name="test-service")
        result = mgr.get_credentials()

        assert result is not None
        assert result == ("213000001", "secret123")

    @patch("cli_campus.core.auth.keyring")
    def test_get_credentials_not_exist(self, mock_keyring: MagicMock) -> None:
        mock_keyring.get_password.return_value = None

        mgr = CampusAuthManager(service_name="test-service")
        result = mgr.get_credentials()

        assert result is None

    @patch("cli_campus.core.auth.keyring")
    def test_get_credentials_password_missing(self, mock_keyring: MagicMock) -> None:
        """用户名存在但密码缺失的情况。"""
        mock_keyring.get_password.side_effect = lambda svc, key: {
            "cli-campus-username": "213000001",
        }.get(key)

        mgr = CampusAuthManager(service_name="test-service")
        result = mgr.get_credentials()

        assert result is None

    @patch("cli_campus.core.auth.keyring")
    def test_clear_credentials(self, mock_keyring: MagicMock) -> None:
        mock_keyring.get_password.return_value = "213000001"

        mgr = CampusAuthManager(service_name="test-service")
        mgr.clear_credentials()

        assert mock_keyring.delete_password.call_count == 2

    @patch("cli_campus.core.auth.keyring")
    def test_clear_credentials_when_empty(self, mock_keyring: MagicMock) -> None:
        """无凭证时 clear 不应抛异常。"""
        mock_keyring.get_password.return_value = None

        mgr = CampusAuthManager(service_name="test-service")
        mgr.clear_credentials()

        mock_keyring.delete_password.assert_not_called()
