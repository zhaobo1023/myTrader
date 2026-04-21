# 大盘总览数据修复记录

> 日期: 2026-04-21

## 已完成修复

### HIGH - 代码逻辑修复 (已提交部署)

| 问题 | 文件 | 修复方式 |
|------|------|----------|
| 成交量异常值污染 MA20 | `market_dashboard/calculator.py` | 滚动中位数 * 0.3 过滤异常值 |
| PMI null 误判为 contraction | `market_overview/calculator.py` | 显式 None 检查,返回 "unknown" |
| AH 溢价阈值错误 [120,140] | `market_overview/calculator.py` + `market_dashboard/calculator.py` | 改为 [15,30] (百分比格式) |
| MACD 状态命名歧义 | `market_dashboard/calculator.py` | 新增 `dif_above_dea` / `dif_below_dea` 状态 |
| new_high_60d 为 0 时无回退 | `market_dashboard/calculator.py` | 回退取最近非零记录 |

### MEDIUM - 数据缺失修复

| 问题 | 修复方式 | 状态 |
|------|----------|------|
| idx_sh / idx_gem 无数据 | macro_fetcher 新增注册 + 回填 312 行 | 已完成 (commit f7de6b0) |

## 待今晚执行 (大批量计算)

以下任务需大量 DB 查询,远程连接易超时,建议在服务器本地执行:

### 1. SVD 市场状态更新 (最后数据: 2026-04-02)

```bash
DB_ENV=online python -m data_analyst.market_monitor.run_monitor --latest
```

说明: 需查询全 A 股收益率矩阵做 SVD 分解,本地跑 MySQL 超时。

### 2. Dashboard 数据拉取 (margin/new_high_low 等)

```bash
DB_ENV=online python -c "
from data_analyst.market_dashboard.fetcher import fetch_all
fetch_all('2026-04-21', env='online')
"
```

说明: margin_balance 最后数据 4/10,new_high_low 需从 trade_stock_daily 聚合。

### 3. Fear Index 数据补全 (仅 5 条记录)

```bash
DB_ENV=online python -m data_analyst.sentiment.run_monitor --task fear-index
```

说明: 需调用外部 API 获取 VIX/OVX/GVZ/US10Y,数据源可用性不稳定。

## 非代码问题 (无需修复)

| 问题 | 原因 |
|------|------|
| Margin 数据滞后 (4/10) | 交易所两融数据报送延迟,非代码问题 |
| 成长/价值轮动显示"数据不足" | 依赖因子数据未计算,需先完成因子任务 |
| 5 年锚偏离 current=19.2 | 正确值 (idx_all_a 中证全指点位,非 PE) |
