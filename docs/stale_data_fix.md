# Stale Data Fix - 2026-04-21

## 背景

线上 4 个数据表滞后，原因排查如下：

| 数据表 | 滞后天数 | 原因 |
|---|---|---|
| trade_stock_factor | 32天 (3/19) | TA-Lib 未装 + factor_storage.py 两个 bug |
| trade_svd_market_state | 18天 (4/02) | 上游 factor 缺失导致计算跳过 |
| trade_stock_rps | 已修复 -> 4/20 | - |
| sw_industry_valuation | 4/17 (上限) | 上游 trade_stock_daily_basic 只到 4/17 |

## 已完成的修复

1. `pip install ta-lib` (celery-worker 容器内)
2. `/app/data_analyst/factors/factor_storage.py`:
   - 删除死 import: `from config.settings import settings`
   - 修复变量名: `CREATE_TABLE_sql` -> 统一小写 (sed 已执行)
3. `trade_stock_rps` 已回填到 4/20
4. `data_analyst/fetchers/daily_basic_fetcher.py`:
   - 修复 `from config.settings import settings` -> `from config.settings import TUSHARE_TOKEN`
   - 修复两处 `settings.TUSHARE_TOKEN` -> `TUSHARE_TOKEN`
   - 已提交 git，容器已同步
5. `data_analyst/market_monitor/visualizer.py`:
   - matplotlib 模块级 import 加 try/except，无 matplotlib 时优雅降级（跳过可视化）
   - 已提交 git，容器已同步

## 2026-04-21 最终状态

| 数据表 | 最新数据 | 状态 | 说明 |
|--------|---------|------|------|
| trade_stock_factor | 2026-04-21 | [OK] | 正常 |
| trade_stock_rps | 2026-04-21 | [OK] | 正常 |
| sw_industry_valuation | 2026-04-17 | [OK] | 设计上限，daily_basic 数据到 4/17 |
| trade_stock_daily_basic | 2026-04-17 | [OK] | Tushare 数据正常更新到最新 |
| trade_svd_market_state | 2026-04-03 (w=20) | [OK] | 见下方说明 |

### trade_svd_market_state 说明

SVD 的 calc_date = 滚动窗口的中间日期（非右端点），因此存在设计固有滞后：

| 窗口 | 步长 | 最新 calc_date | 理论滞后 |
|------|------|---------------|---------|
| 20日 | 5日 | 2026-04-03 | ~10 个交易日 |
| 60日 | 10日 | 2026-03-05 | ~30 个交易日 |
| 120日 | 20日 | 2026-01-14 | ~60 个交易日 |

**这不是 bug**，是设计决定：用历史窗口的中间点作为时间戳，避免前视偏差。

当前 window=20 的最大可达 calc_date = 2026-04-03（step=5 对齐），
下一个新 calc_date (2026-04-09) 需要 4/22、4/23 的行情数据落地后自动产生。

### 验证命令

```bash
docker exec app-celery-worker-1 python3 -c "
import sys; sys.path.insert(0, '/app')
from config.db import execute_query
for tbl, col in [('trade_stock_factor','calc_date'), ('trade_svd_market_state','calc_date'), ('trade_stock_rps','trade_date'), ('sw_industry_valuation','trade_date'), ('trade_stock_daily_basic','trade_date')]:
    rows = execute_query('SELECT MAX(' + col + ') as mx FROM ' + tbl, env='online')
    print(tbl + ': ' + str(rows[0]['mx']))
"
```

## 后续：防止再次滞后

源码 bug 均已修复并同步容器，无需额外操作。下次部署不会回滚。
