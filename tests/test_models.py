"""Tests for core Pydantic models."""

from __future__ import annotations

from datetime import datetime

from cli_campus.core.models import (
    AdapterSource,
    BusRoute,
    CampusEvent,
    CourseInfo,
    EventCategory,
    TaskItem,
)


class TestCampusEvent:
    """CampusEvent 模型测试。"""

    def test_create_minimal_event(self) -> None:
        event = CampusEvent(
            id="test:course:001",
            source=AdapterSource.MOCK,
            category=EventCategory.COURSE,
            title="测试事件",
        )
        assert event.id == "test:course:001"
        assert event.source == AdapterSource.MOCK
        assert event.category == EventCategory.COURSE
        assert event.content == {}
        assert event.raw_data is None

    def test_create_full_event(self) -> None:
        ts = datetime(2026, 3, 1, 8, 0, 0)
        event = CampusEvent(
            id="test:course:002",
            source=AdapterSource.ZHENGFANG,
            category=EventCategory.COURSE,
            title="高等数学 A",
            content={"name": "高等数学 A", "teacher": "张三"},
            raw_data={"html": "<tr>...</tr>"},
            timestamp=ts,
        )
        assert event.content["teacher"] == "张三"
        assert event.raw_data is not None
        assert event.timestamp == ts

    def test_event_json_serialization(self) -> None:
        event = CampusEvent(
            id="test:bus:001",
            source=AdapterSource.STATIC_JSON,
            category=EventCategory.BUS,
            title="校车时刻",
        )
        json_str = event.model_dump_json()
        assert "test:bus:001" in json_str

        restored = CampusEvent.model_validate_json(json_str)
        assert restored.id == event.id
        assert restored.source == event.source


class TestCourseInfo:
    """CourseInfo 模型测试。"""

    def test_create_course(self) -> None:
        course = CourseInfo(
            name="算法设计与分析",
            teacher="方效林",
            location="教四-103",
            day_of_week=3,
            periods="3-4",
            weeks="1-8周",
            raw_schedule_info="1-8周 星期三 3-4节 教四-103",
        )
        assert course.name == "算法设计与分析"
        assert course.day_of_week == 3
        assert course.periods == "3-4"
        assert course.weeks == "1-8周"

    def test_course_day_of_week_validation(self) -> None:
        import pytest

        with pytest.raises(Exception):
            CourseInfo(
                name="X",
                day_of_week=0,  # invalid: must be 1~7
                periods="1-2",
            )

        with pytest.raises(Exception):
            CourseInfo(
                name="X",
                day_of_week=8,  # invalid: must be 1~7
                periods="1-2",
            )


class TestBusRoute:
    """BusRoute 模型测试。"""

    def test_create_bus_route(self) -> None:
        route = BusRoute(
            route_name="九龙湖 → 四牌楼",
            departure_time="07:30",
            departure_stop="九龙湖西门",
            arrival_stop="四牌楼校区",
        )
        assert route.route_name == "九龙湖 → 四牌楼"
        assert route.departure_time == "07:30"


class TestTaskItem:
    """TaskItem 模型测试。"""

    def test_create_task(self) -> None:
        task = TaskItem(
            task_id="cx-001",
            platform="学习通",
            course_name="大学物理",
            title="第三章作业",
            deadline=datetime(2026, 4, 15, 23, 59, 59),
        )
        assert task.platform == "学习通"
        assert not task.is_completed
        assert task.deadline is not None
