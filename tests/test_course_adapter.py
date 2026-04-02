"""Tests for CourseAdapter."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cli_campus.adapters.course_adapter import CourseAdapter
from cli_campus.core.exceptions import AdapterError, AuthFailedError, AuthRequiredError
from cli_campus.core.models import AdapterSource, EventCategory

# ---------------------------------------------------------------------------
# 固定测试数据 — 模拟 ehall API 响应
# ---------------------------------------------------------------------------

_SAMPLE_ROW: dict[str, Any] = {
    "KCM": "高等数学 A",
    "SKJS": "张三",
    "JASMC": "九龙湖教三-302",
    "SKXQ": "1",
    "KSJC": "1",
    "JSJC": "2",
    "ZCMC": "1-16周",
    "YPSJDD": "1-16周 星期一 1-2节 九龙湖教三-302",
}

_SAMPLE_RESPONSE: dict[str, Any] = {
    "datas": {
        "xskcb": {
            "rows": [_SAMPLE_ROW],
        }
    }
}

_WDKB_SERVICE_URL = (
    "http://ehall.seu.edu.cn/jwapp/sys/wdkb/*default/index.do"
    "?t_s=123&EMAP_LANG=zh&THEME=indigo&gid_=abc"
)


def _make_adapter(
    mock_wrapper: MagicMock | None = None,
    config: dict[str, Any] | None = None,
) -> CourseAdapter:
    """创建带 mock auth wrapper 的 CourseAdapter。"""
    wrapper = mock_wrapper or MagicMock()
    return CourseAdapter(config=config, auth_wrapper=wrapper)


def _make_appshow_response() -> MagicMock:
    """创建 appShow 302 响应。"""
    resp = MagicMock()
    resp.status_code = 302
    resp.headers = {"location": _WDKB_SERVICE_URL}
    return resp


def _make_platform_client(has_redirect: bool = True) -> AsyncMock:
    """创建 Phase 1+2 的 platform_client：GET redirect → ok, GET appShow → 302."""
    client = AsyncMock()
    platform_resp = MagicMock()
    platform_resp.url = "https://ehall.seu.edu.cn/new/index.html"
    appshow_resp = _make_appshow_response()
    if has_redirect:
        client.get = AsyncMock(side_effect=[platform_resp, appshow_resp])
    else:
        # redirect_url=None → 只有 appShow 一次 GET
        client.get = AsyncMock(side_effect=[appshow_resp])
    # headers 模拟 SDK 遗留头
    client.headers = {
        "content-type": "application/json",
        "origin": "https://auth.seu.edu.cn/",
        "referer": "https://auth.seu.edu.cn/dist/",
    }
    return client


def _make_app_client(
    api_response: MagicMock | None = None,
) -> AsyncMock:
    """创建 Phase 3 的 app_client：GET redirect → ok, POST → api_response."""
    client = AsyncMock()
    init_resp = MagicMock()
    init_resp.url = "https://ehall.seu.edu.cn/jwapp/sys/wdkb/*default/index.do"
    client.get = AsyncMock(return_value=init_resp)

    if api_response is None:
        api_response = MagicMock()
        api_response.json.return_value = _SAMPLE_RESPONSE
        api_response.text = '{"datas":{"xskcb":{"rows":[{}]}}}'
        api_response.raise_for_status = MagicMock()
        api_response.url = (
            "https://ehall.seu.edu.cn/jwapp/sys/wdkb/modules/xskcb/xskcb.do"
        )
    client.post = AsyncMock(return_value=api_response)
    client.headers = {
        "content-type": "application/json",
        "origin": "https://auth.seu.edu.cn/",
        "referer": "https://auth.seu.edu.cn/dist/",
    }
    return client


class TestCourseAdapterParse:
    """CourseAdapter._parse_response 解析测试。"""

    def test_parse_single_row(self) -> None:
        adapter = _make_adapter()
        events = adapter._parse_response(_SAMPLE_RESPONSE)
        assert len(events) == 1

        event = events[0]
        assert event.source == AdapterSource.SEU_EHALL
        assert event.category == EventCategory.COURSE
        assert "高等数学 A" in event.title

        c = event.content
        assert c["name"] == "高等数学 A"
        assert c["teacher"] == "张三"
        assert c["location"] == "九龙湖教三-302"
        assert c["day_of_week"] == 1
        assert c["periods"] == "1-2"
        assert c["weeks"] == "1-16周"

    def test_parse_multiple_rows(self) -> None:
        row2 = {
            "KCM": "线性代数",
            "SKJS": "李四",
            "JASMC": "教四-103",
            "SKXQ": "3",
            "KSJC": "3",
            "JSJC": "4",
            "ZCMC": "1-8周",
            "YPSJDD": "",
        }
        response = {"datas": {"xskcb": {"rows": [_SAMPLE_ROW, row2]}}}
        adapter = _make_adapter()
        events = adapter._parse_response(response)
        assert len(events) == 2
        assert events[1].content["name"] == "线性代数"
        assert events[1].content["day_of_week"] == 3

    def test_parse_empty_rows(self) -> None:
        response = {"datas": {"xskcb": {"rows": []}}}
        adapter = _make_adapter()
        events = adapter._parse_response(response)
        assert events == []

    def test_parse_bad_format_raises(self) -> None:
        adapter = _make_adapter()
        with pytest.raises(AdapterError, match="响应格式异常"):
            adapter._parse_response({"unexpected": True})

    def test_parse_missing_optional_fields(self) -> None:
        """缺少可选字段时使用默认值。"""
        row = {"KCM": "体育", "SKXQ": "5", "KSJC": "7", "JSJC": "8"}
        response = {"datas": {"xskcb": {"rows": [row]}}}
        adapter = _make_adapter()
        events = adapter._parse_response(response)
        assert len(events) == 1
        assert events[0].content["teacher"] == ""
        assert events[0].content["location"] == ""

    def test_parse_none_optional_fields(self) -> None:
        """可选字段值为 None 时使用默认值（API 实际返回 null）。"""
        row = {
            "KCM": "体育",
            "SKJS": None,
            "JASMC": None,
            "SKXQ": "5",
            "KSJC": "7",
            "JSJC": "8",
            "ZCMC": None,
            "YPSJDD": None,
        }
        response = {"datas": {"xskcb": {"rows": [row]}}}
        adapter = _make_adapter()
        events = adapter._parse_response(response)
        assert len(events) == 1
        assert events[0].content["teacher"] == ""
        assert events[0].content["location"] == ""
        assert events[0].content["weeks"] == ""

    def test_parse_invalid_day_fallback(self) -> None:
        """SKXQ 非数字时回退到 1。"""
        row = {**_SAMPLE_ROW, "SKXQ": "abc"}
        response = {"datas": {"xskcb": {"rows": [row]}}}
        adapter = _make_adapter()
        events = adapter._parse_response(response)
        assert events[0].content["day_of_week"] == 1


class TestCourseAdapterFetch:
    """CourseAdapter.fetch 集成测试（mock 网络）— 三阶段认证流程。"""

    @patch("cli_campus.adapters.ehall_base.SEUAuthWrapper")
    def test_fetch_success(self, MockWrapper) -> None:
        # Phase 1+2: platform wrapper
        platform_wrapper = MagicMock()
        platform_client = _make_platform_client()
        platform_wrapper.get_authenticated_client = AsyncMock(
            return_value=(platform_client, "https://redirect")
        )
        platform_wrapper.close = AsyncMock()

        # Phase 3: app wrapper (created by SEUAuthWrapper() in fetch)
        app_wrapper_instance = MagicMock()
        app_client = _make_app_client()
        app_wrapper_instance.get_authenticated_client = AsyncMock(
            return_value=(app_client, "http://ehall.seu.edu.cn/jwapp/...?ticket=ST-x")
        )
        app_wrapper_instance.close = AsyncMock()
        MockWrapper.return_value = app_wrapper_instance

        adapter = _make_adapter(mock_wrapper=platform_wrapper)
        events = asyncio.run(adapter.fetch())
        assert len(events) == 1
        assert events[0].content["name"] == "高等数学 A"
        platform_wrapper.close.assert_awaited_once()
        app_wrapper_instance.close.assert_awaited_once()
        # 验证 appShow 请求使用了 follow_redirects=False
        appshow_call = platform_client.get.call_args_list[1]
        assert appshow_call[1].get("follow_redirects") is False

    def test_fetch_no_credentials(self) -> None:
        mock_wrapper = MagicMock()
        mock_wrapper.get_authenticated_client = AsyncMock(
            side_effect=AuthRequiredError()
        )
        mock_wrapper.close = AsyncMock()

        adapter = _make_adapter(mock_wrapper=mock_wrapper)
        with pytest.raises(AuthRequiredError):
            asyncio.run(adapter.fetch())

    def test_fetch_auth_failed(self) -> None:
        mock_wrapper = MagicMock()
        mock_wrapper.get_authenticated_client = AsyncMock(
            side_effect=AuthFailedError("bad password")
        )
        mock_wrapper.close = AsyncMock()

        adapter = _make_adapter(mock_wrapper=mock_wrapper)
        with pytest.raises(AuthFailedError):
            asyncio.run(adapter.fetch())

    @patch("cli_campus.adapters.ehall_base.SEUAuthWrapper")
    def test_fetch_api_error(self, MockWrapper) -> None:
        # Phase 1+2
        platform_wrapper = MagicMock()
        platform_client = _make_platform_client()
        platform_wrapper.get_authenticated_client = AsyncMock(
            return_value=(platform_client, "https://redirect")
        )
        platform_wrapper.close = AsyncMock()

        # Phase 3: app client POST fails
        app_wrapper_instance = MagicMock()
        app_client = AsyncMock()
        init_resp = MagicMock()
        init_resp.url = "https://ehall.seu.edu.cn/jwapp/..."
        app_client.get = AsyncMock(return_value=init_resp)
        app_client.post = AsyncMock(side_effect=Exception("timeout"))
        app_client.headers = {}
        app_wrapper_instance.get_authenticated_client = AsyncMock(
            return_value=(app_client, "http://redirect?ticket=ST-x")
        )
        app_wrapper_instance.close = AsyncMock()
        MockWrapper.return_value = app_wrapper_instance

        adapter = _make_adapter(mock_wrapper=platform_wrapper)
        with pytest.raises(AdapterError, match="API 请求失败"):
            asyncio.run(adapter.fetch())
        app_wrapper_instance.close.assert_awaited_once()

    @patch("cli_campus.adapters.ehall_base.SEUAuthWrapper")
    def test_fetch_custom_semester(self, MockWrapper) -> None:
        # Phase 1+2 (no redirect)
        platform_wrapper = MagicMock()
        platform_client = _make_platform_client(has_redirect=False)
        platform_wrapper.get_authenticated_client = AsyncMock(
            return_value=(platform_client, None)
        )
        platform_wrapper.close = AsyncMock()

        # Phase 3
        app_wrapper_instance = MagicMock()
        app_client = _make_app_client()
        app_wrapper_instance.get_authenticated_client = AsyncMock(
            return_value=(app_client, None)
        )
        app_wrapper_instance.close = AsyncMock()
        MockWrapper.return_value = app_wrapper_instance

        adapter = _make_adapter(mock_wrapper=platform_wrapper)
        asyncio.run(adapter.fetch(semester="2024-2025-1"))

        call_kwargs = app_client.post.call_args
        assert call_kwargs[1]["data"]["XNXQDM"] == "2024-2025-1"

    @patch("cli_campus.adapters.ehall_base.SEUAuthWrapper")
    def test_fetch_empty_response_raises(self, MockWrapper) -> None:
        """API 返回空响应时抛出 AdapterError。"""
        # Phase 1+2 (no redirect)
        platform_wrapper = MagicMock()
        platform_client = _make_platform_client(has_redirect=False)
        platform_wrapper.get_authenticated_client = AsyncMock(
            return_value=(platform_client, None)
        )
        platform_wrapper.close = AsyncMock()

        # Phase 3: empty response
        empty_resp = MagicMock()
        empty_resp.text = ""
        empty_resp.raise_for_status = MagicMock()
        empty_resp.url = "https://ehall.seu.edu.cn/jwapp/..."
        app_client = _make_app_client(api_response=empty_resp)
        app_wrapper_instance = MagicMock()
        app_wrapper_instance.get_authenticated_client = AsyncMock(
            return_value=(app_client, None)
        )
        app_wrapper_instance.close = AsyncMock()
        MockWrapper.return_value = app_wrapper_instance

        adapter = _make_adapter(mock_wrapper=platform_wrapper)
        with pytest.raises(AdapterError, match="空响应"):
            asyncio.run(adapter.fetch())

    def test_fetch_vpn_redirect_detected(self) -> None:
        """Phase 1 平台登录时检测到 VPN 重定向。"""
        mock_wrapper = MagicMock()
        mock_client = AsyncMock()
        mock_vpn_resp = MagicMock()
        mock_vpn_resp.url = "https://vpn.seu.edu.cn/portal/shortcut.html"
        mock_client.get = AsyncMock(return_value=mock_vpn_resp)
        mock_client.headers = {}
        mock_wrapper.get_authenticated_client = AsyncMock(
            return_value=(mock_client, "http://ehall.seu.edu.cn/login?ticket=ST-x")
        )
        mock_wrapper.close = AsyncMock()

        adapter = _make_adapter(mock_wrapper=mock_wrapper)
        with pytest.raises(AdapterError, match="VPN"):
            asyncio.run(adapter.fetch())
        mock_wrapper.close.assert_awaited_once()

    def test_fetch_appshow_non_redirect_raises(self) -> None:
        """appShow 未返回 302 重定向时抛出错误。"""
        mock_wrapper = MagicMock()
        mock_client = AsyncMock()
        platform_resp = MagicMock()
        platform_resp.url = "https://ehall.seu.edu.cn/new/index.html"
        appshow_resp = MagicMock()
        appshow_resp.status_code = 200  # 非 302
        mock_client.get = AsyncMock(side_effect=[platform_resp, appshow_resp])
        mock_client.headers = {}
        mock_wrapper.get_authenticated_client = AsyncMock(
            return_value=(mock_client, "https://redirect")
        )
        mock_wrapper.close = AsyncMock()

        adapter = _make_adapter(mock_wrapper=mock_wrapper)
        with pytest.raises(AdapterError, match="appShow"):
            asyncio.run(adapter.fetch())


class TestCourseAdapterCheckAuth:
    """CourseAdapter.check_auth 测试。"""

    def test_check_auth_success(self) -> None:
        mock_wrapper = MagicMock()
        mock_client = AsyncMock()
        mock_wrapper.get_authenticated_client = AsyncMock(
            return_value=(mock_client, None)
        )
        mock_wrapper.close = AsyncMock()

        adapter = _make_adapter(mock_wrapper=mock_wrapper)
        assert asyncio.run(adapter.check_auth()) is True
        mock_wrapper.close.assert_awaited_once()

    def test_check_auth_no_credentials(self) -> None:
        mock_wrapper = MagicMock()
        mock_wrapper.get_authenticated_client = AsyncMock(
            side_effect=AuthRequiredError()
        )

        adapter = _make_adapter(mock_wrapper=mock_wrapper)
        with pytest.raises(AuthRequiredError):
            asyncio.run(adapter.check_auth())


class TestCleanClientHeaders:
    """_clean_client_headers 测试。"""

    def test_removes_cas_headers(self) -> None:
        mock_client = MagicMock()
        mock_client.headers = {
            "content-type": "application/json",
            "origin": "https://auth.seu.edu.cn/",
            "referer": "https://auth.seu.edu.cn/dist/",
            "accept": "*/*",
        }
        CourseAdapter._clean_client_headers(mock_client)
        assert "content-type" not in mock_client.headers
        assert "origin" not in mock_client.headers
        assert "referer" not in mock_client.headers
        assert mock_client.headers["accept"] == "*/*"

    def test_no_error_when_headers_missing(self) -> None:
        mock_client = MagicMock()
        mock_client.headers = {"accept": "*/*"}
        # 不应该抛异常
        CourseAdapter._clean_client_headers(mock_client)


class TestComputeCurrentSemester:
    """compute_current_semester 学期自动推断测试。"""

    def test_fall_semester_september(self) -> None:
        from datetime import date

        from cli_campus.adapters.course_adapter import compute_current_semester

        assert compute_current_semester(date(2025, 9, 15)) == "2025-2026-2"

    def test_fall_semester_december(self) -> None:
        from datetime import date

        from cli_campus.adapters.course_adapter import compute_current_semester

        assert compute_current_semester(date(2025, 12, 31)) == "2025-2026-2"

    def test_january_is_fall(self) -> None:
        from datetime import date

        from cli_campus.adapters.course_adapter import compute_current_semester

        assert compute_current_semester(date(2026, 1, 10)) == "2025-2026-2"

    def test_spring_semester(self) -> None:
        from datetime import date

        from cli_campus.adapters.course_adapter import compute_current_semester

        assert compute_current_semester(date(2026, 4, 1)) == "2025-2026-3"

    def test_spring_semester_february(self) -> None:
        from datetime import date

        from cli_campus.adapters.course_adapter import compute_current_semester

        assert compute_current_semester(date(2026, 2, 20)) == "2025-2026-3"

    def test_spring_semester_june(self) -> None:
        from datetime import date

        from cli_campus.adapters.course_adapter import compute_current_semester

        assert compute_current_semester(date(2026, 6, 15)) == "2025-2026-3"

    def test_summer_semester_july(self) -> None:
        from datetime import date

        from cli_campus.adapters.course_adapter import compute_current_semester

        assert compute_current_semester(date(2025, 7, 15)) == "2025-2026-1"

    def test_summer_semester_august(self) -> None:
        from datetime import date

        from cli_campus.adapters.course_adapter import compute_current_semester

        assert compute_current_semester(date(2025, 8, 20)) == "2025-2026-1"

    def test_default_uses_today(self) -> None:
        from cli_campus.adapters.course_adapter import compute_current_semester

        result = compute_current_semester()
        # 返回格式应为 YYYY-YYYY-T
        parts = result.split("-")
        assert len(parts) == 3
        assert parts[2] in ("1", "2", "3")


class TestParseWeeks:
    """parse_weeks 周次解析测试。"""

    def test_simple_range(self) -> None:
        from cli_campus.adapters.course_adapter import parse_weeks

        assert parse_weeks("1-16周") == set(range(1, 17))

    def test_single_week(self) -> None:
        from cli_campus.adapters.course_adapter import parse_weeks

        assert parse_weeks("5周") == {5}

    def test_multiple_ranges(self) -> None:
        from cli_campus.adapters.course_adapter import parse_weeks

        assert parse_weeks("1-8周,10-16周") == set(range(1, 9)) | set(range(10, 17))

    def test_comma_separated_singles(self) -> None:
        from cli_campus.adapters.course_adapter import parse_weeks

        assert parse_weeks("1,3,5,7周") == {1, 3, 5, 7}

    def test_empty_string(self) -> None:
        from cli_campus.adapters.course_adapter import parse_weeks

        assert parse_weeks("") == set()

    def test_mixed_format(self) -> None:
        from cli_campus.adapters.course_adapter import parse_weeks

        assert parse_weeks("1-4周,6,8-10周") == {1, 2, 3, 4, 6, 8, 9, 10}
