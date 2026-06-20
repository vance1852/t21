"""传感器推荐模块测试"""

import pytest

from ocean_sentinel.config import Config
from ocean_sentinel.recommend import (
    recommend_keep,
    recommend_maintain,
    RecommendationResult,
    RecommendationItem,
)


class TestRecommend:
    """推荐模块测试"""

    def test_recommend_keep_empty(self, empty_db):
        """空数据库推荐保留"""
        config = Config()
        result = recommend_keep(empty_db, config)

        assert isinstance(result, RecommendationResult)
        assert result.total_sensors == 0

    def test_recommend_keep_with_sample(self, populated_db):
        """示例数据推荐保留"""
        config = Config()
        result = recommend_keep(populated_db, config)

        assert result.total_sensors > 0
        assert len(result.keep) > 0
        assert result.strategy == "greedy_keep"

    def test_recommend_keep_max_sensors(self, populated_db):
        """按数量约束推荐保留"""
        config = Config()
        result = recommend_keep(populated_db, config, max_sensors=5)

        assert len(result.keep) <= 5
        assert result.keep_count <= 5

    def test_recommend_keep_min_coverage(self, populated_db):
        """按覆盖率约束推荐保留"""
        config = Config()
        result = recommend_keep(populated_db, config, min_coverage_ratio=0.3)

        assert result.keep_count >= 0
        assert result.expected_coverage >= 0

    def test_recommend_maintain(self, populated_db):
        """推荐检修优先级"""
        config = Config()
        result = recommend_maintain(populated_db, config)

        assert isinstance(result, RecommendationResult)
        assert result.strategy == "greedy_maintain"
        assert len(result.maintain_first) >= 0

    def test_recommend_maintain_count(self, populated_db):
        """指定数量的检修推荐"""
        config = Config()
        result = recommend_maintain(populated_db, config, count=3)

        assert len(result.maintain_first) <= 3

    def test_recommendation_result_to_dict(self, populated_db):
        """推荐结果转字典"""
        config = Config()
        result = recommend_keep(populated_db, config)

        d = result.to_dict()
        assert "strategy" in d
        assert "total_sensors" in d
        assert "keep_count" in d
        assert "remove_count" in d
        assert "expected_coverage" in d
        assert "total_maintenance_cost" in d
        assert "keep" in d
        assert "remove" in d

    def test_recommendation_item_to_dict(self):
        """推荐项转字典"""
        item = RecommendationItem()
        item.sensor_id = "S001"
        item.score = 0.85
        item.variables = ["temperature"]
        item.maintenance_cost = 1.5
        item.stability = 0.9

        d = item.to_dict()
        assert d["sensor_id"] == "S001"
        assert d["score"] == pytest.approx(0.85)
        assert "reasons" in d

    def test_recommend_keep_sorted_by_score(self, populated_db):
        """推荐结果按分数排序"""
        config = Config()
        result = recommend_keep(populated_db, config)

        if len(result.keep) > 1:
            scores = [item.score for item in result.keep]
            assert scores == sorted(scores, reverse=True)

    def test_recommend_keep_has_reasons(self, populated_db):
        """推荐项有理由"""
        config = Config()
        result = recommend_keep(populated_db, config)

        if result.keep:
            item = result.keep[0]
            assert isinstance(item.reasons, list)
            assert len(item.reasons) > 0

    def test_recommend_maintain_sorted(self, populated_db):
        """检修推荐按优先级排序"""
        config = Config()
        result = recommend_maintain(populated_db, config)

        if len(result.maintain_first) > 1:
            scores = [item.score for item in result.maintain_first]
            assert scores == sorted(scores, reverse=True)

    def test_total_maintenance_cost(self, populated_db):
        """总维护成本计算"""
        config = Config()
        result = recommend_keep(populated_db, config)

        expected_cost = sum(item.maintenance_cost for item in result.keep)
        assert result.total_maintenance_cost == pytest.approx(expected_cost)
