"""ehall 教务应用基座 — 封装三阶段 CAS 认证流程。

所有依赖 ``ehall.seu.edu.cn/jwapp`` 的教务适配器都应继承此基类，
只需指定 ``_APP_ID`` 和 ``_API_PATH``，即可复用平台登录 → appShow 授权
→ 应用 CAS 登录的完整认证链路。

三阶段认证流程：

1. **平台认证**：CAS 登录 ``ehall.seu.edu.cn/login``，
   建立 ehall 平台级会话（``JSESSIONID`` / ``asessionid``）。
2. **应用授权**：GET ``appShow?appId=<_APP_ID>``，
   ehall 平台返回带 ``gid_`` 授权令牌的应用 ``http://`` URL。
3. **应用认证**：以该 URL 为 CAS service 做第二次 CAS 登录，
   建立应用级会话（``GS_SESSIONID`` / ``_WEU``）。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from cli_campus.adapters.seu_auth_wrapper import SEUAuthWrapper
from cli_campus.core.exceptions import AdapterError
from cli_campus.core.interfaces import BaseCampusAdapter

logger = logging.getLogger(__name__)

# Phase-1: CAS service 指向 ehall 平台登录页（非具体应用）
# 注意：必须使用 http:// 而非 https://，后者不在 CAS 白名单中。
_EHALL_PLATFORM_SERVICE: str = (
    "http://ehall.seu.edu.cn/login?service=https://ehall.seu.edu.cn/new/index.html"
)


class EhallBaseAdapter(BaseCampusAdapter):
    """ehall 教务应用基座 — 三阶段 CAS 认证 + API 调用。

    子类只需覆盖类变量：

    - ``_APP_ID``: ehall appShow 所需的应用 ID。
    - ``_API_PATH``: ``modules/`` 下的 API 相对路径（如 ``"cjcx/xscjcx.do"``）。

    以及实现 ``_parse_response()`` 方法。
    """

    _APP_ID: str = ""
    _API_PATH: str = ""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        auth_wrapper: SEUAuthWrapper | None = None,
    ) -> None:
        super().__init__(config=config or {})
        self._auth = auth_wrapper or SEUAuthWrapper()
        self._platform_service: str = self.config.get(
            "platform_service", _EHALL_PLATFORM_SERVICE
        )

    # ------------------------------------------------------------------
    # 三阶段认证
    # ------------------------------------------------------------------

    async def _get_app_client(self) -> tuple[httpx.AsyncClient, SEUAuthWrapper]:
        """执行三阶段认证，返回 ``(应用级 httpx 客户端, wrapper)``。

        调用方负责在完成后调用 ``await wrapper.close()``。
        """
        # Phase 1: CAS → ehall 平台
        platform_client, redirect_url = await self._auth.get_authenticated_client(
            self._platform_service
        )
        try:
            self._clean_client_headers(platform_client)
            if redirect_url:
                resp = await platform_client.get(redirect_url)
                self._check_vpn_redirect(resp)
            logger.debug("Phase 1: ehall 平台登录完成")

            # Phase 2: appShow 获取应用授权 URL
            appshow_url = self.config.get(
                "appshow_url",
                f"https://ehall.seu.edu.cn/appShow?appId={self._APP_ID}",
            )
            resp = await platform_client.get(appshow_url, follow_redirects=False)
            if resp.status_code not in (301, 302, 303, 307):
                raise AdapterError(
                    f"appShow 未返回重定向 (status={resp.status_code})，"
                    "无法获取应用授权 URL"
                )
            app_service_url: str = resp.headers["location"]
            logger.debug("Phase 2: appShow → %s", app_service_url)
        except AdapterError:
            raise
        except Exception as exc:
            raise AdapterError(f"ehall 平台/appShow 请求失败: {exc}") from exc
        finally:
            await self._auth.close()

        # Phase 3: CAS → 应用
        app_wrapper = SEUAuthWrapper()
        app_client, app_redirect_url = await app_wrapper.get_authenticated_client(
            app_service_url
        )
        try:
            self._clean_client_headers(app_client)
            if app_redirect_url:
                resp = await app_client.get(app_redirect_url)
                self._check_vpn_redirect(resp)
            logger.debug("Phase 3: 应用 Session 已初始化")
        except Exception:
            await app_wrapper.close()
            raise

        return app_client, app_wrapper

    async def _post_api(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """三阶段认证后 POST 请求应用 API，返回解析后的 JSON。"""
        app_client, app_wrapper = await self._get_app_client()
        try:
            api_url = self.config.get(
                "api_url",
                f"https://ehall.seu.edu.cn/jwapp/sys/"
                f"{self._module_name()}/modules/{self._API_PATH}",
            )

            response = await app_client.post(api_url, data=data or {})
            response.raise_for_status()
            self._check_vpn_redirect(response)

            raw_text = response.text
            if not raw_text.strip():
                raise AdapterError("API 返回空响应，可能是 Session 初始化失败")
            return response.json()
        except AdapterError:
            raise
        except Exception as exc:
            raise AdapterError(f"API 请求失败: {exc}") from exc
        finally:
            await app_wrapper.close()

    def _module_name(self) -> str:
        """返回 jwapp 模块名，子类可覆盖。"""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 共享工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_client_headers(client: Any) -> None:
        """清理 SDK 遗留的 CAS 请求头。"""
        for key in ("origin", "referer", "content-type"):
            if key in client.headers:
                del client.headers[key]

    @staticmethod
    def _check_vpn_redirect(response: Any) -> None:
        """检测 VPN 重定向。"""
        final_url = str(response.url)
        if "vpn.seu.edu.cn" in final_url:
            raise AdapterError(
                "当前网络无法直接访问 ehall（已被重定向至校园 VPN）。\n"
                "  请先连接校园网络或 VPN 后再试。\n"
                "  提示: 使用 Sangfor/EasyConnect 客户端，"
                "或在校园 WiFi 环境下运行。"
            )

    async def check_auth(self) -> bool:
        """验证本地凭证是否存在且 CAS 登录可达。"""
        client, _ = await self._auth.get_authenticated_client(self._platform_service)
        await self._auth.close()
        return client is not None
