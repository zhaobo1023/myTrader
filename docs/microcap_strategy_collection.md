# 微盘股策略集合 - 完整文档

**更新时间:** 2026-04-09  
**维护者:** zhaobo  
**代码路径:** `strategist/microcap/`

---

## 一、策略分类总览

### 分类框架

微盘股策略按"选股逻辑"分为四类：

| 类别 | 策略名称 | 核心思路 | 实现状态 |
|------|---------|--------|---------|
| **基本面小市值** | PEG+EBIT+小市值 | 质量筛选后再取最小市值 | [OK] 已实现 |
| **估值小市值** | 低PEG微盘 | 微盘池内选低估值 | [OK] 已实现 |
| **估值小市值** | 低PE微盘 | 微盘池内选低市盈率 | [OK] 已实现 |
| **质量小市值** | 高ROE微盘 | 微盘池内选高盈利质量 | [OK] 已实现 |
| **垃圾小市值** | 纯市值轮动 | 无基本面，纯选最小市值 | [OK] 已实现 |
| **机器学习小市值** | XGBoost截面预测 | 52因子ML预测+小市值 | [OK] 另见 xgboost_strategy/ |
| **高股息小市值** | 小市值高股息 | 小市值+高分红 | [TODO] 待实现 |
| **赛道小市值** | 行业轮动+小市值 | 热门赛道内选最小市值 | [TODO] 待实现 |

---

## 二、已实现策略详解

### 策略 1：PEG+EBIT+小市值（基本面小市值）

**代码因子名：** `peg_ebit_mv`  
**参考来源：** 2020年分享的基本面小市值策略，2025年收益124%，每年跑赢微盘指数

#### 选股逻辑（两阶段漏斗）

```
全市场 (~5000只)
    |
    | 第一层：按 PEG 升序，保留最小 20%
    v
约 1000 只（低PEG股票）
    |
    | 第二层：按 EBIT 降序，保留最大 30%
    v
约 300 只（低PEG + 高EBIT）
    |
    | 第三层：按总市值升序，选最小的 top_n 只
    v
最终持仓 5-10 只
```

#### 因子公式

```
PEG = PE_TTM / (EPS同比增速 × 100)
      EPS同比增速 = (最新年报EPS - 上年EPS) / |上年EPS|
      只保留增速 > 0 且 PEG < 1000 的股票

EBIT = 息税前利润（来自 trade_stock_ebit，最近年报）
       EBIT > 0 才有效

市值排序：总市值 total_mv 升序（越小越靠前）
```

#### 与其他策略的本质区别

- **不先限定微盘池**：从全市场挑，然后因为小市值排序，自然落在小票上
- **质量优先**：PEG 和 EBIT 都是质量/价值筛选，最后的市值排序是"锦上添花"
- **容量较高**：候选池更广，比纯微盘池策略更不容易踩流动性问题

#### 运行命令

```bash
DB_ENV=online python -m strategist.microcap.run_backtest \
  --start 2022-01-01 --end 2026-03-24 \
  --factor peg_ebit_mv \
  --top-n 10 \
  --hold-days 1 \
  --exclude-st
```

#### 数据依赖

| 数据表 | 字段 | 用途 |
|--------|------|------|
| `trade_stock_daily_basic` | pe_ttm, total_mv | PEG计算、市值排序 |
| `trade_stock_financial` | eps | EPS增速计算 |
| `trade_stock_ebit` | ebit | EBIT筛选 |
| `trade_stock_daily` | close_price | 买卖价格 |

---

### 策略 2：低PEG微盘（估值小市值）

**代码因子名：** `peg`

#### 选股逻辑

```
微盘池：全市场市值后 20%（~1000只）
    → 排除 ST/*ST
    → 计算 PEG = PE_TTM / (EPS增速 × 100)
    → 选 PEG 最小的 top_n 只（默认15只）
```

#### 特点

- 兼顾估值（PE低）和成长性（EPS增速高）
- 在微盘股中进一步用质量因子筛选，避免"纯垃圾"
- **问题**：年报季（3-4月）EPS数据未更新，容易选出被错误估值的股票

#### 运行命令

```bash
DB_ENV=online python -m strategist.microcap.run_backtest \
  --start 2022-01-01 --end 2026-03-24 \
  --factor peg --top-n 15 --hold-days 1 --exclude-st
```

#### 回测结果（2025-03-24 ~ 2026-03-24，1年）

| 指标 | 值 |
|------|-----|
| 总收益 | -5.58% |
| 年化收益 | -5.73% |
| 夏普比率 | -0.14 |
| 最大回撤 | -17.80% |
| 胜率 | 47.49% |
| 总交易笔数 | 3102 |

月度收益（正收益 6 个月，负收益 7 个月）：

| 月份 | 收益 | 备注 |
|------|------|------|
| 2025-03 | -0.30% | 仅6个交易日 |
| 2025-04 | -5.10% | 年报季风险 |
| 2025-05 | +4.21% | |
| 2025-06 | +1.04% | |
| 2025-07 | -3.24% | |
| 2025-08 | -1.53% | |
| 2025-09 | -4.32% | |
| 2025-10 | +2.38% | |
| 2025-11 | +3.96% | 微盘行情 |
| 2025-12 | -7.49% | 最大月度亏损 |
| 2026-01 | +5.11% | 节后微盘反弹 |
| 2026-02 | +4.21% | |
| 2026-03 | -9.86% | 最大单月亏损 |

**结论：** 策略阶段性有效，微盘风格主导月份有超额，风格切换月份损失大

---

### 策略 3：低PE微盘（纯价值小市值）

**代码因子名：** `pe`

#### 选股逻辑

```
微盘池：全市场市值后 20%（~1000只）
    → 排除 ST/*ST
    → 按 PE_TTM 升序
    → 选最小 PE 的 top_n 只
```

#### 特点

- 比 PEG 更简单，不依赖 EPS 增速数据（EPS 缺失比例约 8%）
- 纯价值逻辑：市场对这些股票的盈利定价最低
- **风险**：可能选到"价值陷阱"——PE 低是因为基本面持续恶化

#### 数据依赖

只需 `trade_stock_daily_basic.pe_ttm`，数据最完整

---

### 策略 4：高ROE微盘（质量小市值）

**代码因子名：** `roe`

#### 选股逻辑

```
微盘池：全市场市值后 20%（~1000只）
    → 排除 ST/*ST
    → 取最近年报 ROE（roe_avg）
    → 选 ROE 最高的 top_n 只
```

#### 特点

- 质量因子：用净资产收益率衡量公司赚钱能力
- 微盘股中 ROE 高的公司通常是细分龙头或隐形冠军
- **注意**：ROE 取负值后排序，保持"越小越好"接口一致

---

### 策略 5：纯市值轮动（垃圾小市值）

**代码因子名：** `pure_mv`

#### 选股逻辑

```
全市场 (~5000只)
    → 排除 ST/*ST
    → 按总市值升序
    → 选最小 top_n 只（默认15只）
```

#### 特点

- **无任何基本面筛选**，纯粹买最小市值的股票
- 利用小市值效应（小市值股票历史上有超额收益）
- 高换手，成本消耗大
- **容量极低**：最小市值股票流动性差，实盘大资金无法跟踪
- **适合用来验证小市值效应是否存在**，作为其他策略的基准

#### 预期行为

- 牛市/微盘行情中表现极好（弹性大）
- 熊市或流动性危机时损失惨重
- 年化收益可能很高，但最大回撤也很大

---

## 三、回测框架设计

### 核心文件

```
strategist/microcap/
├── config.py          # 参数配置类 MicrocapConfig
├── universe.py        # 股票池构建 get_daily_universe()
├── factors.py         # 因子计算（6个因子函数）
├── backtest.py        # 回测引擎 MicrocapBacktest
├── run_backtest.py    # 单策略 CLI
└── run_grid.py        # 多策略网格对比
```

### 回测流程

```
每个交易日循环：
  Step 1: 先卖出到期持仓（T日 sell_date 触发）→ 现金回收
  Step 2: 用回收现金买入前一日选好的标的（T+1 买入）
           只买未持有的股票（避免覆盖已有仓位）
  Step 3: 选出今日因子排名最小的 top_n 只（明日买入）
  Step 4: NAV = 现金 + Σ(持仓 × 当日收盘价)
```

### 关键 Bug 记录和修复

| Bug | 原因 | 修复方式 |
|-----|------|---------|
| NAV 第3天归零 | Buy 在 Sell 之前执行，hold_days=1 时现金耗尽后原始仓位被覆盖 | 先 Sell 后 Buy |
| 持仓 units 丢失 | 同一只股票被重新选中时 holdings[code] 直接覆盖 | 跳过已持有股票 |
| total_return=-1.0 | 上述两个 bug 叠加导致 NAV 归零 | 两个 bug 同时修复 |
| pe_ttm 写入溢出 | 极端亏损股 PE 超过 DECIMAL(10,4) 范围 | 插入前截断为 NULL |
| 数据单位不一致 | AKShare 返回元，DB 存亿元 | 插入时除以 1e8 |

### 价格缓存优化

原始实现每次查询一只股票的价格（一日约 45 次 DB 查询），已优化为：
- `_load_prices_for_date(trade_date)`：一次性加载某日全市场价格
- `_price_cache`：日期级缓存，避免重复查询
- 效果：250天回测从约 11000 次查询减少到 250 次

---

## 四、网格测试计划

### 当前正在运行的测试

**运行时间：** 2026-04-09 启动  
**日志：** `/tmp/grid_test.log`

```bash
# 查看实时进度
grep -E "RUN|OK.*total=|ERROR" /tmp/grid_test.log | tail -20
```

### 测试矩阵（3因子 × 4持仓周期 = 12组合）

| 因子 | hold=1 | hold=3 | hold=5 | hold=10 |
|------|--------|--------|--------|---------|
| peg | - | - | - | - |
| pe | - | - | - | - |
| roe | - | - | - | - |

### 待追加测试（数据就绪后）

```bash
# 基本面小市值策略（核心策略）
DB_ENV=online python -m strategist.microcap.run_grid \
  --start 2022-01-01 --end 2026-03-24 \
  --factors peg_ebit_mv pure_mv \
  --hold-days 1 3 5

# 查看网格汇总
cat /tmp/grid_test.log | tail -60
```

---

## 五、数据准备状态

### trade_stock_daily_basic（关键表）

| 状态 | 说明 |
|------|------|
| 原始数据 | 2025-03-24 ~ 2026-03-24（366天，来自原始系统） |
| 历史补充 | 2022-01-04 起，AKShare stock_value_em 拉取 |
| 拉取进度 | 进行中（约 1590/5196 只，预计 13:10 完成） |
| 拉取脚本 | `data_analyst/financial_fetcher/daily_basic_history_fetcher.py` |

```bash
# 查看拉取进度
grep -E "进度|完成" /tmp/daily_basic_history.log | tail -5

# 完成后验证
DB_ENV=online python -c "
from config.db import get_connection
conn = get_connection()
cur = conn.cursor()
cur.execute('SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT stock_code) FROM trade_stock_daily_basic')
print(cur.fetchone())
conn.close()
"
```

### 其他数据表

| 数据表 | 状态 | 覆盖范围 |
|--------|------|---------|
| `trade_stock_daily` | [OK] 完整 | 全A股历史 |
| `trade_stock_financial` | [OK] 完整 | 2016-2025年报 |
| `trade_stock_ebit` | [部分] 测试拉了1只 | 需要全量拉取 |

```bash
# 补充全量 EBIT 数据
DB_ENV=online python data_analyst/financial_fetcher/tushare_ebit_fetcher.py
```

---

## 六、输出文件位置

### 已有回测结果

```
output/microcap/
├── backtest_20250324_20260324.csv              # PEG策略交易记录（1年）
├── backtest_daily_values_20250324_20260324.csv # PEG策略每日净值
├── backtest_monthly_20250324_20260324.csv      # PEG策略月度收益
├── backtest_summary.json                       # 最新一次回测摘要
├── grid_peg_h1_*.csv                           # 网格测试结果（运行中）
└── daily_basic_history.log                     # 历史数据拉取日志
```

### 网格测试完成后

```
output/microcap/
├── grid_summary_20220101_20260324.json         # 12组合汇总对比
├── grid_<factor>_h<n>_*_daily.csv             # 各组合每日净值
└── grid_<factor>_h<n>_*_monthly.csv           # 各组合月度收益
```

---

## 七、如何解读结果

### 关键指标

| 指标 | 好的标准 | 说明 |
|------|---------|------|
| 年化收益 | > 15%（跑赢微盘指数） | 绝对收益能力 |
| 夏普比率 | > 0.5 | 风险调整后收益，>1 优秀 |
| 最大回撤 | < 30% | 超过 40% 实盘心理难以承受 |
| 胜率 | > 50% | 低于50%但盈亏比高也可以 |
| 月度正收益比例 | > 55% | 策略稳定性指标 |

### 月度数据的解读

月度收益矩阵最有价值——可以看出：
- **策略失效的季节性规律**：4月（年报季）、年末（机构调仓）通常弱
- **与市场风格的相关性**：微盘行情好的月份策略是否同步受益
- **不同因子的差异化**：peg_ebit_mv 和 pure_mv 在同一月份是否走势分化

### 对比基准

目前没有直接接入微盘指数数据，可以手动对比：
- 国证2000指数（微盘股代表）
- 中证2000指数

---

## 八、后续计划

### 数据层（优先）

- [ ] 完成 trade_stock_daily_basic 历史数据补充（2022-2026）
- [ ] 全量拉取 trade_stock_ebit（5499只股票）
- [ ] 接入微盘指数日线数据作为基准

### 策略层

- [ ] 完成当前网格测试（12组合，2022-2026三年）
- [ ] 运行 peg_ebit_mv 和 pure_mv 三年回测
- [ ] 参数灵敏度分析（peg_pct、ebit_pct 的影响）
- [ ] 加入高股息小市值（dv_ttm 字段已在 daily_basic 表中）
- [ ] 赛道小市值：申万行业内选最小市值（需 sw_rotation 模块配合）

### 风控层（实盘前必做）

- [ ] 年报季（4月）自动降仓或空仓
- [ ] ST/退市前预警（交易所公告接入）
- [ ] 立案调查检测
- [ ] 单日涨跌停处理（无法成交时顺延或取消）

### 容量评估

| 策略 | 预估可用资金规模 | 说明 |
|------|--------------|------|
| pure_mv | < 50万 | 最小市值股流动性极差 |
| peg_ebit_mv (top5-10) | < 200万 | 部分标的流动性受限 |
| peg/pe/roe (top15) | < 500万 | 微盘池流动性可接受 |

---

## 九、快速操作手册

```bash
# 1. 查看数据拉取进度
grep -E "进度|完成|ERROR" /tmp/daily_basic_history.log | tail -5

# 2. 查看网格测试进度
grep -E "RUN|OK.*total=" /tmp/grid_test.log | tail -10

# 3. 手动运行单个策略
DB_ENV=online python -m strategist.microcap.run_backtest \
  --start 2022-01-01 --end 2026-03-24 \
  --factor peg_ebit_mv --top-n 10 --hold-days 1 --exclude-st

# 4. 运行完整网格（数据就绪后）
DB_ENV=online python -m strategist.microcap.run_grid \
  --start 2022-01-01 --end 2026-03-24 \
  --factors peg pe roe peg_ebit_mv pure_mv \
  --hold-days 1 3 5 10

# 5. 查看当前 DB 数据范围
DB_ENV=online python -c "
from config.db import get_connection
conn = get_connection()
cur = conn.cursor()
cur.execute('SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT stock_code), COUNT(*) FROM trade_stock_daily_basic')
print(cur.fetchone())
conn.close()
"
```
