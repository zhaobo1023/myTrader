# 策略模拟池系统设计文档

**版本**: v1.0  
**日期**: 2026-04-14  
**状态**: 待开发

---

## 1. 背景与目标

### 1.1 问题

现有回测框架（`strategist/backtest/`）是**历史回测**，无法跟踪策略信号在真实时间流中的表现。动量策略（`doctor_tao`）、全市场扫描（`universe_scanner`）等每次运行都会产生选股信号，但信号产生后没有持续的持仓跟踪和绩效统计机制。

### 1.2 目标

构建**策略模拟池系统（SimPool）**，实现：

1. 将策略每次选股结果存入独立的"模拟池"
2. T+1 自动买入，每日盘后自动检查止盈/止损/到期
3. 严格纪律：**选入后不允许人工干预**，只有预设条件触发退出
4. 每日/每周自动生成绩效报告
5. 复用现有 `BacktestEngine.MetricsCalculator` 计算所有绩效指标

### 1.3 支持的策略类型

| 策略类型 | 选股来源 | 特征 |
|---|---|---|
| `momentum` | `doctor_tao.SignalScreener` | RPS≥95，动量/反转信号 |
| `industry` | `universe_scanner.ScoringEngine`（行业过滤） | 行业轮动选股 |
| `micro_cap` | `universe_scanner` + 市值过滤（<50亿） | 微盘股策略 |
| `custom` | 用户自定义股票列表 | 手动构建组合 |

---

## 2. 核心概念

```
策略 (Strategy)
  └─ 模拟池 (SimPool)      ← 每次选股 = 一个独立池子，永久存档
       ├─ 持仓 (SimPosition)  ← 每只股票的完整生命周期记录
       ├─ 日净值 (SimDailyNav) ← 每日快照，用于净值曲线
       ├─ 交易日志 (SimTradeLog) ← 每笔买卖的审计记录
       └─ 绩效报告 (SimReport) ← 日报/周报/终报
```

**关键约束**：
- 同一策略的每次选股进入独立的池子，互不干扰
- 买入：T+1 收盘价，等权平均买入
- 退出：止盈 / 止损 / 最大持仓期 三条件之一触发，每日盘后自动执行
- **不允许人工干预**（无手动买卖接口）
- 成本：手续费 0.03% + 滑点 0.1% + 卖出印花税 0.1%

---

## 3. 数据库表设计

使用现有 `strategies` 表，新增 5 张表。字符集统一 `utf8`（兼容线上 MySQL）。

### 3.1 sim_pool（模拟池）

```sql
CREATE TABLE IF NOT EXISTS sim_pool (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    strategy_id   INT NOT NULL COMMENT '关联 strategies.id',
    name          VARCHAR(100) NOT NULL COMMENT '池子名称，如 momentum_20260414',
    signal_date   DATE NOT NULL COMMENT '选股信号日期',
    entry_date    DATE COMMENT 'T+1 实际买入日',
    initial_cash  DOUBLE NOT NULL DEFAULT 1000000 COMMENT '初始资金（元）',
    status        VARCHAR(20) NOT NULL DEFAULT 'pending'
                  COMMENT 'pending|active|closed',
    stock_count   INT COMMENT '持仓股票数量',
    total_return  DOUBLE COMMENT '当前累计收益率',
    benchmark_code VARCHAR(20) DEFAULT '000300.SH' COMMENT '基准指数',
    benchmark_return DOUBLE COMMENT '同期基准收益率',
    max_drawdown  DOUBLE COMMENT '最大回撤',
    sharpe_ratio  DOUBLE COMMENT '夏普比率',
    win_rate      DOUBLE COMMENT '胜率',
    params        TEXT COMMENT 'JSON: stop_loss/take_profit/max_hold_days/commission/slippage',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at     DATETIME,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_strategy (strategy_id),
    INDEX idx_status (status),
    INDEX idx_signal_date (signal_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='策略模拟池';
```

### 3.2 sim_position（持仓明细）

```sql
CREATE TABLE IF NOT EXISTS sim_position (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    pool_id       INT NOT NULL COMMENT '关联 sim_pool.id',
    stock_code    VARCHAR(20) NOT NULL,
    stock_name    VARCHAR(50),
    weight        DOUBLE NOT NULL COMMENT '仓位权重，等权=1/N',
    shares        INT COMMENT '持股数量',
    entry_price   DOUBLE COMMENT 'T+1 实际买入价（收盘价）',
    entry_date    DATE,
    entry_cost    DOUBLE COMMENT '含手续费+滑点的实际成本',
    current_price DOUBLE COMMENT '最新收盘价',
    exit_price    DOUBLE COMMENT '退出成交价',
    exit_date     DATE,
    exit_reason   VARCHAR(20) COMMENT 'stop_loss|take_profit|max_hold|strategy',
    gross_return  DOUBLE COMMENT '毛收益率',
    net_return    DOUBLE COMMENT '扣费后收益率',
    status        VARCHAR(20) NOT NULL DEFAULT 'pending'
                  COMMENT 'pending|active|exited',
    signal_meta   TEXT COMMENT 'JSON: 选股时的信号数据（rps/score等）',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_pool (pool_id),
    INDEX idx_stock (stock_code),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='模拟池持仓明细';
```

### 3.3 sim_daily_nav（每日净值）

```sql
CREATE TABLE IF NOT EXISTS sim_daily_nav (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    pool_id          INT NOT NULL,
    nav_date         DATE NOT NULL,
    portfolio_value  DOUBLE COMMENT '持仓市值（元）',
    cash             DOUBLE COMMENT '剩余现金',
    total_value      DOUBLE COMMENT '总资产',
    nav              DOUBLE COMMENT '单位净值（初始=1.0）',
    daily_return     DOUBLE COMMENT '当日收益率',
    benchmark_nav    DOUBLE COMMENT '基准单位净值',
    drawdown         DOUBLE COMMENT '当日回撤（距历史高点）',
    active_positions INT COMMENT '当日持仓数',
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_pool_date (pool_id, nav_date),
    INDEX idx_pool (pool_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='模拟池每日净值快照';
```

### 3.4 sim_trade_log（交易日志）

```sql
CREATE TABLE IF NOT EXISTS sim_trade_log (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    pool_id     INT NOT NULL,
    position_id INT NOT NULL,
    stock_code  VARCHAR(20) NOT NULL,
    trade_date  DATE NOT NULL,
    action      VARCHAR(10) NOT NULL COMMENT 'buy|sell',
    price       DOUBLE NOT NULL COMMENT '成交价（含滑点）',
    shares      INT NOT NULL,
    amount      DOUBLE COMMENT '成交金额',
    commission  DOUBLE COMMENT '手续费',
    slippage    DOUBLE COMMENT '滑点成本',
    stamp_tax   DOUBLE COMMENT '印花税（卖出时）',
    net_amount  DOUBLE COMMENT '实际资金变动',
    trigger     VARCHAR(20) COMMENT 'entry|stop_loss|take_profit|max_hold|strategy',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_pool (pool_id),
    INDEX idx_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='交易日志（审计）';
```

### 3.5 sim_report（绩效报告）

```sql
CREATE TABLE IF NOT EXISTS sim_report (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    pool_id     INT NOT NULL,
    report_date DATE NOT NULL,
    report_type VARCHAR(20) NOT NULL COMMENT 'daily|weekly|final',
    metrics     TEXT COMMENT 'JSON: 完整绩效指标（复用 BacktestResult 结构）',
    narrative   TEXT COMMENT 'LLM 生成的自然语言点评（可选）',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_pool_date_type (pool_id, report_date, report_type),
    INDEX idx_pool (pool_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='绩效报告快照';
```

---

## 4. 模块结构

```
strategist/sim_pool/
├── __init__.py
├── config.py                  # SimPoolConfig（交易成本/止盈止损参数）
├── schemas.py                 # DDL 常量 + Pydantic 数据模型
├── pool_manager.py            # 创建池、查询池、关闭池
├── position_tracker.py        # 每日盘后：更新持仓价格、检查退出条件
├── nav_calculator.py          # 计算每日净值、回撤、基准对比
├── report_generator.py        # 复用 MetricsCalculator，生成日报/周报/终报
├── strategies/
│   ├── __init__.py
│   ├── base.py                # 抽象基类 BaseStrategyAdapter
│   ├── momentum.py            # 接 doctor_tao.SignalScreener
│   ├── industry.py            # 接 universe_scanner（行业过滤）
│   └── micro_cap.py           # 微盘股过滤器
└── scheduler.py               # 定时任务注册（Celery beat）

api/
├── routers/sim_pool.py        # REST API 路由
├── services/sim_pool_service.py  # 业务逻辑层
└── tasks/sim_pool_tasks.py    # Celery 异步任务

web/src/app/sim-pool/
├── page.tsx                   # 池子列表 + 创建入口
├── [id]/page.tsx              # 单池详情页
└── components/
    ├── NavChart.tsx           # 净值曲线（对比基准）
    ├── PositionTable.tsx      # 持仓明细（含买卖标注）
    ├── MetricsCard.tsx        # 绩效指标卡片
    └── CreatePoolModal.tsx    # 创建模拟池弹窗

tests/
├── unit/sim_pool/
│   ├── test_pool_manager.py
│   ├── test_position_tracker.py
│   ├── test_nav_calculator.py
│   └── test_report_generator.py
└── integration/sim_pool/
    ├── test_full_lifecycle.py  # 创建→买入→持仓→退出→报告全流程
    └── test_api_endpoints.py
```

---

## 5. 核心流程

### 5.1 创建模拟池流程

```
用户操作：选择策略 → 设置参数 → 点"运行选股并创建池"
    │
    ▼ POST /api/sim-pool/create
    ▼ Celery Task: create_sim_pool_task
    │
    ├─ 1. 执行选股（调用对应 StrategyAdapter）
    │      → 返回 signals_df [stock_code, stock_name, signal_meta]
    │
    ├─ 2. 写入 sim_pool（status=pending）
    │
    ├─ 3. 写入 sim_position × N 条（status=pending, entry_price=null）
    │
    └─ 4. 返回 pool_id → 前端展示"等待T+1买入"状态
```

### 5.2 T+1 买入流程（每日 9:35 触发）

```
Celery Beat → fill_entry_prices_task
    │
    ├─ 查询所有 status=pending 的 sim_pool
    │
    ├─ 确认今日为交易日（查 trade_stock_daily）
    │
    ├─ 对每个 pending 池：
    │   ├─ 查询各持仓股 T+1 收盘价
    │   ├─ 计算等权仓位、含滑点买入价、实际持股数
    │   ├─ 计算手续费，更新 sim_position（status=active）
    │   ├─ 写入 sim_trade_log（action=buy）
    │   └─ 更新 sim_pool（status=active, entry_date=today）
    │
    └─ 写入当日 sim_daily_nav（初始 nav=1.0）
```

### 5.3 每日盘后流程（每日 16:30 触发）

```
Celery Beat → daily_update_task
    │
    ├─ 1. 更新持仓价格
    │      查询 active 持仓的最新收盘价 → 更新 sim_position.current_price
    │
    ├─ 2. 检查退出条件（按优先级）
    │      止损: current_return <= stop_loss  → 触发卖出
    │      止盈: current_return >= take_profit → 触发卖出
    │      到期: hold_days >= max_hold_days   → 触发卖出
    │      ※ 以收盘价 × (1 - slippage) 作为卖出成交价
    │      ※ 扣除印花税 + 手续费
    │      ※ 写 sim_trade_log（action=sell）
    │      ※ 更新 sim_position（status=exited）
    │
    ├─ 3. 计算净值
    │      portfolio_value = sum(position.shares × close_price)
    │      nav = total_value / initial_cash
    │      drawdown = (nav - max_nav) / max_nav
    │      写入 sim_daily_nav
    │
    ├─ 4. 生成日报
    │      调用 MetricsCalculator → 写入 sim_report（type=daily）
    │
    ├─ 5. 如果今天是周五 → 生成周报（type=weekly）
    │
    └─ 6. 如果所有持仓 exited → 关闭池
           pool.status = closed，生成终报（type=final）
```

---

## 6. API 接口设计

| Method | Path | 说明 |
|---|---|---|
| POST | `/api/sim-pool/pools` | 创建模拟池（触发选股） |
| GET | `/api/sim-pool/pools` | 列出所有池（支持按策略/状态过滤） |
| GET | `/api/sim-pool/pools/{id}` | 池详情（含持仓列表） |
| GET | `/api/sim-pool/pools/{id}/nav` | 净值曲线数据 |
| GET | `/api/sim-pool/pools/{id}/positions` | 持仓明细（含退出记录） |
| GET | `/api/sim-pool/pools/{id}/reports` | 报告列表 |
| GET | `/api/sim-pool/pools/{id}/reports/{date}` | 指定日期报告详情 |
| GET | `/api/sim-pool/pools/{id}/trades` | 交易日志 |
| POST | `/api/sim-pool/pools/{id}/close` | 手动关闭池（强制全部平仓，记录原因） |

---

## 7. 绩效指标（复用 MetricsCalculator）

| 指标 | 字段 | 说明 |
|---|---|---|
| 累计收益率 | `total_return` | |
| 年化收益率 | `annual_return` | 252交易日标准化 |
| 基准收益率 | `benchmark_return` | 同期沪深300 |
| 超额收益 | `excess_return` | |
| 最大回撤 | `max_drawdown` | |
| 夏普比率 | `sharpe_ratio` | 无风险利率3% |
| 索提诺比率 | `sortino_ratio` | |
| 卡玛比率 | `calmar_ratio` | 年化/最大回撤 |
| 胜率 | `win_rate` | |
| 盈亏比 | `profit_loss_ratio` | |
| 平均持仓天数 | `avg_hold_days` | |
| 总交易次数 | `total_trades` | |

---

## 8. 交易成本参数（默认值）

```python
commission: float = 0.0003     # 手续费 0.03%（双边）
slippage: float = 0.001        # 滑点 0.1%（买入加、卖出减）
stamp_tax: float = 0.001       # 印花税 0.1%（仅卖出）
stop_loss: float = -0.10       # 止损 -10%
take_profit: float = 0.20      # 止盈 +20%
max_hold_days: int = 60        # 最大持仓 60 交易日
position_sizing: str = 'equal' # 等权分配
max_positions: int = 10        # 最大持仓股数
initial_cash: float = 1000000  # 初始资金 100万
```

---

## 9. 与现有代码的复用关系

| 新系统组件 | 复用自 | 方式 |
|---|---|---|
| 买卖成本计算 | `backtest/portfolio.py` Portfolio.execute_buy/sell | 直接调用 |
| 绩效指标 | `backtest/metrics.py` MetricsCalculator | 直接调用 |
| 动量选股 | `doctor_tao/signal_screener.py` SignalScreener | 适配器封装 |
| 行业/全市场选股 | `universe_scanner/scoring_engine.py` ScoringEngine | 适配器封装 |
| 技术指标 | `doctor_tao/indicators.py` IndicatorCalculator | 直接调用 |
| Celery 任务框架 | `api/tasks/` | 新增任务文件 |
| 数据库连接 | `config/db.py` execute_update/execute_query | 直接调用 |

---

## 10. 前端页面规划

### 10.1 池子列表页（`/sim-pool`）

- 卡片列表：展示各池的策略名、创建时间、当前状态、累计收益、最大回撤
- 顶部筛选：按策略类型 / 状态（active/closed）过滤
- 右上角按钮："新建模拟池"（弹出创建弹窗）

### 10.2 创建弹窗

- 选择策略类型（momentum/industry/micro_cap/custom）
- 配置参数：止盈止损、最大持仓天数、初始资金、基准指数
- Custom 类型：手动粘贴股票代码列表
- 确认后异步触发选股，展示进度

### 10.3 池子详情页（`/sim-pool/[id]`）

**Tab 1: 概览**
- 绩效指标卡片（总收益/年化/回撤/夏普）
- 净值曲线（与基准对比，标注每笔买卖点）

**Tab 2: 持仓明细**
- 表格：股票 / 买入日期 / 买入价 / 当前价 / 收益率 / 状态
- 已退出持仓显示退出原因（止盈/止损/到期）标签

**Tab 3: 报告**
- 日报/周报列表，点击展开完整报告
- 关键指标趋势图（收益率随时间变化）

**Tab 4: 交易记录**
- 完整的买卖日志，每行含成本明细

---

## 11. 约束与边界

1. **不允许人工干预持仓**：无手动买卖 API，只有系统根据条件自动执行
2. **池子一旦创建不可修改参数**：止盈止损等参数在创建时锁定，存入 `sim_pool.params`
3. **退市/停牌处理**：若股票停牌超过 5 个交易日，以最后可交易价格强制平仓，触发原因标记为 `strategy`
4. **T+1 限制**：买入以信号次日收盘价成交，不使用当日价格
5. **数据依赖**：依赖 `trade_stock_daily` 表有每日收盘价数据，若数据缺失跳过当日更新并记录警告

---

## 12. 未来扩展方向（暂不实现）

- 策略参数优化（网格搜索最优止盈止损）
- 多池组合绩效聚合视图
- 真实账户对接（QMT 执行层）
- 微信/飞书推送日报
- 因子归因分析（收益来源拆解）
