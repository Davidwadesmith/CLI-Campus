"""Tests for GradeAdapter."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cli_campus.adapters.grade_adapter import GradeAdapter
from cli_campus.core.exceptions import AdapterError, AuthRequiredError
from cli_campus.core.models import AdapterSource, EventCategory

# ---------------------------------------------------------------------------
# 固定测试数据 — 模拟 ehall 成绩 API 响应
# ---------------------------------------------------------------------------

_SAMPLE_ROW: dict[str, Any] = {
    "KCM": "高等数学 A",
    "ZCJ": "93",
    "XF": "5.0",
    "XFJD": "4.3",
    "KCXZDM_DISPLAY": "必修",
    "DJCJMC": "优",
    "XNXQDM": "2025-2026-2",
    "SFJG_DISPLAY": "是",
}

_SAMPLE_RESPONSE: dict[str, Any] = {
    "datas": {
        "xscjcx": {
            "rows": [_SAMPLE_ROW],
        }
    }
}


def _make_adapter(
    mock_wrapper: MagicMock | None = None,
    config: dict[str, Any] | None = None,
) -> GradeAdapter:
    wrapper = mock_wrapper or MagicMock()
    return GradeAdapter(config=config, auth_wrapper=wrapper)


class TestGradeAdapterParse:
    """GradeAdapter._parse_response 解析测试。"""

    def test_parse_single_row(self) -> None:
        adapter = _make_adapter()
        events = adapter._parse_response(_SAMPLE_RESPONSE)
        assert len(events) == 1

        event = events[0]
        assert event.source == AdapterSource.SEU_EHALL
        assert event.category == EventCategory.GRADE
        assert "高等数学 A" in event.title

        c = event.content
        assert c["course_name"] == "高等数学 A"
        assert c["score"] == "93"
        assert c["credit"] == 5.0
        assert c["gpa"] == 4.3
        assert c["course_type"] == "必修"
        assert c["grade_label"] == "优"
        assert c["semester"] == "2025-2026-2"
        assert c["passed"] is True

    def test_parse_multiple_rows(self) -> None:
        row2 = {
            "KCM": "线性代数",
            "ZCJ": "85",
            "XF": "3.0",
            "XFJD": "3.5",
            "KCXZDM_DISPLAY": "必修",
            "DJCJMC": "良",
            "XNXQDM": "2025-2026-2",
            "SFJG_DISPLAY": "是",
        }
        response = {"datas": {"xscjcx": {"rows": [_SAMPLE_ROW, row2]}}}
        adapter = _make_adapter()
        events = adapter._parse_response(response)
        assert len(events) == 2
        assert events[1].content["course_name"] == "线性代数"
        assert events[1].content["credit"] == 3.0

    def test_parse_empty_rows(self) -> None:
        response = {"datas": {"xscjcx": {"rows": []}}}
        adapter = _make_adapter()
        events = adapter._parse_response(response)
        assert events == []

    def test_parse_bad_format_raises(self) -> None:
        adapter = _make_adapter()
        with pytest.raises(AdapterError, match="成绩响应格式异常"):
            adapter._parse_response({"unexpected": True})

    def test_parse_failed_grade(self) -> None:
        """SFJG_DISPLAY 为 '否' 时 passed 应为 False。"""
        row = {**_SAMPLE_ROW, "ZCJ": "45", "SFJG_DISPLAY": "否"}
        response = {"datas": {"xscjcx": {"rows": [row]}}}
        adapter = _make_adapter()
        events = adapter._parse_response(response)
        assert events[0].content["passed"] is False

    def test_parse_missing_optional_fields(self) -> None:
        """缺少可选字段时使用默认值。"""
        row = {"KCM": "体育", "ZCJ": "合格"}
        response = {"datas": {"xscjcx": {"rows": [row]}}}
        adapter = _make_adapter()
        events = adapter._parse_response(response)
        assert len(events) == 1
        assert events[0].content["credit"] == 0.0
        assert events[0].content["gpa"] == 0.0
        assert events[0].content["course_type"] == ""

    def test_parse_none_score(self) -> None:
        """ZCJ 为 None 时 score 应为空字符串。"""
        row = {**_SAMPLE_ROW, "ZCJ": None}
        response = {"datas": {"xscjcx": {"rows": [row]}}}
        adapter = _make_adapter()
        events = adapter._parse_response(response)
        assert events[0].content["score"] == ""


class TestGradeAdapterFetch:
    """GradeAdapter.fetch 集成测试（mock 网络）。"""

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
        assert adapter._module_name() == "cjcx"

    def test_app_id(self) -> None:
        adapter = _make_adapter()
        assert adapter._APP_ID == "4768574631264620"
