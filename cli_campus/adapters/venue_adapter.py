"""场馆预约适配器 — 对接 dndxyyg.seu.edu.cn 预约系统。

认证流程 (OIDC):
1. CAS 登录 → dndxyyg SSO 建立会话。
2. OIDC implicit flow → access_token (Bearer)。
3. GraphQL API 调用 (authenticated)。

与 ehall 适配器不同，此系统使用 OIDC 而非 ehall 三阶段 CAS。
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import urllib.parse
from typing import Any

import httpx

from cli_campus.core.exceptions import AdapterError, AuthFailedError, AuthRequiredError
from cli_campus.core.interfaces import BaseCampusAdapter
from cli_campus.core.models import (
    AdapterSource,
    BookingInfo,
    CampusEvent,
    EventCategory,
    TimeSlotInfo,
    VenueInfo,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://dndxyyg.seu.edu.cn"
_GQL_ENDPOINT = f"{_BASE_URL}/bus/graphql/apps_yy_sys"
_OIDC_CLIENT_ID = "ePmSCRT2MsHl7ZdSxlbL"
_OIDC_SCOPES = "data openid process task app submit process_edit start profile"

# 校区编号前缀 → 校区名称
_CAMPUS_MAP: dict[str, str] = {
    "JLH": "九龙湖",
    "SPL": "四牌楼",
    "DJQ": "丁家桥",
    "WX": "无锡",
}


def _infer_campus(number: str) -> str:
    """从场馆编号推断校区名称。"""
    for prefix, campus in _CAMPUS_MAP.items():
        if number.upper().startswith(prefix):
            return campus
    return ""


class VenueAdapter(BaseCampusAdapter):
    """场馆预约适配器 — 查询场馆、时段、预约与取消。

    通过 OIDC implicit flow 获取 Bearer token，
    调用 GraphQL API 完成所有场馆预约操作。
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config or {})
        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # OIDC 认证
    # ------------------------------------------------------------------

    async def _ensure_token(self) -> str:
        """确保持有有效的 OIDC access_token，必要时执行完整认证流程。"""
        if self._token:
            return self._token

        from cli_campus.core.auth import CampusAuthManager

        try:
            from src.seu_auth import SEUAuthManager
        except ImportError as exc:
            raise AuthFailedError("seu-auth SDK 未安装") from exc

        mgr = CampusAuthManager()
        creds = mgr.get_credentials()
        if creds is None:
            raise AuthRequiredError

        username, password = creds
        manager = SEUAuthManager(username=username, password=password)

        try:
            await manager.__aenter__()
            service_url = (
                f"{_BASE_URL}/sso/login?"
                f"redirect_uri={urllib.parse.quote(_BASE_URL + '/sso/success')}"
                f"&x_client=cas"
            )
            auth_client, redirect_url = await manager.login(service=service_url)

            # 清理 SDK 遗留的请求头 (会导致 403)
            for key in ("origin", "referer", "content-type"):
                if key in auth_client.headers:
                    del auth_client.headers[key]

            # 建立 SSO 会话
            await auth_client.get(redirect_url, follow_redirects=True)

            # OIDC authorize → token in redirect fragment
            callback_url = (
                f"{_BASE_URL}/yy-sys/oidc-callback?"
                f"retUrl={urllib.parse.quote(_BASE_URL + '/yy-sys/')}"
            )
            resp = await auth_client.get(
                f"{_BASE_URL}/sso/oauth2/authorize",
                params={
                    "client_id": _OIDC_CLIENT_ID,
                    "redirect_uri": callback_url,
                    "response_type": "id_token token",
                    "scope": _OIDC_SCOPES,
                    "nonce": hashlib.sha256(
                        str(datetime.datetime.now().timestamp()).encode()
                    ).hexdigest()[:16],
                },
                follow_redirects=False,
            )

            location = resp.headers.get("location", "")
            fragment = urllib.parse.urlparse(location).fragment
            params = urllib.parse.parse_qs(fragment)
            token_list = params.get("access_token")
            if not token_list:
                raise AdapterError(
                    f"OIDC 未返回 access_token (status={resp.status_code})"
                )
            self._token = token_list[0]

        except (AuthRequiredError, AuthFailedError, AdapterError):
            raise
        except Exception as exc:
            raise AuthFailedError(f"场馆系统认证失败: {exc}") from exc
        finally:
            await manager.__aexit__(None, None, None)

        logger.info("场馆系统 OIDC 认证成功")
        return self._token

    async def _get_client(self) -> httpx.AsyncClient:
        """获取带 Bearer token 的 httpx 客户端。"""
        if self._client is None:
            self._client = httpx.AsyncClient(verify=False, timeout=30)
        return self._client

    async def close(self) -> None:
        """关闭 httpx 客户端。"""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # GraphQL 通用
    # ------------------------------------------------------------------

    async def _gql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """执行 GraphQL 请求并返回 data 部分。"""
        token = await self._ensure_token()
        client = await self._get_client()

        body: dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables

        resp = await client.post(
            _GQL_ENDPOINT,
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )

        if resp.status_code != 200:
            raise AdapterError(f"GraphQL 请求失败 (HTTP {resp.status_code})")

        result = resp.json()
        if "errors" in result and result["errors"]:
            first_error = result["errors"][0].get("message", "Unknown error")
            raise AdapterError(f"GraphQL 错误: {first_error}")

        return result.get("data", {})

    # ------------------------------------------------------------------
    # 公共 API — 查询场馆
    # ------------------------------------------------------------------

    async def get_venues(self, type_name: str = "羽毛球场") -> list[VenueInfo]:
        """获取指定类型的所有场馆列表。

        Args:
            type_name: 场馆类型名称 (如 "羽毛球场"、"网球场"、"篮球馆")。

        Returns:
            VenueInfo 列表。
        """
        query = """query($typeName: String!) {
          findResourcesAllByAccount(typeName: $typeName) {
            id resources_name resources_number resources_type_name
            state capacity
          }
        }"""
        data = await self._gql(query, {"typeName": type_name})
        resources = data.get("findResourcesAllByAccount", [])

        venues = []
        for r in resources:
            number = r.get("resources_number", "") or ""
            venues.append(
                VenueInfo(
                    venue_id=r["id"],
                    name=r.get("resources_name", ""),
                    number=number,
                    type_name=r.get("resources_type_name", ""),
                    campus=_infer_campus(number),
                    capacity=r.get("capacity") or 0
                    if isinstance(r.get("capacity"), int)
                    else int(r.get("capacity", 0) or 0),
                    state=r.get("state", 0) or 0,
                )
            )
        return venues

    # ------------------------------------------------------------------
    # 公共 API — 查询时段
    # ------------------------------------------------------------------

    async def get_time_slots(self, venue_id: str, date: str) -> list[TimeSlotInfo]:
        """获取指定场馆在指定日期的时间段列表。

        Args:
            venue_id: 场馆 UUID。
            date: 日期 (YYYY-MM-DD 格式)。

        Returns:
            TimeSlotInfo 列表 (按时间排序)。
        """
        # 转换日期为毫秒时间戳 (GraphQL Date! 类型要求)
        dt = datetime.datetime.strptime(date, "%Y-%m-%d")
        ts_ms = int(dt.timestamp() * 1000)

        query = """query($resId: String!, $date: Date!) {
          findResourcesTimeSlotByResourcesIdAndDate(
            resourcesId: $resId, date: $date
          ) {
            id kssj jssj canAppointmentNumber canAppointmentNumberDesc
          }
        }"""
        data = await self._gql(query, {"resId": venue_id, "date": ts_ms})
        slots_raw = data.get("findResourcesTimeSlotByResourcesIdAndDate", [])

        slots = []
        for s in slots_raw:
            slots.append(
                TimeSlotInfo(
                    slot_id=s.get("id", ""),
                    start_time=s.get("kssj", ""),
                    end_time=s.get("jssj", ""),
                    available=s.get("canAppointmentNumber", 0) or 0,
                    status_text=s.get("canAppointmentNumberDesc", ""),
                    venue_id=venue_id,
                    date=date,
                )
            )
        return slots

    # ------------------------------------------------------------------
    # 公共 API — 预约
    # ------------------------------------------------------------------

    async def make_booking(
        self,
        venue_id: str,
        date: str,
        start_time: str,
        end_time: str,
        event: str = "运动健身",
    ) -> BookingInfo:
        """提交场馆预约。

        Args:
            venue_id: 场馆 UUID。
            date: 日期 (YYYY-MM-DD)。
            start_time: 开始时间 (HH:MM)。
            end_time: 结束时间 (HH:MM)。
            event: 活动名称 (默认 "运动健身")。

        Returns:
            BookingInfo — 创建成功的预约信息。

        Raises:
            AdapterError: 预约失败 (已满 / 时段冲突 / 服务端拒绝)。
        """
        dt = datetime.datetime.strptime(date, "%Y-%m-%d")
        ts_ms = int(dt.timestamp() * 1000)

        mutation = """mutation($model: InputAppointmentInformation!) {
          saveAppointmentInformation(model: $model) {
            id resources_name resources_type_name
            appointment_date start_time end_time state event
          }
        }"""
        model: dict[str, Any] = {
            "resources_id": venue_id,
            "appointment_date": ts_ms,
            "start_time": start_time,
            "end_time": end_time,
            "event": event,
        }
        data = await self._gql(mutation, {"model": model})
        result = data.get("saveAppointmentInformation")
        if not result:
            raise AdapterError("预约提交失败，服务端未返回预约信息")

        # 解析 appointment_date (可能是时间戳)
        appt_date = result.get("appointment_date")
        if isinstance(appt_date, (int, float)):
            date_str = datetime.datetime.fromtimestamp(appt_date / 1000).strftime(
                "%Y-%m-%d"
            )
        else:
            date_str = str(appt_date or date)

        return BookingInfo(
            booking_id=result.get("id", ""),
            venue_name=result.get("resources_name", ""),
            venue_type=result.get("resources_type_name", ""),
            date=date_str,
            start_time=result.get("start_time", ""),
            end_time=result.get("end_time", ""),
            state=result.get("state", 0) or 0,
            event=result.get("event", ""),
        )

    # ------------------------------------------------------------------
    # 公共 API — 取消预约
    # ------------------------------------------------------------------

    async def cancel_booking(self, booking_id: str, reason: str = "") -> bool:
        """取消指定预约。

        Args:
            booking_id: 预约 ID。
            reason: 取消原因 (可选)。

        Returns:
            True 表示取消成功。
        """
        mutation = """mutation($id: ID!, $state: String!) {
          updateAppointmentInformationState(id: $id, state: $state, reason: $reason) {
            id state
          }
        }"""
        # 使用直接的变量替换方式
        mutation = """mutation($id: ID!, $state: String!, $reason: String) {
          updateAppointmentInformationState(id: $id, state: $state, reason: $reason) {
            id state
          }
        }"""
        data = await self._gql(
            mutation, {"id": booking_id, "state": "2", "reason": reason}
        )
        result = data.get("updateAppointmentInformationState")
        return result is not None

    # ------------------------------------------------------------------
    # 公共 API — 我的预约
    # ------------------------------------------------------------------

    async def get_my_bookings(self) -> list[BookingInfo]:
        """获取当前用户的所有预约记录。

        Returns:
            BookingInfo 列表。
        """
        query = """query {
          findAppointmentInformationAllForSelf {
            edges {
              node {
                id resources_name resources_type_name
                appointment_date start_time end_time state event
              }
            }
          }
        }"""
        data = await self._gql(query)
        edges = data.get("findAppointmentInformationAllForSelf", {}).get("edges", [])

        bookings = []
        for edge in edges:
            node = edge.get("node", {})
            appt_date = node.get("appointment_date")
            if isinstance(appt_date, (int, float)):
                date_str = datetime.datetime.fromtimestamp(appt_date / 1000).strftime(
                    "%Y-%m-%d"
                )
            else:
                date_str = str(appt_date or "")

            bookings.append(
                BookingInfo(
                    booking_id=node.get("id", ""),
                    venue_name=node.get("resources_name", ""),
                    venue_type=node.get("resources_type_name", ""),
                    date=date_str,
                    start_time=node.get("start_time", ""),
                    end_time=node.get("end_time", ""),
                    state=node.get("state", 0) or 0,
                    event=node.get("event", ""),
                )
            )
        return bookings

    # ------------------------------------------------------------------
    # 便捷方法 — 获取当前时间 (原子操作)
    # ------------------------------------------------------------------

    @staticmethod
    def get_current_time() -> datetime.datetime:
        """获取当前时间 — 原子操作，供定时预约使用。

        Returns:
            当前本地时间 (datetime.datetime)。
        """
        return datetime.datetime.now()

    # ------------------------------------------------------------------
    # BaseCampusAdapter 协议方法
    # ------------------------------------------------------------------

    async def check_auth(self) -> bool:
        """验证 OIDC 认证是否可用。"""
        try:
            await self._ensure_token()
            return True
        except (AuthRequiredError, AuthFailedError):
            return False

    async def fetch(self, **kwargs: Any) -> list[CampusEvent]:
        """拉取场馆时段数据并返回标准化 CampusEvent 列表。

        Kwargs:
            type_name (str): 场馆类型名称 (默认 "羽毛球场")。
            date (str): 查询日期 (YYYY-MM-DD，默认明天)。
            campus (str): 筛选校区 (如 "九龙湖")。

        Returns:
            CampusEvent 列表，每条代表一个可查看的时段信息。
        """
        type_name = kwargs.get("type_name", "羽毛球场")
        date = kwargs.get("date") or (
            datetime.date.today() + datetime.timedelta(days=1)
        ).strftime("%Y-%m-%d")
        campus_filter = kwargs.get("campus", "")

        venues = await self.get_venues(type_name)
        if campus_filter:
            venues = [
                v
                for v in venues
                if campus_filter in v.campus or campus_filter in v.name
            ]

        events: list[CampusEvent] = []
        for venue in venues:
            try:
                slots = await self.get_time_slots(venue.venue_id, date)
            except AdapterError:
                logger.warning("获取 %s 时段失败，跳过", venue.name)
                continue

            for slot in slots:
                event_id = f"seu_venue:{venue.venue_id}:{date}:{slot.start_time}"
                events.append(
                    CampusEvent(
                        id=event_id,
                        source=AdapterSource.SEU_VENUE,
                        category=EventCategory.ROOM,
                        title=(
                            f"{venue.name} {slot.start_time}-"
                            f"{slot.end_time} ({slot.status_text})"
                        ),
                        content={
                            "venue": venue.model_dump(),
                            "slot": slot.model_dump(),
                        },
                    )
                )

        return events
