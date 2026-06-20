"""传感器推荐模块（贪心策略）"""

from __future__ import annotations

from typing import Any

from .config import Config
from .database import DatabaseManager
from .coverage import calculate_coverage, CoverageResult
from .simulate import simulate_custom, SimulationResult


class RecommendationItem:
    """推荐项"""

    def __init__(self):
        self.sensor_id: str = ""
        self.action: str = "keep"
        self.score: float = 0.0
        self.reasons: list[str] = []
        self.variables: list[str] = []
        self.coverage_contribution: float = 0.0
        self.maintenance_cost: float = 0.0
        self.stability: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "action": self.action,
            "score": round(self.score, 4),
            "reasons": self.reasons,
            "variables": self.variables,
            "coverage_contribution": round(self.coverage_contribution, 4),
            "maintenance_cost": self.maintenance_cost,
            "stability": self.stability,
        }


class RecommendationResult:
    """推荐结果"""

    def __init__(self):
        self.keep: list[RecommendationItem] = []
        self.remove: list[RecommendationItem] = []
        self.maintain_first: list[RecommendationItem] = []
        self.strategy: str = ""
        self.total_sensors: int = 0
        self.keep_count: int = 0
        self.remove_count: int = 0
        self.expected_coverage: float = 0.0
        self.total_maintenance_cost: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "total_sensors": self.total_sensors,
            "keep_count": self.keep_count,
            "remove_count": self.remove_count,
            "expected_coverage": round(self.expected_coverage, 4),
            "total_maintenance_cost": round(self.total_maintenance_cost, 2),
            "keep": [item.to_dict() for item in self.keep],
            "remove": [item.to_dict() for item in self.remove],
            "maintain_first": [item.to_dict() for item in self.maintain_first],
        }


def recommend_keep(
    db: DatabaseManager,
    config: Config,
    max_sensors: int | None = None,
    min_coverage_ratio: float | None = None,
    max_cost: float | None = None,
) -> RecommendationResult:
    """推荐优先保留的传感器（贪心策略）"""
    result = RecommendationResult()
    result.strategy = "greedy_keep"

    sensors = _get_sensors_with_info(db)
    result.total_sensors = len(sensors)

    if not sensors:
        return result

    min_ratio = min_coverage_ratio or config.get("coverage.min_coverage_ratio", 0.7)

    scored_sensors = []
    for sensor in sensors:
        item = _score_sensor(sensor, db, config)
        scored_sensors.append(item)

    scored_sensors.sort(key=lambda x: (-x.score, x.maintenance_cost, -x.stability))

    baseline = calculate_coverage(db, config)

    if max_sensors is not None:
        selected = _select_by_count(scored_sensors, max_sensors)
    elif max_cost is not None:
        selected = _select_by_cost(scored_sensors, max_cost)
    else:
        selected = _select_by_coverage(scored_sensors, min_ratio, db, config)

    keep_ids = [s.sensor_id for s in selected]
    all_ids = [s.sensor_id for s in scored_sensors]
    remove_ids = [sid for sid in all_ids if sid not in keep_ids]

    result.keep = [s for s in scored_sensors if s.sensor_id in keep_ids]
    result.remove = [s for s in scored_sensors if s.sensor_id in remove_ids]
    for item in result.remove:
        item.action = "remove"
    result.keep_count = len(keep_ids)
    result.remove_count = len(remove_ids)
    result.total_maintenance_cost = sum(s.maintenance_cost for s in result.keep)

    simulated = simulate_custom(db, config, remove_ids)
    if simulated.simulated_coverage:
        result.expected_coverage = simulated.simulated_coverage.overall_ratio
    else:
        result.expected_coverage = 0.0

    return result


def recommend_maintain(
    db: DatabaseManager,
    config: Config,
    count: int | None = None,
) -> RecommendationResult:
    """推荐优先检修的传感器"""
    result = RecommendationResult()
    result.strategy = "greedy_maintain"

    sensors = _get_sensors_with_info(db)
    result.total_sensors = len(sensors)

    if not sensors:
        return result

    scored = []
    for sensor in sensors:
        item = _score_maintain_priority(sensor, db, config)
        scored.append(item)

    scored.sort(key=lambda x: (-x.score, x.maintenance_cost))

    if count is not None:
        result.maintain_first = scored[:count]
    else:
        result.maintain_first = scored[: max(1, len(scored) // 3)]

    result.keep = scored
    result.keep_count = len(scored)

    return result


def _get_sensors_with_info(db: DatabaseManager) -> list[dict]:
    """获取传感器及其关联信息"""
    rows = db.fetchall(
        """SELECT s.*, st.grid_id, st.name as station_name, st.latitude, st.longitude
           FROM sensors s
           JOIN stations st ON s.station_id = st.id
           WHERE s.status = 'active'
           ORDER BY s.id"""
    )
    sensors = []
    for row in rows:
        sensor = dict(row)
        cal_count = db.fetchone(
            "SELECT COUNT(*) as cnt FROM calibrations WHERE sensor_id = ?",
            (row["id"],),
        )
        sensor["calibration_count"] = cal_count["cnt"] if cal_count else 0

        obs_stats = db.fetchone(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN is_outlier = 1 THEN 1 ELSE 0 END) as outliers
               FROM observations WHERE sensor_id = ?""",
            (row["id"],),
        )
        sensor["observation_count"] = obs_stats["total"] if obs_stats else 0
        sensor["outlier_count"] = obs_stats["outliers"] if obs_stats else 0

        sensors.append(sensor)

    return sensors


def _score_sensor(sensor: dict, db: DatabaseManager, config: Config) -> RecommendationItem:
    """评估传感器保留价值"""
    item = RecommendationItem()
    item.sensor_id = sensor["id"]
    item.variables = [sensor["variable"]]
    item.maintenance_cost = sensor.get("maintenance_cost", 1.0)
    item.stability = sensor.get("historical_stability", 0.9)

    scores = []
    reasons = []

    obs_count = sensor.get("observation_count", 0)
    if obs_count > 0:
        outlier_ratio = sensor.get("outlier_count", 0) / max(obs_count, 1)
        data_quality = 1.0 - outlier_ratio * 2.0
        data_quality = max(0.0, min(1.0, data_quality))
        scores.append(data_quality * 0.3)
        if data_quality > 0.9:
            reasons.append("数据质量优秀")
        elif data_quality > 0.7:
            reasons.append("数据质量良好")
        else:
            reasons.append("数据质量一般")
    else:
        scores.append(0.1)
        reasons.append("无观测数据")

    stability = sensor.get("historical_stability", 0.9)
    scores.append(stability * 0.25)
    if stability >= 0.95:
        reasons.append("历史稳定性高")
    elif stability >= 0.9:
        reasons.append("历史稳定性良好")

    var_config = config.get(f"variables.{sensor['variable']}", {})
    var_importance = var_config.get("importance", 0.5) if var_config else 0.5
    scores.append(var_importance * 0.2)
    reasons.append(f"观测变量: {sensor['variable']}")

    grid_id = sensor.get("grid_id", "")
    neighbor_count = _get_neighbor_count(db, grid_id)
    grid_importance = 1.0 / max(neighbor_count, 1)
    scores.append(grid_importance * 0.15)
    if neighbor_count <= 1:
        reasons.append("网格位置关键，替代少")

    cost_efficiency = 1.0 / max(sensor.get("maintenance_cost", 1.0), 0.1)
    cost_efficiency = min(1.0, cost_efficiency)
    scores.append(cost_efficiency * 0.1)
    if sensor.get("maintenance_cost", 1.0) <= 1.0:
        reasons.append("维护成本低")

    item.coverage_contribution = sum(scores)
    item.score = sum(scores)
    item.reasons = reasons

    return item


def _score_maintain_priority(
    sensor: dict, db: DatabaseManager, config: Config
) -> RecommendationItem:
    """评估传感器检修优先级"""
    item = RecommendationItem()
    item.sensor_id = sensor["id"]
    item.action = "maintain"
    item.variables = [sensor["variable"]]
    item.maintenance_cost = sensor.get("maintenance_cost", 1.0)
    item.stability = sensor.get("historical_stability", 0.9)

    scores = []
    reasons = []

    obs_count = sensor.get("observation_count", 0)
    if obs_count > 0:
        outlier_ratio = sensor.get("outlier_count", 0) / max(obs_count, 1)
        need_score = outlier_ratio * 1.0
        scores.append(need_score * 0.35)
        if outlier_ratio > 0.1:
            reasons.append("离群点比例高")
        elif outlier_ratio > 0.05:
            reasons.append("离群点略多")
    else:
        scores.append(0.5)
        reasons.append("数据量不足")

    cal_count = sensor.get("calibration_count", 0)
    last_maintenance = sensor.get("last_maintenance")
    if last_maintenance:
        from .utils import parse_timestamp
        from datetime import datetime, timezone
        try:
            last_dt = parse_timestamp(last_maintenance)
            days_since = (datetime.now(timezone.utc) - last_dt).days
            staleness = min(days_since / 365.0, 1.0)
            scores.append(staleness * 0.25)
            if days_since > 300:
                reasons.append("距上次校准超过10个月")
            elif days_since > 180:
                reasons.append("距上次校准超过半年")
        except Exception:
            scores.append(0.3)
            reasons.append("校准记录不完整")
    else:
        scores.append(0.5)
        reasons.append("无校准记录")

    stability = sensor.get("historical_stability", 0.9)
    importance = 1.0 - stability
    scores.append(importance * 0.2)
    if stability < 0.85:
        reasons.append("历史稳定性较差")

    var_config = config.get(f"variables.{sensor['variable']}", {})
    var_importance = var_config.get("importance", 0.5) if var_config else 0.5
    scores.append(var_importance * 0.2)

    item.score = sum(scores)
    item.reasons = reasons

    return item


def _get_neighbor_count(db: DatabaseManager, grid_id: str) -> int:
    """获取网格邻居数"""
    row = db.fetchone(
        "SELECT COUNT(*) as cnt FROM grid_neighbors WHERE grid_id = ?",
        (grid_id,),
    )
    return row["cnt"] if row else 0


def _select_by_count(sensors: list[RecommendationItem], count: int) -> list[RecommendationItem]:
    """按数量选择（贪心 + 变量多样性）"""
    selected: list[RecommendationItem] = []
    selected_vars: set[str] = set()
    remaining = list(sensors)

    while len(selected) < count and remaining:
        best = None
        best_score = -1.0
        for s in remaining:
            var_bonus = 0.3 if not any(v in selected_vars for v in s.variables) else 0.0
            effective_score = s.score + var_bonus
            if effective_score > best_score:
                best_score = effective_score
                best = s
        if best is None:
            break
        selected.append(best)
        for v in best.variables:
            selected_vars.add(v)
        remaining.remove(best)

    return selected


def _select_by_cost(sensors: list[RecommendationItem], max_cost: float) -> list[RecommendationItem]:
    """按成本约束选择（贪心 + 变量多样性）"""
    selected: list[RecommendationItem] = []
    total_cost = 0.0
    selected_vars: set[str] = set()
    remaining = list(sensors)

    while remaining:
        best = None
        best_score = -1.0
        for s in remaining:
            if total_cost + s.maintenance_cost > max_cost:
                continue
            var_bonus = 0.3 if not any(v in selected_vars for v in s.variables) else 0.0
            effective_score = s.score + var_bonus
            if effective_score > best_score:
                best_score = effective_score
                best = s
        if best is None:
            break
        selected.append(best)
        total_cost += best.maintenance_cost
        for v in best.variables:
            selected_vars.add(v)
        remaining.remove(best)

    return selected


def _select_by_coverage(
    sensors: list[RecommendationItem],
    min_ratio: float,
    db: DatabaseManager,
    config: Config,
) -> list[RecommendationItem]:
    """按覆盖率约束选择（贪心添加直到达到阈值）"""
    selected = []
    all_ids = [s.sensor_id for s in sensors]

    for sensor in sensors:
        selected.append(sensor)
        selected_ids = [s.sensor_id for s in selected]
        remove_ids = [sid for sid in all_ids if sid not in selected_ids]

        simulated = simulate_custom(db, config, remove_ids)
        if simulated.simulated_coverage and simulated.simulated_coverage.overall_ratio >= min_ratio:
            break

    return selected
