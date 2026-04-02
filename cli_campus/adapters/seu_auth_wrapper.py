"""SEU-Auth SDK 包装器 — 解耦核心逻辑与外部认证 SDK。

将 SEU-Auth (https://github.com/Golevka2001/SEU-Auth) 的 ``SEUAuthManager``
封装为 CLI-Campus 内部的 ``SEUAuthWrapper``，使上层 Adapter 和 CLI 命令
不直接依赖第三方 SDK 的具体 API。

核心职责：
1. 从 ``CampusAuthManager`` 获取本地凭证。
2. 使用 SEU-Auth SDK 执行 CAS 登录。
3. 返回已认证的 ``httpx.AsyncClient`` 供 Adapter 复用。
4. 凭证不存在时抛出 ``AuthRequiredError``。
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from cli_campus.core.auth import CampusAuthManager
from cli_campus.core.exceptions import AuthFailedError, AuthRequiredError

logger = logging.getLogger(__name__)

# SDK 内部 logger 名称，用于在 verify 时临时静默
_SDK_LOGGER_NAME: str = "src.seu_auth"


class SEUAuthWrapper:
    """SEU-Auth SDK 的封装层 — 提供透明的认证会话获取能力。

    Adapter 调用 ``get_authenticated_client()`` 即可获得一个
    已通过 CAS 认证的 ``httpx.AsyncClient``，无需了解底层登录细节。

    Example:
        >>> wrapper = SEUAuthWrapper()
        >>> async with wrapper.get_authenticated_client("https://...") as client:
        ...     resp = await client.get("https://...")
    """

    def __init__(
        self,
        auth_manager: Optional[CampusAuthManager] = None,
    ) -> None:
        self._auth_manager = auth_manager or CampusAuthManager()
        self._manager_instance: object | None = None

    async def get_authenticated_client(
        self,
        service_url: str,
    ) -> tuple[httpx.AsyncClient, str | None]:
        """获取已通过 CAS 认证的 httpx 异步客户端。

        Args:
            service_url: 目标服务的 CAS service URL。

        Returns:
            ``(httpx_client, redirect_url)`` 元组。
            ``httpx_client`` 已携带完整的认证 Cookie，可直接请求校内服务。
            ``redirect_url`` 为登录后服务端返回的重定向地址（可能为 ``None``）。

        Raises:
            AuthRequiredError: 本地未保存凭证。
            AuthFailedError: CAS 登录流程失败。
        """
        credentials = self._auth_manager.get_credentials()
        if credentials is None:
            raise AuthRequiredError

        username, password = credentials

        try:
            from src.seu_auth import SEUAuthManager
        except ImportError as exc:
            raise AuthFailedError(
                "seu-auth SDK 未安装，请执行: uv add seu-auth"
            ) from exc

        manager = SEUAuthManager(username=username, password=password)
        self._manager_instance = manager

        try:
            await manager.__aenter__()
            client, redirect_url = await manager.login(service=service_url)
        except Exception as exc:
            await self._close_manager()
            raise AuthFailedError(f"CAS 登录失败: {exc}") from exc

        if client is None:
            await self._close_manager()
            raise AuthFailedError("CAS 登录失败，请检查学号和密码是否正确。")

        logger.info("CAS 认证成功 (user=%s)", username)
        return client, redirect_url

    async def verify(self, service_url: str = "") -> bool:
        """验证已保存的凭证是否能通过 CAS 认证。

        执行一次完整的 CAS 登录流程，成功返回 ``True``，
        否则返回 ``False``。无论结果如何，均会自动释放底层连接。

        验证过程中会临时静默 SDK 内部日志，避免重试噪声输出到终端。

        Args:
            service_url: 用于验证的 CAS service URL。
                留空则仅验证 CAS 凭证本身，不携带 service 参数。

        Returns:
            ``True`` 凭证有效且 CAS 登录成功；``False`` 反之。
        """
        credentials = self._auth_manager.get_credentials()
        if credentials is None:
            return False

        username, password = credentials

        try:
            from src.seu_auth import SEUAuthManager
        except ImportError:
            return False

        # 临时提高 SDK logger 级别，抑制内部重试产生的 error 日志
        sdk_logger = logging.getLogger(_SDK_LOGGER_NAME)
        original_level = sdk_logger.level
        sdk_logger.setLevel(logging.CRITICAL)

        manager = SEUAuthManager(
            username=username, password=password, max_step_retries=1
        )
        self._manager_instance = manager

        try:
            await manager.__aenter__()
            client, _ = await manager.login(service=service_url)
            return client is not None
        except Exception:
            return False
        finally:
            sdk_logger.setLevel(original_level)
            await self.close()

    async def close(self) -> None:
        """关闭底层 SEUAuthManager 及其 httpx client。"""
        await self._close_manager()

    async def _close_manager(self) -> None:
        """安全关闭 SEUAuthManager 实例。"""
        if self._manager_instance is not None:
            try:
                await self._manager_instance.__aexit__(None, None, None)  # type: ignore[union-attr]
            except Exception:
                logger.debug("关闭 SEUAuthManager 时出现异常", exc_info=True)
            finally:
                self._manager_instance = None
