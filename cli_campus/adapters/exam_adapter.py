"""考试安排适配器 — 查询考试时间与考场。

通过 ``EhallBaseAdapter`` 三阶段认证，
向 ehall 考试安排应用 (studentWdksapApp) 发起请求并返回标准化的 CampusEvent 列表。
"""

from __future__ import annotations

import logging
from datetime import datetime
from hashlib import md5
from typing import Any

from cli_campus.adapters.ehall_base import EhallBaseAdapter
from cli_campus.adapters.seu_auth_wrapper import SEUAuthWrapper
from cli_campus.core.exceptions import AdapterError
from cli_campus.core.models import (
    AdapterSource,
    CampusEvent,
    EventCategory,
    ExamInfo,
)

logger = logging.getLogger(__name__)


class ExamAdapter(EhallBaseAdapter):
    """考试安排适配器 — 查询指定学期的考试时间与考场信息。

    config 参数（可选）：
        semester: 学年学期代码，默认使用当前学期。
    """

    _APP_ID: str = "4768687067472349"
    _API_PATH: str = "wdksap/wdksap.do"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        auth_wrapper: SEUAuthWrapper | None = None,
    ) -> None:
        super().__init__(config=config, auth_wrapper=auth_wrapper)
        from cli_campus.adapters.course_adapter import compute_current_semester

        self._semester: str = self.config.get("semester", compute_current_semester())

    def _module_name(self) -> str:
        return "studentWdksapApp"

    async def fetch(self, **kwargs: Any) -> list[CampusEvent]:
        """拉取考试安排数据。

        Keyword Args:
            semester: 学期代码。

        Raises:
            AuthRequiredError: 本地无凭证。
            AuthFailedError: CAS 登录失败。
            AdapterError: API 请求失败。
        """
        semester = kwargs.get("semester", self._semester)
        raw_data = await self._post_api(data={"XNXQDM": semester})
        return self._parse_response(raw_data)

    def _parse_response(self, raw: dict[str, Any]) -> list[CampusEvent]:
        """将 API JSON 解析为 CampusEvent 列表。"""
        try:
            rows: list[dict[str, Any]] = raw["datas"]["wdksap"]["rows"]
        except (KeyError, TypeError) as exc:
            raise AdapterError(f"考试安排响应格式异常: {exc}") from exc

        events: list[CampusEvent] = []
        for row in rows:
            exam = self._row_to_exam(row)

            event_hash = md5(
                f"{exam.course_name}:{exam.time_text}:{exam.location}".encode()
            ).hexdigest()[:12]

            events.append(
                CampusEvent(
                    id=f"seu_ehall:exam:{event_hash}",
                    source=AdapterSource.SEU_EHALL,
                    category=EventCategory.EXAM,
                    title=f"{exam.course_name} — {exam.time_text}",
                    content=exam.model_dump(),
                    raw_data=row,
                    timestamp=datetime.now(),
                )
            )

        return events

    @staticmethod
    def _row_to_exam(row: dict[str, Any]) -> ExamInfo:
        """将 API 行数据映射为 ExamInfo。"""
        credit_raw = row.get("XF")
        try:
            credit = float(credit_raw) if credit_raw is not None else 0.0
        except (TypeError, ValueError):
            credit = 0.0

        return ExamInfo(
            course_name=row.get("KCM") or "未知课程",
            time_text=row.get("KSSJMS") or "",
            location=row.get("JASMC") or "",
            seat_number=str(row.get("ZWH") or ""),
            teacher=row.get("ZJJSXM") or "",
            semester=row.get("XNXQDM") or "",
            exam_name=row.get("KSMC") or "",
            credit=credit,
        )
