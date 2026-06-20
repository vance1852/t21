"""示例数据生成模块测试"""

import pytest
from pathlib import Path

from ocean_sentinel.sample_data import generate_sample_workspace
from ocean_sentinel.config import Config
from ocean_sentinel.database import DatabaseManager


class TestSampleData:
    """示例数据模块测试"""

    def test_generate_workspace(self, temp_dir):
        """生成示例工作区"""
        workspace = temp_dir / "workspace"
        result = generate_sample_workspace(workspace)

        assert isinstance(result, dict)
        assert "workspace_dir" in result
        assert "created_files" in result
        assert "stats" in result

        assert (workspace / "config.yaml").exists()
        assert (workspace / "data").exists()
        assert (workspace / "sample_data").exists()

    def test_config_exists(self, temp_dir):
        """配置文件存在且有效"""
        workspace = temp_dir / "workspace"
        generate_sample_workspace(workspace)

        config = Config.from_file(workspace / "config.yaml")
        assert config.get("variables.temperature") is not None
        assert config.get("grids") is not None
        assert len(config.get("grids", [])) > 0

    def test_database_initialized(self, temp_dir):
        """数据库已初始化"""
        workspace = temp_dir / "workspace"
        generate_sample_workspace(workspace)

        config = Config.from_file(workspace / "config.yaml")
        db_path = workspace / config.get("database.path", "data/ocean_sentinel.db")

        assert db_path.exists()

        db = DatabaseManager(db_path)
        try:
            grids = db.fetchall("SELECT * FROM grids")
            assert len(grids) > 0

            stations = db.fetchall("SELECT * FROM stations")
            assert len(stations) > 0

            sensors = db.fetchall("SELECT * FROM sensors")
            assert len(sensors) > 0

            observations = db.fetchall("SELECT * FROM observations")
            assert len(observations) > 0

            calibrations = db.fetchall("SELECT * FROM calibrations")
            assert len(calibrations) > 0
        finally:
            db.close()

    def test_sample_data_files(self, temp_dir):
        """示例数据文件"""
        workspace = temp_dir / "workspace"
        generate_sample_workspace(workspace)

        sample_dir = workspace / "sample_data"
        assert sample_dir.exists()

        csv_file = sample_dir / "sample_temperature.csv"
        assert csv_file.exists()
        assert csv_file.stat().st_size > 0

        json_file = sample_dir / "sample_salinity.json"
        assert json_file.exists()
        assert json_file.stat().st_size > 0

        yaml_file = sample_dir / "sample_metadata.yaml"
        assert yaml_file.exists()
        assert yaml_file.stat().st_size > 0

    def test_grid_neighbors(self, temp_dir):
        """网格邻接关系"""
        workspace = temp_dir / "workspace"
        generate_sample_workspace(workspace)

        config = Config.from_file(workspace / "config.yaml")
        db_path = workspace / config.get("database.path", "data/ocean_sentinel.db")
        db = DatabaseManager(db_path)

        try:
            neighbors = db.fetchall("SELECT * FROM grid_neighbors")
            assert len(neighbors) > 0
        finally:
            db.close()

    def test_maintenance_windows(self, temp_dir):
        """维护窗口数据"""
        workspace = temp_dir / "workspace"
        generate_sample_workspace(workspace)

        config = Config.from_file(workspace / "config.yaml")
        db_path = workspace / config.get("database.path", "data/ocean_sentinel.db")
        db = DatabaseManager(db_path)

        try:
            windows = db.fetchall("SELECT * FROM maintenance_windows")
            assert len(windows) >= 1
        finally:
            db.close()

    def test_deployment_plans(self, temp_dir):
        """撤收方案数据"""
        workspace = temp_dir / "workspace"
        generate_sample_workspace(workspace)

        config = Config.from_file(workspace / "config.yaml")
        db_path = workspace / config.get("database.path", "data/ocean_sentinel.db")
        db = DatabaseManager(db_path)

        try:
            plans = db.fetchall("SELECT * FROM deployment_plans")
            assert len(plans) >= 1

            plan_sensors = db.fetchall("SELECT * FROM plan_sensors")
            assert len(plan_sensors) >= 1
        finally:
            db.close()

    def test_stats_correct(self, temp_dir):
        """统计数据正确"""
        workspace = temp_dir / "workspace"
        result = generate_sample_workspace(workspace)

        stats = result.get("stats", {})
        assert stats.get("grids", 0) > 0
        assert stats.get("stations", 0) > 0
        assert stats.get("sensors", 0) > 0
