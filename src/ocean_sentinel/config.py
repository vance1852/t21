"""配置加载与管理模块"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "database": {
        "path": "data/ocean_sentinel.db",
    },
    "variables": {
        "temperature": {
            "name": "海水温度",
            "unit": "celsius",
            "valid_range": [-2.0, 40.0],
            "outlier_mad_threshold": 3.0,
        },
        "salinity": {
            "name": "盐度",
            "unit": "psu",
            "valid_range": [0.0, 42.0],
            "outlier_mad_threshold": 3.0,
        },
        "current_speed": {
            "name": "流速",
            "unit": "m/s",
            "valid_range": [0.0, 5.0],
            "outlier_mad_threshold": 3.0,
        },
        "ph": {
            "name": "酸碱度",
            "unit": "pH",
            "valid_range": [6.5, 9.0],
            "outlier_mad_threshold": 3.0,
        },
        "dissolved_oxygen": {
            "name": "溶解氧",
            "unit": "mg/L",
            "valid_range": [0.0, 15.0],
            "outlier_mad_threshold": 3.0,
        },
    },
    "depth_layers": [
        {"id": "surface", "name": "表层", "depth_range": [0, 10]},
        {"id": "shallow", "name": "浅层", "depth_range": [10, 50]},
        {"id": "middle", "name": "中层", "depth_range": [50, 200]},
        {"id": "deep", "name": "深层", "depth_range": [200, 1000]},
    ],
    "coverage": {
        "min_coverage_ratio": 0.7,
        "adjacent_grid_decay": 0.6,
        "adjacent_depth_decay": 0.7,
        "degraded_data_factor": 0.5,
        "max_sensors_per_grid_var": 3,
        "min_variables_per_grid": 3,
    },
    "risk_levels": [
        {"level": "critical", "threshold": 0.3, "color": "red"},
        {"level": "warning", "threshold": 0.5, "color": "yellow"},
        {"level": "marginal", "threshold": 0.7, "color": "bright_yellow"},
        {"level": "ok", "threshold": 1.0, "color": "green"},
    ],
    "audit": {
        "gap_min_duration_minutes": 120,
        "jitter_window_minutes": 30,
        "jitter_std_ratio": 2.0,
        "drift_window_hours": 24,
        "drift_std_threshold": 2.0,
        "clock_offset_threshold_seconds": 60,
        "mad_window_size": 50,
        "mad_step": 10,
    },
    "timezone": "UTC",
    "unit_conversions": {
        "temperature": {
            "celsius": 1.0,
            "fahrenheit": {"offset": -32, "scale": 5.0 / 9.0},
            "kelvin": {"offset": -273.15, "scale": 1.0},
        },
        "salinity": {
            "psu": 1.0,
            "ppt": 1.0,
        },
        "current_speed": {
            "m/s": 1.0,
            "cm/s": 0.01,
            "knots": 0.514444,
        },
        "dissolved_oxygen": {
            "mg/L": 1.0,
            "ml/L": 1.429,
            "umol/kg": 0.032,
        },
    },
    "maintenance_windows": [],
    "deployment_plans": [],
    "report": {
        "title": "海洋观测数据质量与覆盖报告",
        "include_charts": True,
        "include_raw_data": False,
    },
}


class Config:
    """配置管理类"""

    def __init__(self, config_dict: dict[str, Any] | None = None):
        self._config = copy.deepcopy(DEFAULT_CONFIG)
        if config_dict:
            self._deep_update(self._config, config_dict)

    @classmethod
    def from_file(cls, config_path: str | Path) -> "Config":
        """从YAML文件加载配置"""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        with open(path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        return cls(user_config)

    def _deep_update(self, base: dict, update: dict) -> None:
        """深度更新字典"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = copy.deepcopy(value)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项，支持点号分隔的路径"""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    @property
    def raw(self) -> dict[str, Any]:
        """获取原始配置字典的深拷贝"""
        return copy.deepcopy(self._config)

    def get_variable_config(self, variable_id: str) -> dict[str, Any]:
        """获取变量配置"""
        variables = self.get("variables", {})
        if variable_id not in variables:
            raise ValueError(f"未知变量: {variable_id}")
        return variables[variable_id]

    def get_depth_layer(self, depth: float) -> dict[str, Any] | None:
        """根据深度获取深度层配置"""
        for layer in self.get("depth_layers", []):
            depth_range = layer["depth_range"]
            if depth_range[0] <= depth < depth_range[1]:
                return layer
        return None

    def get_depth_layer_by_id(self, layer_id: str) -> dict[str, Any] | None:
        """根据ID获取深度层配置"""
        for layer in self.get("depth_layers", []):
            if layer["id"] == layer_id:
                return layer
        return None

    def get_risk_level(self, coverage_ratio: float) -> dict[str, Any]:
        """根据覆盖率获取风险等级"""
        for level in self.get("risk_levels", []):
            if coverage_ratio <= level["threshold"]:
                return level
        return self.get("risk_levels", [])[-1]

    def convert_unit(
        self, variable_id: str, value: float, from_unit: str
    ) -> float:
        """单位转换"""
        conversions = self.get(f"unit_conversions.{variable_id}", {})
        target_unit = self.get(f"variables.{variable_id}.unit")
        if from_unit == target_unit:
            return value
        if from_unit not in conversions:
            raise ValueError(f"未知单位 {from_unit} 用于变量 {variable_id}")
        conv = conversions[from_unit]
        if isinstance(conv, dict):
            return (value + conv.get("offset", 0)) * conv.get("scale", 1.0)
        else:
            return value * conv

    def save(self, config_path: str | Path) -> None:
        """保存配置到文件"""
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                self._config, f, default_flow_style=False, allow_unicode=True, sort_keys=False
            )


def generate_sample_config() -> dict[str, Any]:
    """生成示例配置（带注释性数据）"""
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["grids"] = [
        {
            "id": "A1",
            "name": "A1网格",
            "bounds": {"lat_min": 30.0, "lat_max": 31.0, "lon_min": 120.0, "lon_max": 121.0},
            "neighbors": ["A2", "B1"],
        },
        {
            "id": "A2",
            "name": "A2网格",
            "bounds": {"lat_min": 30.0, "lat_max": 31.0, "lon_min": 121.0, "lon_max": 122.0},
            "neighbors": ["A1", "A3", "B2"],
        },
        {
            "id": "B1",
            "name": "B1网格",
            "bounds": {"lat_min": 29.0, "lat_max": 30.0, "lon_min": 120.0, "lon_max": 121.0},
            "neighbors": ["A1", "B2"],
        },
    ]
    config["deployment_plans"] = [
        {
            "id": "plan_a",
            "name": "A类设备撤收方案",
            "sensors_to_remove": ["S001", "S002"],
            "start_date": "2025-06-01",
            "end_date": "2025-06-15",
            "reason": "年度校准维护",
        },
    ]
    config["maintenance_windows"] = [
        {
            "id": "mw_2025q2",
            "name": "2025年第二季度维护窗口",
            "start_date": "2025-06-01",
            "end_date": "2025-06-30",
            "max_sensors_out": 2,
        },
    ]
    return config
