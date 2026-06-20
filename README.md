# Ocean Sentinel

近海浮标与水下传感器数据质量审计及覆盖率分析命令行工具。

## 功能特性

- **数据导入**：支持 CSV/JSON/YAML 格式，自动单位归一、时区处理、去重、越界标记
- **质量审计**：缺测段检测、短时抖动分析、校准前后漂移、时钟偏移、MAD 离群点检测
- **覆盖率分析**：网格覆盖、深度层覆盖、变量覆盖、邻接衰减、传感器替代折算
- **撤收模拟**：模拟撤收方案或维护窗口的影响，输出风险等级
- **智能推荐**：基于贪心策略的传感器保留/检修优先级推荐
- **报告导出**：Markdown/HTML 报告、可复导入备份包
- **纯本地运行**：基于 SQLite 和本地文件，无外部 API 依赖

## 安装

### 环境要求

- Python 3.11+

### 安装方式

```bash
# 克隆项目后，在项目根目录执行
pip install -e .
```

开发模式（含测试依赖）：

```bash
pip install -e ".[dev]"
```

## 快速开始

### 1. 初始化示例工作区

```bash
# 在当前目录初始化
ocean-sentinel init .

# 或指定目录
ocean-sentinel init my_workspace
```

初始化会创建：
- `config.yaml` - 配置文件
- `data/ocean_sentinel.db` - SQLite 数据库（含示例数据）
- `sample_data/` - 示例数据文件

### 2. 查看覆盖率

```bash
ocean-sentinel -w my_workspace coverage
```

预期输出：
```
╭─────────────────────────── 📈 覆盖率报告 ───────────────────────────╮
│ 整体覆盖率: 66.7%                                                    │
│ 风险等级:  marginal                                                  │
│ 不达标网格: 3 个                                                     │
╰──────────────────────────────────────────────────────────────────────╯

┏━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┓
┃ 网格   ┃ 覆盖率    ┃ 风险等级   ┃ 达标  ┃ 变量数  ┃
┡━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━┩
│ A1     │ 100.0%    │    ok      │   ✓    │ 5       │
│ A2     │ 80.0%     │    ok      │   ✓    │ 4       │
│ B1     │ 60.0%     │  warning  │   ✗    │ 3       │
└────────┴───────────┴────────────┴───────┴─────────┘
```

### 3. 数据质量审计

```bash
ocean-sentinel -w my_workspace audit
```

预期输出：
```
╭────────────────────────── 📊 数据质量审计报告 ──────────────────────────╮
│ 总记录数: 12,450                                                        │
│ 问题总数: 87                                                             │
│ 缺测段: 12                                                               │
│ 离群点: 45                                                               │
│ 漂移次数: 3                                                              │
│ 越界值: 8                                                                │
│ 时钟偏移: 1                                                              │
╰─────────────────────────────────────────────────────────────────────────╯
```

按天汇总：

```bash
ocean-sentinel -w my_workspace audit --daily
```

### 4. 导入数据

```bash
# 导入 CSV 文件
ocean-sentinel -w my_workspace ingest sample_data/sample_temperature.csv

# 导入多个文件
ocean-sentinel -w my_workspace ingest data1.csv data2.json data3.yaml
```

预期输出：
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┓
┃ 文件                       ┃ 总记录 ┃ 已导入 ┃  跳过  ┃  错误  ┃ 越界值  ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━━┩
│ sample_temperature.csv     │ 200    │ 198    │ 2      │ 0      │ 1       │
└────────────────────────────┴────────┴────────┴────────┴────────┴─────────┘

导入完成: 共 198 条记录
```

### 5. 撤收模拟

列出所有方案：

```bash
ocean-sentinel -w my_workspace simulate --list
```

模拟指定方案：

```bash
ocean-sentinel -w my_workspace simulate --plan plan_annual_service
```

自定义撤收模拟：

```bash
ocean-sentinel -w my_workspace simulate --sensors S001,S002,S005
```

预期输出：
```
╭────────────────────────────── 🎯 撤收模拟结果 ──────────────────────────────╮
│ 方案: 年度检修方案 (plan_annual_service)                                   │
│ 撤收传感器: 3 个                                                            │
│                                                                              │
│ 基线覆盖率: 77.8% (ok)                                                       │
│ 模拟覆盖率: 55.6% (warning)                                                  │
│ 整体变化: 下降                                                               │
│                                                                              │
│ 受影响网格: 5 个                                                             │
│ 新增不达标: 2 个                                                             │
│ 风险等级下降: 1 个                                                           │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### 6. 传感器推荐

推荐优先保留：

```bash
ocean-sentinel -w my_workspace recommend --mode keep
```

推荐优先检修：

```bash
ocean-sentinel -w my_workspace recommend --mode maintain
```

带约束的推荐：

```bash
# 最多保留 10 个传感器
ocean-sentinel -w my_workspace recommend --mode keep --max-sensors 10

# 最低覆盖率 70%
ocean-sentinel -w my_workspace recommend --mode keep --min-coverage 0.7

# 最大维护成本 5.0
ocean-sentinel -w my_workspace recommend --mode keep --max-cost 5.0
```

预期输出：
```
╭────────────────────────── 💡 传感器保留推荐 ──────────────────────────╮
│ 策略: greedy_keep                                                     │
│ 总传感器: 18 个                                                       │
│ 建议保留: 12 个                                                       │
│ 建议撤收: 6 个                                                        │
│ 预期覆盖率: 72.2%                                                     │
│ 总维护成本: 15.80                                                     │
╰──────────────────────────────────────────────────────────────────────╯

┏━━━━┳━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ #  ┃ 传感器    ┃  分数  ┃ 变量               ┃  成本  ┃ 稳定性   ┃ 主要理由         ┃
┡━━━━╇━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ 1  │ S001      │ 0.875  │ temperature         │ 1.0    │ 0.95     │ 数据质量优秀     │
│ 2  │ S004      │ 0.821  │ current_speed       │ 3.0    │ 0.88     │ 网格位置关键     │
└────┴───────────┴────────┴─────────────────────┴────────┴──────────┴──────────────────┘
```

### 7. 导出报告

导出 Markdown 报告：

```bash
ocean-sentinel -w my_workspace export report.md -f markdown --include-coverage --include-audit
```

导出 HTML 报告：

```bash
ocean-sentinel -w my_workspace export report.html -f html --include-coverage
```

创建备份：

```bash
ocean-sentinel -w my_workspace export backup.zip -f backup
```

从备份恢复：

```bash
ocean-sentinel -w new_workspace export backup.zip --restore
```

## JSON 输出

所有命令都支持 `--json` 选项，输出结构化 JSON 结果，便于自动化脚本调用：

```bash
ocean-sentinel -w my_workspace --json coverage
ocean-sentinel -w my_workspace --json audit
ocean-sentinel -w my_workspace --json simulate --plan plan_a
```

## 配置说明

配置文件位于工作区的 `config.yaml`，包含以下主要配置项：

### 变量配置

```yaml
variables:
  temperature:
    name: 海水温度
    unit: celsius
    valid_range: [-2.0, 40.0]
    outlier_mad_threshold: 3.0
```

### 覆盖率配置

```yaml
coverage:
  min_coverage_ratio: 0.7          # 最低覆盖率阈值
  adjacent_grid_decay: 0.6         # 相邻网格覆盖衰减系数
  adjacent_depth_decay: 0.7        # 相邻深度层覆盖衰减系数
  degraded_data_factor: 0.5        # 降级数据折算因子
  max_sensors_per_grid_var: 3      # 每网格每变量最大传感器数
  min_variables_per_grid: 3        # 每网格最少变量数
```

### 审计配置

```yaml
audit:
  gap_min_duration_minutes: 120    # 最小缺测段时长（分钟）
  mad_window_size: 50              # MAD滑动窗口大小
  mad_step: 10                     # MAD滑动步长
```

## 支持的变量

| 变量ID | 名称 | 默认单位 |
|--------|------|----------|
| temperature | 海水温度 | celsius |
| salinity | 盐度 | psu |
| current_speed | 流速 | m/s |
| ph | 酸碱度 | pH |
| dissolved_oxygen | 溶解氧 | mg/L |

## 风险等级

| 等级 | 阈值 | 含义 |
|------|------|------|
| critical | ≤ 30% | 严重不足 |
| warning | ≤ 50% | 警告 |
| marginal | ≤ 70% | 勉强达标 |
| ok | > 70% | 正常 |

## 算法说明

### 离群点检测

采用基于滑动窗口的中位数绝对偏差（MAD）方法，比固定阈值更稳健：

- 滑动窗口遍历数据
- 计算窗口内中位数和 MAD
- 使用修正 Z 分数判断离群点
- 对非正态分布数据更鲁棒

### 覆盖率计算

遵循以下原则：

1. 传感器健康度基于数据完整性、质量和历史稳定性综合计算
2. 相邻网格的覆盖按距离衰减系数折算
3. 相邻深度层的覆盖按深度衰减系数折算
4. 多个低质量传感器叠加不超过一个健康主传感器的上限
5. 校准失效后的数据按较低可信度参与计算

### 推荐策略

采用贪心算法：

1. 综合评估每个传感器的价值分数
2. 按分数降序排序
3. 根据约束条件（数量、成本、覆盖率）逐步选择
4. 相同分数时按维护成本、历史稳定性、覆盖变量数稳定排序

## 命令速查

| 命令 | 说明 |
|------|------|
| `init` | 初始化示例工作区 |
| `ingest` | 导入观测数据 |
| `audit` | 数据质量审计 |
| `coverage` | 计算覆盖率 |
| `simulate` | 撤收/维护模拟 |
| `recommend` | 传感器推荐 |
| `export` | 导出报告或备份 |

## 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行指定模块测试
python -m pytest tests/test_audit.py -v

# 生成覆盖率报告
python -m pytest tests/ --cov=ocean_sentinel
```

## 项目结构

```
ocean-sentinel/
├── src/ocean_sentinel/
│   ├── __init__.py          # 包初始化
│   ├── cli.py               # CLI入口
│   ├── config.py            # 配置管理
│   ├── database.py          # 数据库模型
│   ├── utils.py             # 工具函数
│   ├── ingest.py            # 数据导入
│   ├── audit.py             # 质量审计
│   ├── coverage.py          # 覆盖率计算
│   ├── simulate.py          # 撤收模拟
│   ├── recommend.py         # 推荐算法
│   ├── export.py            # 报告导出
│   └── sample_data.py       # 示例数据
├── tests/                   # 测试套件
├── pyproject.toml           # 项目配置
└── README.md                # 项目文档
```

## License

MIT
