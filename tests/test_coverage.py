"""覆盖率计算模块测试"""

import pytest

from ocean_sentinel.config import Config
from ocean_sentinel.coverage import calculate_coverage, CoverageResult


class TestCoverage:
    """覆盖率模块测试"""

    def test_coverage_empty_db(self, empty_db):
        """空数据库覆盖率"""
        config = Config()
        result = calculate_coverage(empty_db, config)

        assert isinstance(result, CoverageResult)
        assert result.overall_ratio == 0.0
        assert len(result.grid_coverage) == 0

    def test_coverage_with_sample_data(self, populated_db):
        """示例数据覆盖率"""
        config = Config()
        result = calculate_coverage(populated_db, config)

        assert result.overall_ratio >= 0.0
        assert result.overall_ratio <= 1.0
        assert len(result.grid_coverage) > 0
        assert len(result.variable_coverage) > 0
        assert len(result.depth_layer_coverage) > 0

    def test_coverage_result_to_dict(self, populated_db):
        """覆盖率结果转字典"""
        config = Config()
        result = calculate_coverage(populated_db, config)

        d = result.to_dict()
        assert "overall_ratio" in d
        assert "overall_level" in d
        assert "under_min_grids" in d
        assert "grid_coverage" in d
        assert "variable_coverage" in d
        assert "depth_layer_coverage" in d

    def test_coverage_with_date_range(self, populated_db):
        """指定日期范围的覆盖率"""
        config = Config()
        result = calculate_coverage(
            populated_db,
            config,
            start_date="2025-03-01T00:00:00Z",
            end_date="2025-03-31T23:59:59Z",
        )

        assert result is not None
        assert len(result.grid_coverage) > 0

    def test_coverage_exclude_sensors(self, populated_db):
        """排除传感器后的覆盖率"""
        config = Config()

        baseline = calculate_coverage(populated_db, config)

        sensors = populated_db.fetchall("SELECT id FROM sensors LIMIT 3")
        sensor_ids = [s["id"] for s in sensors]

        result = calculate_coverage(populated_db, config, sensors_to_exclude=sensor_ids)

        assert result.overall_ratio <= baseline.overall_ratio

    def test_coverage_grid_details(self, populated_db):
        """网格详情"""
        config = Config()
        result = calculate_coverage(populated_db, config)

        for grid_id, grid_info in result.grid_coverage.items():
            assert "coverage_ratio" in grid_info
            assert "risk_level" in grid_info
            assert "meets_minimum" in grid_info
            assert "variables" in grid_info
            assert "total_variables_covered" in grid_info

    def test_coverage_variable_details(self, populated_db):
        """变量覆盖率详情"""
        config = Config()
        result = calculate_coverage(populated_db, config)

        for var, ratio in result.variable_coverage.items():
            assert isinstance(ratio, float)
            assert 0 <= ratio <= 1

    def test_coverage_depth_layer_details(self, populated_db):
        """深度层覆盖率详情"""
        config = Config()
        result = calculate_coverage(populated_db, config)

        for layer, ratio in result.depth_layer_coverage.items():
            assert isinstance(ratio, float)
            assert 0 <= ratio <= 1

    def test_coverage_under_min(self, populated_db):
        """不达标网格列表"""
        config = Config()
        result = calculate_coverage(populated_db, config)

        for grid_id in result.under_min:
            assert grid_id in result.grid_coverage
            assert not result.grid_coverage[grid_id]["meets_minimum"]

    def test_coverage_max_sensors_per_var(self, empty_db):
        """每个网格每个变量的最大传感器数限制"""
        config = Config()

        empty_db.execute(
            "INSERT INTO grids (id, name, lat_min, lat_max, lon_min, lon_max, min_variables) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("G1", "G1", 30, 31, 120, 121, 1),
        )
        empty_db.execute(
            "INSERT INTO stations (id, name, grid_id, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
            ("ST1", "ST1", "G1", 30.5, 120.5),
        )

        for i in range(5):
            empty_db.execute(
                """INSERT INTO sensors
                   (id, station_id, variable, depth, sampling_interval_seconds, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (f"S{i}", "ST1", "temperature", 5.0 + i, 600, "active"),
            )

        empty_db.conn.commit()

        result = calculate_coverage(empty_db, config)
        grid_info = result.grid_coverage.get("G1", {})
        var_info = grid_info.get("variables", {}).get("temperature", {})
        layer_info = var_info.get("layers", {}).get("surface", {})
        sensors_list = layer_info.get("sensors", [])

        max_sensors = config.get("coverage.max_sensors_per_grid_var", 3)
        assert len(sensors_list) <= max_sensors
