# myTrader 生产环境部署指南

本文档介绍如何将 myTrader 项目部署到生产服务器，并配置域名 mytrader.cc。

## 前置条件

- 服务器: Ubuntu 20.04+ / CentOS 7+
- 域名: mytrader.cc (已解析到服务器 IP)
- Python 3.10+
- Docker & Docker Compose
- Nginx (可选，如果使用 Docker 部署则不需要)

## 部署架构

```
Internet
    |
    v
[Nginx :80/:443] (Docker)
    |
    +---> /api/* --> [FastAPI :8000] (Docker)
    |
    +---> /      --> [Next.js :3000] (本地/Docker)
    |
    +---> [Redis :6379] (Docker)
    |
    +---> [Celery Worker] (Docker)
    |
    +---> [Celery Beat] (Docker)
```

## 部署步骤

### 1. 服务器准备

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 安装 Certbot (用于 HTTPS)
sudo apt install certbot python3-certbot-nginx -y
```

### 2. 部署代码

```bash
# 克隆代码
cd /opt
sudo git clone <your-repo-url> mytrader
cd mytrader

# 复制环境配置
sudo cp .env.example .env
sudo nano .env  # 填写配置

# 关键配置项:
# DB_ENV=online
# ONLINE_DB_HOST=your_db_host
# ONLINE_DB_NAME=your_db_name
# REDIS_HOST=redis
# JWT_SECRET_KEY=your-random-secret-key
```

### 3. 配置环境变量

```bash
# 生成 JWT 密钥
openssl rand -hex 32

# 编辑 .env 文件
JWT_SECRET_KEY=生成的随机密钥
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# 数据库配置
ONLINE_DB_HOST=your_db_host
ONLINE_DB_NAME=your_db_name
ONLINE_DB_USER=your_db_user
ONLINE_DB_PASSWORD=your_db_password
```

### 4. 启动服务

```bash
# 构建并启动所有服务
sudo docker compose up -d

# 查看日志
sudo docker compose logs -f

# 检查服务状态
sudo docker compose ps
```

### 5. 配置 Nginx

Nginx 配置已经完成，主要配置：

- **域名**: mytrader.cc www.mytrader.cc
- **HTTP**: 80 端口
- **API 路由**: /api/* --> FastAPI (Docker)
- **前端路由**: / --> Next.js (需要单独配置)

#### 前端部署选项

**选项 1: Next.js 在服务器本地运行**

```bash
# 在服务器上安装 Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# 构建前端
cd /opt/mytrader/web
npm install
npm run build

# 使用 PM2 运行
sudo npm install -g pm2
pm2 start npm --name "mytrader-frontend" -- start

# 修改 nginx.conf，取消注释本地 Next.js 配置
# 注释掉 Docker 的 nextjs upstream
```

**选项 2: Next.js 使用 Docker 部署**

```bash
# 1. 创建 web/Dockerfile
cat > /opt/mytrader/web/Dockerfile << 'EOF'
FROM node:18-alpine AS base

# Install dependencies only when needed
FROM base AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

# Rebuild the source code only when needed
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# Production image, copy all the files and run next
FROM base AS runner
WORKDIR /app
ENV NODE_ENV production
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT 3000

CMD ["node", "server.js"]
EOF

# 2. 修改 next.config.js，启用 standalone 输出
# module.exports = {
#   output: 'standalone',
#   // ... 其他配置
# }

# 3. 取消 docker-compose.yml 中 nextjs 服务的注释
# 4. 重新构建
sudo docker compose up -d --build
```

### 6. 配置 DNS 解析

在你的域名服务商（如阿里云、腾讯云）配置 DNS:

| 类型 | 主机记录 | 记录值 |
|------|---------|--------|
| A | @ | 你的服务器 IP |
| A | www | 你的服务器 IP |

### 7. 配置 HTTPS (SSL 证书)

```bash
# 方式 1: 使用 Certbot (推荐)
sudo certbot --nginx -d mytrader.cc -d www.mytrader.cc

# 方式 2: 手动配置 (如果 Certbot 不可用)
# 1. 获取 SSL 证书
sudo certbot certonly --nginx -d mytrader.cc -d www.mytrader.cc

# 2. 修改 nginx.conf，取消注释 HTTPS 配置块
# 3. 重启 nginx
sudo docker compose restart nginx

# 自动续期
sudo certbot renew --dry-run
```

配置 HTTPS 后，修改 `nginx.conf`:

```nginx
# 取消注释 HTTPS 重定向
return 301 https://mytrader.cc$request_uri;

# 取消注释 HTTPS server 块
# 同时注释掉 HTTP server 块中的 location 配置
```

### 8. 数据库迁移

```bash
# 进入 API 容器
sudo docker compose exec api bash

# 运行迁移
alembic upgrade head

# 创建初始用户
python -c "
from api.core.security import get_password_hash
from api.models.user import User
from config.db import SessionLocal

db = SessionLocal()
admin = User(
    email='admin@mytrader.cc',
    hashed_password=get_password_hash('your_password'),
    tier='premium',
    role='admin',
    is_active=True
)
db.add(admin)
db.commit()
print('Admin user created')
"
```

### 9. 验证部署

```bash
# 检查服务状态
sudo docker compose ps

# 检查健康状态
curl http://localhost/health

# 检查 API
curl http://localhost/api/health

# 检查前端
curl http://localhost/

# 检查日志
sudo docker compose logs -f api
sudo docker compose logs -f nginx
```

访问:
- HTTP: http://mytrader.cc
- HTTPS: https://mytrader.cc (配置 SSL 后)

### 10. 防火墙配置

```bash
# Ubuntu/Debian
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# CentOS/RHEL
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

## 运维管理

### 日志查看

```bash
# 所有服务日志
sudo docker compose logs -f

# 特定服务日志
sudo docker compose logs -f api
sudo docker compose logs -f nginx
sudo docker compose logs -f redis

# Nginx 访问日志
sudo tail -f /var/lib/docker/volumes/mytrader_nginx_logs/_log/access.log

# Nginx 错误日志
sudo tail -f /var/lib/docker/volumes/mytrader_nginx_logs/_log/error.log
```

### 服务管理

```bash
# 重启服务
sudo docker compose restart api
sudo docker compose restart nginx

# 重新构建服务
sudo docker compose up -d --build api

# 停止所有服务
sudo docker compose down

# 停止并删除数据 (危险)
sudo docker compose down -v
```

### 数据库备份

```bash
# 创建备份脚本
cat > /opt/mytrader/scripts/backup_db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/backups/mytrader"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# 备份数据库
mysqldump -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME > $BACKUP_DIR/db_$DATE.sql

# 保留最近 7 天的备份
find $BACKUP_DIR -name "db_*.sql" -mtime +7 -delete

echo "Backup completed: db_$DATE.sql"
EOF

chmod +x /opt/mytrader/scripts/backup_db.sh

# 添加到 crontab (每天凌晨 2 点)
crontab -e
# 0 2 * * * /opt/mytrader/scripts/backup_db.sh
```

### 监控

```bash
# 安装监控工具
sudo docker run -d \
  --name prometheus \
  -p 9090:9090 \
  -v /opt/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus

# 配置 Grafana
sudo docker run -d \
  --name grafana \
  -p 3001:3000 \
  grafana/grafana
```

## 故障排查

### 常见问题

1. **Nginx 502 Bad Gateway**
   - 检查 API 服务是否运行: `sudo docker compose ps api`
   - 检查 API 日志: `sudo docker compose logs api`
   - 检查网络连接: `sudo docker network inspect mytrader_mytrader-network`

2. **数据库连接失败**
   - 检查 .env 中的数据库配置
   - 测试连接: `python -c "from config.db import test_connection; print(test_connection())"`

3. **前端页面空白**
   - 检查 Next.js 是否运行: `pm2 list` 或 `sudo docker compose ps nextjs`
   - 检查前端构建: `cd web && npm run build`

4. **HTTPS 证书过期**
   - 手动续期: `sudo certbot renew`
   - 检查自动续期: `sudo systemctl status certbot.timer`

### 性能优化

1. **启用 Gzip 压缩** (在 nginx.conf)
   ```nginx
   gzip on;
   gzip_types text/plain text/css application/json application/javascript;
   ```

2. **配置缓存头**
   ```nginx
   location ~* \.(js|css|png|jpg|jpeg|gif|ico)$ {
       expires 30d;
       add_header Cache-Control "public, immutable";
   }
   ```

3. **数据库连接池优化**
   - 调整 SQLAlchemy pool_size 和 max_overflow

## 安全建议

1. **启用防火墙**，只开放必要端口
2. **配置 HTTPS**，强制 SSL 重定向
3. **定期更新**系统和 Docker 镜像
4. **限制 API 请求频率** (已配置 rate limiting)
5. **定期备份数据库**
6. **监控日志**，设置异常报警
7. **使用强密码**和 JWT 密钥

## 扩展阅读

- [Docker Compose 文档](https://docs.docker.com/compose/)
- [Nginx 配置指南](https://nginx.org/en/docs/)
- [Certbot 使用指南](https://certbot.eff.org/docs/)
- [Next.js 部署文档](https://nextjs.org/docs/deployment)
