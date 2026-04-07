# 数据补充方案

五截面分析框架依赖的四张数据表当前为空，本文说明缺失原因、影响范围及补充步骤。

---

## 1. 缺失数据总览

| 表名 | 状态 | 影响截面 | 优先级 |
|------|------|----------|--------|
| `trade_stock_moneyflow` | 空表（0行） | 资金面（权重 20%）| [HIGH] |
| `trade_stock_industry` | 空表（0行） | 全部（行业类型决定估值模型） | [HIGH] |
| `trade_margin_trade` | 空表（0行） | 情绪面（融资余额增速） | [MED] |
| `trade_north_holding` | 空表（0行） | 情绪面（北向偏差） | [MED] |

**已有数据（无需补充）：**
- `trade_stock_rps`：6,587,656 行，正常
- `trade_stock_daily_basic`：PE/PB 估值，正常
- `trade_stock_financial`：财务年报，正常

---

## 2. 各表补充方案

### 2.1 `trade_stock_moneyflow` — 主力资金净流入

**数据来源：** AKShare `ak.stock_individual_fund_flow`（东方财富接口）

**字段对应：**
```
超大单净流入 + 大单净流入 -> net_mf_amount（主力净流入金额，元）
```

**补充步骤：**
```bash
# 1. 快速验证单只股票
DB_ENV=online python scripts/fetch_moneyflow.py --stock 000807

# 2. 全量补充（约 5000 只股票，建议 workers=3 避免频控）
DB_ENV=online python scripts/fetch_moneyflow.py --start 2024-01-01 --workers 3

# 3. 后续每日增量（计划任务或手动）
DB_ENV=online python scripts/fetch_moneyflow.py --start 2025-01-01
```

**预计耗时：** ~3-5 小时（5000 只 × 0.8s/只 ÷ 3 并行）

**注意：**
- AKShare 东方财富接口有频控限制，`REQUEST_DELAY=0.8s` 为保守值
- 如遇 IP 封禁，增大 `--workers` 等待时间或改用代理

---

### 2.2 `trade_stock_industry` — 申万行业分类

**数据来源（双路）：**
- 优先：AKShare `ak.sw_index_first_info()` + `ak.sw_index_cons()`（官方申万分类）
- 快速备用：`trade_stock_basic.industry` 字段（已有 5497 条，分类名与申万基本一致）

**补充步骤：**

**方案 A（推荐）— AKShare 官方申万：**
```bash
DB_ENV=online python scripts/fetch_sw_industry.py
```

**方案 B（快速备用）— 从 trade_stock_basic 同步：**
```bash
# 立即可用，约 1 秒完成，无网络请求
DB_ENV=online python scripts/fetch_sw_industry.py --use-basic
```

> 方案 B 适合立即恢复五截面报告功能；方案 A 适合数据准确性要求更高的场景。
> 两者均使用 `classify_type='SW', industry_level='1'`，可被 `IndustryClassifier` 直接读取。

**验证：**
```bash
DB_ENV=online python -c "
from config.db import execute_query
rows = execute_query('SELECT COUNT(*) as c FROM trade_stock_industry WHERE classify_type=\"SW\"', env='online')
print('SW industry rows:', rows[0]['c'])
rows = execute_query('SELECT industry_name, COUNT(*) as c FROM trade_stock_industry WHERE classify_type=\"SW\" GROUP BY industry_name ORDER BY c DESC LIMIT 10', env='online')
for r in rows: print(r)
"
```

---

### 2.3 `trade_margin_trade` — 融资融券

**数据来源：** AKShare `ak.stock_margin_detail_szse` / `ak.stock_margin_detail_sse`

**影响：** 情绪面 `融资余额增速` 指标（融资买入额 / 融资余额变化率）

**补充步骤：**
```bash
# 方案 A: 按日期批量拉取（推荐，效率高）
DB_ENV=online python scripts/fetch_margin.py --by-date --start 2024-01-01

# 方案 B: 逐只股票（可测试单只）
DB_ENV=online python scripts/fetch_margin.py --stock 000807 --start 2024-01-01
```

**注意：** 融资融券数据仅覆盖两融标的股（约 2000 只），非全市场。

---

### 2.4 `trade_north_holding` — 沪深港通北向持仓

**数据来源：** AKShare `ak.stock_hsgt_individual_em`（沪股通/深股通）

**影响：** 情绪面 `北向资金偏差` 指标（北向持仓比例相对60日均值的偏离）

**补充步骤：**
```bash
# 按日期批量拉取（推荐）
DB_ENV=online python scripts/fetch_north_holding.py --start 2024-01-01

# 测试单只
DB_ENV=online python scripts/fetch_north_holding.py --stock 000807
```

**注意：** 北向持仓仅覆盖沪深港通标的（约 500 只），其余股票情绪面降级为仅融资余额评分。

---

## 3. 执行顺序建议

**注意：** fetch_moneyflow / fetch_margin / fetch_north_holding 调用 AKShare（东方财富接口），
需要能访问 push2his.eastmoney.com。如本地网络不通，请在服务器（100.119.128.104）上运行。

```
优先级 1（行业分类，已完成 -- 2026-04-07 通过 --use-basic 回填了 5194 条）:
  DB_ENV=online python scripts/fetch_sw_industry.py --use-basic --envs online

优先级 2（在服务器上执行，恢复资金面评分）:
  python scripts/fetch_moneyflow.py --start 2024-01-01 --no-proxy --envs online

优先级 3（在服务器上执行，完善情绪面评分）:
  python scripts/fetch_margin.py --by-date --start 2024-01-01 --no-proxy --envs online
  python scripts/fetch_north_holding.py --start 2024-01-01 --no-proxy --envs online
```

**双写说明（仅限服务器上本地 DB 也可达时）：**
```bash
python scripts/fetch_moneyflow.py --start 2024-01-01 --no-proxy --envs local,online
```

---

## 4. 定期更新（每日增量）

建议将以下命令加入调度器 `tasks/06_maintenance.yaml`：

```yaml
- name: fetch_moneyflow_daily
  description: "每日补充主力资金流向"
  command: "DB_ENV=online python scripts/fetch_moneyflow.py --start {yesterday}"
  schedule: "18:30"
  tags: [daily, data]

- name: fetch_margin_daily
  description: "每日补充融资融券"
  command: "DB_ENV=online python scripts/fetch_margin.py --by-date --start {yesterday}"
  schedule: "18:45"
  tags: [daily, data]
```

---

## 5. 数据完整性验证

执行补充后，运行完整性检查确认状态：

```bash
# 检查所有模块
DB_ENV=online python scripts/data_completeness_check.py

# 仅检查已补充的模块
DB_ENV=online python scripts/data_completeness_check.py --modules moneyflow industry margin

# 对比两套环境
python scripts/data_completeness_check.py --compare
```

期望结果：

| 模块 | 补充前 | 补充后 |
|------|--------|--------|
| moneyflow | [FAIL] 0 行 | [OK] |
| industry | [FAIL] 0 行 | [OK] |
| margin | [FAIL] 0 行 | [OK] 或 [WARN] 覆盖率 <100% |
| north_holding | [FAIL] 0 行 | [OK] 或 [WARN] 覆盖率 <100% |
