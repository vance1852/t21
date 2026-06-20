"""数据导入模块测试"""

import csv
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import yaml

from ocean_sentinel.config import Config
from ocean_sentinel.database import DatabaseManager
from ocean_sentinel.ingest import (
    ingest_file,
    IngestError,
    IngestResult,
    check_time_order,
    record_import_batch,
)


@pytest.fixture
def test_db_with_sensor(temp_dir):
    """带传感器的测试数据库"""
    db = DatabaseManager(temp_dir / "test.db")
    db.initialize()

    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO grids (id, name, lat_min, lat_max, lon_min, lon_max) VALUES (?, ?, ?, ?, ?, ?)",
            ("A1", "Test Grid", 30.0, 31.0, 120.0, 121.0),
        )
        conn.execute(
            "INSERT INTO stations (id, name, grid_id, latitude, longitude, depth) VALUES (?, ?, ?, ?, ?, ?)",
            ("ST001", "Test Station", "A1", 30.5, 120.5, 50.0),
        )
        conn.execute(
            """INSERT INTO sensors
               (id, station_id, variable, depth, sampling_interval_seconds, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("S001", "ST001", "temperature", 5.0, 600, "active"),
        )
        conn.execute(
            """INSERT INTO sensors
               (id, station_id, variable, depth, sampling_interval_seconds, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("S002", "ST001", "salinity", 5.0, 600, "active"),
        )

    yield db
    db.close()


class TestIngest:
    """导入模块测试"""

    def test_ingest_csv(self, temp_dir, test_db_with_sensor):
        """导入CSV文件"""
        config = Config()
        csv_file = temp_dir / "test.csv"

        base_time = datetime(2025, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "value", "sensor_id", "unit"])
            for i in range(10):
                ts = base_time + timedelta(minutes=10 * i)
                writer.writerow([ts.strftime("%Y-%m-%dT%H:%M:%SZ"), 15.0 + i * 0.1, "S001", "celsius"])

        result = ingest_file(csv_file, test_db_with_sensor, config)

        assert result.total_records == 10
        assert result.imported_records == 10
        assert result.error_records == 0
        assert "S001" in result.sensor_ids

        obs_count = test_db_with_sensor.fetchone(
            "SELECT COUNT(*) as cnt FROM observations WHERE sensor_id = ?",
            ("S001",),
        )
        assert obs_count["cnt"] == 10

    def test_ingest_json(self, temp_dir, test_db_with_sensor):
        """导入JSON文件"""
        config = Config()
        json_file = temp_dir / "test.json"

        base_time = datetime(2025, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
        records = []
        for i in range(5):
            ts = base_time + timedelta(minutes=10 * i)
            records.append({
                "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "value": 15.0 + i * 0.1,
                "sensor_id": "S001",
                "unit": "celsius",
            })

        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({"records": records}, f)

        result = ingest_file(json_file, test_db_with_sensor, config)
        assert result.total_records == 5
        assert result.imported_records == 5

    def test_ingest_yaml(self, temp_dir, test_db_with_sensor):
        """导入YAML文件"""
        config = Config()
        yaml_file = temp_dir / "test.yaml"

        base_time = datetime(2025, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
        records = []
        for i in range(3):
            ts = base_time + timedelta(minutes=10 * i)
            records.append({
                "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "value": 15.0 + i * 0.1,
                "sensor_id": "S001",
                "unit": "celsius",
            })

        with open(yaml_file, "w", encoding="utf-8") as f:
            yaml.dump({"records": records}, f)

        result = ingest_file(yaml_file, test_db_with_sensor, config)
        assert result.total_records == 3
        assert result.imported_records == 3

    def test_ingest_unknown_sensor(self, temp_dir, test_db_with_sensor):
        """未知传感器"""
        config = Config()
        csv_file = temp_dir / "test.csv"

        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "value", "sensor_id"])
            writer.writerow(["2025-01-01T00:00:00Z", 15.0, "S999"])

        result = ingest_file(csv_file, test_db_with_sensor, config)
        assert result.skipped_records == 1
        assert len(result.errors) > 0

    def test_ingest_duplicates(self, temp_dir, test_db_with_sensor):
        """重复记录处理"""
        config = Config()
        csv_file = temp_dir / "test.csv"

        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "value", "sensor_id"])
            writer.writerow(["2025-01-01T00:00:00Z", 15.0, "S001"])
            writer.writerow(["2025-01-01T00:00:00Z", 16.0, "S001"])

        result = ingest_file(csv_file, test_db_with_sensor, config)
        assert result.imported_records == 1
        assert result.duplicates == 1

    def test_ingest_out_of_range(self, temp_dir, test_db_with_sensor):
        """越界值标记"""
        config = Config()
        csv_file = temp_dir / "test.csv"

        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "value", "sensor_id"])
            writer.writerow(["2025-01-01T00:00:00Z", 100.0, "S001"])
            writer.writerow(["2025-01-01T00:10:00Z", 15.0, "S001"])

        result = ingest_file(csv_file, test_db_with_sensor, config)
        assert result.out_of_range == 1

        out_of_range_row = test_db_with_sensor.fetchone(
            "SELECT is_outlier FROM observations WHERE sensor_id = ? AND value > 50",
            ("S001",),
        )
        assert out_of_range_row is not None
        assert out_of_range_row["is_outlier"] == 1

    def test_ingest_unit_conversion(self, temp_dir, test_db_with_sensor):
        """单位转换"""
        config = Config()
        csv_file = temp_dir / "test.csv"

        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "value", "sensor_id", "unit"])
            writer.writerow(["2025-01-01T00:00:00Z", 32.0, "S001", "fahrenheit"])

        result = ingest_file(csv_file, test_db_with_sensor, config)
        assert result.imported_records == 1

        row = test_db_with_sensor.fetchone(
            "SELECT value FROM observations WHERE sensor_id = ?",
            ("S001",),
        )
        assert row is not None
        assert row["value"] == pytest.approx(0.0, abs=0.1)

    def test_ingest_invalid_file_format(self, temp_dir, test_db_with_sensor):
        """不支持的文件格式"""
        config = Config()
        txt_file = temp_dir / "test.txt"
        txt_file.write_text("not valid")

        with pytest.raises(IngestError):
            ingest_file(txt_file, test_db_with_sensor, config)

    def test_ingest_file_not_found(self, test_db_with_sensor):
        """文件不存在"""
        config = Config()
        with pytest.raises(IngestError):
            ingest_file("/nonexistent/file.csv", test_db_with_sensor, config)

    def test_ingest_missing_columns(self, temp_dir, test_db_with_sensor):
        """缺少必要列"""
        config = Config()
        csv_file = temp_dir / "test.csv"

        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["not_valid_column"])
            writer.writerow(["value"])

        result = ingest_file(csv_file, test_db_with_sensor, config)
        assert result.error_records > 0

    def test_ingest_result_to_dict(self):
        """结果转字典"""
        result = IngestResult()
        result.total_records = 10
        result.imported_records = 8
        result.skipped_records = 1
        result.error_records = 1

        d = result.to_dict()
        assert d["total_records"] == 10
        assert d["imported_records"] == 8

    def test_check_time_order(self):
        """检查时间顺序"""
        records = [
            {"timestamp": datetime(2025, 1, 1, tzinfo=timezone.utc)},
            {"timestamp": datetime(2025, 1, 2, tzinfo=timezone.utc)},
        ]
        assert check_time_order(records)

        records_reverse = [
            {"timestamp": datetime(2025, 1, 2, tzinfo=timezone.utc)},
            {"timestamp": datetime(2025, 1, 1, tzinfo=timezone.utc)},
        ]
        assert not check_time_order(records_reverse)

    def test_record_import_batch(self, temp_dir, test_db_with_sensor):
        """记录导入批次"""
        config = Config()
        result = IngestResult()
        result.total_records = 10
        result.imported_records = 8

        batch_id = record_import_batch(test_db_with_sensor, "test.csv", result)
        assert batch_id > 0

        batch = test_db_with_sensor.fetchone(
            "SELECT * FROM import_batches WHERE id = ?",
            (batch_id,),
        )
        assert batch is not None
        assert batch["source_file"] == "test.csv"
        assert batch["total_records"] == 10
