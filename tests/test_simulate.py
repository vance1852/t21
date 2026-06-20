"""撤收模拟模块测试"""

import pytest

from ocean_sentinel.config import Config
from ocean_sentinel.simulate import (
    simulate_plan,
    simulate_custom,
    simulate_maintenance_window,
    get_all_plans,
    get_all_maintenance_windows,
    SimulationResult,
)


class TestSimulate:
    """模拟模块测试"""

    def test_simulate_custom_empty(self, empty_db):
        """空数据库自定义模拟"""
        config = Config()
        result = simulate_custom(empty_db, config, ["S001"])

        assert isinstance(result, SimulationResult)
        assert result.plan_id == "custom"

    def test_simulate_with_sample_data(self, populated_db):
        """示例数据的自定义模拟"""
        config = Config()

        sensors = populated_db.fetchall("SELECT id FROM sensors LIMIT 2")
        sensor_ids = [s["id"] for s in sensors]

        result = simulate_custom(populated_db, config, sensor_ids)

        assert len(result.sensors_removed) == 2
        assert result.baseline_coverage is not None
        assert result.simulated_coverage is not None
        assert result.overall_risk_change in ("degraded", "improved", "neutral")

    def test_simulate_plan(self, populated_db):
        """模拟撤收方案"""
        config = Config()

        plans = get_all_plans(populated_db)
        if plans:
            result = simulate_plan(populated_db, config, plans[0]["id"])
            assert result.plan_id == plans[0]["id"]
            assert result.sensors_removed == [s["sensor_id"] for s in plans[0].get("sensors", []) if s.get("action") == "remove"]

    def test_simulate_plan_not_found(self, empty_db):
        """方案不存在"""
        config = Config()
        with pytest.raises(ValueError):
            simulate_plan(empty_db, config, "nonexistent_plan")

    def test_simulate_maintenance_window_not_found(self, empty_db):
        """维护窗口不存在"""
        config = Config()
        with pytest.raises(ValueError):
            simulate_maintenance_window(empty_db, config, "nonexistent_window")

    def test_simulate_result_to_dict(self, populated_db):
        """模拟结果转字典"""
        config = Config()

        result = simulate_custom(populated_db, config, [])

        d = result.to_dict()
        assert "plan_id" in d
        assert "plan_name" in d
        assert "sensors_removed" in d
        assert "baseline_overall_ratio" in d
        assert "simulated_overall_ratio" in d
        assert "impacted_grids" in d
        assert "newly_under_min" in d

    def test_get_all_plans(self, populated_db):
        """获取所有方案"""
        plans = get_all_plans(populated_db)
        assert isinstance(plans, list)
        if plans:
            assert "id" in plans[0]
            assert "sensors" in plans[0]

    def test_get_all_maintenance_windows(self, populated_db):
        """获取所有维护窗口"""
        windows = get_all_maintenance_windows(populated_db)
        assert isinstance(windows, list)
        if windows:
            assert "id" in windows[0]
            assert "sensors" in windows[0]

    def test_simulate_impacted_grids(self, populated_db):
        """受影响网格"""
        config = Config()

        sensors = populated_db.fetchall("SELECT id FROM sensors LIMIT 3")
        sensor_ids = [s["id"] for s in sensors]

        result = simulate_custom(populated_db, config, sensor_ids)

        assert isinstance(result.impacted_grids, list)
        for grid in result.impacted_grids:
            assert "grid_id" in grid
            assert "baseline_ratio" in grid
            assert "simulated_ratio" in grid
            assert "ratio_change" in grid

    def test_simulate_newly_under_min(self, populated_db):
        """新增不达标网格"""
        config = Config()

        sensors = populated_db.fetchall("SELECT id FROM sensors LIMIT 3")
        sensor_ids = [s["id"] for s in sensors]

        result = simulate_custom(populated_db, config, sensor_ids)

        assert isinstance(result.newly_under_min, list)
        for grid_id in result.newly_under_min:
            assert grid_id in [g["grid_id"] for g in result.impacted_grids]

    def test_simulate_summary(self, populated_db):
        """模拟摘要"""
        config = Config()

        result = simulate_custom(populated_db, config, [])
        assert isinstance(result.summary, str)
        assert len(result.summary) > 0
