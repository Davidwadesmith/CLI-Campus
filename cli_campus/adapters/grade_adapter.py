"""成绩查询适配器 — 查询学期成绩。

通过 ``EhallBaseAdapter`` 三阶段认证，
向 ehall 成绩查询应用 (cjcx) 发起请求并返回标准化的 CampusEvent 列表。
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
    GradeInfo,
)

logger = logging.getLogger(__name__)


class GradeAdapter(EhallBaseAdapter):
    """成绩查询适配器 — 查询学期或全量成绩。

    config 参数（可选）：
        semester: 学年学期代码，留空则查询全部成绩。
    """

    _APP_ID: str = "4768574631264620"
    _API_PATH: str = "cjcx/xscjcx.do"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        auth_wrapper: SEUAuthWrapper | None = None,
    ) -> None:
        super().__init__(config=config, auth_wrapper=auth_wrapper)
        self._semester: str = self.config.get("semester", "")

    def _module_name(self) -> str:
        return "cjcx"

    async def fetch(self, **kwargs: Any) -> list[CampusEvent]:
        """拉取成绩数据。

        Keyword Args:
            semester: 学期代码，空字符串表示全部学期。

        Raises:
            AuthRequiredError: 本地无凭证。
            AuthFailedError: CAS 登录失败。
            AdapterError: API 请求失败。
        """
        semester = kwargs.get("semester", self._semester)
        raw_data = await self._post_api(data={"XNXQDM": semester, "*order": "-XNXQDM"})
        return self._parse_response(raw_data)

    def _parse_response(self, raw: dict[str, Any]) -> list[CampusEvent]:
        """将 API JSON 解析为 CampusEvent 列表。"""
        try:
            rows: list[dict[str, Any]] = raw["datas"]["xscjcx"]["rows"]
        except (KeyError, TypeError) as exc:
            raise AdapterError(f"成绩响应格式异常: {exc}") from exc

        events: list[CampusEvent] = []
        for row in rows:
            grade = self._row_to_grade(row)

            event_hash = md5(
                f"{grade.course_name}:{grade.semester}:{grade.score}".encode()
            ).hexdigest()[:12]

            events.append(
                CampusEvent(
                    id=f"seu_ehall:grade:{event_hash}",
                    source=AdapterSource.SEU_EHALL,
                    category=EventCategory.GRADE,
                    title=f"{grade.course_name} — {grade.score}",
                    content=grade.model_dump(),
                    raw_data=row,
                    timestamp=datetime.now(),
                )
            )

        return events

    @staticmethod
    def _row_to_grade(row: dict[str, Any]) -> GradeInfo:
        """将 API 行数据映射为 GradeInfo。"""
        score_raw = row.get("ZCJ")
        score = str(score_raw) if score_raw is not None else ""

        credit_raw = row.get("XF")
        try:
            credit = float(credit_raw) if credit_raw is not None else 0.0
        except (TypeError, ValueError):
            credit = 0.0

        gpa_raw = row.get("XFJD")
        try:
            gpa = float(gpa_raw) if gpa_raw is not None else 0.0
        except (TypeError, ValueError):
            gpa = 0.0

        passed_display = row.get("SFJG_DISPLAY") or ""

        return GradeInfo(
            course_name=row.get("KCM") or "未知课程",
            score=score,
            credit=credit,
            gpa=gpa,
            course_type=row.get("KCXZDM_DISPLAY") or "",
            grade_label=row.get("DJCJMC") or "",
            semester=row.get("XNXQDM") or "",
            passed=passed_display != "否",
        )
