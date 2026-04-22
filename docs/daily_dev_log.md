# myTrader 每日开发日志

> 格式规范：每条日志必须包含【根因】【模式】【坑】三个字段，供 Claude 日后调取复用。
> 清理机制：每月末将当月条目归档至 docs/dev_log_archive/YYYY-MM.md，主文件只保留当月。
> 归档记录：docs/dev_log_archive/2026-04.md（2026-04-14 ~ 2026-04-19，1798行）

---

## 2026-04-20 Celery Redis 连接故障修复 + 监控体系建设

### 概要
Celery Beat/Worker 容器重启后无法连接 Redis broker，所有定时任务停摆约 8 小时。

### 根因
`celery_app.py` 中 `del os.environ['CELERY_BROKER_URL']` 意图让 Celery 使用 `settings.redis_host` 构建 URL，但 Celery CLI 在 import 前已缓存环境变量，`del` 后回退默认值 `redis://localhost:6379/1`，容器内解析为 `127.0.0.1`，而 Redis 在独立容器 `mytrader-redis`，连接永久失败。

### 修复内容

| 文件 | 变更 | 目的 |
|------|------|------|
| `api/tasks/celery_app.py` | `del` 改为 `os.environ[...] = broker_url` | 保证 Celery CLI 和 app 使用同一 broker 地址 |
| `api/tasks/celery_app.py` | 新增 `broker_connection_retry_on_startup=True`, `broker_connection_max_retries=10`, `socket_keepalive`, `retry_on_timeout` | Redis 断连后自动重连 |
| `api/tasks/celery_app.py` | 新增 `task_soft_time_limit=1800`, `task_time_limit=2400` | 全局任务超时保护 |
| `docker-compose.yml` | celery-worker 添加 healthcheck (`celery inspect ping`) | 容器 unhealthy 时自动重启 |
| `docker-compose.yml` | celery-beat 启动时 `rm -f celerybeat-schedule` + healthcheck | 清理旧调度缓存 + 健康检测 |
| `scripts/check_celery_health.sh` | 新增宿主机监控脚本 | crontab 每5分钟探测，异常推飞书（10分钟冷却） |

### 监控层级（修复后）
```
L1: Docker healthcheck + restart: unless-stopped   -> 容器自愈
L2: 宿主机 crontab 探针 (check_celery_health.sh)   -> 飞书告警 (5min)
L3: Celery Watchdog (scheduler/watchdog.py)        -> 漏执行检测 + 自动重试
L4: Celery task on_failure + alert.py              -> 单任务失败飞书告警
```

### 补跑任务
手动补发 16 个漏掉的定时任务，通过 `celery_app.send_task()` 入队执行。
**关键操作顺序**：先确认新 worker 日志出现 `ready` -> 再入队，否则任务发到旧 worker 丢失。

### 模式（可复用）
> Celery + Docker 环境变量陷阱：不要用 `del os.environ[KEY]`，Celery CLI 启动时已缓存，del 后回退默认值。始终用 `os.environ[KEY] = value` 显式覆盖。

### 坑
- `del os.environ` 在 Celery CLI 场景下无效，且静默失败，难以排查
- 重新入队前必须确认新 worker 已 ready，否则任务路由到旧 worker 后丢失

---

<!-- 新日志从这里往上插入，格式参考上方条目 -->
<!-- 字段说明：
  ### 概要      一句话说清楚做了什么
  ### 根因      为什么出问题（bug类）或为什么要做（需求类）
  ### 修复/实现  具体改动，优先用表格
  ### 模式      可复用的经验，用 > 引用块标注，GC 时提取
  ### 坑        踩过的坑，下次避免
-->
