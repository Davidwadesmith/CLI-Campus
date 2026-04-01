"""本地配置与环境变量加载。

管理 CLI-Campus 的运行时配置，包括：
- 当前活跃的校园命名空间（为多租户架构预留）
- 全局默认参数（超时、输出格式等）
- 配置文件路径约定
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 路径约定
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_DIR: Path = Path.home() / ".cli-campus"
DEFAULT_CONFIG_FILE: Path = DEFAULT_CONFIG_DIR / "config.json"


# ---------------------------------------------------------------------------
# 配置模型
# ---------------------------------------------------------------------------


class CampusConfig(BaseModel):
    """CLI-Campus 全局配置模型。

    Attributes:
        campus_id: 当前校园标识（如 "seu"）。
        campus_name: 校园全称（如 "东南大学"）。
        config_dir: 配置文件目录路径。
        default_timeout: HTTP 请求默认超时秒数。
        json_output: 全局默认是否以 JSON 格式输出。
        adapters: 各 Adapter 的个性化配置。
    """

    campus_id: str = Field(default="seu", description="当前校园标识")
    campus_name: str = Field(default="东南大学", description="校园全称")
    config_dir: Path = Field(default=DEFAULT_CONFIG_DIR, description="配置文件目录路径")
    default_timeout: int = Field(default=10, ge=1, description="默认超时秒数")
    json_output: bool = Field(default=False, description="默认 JSON 输出模式")
    adapters: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="各 Adapter 的个性化配置"
    )


def load_config(config_path: Optional[Path] = None) -> CampusConfig:
    """加载配置文件。

    如果配置文件不存在，则返回默认配置。

    Args:
        config_path: 配置文件路径，默认为 ``~/.cli-campus/config.json``。

    Returns:
        解析后的 CampusConfig 实例。
    """
    path = config_path or DEFAULT_CONFIG_FILE

    if path.exists():
        return CampusConfig.model_validate_json(path.read_text(encoding="utf-8"))

    return CampusConfig()
