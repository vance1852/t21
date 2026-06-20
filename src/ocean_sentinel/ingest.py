"""数据导入模块"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .config import Config
from .database import DatabaseManager
from .utils import parse_timestamp, format_timestamp


class IngestError(Exception):
    """导入错误基类"""
    pass


class IngestResult:
    """导入结果汇总"""

    def __init__(self):
        self.total_records = 0
        self.imported_records = 0
        self.skipped_records = 0
        self.error_records = 0
        self.out_of_range = 0
        self.duplicates = 0
        self.errors: list[str] = []
        self.sensor_ids: set[str] = set()
        self.time_range: tuple[datetime, datetime] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "imported_records": self.imported_records,
            "skipped_records": self.skipped_records,
            "error_records": self.error_records,
            "out_of_range": self.out_of_range,
            "duplicates": self.duplicates,
            "errors": self.errors,
            "sensor_count": len(self.sensor_ids),
            "time_range_start": format_timestamp(self.time_range[0]) if self.time_range else None,
            "time_range_end": format_timestamp(self.time_range[1]) if self.time_range else None,
        }


def ingest_file(
    file_path: str | Path,
    db: DatabaseManager,
    config: Config,
    source_file: str | None = None,
) -> IngestResult:
    """导入单个数据文件"""
    path = Path(file_path)
    if not path.exists():
        raise IngestError(f"文件不存在: {file_path}")

    suffix = path.suffix.lower()
    if suffix in (".csv",):
        return _ingest_csv(path, db, config, source_file or str(path))
    elif suffix in (".json",):
        return _ingest_json(path, db, config, source_file or str(path))
    elif suffix in (".yaml", ".yml"):
        return _ingest_yaml(path, db, config, source_file or str(path))
    else:
        raise IngestError(f"不支持的文件格式: {suffix}")


def _ingest_csv(
    path: Path, db: DatabaseManager, config: Config, source_file: str
) -> IngestResult:
    """导入CSV文件"""
    result = IngestResult()
    records = []

    encodings_to_try = ["utf-8-sig", "utf-8", "gbk"]
    last_error = None
    reader = None
    for enc in encodings_to_try:
        try:
            with open(path, "r", encoding=enc) as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    raise IngestError("CSV文件缺少表头")

                reader.fieldnames = [fn.lstrip("\ufeff").strip() for fn in reader.fieldnames]

                for row in reader:
                    result.total_records += 1
                    try:
                        record = _parse_record(row, config)
                        if record:
                            records.append(record)
                            result.sensor_ids.add(record["sensor_id"])
                    except Exception as e:
                        result.error_records += 1
                        if len(result.errors) < 20:
                            result.errors.append(f"第{result.total_records}行: {str(e)}")
            break
        except UnicodeDecodeError as e:
            last_error = e
            continue

    if reader is None and last_error:
        raise IngestError(f"无法识别文件编码，请确保文件使用UTF-8或GBK编码: {last_error}")

    if not check_time_order(records):
        result.errors.insert(0, "警告: 检测到时间倒序，已自动排序")

    _validate_sensors(records, db, result)
    _insert_records(records, db, config, result, source_file)

    return result


def _ingest_json(
    path: Path, db: DatabaseManager, config: Config, source_file: str
) -> IngestResult:
    """导入JSON文件"""
    result = IngestResult()
    records = []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_records = data.get("records", data) if isinstance(data, dict) else data

    for i, row in enumerate(raw_records):
        result.total_records += 1
        try:
            record = _parse_record(row, config)
            if record:
                records.append(record)
                result.sensor_ids.add(record["sensor_id"])
        except Exception as e:
            result.error_records += 1
            if len(result.errors) < 20:
                result.errors.append(f"第{i+1}条: {str(e)}")

    _validate_sensors(records, db, result)
    _insert_records(records, db, config, result, source_file)

    return result


def _ingest_yaml(
    path: Path, db: DatabaseManager, config: Config, source_file: str
) -> IngestResult:
    """导入YAML文件"""
    result = IngestResult()
    records = []

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    raw_records = data.get("records", [])

    for i, row in enumerate(raw_records):
        result.total_records += 1
        try:
            record = _parse_record(row, config)
            if record:
                records.append(record)
                result.sensor_ids.add(record["sensor_id"])
        except Exception as e:
            result.error_records += 1
            if len(result.errors) < 20:
                result.errors.append(f"第{i+1}条: {str(e)}")

    _validate_sensors(records, db, result)
    _insert_records(records, db, config, result, source_file)

    return result


def _parse_record(row: dict[str, Any], config: Config) -> dict[str, Any] | None:
    """解析单条记录"""
    sensor_id = row.get("sensor_id") or row.get("sensor") or row.get("sensorId")
    if not sensor_id:
        raise ValueError("缺少 sensor_id 字段")

    ts_str = row.get("timestamp") or row.get("time") or row.get("datetime")
    if not ts_str:
        raise ValueError("缺少 timestamp 字段")

    value_str = row.get("value") or row.get("measurement")
    if value_str is None:
        raise ValueError("缺少 value 字段")

    try:
        value = float(value_str)
    except (ValueError, TypeError):
        raise ValueError(f"无效的数值: {value_str}")

    unit = row.get("unit") or row.get("units")
    variable = row.get("variable") or row.get("var")

    ts = parse_timestamp(str(ts_str), config.get("timezone", "UTC"))

    return {
        "sensor_id": str(sensor_id),
        "timestamp": ts,
        "value": value,
        "unit": str(unit) if unit else None,
        "variable": str(variable) if variable else None,
    }


def _validate_sensors(records: list[dict], db: DatabaseManager, result: IngestResult) -> None:
    """验证传感器是否存在"""
    if not records:
        return

    sensor_ids = list(set(r["sensor_id"] for r in records))
    placeholders = ",".join(["?"] * len(sensor_ids))
    existing = db.fetchall(
        f"SELECT id, variable FROM sensors WHERE id IN ({placeholders})",
        tuple(sensor_ids),
    )
    existing_ids = {row["id"]: row["variable"] for row in existing}

    valid_records = []
    for rec in records:
        if rec["sensor_id"] not in existing_ids:
            result.skipped_records += 1
            if len(result.errors) < 20:
                result.errors.append(f"未知传感器: {rec['sensor_id']}")
            continue

        if rec["variable"] is None:
            rec["variable"] = existing_ids[rec["sensor_id"]]

        valid_records.append(rec)

    records.clear()
    records.extend(valid_records)


def _insert_records(
    records: list[dict],
    db: DatabaseManager,
    config: Config,
    result: IngestResult,
    source_file: str,
) -> None:
    """将记录插入数据库（带事务回滚）"""
    if not records:
        return

    records.sort(key=lambda r: r["timestamp"])

    times = [r["timestamp"] for r in records]
    result.time_range = (min(times), max(times))

    try:
        with db.transaction() as conn:
            for rec in records:
                try:
                    sensor_var = rec["variable"]
                    if rec["unit"] and rec["unit"] != config.get(f"variables.{sensor_var}.unit"):
                        try:
                            rec["value"] = config.convert_unit(
                                sensor_var, rec["value"], rec["unit"]
                            )
                        except ValueError:
                            pass

                    var_config = config.get_variable_config(sensor_var)
                    valid_range = var_config.get("valid_range")
                    is_out_of_range = False
                    if valid_range:
                        if rec["value"] < valid_range[0] or rec["value"] > valid_range[1]:
                            is_out_of_range = True
                            result.out_of_range += 1

                    ts_str = format_timestamp(rec["timestamp"])

                    try:
                        conn.execute(
                            """INSERT INTO observations
                               (sensor_id, timestamp, value, quality_flag, is_outlier, is_degraded, source_file)
                               VALUES (?, ?, ?, 0, ?, 0, ?)""",
                            (
                                rec["sensor_id"],
                                ts_str,
                                rec["value"],
                                1 if is_out_of_range else 0,
                                source_file,
                            ),
                        )
                        result.imported_records += 1
                    except Exception as e:
                        if "UNIQUE constraint failed" in str(e) or "Duplicate" in str(e):
                            result.duplicates += 1
                            result.skipped_records += 1
                        else:
                            raise

                except Exception as e:
                    result.error_records += 1
                    if len(result.errors) < 20:
                        result.errors.append(f"{rec['sensor_id']}@{rec['timestamp']}: {str(e)}")

    except Exception as e:
        raise IngestError(f"导入失败，已回滚: {str(e)}")


def check_time_order(records: list[dict]) -> bool:
    """检查记录是否按时间升序排列"""
    if len(records) <= 1:
        return True
    for i in range(1, len(records)):
        if records[i]["timestamp"] < records[i - 1]["timestamp"]:
            return False
    return True


def record_import_batch(
    db: DatabaseManager,
    source_file: str,
    result: IngestResult,
    status: str = "completed",
) -> int:
    """记录导入批次"""
    batch = db.fetchone(
        """INSERT INTO import_batches
           (source_file, import_time, total_records, imported_records,
            skipped_records, error_records, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           RETURNING id""",
        (
            source_file,
            format_timestamp(datetime.now(timezone.utc)),
            result.total_records,
            result.imported_records,
            result.skipped_records,
            result.error_records,
            status,
        ),
    )
    return batch["id"] if batch else 0
