"""Tests for config module."""

from __future__ import annotations

from pathlib import Path

from cli_campus.core.config import CampusConfig, load_config


class TestCampusConfig:
    """配置模型测试。"""

    def test_default_config(self) -> None:
        config = CampusConfig()
        assert config.campus_id == "seu"
        assert config.campus_name == "东南大学"
        assert config.default_timeout == 10
        assert config.json_output is False
        assert config.adapters == {}

    def test_custom_config(self) -> None:
        config = CampusConfig(
            campus_id="nju",
            campus_name="南京大学",
            default_timeout=30,
            adapters={"zhengfang": {"base_url": "https://jwc.nju.edu.cn"}},
        )
        assert config.campus_id == "nju"
        assert config.adapters["zhengfang"]["base_url"] == "https://jwc.nju.edu.cn"

    def test_load_config_nonexistent_returns_default(self) -> None:
        config = load_config(Path("/nonexistent/path/config.json"))
        assert config.campus_id == "seu"

    def test_config_json_roundtrip(self, tmp_path: Path) -> None:
        original = CampusConfig(
            campus_id="test",
            campus_name="测试大学",
            default_timeout=5,
        )
        config_file = tmp_path / "config.json"
        config_file.write_text(original.model_dump_json(), encoding="utf-8")

        loaded = load_config(config_file)
        assert loaded.campus_id == "test"
        assert loaded.campus_name == "测试大学"
        assert loaded.default_timeout == 5
