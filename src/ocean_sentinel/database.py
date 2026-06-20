"""数据库连接与数据模型模块"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA_SQL = """
-- 海域网格
CREATE TABLE IF NOT EXISTS grids (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    lat_min REAL NOT NULL,
    lat_max REAL NOT NULL,
    lon_min REAL NOT NULL,
    lon_max REAL NOT NULL,
    min_variables INTEGER DEFAULT 3
);

-- 网格邻接关系
CREATE TABLE IF NOT EXISTS grid_neighbors (
    grid_id TEXT NOT NULL,
    neighbor_id TEXT NOT NULL,
    PRIMARY KEY (grid_id, neighbor_id),
    FOREIGN KEY (grid_id) REFERENCES grids(id),
    FOREIGN KEY (neighbor_id) REFERENCES grids(id)
);

-- 观测站
CREATE TABLE IF NOT EXISTS stations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    grid_id TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    depth REAL,
    status TEXT DEFAULT 'active',
    deployment_date TEXT,
    FOREIGN KEY (grid_id) REFERENCES grids(id)
);

-- 传感器
CREATE TABLE IF NOT EXISTS sensors (
    id TEXT PRIMARY KEY,
    station_id TEXT NOT NULL,
    variable TEXT NOT NULL,
    depth REAL NOT NULL,
    sampling_interval_seconds INTEGER NOT NULL,
    accuracy REAL,
    status TEXT DEFAULT 'active',
    install_date TEXT,
    last_maintenance TEXT,
    maintenance_cost REAL DEFAULT 1.0,
    historical_stability REAL DEFAULT 0.9,
    FOREIGN KEY (station_id) REFERENCES stations(id)
);

-- 校准记录
CREATE TABLE IF NOT EXISTS calibrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id TEXT NOT NULL,
    calibration_date TEXT NOT NULL,
    offset_before REAL,
    offset_after REAL,
    drift_rate REAL,
    technician TEXT,
    notes TEXT,
    FOREIGN KEY (sensor_id) REFERENCES sensors(id)
);

-- 观测数据
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    value REAL NOT NULL,
    quality_flag INTEGER DEFAULT 0,
    is_outlier INTEGER DEFAULT 0,
    is_degraded INTEGER DEFAULT 0,
    source_file TEXT,
    UNIQUE(sensor_id, timestamp),
    FOREIGN KEY (sensor_id) REFERENCES sensors(id)
);

-- 数据质量标记索引
CREATE INDEX IF NOT EXISTS idx_obs_sensor_time ON observations(sensor_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_obs_quality ON observations(quality_flag);

-- 维护窗口
CREATE TABLE IF NOT EXISTS maintenance_windows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    max_sensors_out INTEGER DEFAULT 1
);

-- 维护窗口涉及的传感器
CREATE TABLE IF NOT EXISTS maintenance_sensors (
    window_id TEXT NOT NULL,
    sensor_id TEXT NOT NULL,
    PRIMARY KEY (window_id, sensor_id),
    FOREIGN KEY (window_id) REFERENCES maintenance_windows(id),
    FOREIGN KEY (sensor_id) REFERENCES sensors(id)
);

-- 撤收方案
CREATE TABLE IF NOT EXISTS deployment_plans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    plan_type TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    reason TEXT
);

-- 方案涉及的传感器
CREATE TABLE IF NOT EXISTS plan_sensors (
    plan_id TEXT NOT NULL,
    sensor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    PRIMARY KEY (plan_id, sensor_id),
    FOREIGN KEY (plan_id) REFERENCES deployment_plans(id),
    FOREIGN KEY (sensor_id) REFERENCES sensors(id)
);

-- 导入批次记录
CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    import_time TEXT NOT NULL,
    total_records INTEGER DEFAULT 0,
    imported_records INTEGER DEFAULT 0,
    skipped_records INTEGER DEFAULT 0,
    error_records INTEGER DEFAULT 0,
    status TEXT DEFAULT 'completed'
);
"""


class DatabaseManager:
    """数据库管理器"""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._local = threading.local()

    @property
    def conn(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                detect_types=sqlite3.PARSE_DECLTYPES,
                timeout=30.0,
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA foreign_keys = ON")
        return self._local.conn

    def close(self) -> None:
        """关闭当前线程的数据库连接"""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    def initialize(self) -> None:
        """初始化数据库表结构"""
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """事务上下文管理器，支持回滚"""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行SQL语句"""
        return self.conn.execute(sql, params)

    def executemany(self, sql: str, params: list[tuple]) -> sqlite3.Cursor:
        """批量执行SQL语句"""
        return self.conn.executemany(sql, params)

    def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """查询所有行"""
        cursor = self.conn.execute(sql, params)
        return cursor.fetchall()

    def fetchone(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        """查询单行"""
        cursor = self.conn.execute(sql, params)
        return cursor.fetchone()


def get_db(db_path: str | Path) -> DatabaseManager:
    """获取数据库管理器实例"""
    return DatabaseManager(db_path)
