"""课程表适配器 — 查询本学期课程安排。

通过 ``EhallBaseAdapter`` 三阶段认证，
向教务系统 ehall 接口发起请求并返回标准化的 CampusEvent 列表。
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from hashlib import md5
from typing import Any

from cli_campus.adapters.ehall_base import EhallBaseAdapter
from cli_campus.adapters.seu_auth_wrapper import SEUAuthWrapper
from cli_campus.core.exceptions import AdapterError
from cli_campus.core.models import (
    AdapterSource,
    CampusEvent,
    CourseInfo,
    EventCategory,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

_WEEK_RANGE_RE = re.compile(r"(\d+)(?:-(\d+))?")


def parse_weeks(weeks_str: str) -> set[int]:
    """解析周次描述字符串为整数集合。

    支持格式: ``"1-16周"``, ``"1-8周,10-16周"``, ``"1,3,5,7周"`` 等。
    """
    result: set[int] = set()
    for m in _WEEK_RANGE_RE.finditer(weeks_str):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        result.update(range(start, end + 1))
    return result


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_DAY_NAMES: dict[int, str] = {
    1: "周一",
    2: "周二",
    3: "周三",
    4: "周四",
    5: "周五",
    6: "周六",
    7: "周日",
}

_SEMESTER_NAMES: dict[str, str] = {"1": "暑期学校", "2": "秋季", "3": "春季"}


def compute_current_semester(d: date | None = None) -> str:
    """根据日期推算当前 SEU 学年学期代码 (XNXQDM)。

    SEU 三学期制（学期编号与自然顺序不同）：
    - 暑期学校 (T=1)：7 月 ~ 8 月，归入 **下一学年**
    - 秋季学期 (T=2)：9 月 ~ 次年 1 月
    - 春季学期 (T=3)：2 月 ~ 6 月

    Returns:
        形如 ``"2025-2026-3"`` 的学期代码。
    """
    if d is None:
        d = date.today()

    month = d.month
    year = d.year

    if 7 <= month <= 8:
        # 暑期学校归入下一学年
        return f"{year}-{year + 1}-1"
    elif month >= 9:
        # 秋季学期
        return f"{year}-{year + 1}-2"
    elif month == 1:
        # 秋季学期考试周
        return f"{year - 1}-{year}-2"
    else:  # 2-6
        # 春季学期
        return f"{year - 1}-{year}-3"


class CourseAdapter(EhallBaseAdapter):
    """课程表适配器 — 查询本学期课表。

    继承 ``EhallBaseAdapter`` 三阶段认证，
    通过 ``xskcb.do`` 端点获取学生课程表 JSON 数据。

    config 参数（可选）：
        semester: 学年学期代码（如 ``"2025-2026-3"``）。
    """

    _APP_ID: str = "4770397878132218"
    _API_PATH: str = "xskcb/xskcb.do"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        auth_wrapper: SEUAuthWrapper | None = None,
    ) -> None:
        super().__init__(config=config, auth_wrapper=auth_wrapper)
        self._semester: str = self.config.get("semester", compute_current_semester())

    def _module_name(self) -> str:
        return "wdkb"

    async def fetch(self, **kwargs: Any) -> list[CampusEvent]:
        """拉取课程表数据并封装为 CampusEvent 列表。

        Keyword Args:
            semester: 可覆盖默认学期代码。

        Raises:
            AuthRequiredError: 本地无凭证。
            AuthFailedError: CAS 登录失败。
            AdapterError: API 请求失败。
        """
        semester = kwargs.get("semester", self._semester)
        raw_data = await self._post_api(data={"XNXQDM": semester})
        return self._parse_response(raw_data)

    # ------------------------------------------------------------------
    # 内部解析
    # ------------------------------------------------------------------

    def _parse_response(self, raw: dict[str, Any]) -> list[CampusEvent]:
        """将 ehall 接口原始 JSON 解析为 CampusEvent 列表。"""
        try:
            rows: list[dict[str, Any]] = raw["datas"]["xskcb"]["rows"]
        except (KeyError, TypeError) as exc:
            raise AdapterError(f"课程表响应格式异常: {exc}") from exc

        events: list[CampusEvent] = []
        for row in rows:
            course = self._row_to_course(row)
            day_label = _DAY_NAMES.get(course.day_of_week, f"第{course.day_of_week}天")

            event_hash = md5(
                f"{course.name}:{course.day_of_week}:{course.periods}:{course.weeks}".encode()
            ).hexdigest()[:12]

            events.append(
                CampusEvent(
                    id=f"seu_ehall:course:{event_hash}",
                    source=AdapterSource.SEU_EHALL,
                    category=EventCategory.COURSE,
                    title=f"{course.name} — {day_label} {course.periods} 节",
                    content=course.model_dump(),
                    raw_data=row,
                    timestamp=datetime.now(),
                )
            )

        return events

    @staticmethod
    def _row_to_course(row: dict[str, Any]) -> CourseInfo:
        """将单行 API 数据映射为 CourseInfo 模型。"""
        start = str(row.get("KSJC") or "")
        end = str(row.get("JSJC") or "")
        periods = f"{start}-{end}" if start and end else start or end

        day_raw = row.get("SKXQ")
        try:
            day_of_week = int(day_raw)
        except (TypeError, ValueError):
            day_of_week = 1  # fallback

        return CourseInfo(
            name=row.get("KCM") or "未知课程",
            teacher=row.get("SKJS") or "",
            location=row.get("JASMC") or "",
            day_of_week=day_of_week,
            periods=periods,
            weeks=row.get("ZCMC") or "",
            raw_schedule_info=row.get("YPSJDD") or "",
        )
