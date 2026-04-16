# Celery Beat 统一调度方案

> 2026-04-16 整合完成

## 背景

项目中存在两套调度系统:

1. **Celery Beat** (`api/tasks/celery_app.py`) -- 生产环境活跃, 20个任务
2. **YAML Scheduler** (`tasks/*.yaml` + `scheduler/`) -- 设计完成但未在生产激活, 30+个任务

整合目标: 以 Celery Beat 为唯一生产调度入口, 将 YAML 中缺失的任务全部补齐, 修复已知问题。

---

## 修复的问题

| 问题 | 修复前 | 修复后 |
|------|--------|--------|
| 恐慌指数过度执行 | `crontab(minute=0)` 每小时 = 24次/天 | 3次/天 (08:00/12:00/18:30) |
| 16:30 三任务冲突 | precheck + watchlist + sim_pool 同时 | 16:25 / 16:30 / 16:35 错开 |
| 18:30 两任务冲突 | factor_calc + stock_news 同时 | stock_news 提前到 17:30 (无依赖) |
| 5个adapter函数缺失 | Celery引用但 adapters.py 中不存在 | 全部实现 |
| YAML任务未纳入Celery | 15个任务只在YAML中定义 | 全部加入 beat_schedule |
| 因子计算无gate检查 | 固定时间触发, 不管数据是否就绪 | 18:00 gate 轮询后才启动后续链 |

---

## 新增的adapter函数 (`scheduler/adapters.py`)

| 函数 | 作用 |
|------|------|
| `run_data_gate()` | 轮询 trade_stock_daily 直到今日数据就绪 (超时60min) |
| `run_factor_calculation()` | 顺序运行 basic -> extended -> valuation -> quality -> technical 因子 |
| `run_indicator_calculation()` | 顺序运行 RPS -> 技术指标 -> SVD 监控 |
| `run_data_integrity_check()` | 调用 check_data_completeness.run_check() |
| `run_tech_scan()` | 调用 tech_scan.run_daily_scan() 扫描持仓技术面 |

---

## 新增 Celery Task 文件

`api/tasks/data_pipeline_tasks.py` -- 为以下任务创建 Celery wrapper:

- 数据补充: `fetch_moneyflow_daily` / `fetch_margin_daily` / `fetch_north_holding_daily`
- 舆情: `fetch_news_sentiment` / `fetch_event_signals` / `fetch_polymarket`
- 指标: `sync_concept_board` / `monitor_candidate_pool` / `fetch_dashboard_data` / `compute_dashboard` / `calc_sw_valuation`
- 健康: `check_data_completeness`

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
| 08:00 | 数据完备性检查 | `check_data_completeness` | Mon-Fri |
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
| 17:00 | 市场看板数据拉取 | `fetch_dashboard_data` | |
| 17:30 | 个股新闻拉取 | `fetch_stock_news_daily` | |

### 收盘后 -- 数据处理链 (有依赖)

依赖关系:

```
data_gate (18:00)
  -> factor_calc (18:30, ~20min)
    -> indicator_calc (19:30, ~15min)
      -> preset_strategies (20:10, ~20min)
      -> theme_pool_score (20:40)
      -> candidate_monitor (20:50)
      -> dashboard_compute (21:00)
```

重任务之间间隔 30-40 分钟, 轻任务间隔 5 分钟, 避免 3.6GB 服务器 OOM。

| 时间 | 任务名 | Celery task name | 依赖 |
|------|--------|------------------|------|
| 18:00 | 数据就绪Gate | `scheduler.adapters.run_data_gate` | 无 (轮询) |
| 18:30 | 因子计算 | `scheduler.adapters.run_factor_calculation` | gate |
| 18:30 | 恐慌指数(盘后) | `fetch_fear_index` | 无 |
| 19:30 | 指标计算 | `scheduler.adapters.run_indicator_calculation` | 因子 |
| 19:35 | 资金流向增量 | `fetch_moneyflow_daily` | 无 |
| 19:40 | 概念板块同步 | `sync_concept_board` | 无 |
| 19:50 | 新闻情感分析 | `fetch_news_sentiment` | 无 |
| 20:10 | 预设策略 | `run_preset_strategies_daily` | 指标 |
| 20:15 | 融资融券增量 | `fetch_margin_daily` | 无 |
| 20:20 | 事件信号检测 | `fetch_event_signals` | 新闻 |
| 20:30 | Polymarket | `fetch_polymarket` | 无 |
| 20:40 | 主题池评分 | `scheduler.adapters.run_theme_pool_score` | 概念板块 + 指标 |
| 20:45 | 北向持仓增量 | `fetch_north_holding_daily` | 无 |
| 20:50 | 候选池监控 | `monitor_candidate_pool` | 指标 |
| 21:00 | 看板信号计算 | `compute_dashboard` | 因子 + 指标 |
| 21:05 | 申万行业估值 | `calc_sw_valuation` | 无 |

### 晚间收尾

| 时间 | 任务名 | Celery task name | 说明 |
|------|--------|------------------|------|
| 21:30 | 数据健康日报 | `push_daily_health_report` | 推送到飞书 |
| 23:00 | 精选观点日报 | `run_nightly_digest` | wechat2rss导出+LLM摘要+飞书 |

---

## 总任务数

整合前: 20 个 Celery Beat 任务 (5个引用缺失函数)
整合后: **35 个** Celery Beat 任务, 全部有对应实现

---

## 涉及文件

| 文件 | 改动 |
|------|------|
| `scheduler/adapters.py` | 新增 5 个 adapter 函数 |
| `api/tasks/data_pipeline_tasks.py` | 新建: 12 个 Celery task wrapper |
| `api/tasks/celery_app.py` | 重写 beat_schedule, 35 个任务 |

---

## 注意事项

1. **依赖是时间间隔保证的**: Celery Beat 不支持 DAG 依赖, 依靠任务间留足时间间隔。如果上游超时, 下游仍会按时启动。data_gate 有 60min 超时, 超时会抛 TimeoutError, 但不会阻止 18:30 因子计算启动。
2. **YAML Scheduler 保留**: YAML 任务定义和 `scheduler/` 模块代码保留不删, 可用于本地 dry-run 测试 (`python -m scheduler run all --dry-run`)。
3. **手动任务未纳入**: `06_maintenance.yaml` 中的手动任务 (行业更新/财报拉取/因子验证/因子回填) 保持手动触发, 不加入 beat_schedule。
4. **宏观数据**: 保持每小时拉取, Redis 锁 (55min 过期) 防止重叠运行。
