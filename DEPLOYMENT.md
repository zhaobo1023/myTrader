# myTrader 线上部署说明

## 部署目录结构

```
服务器: 123.56.3.1
SSH 别名: aliyun-ecs (见 ~/.ssh/config)
```

### 两个代码目录说明

| 目录 | 用途 | 说明 |
|------|------|------|
| `/root/app` | API + Celery 代码目录 | 卷挂载到容器 /app，git pull 后直接生效 |
| `/app/myTrader` | 前端代码目录 | 用于构建 mytrader-web 镜像，git pull 后需重新 build |

两个目录都指向同一个 GitHub 仓库，均需执行 `git pull`。

### 目录映射（容器卷挂载）

| 宿主机路径 | 容器内路径 | 说明 |
|-----------|-----------|------|
| `/root/app` | `/app` | API 代码目录（卷挂载，改动立即生效） |
| `/root/app/output` | `/app/output` | 输出文件目录 |
| `/root/app/.pip_cache` | `/root/.local` | Python 依赖缓存 |
| `/root/app/nginx.conf` | `/etc/nginx/conf.d/default.conf` | Nginx 配置 |
| `/root/app/nginx_logs` | `/var/log/nginx` | Nginx 日志 |

### 容器端口映射

| 容器名 | 内部端口 | 宿主机绑定 | 外部访问 |
|--------|---------|-----------|---------|
| mytrader-api | 8000 | 127.0.0.1:8000 | 通过 Nginx 反代 |
| mytrader-web | 3000 | 127.0.0.1:3000 | 通过 Nginx 反代 |
| mytrader-nginx-new | 80 | 0.0.0.0:80 | http://123.56.3.1 |

## 重启脚本

### restart_v2.sh (推荐，用于全量重启)
```bash
bash /root/app/restart_v2.sh
```
注意：此脚本会重建并替换 API 和 Web 容器，适合全量重启场景。

## 常用运维命令

### 查看状态
```bash
docker ps | grep mytrader
docker logs -f mytrader-api
docker logs -f mytrader-web
docker logs -f mytrader-nginx-new
```

### 代码更新 - 仅后端 Python 改动
```bash
# API 使用卷挂载，git pull 后重启容器即可
ssh aliyun-ecs "cd /root/app && git pull origin main && docker restart mytrader-api"
```

### 代码更新 - 前端改动（需重新 build 镜像）
```bash
# 1. 拉取最新代码到前端目录
ssh aliyun-ecs "cd /app/myTrader && git pull origin main"

# 2. 重新构建镜像（NEXT_PUBLIC_API_BASE_URL 在 build 时静态嵌入，必须在此传入）
ssh aliyun-ecs "cd /app/myTrader/web && \
  NEXT_PUBLIC_API_BASE_URL=http://123.56.3.1 docker build \
  --build-arg NEXT_PUBLIC_API_BASE_URL=http://123.56.3.1 \
  -t mytrader-web:latest ."

# 3. 替换运行中的容器
ssh aliyun-ecs "docker stop mytrader-web && docker rm mytrader-web && \
  docker run -d \
    --name mytrader-web \
    --network app_mytrader-network \
    -p 127.0.0.1:3000:3000 \
    -e NEXT_PUBLIC_API_BASE_URL=http://123.56.3.1 \
    --restart unless-stopped \
    mytrader-web:latest"
```

> 注意：`NEXT_PUBLIC_*` 变量在 Next.js build 时静态嵌入 JS bundle，运行时改环境变量无效，必须重新 build 镜像。

### 进入容器调试
```bash
# 进入 API 容器
docker exec -it mytrader-api bash

# 在容器内执行 Python
docker exec mytrader-api python -c "import pandas; print(pandas.__version__)"

# 在容器内安装依赖
docker exec mytrader-api pip install pyarrow -i https://mirrors.aliyun.com/pypi/simple/ --user
```

### 数据库操作
```bash
# 进入 API 容器执行迁移
docker exec -it mytrader-api alembic upgrade head

# 查看当前迁移版本
docker exec mytrader-api alembic current

# 查看迁移历史
docker exec mytrader-api alembic history
```

### 日志查看
```bash
# API 日志
docker logs mytrader-api | tail -100

# Nginx 访问日志
tail -f /root/app/nginx_logs/access.log

# Nginx 错误日志
tail -f /root/app/nginx_logs/error.log
```

## 环境变量

### 数据库配置
```bash
DB_ENV=online
ONLINE_DB_HOST=host.docker.internal
ONLINE_DB_PORT=3306
ONLINE_DB_USER=root
ONLINE_DB_PASSWORD='Hao1023@zb'
ONLINE_DB_NAME=trade
```

### Redis 配置
```bash
REDIS_HOST=host.docker.internal
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
```

### 前端配置
```bash
NEXT_PUBLIC_API_BASE_URL=http://123.56.3.1
```

## 故障排查

### API 无法访问
```bash
# 检查容器状态
docker ps | grep mytrader-api

# 检查日志
docker logs --tail 50 mytrader-api

# 检查健康端点
curl http://localhost:8000/health
```

### 前端 404
```bash
# 检查 Nginx 配置
docker exec mytrader-nginx-new cat /etc/nginx/conf.d/default.conf

# 检查 Web 容器
docker logs mytrader-web

# 测试 Web 容器直接访问
curl http://localhost:3000/
```

### 数据库连接失败
```bash
# 进入 API 容器测试数据库连接
docker exec -it mytrader-api python -c "
from config.db import test_connection
print(test_connection())
"
```

### 依赖缺失
```bash
# 安装缺失的依赖
docker exec mytrader-api pip install \
  pyarrow \
  yfinance \
  akshare \
  -i https://mirrors.aliyun.com/pypi/simple/ \
  --user
```

## 镜像重建

当需要重建镜像时（非日常使用）：
```bash
cd /root/app

# 重建 API 镜像
docker build -t app-api:latest -f Dockerfile .

# 重启服务
bash restart_v2.sh
```

## 安全注意事项

1. **敏感信息**：
   - `.env` 文件包含数据库密码
   - 不要提交到 Git 仓库

2. **端口暴露**：
   - API 和 Web 只绑定到 127.0.0.1
   - 只有 Nginx 暴露到 0.0.0.0:80

3. **日志管理**：
   - 定期清理 nginx_logs
   - 使用 logrotate 管理日志轮转

## 联系方式

管理员：zhaobo_1023@163.com
