"""CLI命令测试"""

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from ocean_sentinel.cli import main


@pytest.fixture
def cli_runner():
    """CLI测试运行器"""
    return CliRunner()


class TestCLI:
    """CLI命令测试"""

    def test_version(self, cli_runner):
        """版本命令"""
        result = cli_runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "ocean-sentinel" in result.output

    def test_help(self, cli_runner):
        """帮助命令"""
        result = cli_runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Ocean Sentinel" in result.output

    def test_init(self, cli_runner, temp_dir):
        """init命令"""
        workspace = temp_dir / "workspace"
        result = cli_runner.invoke(main, ["init", str(workspace)])

        assert result.exit_code == 0
        assert (workspace / "config.yaml").exists()
        assert (workspace / "data").exists()

    def test_init_json(self, cli_runner, temp_dir):
        """init命令JSON输出"""
        workspace = temp_dir / "workspace"
        result = cli_runner.invoke(main, ["--json", "init", str(workspace)])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert "workspace" in data

    def test_init_force(self, cli_runner, temp_dir):
        """init命令--force选项"""
        workspace = temp_dir / "workspace"
        workspace.mkdir()
        (workspace / "config.yaml").write_text("old: true")

        result = cli_runner.invoke(main, ["init", "--force", str(workspace)])
        assert result.exit_code == 0

    def test_init_exists_no_force(self, cli_runner, temp_dir):
        """init命令不覆盖已有工作区"""
        workspace = temp_dir / "workspace"
        workspace.mkdir()
        (workspace / "config.yaml").write_text("old: true")

        result = cli_runner.invoke(main, ["init", str(workspace)])
        assert result.exit_code != 0

    def test_ingest_no_workspace(self, cli_runner, temp_dir):
        """ingest命令无工作区"""
        result = cli_runner.invoke(main, ["-w", str(temp_dir), "ingest", "test.csv"])
        assert result.exit_code != 0

    def test_coverage(self, cli_runner, sample_workspace):
        """coverage命令"""
        result = cli_runner.invoke(main, ["-w", str(sample_workspace), "coverage"])
        assert result.exit_code == 0
        assert "覆盖率" in result.output or "coverage" in result.output.lower()

    def test_coverage_json(self, cli_runner, sample_workspace):
        """coverage命令JSON输出"""
        result = cli_runner.invoke(main, ["-w", str(sample_workspace), "--json", "coverage"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "overall_ratio" in data
        assert "grid_coverage" in data

    def test_audit(self, cli_runner, sample_workspace):
        """audit命令"""
        result = cli_runner.invoke(main, ["-w", str(sample_workspace), "audit"])
        assert result.exit_code == 0

    def test_audit_json(self, cli_runner, sample_workspace):
        """audit命令JSON输出"""
        result = cli_runner.invoke(main, ["-w", str(sample_workspace), "--json", "audit"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total_records" in data
        assert "issues_count" in data

    def test_audit_daily(self, cli_runner, sample_workspace):
        """audit命令按天汇总"""
        result = cli_runner.invoke(main, ["-w", str(sample_workspace), "audit", "--daily"])
        assert result.exit_code == 0

    def test_simulate_list(self, cli_runner, sample_workspace):
        """simulate命令列出方案"""
        result = cli_runner.invoke(main, ["-w", str(sample_workspace), "simulate", "--list"])
        assert result.exit_code == 0

    def test_simulate_sensors(self, cli_runner, sample_workspace):
        """simulate命令自定义传感器"""
        result = cli_runner.invoke(
            main, ["-w", str(sample_workspace), "simulate", "--sensors", "S001,S002"]
        )
        assert result.exit_code == 0

    def test_simulate_json(self, cli_runner, sample_workspace):
        """simulate命令JSON输出"""
        result = cli_runner.invoke(
            main, ["-w", str(sample_workspace), "--json", "simulate", "--sensors", "S001"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "plan_id" in data
        assert "sensors_removed" in data

    def test_recommend_keep(self, cli_runner, sample_workspace):
        """recommend命令保留模式"""
        result = cli_runner.invoke(main, ["-w", str(sample_workspace), "recommend", "--mode", "keep"])
        assert result.exit_code == 0

    def test_recommend_maintain(self, cli_runner, sample_workspace):
        """recommend命令检修模式"""
        result = cli_runner.invoke(main, ["-w", str(sample_workspace), "recommend", "--mode", "maintain"])
        assert result.exit_code == 0

    def test_recommend_json(self, cli_runner, sample_workspace):
        """recommend命令JSON输出"""
        result = cli_runner.invoke(
            main, ["-w", str(sample_workspace), "--json", "recommend"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "strategy" in data
        assert "keep" in data

    def test_export_markdown(self, cli_runner, sample_workspace, temp_dir):
        """export命令Markdown格式"""
        output_file = temp_dir / "report.md"
        result = cli_runner.invoke(
            main,
            [
                "-w", str(sample_workspace),
                "export", str(output_file),
                "-f", "markdown",
                "--include-coverage",
            ],
        )
        assert result.exit_code == 0
        assert output_file.exists()

    def test_export_html(self, cli_runner, sample_workspace, temp_dir):
        """export命令HTML格式"""
        output_file = temp_dir / "report.html"
        result = cli_runner.invoke(
            main,
            [
                "-w", str(sample_workspace),
                "export", str(output_file),
                "-f", "html",
                "--include-coverage",
            ],
        )
        assert result.exit_code == 0
        assert output_file.exists()

    def test_export_backup(self, cli_runner, sample_workspace, temp_dir):
        """export命令备份"""
        output_file = temp_dir / "backup.zip"
        result = cli_runner.invoke(
            main,
            [
                "-w", str(sample_workspace),
                "export", str(output_file),
                "-f", "backup",
            ],
        )
        assert result.exit_code == 0
        assert output_file.exists()

    def test_export_json(self, cli_runner, sample_workspace, temp_dir):
        """export命令JSON输出"""
        output_file = temp_dir / "report.md"
        result = cli_runner.invoke(
            main,
            [
                "-w", str(sample_workspace),
                "--json",
                "export", str(output_file),
                "-f", "markdown",
                "--include-coverage",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"

    def test_export_restore(self, cli_runner, sample_workspace, temp_dir):
        """export命令恢复备份"""
        backup_file = temp_dir / "backup.zip"
        cli_runner.invoke(
            main,
            ["-w", str(sample_workspace), "export", str(backup_file), "-f", "backup"],
        )

        restore_dir = temp_dir / "restored"
        result = cli_runner.invoke(
            main,
            ["-w", str(restore_dir), "export", str(backup_file), "--restore"],
        )
        assert result.exit_code == 0
        assert (restore_dir / "config.yaml").exists()

    def test_ingest_file(self, cli_runner, sample_workspace):
        """ingest命令"""
        sample_file = sample_workspace / "sample_data" / "sample_temperature.csv"
        if sample_file.exists():
            result = cli_runner.invoke(
                main,
                ["-w", str(sample_workspace), "ingest", str(sample_file)],
            )
            assert result.exit_code == 0

    def test_ingest_file_json(self, cli_runner, sample_workspace):
        """ingest命令JSON输出"""
        sample_file = sample_workspace / "sample_data" / "sample_temperature.csv"
        if sample_file.exists():
            result = cli_runner.invoke(
                main,
                ["-w", str(sample_workspace), "--json", "ingest", str(sample_file)],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "total_imported" in data or "results" in data
