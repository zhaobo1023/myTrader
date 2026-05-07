# 微盘股策略回测增强 -- 技术方案与任务拆解

> 基于外部诊断报告，对 `strategist/microcap/` 回测引擎进行 7 项增强。
> 目标：提升回测可信度，使结论可作为实盘决策依据。

---

## 一、问题总览

| # | 问题 | 优先级 | 影响文件 | 风险等级 |
|---|------|--------|----------|----------|
| 1 | 滑点模型过于乐观 | P0 | config.py, run_grid.py | 策略收益可能高估 50%+ |
| 2 | 幸存者偏差（退市股缺失） | P2 | 数据层, universe.py | 收益高估（退市归零未计入） |
| 3 | 涨跌停无法成交未处理 | P0 | backtest.py | 最大回撤被低估 |
| 4 | PEG 因子前视偏差 | P0 | factors.py | PEG 优势可能被夸大 |
| 5 | 持有期参数过拟合 | P1 | run_grid.py（仅参数） | h5 可能是尖峰而非高原 |
| 6 | 缺少成交额过滤 | P1 | universe.py | 选入不可交易标的 |
| 7 | 缺少基准对比 | P2 | backtest.py, 可视化 | 无法区分 alpha/beta |

---

## 二、详细技术方案与任务拆解

---

### P0-1: 滑点敏感性测试

**现状**: `config.py:34` 固定 `slippage_rate=0.001`（单边 0.1%），微盘股实际 bid-ask spread 0.3%-0.5%。

**方案**: 在 grid search 中加入 slippage 维度，输出 Sharpe 衰减表和可视化。

#### 任务拆解

| 编号 | 任务 | 文件 | 说明 |
|------|------|------|------|
| 1.1 | `run_grid.py` 增加 `--slippage` CLI 参数 | `run_grid.py` | 接受多个浮点值，如 `--slippage 0.001 0.002 0.003 0.005` |
| 1.2 | grid search 循环中加入 slippage 维度 | `run_grid.py` | 在 factor x hold_days 外层再套一层 slippage 循环 |
| 1.3 | 汇总输出增加 slippage 列 | `run_grid.py` | `grid_summary.json` 增加 slippage_rate 字段 |
| 1.4 | 新增 `slippage_sensitivity_report()` | `run_grid.py` | 固定最优因子+持有期，输出 slippage vs Sharpe/AnnualReturn 表格到 CSV |
| 1.5 | 单元测试: 验证不同 slippage 下成本计算正确 | `tests/unit/test_microcap_slippage.py` | 构造已知价格序列，断言买卖价格 = raw * (1 +/- slippage) |

#### 验收标准

- [ ] `python -m strategist.microcap.run_grid --slippage 0.001 0.002 0.003 0.005 --hold-days 5 --factor peg` 可正常运行
- [ ] `output/microcap/slippage_sensitivity.csv` 包含 4 行数据，列含 slippage_rate / annual_return / sharpe / max_drawdown
- [ ] 单测通过: `pytest tests/unit/test_microcap_slippage.py -v` 全绿
- [ ] 当 slippage=0.005 时，买入价 = open * 1.005，卖出价 = open * 0.995（精度 1e-6）

---

### P0-2: 涨跌停处理

**现状**: `backtest.py:318-321` 仅处理 price=None/0（停牌），未检测一字涨跌停。实盘中一字跌停无法卖出，一字涨停无法买入。

**方案**: 加载价格时同时判断是否一字板，买卖逻辑中相应跳过或顺延。

#### 任务拆解

| 编号 | 任务 | 文件 | 说明 |
|------|------|------|------|
| 3.1 | `_load_prices_for_date` 增加涨跌幅和最高/最低价加载 | `backtest.py` | SQL 增加 high_price, low_price, pct_chg 字段，缓存到 `_price_cache` |
| 3.2 | 新增 `_is_limit_down(stock_code, trade_date)` | `backtest.py` | 判断条件: open==high==low==close 且 pct_chg <= -9.5%（ST 为 -4.5%） |
| 3.3 | 新增 `_is_limit_up(stock_code, trade_date)` | `backtest.py` | 判断条件: open==high==low==close 且 pct_chg >= 9.5%（ST 为 4.5%） |
| 3.4 | 卖出逻辑: 跌停顺延 | `backtest.py` | 到期日若一字跌停，sell_date 顺延到下一个非跌停交易日（最多顺延 5 日，超过则强制以当日收盘价卖出） |
| 3.5 | 买入逻辑: 涨停跳过 | `backtest.py` | T+1 买入日若一字涨停，跳过该标的，资金分配给其余股票 |
| 3.6 | 新增统计: 涨跌停触发次数 | `backtest.py` | 在 summary 中增加 limit_up_skipped / limit_down_delayed 计数 |
| 3.7 | 单元测试: 涨跌停判断 | `tests/unit/test_microcap_limit.py` | 构造一字板价格数据，验证判断函数准确性 |
| 3.8 | 单元测试: 卖出顺延逻辑 | `tests/unit/test_microcap_limit.py` | 模拟连续 3 天跌停后第 4 天正常，验证卖出日期为第 4 天 |

#### 验收标准

- [ ] 一字跌停（open==high==low==close, pct_chg<=-9.5%）被正确识别
- [ ] 一字涨停（open==high==low==close, pct_chg>=9.5%）被正确识别
- [ ] 卖出遇跌停时，持仓自动顺延，交易记录中 sell_date > 原始预期 sell_date
- [ ] 买入遇涨停时，该标的被跳过，资金重新分配给其余标的
- [ ] 连续 5 天跌停时强制卖出，不会无限顺延
- [ ] summary 中 limit_up_skipped / limit_down_delayed 字段有值
- [ ] 单测通过: `pytest tests/unit/test_microcap_limit.py -v` 全绿

---

### P0-3: PEG 因子前视偏差修复

**现状**: `factors.py:66` 使用 `report_date <= trade_date`，但 `report_date` 是报告期（如 2025-12-31），不是披露日。年报最晚 4 月 30 日才披露，1-4 月间会错误使用尚未公开的年报数据。

**方案**: 增加披露日约束；若无 announce_date 字段，用保守规则兜底。

#### 任务拆解

| 编号 | 任务 | 文件 | 说明 |
|------|------|------|------|
| 4.1 | 检查 `trade_stock_financial` 表是否有 announce_date 字段 | 数据层 | 执行 `SHOW COLUMNS FROM trade_stock_financial` |
| 4.2a | (有 announce_date) 修改 SQL 为 `announce_date <= trade_date` | `factors.py` | 替换 `report_date <= %s` 为 `announce_date <= %s` |
| 4.2b | (无 announce_date) 增加保守规则 | `factors.py` | 1-4 月只用 report_year <= year(trade_date) - 1 的年报；5-12 月用 report_year <= year(trade_date) |
| 4.3 | 增加日志: 记录 EPS 来源年份 | `factors.py` | DEBUG 级别日志，输出 "stock_code=XXX, trade_date=XXX, eps_year_latest=XXX, eps_year_prior=XXX" |
| 4.4 | 单元测试: 前视偏差防护 | `tests/unit/test_microcap_pit.py` | 构造场景: trade_date=2026-03-15，年报 report_date=2025-12-31，验证该年报不被使用（保守规则下） |
| 4.5 | 单元测试: 正常场景 | `tests/unit/test_microcap_pit.py` | trade_date=2026-06-15，2025 年报应被正常使用 |

#### 验收标准

- [ ] trade_date 在 1-4 月时，不使用当年度（trade_date 所在年份 - 1）的 12 月年报
- [ ] trade_date 在 5-12 月时，可正常使用上一年度年报
- [ ] 修复前后对 peg_h5 回测结果进行对比，记录 annual_return / sharpe 变化量到日志
- [ ] 单测通过: `pytest tests/unit/test_microcap_pit.py -v` 全绿
- [ ] 无 announce_date 时的保守规则不会导致 5-12 月的 EPS 覆盖率下降

---

### P1-1: 补测持有期参数（h4/h6/h7/h8）

**现状**: 仅测了 h1/h3/h5/h10，h3(3.9%) 到 h5(27.15%) 跳跃过大，无法判断 h5 是高原还是尖峰。

**方案**: 纯参数扩展，无代码改动（`run_grid.py` 已支持任意 `--hold-days` 列表）。

#### 执行命令（P0 + P1-2 修复后）

```bash
# 补测 h2/h4/h6/h7/h8（在修复后的引擎上重跑）
DB_ENV=online python -m strategist.microcap.run_grid \
  --start 2022-01-01 --end 2026-03-24 \
  --factors peg --hold-days 2 4 6 7 8

# 滑点敏感性测试（h5 固定，4档滑点）
DB_ENV=online python -m strategist.microcap.run_grid \
  --start 2022-01-01 --end 2026-03-24 \
  --factors peg --hold-days 5 \
  --slippage 0.001 0.002 0.003 0.005
```

#### 任务拆解

| 编号 | 任务 | 文件 | 说明 |
|------|------|------|------|
| 5.1 | 执行补测 h2/h4/h6/h7/h8 | 命令行 | 见上方命令 |
| 5.2 | 汇总 h1~h10 全量结果表 | 手动/脚本 | 合并所有 grid_summary，输出 hold_days vs annual_return / sharpe 表 |
| 5.3 | 判断参数鲁棒性 | 分析 | 如果 h4-h6 之间 Sharpe 变化 < 20%，则为高原；否则标记过拟合风险 |

#### 验收标准

- [ ] h1/h3/h4/h5/h6/h7/h8/h10 共 8 个持有期的完整回测结果
- [ ] 输出 `output/microcap/hold_days_sensitivity.csv`，含 hold_days / annual_return / sharpe / max_drawdown
- [ ] 文档中记录结论: h5 附近是高原还是尖峰

---

### P1-2: 成交额过滤

**现状**: `universe.py` 无任何流动性过滤，可能选入日均成交额极低的标的。

**方案**: 在选股池构建时加入近 5 日平均成交额过滤。

#### 任务拆解

| 编号 | 任务 | 文件 | 说明 |
|------|------|------|------|
| 6.1 | `MicrocapConfig` 增加 `min_avg_turnover` 参数 | `config.py` | 默认 500 万（单位: 元），CLI 可配 |
| 6.2 | `get_daily_universe()` 增加成交额过滤 | `universe.py` | 从 `trade_stock_daily` 取近 5 日 amount 均值，剔除低于阈值的标的 |
| 6.3 | `run_backtest.py` / `run_grid.py` 增加 `--min-turnover` CLI 参数 | CLI 入口 | 传递到 config |
| 6.4 | 单元测试: 成交额过滤 | `tests/unit/test_microcap_universe.py` | 构造含低成交额股票的数据，验证被正确过滤 |
| 6.5 | 对比测试 | 回测 | 加过滤前后的 peg_h5 对比，记录收益和持仓数量变化 |

#### 验收标准

- [ ] `--min-turnover 5000000` 时，日均成交额 < 500 万的标的不出现在选股池中
- [ ] 过滤后每日选股池平均数量记录在 summary 中（新增 avg_universe_size 字段）
- [ ] 单测通过: `pytest tests/unit/test_microcap_universe.py -v` 全绿
- [ ] 过滤前后回测结果对比记录到日志

---

### P2-1: 退市股数据补全

**现状**: 85 只退市股因 AKShare 拉取失败不在 `trade_stock_daily_basic` 表中，这些恰是微盘股策略最可能选中的标的。

**方案**: 补全退市股历史数据，退市后标记价格归零。

#### 任务拆解

| 编号 | 任务 | 文件 | 说明 |
|------|------|------|------|
| 2.1 | 获取 A 股历史退市股列表 | 新脚本 `scripts/fetch_delisted_stocks.py` | 从 AKShare `stock_info_sh_delist` / `stock_info_sz_delist` 获取 |
| 2.2 | 补充退市股的历史日线数据 | 同上脚本 | 尝试从 AKShare 拉取退市前的日线数据写入 `trade_stock_daily` |
| 2.3 | 补充退市股的 daily_basic 数据 | 同上脚本 | 写入 `trade_stock_daily_basic`，退市后日期标记 total_mv=0 |
| 2.4 | 回测引擎处理归零标的 | `backtest.py` | 持仓股票在持有期内退市（price=0 或无数据），按归零处理，亏损 100% |
| 2.5 | 单元测试: 退市归零处理 | `tests/unit/test_microcap_delist.py` | 构造持有期内退市场景，验证 PnL = -100% |
| 2.6 | 对比测试 | 回测 | 补数据前后 peg_h5 对比 |

#### 验收标准

- [ ] 退市股列表 >= 80 只被识别并记录
- [ ] 退市股在退市前的历史数据已写入数据库
- [ ] 回测中持仓股退市时，该笔交易 return = -1.0（亏损 100%）
- [ ] 单测通过: `pytest tests/unit/test_microcap_delist.py -v` 全绿
- [ ] 补数据前后回测结果对比已记录

---

### P2-2: 基准对比

**现状**: 回测无基准线，无法判断收益是 alpha 还是 beta。

**方案**: 接入国证 2000 指数作为基准，计算超额收益和信息比率。

#### 任务拆解

| 编号 | 任务 | 文件 | 说明 |
|------|------|------|------|
| 7.1 | 新增基准数据拉取 | `strategist/microcap/benchmark.py` | 从 AKShare `index_zh_a_hist` 拉取国证 2000 (399303) 日线数据 |
| 7.2 | `MicrocapConfig` 增加 `benchmark_code` 参数 | `config.py` | 默认 '399303'（国证 2000） |
| 7.3 | `_calc_summary()` 增加超额收益指标 | `backtest.py` | 计算: excess_annual_return, information_ratio, beta, alpha |
| 7.4 | 可视化增加基准 NAV 曲线 | 新增或修改可视化模块 | 策略 NAV vs 基准 NAV 双线图 |
| 7.5 | 单元测试: 超额收益计算 | `tests/unit/test_microcap_benchmark.py` | 构造策略和基准日收益序列，验证 excess_return / IR 计算正确 |

#### 验收标准

- [ ] summary 中新增 benchmark_annual_return / excess_annual_return / information_ratio / beta / alpha 字段
- [ ] `output/microcap/` 下输出含基准曲线的 NAV 对比图
- [ ] 单测通过: `pytest tests/unit/test_microcap_benchmark.py -v` 全绿
- [ ] 基准数据日期范围覆盖回测区间，缺失率 < 1%

---

## 三、实施顺序与依赖关系

```
阶段 1 (P0 -- 回测可信度根基)
  ├── P0-3: PEG 前视偏差修复     ← 最先做，影响后续所有回测结论
  ├── P0-2: 涨跌停处理           ← 与 P0-3 无依赖，可并行
  └── P0-1: 滑点敏感性测试       ← 依赖 P0-2/P0-3 完成后的代码，最后跑

阶段 2 (P1 -- 回测完善)
  ├── P1-2: 成交额过滤           ← 先做，改变选股池
  └── P1-1: 补测 h4/h6/h7/h8    ← 在 P0 + P1-2 全部完成后再跑，确保参数测试基于修复后的引擎

阶段 3 (P2 -- 锦上添花)
  ├── P2-1: 退市股数据补全       ← 数据量大，可后台执行
  └── P2-2: 基准对比             ← 与 P2-1 无依赖，可并行
```

---

## 四、测试策略

### 单元测试文件清单

| 测试文件 | 覆盖任务 | 测试数量（预估） |
|----------|----------|------------------|
| `tests/unit/test_microcap_slippage.py` | P0-1 | 3-4 cases |
| `tests/unit/test_microcap_limit.py` | P0-2 | 5-6 cases |
| `tests/unit/test_microcap_pit.py` | P0-3 | 3-4 cases |
| `tests/unit/test_microcap_universe.py` | P1-2 | 3-4 cases |
| `tests/unit/test_microcap_delist.py` | P2-1 | 2-3 cases |
| `tests/unit/test_microcap_benchmark.py` | P2-2 | 3-4 cases |

### 集成测试

每个阶段完成后，执行一次完整的 peg_h5 回测（短周期，如 3 个月），与修复前基线对比:

```bash
# 基线（修复前，已有结果）
# peg_h5: annual_return=27.15%, sharpe=0.866, max_dd=-49.76%

# 修复后跑同样参数
DB_ENV=online python -m strategist.microcap.run_backtest \
  --factor peg --hold-days 5 --start 2022-01-01 --end 2026-03-24
```

预期: 修复前视偏差 + 涨跌停后，annual_return 和 Sharpe 会有所下降，这是正常的（回测更真实了）。

---

## 五、风险与注意事项

1. **P0-3（前视偏差）修复后 PEG 收益可能显著下降** -- 如果大部分超额来自 look-ahead，需要重新评估策略价值。这不是 bug，而是发现了真相。
2. **P0-2（涨跌停）顺延逻辑会增加实际持有天数** -- h5 策略某些交易可能变成 h6/h7，需要在统计中区分"计划持有天数"和"实际持有天数"。
3. **P2-1（退市股）数据可能拉取不全** -- AKShare 对退市股的历史数据覆盖率有限，可能需要多数据源交叉补全。
4. **所有修复完成后必须重新跑一次完整 grid search** -- 之前的参数结论（h5 最优）可能不再成立。
5. **MySQL utf8 字符集限制** -- 所有新增字段、日志、报告中禁止使用 emoji 字符。
