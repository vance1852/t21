"""导出模块测试"""

import os
import json
from pathlib import Path

import pytest

from ocean_sentinel.config import Config
from ocean_sentinel.export import (
    export_report,
    create_backup,
    restore_backup,
)


class TestExport:
    """导出模块测试"""

    def test_export_markdown(self, temp_dir, populated_db):
        """导出Markdown报告"""
        config = Config()
        output_file = temp_dir / "report.md"

        result_path = export_report(
            "markdown",
            output_file,
            populated_db,
            config,
        )

        assert result_path.exists()
        assert result_path.suffix == ".md"

        content = result_path.read_text(encoding="utf-8")
        assert len(content) > 0
        assert "#" in content

    def test_export_html(self, temp_dir, populated_db):
        """导出HTML报告"""
        config = Config()
        output_file = temp_dir / "report.html"

        result_path = export_report(
            "html",
            output_file,
            populated_db,
            config,
        )

        assert result_path.exists()
        assert result_path.suffix == ".html"

        content = result_path.read_text(encoding="utf-8")
        assert "<html" in content.lower()
        assert "</html>" in content.lower()

    def test_export_invalid_format(self, temp_dir, populated_db):
        """不支持的导出格式"""
        config = Config()
        output_file = temp_dir / "report.txt"

        with pytest.raises(ValueError):
            export_report("txt", output_file, populated_db, config)

    def test_create_backup(self, temp_dir, populated_db):
        """创建备份"""
        config = Config()
        backup_path = temp_dir / "backup.zip"

        result = create_backup(populated_db, config, backup_path)

        assert result.exists()
        assert result.suffix == ".zip"

    def test_create_backup_no_data(self, temp_dir, populated_db):
        """创建不包含数据的备份"""
        config = Config()
        backup_path = temp_dir / "backup_nodata.zip"

        result = create_backup(populated_db, config, backup_path, include_data=False)

        assert result.exists()

    def test_create_backup_directory(self, temp_dir, populated_db):
        """创建目录形式的备份"""
        config = Config()
        backup_dir = temp_dir / "backup_dir"

        result = create_backup(populated_db, config, backup_dir)

        assert result.is_dir()
        assert (result / "config.yaml").exists()
        assert (result / "manifest.json").exists()

    def test_restore_backup(self, temp_dir, populated_db):
        """恢复备份"""
        config = Config()
        backup_path = temp_dir / "backup.zip"
        restore_dir = temp_dir / "restored"

        create_backup(populated_db, config, backup_path)

        result = restore_backup(backup_path, restore_dir)

        assert result["config_loaded"]
        assert result["db_restored"]
        assert len(result["restored_files"]) > 0
        assert (restore_dir / "config.yaml").exists()
        assert (restore_dir / "data" / "ocean_sentinel.db").exists()

    def test_restore_backup_not_found(self, temp_dir):
        """备份文件不存在"""
        with pytest.raises(FileNotFoundError):
            restore_backup(temp_dir / "nonexistent.zip", temp_dir / "restore")

    def test_restore_backup_overwrite(self, temp_dir, populated_db):
        """覆盖恢复"""
        config = Config()
        backup_path = temp_dir / "backup.zip"
        restore_dir = temp_dir / "restored"

        create_backup(populated_db, config, backup_path)
        restore_backup(backup_path, restore_dir)

        restore_dir.joinpath("config.yaml").write_text("# modified", encoding="utf-8")

        with pytest.raises(FileExistsError):
            restore_backup(backup_path, restore_dir)

        result = restore_backup(backup_path, restore_dir, overwrite=True)
        assert result["config_loaded"]

    def test_export_with_audit(self, temp_dir, populated_db):
        """包含审计的报告导出"""
        from ocean_sentinel.audit import audit_data

        config = Config()
        audit_result = audit_data(populated_db, config)
        output_file = temp_dir / "report_with_audit.md"

        result_path = export_report(
            "markdown",
            output_file,
            populated_db,
            config,
            audit_result=audit_result,
        )

        assert result_path.exists()
        content = result_path.read_text(encoding="utf-8")
        assert "数据质量审计" in content

    def test_export_with_coverage(self, temp_dir, populated_db):
        """包含覆盖率的报告导出"""
        from ocean_sentinel.coverage import calculate_coverage

        config = Config()
        coverage_result = calculate_coverage(populated_db, config)
        output_file = temp_dir / "report_with_cov.md"

        result_path = export_report(
            "markdown",
            output_file,
            populated_db,
            config,
            coverage_result=coverage_result,
        )

        assert result_path.exists()
        content = result_path.read_text(encoding="utf-8")
        assert "覆盖率" in content

    def test_export_with_recommendation(self, temp_dir, populated_db):
        """包含推荐的报告导出"""
        from ocean_sentinel.recommend import recommend_keep

        config = Config()
        rec_result = recommend_keep(populated_db, config)
        output_file = temp_dir / "report_with_rec.md"

        result_path = export_report(
            "markdown",
            output_file,
            populated_db,
            config,
            recommendation_result=rec_result,
        )

        assert result_path.exists()
        content = result_path.read_text(encoding="utf-8")
        assert "传感器推荐" in content
