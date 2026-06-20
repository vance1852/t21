"""覆盖率计算模块"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from .config import Config
from .database import DatabaseManager
from .utils import parse_timestamp, format_timestamp, depth_to_layer


class CoverageResult:
    """覆盖率计算结果"""

    def __init__(self):
        self.grid_coverage: dict[str, dict] = {}
        self.overall_ratio: float = 0.0
        self.overall_level: str = "unknown"
        self.under_min: list[str] = []
        self.variable_coverage: dict[str, float] = {}
        self.depth_layer_coverage: dict[str, float] = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_ratio": self.overall_ratio,
            "overall_level": self.overall_level,
            "under_min_grids": self.under_min,
            "grid_coverage": self.grid_coverage,
            "variable_coverage": self.variable_coverage,
            "depth_layer_coverage": self.depth_layer_coverage,
        }


def calculate_coverage(
    db: DatabaseManager,
    config: Config,
    start_date: str | None = None,
    end_date: str | None = None,
    sensors_to_exclude: list[str] | None = None,
) -> CoverageResult:
    """计算覆盖率"""
    result = CoverageResult()

    grids = _get_grids(db)
    if not grids:
        return result

    grid_neighbors = _get_grid_neighbors(db)
    sensors = _get_sensors(db, sensors_to_exclude or [])
    depth_layers = config.get("depth_layers", [])
    variables = config.get("variables", {})

    cov_config = config.get("coverage", {})
    min_ratio = cov_config.get("min_coverage_ratio", 0.7)
    adj_grid_decay = cov_config.get("adjacent_grid_decay", 0.6)
    adj_depth_decay = cov_config.get("adjacent_depth_decay", 0.7)
    degraded_factor = cov_config.get("degraded_data_factor", 0.5)
    max_sensors_per_var = cov_config.get("max_sensors_per_grid_var", 3)
    min_vars_per_grid = cov_config.get("min_variables_per_grid", 3)

    time_range = _get_time_range(db, start_date, end_date)

    sensor_health = _get_sensor_health(db, sensors, time_range, config)

    grid_var_scores: dict[str, dict[str, list[tuple[str, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for sensor in sensors:
        sid = sensor["id"]
        variable = sensor["variable"]
        depth = sensor["depth"]
        grid_id = sensor["grid_id"]
        station_status = sensor.get("status", "active")

        if station_status != "active":
            continue

        health = sensor_health.get(sid, 1.0)
        if health <= 0:
            continue

        layer = depth_to_layer(depth, depth_layers)
        if not layer:
            continue

        base_score = health

        _add_coverage_score(
            grid_var_scores, grid_id, variable, layer, sid, base_score, 1.0, 1.0
        )

        for neighbor_id in grid_neighbors.get(grid_id, []):
            if neighbor_id in grids:
                _add_coverage_score(
                    grid_var_scores,
                    neighbor_id,
                    variable,
                    layer,
                    sid,
                    base_score,
                    adj_grid_decay,
                    1.0,
                )

        layer_idx = None
        for i, dl in enumerate(depth_layers):
            if dl["id"] == layer:
                layer_idx = i
                break
        if layer_idx is not None:
            if layer_idx > 0:
                upper_layer = depth_layers[layer_idx - 1]["id"]
                _add_coverage_score(
                    grid_var_scores,
                    grid_id,
                    variable,
                    upper_layer,
                    sid,
                    base_score,
                    1.0,
                    adj_depth_decay,
                )
            if layer_idx < len(depth_layers) - 1:
                lower_layer = depth_layers[layer_idx + 1]["id"]
                _add_coverage_score(
                    grid_var_scores,
                    grid_id,
                    variable,
                    lower_layer,
                    sid,
                    base_score,
                    1.0,
                    adj_depth_decay,
                )

    for grid_id in grids:
        grid_info = {
            "grid_id": grid_id,
            "variables": {},
            "total_variables_covered": 0,
            "coverage_ratio": 0.0,
            "risk_level": "unknown",
        }

        var_scores = grid_var_scores.get(grid_id, {})
        var_count = 0

        for var_id in variables:
            layers_scores = var_scores.get(var_id, {})
            var_layer_scores = {}

            for layer in depth_layers:
                layer_id = layer["id"]
                sensor_scores = layers_scores.get(layer_id, [])

                if sensor_scores:
                    sensor_scores.sort(key=lambda x: x[1], reverse=True)
                    top_scores = sensor_scores[:max_sensors_per_var]

                    total_score = sum(s[1] for s in top_scores)
                    total_score = min(total_score, 1.0)

                    var_layer_scores[layer_id] = {
                        "score": round(total_score, 4),
                        "sensors": [
                            {"sensor_id": s[0], "contribution": round(s[1], 4)}
                            for s in top_scores
                        ],
                    }
                else:
                    var_layer_scores[layer_id] = {"score": 0.0, "sensors": []}

            has_coverage = any(
                ls["score"] >= min_ratio for ls in var_layer_scores.values()
            )
            if has_coverage:
                var_count += 1

            grid_info["variables"][var_id] = {
                "layers": var_layer_scores,
                "has_coverage": has_coverage,
            }

        ratio = var_count / max(len(variables), 1)
        grid_info["total_variables_covered"] = var_count
        grid_info["coverage_ratio"] = round(ratio, 4)
        grid_info["meets_minimum"] = var_count >= min_vars_per_grid

        risk = config.get_risk_level(ratio)
        grid_info["risk_level"] = risk["level"]

        result.grid_coverage[grid_id] = grid_info

        if not grid_info["meets_minimum"]:
            result.under_min.append(grid_id)

    total_grids = len(grids)
    covered_grids = sum(1 for g in result.grid_coverage.values() if g["meets_minimum"])
    result.overall_ratio = round(covered_grids / max(total_grids, 1), 4)
    overall_risk = config.get_risk_level(result.overall_ratio)
    result.overall_level = overall_risk["level"]

    for var_id in variables:
        var_covered = sum(
            1
            for g in result.grid_coverage.values()
            if g["variables"].get(var_id, {}).get("has_coverage", False)
        )
        result.variable_coverage[var_id] = round(var_covered / max(total_grids, 1), 4)

    for layer in depth_layers:
        layer_id = layer["id"]
        total_var_grid = len(variables) * total_grids
        covered = 0
        for grid_id in grids:
            grid_info = result.grid_coverage.get(grid_id, {})
            for var_id in variables:
                var_info = grid_info.get("variables", {}).get(var_id, {})
                layer_score = var_info.get("layers", {}).get(layer_id, {}).get("score", 0)
                if layer_score >= min_ratio:
                    covered += 1
        result.depth_layer_coverage[layer_id] = round(
            covered / max(total_var_grid, 1), 4
        )

    return result


def _add_coverage_score(
    grid_var_scores: dict,
    grid_id: str,
    variable: str,
    depth_layer: str,
    sensor_id: str,
    base_score: float,
    distance_factor: float,
    depth_factor: float,
) -> None:
    """添加覆盖分数（确保传感器不被重复满额使用）"""
    score = base_score * distance_factor * depth_factor
    if grid_id not in grid_var_scores:
        grid_var_scores[grid_id] = {}
    if variable not in grid_var_scores[grid_id]:
        grid_var_scores[grid_id][variable] = {}
    if depth_layer not in grid_var_scores[grid_id][variable]:
        grid_var_scores[grid_id][variable][depth_layer] = []

    grid_var_scores[grid_id][variable][depth_layer].append((sensor_id, score))


def _get_grids(db: DatabaseManager) -> dict[str, dict]:
    """获取所有网格"""
    rows = db.fetchall("SELECT * FROM grids")
    return {row["id"]: dict(row) for row in rows}


def _get_grid_neighbors(db: DatabaseManager) -> dict[str, list[str]]:
    """获取网格邻接关系"""
    rows = db.fetchall("SELECT grid_id, neighbor_id FROM grid_neighbors")
    neighbors: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        neighbors[row["grid_id"]].append(row["neighbor_id"])
    return dict(neighbors)


def _get_sensors(db: DatabaseManager, exclude_ids: list[str]) -> list[dict]:
    """获取传感器及其所在网格"""
    placeholders = ",".join(["?"] * len(exclude_ids)) if exclude_ids else ""
    sql = """
        SELECT s.*, st.grid_id
        FROM sensors s
        JOIN stations st ON s.station_id = st.id
    """
    params: tuple = ()
    if exclude_ids:
        sql += f" WHERE s.id NOT IN ({placeholders})"
        params = tuple(exclude_ids)

    rows = db.fetchall(sql, params)
    return [dict(row) for row in rows]


def _get_time_range(
    db: DatabaseManager, start_date: str | None, end_date: str | None
) -> tuple[datetime, datetime]:
    """获取时间范围"""
    if start_date and end_date:
        return (parse_timestamp(start_date), parse_timestamp(end_date))

    row = db.fetchone("SELECT MIN(timestamp) as min_ts, MAX(timestamp) as max_ts FROM observations")
    if row and row["min_ts"] and row["max_ts"]:
        min_ts = parse_timestamp(row["min_ts"])
        max_ts = parse_timestamp(row["max_ts"])
        if start_date:
            min_ts = parse_timestamp(start_date)
        if end_date:
            max_ts = parse_timestamp(end_date)
        return (min_ts, max_ts)

    now = datetime.now(timezone.utc)
    return (now - timedelta(days=30), now)


def _get_sensor_health(
    db: DatabaseManager,
    sensors: list[dict],
    time_range: tuple[datetime, datetime],
    config: Config,
) -> dict[str, float]:
    """计算传感器健康度（基于数据质量和完整性）"""
    health: dict[str, float] = {}
    degraded_factor = config.get("coverage.degraded_data_factor", 0.5)

    for sensor in sensors:
        sid = sensor["id"]
        interval = sensor["sampling_interval_seconds"]

        start_ts = format_timestamp(time_range[0])
        end_ts = format_timestamp(time_range[1])

        stats = db.fetchone(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN is_degraded = 1 THEN 1 ELSE 0 END) as degraded,
                      SUM(CASE WHEN is_outlier = 1 THEN 1 ELSE 0 END) as outliers
               FROM observations
               WHERE sensor_id = ? AND timestamp >= ? AND timestamp <= ?""",
            (sid, start_ts, end_ts),
        )

        if not stats or stats["total"] == 0:
            health[sid] = 0.0
            continue

        total = stats["total"]
        degraded = stats["degraded"] or 0
        outliers = stats["outliers"] or 0

        total_seconds = (time_range[1] - time_range[0]).total_seconds()
        expected_points = total_seconds / interval
        completeness = min(total / max(expected_points, 1), 1.0)

        quality = 1.0 - (outliers / max(total, 1)) * 0.3
        quality *= 1.0 - (degraded / max(total, 1)) * (1.0 - degraded_factor)

        stability = sensor.get("historical_stability", 0.9)

        health[sid] = round((completeness * 0.5 + quality * 0.3 + stability * 0.2), 4)

    return health
