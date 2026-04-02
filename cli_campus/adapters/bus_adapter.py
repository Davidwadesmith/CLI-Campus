"""校车时刻表适配器 — 从本地 JSON 加载并查询校园接驳车时刻。

数据来源: 东南大学总务处 (zwc.seu.edu.cn) 官方公告。
本适配器属于 *静态适配器*，不需要网络认证，直接读取打包在项目中的
``data/bus_schedule.json`` 文件。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from hashlib import md5
from importlib import resources
from typing import Any

from cli_campus.core.interfaces import BaseCampusAdapter
from cli_campus.core.models import (
    AdapterSource,
    BusRoute,
    CampusEvent,
    EventCategory,
)

logger = logging.getLogger(__name__)


def _load_schedule() -> dict[str, Any]:
    """从包内 ``data/bus_schedule.json`` 加载时刻表数据。"""
    ref = resources.files("cli_campus") / "data" / "bus_schedule.json"
    return json.loads(ref.read_text(encoding="utf-8"))


class BusAdapter(BaseCampusAdapter):
    """校车时刻表静态适配器。

    与其他 Adapter 不同，BusAdapter 不需要网络认证，
    直接从本地 JSON 文件读取时刻表数据。

    config 参数（可选）：
        route: 按线路名称筛选（模糊匹配）。
        schedule_type: 时刻表类型 ("workday" | "holiday" | "spring_festival")。
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        schedule_data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(config=config or {})
        self._data = schedule_data or _load_schedule()

    async def check_auth(self) -> bool:
        """静态适配器无需认证，始终返回 True。"""
        return True

    async def fetch(self, **kwargs: Any) -> list[CampusEvent]:
        """查询校车时刻并返回 CampusEvent 列表。

        支持的 kwargs:
            route: 按线路名称筛选（模糊匹配）。
            schedule_type: 时刻表类型。
        """
        route_filter: str = kwargs.get("route") or self.config.get("route", "")
        schedule_type: str = kwargs.get("schedule_type") or self.config.get(
            "schedule_type", ""
        )

        events: list[CampusEvent] = []

        for route_cfg in self._data.get("routes", []):
            route_name: str = route_cfg["name"]
            # 模糊匹配线路名
            if route_filter and route_filter not in route_name:
                short = route_cfg.get("short_name", "")
                if route_filter not in short:
                    continue

            for direction in route_cfg.get("directions", []):
                dep_stop: str = direction["from"]
                arr_stop: str = direction["to"]

                schedules: dict[str, list[str]] = direction.get("schedules", {})
                for stype, departures in schedules.items():
                    if schedule_type and stype != schedule_type:
                        continue

                    for dep_time in departures:
                        bus = BusRoute(
                            route_name=route_name,
                            departure_time=dep_time,
                            departure_stop=dep_stop,
                            arrival_stop=arr_stop,
                            note=_schedule_type_label(stype),
                        )

                        event_hash = md5(
                            f"{route_name}:{dep_stop}:{arr_stop}:{stype}:{dep_time}".encode()
                        ).hexdigest()[:12]

                        events.append(
                            CampusEvent(
                                id=f"static_json:bus:{event_hash}",
                                source=AdapterSource.STATIC_JSON,
                                category=EventCategory.BUS,
                                title=f"{route_name} {dep_stop}→{arr_stop} {dep_time}",
                                content=bus.model_dump(),
                                timestamp=datetime.now(),
                            )
                        )

        # 按发车时间排序
        events.sort(key=lambda e: e.content.get("departure_time", ""))
        return events

    def get_route_names(self) -> list[str]:
        """返回所有线路名称列表（用于 CLI 提示）。"""
        return [r["name"] for r in self._data.get("routes", [])]

    def get_schedule_types(self, route_name: str = "") -> set[str]:
        """返回指定线路可用的时刻表类型集合。"""
        types: set[str] = set()
        for route_cfg in self._data.get("routes", []):
            if route_name and route_name not in route_cfg["name"]:
                continue
            for direction in route_cfg.get("directions", []):
                types.update(direction.get("schedules", {}).keys())
        return types

    def get_notes(self, route_name: str = "") -> list[str]:
        """返回线路备注信息。"""
        notes: list[str] = []
        for route_cfg in self._data.get("routes", []):
            if route_name and route_name not in route_cfg["name"]:
                continue
            notes.extend(route_cfg.get("notes", []))
        return notes

    def get_meta(self) -> dict[str, Any]:
        """返回数据元信息（版本、来源等）。"""
        return self._data.get("meta", {})


def _schedule_type_label(stype: str) -> str:
    """将 schedule type key 转换为中文标签。"""
    return {
        "workday": "工作日",
        "holiday": "节假日",
        "spring_festival": "春节",
    }.get(stype, stype)
