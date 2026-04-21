# 统一任务调度器

通过 YAML 定义 DAG 任务依赖关系，替代散落在各处的定时脚本。

## 模块结构

```
scheduler/
├── cli.py                 # CLI 入口 (list/run/status/summary)
├── loader.py              # YAML 任务加载与环境合并
├── dag.py                 # DAG 依赖解析与拓扑排序
├── executor.py            # 任务执行器（重试/超时/dry_run）
├── state.py               # task_runs 表状态持久化
├── readiness.py           # 数据就绪探测（轮询 DB）
├── alert.py               # Webhook 报警通知
├── adapters.py            # 模块适配器（无简单入口的模块包装）
└── tests/                 # 单元测试与集成测试

tasks/                     # YAML 任务定义文件
├── _base.yaml             # 全局默认值与环境配置
├── 02_macro.yaml          # 宏观数据拉取与因子计算
├── 03_factors_basic.yaml  # 因子计算（含数据就绪 gate）
├── 04_indicators.yaml     # 技术指标（RPS/SVD/LogBias）
├── 05_strategy.yaml       # 策略相关（IC 监控/模拟交易）
└── 06_maintenance.yaml    # 维护任务（手动触发）
```

## 常用命令

```bash
# 列出所有任务
python -m scheduler list

# 按标签过滤
python -m scheduler list --tag daily

# 全量 dry-run（验证配置不实际执行）
python -m scheduler run all --dry-run

# 单任务 dry-run
python -m scheduler run fetch_macro_data --dry-run

# 运行所有 daily 任务
python -m scheduler run all --tag daily

# 查看任务最近运行状态
python -m scheduler status fetch_macro_data

# 查看今日执行摘要
python -m scheduler summary
```

## 数据拉取管理服务

```python
from data_analyst.fetchers.data_fetch_manager import DataFetchManager, DataFetchResult

manager = DataFetchManager()
# 从 AKShare 拉取日线数据
result = manager.fetch_daily_data(DataFetcherType.AKSHARE)
```

## 数据监控服务

每天 18:00 自动检查数据完整性：

```python
from data_analyst.services.data_monitor import DataMonitor

monitor = DataMonitor()
result = monitor.check_daily_data()
if result['is_ok']:
    print("数据正常，触发因子计算...")
else:
    print("数据异常，发送报警...")
```

## 报警通知

支持飞书 Webhook 推送，配置 `.env`:

```bash
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

[返回主文档](../../CLAUDE.md)
