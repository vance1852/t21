"""示例数据生成模块（用于init命令）"""

from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from .config import Config
from .database import DatabaseManager


def generate_sample_workspace(workspace_dir: str | Path) -> dict[str, Any]:
    """生成示例工作区，包含配置文件和示例数据"""
    workspace = Path(workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {"workspace_dir": str(workspace), "created_files": []}

    config_path = workspace / "config.yaml"
    _generate_sample_config(config_path)
    results["created_files"].append(str(config_path))

    config = Config.from_file(config_path)

    data_dir = workspace / "data"
    data_dir.mkdir(exist_ok=True)

    db_path = data_dir / "ocean_sentinel.db"
    db = DatabaseManager(db_path)
    db.initialize()

    grids = _generate_sample_grids(db, config)
    stations = _generate_sample_stations(db, grids)
    sensors = _generate_sample_sensors(db, stations, config)
    _generate_sample_calibrations(db, sensors)
    _generate_sample_observations(db, sensors, config)
    _generate_sample_maintenance(db, config)
    _generate_sample_deployment_plans(db, sensors)

    db.close()
    results["created_files"].append(str(db_path))

    sample_data_dir = workspace / "sample_data"
    sample_data_dir.mkdir(exist_ok=True)

    csv_file = sample_data_dir / "sample_temperature.csv"
    _generate_sample_csv(csv_file)
    results["created_files"].append(str(csv_file))

    json_file = sample_data_dir / "sample_salinity.json"
    _generate_sample_json(json_file)
    results["created_files"].append(str(json_file))

    yaml_file = sample_data_dir / "sample_metadata.yaml"
    _generate_sample_yaml(yaml_file)
    results["created_files"].append(str(yaml_file))

    results["stats"] = {
        "grids": len(grids),
        "stations": len(stations),
        "sensors": len(sensors),
    }

    return results


def _generate_sample_config(config_path: Path) -> None:
    """生成示例配置文件"""
    config_dict = {
        "database": {"path": "data/ocean_sentinel.db"},
        "timezone": "UTC",
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
        "grids": [
            {
                "id": "A1",
                "name": "北部近海A1",
                "bounds": {
                    "lat_min": 31.0,
                    "lat_max": 32.0,
                    "lon_min": 121.0,
                    "lon_max": 122.0,
                },
                "neighbors": ["A2", "B1"],
                "min_variables": 3,
            },
            {
                "id": "A2",
                "name": "北部近海A2",
                "bounds": {
                    "lat_min": 31.0,
                    "lat_max": 32.0,
                    "lon_min": 122.0,
                    "lon_max": 123.0,
                },
                "neighbors": ["A1", "A3", "B2"],
                "min_variables": 3,
            },
            {
                "id": "A3",
                "name": "北部近海A3",
                "bounds": {
                    "lat_min": 31.0,
                    "lat_max": 32.0,
                    "lon_min": 123.0,
                    "lon_max": 124.0,
                },
                "neighbors": ["A2", "B3"],
                "min_variables": 3,
            },
            {
                "id": "B1",
                "name": "中部近海B1",
                "bounds": {
                    "lat_min": 30.0,
                    "lat_max": 31.0,
                    "lon_min": 121.0,
                    "lon_max": 122.0,
                },
                "neighbors": ["A1", "B2", "C1"],
                "min_variables": 3,
            },
            {
                "id": "B2",
                "name": "中部近海B2",
                "bounds": {
                    "lat_min": 30.0,
                    "lat_max": 31.0,
                    "lon_min": 122.0,
                    "lon_max": 123.0,
                },
                "neighbors": ["A2", "B1", "B3", "C2"],
                "min_variables": 3,
            },
            {
                "id": "B3",
                "name": "中部近海B3",
                "bounds": {
                    "lat_min": 30.0,
                    "lat_max": 31.0,
                    "lon_min": 123.0,
                    "lon_max": 124.0,
                },
                "neighbors": ["A3", "B2", "C3"],
                "min_variables": 3,
            },
            {
                "id": "C1",
                "name": "南部近海C1",
                "bounds": {
                    "lat_min": 29.0,
                    "lat_max": 30.0,
                    "lon_min": 121.0,
                    "lon_max": 122.0,
                },
                "neighbors": ["B1", "C2"],
                "min_variables": 3,
            },
            {
                "id": "C2",
                "name": "南部近海C2",
                "bounds": {
                    "lat_min": 29.0,
                    "lat_max": 30.0,
                    "lon_min": 122.0,
                    "lon_max": 123.0,
                },
                "neighbors": ["B2", "C1", "C3"],
                "min_variables": 3,
            },
            {
                "id": "C3",
                "name": "南部近海C3",
                "bounds": {
                    "lat_min": 29.0,
                    "lat_max": 30.0,
                    "lon_min": 123.0,
                    "lon_max": 124.0,
                },
                "neighbors": ["B3", "C2"],
                "min_variables": 3,
            },
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
        "unit_conversions": {
            "temperature": {
                "celsius": 1.0,
                "fahrenheit": {"offset": -32, "scale": 0.5555555555555556},
                "kelvin": {"offset": -273.15, "scale": 1.0},
            },
            "salinity": {"psu": 1.0, "ppt": 1.0},
            "current_speed": {"m/s": 1.0, "cm/s": 0.01, "knots": 0.514444},
            "dissolved_oxygen": {"mg/L": 1.0, "ml/L": 1.429, "umol/kg": 0.032},
        },
        "report": {
            "title": "海洋观测数据质量与覆盖报告",
            "include_charts": True,
            "include_raw_data": False,
        },
    }
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _generate_sample_grids(db: DatabaseManager, config: Config) -> list[str]:
    """生成示例网格"""
    grids = config.get("grids", [])
    with db.transaction() as conn:
        for grid in grids:
            bounds = grid["bounds"]
            conn.execute(
                "INSERT INTO grids (id, name, lat_min, lat_max, lon_min, lon_max, min_variables) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    grid["id"],
                    grid["name"],
                    bounds["lat_min"],
                    bounds["lat_max"],
                    bounds["lon_min"],
                    bounds["lon_max"],
                    grid.get("min_variables", 3),
                ),
            )
        for grid in grids:
            grid_id = grid["id"]
            valid_neighbors = [n for n in grid.get("neighbors", []) if any(g["id"] == n for g in grids)]
            for neighbor_id in valid_neighbors:
                conn.execute(
                    "INSERT OR IGNORE INTO grid_neighbors (grid_id, neighbor_id) VALUES (?, ?)",
                    (grid_id, neighbor_id),
                )
    return [g["id"] for g in grids]


def _generate_sample_stations(db: DatabaseManager, grid_ids: list[str]) -> list[str]:
    """生成示例观测站"""
    stations = [
        {"id": "ST-A1-01", "name": "A1区浮标站", "grid_id": "A1", "lat": 31.5, "lon": 121.5, "depth": 50.0},
        {"id": "ST-A2-01", "name": "A2区潜标站", "grid_id": "A2", "lat": 31.5, "lon": 122.5, "depth": 80.0},
        {"id": "ST-B1-01", "name": "B1区浮标站", "grid_id": "B1", "lat": 30.5, "lon": 121.5, "depth": 60.0},
        {"id": "ST-B2-01", "name": "B2区海床基", "grid_id": "B2", "lat": 30.5, "lon": 122.5, "depth": 120.0},
        {"id": "ST-B3-01", "name": "B3区浮标站", "grid_id": "B3", "lat": 30.5, "lon": 123.5, "depth": 45.0},
        {"id": "ST-C2-01", "name": "C2区潜标站", "grid_id": "C2", "lat": 29.5, "lon": 122.5, "depth": 100.0},
    ]
    with db.transaction() as conn:
        for st in stations:
            conn.execute(
                "INSERT INTO stations (id, name, grid_id, latitude, longitude, depth, status, deployment_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    st["id"],
                    st["name"],
                    st["grid_id"],
                    st["lat"],
                    st["lon"],
                    st["depth"],
                    "active",
                    "2024-01-15T00:00:00Z",
                ),
            )
    return [s["id"] for s in stations]


def _generate_sample_sensors(db: DatabaseManager, station_ids: list[str], config: Config) -> list[str]:
    """生成示例传感器"""
    sensors_def = [
        {"station_id": "ST-A1-01", "variable": "temperature", "depth": 2.0, "interval": 600, "cost": 1.0, "stability": 0.95},
        {"station_id": "ST-A1-01", "variable": "salinity", "depth": 2.0, "interval": 600, "cost": 1.2, "stability": 0.92},
        {"station_id": "ST-A1-01", "variable": "dissolved_oxygen", "depth": 2.0, "interval": 900, "cost": 2.0, "stability": 0.85},
        {"station_id": "ST-A1-01", "variable": "current_speed", "depth": 5.0, "interval": 600, "cost": 3.0, "stability": 0.88},
        {"station_id": "ST-A2-01", "variable": "temperature", "depth": 20.0, "interval": 600, "cost": 1.0, "stability": 0.90},
        {"station_id": "ST-A2-01", "variable": "temperature", "depth": 60.0, "interval": 600, "cost": 1.1, "stability": 0.93},
        {"station_id": "ST-A2-01", "variable": "salinity", "depth": 20.0, "interval": 600, "cost": 1.2, "stability": 0.91},
        {"station_id": "ST-B1-01", "variable": "temperature", "depth": 3.0, "interval": 600, "cost": 1.0, "stability": 0.94},
        {"station_id": "ST-B1-01", "variable": "ph", "depth": 3.0, "interval": 1800, "cost": 2.5, "stability": 0.80},
        {"station_id": "ST-B2-01", "variable": "temperature", "depth": 50.0, "interval": 600, "cost": 1.0, "stability": 0.96},
        {"station_id": "ST-B2-01", "variable": "temperature", "depth": 100.0, "interval": 600, "cost": 1.1, "stability": 0.97},
        {"station_id": "ST-B2-01", "variable": "salinity", "depth": 50.0, "interval": 600, "cost": 1.2, "stability": 0.94},
        {"station_id": "ST-B2-01", "variable": "current_speed", "depth": 80.0, "interval": 600, "cost": 3.0, "stability": 0.87},
        {"station_id": "ST-B3-01", "variable": "temperature", "depth": 2.0, "interval": 600, "cost": 1.0, "stability": 0.91},
        {"station_id": "ST-B3-01", "variable": "dissolved_oxygen", "depth": 2.0, "interval": 900, "cost": 2.0, "stability": 0.83},
        {"station_id": "ST-C2-01", "variable": "temperature", "depth": 30.0, "interval": 600, "cost": 1.0, "stability": 0.92},
        {"station_id": "ST-C2-01", "variable": "salinity", "depth": 30.0, "interval": 600, "cost": 1.2, "stability": 0.90},
        {"station_id": "ST-C2-01", "variable": "ph", "depth": 30.0, "interval": 1800, "cost": 2.5, "stability": 0.78},
    ]

    sensor_ids = []
    with db.transaction() as conn:
        for i, s in enumerate(sensors_def):
            sid = f"S{i+1:03d}"
            conn.execute(
                """INSERT INTO sensors
                   (id, station_id, variable, depth, sampling_interval_seconds,
                    status, install_date, last_maintenance, maintenance_cost, historical_stability)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sid,
                    s["station_id"],
                    s["variable"],
                    s["depth"],
                    s["interval"],
                    "active",
                    "2024-01-15T00:00:00Z",
                    "2025-01-10T00:00:00Z",
                    s["cost"],
                    s["stability"],
                ),
            )
            sensor_ids.append(sid)
    return sensor_ids


def _generate_sample_calibrations(db: DatabaseManager, sensor_ids: list[str]) -> None:
    """生成示例校准记录"""
    cal_count = 0
    with db.transaction() as conn:
        for sid in sensor_ids[:10]:
            conn.execute(
                """INSERT INTO calibrations
                   (sensor_id, calibration_date, offset_before, offset_after, drift_rate, technician, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    sid,
                    "2025-01-10T08:00:00Z",
                    random.uniform(-0.2, 0.2),
                    random.uniform(-0.05, 0.05),
                    random.uniform(0.001, 0.01),
                    "张工",
                    "例行年度校准",
                ),
            )
            cal_count += 1

            if random.random() > 0.5:
                conn.execute(
                    """INSERT INTO calibrations
                       (sensor_id, calibration_date, offset_before, offset_after, drift_rate, technician, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sid,
                        "2024-06-15T08:00:00Z",
                        random.uniform(-0.3, 0.3),
                        random.uniform(-0.1, 0.1),
                        random.uniform(0.005, 0.02),
                        "李工",
                        "年中校准",
                    ),
                )
                cal_count += 1


def _generate_sample_observations(db: DatabaseManager, sensor_ids: list[str], config: Config) -> None:
    """生成带缺口的示例观测数据"""
    base_date = datetime(2025, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    num_days = 30

    variables_config = config.get("variables", {})

    with db.transaction() as conn:
        for sensor_id in sensor_ids:
            sensor_row = conn.execute(
                "SELECT variable, sampling_interval_seconds, depth FROM sensors WHERE id = ?",
                (sensor_id,),
            ).fetchone()
            if not sensor_row:
                continue

            variable = sensor_row["variable"]
            interval = sensor_row["sampling_interval_seconds"]
            var_config = variables_config.get(variable, {})
            valid_range = var_config.get("valid_range", [0, 100])

            base_value = _get_base_value(variable, sensor_row["depth"])
            noise_scale = _get_noise_scale(variable)

            total_records = int(num_days * 86400 / interval)
            timestamps = [base_date + timedelta(seconds=i * interval) for i in range(total_records)]

            gap_intervals = _generate_gap_intervals(total_records)

            for i, ts in enumerate(timestamps):
                if i in gap_intervals:
                    continue

                diurnal_phase = (ts.hour + ts.minute / 60.0) / 24.0 * 2 * 3.14159
                daily_variation = _get_daily_variation(variable) * math.sin(diurnal_phase)

                noise = random.gauss(0, noise_scale)
                value = base_value + daily_variation + noise

                if random.random() < 0.005:
                    value = base_value + random.choice([-1, 1]) * noise_scale * 10

                value = max(valid_range[0], min(valid_range[1], value))

                is_degraded = 1 if random.random() < 0.02 else 0

                ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
                try:
                    conn.execute(
                        """INSERT INTO observations
                           (sensor_id, timestamp, value, quality_flag, is_outlier, is_degraded, source_file)
                           VALUES (?, ?, ?, 0, 0, ?, ?)""",
                        (sensor_id, ts_str, round(value, 4), is_degraded, "sample_data"),
                    )
                except Exception:
                    pass


import math


def _get_base_value(variable: str, depth: float) -> float:
    """获取变量的基准值"""
    base_values = {
        "temperature": {0: 18.0, 50: 15.0, 100: 12.0, 200: 8.0},
        "salinity": {0: 32.0, 50: 33.0, 100: 33.5, 200: 34.0},
        "current_speed": {0: 0.5, 50: 0.3, 100: 0.15, 200: 0.08},
        "ph": {0: 8.1, 50: 8.0, 100: 7.9, 200: 7.8},
        "dissolved_oxygen": {0: 8.0, 50: 7.0, 100: 5.5, 200: 3.5},
    }
    depth_profiles = base_values.get(variable, {})
    depths = sorted(depth_profiles.keys())
    if depth <= depths[0]:
        return depth_profiles[depths[0]]
    if depth >= depths[-1]:
        return depth_profiles[depths[-1]]
    for i in range(len(depths) - 1):
        if depths[i] <= depth < depths[i + 1]:
            ratio = (depth - depths[i]) / (depths[i + 1] - depths[i])
            return depth_profiles[depths[i]] + ratio * (
                depth_profiles[depths[i + 1]] - depth_profiles[depths[i]]
            )
    return 10.0


def _get_noise_scale(variable: str) -> float:
    """获取变量的噪声尺度"""
    scales = {
        "temperature": 0.3,
        "salinity": 0.2,
        "current_speed": 0.1,
        "ph": 0.05,
        "dissolved_oxygen": 0.3,
    }
    return scales.get(variable, 0.5)


def _get_daily_variation(variable: str) -> float:
    """获取变量的日变化幅度"""
    variations = {
        "temperature": 1.5,
        "salinity": 0.3,
        "current_speed": 0.2,
        "ph": 0.1,
        "dissolved_oxygen": 1.0,
    }
    return variations.get(variable, 0.5)


def _generate_gap_intervals(total_records: int) -> set[int]:
    """生成缺口（缺测）索引"""
    gaps = set()
    num_gaps = random.randint(3, 6)
    for _ in range(num_gaps):
        gap_start = random.randint(0, total_records - 10)
        gap_length = random.randint(5, 50)
        for i in range(gap_start, min(gap_start + gap_length, total_records)):
            gaps.add(i)
    return gaps


def _generate_sample_maintenance(db: DatabaseManager, config: Config) -> None:
    """生成示例维护窗口"""
    with db.transaction() as conn:
        conn.execute(
            """INSERT INTO maintenance_windows (id, name, start_date, end_date, max_sensors_out)
               VALUES (?, ?, ?, ?, ?)""",
            ("mw_2025q2", "2025年第二季度维护", "2025-06-01T00:00:00Z", "2025-06-30T23:59:59Z", 3),
        )
        conn.execute(
            """INSERT INTO maintenance_sensors (window_id, sensor_id) VALUES (?, ?)""",
            ("mw_2025q2", "S001"),
        )


def _generate_sample_deployment_plans(db: DatabaseManager, sensor_ids: list[str]) -> None:
    """生成示例撤收方案"""
    with db.transaction() as conn:
        conn.execute(
            """INSERT INTO deployment_plans (id, name, plan_type, start_date, end_date, reason)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "plan_annual_service",
                "年度检修方案",
                "maintenance",
                "2025-06-10T00:00:00Z",
                "2025-06-20T23:59:59Z",
                "年度校准与设备检修",
            ),
        )
        for sid in ["S001", "S002", "S009"]:
            if sid in sensor_ids:
                conn.execute(
                    """INSERT INTO plan_sensors (plan_id, sensor_id, action) VALUES (?, ?, ?)""",
                    ("plan_annual_service", sid, "remove"),
                )


def _generate_sample_csv(file_path: Path) -> None:
    """生成示例CSV数据文件"""
    base_date = datetime(2025, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "value", "unit", "sensor_id"])
        for i in range(200):
            ts = base_date + timedelta(minutes=10 * i)
            value = 17.5 + 0.5 * math.sin(i / 20.0) + random.gauss(0, 0.2)
            writer.writerow([ts.strftime("%Y-%m-%dT%H:%M:%SZ"), round(value, 3), "celsius", "S001"])


def _generate_sample_json(file_path: Path) -> None:
    """生成示例JSON数据文件"""
    base_date = datetime(2025, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    records = []
    for i in range(150):
        ts = base_date + timedelta(minutes=10 * i)
        value = 32.5 + 0.2 * math.sin(i / 30.0) + random.gauss(0, 0.1)
        records.append(
            {
                "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "value": round(value, 4),
                "unit": "psu",
                "sensor_id": "S003",
            }
        )
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump({"records": records, "variable": "salinity"}, f, ensure_ascii=False, indent=2)


def _generate_sample_yaml(file_path: Path) -> None:
    """生成示例YAML元数据文件"""
    data = {
        "station": {
            "id": "ST-A1-01",
            "name": "A1区浮标站",
            "location": {"latitude": 31.5, "longitude": 121.5},
            "deployment_date": "2024-01-15",
        },
        "sensors": [
            {
                "id": "S001",
                "variable": "temperature",
                "depth": 2.0,
                "sampling_interval": 600,
                "unit": "celsius",
                "accuracy": 0.01,
            }
        ],
        "data_quality": {
            "last_calibration": "2025-01-10",
            "next_calibration_due": "2026-01-10",
        },
    }
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
