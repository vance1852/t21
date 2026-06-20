"""工具函数测试"""

from datetime import datetime, timezone, timedelta

import numpy as np
import pytest

from ocean_sentinel.utils import (
    parse_timestamp,
    format_timestamp,
    median_absolute_deviation,
    detect_outliers_mad,
    find_gaps,
    check_time_order,
    haversine_distance,
    depth_to_layer,
    calculate_coverage_score,
    risk_level_from_ratio,
)


class TestUtils:
    """工具函数测试"""

    def test_parse_timestamp_iso(self):
        """解析ISO格式时间戳"""
        dt = parse_timestamp("2025-01-15T10:30:00Z")
        assert dt.year == 2025
        assert dt.month == 1
        assert dt.day == 15
        assert dt.hour == 10
        assert dt.minute == 30
        assert dt.tzinfo is not None

    def test_parse_timestamp_with_space(self):
        """解析带空格的时间戳"""
        dt = parse_timestamp("2025-01-15 10:30:00")
        assert dt.year == 2025
        assert dt.hour == 10

    def test_parse_timestamp_date_only(self):
        """解析仅日期"""
        dt = parse_timestamp("2025-01-15")
        assert dt.year == 2025
        assert dt.hour == 0

    def test_parse_timestamp_invalid(self):
        """无效时间戳抛出异常"""
        with pytest.raises(ValueError):
            parse_timestamp("not-a-date")

    def test_format_timestamp(self):
        """格式化时间戳"""
        dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        ts = format_timestamp(dt)
        assert ts == "2025-01-15T10:30:00Z"

    def test_format_timestamp_naive(self):
        """格式化朴素时间"""
        dt = datetime(2025, 1, 15, 10, 30, 0)
        ts = format_timestamp(dt)
        assert "T10:30:00Z" in ts

    def test_median_absolute_deviation(self):
        """MAD计算"""
        data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 100])
        median, mad = median_absolute_deviation(data)
        assert median == pytest.approx(5.5, abs=0.1)
        assert mad > 0

    def test_median_absolute_deviation_empty(self):
        """空数据MAD"""
        data = np.array([])
        median, mad = median_absolute_deviation(data)
        assert median == 0.0
        assert mad == 0.0

    def test_detect_outliers_mad(self):
        """MAD离群点检测"""
        np.random.seed(42)
        data = np.random.normal(10, 1, 100)
        data[50] = 50.0
        data[80] = -30.0

        outliers = detect_outliers_mad(data, threshold=3.0, window_size=20, step=5)
        assert outliers[50] == True
        assert outliers[80] == True
        assert sum(outliers) >= 2

    def test_detect_outliers_mad_small_data(self):
        """少量数据的离群点检测"""
        data = np.array([1.0, 2.0])
        outliers = detect_outliers_mad(data)
        assert len(outliers) == 2
        assert not any(outliers)

    def test_find_gaps(self):
        """查找缺测段"""
        base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        timestamps = [base + timedelta(minutes=10 * i) for i in range(10)]
        for i in range(4, 7):
            timestamps[i] = base + timedelta(minutes=10 * i + 60)

        gaps = find_gaps(timestamps, 600, 1800)
        assert len(gaps) >= 1
        if gaps:
            assert gaps[0][2] > 0

    def test_find_gaps_no_gaps(self):
        """无缺测的情况"""
        base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        timestamps = [base + timedelta(minutes=10 * i) for i in range(10)]

        gaps = find_gaps(timestamps, 600, 1800)
        assert len(gaps) == 0

    def test_find_gaps_insufficient_data(self):
        """数据量不足"""
        base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        timestamps = [base]

        gaps = find_gaps(timestamps, 600, 1800)
        assert len(gaps) == 0

    def test_check_time_order_true(self):
        """时间有序"""
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        timestamps = [base + timedelta(days=i) for i in range(5)]
        assert check_time_order(timestamps)

    def test_check_time_order_false(self):
        """时间无序"""
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        timestamps = [base + timedelta(days=i) for i in range(5, 0, -1)]
        assert not check_time_order(timestamps)

    def test_haversine_distance(self):
        """球面距离计算"""
        d = haversine_distance(30.0, 120.0, 31.0, 121.0)
        assert d > 100
        assert d < 200

    def test_haversine_distance_same_point(self):
        """同一点距离为0"""
        d = haversine_distance(30.0, 120.0, 30.0, 120.0)
        assert d == pytest.approx(0.0, abs=0.01)

    def test_depth_to_layer(self):
        """深度到深度层映射"""
        layers = [
            {"id": "surface", "depth_range": [0, 10]},
            {"id": "shallow", "depth_range": [10, 50]},
            {"id": "deep", "depth_range": [200, 1000]},
        ]
        assert depth_to_layer(5.0, layers) == "surface"
        assert depth_to_layer(20.0, layers) == "shallow"
        assert depth_to_layer(500.0, layers) == "deep"
        assert depth_to_layer(2000.0, layers) is None

    def test_calculate_coverage_score(self):
        """覆盖分数计算"""
        score = calculate_coverage_score(1.0, 0.8, 0.7, 0.9)
        assert score == pytest.approx(0.504, abs=0.001)

    def test_calculate_coverage_score_base(self):
        """基础分数"""
        assert calculate_coverage_score(1.0) == 1.0

    def test_risk_level_from_ratio(self):
        """风险等级"""
        levels = [
            {"level": "critical", "threshold": 0.3},
            {"level": "warning", "threshold": 0.5},
            {"level": "ok", "threshold": 1.0},
        ]
        assert risk_level_from_ratio(0.2, levels)["level"] == "critical"
        assert risk_level_from_ratio(0.4, levels)["level"] == "warning"
        assert risk_level_from_ratio(1.0, levels)["level"] == "ok"
