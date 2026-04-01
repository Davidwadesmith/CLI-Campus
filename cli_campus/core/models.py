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
    OTHER = "other"


class AdapterSource(str, Enum):
    """数据来源枚举 — 标记 CampusEvent 来自哪个 Adapter / 供应商。"""

    SEU_CAS = "seu_cas"
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
    """课程信息模型 — 从教务系统中解析出的单节课程。

    Attributes:
        course_id: 课程编号（如 ``B0900020S``）。
        name: 课程名称。
        teacher: 授课教师。
        location: 上课地点（教学楼 + 教室）。
        weekday: 星期几（1=周一 … 7=周日）。
        start_period: 开始节次。
        end_period: 结束节次。
        weeks: 上课周次列表（如 ``[1,2,3,…,16]``）。
    """

    course_id: str = Field(..., description="课程编号")
    name: str = Field(..., description="课程名称")
    teacher: str = Field(default="", description="授课教师")
    location: str = Field(default="", description="上课地点")
    weekday: int = Field(..., ge=1, le=7, description="星期几 (1~7)")
    start_period: int = Field(..., ge=1, description="开始节次")
    end_period: int = Field(..., ge=1, description="结束节次")
    weeks: list[int] = Field(default_factory=list, description="上课周次列表")


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
