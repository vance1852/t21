"""命令行入口"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from . import __version__
from .config import Config
from .database import DatabaseManager, get_db
from .sample_data import generate_sample_workspace
from .ingest import ingest_file, IngestError
from .audit import audit_data
from .coverage import calculate_coverage
from .simulate import (
    simulate_plan,
    simulate_maintenance_window,
    simulate_custom,
    get_all_plans,
    get_all_maintenance_windows,
)
from .recommend import recommend_keep, recommend_maintain
from .export import export_report, create_backup, restore_backup


def _fix_terminal_encoding() -> None:
    """修复Windows终端编码问题（延迟执行，避免干扰pytest等测试框架）"""
    if sys.platform != "win32":
        return
    try:
        if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
            if hasattr(sys.stdout, "buffer"):
                sys.stdout = io.TextIOWrapper(
                    sys.stdout.buffer, encoding="utf-8", errors="replace"
                )
        if hasattr(sys.stderr, "isatty") and sys.stderr.isatty():
            if hasattr(sys.stderr, "buffer"):
                sys.stderr = io.TextIOWrapper(
                    sys.stderr.buffer, encoding="utf-8", errors="replace"
                )
    except Exception:
        pass


def _make_console() -> Console:
    """创建Console实例，适配Windows终端"""
    kwargs: dict = {"highlight": False, "emoji": False, "force_interactive": False}
    if sys.platform == "win32":
        kwargs["color_system"] = "windows"
    try:
        return Console(**kwargs)
    except Exception:
        kwargs["force_terminal"] = False
        kwargs["color_system"] = None
        return Console(**kwargs)


console = _make_console()


def _load_config(workspace: str) -> Config:
    """加载配置"""
    config_path = Path(workspace) / "config.yaml"
    if not config_path.exists():
        raise click.ClickException(
            f"配置文件不存在: {config_path}\n请先运行 'ocean-sentinel init' 初始化工作区"
        )
    return Config.from_file(config_path)


def _get_db(workspace: str, config: Config) -> DatabaseManager:
    """获取数据库连接"""
    db_path = Path(workspace) / config.get("database.path", "data/ocean_sentinel.db")
    return get_db(db_path)


def _output_json(data: dict) -> None:
    """输出JSON格式"""
    click.echo(json.dumps(data, ensure_ascii=False, indent=2))


def _is_json_output(ctx: click.Context, local_json: bool = False) -> bool:
    """判断是否需要JSON输出，优先使用子命令参数，否则使用全局参数"""
    if local_json:
        return True
    return bool(ctx.obj.get("json_output", False))


def _severity_color(severity: str) -> str:
    """严重程度对应颜色"""
    colors = {
        "critical": "red",
        "warning": "yellow",
        "marginal": "bright_yellow",
        "ok": "green",
    }
    return colors.get(severity, "white")


def _risk_level_color(level: str) -> str:
    """风险等级对应颜色"""
    colors = {
        "critical": "red",
        "warning": "yellow",
        "marginal": "bright_yellow",
        "ok": "green",
    }
    return colors.get(level, "white")


@click.group()
@click.version_option(version=__version__, prog_name="ocean-sentinel")
@click.option(
    "--workspace",
    "-w",
    default=".",
    help="工作区目录路径",
    type=click.Path(),
)
@click.option("--json", "json_output", is_flag=True, help="以JSON格式输出结果")
@click.pass_context
def main(ctx: click.Context, workspace: str, json_output: bool) -> None:
    """Ocean Sentinel - 近海浮标与水下传感器数据质量审计及覆盖率分析工具"""
    _fix_terminal_encoding()
    ctx.ensure_object(dict)
    ctx.obj["workspace"] = str(Path(workspace).resolve())
    ctx.obj["json_output"] = json_output


@main.command()
@click.argument("workspace_path", type=click.Path(), default=".")
@click.option("--force", "-f", is_flag=True, help="强制覆盖已有文件")
@click.option("--json", "json_output_local", is_flag=True, help="以JSON格式输出结果")
@click.pass_context
def init(ctx: click.Context, workspace_path: str, force: bool, json_output_local: bool) -> None:
    """初始化示例工作区"""
    path = Path(workspace_path).resolve()
    json_output = _is_json_output(ctx, json_output_local)

    config_path = path / "config.yaml"
    if config_path.exists() and not force:
        if json_output:
            _output_json({"status": "error", "message": f"工作区已存在: {path}"})
        else:
            console.print(f"[yellow]工作区已存在: {path}[/yellow]")
            console.print("使用 --force 选项强制覆盖")
        sys.exit(1)

    try:
        result = generate_sample_workspace(path)
        if json_output:
            _output_json({
                "status": "ok",
                "workspace": str(path),
                "stats": result.get("stats", {}),
                "created_files": result.get("created_files", []),
            })
        else:
            console.print(Panel.fit(
                f"[green]工作区初始化成功[/green]\n\n"
                f"路径: {path}\n"
                f"网格: {result.get('stats', {}).get('grids', 0)} 个\n"
                f"观测站: {result.get('stats', {}).get('stations', 0)} 个\n"
                f"传感器: {result.get('stats', {}).get('sensors', 0)} 个\n\n"
                f"已创建 {len(result.get('created_files', []))} 个文件",
                title="[Ocean Sentinel]",
                border_style="blue",
            ))
    except Exception as e:
        if json_output:
            _output_json({"status": "error", "message": str(e)})
        else:
            console.print(f"[red]初始化失败: {e}[/red]")
        sys.exit(1)


@main.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--sensor", "-s", help="指定传感器ID（用于元数据文件）")
@click.option("--json", "json_output_local", is_flag=True, help="以JSON格式输出结果")
@click.pass_context
def ingest(ctx: click.Context, files: tuple[str, ...], sensor: Optional[str], json_output_local: bool) -> None:
    """导入观测数据文件"""
    workspace = ctx.obj["workspace"]
    json_output = _is_json_output(ctx, json_output_local)

    if not files:
        if json_output:
            _output_json({"status": "error", "message": "请指定要导入的文件"})
        else:
            console.print("[red]请指定要导入的文件[/red]")
        sys.exit(1)

    try:
        config = _load_config(workspace)
        db = _get_db(workspace, config)
    except Exception as e:
        if json_output:
            _output_json({"status": "error", "message": str(e)})
        else:
            console.print(f"[red]{e}[/red]")
        sys.exit(1)

    all_results = []
    total_imported = 0
    total_errors = 0

    for file_path in files:
        try:
            result = ingest_file(file_path, db, config)
            all_results.append({
                "file": file_path,
                "result": result.to_dict(),
            })
            total_imported += result.imported_records
            total_errors += result.error_records
        except IngestError as e:
            all_results.append({
                "file": file_path,
                "error": str(e),
            })
            total_errors += 1

    db.close()

    if json_output:
        _output_json({
            "status": "ok" if total_errors == 0 else "partial",
            "files_processed": len(files),
            "total_imported": total_imported,
            "total_errors": total_errors,
            "results": all_results,
        })
    else:
        table = Table(title="导入结果", show_header=True, header_style="bold blue")
        table.add_column("文件", style="cyan")
        table.add_column("总记录", justify="right")
        table.add_column("已导入", justify="right", style="green")
        table.add_column("跳过", justify="right", style="yellow")
        table.add_column("错误", justify="right", style="red")
        table.add_column("越界值", justify="right")

        for item in all_results:
            if "error" in item:
                table.add_row(item["file"], "-", "-", "-", item["error"], "-")
            else:
                r = item["result"]
                table.add_row(
                    item["file"],
                    str(r["total_records"]),
                    str(r["imported_records"]),
                    str(r["skipped_records"]),
                    str(r["error_records"]),
                    str(r["out_of_range"]),
                )

        console.print(table)

        if total_errors > 0:
            console.print(f"\n[yellow]注意: 有 {total_errors} 个错误，请检查数据[/yellow]")
        else:
            console.print(f"\n[green]导入完成: 共 {total_imported} 条记录[/green]")


@main.command()
@click.option("--sensor", "-s", help="指定传感器ID")
@click.option("--start", help="开始时间 (ISO格式)")
@click.option("--end", help="结束时间 (ISO格式)")
@click.option("--daily", is_flag=True, help="显示按天汇总")
@click.option("--json", "json_output_local", is_flag=True, help="以JSON格式输出结果")
@click.pass_context
def audit(ctx: click.Context, sensor: Optional[str], start: Optional[str], end: Optional[str], daily: bool, json_output_local: bool) -> None:
    """执行数据质量审计"""
    workspace = ctx.obj["workspace"]
    json_output = _is_json_output(ctx, json_output_local)

    try:
        config = _load_config(workspace)
        db = _get_db(workspace, config)
    except Exception as e:
        if json_output:
            _output_json({"status": "error", "message": str(e)})
        else:
            console.print(f"[red]{e}[/red]")
        sys.exit(1)

    try:
        result = audit_data(db, config, sensor, start, end)
        db.close()

        if json_output:
            _output_json(result.to_dict())
        else:
            _print_audit_result(result, daily)
    except Exception as e:
        db.close()
        if json_output:
            _output_json({"status": "error", "message": str(e)})
        else:
            console.print(f"[red]审计失败: {e}[/red]")
        sys.exit(1)


def _print_audit_result(result, daily: bool) -> None:
    """打印审计结果"""
    console.print(Panel.fit(
        f"总记录数: [bold]{result.total_records:,}[/bold]\n"
        f"问题总数: [bold]{result.issues_count:,}[/bold]\n"
        f"缺测段: [yellow]{len(result.gaps)}[/yellow]\n"
        f"离群点: [yellow]{len(result.outliers)}[/yellow]\n"
        f"漂移次数: [yellow]{len(result.drifts)}[/yellow]\n"
        f"越界值: [red]{len(result.out_of_range)}[/red]\n"
        f"时钟偏移: [yellow]{len(result.clock_offsets)}[/yellow]",
        title="[数据质量审计报告]",
        border_style="blue",
    ))

    if result.gaps:
        console.print()
        table = Table(title="缺测段 (Top 10)", show_header=True, header_style="bold")
        table.add_column("传感器", style="cyan")
        table.add_column("开始时间")
        table.add_column("结束时间")
        table.add_column("时长(小时)", justify="right")
        table.add_column("缺失点数", justify="right")
        table.add_column("严重程度")

        for gap in sorted(result.gaps, key=lambda x: x["duration_hours"], reverse=True)[:10]:
            color = _severity_color(gap["severity"])
            table.add_row(
                gap["sensor_id"],
                gap["start"],
                gap["end"],
                f"{gap['duration_hours']:.1f}",
                str(gap["missing_points"]),
                f"[{color}]{gap['severity']}[/{color}]",
            )
        console.print(table)

    if result.outliers:
        console.print()
        table = Table(title="离群点 (Top 10)", show_header=True, header_style="bold")
        table.add_column("传感器", style="cyan")
        table.add_column("时间")
        table.add_column("数值", justify="right")
        table.add_column("检测方法")

        for outlier in result.outliers[:10]:
            table.add_row(
                outlier["sensor_id"],
                outlier["timestamp"],
                f"{outlier['value']:.4f}",
                outlier["method"],
            )
        console.print(table)

    if daily and result.daily_summary:
        console.print()
        table = Table(title="按天汇总", show_header=True, header_style="bold")
        table.add_column("日期", style="cyan")
        table.add_column("问题数", justify="right")
        table.add_column("缺测", justify="right")
        table.add_column("离群点", justify="right")
        table.add_column("严重问题", justify="right", style="red")

        for day, summary in sorted(result.daily_summary.items()):
            table.add_row(
                day,
                str(summary.get("issues", 0)),
                str(summary.get("gaps", 0)),
                str(summary.get("outliers", 0)),
                str(summary.get("critical_count", 0)),
            )
        console.print(table)


@main.command()
@click.option("--grid", "-g", help="指定网格ID")
@click.option("--start", help="开始时间")
@click.option("--end", help="结束时间")
@click.option("--detail", "-d", is_flag=True, help="显示详细信息")
@click.option("--json", "json_output_local", is_flag=True, help="以JSON格式输出结果")
@click.pass_context
def coverage(ctx: click.Context, grid: Optional[str], start: Optional[str], end: Optional[str], detail: bool, json_output_local: bool) -> None:
    """计算覆盖率"""
    workspace = ctx.obj["workspace"]
    json_output = _is_json_output(ctx, json_output_local)

    try:
        config = _load_config(workspace)
        db = _get_db(workspace, config)
    except Exception as e:
        if json_output:
            _output_json({"status": "error", "message": str(e)})
        else:
            console.print(f"[red]{e}[/red]")
        sys.exit(1)

    try:
        result = calculate_coverage(db, config, start, end)
        db.close()

        if json_output:
            _output_json(result.to_dict())
        else:
            _print_coverage_result(result, detail, grid)
    except Exception as e:
        db.close()
        if json_output:
            _output_json({"status": "error", "message": str(e)})
        else:
            console.print(f"[red]覆盖率计算失败: {e}[/red]")
        sys.exit(1)


def _print_coverage_result(result, detail: bool, grid_filter: Optional[str]) -> None:
    """打印覆盖率结果"""
    color = _risk_level_color(result.overall_level)
    console.print(Panel.fit(
        f"整体覆盖率: [bold]{result.overall_ratio:.1%}[/bold]\n"
        f"风险等级: [{color}] {result.overall_level}[/{color}]\n"
        f"不达标网格: [red]{len(result.under_min)}[/red] 个",
        title="[覆盖率报告]",
        border_style="blue",
    ))

    grids = result.grid_coverage
    if grid_filter:
        grids = {k: v for k, v in grids.items() if k == grid_filter}

    console.print()
    table = Table(title="网格覆盖率", show_header=True, header_style="bold")
    table.add_column("网格", style="cyan")
    table.add_column("覆盖率", justify="right")
    table.add_column("风险等级")
    table.add_column("达标", justify="center")
    table.add_column("变量数", justify="right")

    for grid_id in sorted(grids.keys()):
        grid_info = grids[grid_id]
        color = _risk_level_color(grid_info["risk_level"])
        table.add_row(
            grid_id,
            f"{grid_info['coverage_ratio']:.1%}",
            f"[{color}]{grid_info['risk_level']}[/{color}]",
            "[green]Y[/green]" if grid_info["meets_minimum"] else "[red]N[/red]",
            str(grid_info["total_variables_covered"]),
        )
    console.print(table)

    if detail:
        console.print()
        table = Table(title="变量覆盖率", show_header=True, header_style="bold")
        table.add_column("变量", style="cyan")
        table.add_column("覆盖率", justify="right")
        for var, ratio in sorted(result.variable_coverage.items()):
            table.add_row(var, f"{ratio:.1%}")
        console.print(table)

        console.print()
        table = Table(title="深度层覆盖率", show_header=True, header_style="bold")
        table.add_column("深度层", style="cyan")
        table.add_column("覆盖率", justify="right")
        for layer, ratio in sorted(result.depth_layer_coverage.items()):
            table.add_row(layer, f"{ratio:.1%}")
        console.print(table)


@main.command()
@click.option("--plan", "-p", help="撤收方案ID")
@click.option("--window", "-w", "window_id", help="维护窗口ID")
@click.option("--sensors", "-s", help="自定义撤收传感器ID列表，逗号分隔")
@click.option("--start", help="开始时间")
@click.option("--end", help="结束时间")
@click.option("--list", "list_items", is_flag=True, help="列出所有方案/窗口")
@click.option("--json", "json_output_local", is_flag=True, help="以JSON格式输出结果")
@click.pass_context
def simulate(ctx: click.Context, plan: Optional[str], window_id: Optional[str], sensors: Optional[str],
             start: Optional[str], end: Optional[str], list_items: bool, json_output_local: bool) -> None:
    """模拟撤收或维护的影响"""
    workspace = ctx.obj["workspace"]
    json_output = _is_json_output(ctx, json_output_local)

    try:
        config = _load_config(workspace)
        db = _get_db(workspace, config)
    except Exception as e:
        if json_output:
            _output_json({"status": "error", "message": str(e)})
        else:
            console.print(f"[red]{e}[/red]")
        sys.exit(1)

    try:
        if list_items:
            plans = get_all_plans(db)
            windows = get_all_maintenance_windows(db)
            db.close()
            if json_output:
                _output_json({"plans": plans, "maintenance_windows": windows})
            else:
                _print_plan_list(plans, windows)
            return

        if plan:
            result = simulate_plan(db, config, plan, start, end)
        elif window_id:
            result = simulate_maintenance_window(db, config, window_id)
        elif sensors:
            sensor_list = [s.strip() for s in sensors.split(",") if s.strip()]
            result = simulate_custom(db, config, sensor_list, start, end)
        else:
            db.close()
            if json_output:
                _output_json({"status": "error", "message": "请指定 --plan, --window 或 --sensors"})
            else:
                console.print("[red]请指定 --plan, --window 或 --sensors[/red]")
            sys.exit(1)

        db.close()

        if json_output:
            _output_json(result.to_dict())
        else:
            _print_simulation_result(result)
    except Exception as e:
        db.close()
        if json_output:
            _output_json({"status": "error", "message": str(e)})
        else:
            console.print(f"[red]模拟失败: {e}[/red]")
        sys.exit(1)


def _print_plan_list(plans: list, windows: list) -> None:
    """打印方案和窗口列表"""
    if plans:
        table = Table(title="撤收方案", show_header=True, header_style="bold")
        table.add_column("ID", style="cyan")
        table.add_column("名称")
        table.add_column("类型")
        table.add_column("开始时间")
        table.add_column("结束时间")
        table.add_column("传感器数", justify="right")

        for p in plans:
            table.add_row(
                p["id"],
                p["name"],
                p.get("plan_type", "-"),
                p.get("start_date", "-"),
                p.get("end_date", "-"),
                str(len(p.get("sensors", []))),
            )
        console.print(table)

    if windows:
        table = Table(title="维护窗口", show_header=True, header_style="bold")
        table.add_column("ID", style="cyan")
        table.add_column("名称")
        table.add_column("开始时间")
        table.add_column("结束时间")
        table.add_column("最大撤收数", justify="right")
        table.add_column("传感器数", justify="right")

        for w in windows:
            table.add_row(
                w["id"],
                w["name"],
                w["start_date"],
                w["end_date"],
                str(w.get("max_sensors_out", "-")),
                str(len(w.get("sensors", []))),
            )
        console.print(table)


def _print_simulation_result(result) -> None:
    """打印模拟结果"""
    change_color = "green" if result.overall_risk_change == "improved" else (
        "red" if result.overall_risk_change == "degraded" else "white"
    )
    change_text = "改善" if result.overall_risk_change == "improved" else (
        "下降" if result.overall_risk_change == "degraded" else "无变化"
    )

    console.print(Panel.fit(
        f"方案: [bold]{result.plan_name}[/bold] ({result.plan_id})\n"
        f"撤收传感器: [yellow]{len(result.sensors_removed)}[/yellow] 个\n\n"
        f"基线覆盖率: {result.baseline_coverage.overall_ratio:.1%} "
        f"({result.baseline_coverage.overall_level})\n"
        f"模拟覆盖率: {result.simulated_coverage.overall_ratio:.1%} "
        f"({result.simulated_coverage.overall_level})\n"
        f"整体变化: [{change_color}]{change_text}[/{change_color}]\n\n"
        f"受影响网格: [yellow]{len(result.impacted_grids)}[/yellow] 个\n"
        f"新增不达标: [red]{len(result.newly_under_min)}[/red] 个\n"
        f"风险等级下降: [red]{len(result.risk_level_downgrades)}[/red] 个",
        title="[撤收模拟结果]",
        border_style="blue",
    ))

    if result.impacted_grids:
        console.print()
        table = Table(title="受影响网格", show_header=True, header_style="bold")
        table.add_column("网格", style="cyan")
        table.add_column("基线", justify="right")
        table.add_column("模拟", justify="right")
        table.add_column("变化", justify="right")
        table.add_column("风险等级变化")
        table.add_column("是否达标")

        for grid in sorted(result.impacted_grids, key=lambda x: x["ratio_change"]):
            diff = grid["ratio_change"]
            diff_color = "green" if diff > 0 else "red"
            base_meet = "[green]Y[/green]" if grid["baseline_meets_min"] else "[red]N[/red]"
            sim_meet = "[green]Y[/green]" if grid["simulated_meets_min"] else "[red]N[/red]"
            level_change = "DOWN" if grid["level_downgraded"] else "-"

            table.add_row(
                grid["grid_id"],
                f"{grid['baseline_ratio']:.1%}",
                f"{grid['simulated_ratio']:.1%}",
                f"[{diff_color}]{diff:+.1%}[/{diff_color}]",
                f"[red]{level_change}[/red]" if grid["level_downgraded"] else level_change,
                f"{base_meet} → {sim_meet}",
            )
        console.print(table)

    if result.impacted_variables:
        console.print()
        table = Table(title="受影响变量", show_header=True, header_style="bold")
        table.add_column("变量", style="cyan")
        table.add_column("基线", justify="right")
        table.add_column("模拟", justify="right")
        table.add_column("变化", justify="right")

        for var in sorted(result.impacted_variables, key=lambda x: x["ratio_change"]):
            diff = var["ratio_change"]
            diff_color = "green" if diff > 0 else "red"
            table.add_row(
                var["variable"],
                f"{var['baseline_ratio']:.1%}",
                f"{var['simulated_ratio']:.1%}",
                f"[{diff_color}]{diff:+.1%}[/{diff_color}]",
            )
        console.print(table)


@main.command()
@click.option("--mode", "-m", type=click.Choice(["keep", "maintain"]), default="keep",
              help="推荐模式: keep(保留) 或 maintain(检修)")
@click.option("--max-sensors", type=int, help="最大保留传感器数")
@click.option("--min-coverage", type=float, help="最低覆盖率要求")
@click.option("--max-cost", type=float, help="最大维护成本")
@click.option("--count", type=int, help="推荐数量")
@click.option("--json", "json_output_local", is_flag=True, help="以JSON格式输出结果")
@click.pass_context
def recommend(ctx: click.Context, mode: str, max_sensors: Optional[int], min_coverage: Optional[float],
              max_cost: Optional[float], count: Optional[int], json_output_local: bool) -> None:
    """推荐传感器保留或检修优先级"""
    workspace = ctx.obj["workspace"]
    json_output = _is_json_output(ctx, json_output_local)

    try:
        config = _load_config(workspace)
        db = _get_db(workspace, config)
    except Exception as e:
        if json_output:
            _output_json({"status": "error", "message": str(e)})
        else:
            console.print(f"[red]{e}[/red]")
        sys.exit(1)

    try:
        if mode == "keep":
            result = recommend_keep(db, config, max_sensors, min_coverage, max_cost)
        else:
            result = recommend_maintain(db, config, count)

        db.close()

        if json_output:
            _output_json(result.to_dict())
        else:
            _print_recommendation_result(result, mode)
    except Exception as e:
        db.close()
        if json_output:
            _output_json({"status": "error", "message": str(e)})
        else:
            console.print(f"[red]推荐失败: {e}[/red]")
        sys.exit(1)


def _print_recommendation_result(result, mode: str) -> None:
    """打印推荐结果"""
    if mode == "keep":
        console.print(Panel.fit(
            f"策略: [bold]{result.strategy}[/bold]\n"
            f"总传感器: {result.total_sensors} 个\n"
            f"建议保留: [green]{result.keep_count}[/green] 个\n"
            f"建议撤收: [yellow]{result.remove_count}[/yellow] 个\n"
            f"预期覆盖率: {result.expected_coverage:.1%}\n"
            f"总维护成本: {result.total_maintenance_cost:.2f}",
            title="[传感器保留推荐]",
            border_style="blue",
        ))

        if result.keep:
            console.print()
            table = Table(title="推荐保留 (Top 10)", show_header=True, header_style="bold")
            table.add_column("#", justify="right", style="dim")
            table.add_column("传感器", style="cyan")
            table.add_column("分数", justify="right")
            table.add_column("变量")
            table.add_column("成本", justify="right")
            table.add_column("稳定性", justify="right")
            table.add_column("主要理由")

            for i, item in enumerate(result.keep[:10], 1):
                table.add_row(
                    str(i),
                    item.sensor_id,
                    f"{item.score:.3f}",
                    ", ".join(item.variables),
                    f"{item.maintenance_cost}",
                    f"{item.stability:.2f}",
                    item.reasons[0] if item.reasons else "-",
                )
            console.print(table)

        if result.remove:
            console.print()
            table = Table(title="建议撤收 (Top 10)", show_header=True, header_style="bold")
            table.add_column("传感器", style="cyan")
            table.add_column("分数", justify="right")
            table.add_column("变量")
            table.add_column("理由")

            for item in result.remove[:10]:
                table.add_row(
                    item.sensor_id,
                    f"{item.score:.3f}",
                    ", ".join(item.variables),
                    item.reasons[0] if item.reasons else "-",
                )
            console.print(table)
    else:
        console.print(Panel.fit(
            f"策略: [bold]{result.strategy}[/bold]\n"
            f"总传感器: {result.total_sensors} 个\n"
            f"优先检修: [yellow]{len(result.maintain_first)}[/yellow] 个",
            title="[检修优先级推荐]",
            border_style="blue",
        ))

        if result.maintain_first:
            console.print()
            table = Table(title="优先检修列表", show_header=True, header_style="bold")
            table.add_column("#", justify="right", style="dim")
            table.add_column("传感器", style="cyan")
            table.add_column("优先级分", justify="right")
            table.add_column("变量")
            table.add_column("成本", justify="right")
            table.add_column("主要理由")

            for i, item in enumerate(result.maintain_first, 1):
                table.add_row(
                    str(i),
                    item.sensor_id,
                    f"{item.score:.3f}",
                    ", ".join(item.variables),
                    f"{item.maintenance_cost}",
                    item.reasons[0] if item.reasons else "-",
                )
            console.print(table)


@main.command()
@click.argument("output", type=click.Path())
@click.option("--format", "-f", "fmt", type=click.Choice(["markdown", "html", "backup"]), default="markdown",
              help="输出格式")
@click.option("--include-audit", is_flag=True, help="包含审计报告")
@click.option("--include-coverage", is_flag=True, help="包含覆盖率报告")
@click.option("--include-simulation", is_flag=True, help="包含模拟报告")
@click.option("--include-recommendation", is_flag=True, help="包含推荐报告")
@click.option("--plan", help="模拟方案ID")
@click.option("--no-data", is_flag=True, help="备份时不包含观测数据")
@click.option("--restore", is_flag=True, help="从备份恢复")
@click.option("--overwrite", is_flag=True, help="恢复时覆盖现有文件")
@click.option("--json", "json_output_local", is_flag=True, help="以JSON格式输出结果")
@click.pass_context
def export(ctx: click.Context, output: str, fmt: str, include_audit: bool, include_coverage: bool,
           include_simulation: bool, include_recommendation: bool, plan: Optional[str],
           no_data: bool, restore: bool, overwrite: bool, json_output_local: bool) -> None:
    """导出报告或备份"""
    workspace = ctx.obj["workspace"]
    json_output = _is_json_output(ctx, json_output_local)

    if restore:
        try:
            result = restore_backup(output, workspace, overwrite)
            if json_output:
                _output_json({"status": "ok", **result})
            else:
                console.print(f"[green]恢复成功: {len(result.get('restored_files', []))} 个文件[/green]")
                for f in result.get("restored_files", []):
                    console.print(f"  - {f}")
        except Exception as e:
            if json_output:
                _output_json({"status": "error", "message": str(e)})
            else:
                console.print(f"[red]恢复失败: {e}[/red]")
            sys.exit(1)
        return

    try:
        config = _load_config(workspace)
        db = _get_db(workspace, config)
    except Exception as e:
        if json_output:
            _output_json({"status": "error", "message": str(e)})
        else:
            console.print(f"[red]{e}[/red]")
        sys.exit(1)

    try:
        if fmt == "backup":
            result_path = create_backup(db, config, output, include_data=not no_data)
            db.close()
            if json_output:
                _output_json({"status": "ok", "output": str(result_path)})
            else:
                console.print(f"[green]备份已创建: {result_path}[/green]")
            return

        audit_result = audit_data(db, config) if include_audit else None
        coverage_result = calculate_coverage(db, config) if include_coverage else None

        sim_result = None
        if include_simulation and plan:
            sim_result = simulate_plan(db, config, plan)

        rec_result = None
        if include_recommendation:
            rec_result = recommend_keep(db, config)

        result_path = export_report(
            fmt, output, db, config,
            audit_result, coverage_result, sim_result, rec_result,
        )
        db.close()

        if json_output:
            _output_json({"status": "ok", "output": str(result_path)})
        else:
            console.print(f"[green]报告已导出: {result_path}[/green]")
    except Exception as e:
        db.close()
        if json_output:
            _output_json({"status": "error", "message": str(e)})
        else:
            console.print(f"[red]导出失败: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
