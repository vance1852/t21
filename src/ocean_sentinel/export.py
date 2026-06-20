"""报告导出与备份模块"""

from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .config import Config
from .database import DatabaseManager
from .utils import format_timestamp


def export_report(
    format_type: str,
    output_path: str | Path,
    db: DatabaseManager,
    config: Config,
    audit_result: Any = None,
    coverage_result: Any = None,
    simulation_result: Any = None,
    recommendation_result: Any = None,
) -> Path:
    """导出报告"""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if format_type == "markdown":
        return _export_markdown(output, db, config, audit_result, coverage_result, simulation_result, recommendation_result)
    elif format_type == "html":
        return _export_html(output, db, config, audit_result, coverage_result, simulation_result, recommendation_result)
    else:
        raise ValueError(f"不支持的导出格式: {format_type}")


def _export_markdown(
    output: Path,
    db: DatabaseManager,
    config: Config,
    audit_result,
    coverage_result,
    simulation_result,
    recommendation_result,
) -> Path:
    """导出Markdown报告"""
    lines = []

    title = config.get("report.title", "海洋观测数据质量与覆盖报告")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"生成时间: {format_timestamp(datetime.now(timezone.utc))}")
    lines.append("")

    if coverage_result:
        lines.append("## 一、覆盖率概览")
        lines.append("")
        lines.append(f"- 整体覆盖率: **{coverage_result.overall_ratio:.1%}**")
        lines.append(f"- 风险等级: **{coverage_result.overall_level}**")
        lines.append(f"- 不达标网格数: {len(coverage_result.under_min)}")
        lines.append("")
        lines.append("### 网格覆盖率详情")
        lines.append("")
        lines.append("| 网格 | 覆盖率 | 风险等级 | 达标 |")
        lines.append("|------|--------|----------|------|")
        for grid_id, grid_info in sorted(coverage_result.grid_coverage.items()):
            lines.append(
                f"| {grid_id} | {grid_info['coverage_ratio']:.1%} | {grid_info['risk_level']} | {'是' if grid_info['meets_minimum'] else '否'} |"
            )
        lines.append("")

    if audit_result:
        lines.append("## 二、数据质量审计")
        lines.append("")
        lines.append(f"- 总记录数: {audit_result.total_records}")
        lines.append(f"- 问题总数: {audit_result.issues_count}")
        lines.append(f"- 缺测段数: {len(audit_result.gaps)}")
        lines.append(f"- 离群点数: {len(audit_result.outliers)}")
        lines.append(f"- 漂移次数: {len(audit_result.drifts)}")
        lines.append(f"- 越界值数: {len(audit_result.out_of_range)}")
        lines.append("")

        if audit_result.gaps:
            lines.append("### 缺测段")
            lines.append("")
            lines.append("| 传感器 | 开始时间 | 结束时间 | 持续(小时) | 严重程度 |")
            lines.append("|--------|----------|----------|------------|----------|")
            for gap in audit_result.gaps[:20]:
                lines.append(
                    f"| {gap['sensor_id']} | {gap['start']} | {gap['end']} | {gap['duration_hours']} | {gap['severity']} |"
                )
            lines.append("")

    if simulation_result:
        lines.append("## 三、撤收模拟")
        lines.append("")
        lines.append(f"- 方案: {simulation_result.plan_name} ({simulation_result.plan_id})")
        lines.append(f"- 撤收传感器数: {len(simulation_result.sensors_removed)}")
        lines.append("")
        if simulation_result.baseline_coverage and simulation_result.simulated_coverage:
            lines.append(
                f"- 基线覆盖率: {simulation_result.baseline_coverage.overall_ratio:.1%} -> "
                f"模拟覆盖率: {simulation_result.simulated_coverage.overall_ratio:.1%}"
            )
        lines.append(f"- 受影响网格: {len(simulation_result.impacted_grids)}")
        lines.append(f"- 新增不达标网格: {len(simulation_result.newly_under_min)}")
        lines.append("")

    if recommendation_result:
        lines.append("## 四、传感器推荐")
        lines.append("")
        lines.append(f"- 策略: {recommendation_result.strategy}")
        lines.append(f"- 建议保留: {recommendation_result.keep_count} 个")
        lines.append(f"- 建议撤收: {recommendation_result.remove_count} 个")
        lines.append(f"- 预期覆盖率: {recommendation_result.expected_coverage:.1%}")
        lines.append(f"- 总维护成本: {recommendation_result.total_maintenance_cost:.2f}")
        lines.append("")

        if recommendation_result.keep:
            lines.append("### 推荐保留 Top 10")
            lines.append("")
            lines.append("| 传感器 | 分数 | 变量 | 成本 | 稳定性 | 理由 |")
            lines.append("|--------|------|------|------|--------|------|")
            for item in recommendation_result.keep[:10]:
                lines.append(
                    f"| {item.sensor_id} | {item.score:.3f} | {','.join(item.variables)} | "
                    f"{item.maintenance_cost} | {item.stability:.2f} | {'; '.join(item.reasons[:2])} |"
                )
            lines.append("")

    with open(output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output


def _export_html(
    output: Path,
    db: DatabaseManager,
    config: Config,
    audit_result,
    coverage_result,
    simulation_result,
    recommendation_result,
) -> Path:
    """导出HTML报告"""
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{config.get('report.title', '海洋观测报告')}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #f5f5f5; }}
.container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
h1 {{ color: #1a365d; border-bottom: 3px solid #3182ce; padding-bottom: 10px; }}
h2 {{ color: #2c5282; margin-top: 30px; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }}
h3 {{ color: #2d3748; }}
table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
th {{ background: #edf2f7; font-weight: 600; color: #2d3748; }}
tr:hover {{ background: #f7fafc; }}
.badge {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.85em; font-weight: 500; }}
.badge-ok {{ background: #c6f6d5; color: #22543d; }}
.badge-warning {{ background: #fefcbf; color: #744210; }}
.badge-critical {{ background: #fed7d7; color: #742a2a; }}
.badge-marginal {{ background: #fefcbf; color: #744210; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
.summary-card {{ background: #f7fafc; padding: 20px; border-radius: 8px; border-left: 4px solid #3182ce; }}
.summary-card .value {{ font-size: 2em; font-weight: bold; color: #2c5282; }}
.summary-card .label {{ color: #718096; margin-top: 5px; }}
.meta {{ color: #718096; font-size: 0.9em; }}
</style>
</head>
<body>
<div class="container">
<h1>🌊 {config.get('report.title', '海洋观测数据质量与覆盖报告')}</h1>
<p class="meta">生成时间: {format_timestamp(datetime.now(timezone.utc))}</p>
"""

    if coverage_result:
        risk_class = _risk_to_css_class(coverage_result.overall_level)
        html += f"""
<h2>一、覆盖率概览</h2>
<div class="summary-grid">
<div class="summary-card">
<div class="value">{coverage_result.overall_ratio:.1%}</div>
<div class="label">整体覆盖率</div>
</div>
<div class="summary-card">
<div class="value"><span class="badge badge-{risk_class}">{coverage_result.overall_level}</span></div>
<div class="label">风险等级</div>
</div>
<div class="summary-card">
<div class="value">{len(coverage_result.under_min)}</div>
<div class="label">不达标网格数</div>
</div>
</div>

<h3>网格覆盖率详情</h3>
<table>
<tr><th>网格</th><th>覆盖率</th><th>风险等级</th><th>达标</th></tr>
"""
        for grid_id, grid_info in sorted(coverage_result.grid_coverage.items()):
            grid_risk = _risk_to_css_class(grid_info["risk_level"])
            html += (
                f"<tr><td>{grid_id}</td><td>{grid_info['coverage_ratio']:.1%}</td>"
                f"<td><span class='badge badge-{grid_risk}'>{grid_info['risk_level']}</span></td>"
                f"<td>{'是' if grid_info['meets_minimum'] else '否'}</td></tr>"
            )
        html += "</table>"

    if audit_result:
        html += f"""
<h2>二、数据质量审计</h2>
<div class="summary-grid">
<div class="summary-card"><div class="value">{audit_result.total_records:,}</div><div class="label">总记录数</div></div>
<div class="summary-card"><div class="value">{audit_result.issues_count}</div><div class="label">问题总数</div></div>
<div class="summary-card"><div class="value">{len(audit_result.gaps)}</div><div class="label">缺测段数</div></div>
<div class="summary-card"><div class="value">{len(audit_result.outliers)}</div><div class="label">离群点数</div></div>
</div>
"""
        if audit_result.gaps:
            html += "<h3>缺测段</h3><table><tr><th>传感器</th><th>开始时间</th><th>结束时间</th><th>持续(小时)</th><th>严重程度</th></tr>"
            for gap in audit_result.gaps[:20]:
                sev_class = _risk_to_css_class(gap["severity"])
                html += (
                    f"<tr><td>{gap['sensor_id']}</td><td>{gap['start']}</td>"
                    f"<td>{gap['end']}</td><td>{gap['duration_hours']}</td>"
                    f"<td><span class='badge badge-{sev_class}'>{gap['severity']}</span></td></tr>"
                )
            html += "</table>"

    if simulation_result:
        html += f"""
<h2>三、撤收模拟</h2>
<p><strong>方案:</strong> {simulation_result.plan_name} ({simulation_result.plan_id})</p>
<p><strong>撤收传感器数:</strong> {len(simulation_result.sensors_removed)}</p>
"""
        if simulation_result.baseline_coverage and simulation_result.simulated_coverage:
            html += (
                f"<p><strong>覆盖率变化:</strong> "
                f"{simulation_result.baseline_coverage.overall_ratio:.1%} &rarr; "
                f"{simulation_result.simulated_coverage.overall_ratio:.1%}</p>"
            )
        html += (
            f"<p><strong>受影响网格:</strong> {len(simulation_result.impacted_grids)}</p>"
            f"<p><strong>新增不达标网格:</strong> {len(simulation_result.newly_under_min)}</p>"
        )

    if recommendation_result:
        html += f"""
<h2>四、传感器推荐</h2>
<div class="summary-grid">
<div class="summary-card"><div class="value">{recommendation_result.keep_count}</div><div class="label">建议保留</div></div>
<div class="summary-card"><div class="value">{recommendation_result.remove_count}</div><div class="label">建议撤收</div></div>
<div class="summary-card"><div class="value">{recommendation_result.expected_coverage:.1%}</div><div class="label">预期覆盖率</div></div>
<div class="summary-card"><div class="value">{recommendation_result.total_maintenance_cost:.2f}</div><div class="label">总维护成本</div></div>
</div>
"""
        if recommendation_result.keep:
            html += "<h3>推荐保留 Top 10</h3><table><tr><th>传感器</th><th>分数</th><th>变量</th><th>成本</th><th>稳定性</th><th>理由</th></tr>"
            for item in recommendation_result.keep[:10]:
                html += (
                    f"<tr><td>{item.sensor_id}</td><td>{item.score:.3f}</td>"
                    f"<td>{','.join(item.variables)}</td><td>{item.maintenance_cost}</td>"
                    f"<td>{item.stability:.2f}</td><td>{'; '.join(item.reasons[:2])}</td></tr>"
                )
            html += "</table>"

    html += """
</div>
</body>
</html>
"""

    with open(output, "w", encoding="utf-8") as f:
        f.write(html)

    return output


def _risk_to_css_class(level: str) -> str:
    """风险等级到CSS类名"""
    mapping = {
        "ok": "ok",
        "marginal": "marginal",
        "warning": "warning",
        "critical": "critical",
    }
    return mapping.get(level, "marginal")


def create_backup(
    db: DatabaseManager,
    config: Config,
    output_path: str | Path,
    include_data: bool = True,
) -> Path:
    """创建备份包"""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    tmpdir = Path(tempfile.mkdtemp(prefix="ocean_backup_"))
    try:
        db_path = Path(db.db_path)
        if db_path.exists() and include_data:
            dest_db = tmpdir / db_path.name
            shutil.copy2(db_path, dest_db)

        config_file = tmpdir / "config.yaml"
        config.save(config_file)

        manifest = {
            "version": "1.0",
            "created_at": format_timestamp(datetime.now(timezone.utc)),
            "database": db_path.name if include_data else None,
            "config": "config.yaml",
            "include_data": include_data,
        }
        with open(tmpdir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        if output.suffix in (".zip",):
            base_name = output.stem
            zip_path = tmpdir.parent / base_name
            shutil.make_archive(str(zip_path), "zip", str(tmpdir))
            final_zip = zip_path.with_suffix(".zip")
            shutil.move(str(final_zip), str(output))
        else:
            if output.exists():
                shutil.rmtree(output)
            shutil.copytree(tmpdir, output)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return output


def restore_backup(
    backup_path: str | Path,
    target_dir: str | Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    """从备份恢复"""
    backup = Path(backup_path)
    target = Path(target_dir)

    if not backup.exists():
        raise FileNotFoundError(f"备份文件不存在: {backup_path}")

    result = {"restored_files": [], "config_loaded": False, "db_restored": False}

    tmpdir = Path(tempfile.mkdtemp(prefix="ocean_restore_"))
    try:
        if backup.suffix == ".zip":
            import zipfile
            with zipfile.ZipFile(backup, "r") as zf:
                zf.extractall(tmpdir)
        else:
            shutil.copytree(backup, tmpdir, dirs_exist_ok=True)

        manifest_path = tmpdir / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            result["manifest"] = manifest

        config_src = tmpdir / "config.yaml"
        if config_src.exists():
            config_dst = target / "config.yaml"
            if config_dst.exists() and not overwrite:
                raise FileExistsError(f"配置文件已存在: {config_dst}")
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(config_src, config_dst)
            result["restored_files"].append(str(config_dst))
            result["config_loaded"] = True

        db_files = list(tmpdir.glob("*.db"))
        if db_files:
            data_dir = target / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            for db_file in db_files:
                dest_db = data_dir / db_file.name
                if dest_db.exists() and not overwrite:
                    raise FileExistsError(f"数据库文件已存在: {dest_db}")
                shutil.copy2(db_file, dest_db)
                result["restored_files"].append(str(dest_db))
                result["db_restored"] = True

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return result
