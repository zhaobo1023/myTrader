# myTrader 定时任务调度配置

本文档描述项目中所有定时任务的配置和执行时间安排。

## 调度系统

项目使用 **Celery Beat** 进行任务调度，配置位于 `api/tasks/celery_app.py`。

## 执行时间总览

### 收盘后任务流水线（交易日 15:00-16:00 收盘）

| 时间 | 任务 | 说明 |
|------|------|------|
| 16:30 | watchlist_scan | 监控自选股技术面 |
| 17:30 | macro_fetch | 宏观数据拉取 |
| 18:00 | data_gate | 等待行情数据就绪 |
| 18:30 | factor_calc | 因子计算 |
| 19:00 | indicator_calc | 技术指标 & RPS |
| **19:30** | **preset_strategies** | **预设策略执行（动量反转+微盘股）** |
| 20:00 | theme_pool_score | 主题池评分 |

### 凌晨维护任务

| 时间 | 任务 | 说明 |
|------|------|------|
| 00:05 | expire_subscriptions | 订阅过期检查 |
| 01:00 | data_integrity_check | 数据完整性检查 |
| 02:00 | tech_scan | 技术面持仓扫描 |
| 03:00 | log_bias | 行业ETF对数乖离率 |

### 实时任务

| 频率 | 任务 | 说明 |
|------|------|------|
| 每小时 | fetch_fear_index | 恐慌指数更新 |

## Celery 配置

### 启动 Beat 调度器

```bash
# 启动 Celery Beat (生产环境)
docker run -d \
  --name app-celery-beat \
  --network app_mytrader-network \
  -v /root/app:/app \
  -e REDIS_HOST=host.docker.internal \
  -e REDIS_PORT=6379 \
  --add-host=host.docker.internal:host-gateway \
  --restart unless-stopped \
  app-api:latest \
  celery -A api.tasks.celery_app beat -l info
```

### 启动 Worker

```bash
# 启动 Celery Worker
docker run -d \
  --name app-celery-worker \
  --network app_mytrader-network \
  -v /root/app:/app \
  -v /root/app/output:/app/output \
  -e REDIS_HOST=host.docker.internal \
  -e REDIS_PORT=6379 \
  --add-host=host.docker.internal:host-gateway \
  --restart unless-stopped \
  --memory=2g \
  app-api:latest \
  celery -A api.tasks.celery_app worker -l info -c 1 -Q celery,default
```

## 任务依赖关系

```
数据准备阶段 (17:30-18:30):
  fetch_macro_data (17:30)
       ↓
  _gate_daily_price (18:00)
       ↓
  calc_*_factors (18:30) [并行执行]

指标计算阶段 (19:00):
  calc_rps (19:00)
  calc_svd_monitor (19:00)
  calc_technical_indicator (19:00)

策略执行阶段 (19:30):
  run_preset_strategies_daily (19:30)
    ├─ momentum_reversal
    └─ microcap_pure_mv

其他任务 (20:00+):
  theme_pool_score (20:00)
  ...
```

## 手动触发任务

如果需要手动触发策略执行：

```bash
# 触发动量反转策略
curl -X POST "http://localhost:8000/api/strategy/preset/momentum_reversal/trigger"

# 触发微盘股策略
curl -X POST "http://localhost:8000/api/strategy/preset/microcap_pure_mv/trigger"

# 强制重新执行（即使已完成）
curl -X POST "http://localhost:8000/api/strategy/preset/momentum_reversal/trigger?force=true"
```

## 监控和日志

### 查看 Beat 日志

```bash
docker logs app-celery-beat -f
```

### 查看 Worker 日志

```bash
docker logs app-celery-worker -f
```

### 查看活跃任务

```bash
docker exec app-celery-worker celery -A api.tasks.celery_app inspect active
```

### 查看已注册任务

```bash
docker exec app-celery-worker celery -A api.tasks.celery_app inspect registered
```

## 任务执行状态查询

### 查询最新策略运行记录

```bash
curl "http://localhost:8000/api/strategy/preset"
```

### 查询策略运行详情

```bash
curl "http://localhost:8000/api/strategy/preset/momentum_reversal/runs/22"
```

## 时间窗口设计原则

1. **收盘后 (16:30-18:00)**: 数据准备阶段，轻量级任务
2. **晚上 (18:00-20:00)**: 重计算任务（因子、指标、策略）
3. **凌晨 (00:00-04:00)**: 维护任务（订阅、数据检查、扫描）
4. **实时**: 每小时执行一次的轻量级任务

## 注意事项

1. **交易日判断**: 所有任务配置了 `day_of_week='1-5'`，只在周一到周五执行
2. **数据就绪**: 策略执行依赖前面的数据准备任务完成
3. **内存限制**: 策略任务使用分批处理，每批500只股票
4. **错误重试**: 配置了自动重试，失败后会按指数退避重试
5. **超时处理**: 任务超时后会标记为 failed，可以手动重新触发

## 故障处理

### 任务卡住

如果任务状态长时间为 `running`：

```bash
# 1. 检查 Celery worker 状态
docker exec app-celery-worker celery -A api.tasks.celery_app inspect active

# 2. 查看最新运行记录
docker exec mytrader-api python -c "
from config.db import execute_query
result = execute_query('SELECT * FROM trade_preset_strategy_run ORDER BY id DESC LIMIT 5')
for r in result:
    print(r)
"

# 3. 手动标记为失败
docker exec mytrader-api python -c "
from config.db import execute_update
execute_update('UPDATE trade_preset_strategy_run SET status=\"failed\" WHERE id = XX')
"

# 4. 重新触发
curl -X POST "http://localhost:8000/api/strategy/preset/momentum_reversal/trigger?force=true"
```

### Worker 重启

```bash
# 重启 Worker
docker restart app-celery-worker

# 重启 Beat
docker restart app-celery-beat
```

## 未来优化

1. **动态调度**: 根据市场交易时间动态调整执行时间
2. **智能跳过**: 节假日自动跳过任务执行
3. **负载均衡**: 增加Worker并发数处理更大规模
4. **结果通知**: 任务完成后发送邮件/飞书通知
