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

## 今晚需要执行的任务

### 1. trade_stock_factor 回填 (预计耗时较长)

回填 3/20 ~ 4/20 共 21 个交易日，每日约 5000 只股票的技术因子计算。

```bash
# 脚本已写好在容器内 /tmp/backfill2.py
docker exec -w /app app-celery-worker-1 python3 /tmp/backfill2.py
```

如果容器已重启（/tmp 丢失），用以下命令重建脚本：

```bash
docker exec app-celery-worker-1 bash -c 'cat > /tmp/backfill2.py << "PYEOF"
import sys
sys.path.insert(0, "/app")
import os
os.chdir("/app")

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger()

from datetime import date
from data_analyst.factors.factor_calculator import calculate_factors_for_date

trading_days = [
    (2026,3,20),(2026,3,23),(2026,3,24),(2026,3,25),(2026,3,26),(2026,3,27),
    (2026,3,30),(2026,3,31),(2026,4,1),(2026,4,2),(2026,4,3),
    (2026,4,7),(2026,4,8),(2026,4,9),(2026,4,10),
    (2026,4,13),(2026,4,14),(2026,4,15),(2026,4,16),(2026,4,17),(2026,4,20)
]

for y,m,d in trading_days:
    dt = date(y,m,d)
    logger.info(f"=== Processing {dt} ===")
    try:
        calculate_factors_for_date(calc_date=dt)
        logger.info(f"Done: {dt}")
    except Exception as e:
        logger.error(f"Failed {dt}: {e}", exc_info=True)

logger.info("=== ALL DONE ===")
PYEOF'
```

### 2. SVD Market State 回填

factor 回填完成后执行：

```bash
docker exec app-celery-worker-1 python3 -c "
import sys; sys.path.insert(0, '/app')
from data_analyst.market_monitor.run_monitor import run_daily_monitor
run_daily_monitor()
"
```

### 3. SW Industry Valuation (需先补 daily_basic)

上游 `trade_stock_daily_basic` 只到 4/17，需要先补数据：

```bash
# 先补 daily_basic (PE/PB 等估值数据)
docker exec app-celery-worker-1 python3 -c "
import sys; sys.path.insert(0, '/app')
from data_analyst.fetchers.daily_basic_fetcher import main
main()
"

# 再算行业估值温度
docker exec app-celery-worker-1 python3 -c "
import sys; sys.path.insert(0, '/app')
from data_analyst.fetchers.sw_industry_valuation_fetcher import run_daily
run_daily()
"
```

## 验证

全部执行完后检查：

```bash
docker exec app-celery-worker-1 python3 -c "
import sys; sys.path.insert(0, '/app')
from config.db import execute_query
for tbl, col in [('trade_stock_factor','calc_date'), ('trade_svd_market_state','calc_date'), ('trade_stock_rps','trade_date'), ('sw_industry_valuation','trade_date')]:
    rows = execute_query('SELECT MAX(' + col + ') as mx FROM ' + tbl, env='online')
    print(tbl + ': ' + str(rows[0]['mx']))
"
```

预期结果：
- trade_stock_factor: 2026-04-20
- trade_svd_market_state: 2026-04-20
- trade_stock_rps: 2026-04-20
- sw_industry_valuation: 2026-04-20 (取决于 daily_basic 能否补到 4/20)

## 后续：防止再次滞后

factor_storage.py 的 bug 修复只在容器内做了 sed，没有提交到 git。
这个文件属于 myTrader 项目，需要在源码中也修复并重新部署。
