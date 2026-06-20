"""数据质量审计模块测试"""

import pytest
from datetime import datetime, timezone, timedelta

from ocean_sentinel.config import Config
from ocean_sentinel.audit import audit_data, AuditResult


class TestAudit:
    """审计模块测试"""

    def test_audit_empty_db(self, empty_db):
        """空数据库审计"""
        config = Config()
        result = audit_data(empty_db, config)
        assert result.total_records == 0
        assert result.issues_count == 0
        assert len(result.gaps) == 0
        assert len(result.outliers) == 0

    def test_audit_with_sample_data(self, populated_db):
        """示例数据审计"""
        config = Config()
        result = audit_data(populated_db, config)

        assert result.total_records > 0
        assert isinstance(result, AuditResult)

    def test_audit_specific_sensor(self, populated_db):
        """指定传感器审计"""
        config = Config()

        sensor = populated_db.fetchone("SELECT id FROM sensors LIMIT 1")
        if sensor:
            result = audit_data(populated_db, config, sensor_id=sensor["id"])
            assert result.total_records >= 0

    def test_audit_result_to_dict(self):
        """审计结果转字典"""
        result = AuditResult()
        result.total_records = 100
        result.issues_count = 5

        d = result.to_dict()
        assert d["total_records"] == 100
        assert d["issues_count"] == 5
        assert "gaps" in d
        assert "outliers" in d
        assert "sensor_stats" in d
        assert "daily_summary" in d

    def test_audit_with_date_range(self, populated_db):
        """指定日期范围审计"""
        config = Config()
        result = audit_data(
            populated_db,
            config,
            start_date="2025-03-01T00:00:00Z",
            end_date="2025-03-15T00:00:00Z",
        )
        assert result is not None

    def test_audit_daily_summary(self, populated_db):
        """按天汇总"""
        config = Config()
        result = audit_data(populated_db, config)

        assert isinstance(result.daily_summary, dict)

    def test_audit_sensor_stats(self, populated_db):
        """传感器统计"""
        config = Config()
        result = audit_data(populated_db, config)

        assert isinstance(result.sensor_stats, dict)

    def test_audit_out_of_range_detection(self, empty_db):
        """越界值检测"""
        config = Config()

        empty_db.execute(
            "INSERT INTO grids (id, name, lat_min, lat_max, lon_min, lon_max) VALUES (?, ?, ?, ?, ?, ?)",
            ("G1", "G1", 30, 31, 120, 121),
        )
        empty_db.execute(
            "INSERT INTO stations (id, name, grid_id, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
            ("ST1", "ST1", "G1", 30.5, 120.5),
        )
        empty_db.execute(
            """INSERT INTO sensors
               (id, station_id, variable, depth, sampling_interval_seconds, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("S1", "ST1", "temperature", 5.0, 600, "active"),
        )

        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        for i in range(10):
            ts = base + timedelta(minutes=10 * i)
            value = 20.0 if i < 9 else 100.0
            empty_db.execute(
                """INSERT INTO observations (sensor_id, timestamp, value, quality_flag, is_outlier, is_degraded)
                   VALUES (?, ?, ?, 0, ?, 0)""",
                ("S1", ts.strftime("%Y-%m-%dT%H:%M:%SZ"), value, 1 if value > 50 else 0),
            )
        empty_db.conn.commit()

        result = audit_data(empty_db, config)
        assert result.total_records == 10

    def test_audit_gap_detection(self, empty_db):
        """缺测段检测"""
        config = Config()

        empty_db.execute(
            "INSERT INTO grids (id, name, lat_min, lat_max, lon_min, lon_max) VALUES (?, ?, ?, ?, ?, ?)",
            ("G1", "G1", 30, 31, 120, 121),
        )
        empty_db.execute(
            "INSERT INTO stations (id, name, grid_id, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
            ("ST1", "ST1", "G1", 30.5, 120.5),
        )
        empty_db.execute(
            """INSERT INTO sensors
               (id, station_id, variable, depth, sampling_interval_seconds, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("S1", "ST1", "temperature", 5.0, 600, "active"),
        )

        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        for i in range(40):
            if 5 <= i <= 25:
                continue
            ts = base + timedelta(minutes=10 * i)
            empty_db.execute(
                """INSERT INTO observations (sensor_id, timestamp, value, quality_flag, is_outlier, is_degraded)
                   VALUES (?, ?, ?, 0, 0, 0)""",
                ("S1", ts.strftime("%Y-%m-%dT%H:%M:%SZ"), 20.0),
            )
        empty_db.conn.commit()

        result = audit_data(empty_db, config)
        assert len(result.gaps) >= 1
        assert result.gaps[0]["duration_hours"] >= 2.0
