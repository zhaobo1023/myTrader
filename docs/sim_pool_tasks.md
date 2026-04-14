# 策略模拟池系统 - 任务拆分

**关联设计文档**: `sim_pool_design.md`  
**日期**: 2026-04-14  
**估计总工期**: 约 5 个开发周期

---

## 里程碑划分

| 里程碑 | 内容 | 产出 |
|---|---|---|
| M1 | 数据层 + 核心引擎 | DB 建表、Pool/Position/Nav 核心逻辑可运行 |
| M2 | 策略适配器 + Celery 定时任务 | 选股→买入→每日更新全自动流程跑通 |
| M3 | 报告生成 + REST API | 绩效报告、所有 API 接口可调用 |
| M4 | 前端页面 | 完整 Web UI |
| M5 | 测试 | 单元测试 + 集成测试全部通过 |

---

## M1 - 数据层 + 核心引擎

### T1.1 数据库建表与迁移

**文件**: `strategist/sim_pool/schemas.py`  
**内容**:
- 定义 5 张表的 DDL 常量（sim_pool / sim_position / sim_daily_nav / sim_trade_log / sim_report）
- 提供 `ensure_tables(env='online')` 函数，供 Celery worker 启动时调用
- 所有表字符集使用 `utf8`（兼容线上 MySQL，禁止 emoji）

**验收**: 执行 `ensure_tables()` 后线上 MySQL 成功创建 5 张表

---

### T1.2 配置模块

**文件**: `strategist/sim_pool/config.py`  
**内容**:

```python
@dataclass
class SimPoolConfig:
    # 交易成本
    commission: float = 0.0003      # 手续费率（双边）
    slippage: float = 0.001         # 滑点率
    stamp_tax: float = 0.001        # 印花税（仅卖出）
    # 退出条件
    stop_loss: float = -0.10
    take_profit: float = 0.20
    max_hold_days: int = 60
    # 仓位
    position_sizing: str = 'equal'
    max_positions: int = 10
    initial_cash: float = 1_000_000
    # 基准
    benchmark_code: str = '000300.SH'
    # 数据库环境
    db_env: str = 'online'
```

**验收**: `SimPoolConfig()` 可实例化，参数可被 JSON 序列化后还原

---

### T1.3 PoolManager - 池子生命周期管理

**文件**: `strategist/sim_pool/pool_manager.py`  
**核心类**: `PoolManager`  
**方法**:

```python
def create_pool(strategy_id, name, signal_date, signals_df, config) -> int:
    """写 sim_pool（pending）+ sim_position × N（pending），返回 pool_id"""

def get_pool(pool_id) -> dict:
    """查询单个池子及其持仓列表"""

def list_pools(strategy_id=None, status=None, limit=20) -> list:
    """查询池列表"""

def close_pool(pool_id, reason='manual') -> None:
    """强制关闭池，将 active 持仓标记为 exited（reason=strategy），status=closed"""

def update_pool_metrics(pool_id, metrics: dict) -> None:
    """更新 sim_pool 的绩效摘要字段"""
```

**约束**:
- `create_pool` 接受 `signals_df`，columns 至少包含 `stock_code, stock_name`，可选 `signal_meta`（JSON 字符串）
- 等权分配：`weight = 1 / len(signals_df)`，不超过 `max_positions`
- 所有写操作使用 `execute_update()`，不用 `execute_query()`

**验收**: 调用 `create_pool` 后数据库出现对应记录，`list_pools` 能查回

---

### T1.4 PositionTracker - 持仓价格更新与退出检查

**文件**: `strategist/sim_pool/position_tracker.py`  
**核心类**: `PositionTracker`  
**方法**:

```python
def fill_entry_prices(pool_id, entry_date) -> int:
    """
    填充 T+1 买入价。
    从 trade_stock_daily 查 entry_date 的收盘价。
    计算含滑点买入价 = close * (1 + slippage)。
    计算手续费 = amount * commission。
    计算实际持股数 = floor(cash * weight / entry_price / 100) * 100（手数取整）。
    更新 sim_position（status=active），写 sim_trade_log（action=buy）。
    返回成功填充的持仓数。
    """

def update_prices(pool_id, price_date) -> None:
    """从 trade_stock_daily 查最新收盘价，更新 sim_position.current_price"""

def check_exits(pool_id, price_date, config) -> list:
    """
    检查三个退出条件（按优先级顺序）：
    1. current_return <= stop_loss  → exit_reason=stop_loss
    2. current_return >= take_profit → exit_reason=take_profit
    3. hold_days >= max_hold_days   → exit_reason=max_hold
    触发退出时：
    - 卖出价 = current_price * (1 - slippage)
    - 扣除手续费 + 印花税
    - 更新 sim_position（status=exited，exit_price/date/reason/gross/net_return）
    - 写 sim_trade_log（action=sell）
    返回退出的 position_id 列表。
    """

def get_active_positions(pool_id) -> list:
    """查询 pool 的所有 active 持仓"""

def _calc_current_return(entry_cost, current_price, shares) -> float:
    """(current_price * shares - entry_cost) / entry_cost"""
```

**验收**:
- 止损测试：模拟收盘价下跌 10%，`check_exits` 返回该持仓并写库
- 止盈测试：模拟收盘价上涨 20%，`check_exits` 返回该持仓并写库
- 到期测试：模拟 hold_days=60，`check_exits` 正确触发

---

### T1.5 NavCalculator - 净值计算

**文件**: `strategist/sim_pool/nav_calculator.py`  
**核心类**: `NavCalculator`  
**方法**:

```python
def calculate_daily_nav(pool_id, nav_date) -> dict:
    """
    从 sim_position 汇总持仓市值。
    计算当日 nav = total_value / initial_cash。
    计算 drawdown = (nav - max(历史nav)) / max(历史nav)。
    查询基准指数当日收盘价，计算 benchmark_nav。
    写入 sim_daily_nav。
    返回 nav dict。
    """

def get_nav_series(pool_id) -> list:
    """查询 sim_daily_nav 列表，用于绘图"""

def get_benchmark_nav(pool_id, start_date, end_date) -> list:
    """从 trade_stock_daily 获取基准指数净值序列"""
```

**验收**: 给定 5 天模拟数据，`get_nav_series` 返回正确的 nav 序列，回撤计算准确

---

## M2 - 策略适配器 + Celery 定时任务

### T2.1 策略适配器基类

**文件**: `strategist/sim_pool/strategies/base.py`  
**内容**:

```python
from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategyAdapter(ABC):
    @abstractmethod
    def run(self, date: str, params: dict) -> pd.DataFrame:
        """
        执行选股，返回 signals_df。
        必须包含列: stock_code (str), stock_name (str)
        可选列: signal_type, rps, score, industry 等（存入 signal_meta）
        """

    @abstractmethod
    def strategy_type(self) -> str:
        """返回策略类型字符串"""
```

---

### T2.2 动量策略适配器

**文件**: `strategist/sim_pool/strategies/momentum.py`  
**内容**:

```python
class MomentumAdapter(BaseStrategyAdapter):
    """封装 doctor_tao.SignalScreener"""

    def run(self, date, params) -> pd.DataFrame:
        from strategist.doctor_tao.signal_screener import SignalScreener
        screener = SignalScreener()
        signals = screener.run_screener(date=date)
        # 过滤：可按 signal_type（momentum/reversal）筛选
        # 结构化 signal_meta 字段（rps, ma250, volume_ratio 等）
        return signals[['stock_code', 'stock_name', 'signal_meta']]

    def strategy_type(self): return 'momentum'
```

**验收**: `MomentumAdapter().run(date='2026-04-14', params={})` 返回 DataFrame，不为空

---

### T2.3 行业选股适配器

**文件**: `strategist/sim_pool/strategies/industry.py`  
**内容**:

```python
class IndustryAdapter(BaseStrategyAdapter):
    """封装 universe_scanner.ScoringEngine，支持行业过滤"""

    def run(self, date, params) -> pd.DataFrame:
        # params 可含 industry_names: List[str]（申万一级行业名）
        from strategist.universe_scanner.scoring_engine import ScoringEngine
        engine = ScoringEngine()
        results = engine.run(date=date)
        # 过滤 tier='high_priority'，按行业名过滤（若指定）
        # 按 total_score 排序取 top N
        return results[['stock_code', 'stock_name', 'signal_meta']]

    def strategy_type(self): return 'industry'
```

---

### T2.4 微盘股适配器

**文件**: `strategist/sim_pool/strategies/micro_cap.py`  
**内容**:

```python
class MicroCapAdapter(BaseStrategyAdapter):
    """
    微盘股选股：
    - 流通市值 < 50亿
    - 60日均成交额 >= 1000万（保证流动性）
    - 价格在 MA20 之上（短期趋势）
    - 排除 ST 股
    数据来源: trade_stock_daily_basic + trade_stock_daily
    """

    def run(self, date, params) -> pd.DataFrame:
        # 从 trade_stock_daily_basic 取市值数据
        # 过滤市值、流动性、趋势条件
        # 返回 DataFrame
        pass

    def strategy_type(self): return 'micro_cap'
```

---

### T2.5 Celery 任务

**文件**: `api/tasks/sim_pool_tasks.py`  
**任务列表**:

```python
@celery_app.task(name='tasks.create_sim_pool')
def create_sim_pool_task(strategy_id, strategy_type, signal_date, config_dict, user_id):
    """
    1. 实例化对应 StrategyAdapter
    2. 执行选股 adapter.run()
    3. 调用 PoolManager.create_pool()
    4. 返回 pool_id
    """

@celery_app.task(name='tasks.fill_entry_prices')
def fill_entry_prices_task():
    """
    每日 09:35 运行。
    查询所有 status=pending 的 sim_pool。
    确认今日为交易日。
    对每个 pending 池调用 PositionTracker.fill_entry_prices()。
    """

@celery_app.task(name='tasks.daily_sim_pool_update')
def daily_sim_pool_update_task():
    """
    每日 16:30 运行。
    查询所有 status=active 的 sim_pool。
    对每个池：
      1. PositionTracker.update_prices()
      2. PositionTracker.check_exits()
      3. NavCalculator.calculate_daily_nav()
      4. ReportGenerator.generate_daily_report()
      5. 若周五: generate_weekly_report()
      6. 若所有持仓 exited: PoolManager.close_pool() + generate_final_report()
    """
```

**Celery Beat 配置**（加入 `api/tasks/celery_app.py`）:

```python
beat_schedule = {
    'sim-pool-fill-entry': {
        'task': 'tasks.fill_entry_prices',
        'schedule': crontab(hour=9, minute=35),
    },
    'sim-pool-daily-update': {
        'task': 'tasks.daily_sim_pool_update',
        'schedule': crontab(hour=16, minute=30),
    },
}
```

**验收**: 手动触发 `fill_entry_prices_task.delay()` 后，pending 池变为 active，持仓有买入价

---

### T2.6 停牌/退市处理

**文件**: `strategist/sim_pool/position_tracker.py`（补充方法）  
**内容**:

```python
def handle_suspended(pool_id, price_date) -> list:
    """
    对 active 持仓，若 trade_stock_daily 中该日无数据（停牌），
    累计停牌天数。若连续停牌 > 5 个交易日，
    以最后可交易收盘价强制平仓，exit_reason='strategy'。
    """
```

---

## M3 - 报告生成 + REST API

### T3.1 ReportGenerator - 绩效报告

**文件**: `strategist/sim_pool/report_generator.py`  
**核心类**: `ReportGenerator`  
**方法**:

```python
def generate_daily_report(pool_id, report_date) -> dict:
    """
    从 sim_daily_nav + sim_position 构建 BacktestResult 兼容的数据结构。
    调用 MetricsCalculator.calculate() 计算所有指标。
    写入 sim_report（type=daily）。
    返回 metrics dict。
    """

def generate_weekly_report(pool_id, week_end_date) -> dict:
    """
    统计本周（周一到周五）的绩效指标。
    写入 sim_report（type=weekly）。
    """

def generate_final_report(pool_id) -> dict:
    """
    池子关闭后生成终报，包含：
    - 完整绩效指标
    - 每只股的贡献度（net_return 排名）
    - 退出原因分布（止盈N只 / 止损N只 / 到期N只）
    写入 sim_report（type=final）。
    """

def get_report(pool_id, report_date, report_type) -> dict:
    """从 sim_report 查询单份报告"""

def list_reports(pool_id, report_type=None) -> list:
    """查询报告列表"""
```

**复用**: 直接调用 `strategist.backtest.metrics.MetricsCalculator`

**验收**: `generate_final_report` 返回的 metrics 包含 annual_return/max_drawdown/sharpe_ratio/win_rate 且数值合理

---

### T3.2 SimPoolService - 业务逻辑层

**文件**: `api/services/sim_pool_service.py`  
**内容**: 封装所有数据库查询，供 Router 调用。隔离 Router 与底层模块。

```python
def create_pool_async(strategy_id, strategy_type, params, user_id) -> str:
    """提交 Celery 任务，返回 task_id"""

def get_pool_detail(pool_id) -> dict:
    """查询池详情 + 持仓列表"""

def get_nav_data(pool_id) -> list:
    """查询净值曲线数据"""

def get_positions(pool_id, status=None) -> list:
    """查询持仓（支持 active/exited 过滤）"""

def get_trade_log(pool_id) -> list:
    """查询交易日志"""

def list_reports(pool_id, report_type=None) -> list:
    """查询报告列表"""

def get_report_detail(pool_id, report_date, report_type) -> dict:
    """查询报告详情"""

def close_pool(pool_id) -> None:
    """手动关闭（强制平仓）"""
```

---

### T3.3 REST API Router

**文件**: `api/routers/sim_pool.py`  
**实现所有 Section 6 中定义的 9 个接口**:

- `POST /api/sim-pool/pools` — 接收参数，调用 `create_pool_async`，返回 `{task_id, message}`
- `GET /api/sim-pool/pools` — 列表，支持 `strategy_id / status / limit` 参数
- `GET /api/sim-pool/pools/{id}` — 详情
- `GET /api/sim-pool/pools/{id}/nav` — 净值序列（`{date, nav, benchmark_nav, drawdown}`）
- `GET /api/sim-pool/pools/{id}/positions` — 持仓列表（`?status=active|exited`）
- `GET /api/sim-pool/pools/{id}/reports` — 报告列表
- `GET /api/sim-pool/pools/{id}/reports/{date}` — 报告详情（`?type=daily|weekly|final`）
- `GET /api/sim-pool/pools/{id}/trades` — 交易日志
- `POST /api/sim-pool/pools/{id}/close` — 手动关闭

**注册到 `api/main.py`**: `app.include_router(sim_pool_router)`

**验收**: `curl POST /api/sim-pool/pools` 返回 task_id；`GET /pools` 返回列表

---

### T3.4 注册 Celery 任务

**文件**: `api/tasks/__init__.py`  
**内容**: 添加 `from api.tasks import sim_pool_tasks`

---

## M4 - 前端页面

### T4.1 池子列表页

**文件**: `web/src/app/sim-pool/page.tsx`  
**内容**:
- 调用 `GET /api/sim-pool/pools`
- 卡片网格：策略名 / 创建时间 / 状态标签 / 累计收益率 / 最大回撤
- 顶部过滤栏：按策略类型 / 状态过滤
- "新建模拟池"按钮 → 打开 `CreatePoolModal`

---

### T4.2 创建模拟池弹窗

**文件**: `web/src/app/sim-pool/components/CreatePoolModal.tsx`  
**内容**:
- 下拉选择策略类型（momentum/industry/micro_cap/custom）
- 数字输入：止损% / 止盈% / 最大持仓天数 / 初始资金
- Custom 类型显示文本框（粘贴股票代码，每行一个）
- 提交后 POST `/api/sim-pool/pools`，展示"选股中…"状态，完成后刷新列表

---

### T4.3 净值曲线组件

**文件**: `web/src/app/sim-pool/components/NavChart.tsx`  
**内容**:
- 折线图：策略净值 vs 基准净值（双线）
- X 轴：日期，Y 轴：净值
- 鼠标悬浮展示：日期 / 净值 / 基准净值 / 超额收益
- 标注买卖点（买入绿三角 / 止盈蓝圆 / 止损红叉 / 到期灰方）
- 使用 CSS 简单实现（不依赖 ECharts，保持与现有样式一致）

---

### T4.4 持仓明细组件

**文件**: `web/src/app/sim-pool/components/PositionTable.tsx`  
**内容**:
- 表格列：股票代码 / 名称 / 买入日 / 买入价 / 当前价（或退出价）/ 收益率 / 持仓天数 / 状态/退出原因
- 状态标签颜色：active=蓝 / 止盈=绿 / 止损=红 / 到期=灰
- 支持按状态过滤（Tab 切换 active/exited）

---

### T4.5 绩效指标卡片组件

**文件**: `web/src/app/sim-pool/components/MetricsCard.tsx`  
**内容**:
- 8 个核心指标卡片网格：总收益 / 年化收益 / 最大回撤 / 夏普 / 胜率 / 盈亏比 / 平均持仓天数 / 超额收益
- 数值颜色：正收益绿 / 负收益红

---

### T4.6 池子详情页

**文件**: `web/src/app/sim-pool/[id]/page.tsx`  
**内容**:
- Tab 1 概览：MetricsCard + NavChart
- Tab 2 持仓：PositionTable
- Tab 3 报告：报告列表（日期 / 类型），点击展开 metrics JSON 格式化展示
- Tab 4 交易记录：trade_log 表格（日期/动作/价格/数量/成本）
- 顶部展示：池子名称 / 策略类型 / 状态 / 创建时间

---

### T4.7 导航菜单添加入口

**文件**: `web/src/components/layout/AppShell.tsx`  
**内容**: 在侧边栏添加"模拟池"导航项（路径 `/sim-pool`）

---

## M5 - 测试

### T5.1 单元测试：PoolManager

**文件**: `tests/unit/sim_pool/test_pool_manager.py`  
**测试用例**:

```python
def test_create_pool_writes_db():
    """create_pool 成功写入 sim_pool 和 sim_position"""

def test_create_pool_equal_weight():
    """5只股票，每只 weight=0.2"""

def test_create_pool_max_positions():
    """传入15只股票，max_positions=10，实际只创建10条 sim_position"""

def test_list_pools_filter_by_status():
    """list_pools(status='active') 只返回 active 池"""

def test_close_pool_sets_status():
    """close_pool 后 sim_pool.status='closed'，所有 active 持仓 status='exited'"""
```

---

### T5.2 单元测试：PositionTracker

**文件**: `tests/unit/sim_pool/test_position_tracker.py`  
**测试用例**:

```python
def test_fill_entry_prices_calculates_cost():
    """买入价 = close * (1 + slippage)，手续费正确，持股数为100的整数倍"""

def test_check_exits_stop_loss():
    """current_return = -11%（< -10% 止损线），触发退出，exit_reason='stop_loss'"""

def test_check_exits_take_profit():
    """current_return = +22%（> +20% 止盈线），触发退出，exit_reason='take_profit'"""

def test_check_exits_max_hold():
    """hold_days = 61（> 60天），触发退出，exit_reason='max_hold'"""

def test_check_exits_no_trigger():
    """current_return = -5%，hold_days = 30，无退出"""

def test_sell_cost_includes_stamp_tax():
    """卖出时手续费 + 印花税都被计入，net_return < gross_return"""

def test_suspended_stock_force_exit():
    """停牌超过5个交易日，触发强制平仓，exit_reason='strategy'"""
```

---

### T5.3 单元测试：NavCalculator

**文件**: `tests/unit/sim_pool/test_nav_calculator.py`  
**测试用例**:

```python
def test_nav_day1_equals_one():
    """买入当日 nav=1.0"""

def test_nav_increases_with_price():
    """持仓股价上涨10%，nav 约=1.10（扣去手续费）"""

def test_drawdown_calculation():
    """nav 从1.0涨到1.2再跌到1.08，回撤 = (1.08-1.2)/1.2 = -10%"""

def test_benchmark_nav_fetched():
    """benchmark_nav 从 trade_stock_daily 正确读取"""
```

---

### T5.4 单元测试：ReportGenerator

**文件**: `tests/unit/sim_pool/test_report_generator.py`  
**测试用例**:

```python
def test_daily_report_has_required_fields():
    """日报 metrics 包含 total_return/annual_return/max_drawdown/sharpe_ratio/win_rate"""

def test_final_report_exit_breakdown():
    """终报包含退出原因分布：stop_loss/take_profit/max_hold 各几只"""

def test_final_report_position_contribution():
    """终报包含各股贡献度，按 net_return 排序"""

def test_weekly_report_covers_5_days():
    """周报统计区间为本周一到周五"""
```

---

### T5.5 单元测试：策略适配器

**文件**: `tests/unit/sim_pool/test_strategy_adapters.py`  
**测试用例**:

```python
def test_momentum_adapter_returns_dataframe():
    """MomentumAdapter.run() 返回 DataFrame，含 stock_code/stock_name 列"""

def test_industry_adapter_filters_by_industry():
    """传入 params={'industry_names': ['银行']}, 返回结果全为银行股"""

def test_micro_cap_adapter_market_cap_filter():
    """返回的股票流通市值均 < 50亿"""

def test_adapter_signal_meta_is_serializable():
    """signal_meta 列可被 json.dumps 序列化"""
```

---

### T5.6 集成测试：完整生命周期

**文件**: `tests/integration/sim_pool/test_full_lifecycle.py`  
**前置条件**: 线上数据库有 trade_stock_daily 数据（使用测试专用 schema 或 mock）

```python
def test_full_lifecycle_momentum():
    """
    端到端测试动量策略模拟池：
    1. create_pool（动量策略，选取5只股票）
    2. fill_entry_prices（模拟T+1，给定mock价格）
    3. update_prices × 3天
    4. check_exits（模拟某只股触发止损）
    5. calculate_daily_nav × 3天
    6. generate_daily_report × 3天
    7. 所有持仓强制平仓 close_pool
    8. generate_final_report
    验证：
    - sim_pool.status = 'closed'
    - sim_daily_nav 有3条记录
    - sim_report 有3条daily + 1条final
    - sim_trade_log 有买入5条 + 卖出5条
    - final metrics 中 total_trades=5，胜率合理
    """

def test_stop_loss_triggers_correctly():
    """
    构造持仓价格下跌 > 10%，验证：
    - check_exits 返回该股
    - sim_position.exit_reason = 'stop_loss'
    - sim_trade_log 有对应 sell 记录
    - net_return <= stop_loss（扣费后）
    """

def test_take_profit_triggers_correctly():
    """与止损测试对称，价格上涨 > 20%"""

def test_max_hold_triggers_on_day_61():
    """hold_days=61，即使收益为正也触发退出"""
```

---

### T5.7 集成测试：API 接口

**文件**: `tests/integration/sim_pool/test_api_endpoints.py`  
**使用 `httpx.AsyncClient` 测试**:

```python
async def test_create_pool_returns_task_id():
    """POST /api/sim-pool/pools 返回 task_id"""

async def test_list_pools_empty():
    """GET /api/sim-pool/pools 初始返回空列表"""

async def test_get_pool_detail_after_create():
    """创建后 GET /api/sim-pool/pools/{id} 返回正确详情"""

async def test_get_nav_returns_series():
    """GET /api/sim-pool/pools/{id}/nav 返回列表，每条有 date/nav/benchmark_nav"""

async def test_get_positions_filter():
    """GET /api/sim-pool/pools/{id}/positions?status=active 只返回 active 持仓"""

async def test_close_pool_changes_status():
    """POST /api/sim-pool/pools/{id}/close 后 GET 池状态为 closed"""

async def test_reports_available_after_update():
    """手动触发 daily_sim_pool_update_task 后，报告接口返回数据"""
```

---

## 开发顺序建议

```
T1.1 建表 → T1.2 配置 → T1.3 PoolManager → T1.4 PositionTracker → T1.5 NavCalculator
       ↓
T5.1~T5.3 单元测试（与 M1 并行写）
       ↓
T2.1 基类 → T2.2~T2.4 适配器 → T2.5 Celery 任务 → T2.6 停牌处理
       ↓
T5.5 适配器单元测试
       ↓
T3.1 ReportGenerator → T3.2 Service → T3.3 Router → T3.4 注册任务
       ↓
T5.4 报告单元测试 → T5.6 生命周期集成测试 → T5.7 API 集成测试
       ↓
T4.1~T4.7 前端页面
```

---

## 依赖关系图

```
T1.2 ──► T1.3 ──► T2.5
     └──► T1.4 ──► T2.5
     └──► T1.5 ──► T2.5
T1.1 ──► T1.3, T1.4, T1.5

T2.1 ──► T2.2, T2.3, T2.4
T2.2~T2.4 ──► T2.5

T1.3, T1.4, T1.5 ──► T3.1 ──► T3.2 ──► T3.3

T3.3 ──► T4.1~T4.6
```

---

## 注意事项

1. **禁止 emoji**：所有代码、注释、日志、数据库内容不使用 emoji（MySQL utf8 不支持4字节字符）
2. **写操作必须用 `execute_update()`**：不能用 `execute_query()` 做 INSERT/UPDATE/DELETE
3. **API_BASE 回退**：前端 `const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || ''`
4. **Celery 任务注册**：新任务文件必须在 `api/tasks/__init__.py` 中 import
5. **等权买入取整**：持股数必须是100的整数倍，余额作为现金保留
6. **停牌判断依据**：`trade_stock_daily` 该日无记录视为停牌
