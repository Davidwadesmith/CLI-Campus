"""Tests for CLI entrypoint and JSON middleware."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from cli_campus.main import app

runner = CliRunner()


class TestCLIBasics:
    """CLI 基础功能测试。"""

    def test_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "CLI-Campus" in result.stdout

    def test_version(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "CLI-Campus" in result.stdout

    def test_version_json(self) -> None:
        result = runner.invoke(app, ["--json", "version"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "version" in data


class TestTestAdapterCommand:
    """test-adapter 命令测试。"""

    def test_default_mock_adapter(self) -> None:
        result = runner.invoke(app, ["test-adapter"])
        assert result.exit_code == 0
        assert "MockAdapter" in result.stdout
        assert "认证通过" in result.stdout

    def test_explicit_mock_adapter(self) -> None:
        result = runner.invoke(app, ["test-adapter", "mock"])
        assert result.exit_code == 0
        assert "1 条事件" in result.stdout

    def test_unknown_adapter(self) -> None:
        result = runner.invoke(app, ["test-adapter", "nonexistent"])
        assert result.exit_code == 1
        assert "尚未实现" in result.stdout

    def test_json_output(self) -> None:
        result = runner.invoke(app, ["--json", "test-adapter"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["source"] == "mock"
        assert data[0]["category"] == "course"

    def test_json_event_has_required_fields(self) -> None:
        result = runner.invoke(app, ["--json", "test-adapter"])
        data = json.loads(result.stdout)
        event = data[0]
        required_fields = {"id", "source", "category", "title", "content", "timestamp"}
        assert required_fields.issubset(event.keys())


class TestAuthCommands:
    """auth 子命令组测试。"""

    def test_auth_help(self) -> None:
        result = runner.invoke(app, ["auth", "--help"])
        assert result.exit_code == 0
        assert "login" in result.stdout
        assert "status" in result.stdout
        assert "logout" in result.stdout

    @patch("cli_campus.adapters.seu_auth_wrapper.SEUAuthWrapper")
    @patch("cli_campus.core.auth.CampusAuthManager")
    def test_auth_login(
        self, mock_auth_cls: MagicMock, mock_wrapper_cls: MagicMock
    ) -> None:
        """模拟交互式登录并验证凭证。"""
        mock_mgr = MagicMock()
        mock_mgr.get_credentials.return_value = None
        mock_auth_cls.return_value = mock_mgr

        mock_wrapper = MagicMock()
        mock_wrapper.verify = AsyncMock(return_value=True)
        mock_wrapper_cls.return_value = mock_wrapper

        result = runner.invoke(app, ["auth", "login"], input="213000001\nsecret123\n")
        assert result.exit_code == 0
        assert "凭证已安全存储" in result.stdout
        assert "213000001" in result.stdout
        assert "验证通过" in result.stdout
        mock_mgr.save_credentials.assert_called_once_with("213000001", "secret123")

    @patch("cli_campus.adapters.seu_auth_wrapper.SEUAuthWrapper")
    @patch("cli_campus.core.auth.CampusAuthManager")
    def test_auth_login_verified_false(
        self, mock_auth_cls: MagicMock, mock_wrapper_cls: MagicMock
    ) -> None:
        """验证失败时凭证仍应保存，并显示警告。"""
        mock_mgr = MagicMock()
        mock_mgr.get_credentials.return_value = None
        mock_auth_cls.return_value = mock_mgr

        mock_wrapper = MagicMock()
        mock_wrapper.verify = AsyncMock(return_value=False)
        mock_wrapper_cls.return_value = mock_wrapper

        result = runner.invoke(app, ["auth", "login"], input="213000001\nwrong\n")
        assert result.exit_code == 0
        assert "凭证已安全存储" in result.stdout
        assert "验证未通过" in result.stdout
        mock_mgr.save_credentials.assert_called_once()

    @patch("cli_campus.adapters.seu_auth_wrapper.SEUAuthWrapper")
    @patch("cli_campus.core.auth.CampusAuthManager")
    def test_auth_login_json(
        self, mock_auth_cls: MagicMock, mock_wrapper_cls: MagicMock
    ) -> None:
        mock_mgr = MagicMock()
        mock_mgr.get_credentials.return_value = None
        mock_auth_cls.return_value = mock_mgr

        mock_wrapper = MagicMock()
        mock_wrapper.verify = AsyncMock(return_value=True)
        mock_wrapper_cls.return_value = mock_wrapper

        result = runner.invoke(
            app,
            ["--json", "auth", "login"],
            input="213000001\nsecret123\n",
        )
        assert result.exit_code == 0
        # typer.prompt 的交互输出混入 stdout，需提取 JSON 行
        json_line = [
            line for line in result.stdout.strip().splitlines() if line.startswith("{")
        ][-1]
        data = json.loads(json_line)
        assert data["status"] == "ok"
        assert data["username"] == "213000001"
        assert data["verified"] is True

    @patch("cli_campus.core.auth.CampusAuthManager")
    def test_auth_status_logged_in(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_mgr.get_credentials.return_value = ("213000001", "secret")
        mock_cls.return_value = mock_mgr

        result = runner.invoke(app, ["auth", "status"])
        assert result.exit_code == 0
        assert "已登录" in result.stdout

    @patch("cli_campus.core.auth.CampusAuthManager")
    def test_auth_status_not_logged_in(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_mgr.get_credentials.return_value = None
        mock_cls.return_value = mock_mgr

        result = runner.invoke(app, ["auth", "status"])
        assert result.exit_code == 1
        assert "未登录" in result.stdout

    @patch("cli_campus.core.auth.CampusAuthManager")
    def test_auth_logout(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr

        result = runner.invoke(app, ["auth", "logout"])
        assert result.exit_code == 0
        assert "已清除" in result.stdout
        mock_mgr.clear_credentials.assert_called_once()

    @patch("cli_campus.core.auth.CampusAuthManager")
    def test_auth_status_json(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_mgr.get_credentials.return_value = ("213000001", "secret")
        mock_cls.return_value = mock_mgr

        result = runner.invoke(app, ["--json", "auth", "status"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["logged_in"] is True
        assert data["username"] == "213000001"


class TestCardCommand:
    """card 命令测试。"""

    @patch("cli_campus.adapters.card_adapter.CardAdapter")
    def test_card_no_credentials(self, mock_cls: MagicMock) -> None:
        """无凭证时应提示登录。"""
        from cli_campus.core.exceptions import AuthRequiredError

        mock_adapter = MagicMock()
        mock_adapter.fetch = MagicMock(side_effect=AuthRequiredError())
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["card"])
        assert result.exit_code == 1
        assert "campus auth login" in result.stdout

    @patch("cli_campus.adapters.card_adapter.CardAdapter")
    def test_card_no_credentials_json(self, mock_cls: MagicMock) -> None:
        from cli_campus.core.exceptions import AuthRequiredError

        mock_adapter = MagicMock()
        mock_adapter.fetch = MagicMock(side_effect=AuthRequiredError())
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["--json", "card"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["error"] == "auth_required"


class TestCourseCommand:
    """course 命令测试。"""

    @patch("cli_campus.adapters.course_adapter.CourseAdapter")
    def test_course_no_credentials(self, mock_cls: MagicMock) -> None:
        from cli_campus.core.exceptions import AuthRequiredError

        mock_adapter = MagicMock()
        mock_adapter.fetch = MagicMock(side_effect=AuthRequiredError())
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["course"])
        assert result.exit_code == 1
        assert "campus auth login" in result.stdout

    @patch("cli_campus.adapters.course_adapter.CourseAdapter")
    def test_course_no_credentials_json(self, mock_cls: MagicMock) -> None:
        from cli_campus.core.exceptions import AuthRequiredError

        mock_adapter = MagicMock()
        mock_adapter.fetch = MagicMock(side_effect=AuthRequiredError())
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["--json", "course"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["error"] == "auth_required"

    @patch("cli_campus.adapters.course_adapter.CourseAdapter")
    def test_course_auth_failed(self, mock_cls: MagicMock) -> None:
        from cli_campus.core.exceptions import AuthFailedError

        mock_adapter = MagicMock()
        mock_adapter.fetch = MagicMock(side_effect=AuthFailedError("bad password"))
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["course"])
        assert result.exit_code == 1
        assert "认证失败" in result.stdout

    @patch("cli_campus.adapters.course_adapter.CourseAdapter")
    def test_course_adapter_error(self, mock_cls: MagicMock) -> None:
        from cli_campus.core.exceptions import AdapterError

        mock_adapter = MagicMock()
        mock_adapter.fetch = MagicMock(side_effect=AdapterError("timeout"))
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["course"])
        assert result.exit_code == 1
        assert "请求失败" in result.stdout

    @patch("cli_campus.adapters.course_adapter.CourseAdapter")
    def test_course_empty_result(self, mock_cls: MagicMock) -> None:
        mock_adapter = MagicMock()
        mock_adapter.fetch = AsyncMock(return_value=[])
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["course"])
        assert result.exit_code == 0
        assert "暂无课程数据" in result.stdout

    @patch("cli_campus.adapters.course_adapter.CourseAdapter")
    def test_course_success_table(self, mock_cls: MagicMock) -> None:
        from cli_campus.core.models import (
            AdapterSource,
            CampusEvent,
            CourseInfo,
            EventCategory,
        )

        course = CourseInfo(
            name="高等数学 A",
            teacher="张三",
            location="九龙湖教三-302",
            day_of_week=1,
            periods="1-2",
            weeks="1-16周",
            raw_schedule_info="",
        )
        event = CampusEvent(
            id="test:course:001",
            source=AdapterSource.SEU_EHALL,
            category=EventCategory.COURSE,
            title="高等数学 A — 周一 1-2 节",
            content=course.model_dump(),
        )

        mock_adapter = MagicMock()
        mock_adapter.fetch = AsyncMock(return_value=[event])
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["course"])
        assert result.exit_code == 0
        assert "高等数学 A" in result.stdout
        assert "1-16周" in result.stdout

    @patch("cli_campus.adapters.course_adapter.CourseAdapter")
    def test_course_json_output(self, mock_cls: MagicMock) -> None:
        from cli_campus.core.models import (
            AdapterSource,
            CampusEvent,
            CourseInfo,
            EventCategory,
        )

        course = CourseInfo(
            name="线性代数",
            teacher="李四",
            location="教四-103",
            day_of_week=3,
            periods="3-4",
            weeks="1-8周",
            raw_schedule_info="",
        )
        event = CampusEvent(
            id="test:course:002",
            source=AdapterSource.SEU_EHALL,
            category=EventCategory.COURSE,
            title="线性代数 — 周三 3-4 节",
            content=course.model_dump(),
        )

        mock_adapter = MagicMock()
        mock_adapter.fetch = AsyncMock(return_value=[event])
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["--json", "course"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert data[0]["content"]["name"] == "线性代数"


class TestGradeCommand:
    """grade 命令测试。"""

    @patch("cli_campus.adapters.grade_adapter.GradeAdapter")
    def test_grade_no_credentials(self, mock_cls: MagicMock) -> None:
        from cli_campus.core.exceptions import AuthRequiredError

        mock_adapter = MagicMock()
        mock_adapter.fetch = MagicMock(side_effect=AuthRequiredError())
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["grade"])
        assert result.exit_code == 1
        assert "campus auth login" in result.stdout

    @patch("cli_campus.adapters.grade_adapter.GradeAdapter")
    def test_grade_no_credentials_json(self, mock_cls: MagicMock) -> None:
        from cli_campus.core.exceptions import AuthRequiredError

        mock_adapter = MagicMock()
        mock_adapter.fetch = MagicMock(side_effect=AuthRequiredError())
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["--json", "grade"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["error"] == "auth_required"

    @patch("cli_campus.adapters.grade_adapter.GradeAdapter")
    def test_grade_empty_result(self, mock_cls: MagicMock) -> None:
        mock_adapter = MagicMock()
        mock_adapter.fetch = AsyncMock(return_value=[])
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["grade"])
        assert result.exit_code == 0
        assert "暂无成绩数据" in result.stdout

    @patch("cli_campus.adapters.grade_adapter.GradeAdapter")
    def test_grade_success_table(self, mock_cls: MagicMock) -> None:
        from cli_campus.core.models import (
            AdapterSource,
            CampusEvent,
            EventCategory,
            GradeInfo,
        )

        grade = GradeInfo(
            course_name="高等数学 A",
            score="93",
            credit=5.0,
            gpa=4.3,
            course_type="必修",
            grade_label="优",
            semester="2025-2026-2",
            passed=True,
        )
        event = CampusEvent(
            id="test:grade:001",
            source=AdapterSource.SEU_EHALL,
            category=EventCategory.GRADE,
            title="高等数学 A — 93",
            content=grade.model_dump(),
        )

        mock_adapter = MagicMock()
        mock_adapter.fetch = AsyncMock(return_value=[event])
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["grade"])
        assert result.exit_code == 0
        assert "高等数学 A" in result.stdout

    @patch("cli_campus.adapters.grade_adapter.GradeAdapter")
    def test_grade_json_output(self, mock_cls: MagicMock) -> None:
        from cli_campus.core.models import (
            AdapterSource,
            CampusEvent,
            EventCategory,
            GradeInfo,
        )

        grade = GradeInfo(
            course_name="线性代数",
            score="85",
            credit=3.0,
            gpa=3.5,
        )
        event = CampusEvent(
            id="test:grade:002",
            source=AdapterSource.SEU_EHALL,
            category=EventCategory.GRADE,
            title="线性代数 — 85",
            content=grade.model_dump(),
        )

        mock_adapter = MagicMock()
        mock_adapter.fetch = AsyncMock(return_value=[event])
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["--json", "grade"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert data[0]["content"]["course_name"] == "线性代数"


class TestExamCommand:
    """exam 命令测试。"""

    @patch("cli_campus.adapters.exam_adapter.ExamAdapter")
    def test_exam_no_credentials(self, mock_cls: MagicMock) -> None:
        from cli_campus.core.exceptions import AuthRequiredError

        mock_adapter = MagicMock()
        mock_adapter.fetch = MagicMock(side_effect=AuthRequiredError())
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["exam"])
        assert result.exit_code == 1
        assert "campus auth login" in result.stdout

    @patch("cli_campus.adapters.exam_adapter.ExamAdapter")
    def test_exam_no_credentials_json(self, mock_cls: MagicMock) -> None:
        from cli_campus.core.exceptions import AuthRequiredError

        mock_adapter = MagicMock()
        mock_adapter.fetch = MagicMock(side_effect=AuthRequiredError())
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["--json", "exam"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["error"] == "auth_required"

    @patch("cli_campus.adapters.exam_adapter.ExamAdapter")
    def test_exam_empty_result(self, mock_cls: MagicMock) -> None:
        mock_adapter = MagicMock()
        mock_adapter.fetch = AsyncMock(return_value=[])
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["exam"])
        assert result.exit_code == 0
        assert "暂无考试安排" in result.stdout

    @patch("cli_campus.adapters.exam_adapter.ExamAdapter")
    def test_exam_success_table(self, mock_cls: MagicMock) -> None:
        from cli_campus.core.models import (
            AdapterSource,
            CampusEvent,
            EventCategory,
            ExamInfo,
        )

        exam = ExamInfo(
            course_name="高等数学 A",
            time_text="2025-11-21 19:00-21:00(星期五)",
            location="九龙湖教三-302",
            seat_number="15",
            teacher="张三",
            exam_name="期末考试",
            credit=5.0,
        )
        event = CampusEvent(
            id="test:exam:001",
            source=AdapterSource.SEU_EHALL,
            category=EventCategory.EXAM,
            title="高等数学 A — 2025-11-21 19:00-21:00(星期五)",
            content=exam.model_dump(),
        )

        mock_adapter = MagicMock()
        mock_adapter.fetch = AsyncMock(return_value=[event])
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["exam"])
        assert result.exit_code == 0
        assert "高等数学 A" in result.stdout

    @patch("cli_campus.adapters.exam_adapter.ExamAdapter")
    def test_exam_json_output(self, mock_cls: MagicMock) -> None:
        from cli_campus.core.models import (
            AdapterSource,
            CampusEvent,
            EventCategory,
            ExamInfo,
        )

        exam = ExamInfo(
            course_name="线性代数",
            time_text="2025-12-01 14:00-16:00(星期一)",
            location="教四-103",
            seat_number="22",
        )
        event = CampusEvent(
            id="test:exam:002",
            source=AdapterSource.SEU_EHALL,
            category=EventCategory.EXAM,
            title="线性代数 — 2025-12-01 14:00-16:00(星期一)",
            content=exam.model_dump(),
        )

        mock_adapter = MagicMock()
        mock_adapter.fetch = AsyncMock(return_value=[event])
        mock_cls.return_value = mock_adapter

        result = runner.invoke(app, ["--json", "exam"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert data[0]["content"]["course_name"] == "线性代数"
