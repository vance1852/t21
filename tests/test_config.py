"""配置模块测试"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from ocean_sentinel.config import Config, DEFAULT_CONFIG, generate_sample_config


class TestConfig:
    """配置管理测试"""

    def test_default_config_exists(self):
        """默认配置存在"""
        assert DEFAULT_CONFIG is not None
        assert "variables" in DEFAULT_CONFIG
        assert "depth_layers" in DEFAULT_CONFIG
        assert "coverage" in DEFAULT_CONFIG

    def test_config_init_default(self):
        """使用默认配置初始化"""
        config = Config()
        assert config.get("timezone") == "UTC"
        assert config.get("variables.temperature.unit") == "celsius"

    def test_config_from_dict(self):
        """从字典初始化"""
        config = Config({"timezone": "UTC+8", "custom_key": "value"})
        assert config.get("timezone") == "UTC+8"
        assert config.get("custom_key") == "value"
        assert config.get("variables.temperature.unit") == "celsius"

    def test_config_from_file(self):
        """从YAML文件加载"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump({"timezone": "UTC+8"}, f)
            temp_path = f.name

        try:
            config = Config.from_file(temp_path)
            assert config.get("timezone") == "UTC+8"
        finally:
            os.unlink(temp_path)

    def test_config_file_not_found(self):
        """文件不存在时抛出异常"""
        with pytest.raises(FileNotFoundError):
            Config.from_file("/nonexistent/path/config.yaml")

    def test_get_nested_value(self):
        """获取嵌套配置值"""
        config = Config()
        assert config.get("coverage.min_coverage_ratio") == 0.7
        assert config.get("nonexistent.key", "default") == "default"

    def test_get_variable_config(self):
        """获取变量配置"""
        config = Config()
        var_cfg = config.get_variable_config("temperature")
        assert var_cfg["unit"] == "celsius"
        assert var_cfg["valid_range"] == [-2.0, 40.0]

    def test_get_variable_config_unknown(self):
        """未知变量抛出异常"""
        config = Config()
        with pytest.raises(ValueError):
            config.get_variable_config("unknown_var")

    def test_get_depth_layer(self):
        """根据深度获取深度层"""
        config = Config()
        layer = config.get_depth_layer(5.0)
        assert layer is not None
        assert layer["id"] == "surface"

        layer = config.get_depth_layer(100.0)
        assert layer is not None
        assert layer["id"] == "middle"

        layer = config.get_depth_layer(2000.0)
        assert layer is None

    def test_get_depth_layer_by_id(self):
        """根据ID获取深度层"""
        config = Config()
        layer = config.get_depth_layer_by_id("deep")
        assert layer is not None
        assert layer["id"] == "deep"

        assert config.get_depth_layer_by_id("nonexistent") is None

    def test_convert_unit_same(self):
        """相同单位不转换"""
        config = Config()
        assert config.convert_unit("temperature", 25.0, "celsius") == 25.0

    def test_convert_unit_temperature(self):
        """温度单位转换"""
        config = Config()
        celsius = config.convert_unit("temperature", 32.0, "fahrenheit")
        assert celsius == pytest.approx(0.0, abs=0.01)

    def test_convert_unit_current_speed(self):
        """流速单位转换"""
        config = Config()
        m_s = config.convert_unit("current_speed", 100.0, "cm/s")
        assert m_s == pytest.approx(1.0, abs=0.01)

    def test_convert_unit_unknown(self):
        """未知单位抛出异常"""
        config = Config()
        with pytest.raises(ValueError):
            config.convert_unit("temperature", 25.0, "unknown_unit")

    def test_get_risk_level(self):
        """获取风险等级"""
        config = Config()
        level = config.get_risk_level(0.2)
        assert level["level"] == "critical"

        level = config.get_risk_level(0.4)
        assert level["level"] == "warning"

        level = config.get_risk_level(0.6)
        assert level["level"] == "marginal"

        level = config.get_risk_level(0.85)
        assert level["level"] == "ok"

        level = config.get_risk_level(1.0)
        assert level["level"] == "ok"

    def test_save_config(self):
        """保存配置到文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "subdir" / "config.yaml"
            config = Config({"test_key": "test_value"})
            config.save(config_path)

            assert config_path.exists()
            loaded = Config.from_file(config_path)
            assert loaded.get("test_key") == "test_value"

    def test_raw_deep_copy(self):
        """原始配置是深拷贝"""
        config = Config()
        raw = config.raw
        raw["timezone"] = "modified"
        assert config.get("timezone") != "modified"

    def test_generate_sample_config(self):
        """生成示例配置"""
        sample = generate_sample_config()
        assert "grids" in sample
        assert "deployment_plans" in sample
        assert "maintenance_windows" in sample
        assert len(sample["grids"]) > 0
