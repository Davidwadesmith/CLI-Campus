"""Tests for VenueAdapter."""

from __future__ import annotations

import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cli_campus.adapters.venue_adapter import VenueAdapter, _infer_campus
from cli_campus.core.exceptions import AdapterError
from cli_campus.core.models import (
    AdapterSource,
    BookingInfo,
    EventCategory,
    TimeSlotInfo,
    VenueInfo,
)

# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------


def _make_adapter() -> VenueAdapter:
    """创建测试用 adapter，不触发真实认证。"""
    adapter = VenueAdapter()
    adapter._token = "test_token_12345"
    return adapter


def _mock_gql_response(data: dict) -> MagicMock:
    """构造 httpx response mock。"""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": data}
    return resp


# ---------------------------------------------------------------------------
# _infer_campus 单元测试
# ---------------------------------------------------------------------------


class TestInferCampus:
    def test_jlh(self) -> None:
        assert _infer_campus("JLH01") == "九龙湖"

    def test_spl(self) -> None:
        assert _infer_campus("SPL02") == "四牌楼"

    def test_djq(self) -> None:
        assert _infer_campus("DJQ001") == "丁家桥"

    def test_wx(self) -> None:
        assert _infer_campus("WX05") == "无锡"

    def test_unknown(self) -> None:
        assert _infer_campus("XYZ01") == ""

    def test_empty(self) -> None:
        assert _infer_campus("") == ""

    def test_lowercase(self) -> None:
        assert _infer_campus("jlh03") == "九龙湖"


# ---------------------------------------------------------------------------
# VenueAdapter.get_venues 测试
# ---------------------------------------------------------------------------


class TestGetVenues:
    def test_get_venues_success(self) -> None:
        """正常返回场馆列表。"""
        adapter = _make_adapter()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_mock_gql_response(
                {
                    "findResourcesAllByAccount": [
                        {
                            "id": "uuid-1",
                            "resources_name": "九龙湖一号场地",
                            "resources_number": "JLH01",
                            "resources_type_name": "羽毛球场",
                            "state": 0,
                            "capacity": 4,
                        },
                        {
                            "id": "uuid-2",
                            "resources_name": "四牌楼一号场地",
                            "resources_number": "SPL01",
                            "resources_type_name": "羽毛球场",
                            "state": 0,
                            "capacity": 4,
                        },
                    ]
                }
            )
        )
        adapter._client = mock_client

        venues = asyncio.run(adapter.get_venues("羽毛球场"))

        assert len(venues) == 2
        assert venues[0].venue_id == "uuid-1"
        assert venues[0].name == "九龙湖一号场地"
        assert venues[0].number == "JLH01"
        assert venues[0].campus == "九龙湖"
        assert venues[0].capacity == 4
        assert venues[1].campus == "四牌楼"

    def test_get_venues_empty(self) -> None:
        """无场馆返回空列表。"""
        adapter = _make_adapter()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_mock_gql_response({"findResourcesAllByAccount": []})
        )
        adapter._client = mock_client

        venues = asyncio.run(adapter.get_venues("不存在的类型"))
        assert venues == []

    def test_get_venues_graphql_error(self) -> None:
        """GraphQL 返回错误时抛出 AdapterError。"""
        adapter = _make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"errors": [{"message": "Unauthorized"}]}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        adapter._client = mock_client

        with pytest.raises(AdapterError, match="Unauthorized"):
            asyncio.run(adapter.get_venues("羽毛球场"))


# ---------------------------------------------------------------------------
# VenueAdapter.get_time_slots 测试
# ---------------------------------------------------------------------------


class TestGetTimeSlots:
    def test_get_time_slots_success(self) -> None:
        """正常返回时间段列表。"""
        adapter = _make_adapter()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_mock_gql_response(
                {
                    "findResourcesTimeSlotByResourcesIdAndDate": [
                        {
                            "id": "slot-1",
                            "kssj": "09:00",
                            "jssj": "10:00",
                            "canAppointmentNumber": 3,
                            "canAppointmentNumberDesc": "可预约",
                        },
                        {
                            "id": "slot-2",
                            "kssj": "10:00",
                            "jssj": "11:00",
                            "canAppointmentNumber": 0,
                            "canAppointmentNumberDesc": "已满",
                        },
                    ]
                }
            )
        )
        adapter._client = mock_client

        slots = asyncio.run(adapter.get_time_slots("uuid-1", "2025-07-01"))

        assert len(slots) == 2
        assert slots[0].slot_id == "slot-1"
        assert slots[0].start_time == "09:00"
        assert slots[0].end_time == "10:00"
        assert slots[0].available == 3
        assert slots[0].status_text == "可预约"
        assert slots[0].venue_id == "uuid-1"
        assert slots[0].date == "2025-07-01"

        assert slots[1].available == 0
        assert slots[1].status_text == "已满"

    def test_date_converted_to_timestamp(self) -> None:
        """验证日期正确转换为毫秒时间戳。"""
        adapter = _make_adapter()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_mock_gql_response(
                {"findResourcesTimeSlotByResourcesIdAndDate": []}
            )
        )
        adapter._client = mock_client

        asyncio.run(adapter.get_time_slots("uuid-1", "2025-07-01"))

        # 检查 POST 调用中的 variables
        call_args = mock_client.post.call_args
        body = call_args.kwargs.get("json") or call_args[1].get("json")
        ts = body["variables"]["date"]
        assert isinstance(ts, int)
        # 应为 2025-07-01 00:00:00 本地时间的毫秒时间戳
        expected = int(datetime.datetime(2025, 7, 1).timestamp() * 1000)
        assert ts == expected


# ---------------------------------------------------------------------------
# VenueAdapter.make_booking 测试
# ---------------------------------------------------------------------------


class TestMakeBooking:
    def test_make_booking_success(self) -> None:
        """预约成功返回 BookingInfo。"""
        adapter = _make_adapter()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_mock_gql_response(
                {
                    "saveAppointmentInformation": {
                        "appointmentId": "booking-123",
                        "errcode": "0",
                        "msg": "预约成功",
                    }
                }
            )
        )
        adapter._client = mock_client

        booking = asyncio.run(
            adapter.make_booking("uuid-1", "2025-07-01", "09:00", "10:00")
        )

        assert isinstance(booking, BookingInfo)
        assert booking.booking_id == "booking-123"
        assert booking.start_time == "09:00"
        assert booking.end_time == "10:00"
        assert booking.date == "2025-07-01"

    def test_make_booking_failed(self) -> None:
        """预约失败 (GraphQL 错误) 抛出 AdapterError。"""
        adapter = _make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"errors": [{"message": "该时段已被预约"}]}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        adapter._client = mock_client

        with pytest.raises(AdapterError, match="该时段已被预约"):
            asyncio.run(adapter.make_booking("uuid-1", "2025-07-01", "09:00", "10:00"))

    def test_make_booking_errcode_nonzero(self) -> None:
        """服务端返回 errcode 非零时抛出 AdapterError。"""
        adapter = _make_adapter()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_mock_gql_response(
                {
                    "saveAppointmentInformation": {
                        "appointmentId": "",
                        "errcode": "1001",
                        "msg": "该时间段预约已满",
                    }
                }
            )
        )
        adapter._client = mock_client

        with pytest.raises(AdapterError, match="该时间段预约已满"):
            asyncio.run(adapter.make_booking("uuid-1", "2025-07-01", "09:00", "10:00"))


# ---------------------------------------------------------------------------
# VenueAdapter.cancel_booking 测试
# ---------------------------------------------------------------------------


class TestCancelBooking:
    def test_cancel_success(self) -> None:
        adapter = _make_adapter()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_mock_gql_response(
                {
                    "updateAppointmentInformationState": {
                        "errcode": "0",
                        "msg": "取消成功",
                    }
                }
            )
        )
        adapter._client = mock_client

        result = asyncio.run(adapter.cancel_booking("booking-123", "有事"))
        assert result is True


# ---------------------------------------------------------------------------
# VenueAdapter.get_my_bookings 测试
# ---------------------------------------------------------------------------


class TestGetMyBookings:
    def test_get_my_bookings_success(self) -> None:
        adapter = _make_adapter()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_mock_gql_response(
                {
                    "findAppointmentInformationAllForSelf": {
                        "edges": [
                            {
                                "node": {
                                    "id": "b-1",
                                    "resources_name": "九龙湖一号场地",
                                    "resources_type_name": "羽毛球场",
                                    "appointment_date": 1751299200000,
                                    "start_time": "09:00",
                                    "end_time": "10:00",
                                    "state": 1,
                                    "event": "打球",
                                }
                            }
                        ]
                    }
                }
            )
        )
        adapter._client = mock_client

        bookings = asyncio.run(adapter.get_my_bookings())
        assert len(bookings) == 1
        assert bookings[0].booking_id == "b-1"
        assert bookings[0].venue_name == "九龙湖一号场地"

    def test_get_my_bookings_empty(self) -> None:
        adapter = _make_adapter()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_mock_gql_response(
                {"findAppointmentInformationAllForSelf": {"edges": []}}
            )
        )
        adapter._client = mock_client

        bookings = asyncio.run(adapter.get_my_bookings())
        assert bookings == []


# ---------------------------------------------------------------------------
# VenueAdapter.get_current_time 测试
# ---------------------------------------------------------------------------


class TestGetCurrentTime:
    def test_returns_datetime(self) -> None:
        now = VenueAdapter.get_current_time()
        assert isinstance(now, datetime.datetime)
        # 应在当前时间附近 (1秒内)
        diff = abs((now - datetime.datetime.now()).total_seconds())
        assert diff < 1.0


# ---------------------------------------------------------------------------
# VenueAdapter.check_auth 测试
# ---------------------------------------------------------------------------


class TestCheckAuth:
    def test_check_auth_with_token(self) -> None:
        """已有 token 时 check_auth 返回 True。"""
        adapter = _make_adapter()
        assert asyncio.run(adapter.check_auth()) is True

    @patch("cli_campus.core.auth.CampusAuthManager")
    def test_check_auth_no_credentials(self, mock_mgr_cls: MagicMock) -> None:
        """无凭证时 check_auth 返回 False。"""
        mock_mgr = MagicMock()
        mock_mgr.get_credentials.return_value = None
        mock_mgr_cls.return_value = mock_mgr

        adapter = VenueAdapter()
        assert asyncio.run(adapter.check_auth()) is False


# ---------------------------------------------------------------------------
# VenueAdapter.fetch 测试
# ---------------------------------------------------------------------------


class TestFetch:
    def test_fetch_returns_campus_events(self) -> None:
        """fetch() 返回 CampusEvent 列表。"""
        adapter = _make_adapter()
        mock_client = AsyncMock()

        # First call: get_venues
        venues_resp = _mock_gql_response(
            {
                "findResourcesAllByAccount": [
                    {
                        "id": "uuid-1",
                        "resources_name": "测试场地",
                        "resources_number": "JLH01",
                        "resources_type_name": "羽毛球场",
                        "state": 0,
                        "capacity": 4,
                    }
                ]
            }
        )
        # Second call: get_time_slots
        slots_resp = _mock_gql_response(
            {
                "findResourcesTimeSlotByResourcesIdAndDate": [
                    {
                        "id": "slot-1",
                        "kssj": "09:00",
                        "jssj": "10:00",
                        "canAppointmentNumber": 2,
                        "canAppointmentNumberDesc": "可预约",
                    }
                ]
            }
        )

        mock_client.post = AsyncMock(side_effect=[venues_resp, slots_resp])
        adapter._client = mock_client

        events = asyncio.run(adapter.fetch(type_name="羽毛球场", date="2025-07-01"))

        assert len(events) == 1
        assert events[0].source == AdapterSource.SEU_VENUE
        assert events[0].category == EventCategory.ROOM
        assert "测试场地" in events[0].title
        assert "09:00" in events[0].title


# ---------------------------------------------------------------------------
# Model 测试
# ---------------------------------------------------------------------------


class TestModels:
    def test_venue_info_creation(self) -> None:
        v = VenueInfo(venue_id="uuid-1", name="测试", number="JLH01")
        assert v.venue_id == "uuid-1"
        assert v.campus == ""  # campus not auto-inferred in model

    def test_time_slot_info_creation(self) -> None:
        s = TimeSlotInfo(slot_id="s-1", start_time="09:00", end_time="10:00")
        assert s.available == 0
        assert s.status_text == ""

    def test_booking_info_creation(self) -> None:
        b = BookingInfo(booking_id="b-1")
        assert b.state == 0
        assert b.venue_name == ""

    def test_adapter_source_has_venue(self) -> None:
        from cli_campus.core.models import AdapterSource

        assert AdapterSource.SEU_VENUE == "seu_venue"
