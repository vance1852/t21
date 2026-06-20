"""撤收与维护模拟模块"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Config
from .database import DatabaseManager
from .coverage import calculate_coverage, CoverageResult
from .utils import parse_timestamp, format_timestamp


class SimulationResult:
    """模拟结果"""

    def __init__(self):
        self.plan_id: str = ""
        self.plan_name: str = ""
        self.baseline_coverage: CoverageResult | None = None
        self.simulated_coverage: CoverageResult | None = None
        self.impacted_grids: list[dict] = []
        self.impacted_variables: list[dict] = []
        self.impacted_depth_layers: list[dict] = []
        self.overall_risk_change: str = "neutral"
        self.risk_level_downgrades: list[str] = []
        self.newly_under_min: list[str] = []
        self.sensors_removed: list[str] = []
        self.summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "plan_name": self.plan_name,
            "sensors_removed": self.sensors_removed,
            "baseline_overall_ratio": (
                self.baseline_coverage.overall_ratio if self.baseline_coverage else None
            ),
            "baseline_overall_level": (
                self.baseline_coverage.overall_level if self.baseline_coverage else None
            ),
            "simulated_overall_ratio": (
                self.simulated_coverage.overall_ratio if self.simulated_coverage else None
            ),
            "simulated_overall_level": (
                self.simulated_coverage.overall_level if self.simulated_coverage else None
            ),
            "overall_risk_change": self.overall_risk_change,
            "impacted_grids": self.impacted_grids,
            "impacted_variables": self.impacted_variables,
            "impacted_depth_layers": self.impacted_depth_layers,
            "risk_level_downgrades": self.risk_level_downgrades,
            "newly_under_min": self.newly_under_min,
            "summary": self.summary,
        }


def simulate_plan(
    db: DatabaseManager,
    config: Config,
    plan_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> SimulationResult:
    """模拟撤收方案的影响"""
    result = SimulationResult()

    plan = db.fetchone("SELECT * FROM deployment_plans WHERE id = ?", (plan_id,))
    if not plan:
        raise ValueError(f"撤收方案不存在: {plan_id}")

    result.plan_id = plan["id"]
    result.plan_name = plan["name"]

    plan_sensors = db.fetchall(
        "SELECT sensor_id, action FROM plan_sensors WHERE plan_id = ? AND action = 'remove'",
        (plan_id,),
    )
    sensors_to_remove = [row["sensor_id"] for row in plan_sensors]
    result.sensors_removed = sensors_to_remove

    plan_start = plan["start_date"] if plan["start_date"] else start_date
    plan_end = plan["end_date"] if plan["end_date"] else end_date

    baseline = calculate_coverage(db, config, start_date, end_date)
    result.baseline_coverage = baseline

    simulated = calculate_coverage(
        db, config, plan_start or start_date, plan_end or end_date, sensors_to_remove
    )
    result.simulated_coverage = simulated

    _compare_coverage(result, baseline, simulated, config)
    _generate_summary(result)

    return result


def simulate_maintenance_window(
    db: DatabaseManager,
    config: Config,
    window_id: str,
) -> SimulationResult:
    """模拟维护窗口的影响"""
    result = SimulationResult()

    window = db.fetchone("SELECT * FROM maintenance_windows WHERE id = ?", (window_id,))
    if not window:
        raise ValueError(f"维护窗口不存在: {window_id}")

    result.plan_id = window["id"]
    result.plan_name = window["name"]

    window_sensors = db.fetchall(
        "SELECT sensor_id FROM maintenance_sensors WHERE window_id = ?",
        (window_id,),
    )
    sensors_out = [row["sensor_id"] for row in window_sensors]
    result.sensors_removed = sensors_out

    baseline = calculate_coverage(
        db, config, window["start_date"], window["end_date"]
    )
    result.baseline_coverage = baseline

    simulated = calculate_coverage(
        db, config, window["start_date"], window["end_date"], sensors_out
    )
    result.simulated_coverage = simulated

    _compare_coverage(result, baseline, simulated, config)
    _generate_summary(result)

    return result


def simulate_custom(
    db: DatabaseManager,
    config: Config,
    sensors_to_remove: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> SimulationResult:
    """模拟自定义传感器撤收"""
    result = SimulationResult()
    result.plan_id = "custom"
    result.plan_name = "自定义撤收方案"
    result.sensors_removed = sensors_to_remove

    baseline = calculate_coverage(db, config, start_date, end_date)
    result.baseline_coverage = baseline

    simulated = calculate_coverage(db, config, start_date, end_date, sensors_to_remove)
    result.simulated_coverage = simulated

    _compare_coverage(result, baseline, simulated, config)
    _generate_summary(result)

    return result


def _compare_coverage(
    result: SimulationResult,
    baseline: CoverageResult,
    simulated: CoverageResult,
    config: Config,
) -> None:
    """比较基线和模拟覆盖率"""
    min_ratio = config.get("coverage.min_coverage_ratio", 0.7)
    risk_levels = config.get("risk_levels", [])
    level_order = [l["level"] for l in sorted(risk_levels, key=lambda x: x["threshold"])]

    if simulated.overall_ratio < baseline.overall_ratio:
        result.overall_risk_change = "degraded"
    elif simulated.overall_ratio > baseline.overall_ratio:
        result.overall_risk_change = "improved"
    else:
        result.overall_risk_change = "neutral"

    for grid_id in baseline.grid_coverage:
        base_grid = baseline.grid_coverage.get(grid_id, {})
        sim_grid = simulated.grid_coverage.get(grid_id, {})

        base_ratio = base_grid.get("coverage_ratio", 0)
        sim_ratio = sim_grid.get("coverage_ratio", 0)
        diff = round(sim_ratio - base_ratio, 4)

        base_level = base_grid.get("risk_level", "unknown")
        sim_level = sim_grid.get("risk_level", "unknown")

        base_meets = base_grid.get("meets_minimum", False)
        sim_meets = sim_grid.get("meets_minimum", False)

        if diff != 0 or base_meets != sim_meets:
            result.impacted_grids.append(
                {
                    "grid_id": grid_id,
                    "baseline_ratio": base_ratio,
                    "simulated_ratio": sim_ratio,
                    "ratio_change": diff,
                    "baseline_level": base_level,
                    "simulated_level": sim_level,
                    "baseline_meets_min": base_meets,
                    "simulated_meets_min": sim_meets,
                    "level_downgraded": _is_level_downgrade(base_level, sim_level, level_order),
                }
            )

        if not sim_meets and base_meets:
            result.newly_under_min.append(grid_id)

        if _is_level_downgrade(base_level, sim_level, level_order):
            result.risk_level_downgrades.append(grid_id)

    for var_id in baseline.variable_coverage:
        base_var = baseline.variable_coverage.get(var_id, 0)
        sim_var = simulated.variable_coverage.get(var_id, 0)
        diff = round(sim_var - base_var, 4)
        if diff != 0:
            result.impacted_variables.append(
                {
                    "variable": var_id,
                    "baseline_ratio": base_var,
                    "simulated_ratio": sim_var,
                    "ratio_change": diff,
                }
            )

    for layer_id in baseline.depth_layer_coverage:
        base_layer = baseline.depth_layer_coverage.get(layer_id, 0)
        sim_layer = simulated.depth_layer_coverage.get(layer_id, 0)
        diff = round(sim_layer - base_layer, 4)
        if diff != 0:
            result.impacted_depth_layers.append(
                {
                    "depth_layer": layer_id,
                    "baseline_ratio": base_layer,
                    "simulated_ratio": sim_layer,
                    "ratio_change": diff,
                }
            )


def _is_level_downgrade(before: str, after: str, level_order: list[str]) -> bool:
    """判断风险等级是否下降（更严重）"""
    if before not in level_order or after not in level_order:
        return False
    return level_order.index(after) < level_order.index(before)


def _generate_summary(result: SimulationResult) -> None:
    """生成总结文本"""
    parts = []
    parts.append(f"撤收传感器: {len(result.sensors_removed)} 个")

    if result.baseline_coverage and result.simulated_coverage:
        base = result.baseline_coverage.overall_ratio
        sim = result.simulated_coverage.overall_ratio
        diff = round(sim - base, 4)
        parts.append(
            f"整体覆盖率: {base:.1%} -> {sim:.1%} ({'下降' if diff < 0 else '上升'} {abs(diff):.1%})"
        )

    parts.append(f"受影响网格: {len(result.impacted_grids)} 个")
    parts.append(f"新增不达标网格: {len(result.newly_under_min)} 个")
    parts.append(f"风险等级下降网格: {len(result.risk_level_downgrades)} 个")

    result.summary = " | ".join(parts)


def get_all_plans(db: DatabaseManager) -> list[dict]:
    """获取所有撤收方案"""
    rows = db.fetchall("SELECT * FROM deployment_plans ORDER BY id")
    plans = []
    for row in rows:
        plan = dict(row)
        sensors = db.fetchall(
            "SELECT sensor_id, action FROM plan_sensors WHERE plan_id = ?",
            (row["id"],),
        )
        plan["sensors"] = [dict(s) for s in sensors]
        plans.append(plan)
    return plans


def get_all_maintenance_windows(db: DatabaseManager) -> list[dict]:
    """获取所有维护窗口"""
    rows = db.fetchall("SELECT * FROM maintenance_windows ORDER BY id")
    windows = []
    for row in rows:
        win = dict(row)
        sensors = db.fetchall(
            "SELECT sensor_id FROM maintenance_sensors WHERE window_id = ?",
            (row["id"],),
        )
        win["sensors"] = [s["sensor_id"] for s in sensors]
        windows.append(win)
    return windows
