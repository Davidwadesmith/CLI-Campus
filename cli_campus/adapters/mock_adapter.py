"""Mock Adapter — 用于开发调试和 CI 测试的虚拟适配器。

此适配器不发起任何网络请求，直接返回预设的假数据，
用于验证 Adapter Protocol → CLI 输出的全链路正确性。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from cli_campus.core.interfaces import BaseCampusAdapter
from cli_campus.core.models import (
    AdapterSource,
    CampusEvent,
    CourseInfo,
    EventCategory,
)


class MockAdapter(BaseCampusAdapter):
    """虚拟适配器 — 返回硬编码的测试数据。"""

    async def check_auth(self) -> bool:
        """Mock 永远认证通过。"""
        return True

    async def fetch(self, **kwargs: Any) -> list[CampusEvent]:
        """返回预设的 CampusEvent 列表。"""
        sample_course = CourseInfo(
            name="高等数学 A",
            teacher="张三",
            location="九龙湖教三-302",
            day_of_week=1,
            periods="1-2",
            weeks="1-16周",
            raw_schedule_info="1-16周 星期一 1-2节 九龙湖教三-302",
        )

        event = CampusEvent(
            id="mock:course:demo-001",
            source=AdapterSource.MOCK,
            category=EventCategory.COURSE,
            title="[Mock] 高等数学 A — 周一 1-2 节",
            content=sample_course.model_dump(),
            timestamp=datetime(2026, 3, 1, 8, 0, 0),
        )

        return [event]
