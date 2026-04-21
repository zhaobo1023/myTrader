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

## 今晚执行计划

脚本已就位（服务器 `/tmp/` 和容器 `/tmp/` 均已同步）：

| 文件 | 说明 |
|------|------|
| `/tmp/backfill_all.sh` | 主控脚本，串行执行 step1~4 + verify，日志写 `/tmp/backfill_all.log` |
| `/tmp/backfill_step1.py` (容器内) | trade_stock_factor 回填 3/23~4/20（20 个交易日） |
| `/tmp/backfill_step2.py` (容器内) | trade_svd_market_state 回填 |
| `/tmp/backfill_step3.py` (容器内) | daily_basic 补数据 |
| `/tmp/backfill_step4.py` (容器内) | sw_industry_valuation 回填 |
| `/tmp/backfill_verify.py` (容器内) | 验证各表最新日期 |

执行方式（nohup 防断连）：

```bash
ssh aliyun-ecs "nohup /tmp/backfill_all.sh &"
# 查看进度
ssh aliyun-ecs "tail -f /tmp/backfill_all.log"
```

如果容器重启导致 /tmp 脚本丢失，重新 scp 即可（脚本源文件在本地 /tmp/ 下）。

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

源码 bug 均已修复并同步容器，无需额外操作。下次部署不会回滚。
