"""数据质量审计模块"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from .config import Config
from .database import DatabaseManager
from .utils import (
    parse_timestamp,
    format_timestamp,
    detect_outliers_mad,
    find_gaps,
    median_absolute_deviation,
)


class AuditResult:
    """审计结果"""

    def __init__(self):
        self.gaps: list[dict] = []
        self.outliers: list[dict] = []
        self.jitters: list[dict] = []
        self.drifts: list[dict] = []
        self.clock_offsets: list[dict] = []
        self.out_of_range: list[dict] = []
        self.daily_summary: dict[str, dict] = {}
        self.sensor_stats: dict[str, dict] = {}
        self.total_records: int = 0
        self.issues_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "issues_count": self.issues_count,
            "gaps": [g for g in self.gaps],
            "outliers": [o for o in self.outliers],
            "jitters": [j for j in self.jitters],
            "drifts": [d for d in self.drifts],
            "clock_offsets": [c for c in self.clock_offsets],
            "out_of_range": [o for o in self.out_of_range],
            "sensor_stats": self.sensor_stats,
            "daily_summary": self.daily_summary,
        }


def audit_data(
    db: DatabaseManager,
    config: Config,
    sensor_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> AuditResult:
    """执行数据质量审计"""
    result = AuditResult()

    sensors = _get_sensors(db, sensor_id)
    if not sensors:
        return result

    for sensor in sensors:
        sid = sensor["id"]
        variable = sensor["variable"]
        interval = sensor["sampling_interval_seconds"]

        observations = _get_observations(db, sid, start_date, end_date)
        if not observations:
            continue

        timestamps = [parse_timestamp(row["timestamp"]) for row in observations]
        values = np.array([row["value"] for row in observations], dtype=float)
        result.total_records += len(observations)

        _analyze_gaps(result, sid, timestamps, interval, config)
        _analyze_outliers(result, sid, variable, values, timestamps, config)
        _analyze_jitter(result, sid, timestamps, interval, config)
        _analyze_drift(result, sid, variable, values, timestamps, db, config)
        _analyze_out_of_range(result, sid, variable, values, timestamps, config)
        _analyze_clock_offset(result, sid, timestamps, interval, config)

        _update_sensor_stats(result, sid, len(observations))

    _build_daily_summary(result)
    result.issues_count = (
        len(result.gaps)
        + len(result.outliers)
        + len(result.jitters)
        + len(result.drifts)
        + len(result.clock_offsets)
        + len(result.out_of_range)
    )

    return result


def _get_sensors(db: DatabaseManager, sensor_id: str | None) -> list[dict]:
    """获取传感器列表"""
    if sensor_id:
        row = db.fetchone("SELECT * FROM sensors WHERE id = ?", (sensor_id,))
        return [dict(row)] if row else []
    rows = db.fetchall("SELECT * FROM sensors")
    return [dict(row) for row in rows]


def _get_observations(
    db: DatabaseManager,
    sensor_id: str,
    start_date: str | None,
    end_date: str | None,
) -> list[dict]:
    """获取观测数据"""
    sql = "SELECT * FROM observations WHERE sensor_id = ?"
    params: list = [sensor_id]

    if start_date:
        sql += " AND timestamp >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND timestamp <= ?"
        params.append(end_date)

    sql += " ORDER BY timestamp ASC"
    rows = db.fetchall(sql, tuple(params))
    return [dict(row) for row in rows]


def _analyze_gaps(
    result: AuditResult,
    sensor_id: str,
    timestamps: list[datetime],
    interval: int,
    config: Config,
) -> None:
    """分析缺测段"""
    min_gap_seconds = config.get("audit.gap_min_duration_minutes", 120) * 60

    gaps = find_gaps(timestamps, interval, min_gap_seconds)
    for start, end, missing in gaps:
        duration = (end - start).total_seconds() / 3600.0
        result.gaps.append(
            {
                "sensor_id": sensor_id,
                "start": format_timestamp(start),
                "end": format_timestamp(end),
                "duration_hours": round(duration, 2),
                "missing_points": missing,
                "severity": _gap_severity(duration),
            }
        )


def _gap_severity(duration_hours: float) -> str:
    """根据缺测时长确定严重程度"""
    if duration_hours >= 24:
        return "critical"
    elif duration_hours >= 6:
        return "warning"
    else:
        return "marginal"


def _analyze_outliers(
    result: AuditResult,
    sensor_id: str,
    variable: str,
    values: np.ndarray,
    timestamps: list[datetime],
    config: Config,
) -> None:
    """分析离群点（基于滑动窗口MAD）"""
    threshold = config.get(f"variables.{variable}.outlier_mad_threshold", 3.0)
    window_size = config.get("audit.mad_window_size", 50)
    step = config.get("audit.mad_step", 10)

    outlier_mask = detect_outliers_mad(values, threshold, window_size, step)

    for i, is_outlier in enumerate(outlier_mask):
        if is_outlier:
            result.outliers.append(
                {
                    "sensor_id": sensor_id,
                    "timestamp": format_timestamp(timestamps[i]),
                    "value": float(values[i]),
                    "method": "sliding_mad",
                    "severity": "warning",
                }
            )


def _analyze_jitter(
    result: AuditResult,
    sensor_id: str,
    timestamps: list[datetime],
    interval: int,
    config: Config,
) -> None:
    """分析短时抖动（采样间隔异常波动）"""
    if len(timestamps) < 3:
        return

    window_minutes = config.get("audit.jitter_window_minutes", 30)
    std_ratio = config.get("audit.jitter_std_ratio", 2.0)

    intervals = np.array(
        [(timestamps[i] - timestamps[i - 1]).total_seconds() for i in range(1, len(timestamps))]
    )

    window_size = max(3, int(window_minutes * 60 / interval))

    for i in range(window_size, len(intervals)):
        window = intervals[i - window_size : i]
        mean_interval = np.mean(window)
        std_interval = np.std(window)

        if std_interval > 0 and mean_interval > 0:
            cv = std_interval / mean_interval
            if cv > 0.3:
                result.jitters.append(
                    {
                        "sensor_id": sensor_id,
                        "start": format_timestamp(timestamps[i - window_size]),
                        "end": format_timestamp(timestamps[i]),
                        "mean_interval": round(mean_interval, 1),
                        "std_interval": round(std_interval, 1),
                        "cv": round(cv, 3),
                        "severity": "marginal",
                    }
                )
                break


def _analyze_drift(
    result: AuditResult,
    sensor_id: str,
    variable: str,
    values: np.ndarray,
    timestamps: list[datetime],
    db: DatabaseManager,
    config: Config,
) -> None:
    """分析校准前后漂移"""
    calibrations = db.fetchall(
        "SELECT * FROM calibrations WHERE sensor_id = ? ORDER BY calibration_date",
        (sensor_id,),
    )

    if not calibrations or len(values) < 10:
        return

    drift_threshold = config.get("audit.drift_std_threshold", 2.0)
    window_hours = config.get("audit.drift_window_hours", 24)

    for cal in calibrations:
        cal_date = parse_timestamp(cal["calibration_date"])

        before_mask = []
        after_mask = []
        for i, ts in enumerate(timestamps):
            delta = (cal_date - ts).total_seconds() / 3600.0
            if 0 < delta <= window_hours:
                before_mask.append(i)
            elif -window_hours <= delta < 0:
                after_mask.append(i)

        if len(before_mask) >= 5 and len(after_mask) >= 5:
            before_vals = values[before_mask]
            after_vals = values[after_mask]

            before_mean = np.mean(before_vals)
            before_std = np.std(before_vals)
            after_mean = np.mean(after_vals)
            after_std = np.std(after_vals)

            shift = abs(after_mean - before_mean)
            pooled_std = np.sqrt((before_std**2 + after_std**2) / 2)

            if pooled_std > 0 and shift > drift_threshold * pooled_std:
                result.drifts.append(
                    {
                        "sensor_id": sensor_id,
                        "calibration_date": cal["calibration_date"],
                        "before_mean": round(float(before_mean), 4),
                        "after_mean": round(float(after_mean), 4),
                        "shift": round(float(shift), 4),
                        "pooled_std": round(float(pooled_std), 4),
                        "severity": "warning" if shift > drift_threshold * pooled_std else "marginal",
                    }
                )


def _analyze_out_of_range(
    result: AuditResult,
    sensor_id: str,
    variable: str,
    values: np.ndarray,
    timestamps: list[datetime],
    config: Config,
) -> None:
    """分析越界值"""
    var_config = config.get_variable_config(variable)
    valid_range = var_config.get("valid_range")
    if not valid_range:
        return

    for i, val in enumerate(values):
        if val < valid_range[0] or val > valid_range[1]:
            result.out_of_range.append(
                {
                    "sensor_id": sensor_id,
                    "timestamp": format_timestamp(timestamps[i]),
                    "value": float(val),
                    "valid_range": valid_range,
                    "severity": "critical" if abs(val - sum(valid_range)/2) > (valid_range[1]-valid_range[0]) else "warning",
                }
            )


def _analyze_clock_offset(
    result: AuditResult,
    sensor_id: str,
    timestamps: list[datetime],
    interval: int,
    config: Config,
) -> None:
    """分析时钟偏移（与标称采样间隔的系统性偏差）"""
    if len(timestamps) < 10:
        return

    threshold = config.get("audit.clock_offset_threshold_seconds", 60)

    intervals = np.array(
        [(timestamps[i] - timestamps[i - 1]).total_seconds() for i in range(1, len(timestamps))]
    )

    median_interval = float(np.median(intervals))
    offset = abs(median_interval - interval)

    if offset > threshold:
        result.clock_offsets.append(
            {
                "sensor_id": sensor_id,
                "expected_interval": interval,
                "actual_median_interval": round(median_interval, 2),
                "offset_seconds": round(offset, 2),
                "severity": "warning",
            }
        )


def _update_sensor_stats(result: AuditResult, sensor_id: str, record_count: int) -> None:
    """更新传感器统计"""
    if sensor_id not in result.sensor_stats:
        result.sensor_stats[sensor_id] = {
            "record_count": 0,
            "gap_count": 0,
            "outlier_count": 0,
            "jitter_count": 0,
            "drift_count": 0,
            "out_of_range_count": 0,
        }
    result.sensor_stats[sensor_id]["record_count"] = record_count


def _build_daily_summary(result: AuditResult) -> None:
    """构建按天汇总"""
    daily: dict[str, dict] = defaultdict(
        lambda: {"issues": 0, "gaps": 0, "outliers": 0, "critical_count": 0}
    )

    for gap in result.gaps:
        day = gap["start"][:10]
        daily[day]["gaps"] += 1
        daily[day]["issues"] += 1
        if gap["severity"] == "critical":
            daily[day]["critical_count"] += 1

    for outlier in result.outliers:
        day = outlier["timestamp"][:10]
        daily[day]["outliers"] += 1
        daily[day]["issues"] += 1

    for issue_list, key in [
        (result.jitters, "jitter"),
        (result.drifts, "drift"),
        (result.out_of_range, "out_of_range"),
    ]:
        for issue in issue_list:
            ts = issue.get("timestamp") or issue.get("start") or issue.get("calibration_date", "")
            day = ts[:10] if ts else "unknown"
            daily[day][key] = daily[day].get(key, 0) + 1
            daily[day]["issues"] += 1

    result.daily_summary = dict(sorted(daily.items()))
