"""Tests for BusAdapter."""

from __future__ import annotations

import asyncio

from cli_campus.adapters.bus_adapter import BusAdapter, _schedule_type_label
from cli_campus.core.models import AdapterSource, EventCategory

# ---------------------------------------------------------------------------
# 最小测试数据
# ---------------------------------------------------------------------------

_SAMPLE_DATA: dict = {
    "meta": {
        "version": "2024-11-25",
        "source_url": "https://example.com",
        "last_updated": "2026-01-27",
        "contact": "025-52090448",
    },
    "routes": [
        {
            "name": "九龙湖校园循环巴士",
            "short_name": "循环巴士",
            "campus": "九龙湖",
            "type": "loop",
            "directions": [
                {
                    "from": "图书馆北",
                    "to": "循环线路",
                    "schedules": {
                        "workday": ["07:00", "08:00", "12:00", "18:00"],
                        "holiday": ["09:00", "14:00"],
                    },
                }
            ],
            "notes": ["早高峰坐满即走"],
        },
        {
            "name": "兰台研究生公寓接驳车",
            "short_name": "兰台接驳车",
            "campus": "九龙湖",
            "type": "shuttle",
            "directions": [
                {
                    "from": "兰台",
                    "to": "北门圆盘",
                    "schedules": {"holiday": ["08:00", "10:00"]},
                },
                {
                    "from": "北门圆盘",
                    "to": "兰台",
                    "schedules": {"holiday": ["08:30", "10:30"]},
                },
            ],
            "notes": ["春节期间停开"],
        },
    ],
}


class TestBusAdapter:
    """校车适配器测试。"""

    def _make_adapter(self, data: dict | None = None) -> BusAdapter:
        return BusAdapter(schedule_data=data or _SAMPLE_DATA)

    def test_check_auth_always_true(self) -> None:
        adapter = self._make_adapter()
        assert asyncio.run(adapter.check_auth()) is True

    def test_fetch_all(self) -> None:
        """无筛选时返回所有时刻数据。"""
        adapter = self._make_adapter()
        events = asyncio.run(adapter.fetch())

        # 4 workday + 2 holiday (循环) + 2+2 holiday (兰台) = 10
        assert len(events) == 10
        assert all(e.source == AdapterSource.STATIC_JSON for e in events)
        assert all(e.category == EventCategory.BUS for e in events)

    def test_fetch_filter_by_route(self) -> None:
        """按线路名筛选。"""
        adapter = self._make_adapter()
        events = asyncio.run(adapter.fetch(route="循环"))
        assert len(events) == 6  # 4 workday + 2 holiday

        events = asyncio.run(adapter.fetch(route="兰台"))
        assert len(events) == 4  # 2+2 holiday

    def test_fetch_filter_by_short_name(self) -> None:
        """按短名称筛选也能匹配。"""
        adapter = self._make_adapter()
        events = asyncio.run(adapter.fetch(route="接驳车"))
        assert len(events) == 4

    def test_fetch_filter_by_schedule_type(self) -> None:
        """按时刻表类型筛选。"""
        adapter = self._make_adapter()
        events = asyncio.run(adapter.fetch(schedule_type="workday"))
        assert len(events) == 4  # only 循环巴士 has workday

        events = asyncio.run(adapter.fetch(schedule_type="holiday"))
        assert len(events) == 6  # 2 循环 + 4 兰台

    def test_fetch_combined_filter(self) -> None:
        """同时按线路 + 类型筛选。"""
        adapter = self._make_adapter()
        events = asyncio.run(adapter.fetch(route="循环", schedule_type="holiday"))
        assert len(events) == 2

    def test_fetch_no_match(self) -> None:
        """无匹配时返回空列表。"""
        adapter = self._make_adapter()
        events = asyncio.run(adapter.fetch(route="不存在的线路"))
        assert events == []

    def test_events_sorted_by_time(self) -> None:
        """结果按发车时间排序。"""
        adapter = self._make_adapter()
        events = asyncio.run(adapter.fetch(route="循环", schedule_type="workday"))
        times = [e.content["departure_time"] for e in events]
        assert times == sorted(times)

    def test_event_content_fields(self) -> None:
        """验证 CampusEvent.content 包含 BusRoute 所有字段。"""
        adapter = self._make_adapter()
        events = asyncio.run(adapter.fetch(route="循环", schedule_type="workday"))
        event = events[0]

        c = event.content
        assert c["route_name"] == "九龙湖校园循环巴士"
        assert c["departure_time"] == "07:00"
        assert c["departure_stop"] == "图书馆北"
        assert c["arrival_stop"] == "循环线路"
        assert c["note"] == "工作日"

    def test_event_id_format(self) -> None:
        """事件 ID 格式: static_json:bus:<hash>。"""
        adapter = self._make_adapter()
        events = asyncio.run(adapter.fetch(route="循环", schedule_type="workday"))
        for event in events:
            assert event.id.startswith("static_json:bus:")
            assert len(event.id.split(":")[-1]) == 12

    def test_event_ids_unique(self) -> None:
        """所有事件 ID 唯一。"""
        adapter = self._make_adapter()
        events = asyncio.run(adapter.fetch())
        ids = [e.id for e in events]
        assert len(ids) == len(set(ids))

    def test_bidirectional_route(self) -> None:
        """兰台接驳车有两个方向。"""
        adapter = self._make_adapter()
        events = asyncio.run(adapter.fetch(route="兰台"))

        stops = {
            (e.content["departure_stop"], e.content["arrival_stop"]) for e in events
        }
        assert ("兰台", "北门圆盘") in stops
        assert ("北门圆盘", "兰台") in stops

    def test_get_route_names(self) -> None:
        adapter = self._make_adapter()
        names = adapter.get_route_names()
        assert "九龙湖校园循环巴士" in names
        assert "兰台研究生公寓接驳车" in names

    def test_get_schedule_types(self) -> None:
        adapter = self._make_adapter()
        types = adapter.get_schedule_types()
        assert "workday" in types
        assert "holiday" in types

    def test_get_schedule_types_filtered(self) -> None:
        adapter = self._make_adapter()
        types = adapter.get_schedule_types("兰台")
        assert types == {"holiday"}

    def test_get_notes(self) -> None:
        adapter = self._make_adapter()
        notes = adapter.get_notes("循环")
        assert "早高峰坐满即走" in notes

        notes = adapter.get_notes("兰台")
        assert "春节期间停开" in notes

    def test_get_meta(self) -> None:
        adapter = self._make_adapter()
        meta = adapter.get_meta()
        assert meta["version"] == "2024-11-25"
        assert meta["last_updated"] == "2026-01-27"

    def test_config_route_filter(self) -> None:
        """通过 config 传入 route 筛选。"""
        adapter = BusAdapter(config={"route": "循环"}, schedule_data=_SAMPLE_DATA)
        events = asyncio.run(adapter.fetch())
        assert all("循环" in e.content["route_name"] for e in events)

    def test_config_schedule_type(self) -> None:
        """通过 config 传入 schedule_type。"""
        adapter = BusAdapter(
            config={"schedule_type": "workday"}, schedule_data=_SAMPLE_DATA
        )
        events = asyncio.run(adapter.fetch())
        assert all(e.content["note"] == "工作日" for e in events)

    def test_empty_data(self) -> None:
        """空数据时返回空列表。"""
        adapter = self._make_adapter({"meta": {}, "routes": []})
        events = asyncio.run(adapter.fetch())
        assert events == []

    def test_adapter_name(self) -> None:
        adapter = self._make_adapter()
        assert adapter.adapter_name() == "BusAdapter"


class TestScheduleTypeLabel:
    """_schedule_type_label 辅助函数测试。"""

    def test_workday(self) -> None:
        assert _schedule_type_label("workday") == "工作日"

    def test_holiday(self) -> None:
        assert _schedule_type_label("holiday") == "节假日"

    def test_spring_festival(self) -> None:
        assert _schedule_type_label("spring_festival") == "春节"

    def test_unknown(self) -> None:
        assert _schedule_type_label("custom") == "custom"


class TestLoadRealData:
    """验证打包的真实 JSON 数据能正常加载和解析。"""

    def test_load_real_schedule(self) -> None:
        """加载真实 bus_schedule.json 无报错。"""
        adapter = BusAdapter()
        events = asyncio.run(adapter.fetch())
        assert len(events) > 0

    def test_real_data_has_loop_bus(self) -> None:
        """真实数据包含循环巴士。"""
        adapter = BusAdapter()
        events = asyncio.run(adapter.fetch(route="循环", schedule_type="workday"))
        assert len(events) == 72  # 官方时刻表共 72 趟

    def test_real_data_holiday_trips(self) -> None:
        """真实数据: 循环巴士节假日 23 趟。"""
        adapter = BusAdapter()
        events = asyncio.run(adapter.fetch(route="循环", schedule_type="holiday"))
        assert len(events) == 23

    def test_real_data_spring_festival(self) -> None:
        """真实数据: 循环巴士春节 11 趟。"""
        adapter = BusAdapter()
        events = asyncio.run(
            adapter.fetch(route="循环", schedule_type="spring_festival")
        )
        assert len(events) == 11

    def test_real_data_meta(self) -> None:
        """真实数据元信息完整。"""
        adapter = BusAdapter()
        meta = adapter.get_meta()
        assert "version" in meta
        assert "source_url" in meta
        assert "last_updated" in meta
