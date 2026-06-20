"""共享测试fixture"""

import os
import tempfile
from pathlib import Path

import pytest

from ocean_sentinel.config import Config
from ocean_sentinel.database import DatabaseManager


@pytest.fixture
def temp_dir():
    """临时目录fixture"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_config():
    """示例配置fixture"""
    return Config()


@pytest.fixture
def empty_db(temp_dir):
    """空数据库fixture"""
    db_path = temp_dir / "test.db"
    db = DatabaseManager(db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def populated_db(temp_dir):
    """填充了示例数据的数据库fixture"""
    from ocean_sentinel.sample_data import generate_sample_workspace

    workspace = temp_dir / "workspace"
    generate_sample_workspace(workspace)

    config = Config.from_file(workspace / "config.yaml")
    db_path = workspace / config.get("database.path", "data/ocean_sentinel.db")
    db = DatabaseManager(db_path)

    yield db
    db.close()


@pytest.fixture
def sample_workspace(temp_dir):
    """完整示例工作区fixture"""
    from ocean_sentinel.sample_data import generate_sample_workspace

    workspace = temp_dir / "workspace"
    generate_sample_workspace(workspace)

    yield workspace
