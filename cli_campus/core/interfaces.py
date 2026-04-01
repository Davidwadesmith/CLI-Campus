"""Campus Adapter Protocol — 适配器抽象基类定义。

所有具体的 Adapter（无论对接正方教务、超星学习通还是静态 JSON）
都必须继承 ``BaseCampusAdapter`` 并实现其抽象方法。

核心层（CLI 视图 / Agent 调用）仅通过此接口与 Adapter 交互，
绝不直接依赖任何具体的爬虫或请求逻辑。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from cli_campus.core.models import CampusEvent


class BaseCampusAdapter(ABC):
    """校园数据适配器抽象基类。

    所有 Adapter 必须继承此类并实现以下抽象方法：

    - ``check_auth()``: 验证当前凭证是否有效。
    - ``fetch()``: 拉取数据并返回标准化的 ``CampusEvent`` 列表。

    Adapter 的职责边界：
    1. 屏蔽底层数据源差异（HTTP API / HTML / PDF / SQLite）。
    2. 将原始数据洗净并转换为 Pydantic 模型。
    3. 管理自身的 Session / Cookie / Token 生命周期。

    Example:
        >>> class MyAdapter(BaseCampusAdapter):
        ...     async def check_auth(self) -> bool:
        ...         return True
        ...     async def fetch(self, **kwargs) -> list[CampusEvent]:
        ...         return []
        >>> adapter = MyAdapter(config={"base_url": "https://example.com"})
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """初始化 Adapter。

        Args:
            config: 适配器配置字典，通常包含 base_url、timeout 等参数。
                    具体内容由各 Adapter 子类自行定义。
        """
        self.config = config

    @abstractmethod
    async def check_auth(self) -> bool:
        """验证当前身份凭证是否有效。

        Returns:
            ``True`` 表示凭证有效、可以正常拉取数据；
            ``False`` 表示凭证已失效，需要重新登录。
        """
        ...

    @abstractmethod
    async def fetch(self, **kwargs: Any) -> list[CampusEvent]:
        """拉取数据并返回标准化的 CampusEvent 列表。

        子类实现此方法时，应当：
        1. 使用自身维护的 Session / Token 发起请求。
        2. 将原始响应数据解析为对应的领域模型（如 CourseInfo）。
        3. 封装为 CampusEvent 信封返回。

        Args:
            **kwargs: 查询参数，由调用方传入（如 semester、week 等）。

        Returns:
            标准化的 CampusEvent 实例列表。

        Raises:
            AuthenticationError: 如果凭证已失效且无法自动刷新。
            AdapterError: 如果底层数据源发生不可恢复的错误。
        """
        ...

    def adapter_name(self) -> str:
        """返回适配器名称（默认为类名）。"""
        return self.__class__.__name__
