# ECS 快速启动参考

## 第一次部署（5 分钟版本）

```bash
# 1. 连接到 ECS
ssh ubuntu@your-ecs-ip

# 2. 进入项目
cd /opt/myTrader

# 3. 编辑环境配置
vi .env
# 填写数据库和 Redis 信息

# 4. 安装和启动
pip install -r requirements.txt
cd web && npm install && npm run build && cd ..
alembic upgrade head
sudo systemctl start mytrader-redis mytrader-api mytrader-web

# 5. 验证
curl http://localhost:8000/health
```

---

## 日常部署（3 种方式）

### 方式 A: Git Push (自动部署，推荐)

```bash
# 本地执行
git commit -am "your changes"
git push origin main

# GitHub Actions 自动触发部署（需配置 Secrets）
```

**需要配置的 GitHub Secrets：**
- `ECS_HOST`: 你的 ECS IP 地址
- `ECS_USER`: SSH 用户名（通常 ubuntu）
- `ECS_SSH_KEY`: SSH 私钥内容

### 方式 B: SSH 手动部署

```bash
# 远程执行部署脚本
ssh ubuntu@your-ecs-ip "cd /opt/myTrader && sudo ./scripts/deploy.sh"

# 查看部署日志
ssh ubuntu@your-ecs-ip "sudo tail -f /var/log/mytrader/deploy.log"
```

### 方式 C: 直接远程 Git Pull

```bash
ssh ubuntu@your-ecs-ip << 'EOF'
cd /opt/myTrader
git pull origin main
pip install -q -r requirements.txt
sudo systemctl restart mytrader-api mytrader-web
curl http://localhost:8000/health
EOF
```

---

## 常用命令速查

### 服务管理

```bash
# 查看状态
sudo systemctl status mytrader-api         # API 状态
sudo systemctl status mytrader-web         # 前端状态
sudo systemctl status mytrader-redis       # Redis 状态

# 重启
sudo systemctl restart mytrader-api
sudo systemctl restart mytrader-web

# 停止/启动
sudo systemctl stop mytrader-api
sudo systemctl start mytrader-api
```

### 日志查看

```bash
# 实时日志（最后 100 行 + 持续）
sudo journalctl -u mytrader-api -n 100 -f

# 错误日志
sudo journalctl -u mytrader-api -p err

# Nginx 日志
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 健康检查

```bash
# API
curl http://localhost:8000/health

# 通过 Nginx
curl http://localhost/health

# 前端
curl http://localhost/
```

### 配置修改

```bash
# 编辑环境变量
vi /opt/myTrader/.env
sudo systemctl restart mytrader-api

# 编辑 Nginx
sudo vi /etc/nginx/conf.d/mytrader.conf
sudo nginx -t && sudo systemctl restart nginx

# 查看 systemd 服务
sudo systemctl cat mytrader-api
```

---

## 故障速查

| 问题 | 排查命令 |
|------|--------|
| API 无响应 | `sudo systemctl status mytrader-api` |
| 数据库连接失败 | `python -c "from config.db import get_connection; print(get_connection())"` |
| Nginx 502 Bad Gateway | `sudo tail -f /var/log/nginx/error.log` |
| 前端 404 | `sudo systemctl status mytrader-web` |
| 端口被占用 | `sudo lsof -i :8000` (API) / `:3000` (Web) |

---

## 端口参考

| 服务 | 端口 | 访问方式 |
|------|------|--------|
| API (直连) | 8000 | `http://localhost:8000` |
| 前端 (直连) | 3000 | `http://localhost:3000` |
| Nginx | 80 | `http://localhost` |
| Redis | 6379 | 内部通讯 |

---

## 目录结构

```
/opt/myTrader/
├── .env                          # 环境配置 (需手动创建)
├── api/                          # API 源码
├── web/                          # 前端源码
├── scripts/
│   ├── deploy.sh                 # 部署脚本
│   ├── mytrader-api.service      # API systemd 配置
│   ├── mytrader-web.service      # 前端 systemd 配置
│   └── mytrader-redis.service    # Redis systemd 配置
├── nginx.conf                    # Nginx 配置模板
└── docs/
    ├── DEPLOYMENT_ECS.md         # 完整部署指南
    └── QUICK_START_ECS.md        # 本文件
```

---

## 时间线

1. **初次部署** (30 分钟):
   - 安装依赖
   - 配置环境变量
   - 数据库迁移
   - 启动服务

2. **日常更新** (2-3 分钟):
   - Git push → GitHub Actions 自动部署
   - 或 SSH 执行 deploy.sh

3. **故障恢复** (5-10 分钟):
   - 查看日志
   - 回滚到上一个版本
   - 重新启动

