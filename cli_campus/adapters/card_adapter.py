"""一卡通适配器 — 查询校园卡余额与基本信息。

通过 SEUAuthWrapper 获取已认证的 httpx 客户端，
向校园卡门户发起请求并返回标准化的 CampusEvent。

⚠️  当前一卡通真实接口尚未对接。调用 fetch() 会抛出 AdapterError 提示。
    待确认真实接口地址后可通过 config 的 service_url / api_url 覆盖。
"""

from __future__ import annotations

import logging
from datetime import datetime
from hashlib import md5
from typing import Any

from cli_campus.adapters.seu_auth_wrapper import SEUAuthWrapper
from cli_campus.core.exceptions import AdapterError
from cli_campus.core.interfaces import BaseCampusAdapter
from cli_campus.core.models import (
    AdapterSource,
    CampusEvent,
    CardInfo,
    EventCategory,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量 — 待替换为真实接口
# ---------------------------------------------------------------------------

# 占位 URL — 未对接真实系统前调用会返回明确的错误信息而非 404。
_CARD_SERVICE_URL: str = ""
_CARD_API_URL: str = ""


class CardAdapter(BaseCampusAdapter):
    """一卡通适配器 — 查询校园卡余额与持卡人信息。

    config 参数（可选）：
        service_url: CAS 认证的 service 参数（默认为内置占位 URL）。
        api_url: 一卡通查询 API 地址（默认为内置占位 URL）。
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        auth_wrapper: SEUAuthWrapper | None = None,
    ) -> None:
        super().__init__(config=config or {})
        self._auth = auth_wrapper or SEUAuthWrapper()
        self._service_url: str = self.config.get("service_url", _CARD_SERVICE_URL)
        self._api_url: str = self.config.get("api_url", _CARD_API_URL)

    async def check_auth(self) -> bool:
        """验证本地凭证是否存在且 CAS 登录可达。

        Returns:
            ``True`` 表示可以正常拉取数据。

        Raises:
            AuthRequiredError: 本地无凭证。
            AuthFailedError: CAS 登录失败。
            AdapterError: 真实接口未对接时直接报错。
        """
        if not self._api_url:
            raise AdapterError(
                "一卡通接口尚未对接，当前无法查询。"
                "请在 config 中配置 service_url 和 api_url 后重试。"
            )
        client, _ = await self._auth.get_authenticated_client(self._service_url)
        # 如果走到这里说明认证成功，关闭临时 client
        await self._auth.close()
        return client is not None

    async def fetch(self, **kwargs: Any) -> list[CampusEvent]:
        """拉取一卡通余额数据并封装为 CampusEvent。

        Raises:
            AuthRequiredError: 本地无凭证。
            AuthFailedError: CAS 登录失败。
            AdapterError: API 请求失败或接口未对接。
        """
        if not self._api_url:
            raise AdapterError(
                "一卡通接口尚未对接，当前无法查询余额。"
                "请等待后续版本更新或在 config 中配置真实的 "
                "service_url 和 api_url。"
            )
        client, redirect_url = await self._auth.get_authenticated_client(
            self._service_url
        )

        try:
            # 先访问重定向 URL 完成服务端跳转（如有）
            if redirect_url:
                await client.get(redirect_url)

            response = await client.get(self._api_url)
            response.raise_for_status()
            raw_data = response.json()
        except Exception as exc:
            raise AdapterError(f"一卡通 API 请求失败: {exc}") from exc
        finally:
            await self._auth.close()

        return self._parse_response(raw_data)

    def _parse_response(self, raw: dict[str, Any]) -> list[CampusEvent]:
        """将 API 原始响应解析为 CampusEvent 列表。

        此方法在真实接口确认后需根据实际响应格式调整。
        当前假设响应包含 student_id, name, balance, status 字段。
        """
        card = CardInfo(
            student_id=raw.get("student_id", "unknown"),
            name=raw.get("name", ""),
            balance=float(raw.get("balance", 0.0)),
            status=raw.get("status", "正常"),
        )

        event_id = md5(
            f"card:{card.student_id}:{datetime.now().date()}".encode()
        ).hexdigest()[:12]

        event = CampusEvent(
            id=f"seu_card:card:{event_id}",
            source=AdapterSource.SEU_CARD,
            category=EventCategory.CARD,
            title=f"一卡通余额: ¥{card.balance:.2f}",
            content=card.model_dump(),
            raw_data=raw,
            timestamp=datetime.now(),
        )

        return [event]
