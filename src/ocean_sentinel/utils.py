"""通用工具函数"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Iterable, Sequence

import numpy as np


def parse_timestamp(ts_str: str, tz_name: str = "UTC") -> datetime:
    """解析时间戳字符串，统一转换为指定时区的datetime"""
    ts_str = ts_str.strip()
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d",
    ]:
        try:
            dt = datetime.strptime(ts_str, fmt)
            if dt.tzinfo is None:
                if tz_name == "UTC":
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    from datetime import timezone as dt_timezone
                    import re
                    match = re.match(r"UTC([+-])(\d{1,2})", tz_name)
                    if match:
                        sign = 1 if match.group(1) == "+" else -1
                        hours = int(match.group(2))
                        offset = dt_timezone(sign * hours * 3600)
                        dt = dt.replace(tzinfo=offset)
                    else:
                        dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"无法解析时间戳: {ts_str}")


def format_timestamp(dt: datetime) -> str:
    """格式化时间戳为ISO 8601 UTC格式"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def median_absolute_deviation(data: np.ndarray) -> tuple[float, float]:
    """计算中位数绝对偏差 (MAD)
    返回: (中位数, MAD值)
    """
    if len(data) == 0:
        return 0.0, 0.0
    median = np.median(data)
    mad = np.median(np.abs(data - median))
    return float(median), float(mad)


def detect_outliers_mad(
    values: np.ndarray,
    threshold: float = 3.0,
    window_size: int = 50,
    step: int = 10,
) -> np.ndarray:
    """基于滑动窗口MAD的离群点检测
    返回布尔数组，True表示离群点
    """
    n = len(values)
    outliers = np.zeros(n, dtype=bool)
    if n < 3:
        return outliers

    half_window = window_size // 2
    for i in range(0, n, step):
        start = max(0, i - half_window)
        end = min(n, i + half_window)
        window_data = values[start:end]
        if len(window_data) < 3:
            continue
        median, mad = median_absolute_deviation(window_data)
        if mad == 0:
            continue
        modified_z_scores = 0.6745 * (window_data - median) / mad
        window_outliers = np.abs(modified_z_scores) > threshold
        outliers[start:end] = outliers[start:end] | window_outliers

    return outliers


def find_gaps(
    timestamps: list[datetime],
    expected_interval_seconds: float,
    min_gap_duration_seconds: float,
) -> list[tuple[datetime, datetime, int]]:
    """查找连续缺测段
    返回: [(开始时间, 结束时间, 缺失点数), ...]
    """
    gaps = []
    if len(timestamps) < 2:
        return gaps

    for i in range(1, len(timestamps)):
        delta = (timestamps[i] - timestamps[i - 1]).total_seconds()
        if delta > expected_interval_seconds * 1.5 and delta >= min_gap_duration_seconds:
            missing_count = int(delta / expected_interval_seconds) - 1
            gaps.append((timestamps[i - 1], timestamps[i], max(1, missing_count)))

    return gaps


def check_time_order(timestamps: list[datetime]) -> bool:
    """检查时间序列是否按时间升序排列"""
    return all(timestamps[i] <= timestamps[i + 1] for i in range(len(timestamps) - 1))


def haversine_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """计算两点之间的球面距离（公里）"""
    R = 6371.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def depth_to_layer(depth: float, layers: Sequence[dict]) -> str | None:
    """将深度映射到深度层ID"""
    for layer in layers:
        dr = layer["depth_range"]
        if dr[0] <= depth < dr[1]:
            return layer["id"]
    return None


def calculate_coverage_score(
    base_score: float,
    distance_factor: float = 1.0,
    depth_factor: float = 1.0,
    quality_factor: float = 1.0,
) -> float:
    """计算综合覆盖分数"""
    return base_score * distance_factor * depth_factor * quality_factor


def risk_level_from_ratio(ratio: float, levels: list[dict]) -> dict:
    """根据覆盖率获取风险等级"""
    for level in sorted(levels, key=lambda x: x["threshold"]):
        if ratio <= level["threshold"]:
            return level
    return levels[-1] if levels else {"level": "unknown", "color": "white"}
