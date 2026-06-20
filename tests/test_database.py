"""数据库模块测试"""

import os
import tempfile
from pathlib import Path

import pytest

from ocean_sentinel.database import DatabaseManager, get_db, SCHEMA_SQL


class TestDatabase:
    """数据库管理测试"""

    def test_create_db(self):
        """创建数据库"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = DatabaseManager(db_path)
            assert db is not None
            db.close()

    def test_initialize_schema(self):
        """初始化表结构"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = DatabaseManager(db_path)
            db.initialize()

            tables = db.fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            table_names = [t["name"] for t in tables]

            expected_tables = [
                "calibrations",
                "deployment_plans",
                "grids",
                "grid_neighbors",
                "import_batches",
                "maintenance_sensors",
                "maintenance_windows",
                "observations",
                "plan_sensors",
                "sensors",
                "stations",
            ]
            for t in expected_tables:
                assert t in table_names

            db.close()

    def test_transaction_commit(self):
        """事务提交"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = DatabaseManager(db_path)
            db.initialize()

            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO grids (id, name, lat_min, lat_max, lon_min, lon_max) VALUES (?, ?, ?, ?, ?, ?)",
                    ("G1", "Test Grid", 30.0, 31.0, 120.0, 121.0),
                )

            result = db.fetchone("SELECT * FROM grids WHERE id = ?", ("G1",))
            assert result is not None
            assert result["name"] == "Test Grid"

            db.close()

    def test_transaction_rollback(self):
        """事务回滚"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = DatabaseManager(db_path)
            db.initialize()

            try:
                with db.transaction() as conn:
                    conn.execute(
                        "INSERT INTO grids (id, name, lat_min, lat_max, lon_min, lon_max) VALUES (?, ?, ?, ?, ?, ?)",
                        ("G2", "Test Grid 2", 30.0, 31.0, 120.0, 121.0),
                    )
                    raise ValueError("test error")
            except ValueError:
                pass

            result = db.fetchone("SELECT * FROM grids WHERE id = ?", ("G2",))
            assert result is None

            db.close()

    def test_execute_and_fetchall(self):
        """执行SQL和查询"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = DatabaseManager(db_path)
            db.initialize()

            db.execute(
                "INSERT INTO grids (id, name, lat_min, lat_max, lon_min, lon_max) VALUES (?, ?, ?, ?, ?, ?)",
                ("G3", "Grid 3", 29.0, 30.0, 121.0, 122.0),
            )
            db.conn.commit()

            rows = db.fetchall("SELECT * FROM grids ORDER BY id")
            assert len(rows) == 1
            assert rows[0]["id"] == "G3"

            db.close()

    def test_fetchone(self):
        """查询单行"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = DatabaseManager(db_path)
            db.initialize()

            result = db.fetchone("SELECT * FROM grids WHERE id = ?", ("nonexistent",))
            assert result is None

            db.close()

    def test_executemany(self):
        """批量插入"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = DatabaseManager(db_path)
            db.initialize()

            data = [
                ("G4", "G4", 1, 2, 3, 4),
                ("G5", "G5", 5, 6, 7, 8),
                ("G6", "G6", 9, 10, 11, 12),
            ]
            db.executemany(
                "INSERT INTO grids (id, name, lat_min, lat_max, lon_min, lon_max) VALUES (?, ?, ?, ?, ?, ?)",
                data,
            )
            db.conn.commit()

            rows = db.fetchall("SELECT * FROM grids ORDER BY id")
            assert len(rows) == 3

            db.close()

    def test_get_db_factory(self):
        """get_db工厂函数"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = get_db(db_path)
            assert isinstance(db, DatabaseManager)
            db.close()

    def test_close_connection(self):
        """关闭连接"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = DatabaseManager(db_path)
            db.initialize()

            conn = db.conn
            assert conn is not None

            db.close()

            conn2 = db.conn
            assert conn2 is not None
            assert conn is not conn2

            db.close()

    def test_row_factory(self):
        """行工厂返回Row对象"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = DatabaseManager(db_path)
            db.initialize()

            db.execute(
                "INSERT INTO grids (id, name, lat_min, lat_max, lon_min, lon_max) VALUES (?, ?, ?, ?, ?, ?)",
                ("G7", "Grid 7", 1, 2, 3, 4),
            )
            db.conn.commit()

            row = db.fetchone("SELECT * FROM grids WHERE id = ?", ("G7",))
            assert row is not None
            assert row["id"] == "G7"
            assert row["name"] == "Grid 7"

            db.close()

    def test_foreign_keys_enabled(self):
        """外键约束启用"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = DatabaseManager(db_path)
            db.initialize()

            with pytest.raises(Exception):
                with db.transaction() as conn:
                    conn.execute(
                        "INSERT INTO stations (id, name, grid_id, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
                        ("ST1", "Station 1", "nonexistent_grid", 30.0, 120.0),
                    )

            db.close()
