"""安全凭证保险库 — 基于 OS Keyring 的本地凭证管理。

使用操作系统原生的凭证管理器（Windows Credential Manager / macOS Keychain /
Linux Secret Service）安全存储用户的学号和密码，避免明文存储在配置文件中。
"""

from __future__ import annotations

import keyring

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_SERVICE_NAME: str = "cli-campus"
_USERNAME_KEY: str = "cli-campus-username"


class CampusAuthManager:
    """本地凭证管理器 — 对 keyring 库的轻量封装。

    职责边界：
    - 仅负责凭证的存储、读取和清除。
    - **不**负责网络认证流程（那是 ``SEUAuthWrapper`` 的职责）。

    Example:
        >>> mgr = CampusAuthManager()
        >>> mgr.save_credentials("213000001", "my_password")
        >>> mgr.get_credentials()
        ('213000001', 'my_password')
        >>> mgr.clear_credentials()
        >>> mgr.get_credentials() is None
        True
    """

    def __init__(self, service_name: str = _SERVICE_NAME) -> None:
        self._service = service_name

    def save_credentials(self, username: str, password: str) -> None:
        """将学号和密码安全存入操作系统凭证管理器。

        Args:
            username: 一卡通号 / 学号。
            password: 统一身份认证密码。
        """
        # 先存用户名（以独立 key 的形式），再存密码
        keyring.set_password(self._service, _USERNAME_KEY, username)
        keyring.set_password(self._service, username, password)

    def get_credentials(self) -> tuple[str, str] | None:
        """从操作系统凭证管理器读取已保存的学号和密码。

        Returns:
            ``(username, password)`` 元组；如果未保存过凭证则返回 ``None``。
        """
        username = keyring.get_password(self._service, _USERNAME_KEY)
        if username is None:
            return None

        password = keyring.get_password(self._service, username)
        if password is None:
            return None

        return (username, password)

    def clear_credentials(self) -> None:
        """从操作系统凭证管理器中清除已保存的凭证。"""
        username = keyring.get_password(self._service, _USERNAME_KEY)
        if username is not None:
            try:
                keyring.delete_password(self._service, username)
            except keyring.errors.PasswordDeleteError:
                pass
            try:
                keyring.delete_password(self._service, _USERNAME_KEY)
            except keyring.errors.PasswordDeleteError:
                pass
