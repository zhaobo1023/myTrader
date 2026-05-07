# Celery Beat 统一调度方案

> 2026-04-16 整理 + 修复完成

## 背景

项目中存在两套调度系统:

1. **Celery Beat** (`api/tasks/celery_app.py`) -- 生产环境活跃
2. **YAML Scheduler** (`tasks/*.yaml` + `scheduler/`) -- 本地 dry-run 测试用

以 Celery Beat 为唯一生产调度入口。

---

## 修复记录 (2026-04-16)

| 问题 | 修复前 | 修复后 |
|------|--------|--------|
| 恐慌指数过度执行 | `crontab(minute=0)` 每小时 = 24次/天 | 3次/天 (08:00/12:00/18:30) |
| 16:30 三任务冲突 | precheck + watchlist + sim_pool 同时 | 16:25 / 16:30 / 16:35 错开 |
| 18:30 两任务冲突 | factor_calc + stock_news 同时 | stock_news 提前到 17:30 |
| 因子-指标间隔不足 | 18:30 因子 -> 19:00 指标 (30min) | 18:30 因子 -> 19:30 指标 (60min) |
| 指标-策略间隔不足 | 19:00 指标 -> 19:30 策略 (30min) | 19:30 指标 -> 20:10 策略 (40min) |
| 健康报告时间 | 21:00 | 21:30 (所有计算任务完成后) |
| article_digest DDL 列缺失 | INSERT 引用 digest_date/grade/summary 不存在 | migration 已补充 |
| 硬编码凭证 | 飞书 Open ID / 服务器 IP / 脚本路径 | 改为环境变量 |

---

## 完整时间表 (交易日, Asia/Shanghai)

### 凌晨维护

| 时间 | 任务名 | Celery task name | 说明 |
|------|--------|------------------|------|
| 00:05 | 订阅过期检查 | `expire_subscriptions` | 每天 |
| 01:00 | 数据完整性检查 | `scheduler.adapters.run_data_integrity_check` | Mon-Fri |
| 02:00 | 技术面持仓扫描 | `scheduler.adapters.run_tech_scan` | Mon-Fri |
| 03:00 | ETF对数乖离率 | `scheduler.adapters.run_log_bias_strategy` | Mon-Fri |

### 早间

| 时间 | 任务名 | Celery task name | 说明 |
|------|--------|------------------|------|
| 08:00 | 恐慌指数(盘前) | `fetch_fear_index` | Mon-Fri |
| 08:30 | 晨报 -> 飞书 | `publish_morning_briefing` | Mon-Fri |
| 09:35 | SimPool T+1买入价 | `tasks.fill_entry_prices` | Mon-Fri |

### 盘中

| 时间 | 任务名 | Celery task name | 说明 |
|------|--------|------------------|------|
| 每小时:15 | 宏观数据增量 | `fetch_macro_data_hourly` | Redis锁防重叠 |
| 12:00 | 恐慌指数(午间) | `fetch_fear_index` | Mon-Fri |

### 收盘后 -- 独立任务 (无依赖)

| 时间 | 任务名 | Celery task name | 说明 |
|------|--------|------------------|------|
| 16:25 | 复盘数据预检 | `precheck_evening_data` | 检查5张表是否更新 |
| 16:30 | 监控自选股 | `watchlist_scan.scan_all_users` | |
| 16:35 | SimPool每日更新 | `tasks.daily_sim_pool_update` | |
| 17:00 | 复盘 -> 飞书 | `publish_evening_briefing` | |
| 17:30 | 个股新闻拉取 | `fetch_stock_news_daily` | |

### 收盘后 -- 数据处理链 (时间间隔保证顺序)

```
data_gate (18:00)
  -> factor_calc (18:30, ~20min)
    -> indicator_calc (19:30, ~15min)
      -> preset_strategies (20:10, ~20min)
        -> theme_pool_score (20:40)
```

重任务之间间隔 30-40 分钟, 避免 3.6GB 服务器 OOM。

| 时间 | 任务名 | Celery task name | 依赖 |
|------|--------|------------------|------|
| 18:00 | 数据就绪Gate | `scheduler.adapters.run_data_gate` | 无 (轮询) |
| 18:30 | 因子计算 | `scheduler.adapters.run_factor_calculation` | gate |
| 18:30 | 恐慌指数(盘后) | `fetch_fear_index` | 无 |
| 19:30 | 指标计算 | `scheduler.adapters.run_indicator_calculation` | 因子 |
| 20:10 | 预设策略 | `run_preset_strategies_daily` | 指标 |
| 20:40 | 主题池评分 | `scheduler.adapters.run_theme_pool_score` | 指标 |

### 晚间收尾

| 时间 | 任务名 | Celery task name | 说明 |
|------|--------|------------------|------|
| 21:30 | 数据健康日报 | `push_daily_health_report` | 推送到飞书 |

---

## 总任务数

当前: **20 个** Celery Beat 任务

---

## 注意事项

1. **依赖是时间间隔保证的**: Celery Beat 不支持 DAG 依赖, 依靠任务间留足时间间隔。如果上游超时, 下游仍会按时启动。data_gate 有 60min 超时。
2. **YAML Scheduler 保留**: YAML 任务定义和 `scheduler/` 模块代码保留不删, 可用于本地 dry-run 测试 (`python -m scheduler run all --dry-run`)。
3. **宏观数据**: 保持每小时拉取, Redis 锁 (55min 过期) 防止重叠运行。
4. **恐慌指数**: 每天3次 (08:00/12:00/18:30), 不再每小时执行。
