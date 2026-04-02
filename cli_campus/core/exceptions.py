"""CLI-Campus 自定义异常体系。

所有 Adapter 层和核心层的异常都在此处统一定义，
确保上层 CLI 视图可以精确捕获并向用户呈现友好的错误提示。
"""

from __future__ import annotations


class CampusError(Exception):
    """CLI-Campus 所有异常的基类。"""


class AuthRequiredError(CampusError):
    """凭证不存在 — 用户尚未登录。

    上层 CLI 捕获此异常后应友好提示用户执行 ``campus auth login``。
    """

    def __init__(self, message: str = "请先运行 `campus auth login` 登录。") -> None:
        super().__init__(message)


class AuthFailedError(CampusError):
    """认证流程失败 — 凭证无效或 CAS 登录出错。"""

    def __init__(self, message: str = "认证失败，请检查学号和密码。") -> None:
        super().__init__(message)


class AdapterError(CampusError):
    """适配器运行时错误 — 底层数据源发生不可恢复的故障。"""

    def __init__(self, message: str = "适配器请求失败。") -> None:
        super().__init__(message)
