"""Campus Adapter Protocol — 统一数据模型定义 (Standard Types)。

所有 Adapter 返回的数据必须遵循此处定义的 Pydantic 模型，
屏蔽底层异构数据源的差异，为上层 CLI / Agent 提供干净、结构化的数据。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 枚举定义
# ---------------------------------------------------------------------------


class EventCategory(str, Enum):
    """事件类别枚举 — 用于标记 CampusEvent 的业务分类。"""

    COURSE = "course"
    BUS = "bus"
    DEADLINE = "deadline"
    NEWS = "news"
    FINANCE = "finance"
    ROOM = "room"
    CARD = "card"
    GRADE = "grade"
    EXAM = "exam"
    OTHER = "other"


class AdapterSource(str, Enum):
    """数据来源枚举 — 标记 CampusEvent 来自哪个 Adapter / 供应商。"""

    SEU_CAS = "seu_cas"
    SEU_CARD = "seu_card"
    SEU_EHALL = "seu_ehall"
    ZHENGFANG = "zhengfang"
    CHAOXING = "chaoxing"
    YUKETANG = "yuketang"
    STATIC_JSON = "static_json"
    MOCK = "mock"


# ---------------------------------------------------------------------------
# 顶层信封模型
# ---------------------------------------------------------------------------


class CampusEvent(BaseModel):
    """顶层数据信封 — 所有 Adapter 的标准输出格式。

    无论底层数据源是 JSON API、HTML 页面还是本地 PDF，
    Adapter 最终都必须将数据洗净并封装为 ``CampusEvent`` 实例列表。

    Attributes:
        id: 全局唯一事件 ID（由 Adapter 生成，推荐格式: ``source:category:hash``）。
        source: 数据来源标识。
        category: 业务分类。
        title: 人类可读的事件标题 / 摘要。
        content: 结构化的业务数据，类型取决于 ``category``。
        raw_data: 可选的原始数据快照，便于调试与回溯。
        timestamp: 事件产生 / 抓取的时间戳。
    """

    id: str = Field(..., description="全局唯一事件 ID")
    source: AdapterSource = Field(..., description="数据来源标识")
    category: EventCategory = Field(..., description="业务分类")
    title: str = Field(..., description="人类可读的事件标题")
    content: dict[str, Any] = Field(
        default_factory=dict, description="结构化的业务数据"
    )
    raw_data: Optional[dict[str, Any]] = Field(
        default=None, description="可选的原始数据快照"
    )
    timestamp: datetime = Field(default_factory=datetime.now, description="事件时间戳")


# ---------------------------------------------------------------------------
# 领域模型 — CourseInfo
# ---------------------------------------------------------------------------


class CourseInfo(BaseModel):
    """课程信息模型 — 从教务系统 ehall 接口解析出的单节课程。

    字段映射 (API → Model):
        KCM → name, SKJS → teacher, JASMC → location,
        SKXQ → day_of_week, KSJC/JSJC → periods, ZCMC → weeks,
        YPSJDD → raw_schedule_info

    Attributes:
        name: 课程名称。
        teacher: 授课教师。
        location: 上课地点（教学楼 + 教室）。
        day_of_week: 星期几（1=周一 … 7=周日）。
        periods: 节次范围字符串（如 "3-4"）。
        weeks: 上课周次描述（如 "1-8周"）。
        raw_schedule_info: 原始完整排课信息。
    """

    name: str = Field(..., description="课程名称")
    teacher: str = Field(default="", description="授课教师")
    location: str = Field(default="", description="上课地点")
    day_of_week: int = Field(..., ge=1, le=7, description="星期几 (1~7)")
    periods: str = Field(..., description="节次范围 (如 '3-4')")
    weeks: str = Field(default="", description="上课周次描述 (如 '1-8周')")
    raw_schedule_info: str = Field(default="", description="原始完整排课信息")


# ---------------------------------------------------------------------------
# 领域模型 — BusSchedule
# ---------------------------------------------------------------------------


class BusRoute(BaseModel):
    """校车单条线路时刻。

    Attributes:
        route_name: 线路名称（如 "九龙湖 → 四牌楼"）。
        departure_time: 发车时间（HH:MM 格式）。
        departure_stop: 发车站点。
        arrival_stop: 到达站点。
        note: 备注信息。
    """

    route_name: str = Field(..., description="线路名称")
    departure_time: str = Field(..., description="发车时间 (HH:MM)")
    departure_stop: str = Field(default="", description="发车站点")
    arrival_stop: str = Field(default="", description="到达站点")
    note: str = Field(default="", description="备注信息")


# ---------------------------------------------------------------------------
# 领域模型 — TaskItem (DDL / 作业)
# ---------------------------------------------------------------------------


class TaskItem(BaseModel):
    """待办任务模型 — 聚合雨课堂 / 学习通等平台的 DDL。

    Attributes:
        task_id: 任务唯一标识。
        platform: 来源平台（如 "学习通", "雨课堂"）。
        course_name: 所属课程名称。
        title: 任务标题。
        deadline: 截止时间。
        is_completed: 是否已完成。
        url: 任务原始链接。
    """

    task_id: str = Field(..., description="任务唯一标识")
    platform: str = Field(..., description="来源平台")
    course_name: str = Field(default="", description="所属课程名称")
    title: str = Field(..., description="任务标题")
    deadline: Optional[datetime] = Field(default=None, description="截止时间")
    is_completed: bool = Field(default=False, description="是否已完成")
    url: str = Field(default="", description="任务原始链接")


# ---------------------------------------------------------------------------
# 领域模型 — CardInfo (一卡通)
# ---------------------------------------------------------------------------


class CardInfo(BaseModel):
    """一卡通信息模型 — 校园卡余额与基本信息。

    Attributes:
        student_id: 学号 / 一卡通号。
        name: 持卡人姓名。
        balance: 卡内余额（元）。
        status: 卡片状态（如 "正常", "挂失"）。
    """

    student_id: str = Field(..., description="学号 / 一卡通号")
    name: str = Field(default="", description="持卡人姓名")
    balance: float = Field(..., ge=0.0, description="卡内余额（元）")
    status: str = Field(default="正常", description="卡片状态")


# ---------------------------------------------------------------------------
# 领域模型 — GradeInfo (成绩)
# ---------------------------------------------------------------------------


class GradeInfo(BaseModel):
    """成绩信息模型 — 从 ehall 成绩查询接口解析的单条成绩。

    字段映射 (API → Model):
        KCM → course_name, ZCJ → score, XF → credit,
        KCXZDM_DISPLAY → course_type, DJCJMC → grade_label,
        XNXQDM → semester, SFJG_DISPLAY → passed

    Attributes:
        course_name: 课程名称。
        score: 总成绩（数值或等级，如 "93" / "合格"）。
        credit: 学分。
        gpa: 学分绩点。
        course_type: 课程性质（必修 / 选修 / 任选）。
        grade_label: 等级成绩名称（优 / 良 / 中 / 及格 / 不及格）。
        semester: 所属学期代码。
        passed: 是否及格。
    """

    course_name: str = Field(..., description="课程名称")
    score: str = Field(default="", description="总成绩")
    credit: float = Field(default=0.0, description="学分")
    gpa: float = Field(default=0.0, description="学分绩点")
    course_type: str = Field(default="", description="课程性质")
    grade_label: str = Field(default="", description="等级成绩名称")
    semester: str = Field(default="", description="所属学期代码")
    passed: bool = Field(default=True, description="是否及格")


# ---------------------------------------------------------------------------
# 领域模型 — ExamInfo (考试安排)
# ---------------------------------------------------------------------------


class ExamInfo(BaseModel):
    """考试安排信息模型 — 从 ehall 考试安排接口解析的单条考试。

    字段映射 (API → Model):
        KCM → course_name, KSSJMS → time_text, JASMC → location,
        ZWH → seat_number, ZJJSXM → teacher, XNXQDM → semester,
        KSMC → exam_name

    Attributes:
        course_name: 课程名称。
        time_text: 考试时间描述（如 "2025-11-21 19:00-21:00(星期五)"）。
        location: 考场教室。
        seat_number: 座位号。
        teacher: 任课教师。
        semester: 所属学期代码。
        exam_name: 考试名称（如 "期中考试" / "期末考试"）。
        credit: 学分。
    """

    course_name: str = Field(..., description="课程名称")
    time_text: str = Field(default="", description="考试时间描述")
    location: str = Field(default="", description="考场教室")
    seat_number: str = Field(default="", description="座位号")
    teacher: str = Field(default="", description="任课教师")
    semester: str = Field(default="", description="所属学期代码")
    exam_name: str = Field(default="", description="考试名称")
    credit: float = Field(default=0.0, description="学分")
