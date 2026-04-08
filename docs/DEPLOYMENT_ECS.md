# ECS 部署指南 (systemd + Nginx)

## 一、初始化部署（首次）

### 1.1 SSH 连接到 ECS

```bash
ssh ubuntu@your-ecs-ip
```

### 1.2 准备项目目录

```bash
# 以 root 身份执行以下命令

# 创建项目目录
mkdir -p /opt/myTrader
cd /opt/myTrader

# Clone 项目（或 git pull）
git clone https://github.com/zhaobo03/myTrader.git .
# 或者如果已有项目
git pull origin main
```

### 1.3 安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 前端依赖
cd web && npm install && cd ..

# 编译前端 (生产模式)
cd web && npm run build && cd ..
```

### 1.4 配置环境变量

```bash
# 从模板创建 .env
cp .env.example .env

# 编辑配置，填写以下关键变量：
vi .env
```

```bash
# ========== 数据库配置 ==========
DB_ENV=online
ONLINE_DB_HOST=your-mysql-host
ONLINE_DB_PORT=3306
ONLINE_DB_USER=root
ONLINE_DB_PASSWORD=your-password
ONLINE_DB_NAME=trade

# ========== Redis 配置 ==========
REDIS_HOST=127.0.0.1
REDIS_PORT=6379

# ========== JWT 配置 ==========
JWT_SECRET_KEY=your-secret-key-min-32-chars-long
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ========== 日志 ==========
LOG_LEVEL=INFO

# ========== 其他 ==========
APP_VERSION=0.1.0
```

### 1.5 数据库迁移

```bash
cd /opt/myTrader

# 运行 Alembic 迁移
alembic upgrade head
```

### 1.6 安装并启用 systemd 服务

```bash
# 复制服务文件到 systemd 目录
sudo cp scripts/mytrader-api.service /etc/systemd/system/
sudo cp scripts/mytrader-web.service /etc/systemd/system/
sudo cp scripts/mytrader-redis.service /etc/systemd/system/

# 刷新 systemd daemon
sudo systemctl daemon-reload

# 设置为开机启动
sudo systemctl enable mytrader-redis
sudo systemctl enable mytrader-api
sudo systemctl enable mytrader-web

# 立即启动服务
sudo systemctl start mytrader-redis
sudo systemctl start mytrader-api
sudo systemctl start mytrader-web
```

### 1.7 配置 Nginx

```bash
# 备份原配置
sudo cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak

# 复制新配置
sudo cp /opt/myTrader/nginx.conf /etc/nginx/conf.d/mytrader.conf

# 检查 Nginx 配置语法
sudo nginx -t

# 重启 Nginx
sudo systemctl restart nginx
```

### 1.8 验证部署

```bash
# 检查服务状态
sudo systemctl status mytrader-redis
sudo systemctl status mytrader-api
sudo systemctl status mytrader-web

# 查看日志
sudo journalctl -u mytrader-api -f        # API 日志（持续）
sudo journalctl -u mytrader-web -f        # 前端日志
sudo journalctl -u mytrader-redis -f      # Redis 日志

# 健康检查
curl http://localhost:8000/health         # 直接访问 API
curl http://localhost:3000                # 直接访问前端
curl http://localhost/health              # 通过 Nginx

# 如果以上都通过，部署成功！
```

---

## 二、日常操作

### 2.1 查看日志

```bash
# 实时 API 日志（最后 50 行 + 持续输出）
sudo journalctl -u mytrader-api -n 50 -f

# 过滤错误
sudo journalctl -u mytrader-api -p err

# 查看前端日志
sudo journalctl -u mytrader-web -f

# 查看 Nginx 日志
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 2.2 服务控制

```bash
# 重启 API
sudo systemctl restart mytrader-api

# 停止前端
sudo systemctl stop mytrader-web

# 启动 Redis
sudo systemctl start mytrader-redis

# 查看所有服务状态
sudo systemctl status mytrader-*

# 禁用开机启动
sudo systemctl disable mytrader-api
```

### 2.3 一键部署（推荐）

```bash
# 本地执行：推送代码到 GitHub
git push origin main

# GitHub Actions 会自动触发部署工作流
# 或手动部署：
cd /opt/myTrader
sudo chmod +x scripts/deploy.sh
sudo ./scripts/deploy.sh
```

---

## 三、部署脚本工作流

文件：`scripts/deploy.sh`

自动执行以下步骤：

1. Git pull 最新代码
2. pip install 依赖
3. alembic 数据库迁移
4. systemctl restart API
5. systemctl restart 前端
6. 健康检查

使用方式：

```bash
# 本地推送触发（推荐）
git push origin main

# 或 SSH 手动执行
ssh ubuntu@your-ecs-ip "cd /opt/myTrader && sudo ./scripts/deploy.sh"

# 查看部署日志
sudo tail -f /var/log/mytrader/deploy.log
```

---

## 四、Nginx 配置详解

文件位置：`/etc/nginx/conf.d/mytrader.conf`

**主要配置**：

```nginx
upstream fastapi_backend {
    server 127.0.0.1:8000;    # API 后端
}

upstream nextjs_frontend {
    server 127.0.0.1:3000;    # 前端
}
```

**路由规则**：

| 请求路径 | 转发到 | 说明 |
|---------|--------|------|
| `/api/*` | fastapi_backend:8000 | API 接口 |
| `/health` | fastapi_backend:8000 | 健康检查 |
| `/` (其他) | nextjs_frontend:3000 | 前端页面 |

**SSE 支持**：

```nginx
location /api/ {
    proxy_buffering off;      # 禁用缓冲，支持流式响应
    proxy_cache off;
    chunked_transfer_encoding off;
}
```

---

## 五、故障排查

### API 无法连接

```bash
# 检查 API 服务是否运行
sudo systemctl status mytrader-api

# 查看错误日志
sudo journalctl -u mytrader-api -p err

# 手动启动 API 查看输出
cd /opt/myTrader
PYTHONPATH=. uvicorn api.main:app --host 0.0.0.0 --port 8000

# 检查数据库连接
python -c "from config.db import get_connection; print(get_connection())"

# 检查 Redis 连接
redis-cli ping
```

### Nginx 无法反代

```bash
# 检查 Nginx 配置
sudo nginx -t

# 查看 Nginx 错误日志
sudo tail -f /var/log/nginx/error.log

# 检查 upstream 服务是否在线
netstat -tlnp | grep 8000   # API
netstat -tlnp | grep 3000   # 前端
netstat -tlnp | grep 80     # Nginx
```

### 前端页面 404

```bash
# 检查前端服务
sudo systemctl status mytrader-web

# 检查 Next.js 编译是否成功
cd /opt/myTrader/web && npm run build

# 查看前端日志
sudo journalctl -u mytrader-web -f
```

---

## 六、生产环保建议

### 6.1 SSL/TLS 证书

```bash
# 使用 Certbot + Let's Encrypt
sudo apt-get install certbot python3-certbot-nginx

# 申请证书
sudo certbot certonly --nginx -d your-domain.com

# Nginx 配置 HTTPS
# 在 nginx.conf 中添加：
listen 443 ssl http2;
ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

# HTTP 重定向到 HTTPS
return 301 https://$server_name$request_uri;
```

### 6.2 监控和告警

```bash
# 监听端口和进程
watch -n 2 'sudo systemctl status mytrader-api mytrader-web'

# 或使用 htop 查看资源占用
sudo apt-get install htop
htop
```

### 6.3 日志轮转

```bash
# 编辑 /var/log/mytrader/ 下的日志轮转规则
sudo cat > /etc/logrotate.d/mytrader << 'EOF'
/var/log/mytrader/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 root root
    sharedscripts
}
EOF
```

---

## 七、回滚方案

如果部署出现问题：

```bash
# 查看 Git 历史
git log --oneline -10

# 回滚到上一个稳定版本
git reset --hard HEAD~1
./scripts/deploy.sh

# 或指定具体 commit
git checkout <commit-hash>
./scripts/deploy.sh
```

---

## 附录：完整初始化脚本

将以下内容保存为 `init-ecs.sh`，在 ECS 上执行一次：

```bash
#!/bin/bash
set -e

# 1. 基础依赖
sudo apt-get update
sudo apt-get install -y git python3.11 python3-pip nodejs npm nginx redis-server curl

# 2. 项目部署
cd /opt
sudo git clone https://github.com/zhaobo03/myTrader.git
sudo chown -R ubuntu:ubuntu myTrader
cd myTrader

# 3. Python 依赖
pip install -r requirements.txt

# 4. 前端构建
cd web && npm install && npm run build && cd ..

# 5. systemd 服务
sudo cp scripts/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mytrader-redis mytrader-api mytrader-web

# 6. Nginx
sudo cp nginx.conf /etc/nginx/conf.d/mytrader.conf
sudo nginx -t && sudo systemctl restart nginx

echo "========== 部署完成 =========="
echo "接下来需要："
echo "1. 编辑 .env 文件配置数据库和 Redis"
echo "2. 运行: alembic upgrade head"
echo "3. 启动服务: sudo systemctl start mytrader-redis mytrader-api mytrader-web"
echo "4. 访问: http://localhost"
```

执行：

```bash
chmod +x init-ecs.sh
./init-ecs.sh
```

---

## 总结

**部署方案对比**：

| 方式 | 优点 | 缺点 |
|------|------|------|
| Docker Compose | 环境隔离、易于扩展 | 需要 Docker，资源占用多 |
| systemd + Nginx | 轻量级、资源占用少、直接利用系统 | 手动配置多一些 |
| PM2 (Node.js) | 进程管理方便 | 仅适合前端 |

**推荐**：系统服务器直接用 **systemd + Nginx**，我们已为你准备好所有脚本。

---

## 常见问题

**Q: 如何添加更多 API worker？**

A: 在 `mytrader-api.service` 中修改 `--workers 4` 为所需数量。

**Q: 如何监控服务资源占用？**

A: 使用 `sudo systemctl status mytrader-api` 或 `top -p $(pgrep -f uvicorn)`

**Q: 如何实现蓝绿切换？**

A: 创建两个独立项目目录 `/opt/myTrader-blue` 和 `/opt/myTrader-green`，修改 Nginx 上游指向即可。

