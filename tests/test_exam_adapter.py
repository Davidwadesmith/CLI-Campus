"""Tests for ExamAdapter."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cli_campus.adapters.exam_adapter import ExamAdapter
from cli_campus.core.exceptions import AdapterError, AuthRequiredError
from cli_campus.core.models import AdapterSource, EventCategory

# ---------------------------------------------------------------------------
# 固定测试数据 — 模拟 ehall 考试安排 API 响应
# ---------------------------------------------------------------------------

_SAMPLE_ROW: dict[str, Any] = {
    "KCM": "高等数学 A",
    "KSSJMS": "2025-11-21 19:00-21:00(星期五)",
    "JASMC": "九龙湖教三-302",
    "ZWH": "15",
    "ZJJSXM": "张三",
    "XNXQDM": "2025-2026-2",
    "KSMC": "期末考试",
    "XF": "5.0",
}

_SAMPLE_RESPONSE: dict[str, Any] = {
    "datas": {
        "wdksap": {
            "rows": [_SAMPLE_ROW],
        }
    }
}


def _make_adapter(
    mock_wrapper: MagicMock | None = None,
    config: dict[str, Any] | None = None,
) -> ExamAdapter:
    wrapper = mock_wrapper or MagicMock()
    return ExamAdapter(config=config, auth_wrapper=wrapper)


class TestExamAdapterParse:
    """ExamAdapter._parse_response 解析测试。"""

    def test_parse_single_row(self) -> None:
        adapter = _make_adapter()
        events = adapter._parse_response(_SAMPLE_RESPONSE)
        assert len(events) == 1

        event = events[0]
        assert event.source == AdapterSource.SEU_EHALL
        assert event.category == EventCategory.EXAM
        assert "高等数学 A" in event.title

        c = event.content
        assert c["course_name"] == "高等数学 A"
        assert c["time_text"] == "2025-11-21 19:00-21:00(星期五)"
        assert c["location"] == "九龙湖教三-302"
        assert c["seat_number"] == "15"
        assert c["teacher"] == "张三"
        assert c["semester"] == "2025-2026-2"
        assert c["exam_name"] == "期末考试"
        assert c["credit"] == 5.0

    def test_parse_multiple_rows(self) -> None:
        row2 = {
            "KCM": "线性代数",
            "KSSJMS": "2025-12-01 14:00-16:00(星期一)",
            "JASMC": "教四-103",
            "ZWH": "22",
            "ZJJSXM": "李四",
            "XNXQDM": "2025-2026-2",
            "KSMC": "期末考试",
            "XF": "3.0",
        }
        response = {"datas": {"wdksap": {"rows": [_SAMPLE_ROW, row2]}}}
        adapter = _make_adapter()
        events = adapter._parse_response(response)
        assert len(events) == 2
        assert events[1].content["course_name"] == "线性代数"

    def test_parse_empty_rows(self) -> None:
        response = {"datas": {"wdksap": {"rows": []}}}
        adapter = _make_adapter()
        events = adapter._parse_response(response)
        assert events == []

    def test_parse_bad_format_raises(self) -> None:
        adapter = _make_adapter()
        with pytest.raises(AdapterError, match="考试安排响应格式异常"):
            adapter._parse_response({"unexpected": True})

    def test_parse_missing_optional_fields(self) -> None:
        """缺少可选字段时使用默认值。"""
        row = {"KCM": "体育"}
        response = {"datas": {"wdksap": {"rows": [row]}}}
        adapter = _make_adapter()
        events = adapter._parse_response(response)
        assert len(events) == 1
        assert events[0].content["time_text"] == ""
        assert events[0].content["location"] == ""
        assert events[0].content["seat_number"] == ""
        assert events[0].content["credit"] == 0.0

    def test_parse_none_fields(self) -> None:
        """字段值为 None 时使用默认值。"""
        row = {
            "KCM": "体育",
            "KSSJMS": None,
            "JASMC": None,
            "ZWH": None,
            "ZJJSXM": None,
            "XF": None,
        }
        response = {"datas": {"wdksap": {"rows": [row]}}}
        adapter = _make_adapter()
        events = adapter._parse_response(response)
        c = events[0].content
        assert c["time_text"] == ""
        assert c["location"] == ""
        assert c["seat_number"] == ""
        assert c["teacher"] == ""
        assert c["credit"] == 0.0


class TestExamAdapterFetch:
    """ExamAdapter.fetch 集成测试（mock 网络）。"""

    def test_fetch_no_credentials(self) -> None:
        mock_wrapper = MagicMock()
        mock_wrapper.get_authenticated_client = AsyncMock(
            side_effect=AuthRequiredError()
        )
        mock_wrapper.close = AsyncMock()

        adapter = _make_adapter(mock_wrapper=mock_wrapper)
        with pytest.raises(AuthRequiredError):
            asyncio.run(adapter.fetch())

    def test_module_name(self) -> None:
        adapter = _make_adapter()
        assert adapter._module_name() == "studentWdksapApp"

    def test_app_id(self) -> None:
        adapter = _make_adapter()
        assert adapter._APP_ID == "4768687067472349"
