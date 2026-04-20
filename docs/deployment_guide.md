# myTrader 生产环境部署指南

本文档介绍 myTrader 项目的实际生产环境架构和日常更新流程。
服务器: CentOS 7, 域名: mytrader.cc

## 当前部署架构

```
Internet
    |
    v
[Nginx :80/:443] (Docker: mytrader-nginx)
    |
    +---> /api/* --> [FastAPI :8000] (Docker: mytrader-api)
    |
    +---> /      --> [Next.js :3000] (Docker: mytrader-web)
    |
    +---> [Redis :6379] (Docker: mytrader-redis, 绑定 127.0.0.1:6379)

宿主机进程 (非 Docker):
    - uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
    - celery -A api.tasks.celery_app worker -l info -c 1 -Q celery,default
    - celery -A api.tasks.celery_app beat -l info
```

**关键说明**:
- API (uvicorn) 和 Celery 在宿主机直接运行，非 Docker 容器
- Next.js 前端通过 Docker 容器运行 (node:20-alpine)，因为 CentOS 7 无法运行 Node 20
- Redis 通过 Docker 运行，绑定 127.0.0.1:6379 (宿主机和 Docker 容器都通过 127.0.0.1 访问)
- MySQL 运行在宿主机，Docker 内通过 172.17.0.1 (docker0 网桥) 访问

## 环境变量 (.env) 关键配置

```bash
# 数据库 - Docker 容器内通过 docker0 网桥访问宿主机 MySQL
LOCAL_DB_HOST=172.17.0.1
ONLINE_DB_HOST=172.17.0.1
LOCAL_DB_USER=mytrader_user
LOCAL_DB_PASSWORD=<password>
LOCAL_DB_NAME=trade

# Redis - 宿主机和 Docker 都用 127.0.0.1 (Redis 绑定了 127.0.0.1:6379)
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=<password>
REDIS_DB=0

# Celery - URL 中包含密码
CELERY_BROKER_URL=redis://:<password>@127.0.0.1:6379/1
CELERY_RESULT_BACKEND=redis://:<password>@127.0.0.1:6379/2
```

**踩坑记录**:
- `REDIS_HOST` 不能用 Docker 内部网络名 (如 `mytrader-redis`)，因为 uvicorn/celery 在宿主机运行
- Celery broker/backend URL 必须包含密码，否则 `apply_async` 会报 `Retry limit exceeded`
- `api/tasks/celery_app.py` 通过 `settings.redis_host`/`settings.redis_password` 构建 URL，不是直接读 `CELERY_BROKER_URL` 环境变量 (代码中会先 del 掉)

---

## 日常更新流程

### 只改了后端 Python 代码 (API/Celery)

```bash
ssh aliyun-ecs
cd /root/app && git pull

# 重启 API
ps aux | grep 'uvicorn api.main' | grep -v grep | awk '{print $2}' | xargs kill
nohup /usr/local/bin/python3.11 /root/.local/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2 > /dev/null 2>&1 &

# 重启 Celery worker + beat
ps aux | grep 'celery.*worker' | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null
ps aux | grep 'celery.*beat' | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null
nohup /usr/local/bin/python3.11 -m celery -A api.tasks.celery_app worker -l info -c 1 -Q celery,default > /dev/null 2>&1 &
nohup /usr/local/bin/python3.11 -m celery -A api.tasks.celery_app beat -l info --scheduler celery.beat.PersistentScheduler > /dev/null 2>&1 &

# 验证
sleep 3 && curl -s http://127.0.0.1:8000/health
```

### 只改了前端代码 (web/)

CentOS 7 的 glibc 版本太低，无法运行 Node 20。Next.js 16 要求 Node >= 20.9.0，所以必须在本地或 Docker 中构建。

**方式 1: 本地构建 + rsync 产物 (推荐，较快)**

```bash
# 本地构建
cd web && npm run build

# 同步 .next 到服务器
rsync -avz --delete .next/ aliyun-ecs:/root/app/web/.next/

# 服务器上 Docker 重建 runner 阶段 (不需要完整 build)
ssh aliyun-ecs "cd /root/app/web && docker build -t mytrader-web . && docker rm -f mytrader-web && docker run -d --name mytrader-web --restart unless-stopped -p 127.0.0.1:3000:3000 -e NEXT_PUBLIC_API_BASE_URL= mytrader-web"
```

**方式 2: 服务器上 Docker 完整构建 (较慢但自包含)**

```bash
ssh aliyun-ecs
cd /root/app && git pull
cd web && docker build -t mytrader-web .
docker rm -f mytrader-web
docker run -d --name mytrader-web --restart unless-stopped -p 127.0.0.1:3000:3000 -e NEXT_PUBLIC_API_BASE_URL= mytrader-web
```

### 前后端都改了

先按后端流程重启 API/Celery，再按前端流程重建 Docker 镜像。

---

## 服务状态检查

```bash
# Docker 容器
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'

# 宿主机进程
ps aux | grep -E 'uvicorn|celery' | grep -v grep

# API 健康检查
curl -s http://127.0.0.1:8000/health | python3 -m json.tool

# 前端检查
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/

# Redis 连通性
python3 -c "import redis; r=redis.Redis(host='127.0.0.1',port=6379,password='<password>'); print(r.ping())"
```

---

## 日志位置

| 日志 | 路径 |
|------|------|
| API 应用日志 | `/root/app/logs/app.log` |
| API 错误日志 | `/root/app/logs/error.log` |
| API 访问日志 | `/root/app/logs/access.log` |
| Nginx 访问日志 | `/root/app/nginx_logs/access.log` |
| Nginx 错误日志 | `/root/app/nginx_logs/error.log` |
| Next.js 日志 | `docker logs mytrader-web` |

---

## 故障排查

### API 500 错误

```bash
# 查看最新错误
tail -50 /root/app/logs/error.log
tail -50 /root/app/logs/app.log
```

### Celery 任务提交失败 (Retry limit exceeded)

根因通常是 Redis 连接问题:
1. 检查 `.env` 中 `REDIS_HOST=127.0.0.1` (不是 `mytrader-redis`)
2. 检查 `CELERY_BROKER_URL` 和 `CELERY_RESULT_BACKEND` 包含密码
3. 检查 `api/tasks/celery_app.py` 是否通过 `settings.redis_password` 构建 URL
4. 重启 Celery worker (旧进程可能缓存了错误的 Redis 配置)

### 前端页面空白

```bash
# 检查容器状态
docker ps | grep mytrader-web

# 查看容器日志
docker logs --tail 50 mytrader-web

# 常见原因: Node 版本不兼容 (需要 >= 20.9.0)
# 解决: 用 Docker 构建，不要在宿主机直接 npm run build
```

### Nginx 502 Bad Gateway

```bash
# 检查上游服务是否运行
curl -s http://127.0.0.1:8000/health   # API
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/  # 前端

# 检查 nginx 配置中的 upstream 地址
docker exec mytrader-nginx cat /etc/nginx/conf.d/default.conf
```

### GitHub Actions 自动部署

push 到 main 分支会触发自动部署 (`.github/workflows/deploy.yml`)，但当前部署脚本只处理 API 部分和 git pull。前端仍需手动 Docker 构建。

---

## Docker 容器管理

```bash
# 查看所有容器
docker ps -a

# 重启 Nginx
docker restart mytrader-nginx

# 重启 Redis
docker restart mytrader-redis

# 重建前端镜像
cd /root/app/web && docker build -t mytrader-web .
docker rm -f mytrader-web
docker run -d --name mytrader-web --restart unless-stopped -p 127.0.0.1:3000:3000 -e NEXT_PUBLIC_API_BASE_URL= mytrader-web

# 查看 Nginx 配置
docker exec mytrader-nginx cat /etc/nginx/conf.d/default.conf

# 重新加载 Nginx 配置 (不需要重建容器)
docker exec mytrader-nginx nginx -s reload
```
