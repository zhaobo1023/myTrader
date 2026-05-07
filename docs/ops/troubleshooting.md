# myTrader 线上部署故障排查指南

本文档记录线上服务器开发、测试、调试过程中遇到的问题及解决方案。

## 目录

1. [Docker 相关问题](#docker-相关问题)
2. [API 服务问题](#api-服务问题)
3. [前端部署问题](#前端部署问题)
4. [数据库问题](#数据库问题)
5. [第三方 API 问题](#第三方-api-问题)

---

## Docker 相关问题

### 问题 1: uvicorn 可执行文件找不到

**错误信息:**
```
exec: "uvicorn": executable file not found in $PATH: unknown
```

**原因分析:**
`restart_v2.sh` 脚本中使用了 `-v /root/app/.pip_cache:/root/.local` 卷挂载，这会覆盖 Docker 镜像中已安装的 Python 依赖（包括 uvicorn），导致容器启动时找不到 uvicorn 可执行文件。

**解决方案:**
移除 `.pip_cache` 卷挂载，因为依赖已经打包在 Docker 镜像中。

```bash
# 错误的配置
docker run -d \
  -v /root/app/.pip_cache:/root/.local \
  ...

# 正确的配置（移除该行）
docker run -d \
  -v /root/app:/app \
  -v /root/app/output:/app/output \
  ...
```

**修改文件:**
- `/root/app/restart_v2.sh` - 删除第 47 行的 `-v /root/app/.pip_cache:/root/.local`

---

### 问题 2: 容器内网络连接 host.docker.internal 失败

**错误信息:**
```
Can't connect to MySQL server on 'host.docker.internal' ([Errno -2] Name or service not found)
```

**原因分析:**
1. `host.docker.internal` 是 Docker Desktop 提供的特殊 DNS 名称
2. 在 Linux 服务器上需要使用 `--add-host=host.docker.internal:host-gateway` 参数
3. 宿主机直接运行 Python 脚本时不支持此 DNS 名称

**解决方案:**

在 Docker 容器中：
```bash
docker run -d \
  --add-host=host.docker.internal:host-gateway \
  ...
```

在宿主机上直接运行时，使用 `localhost`：
```python
# 宿主机脚本
DB_CONFIG = {
    'host': 'localhost',  # 而非 host.docker.internal
    ...
}
```

---

## API 服务问题

### 问题 3: RAG_API_KEY 未配置导致 ValueError

**错误信息:**
```
ValueError: RAG_API_KEY is not set in .env
```

**原因分析:**
一页纸生成和综合分析功能使用 DashScope API（阿里云通义千问），需要配置 API Key。

**解决方案:**

1. 获取 DashScope API Key:
   - 访问 https://bailian.console.aliyun.com/
   - 或 https://dashscope.console.aliyun.com/apiKey
   - 创建新的 API-KEY

2. 配置到 `.env` 文件:
   ```bash
   RAG_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

3. 配置到 Docker 容器环境变量:
   ```bash
   docker run -d \
     -e RAG_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
     ...
   ```

4. 添加友好的错误提示:
   ```python
   # api/routers/analysis.py
   try:
       analyzer = OnePagerAnalyzer(db_env='online')
   except ValueError as exc:
       if 'RAG_API_KEY' in str(exc):
           yield f"data: {json.dumps({'type': 'error', 
               'message': 'RAG_API_KEY 未配置，请联系管理员配置 DashScope API Key'})}\n\n"
           return
   ```

---

### 问题 4: JSON 解析错误 "Unexpected token 'I', "Internal S""

**错误信息:**
```
SyntaxError: Unexpected token 'I', "Internal S"... is not valid JSON
```

**原因分析:**
API 返回了非 JSON 格式的错误响应（如 "Internal Server Error"），前端尝试解析 JSON 时失败。

**排查步骤:**

1. 检查 API 容器日志:
   ```bash
   docker logs mytrader-api --tail 50
   ```

2. 检查 API 健康状态:
   ```bash
   curl http://localhost:8000/health
   ```

3. 常见原因:
   - 后端抛出未捕获的异常
   - 数据库连接失败
   - 缺少必需的环境变量

**解决方案:**
确保后端正确处理异常并返回 JSON 格式的错误响应：
```python
try:
    result = await some_operation()
except Exception as exc:
    logger.error(f"Operation failed: {exc}", exc_info=True)
    raise HTTPException(status_code=500, detail=str(exc))
```

---

## 前端部署问题

### 问题 5: 搜索接口使用 localhost 而非线上地址

**错误信息:**
```
前端请求 http://localhost:8000/api/market/search 而非 http://123.56.3.1:8000
```

**原因分析:**
前端代码中使用了不一致的环境变量名称：
- `NEXT_PUBLIC_API_URL` (部分页面)
- `NEXT_PUBLIC_API_BASE_URL` (其他页面)

Docker 容器只设置了 `NEXT_PUBLIC_API_BASE_URL`，导致使用 `NEXT_PUBLIC_API_URL` 的页面回退到默认值 `localhost:8000`。

**解决方案:**

统一使用 `NEXT_PUBLIC_API_BASE_URL`：

```typescript
// 修改前
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// 修改后
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
```

**修改文件:**
- `web/src/app/rag/page.tsx`
- `web/src/app/analysis/page.tsx`
- `web/src/app/stock/page.tsx`

---

### 问题 6: Next.js 构建失败 - Node.js 版本过低

**错误信息:**
```
You are using Node.js 18.20.8. For Next.js, Node.js version ">=20.9.0" is required.
```

**原因分析:**
服务器上的 Node.js 版本是 18.x，而 Next.js 16 需要 Node.js 20+。

**解决方案:**

使用 Docker 构建（推荐）：
```bash
docker build --no-cache -t mytrader-web:latest -f Dockerfile .
```

Dockerfile 使用 `node:20-alpine` 基础镜像，确保了正确的 Node.js 版本。

---

### 问题 7: 前端代码修改后线上不生效

**原因分析:**
前端是静态构建产物，需要重新构建 Docker 镜像才能生效。

**解决方案:**

```bash
# 1. 修改代码后提交
git add web/
git commit -m "fix: ..."
git push

# 2. 在服务器上拉取最新代码
cd /root/app && git pull

# 3. 重新构建前端镜像
docker build -t mytrader-web:latest -f Dockerfile .

# 4. 重启容器
docker stop mytrader-web && docker rm mytrader-web
docker run -d --name mytrader-web ...
```

**或者使用 restart_v2.sh 脚本（需要先手动构建镜像）**

---

## 数据库问题

### 问题 8: 数据库锁超时

**错误信息:**
```
SQLSTATE[HY000]: General error: 1205 Lock wait timeout exceeded
```

**原因分析:**
长时间运行的查询或事务持有锁，其他请求等待超时。

**解决方案:**

1. 检查是否有长时间运行的查询:
   ```sql
   SHOW PROCESSLIST;
   ```

2. 使用 SQL 方式检测超时而非 Python 异常:
   ```python
   sql = """
       UPDATE trade_preset_strategy_run
       SET status = 'timeout'
       WHERE id = %s
         AND status = 'running'
         AND TIMESTAMPDIFF(HOUR, triggered_at, NOW()) > 2
   """
   affected = execute_update(sql, (run_id,))
   if affected > 0:
       logger.info(f"Run {run_id} marked as timeout")
   ```

---

### 问题 9: 策略日期使用触发日期而非数据日期

**问题描述:**
策略使用 `date.today()` 作为日期，导致在非交易日或盘后运行时日期不匹配。

**解决方案:**

从数据库查询最新交易日期:
```python
def trigger_strategy_run(strategy_key: str, env: str = 'online') -> dict:
    # 获取最新交易日期
    trade_date_rows = execute_query(
        "SELECT MAX(trade_date) AS max_date FROM trade_stock_daily WHERE stock_code LIKE '%.SZ' OR stock_code LIKE '%.SH'",
        env=env,
    )
    trade_date_str = str(trade_date_rows[0]['max_date'])

    # 使用交易日期而非触发日期
    execute_update(
        "INSERT INTO trade_preset_strategy_run (run_date, strategy_key, ...) VALUES (%s, %s, ...)",
        (trade_date_str, strategy_key, ...)
    )
```

---

## Celery 异步任务问题

### 问题 10: Celery Worker 被 OOM Killer 杀死

**错误信息:**
```
OOM killer killed process celery
```

**原因分析:**
批量处理数据时内存占用过高，Linux OOM Killer 终止进程。

**解决方案:**

1. 分批处理（每批 500 只股票）:
   ```python
   BATCH_SIZE = 500

   all_stock_codes = get_all_stock_codes()
   for i in range(0, len(all_stock_codes), BATCH_SIZE):
       batch = all_stock_codes[i:i + BATCH_SIZE]
       process_batch(batch)
       gc.collect()  # 强制垃圾回收
   ```

2. 降低 Worker 并发:
   ```bash
   celery -A api.tasks.celery_app worker --concurrency=1
   ```

3. 增加服务器内存或使用 swap

---

### 问题 11: Celery Beat 定时任务不执行

**错误信息:**
```
Received unregistered task of type 'xxx'
```

**原因分析:**
Celery Beat 配置的任务名称与实际任务注册名称不匹配。

**解决方案:**

确保任务名称一致:
```python
# celery_app.py
@celery_app.task(name='tasks.run_preset_strategy')
def run_preset_strategy(...):
    ...

# beat_schedule 配置
celery_app.conf.beat_schedule = {
    'daily-preset-strategies': {
        'task': 'tasks.run_preset_strategy',  # 与 @celery_app.task(name=...) 中的名称一致
        'schedule': crontab(hour=19, minute=30, day_of_week='1-5'),
    },
}
```

---

## 第三方 API 问题

### 问题 12: DashScope API 调用失败

**错误信息:**
```
dashscope.common.error.RequestError: Error code: 401, The API Key is invalid or expired
```

**原因分析:**
1. API Key 错误或已过期
2. 网络代理问题（macOS 系统代理导致 SSL 握手失败）

**解决方案:**

1. 验证 API Key:
   ```python
   import dashscope
   dashscope.api_key = "sk-xxxxxxxx"
   # 测试调用
   ```

2. 设置 NO_PROXY 绕过系统代理:
   ```python
   import os
   os.environ["NO_PROXY"] = "dashscope.aliyuncs.com"
   ```

3. 检查 API Key 配额是否耗尽

---

## 开发工作流建议

### 代码修改到上线流程

1. **本地修改代码**
   ```bash
   vim /root/app/api/routers/xxx.py
   ```

2. **提交到 Git**
   ```bash
   cd /root/app
   git add .
   git commit -m "fix: ..."
   git push origin main
   ```

3. **重启相关服务**
   ```bash
   # API 修改
   docker restart mytrader-api

   # 前端修改（需要重新构建）
   docker build -t mytrader-web:latest -f Dockerfile .
   docker stop mytrader-web && docker rm mytrader-web
   # 运行 docker run 命令...
   ```

4. **验证**
   ```bash
   curl http://localhost:8000/health
   docker logs mytrader-api --tail 20
   ```

### 常用调试命令

```bash
# 查看所有容器状态
docker ps

# 查看容器日志
docker logs mytrader-api --tail 50 -f

# 进入容器调试
docker exec -it mytrader-api bash

# 查看 API 环境变量
docker exec mytrader-api env | grep RAG

# 测试数据库连接
docker exec mytrader-api python -c "from config.db import test_connection; print(test_connection())"

# 重启所有服务
bash /root/app/restart_v2.sh
```

---

## 附录

### 相关文件清单

| 文件 | 用途 |
|------|------|
| `/root/app/restart_v2.sh` | 服务重启脚本 |
| `/root/app/Dockerfile` | API 服务镜像构建 |
| `/root/app/web/Dockerfile` | 前端镜像构建 |
| `/root/app/.env` | 环境变量配置 |
| `/root/app/docker-compose.yml` | Docker 编排配置 |

### 环境变量参考

```bash
# 数据库
DB_ENV=online
ONLINE_DB_HOST=host.docker.internal
ONLINE_DB_USER=root
ONLINE_DB_PASSWORD=xxx
ONLINE_DB_NAME=trade

# Redis
REDIS_HOST=host.docker.internal
REDIS_PORT=6379

# RAG (DashScope)
RAG_API_KEY=sk-xxxxxxxx

# 前端
NEXT_PUBLIC_API_BASE_URL=http://123.56.3.1:8000
```

---

**文档维护:** 请在遇到新问题时及时更新本文档。
**更新日期:** 2026-04-14
