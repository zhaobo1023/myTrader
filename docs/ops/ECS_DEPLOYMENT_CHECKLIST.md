# ECS 部署检查清单

## 已完成 ✅

- [x] 代码已下载到 `/opt/myTrader`
- [x] Git SSH 密钥已配置
- [x] Node.js 16 已安装
- [x] GLM-5 CLI 已配置

## 剩余任务

### Phase 1: 基础环境配置

- [ ] **Nginx 安装和配置**
  - 检查 Nginx 是否已安装
  - 复制配置文件到 `/etc/nginx/conf.d/`
  - 验证配置语法
  - 启动 Nginx

- [ ] **Redis 配置**
  - 检查 Redis 是否已安装
  - 启动 Redis 服务
  - 验证连接

- [ ] **Python 依赖安装**
  - 安装项目依赖：`pip install -r requirements.txt`
  - 验证关键模块

- [ ] **前端构建**
  - 安装前端依赖：`cd web && npm install`
  - 构建前端：`npm run build`

### Phase 2: 数据库和迁移

- [ ] **数据库配置**
  - 编辑 `.env` 文件，配置数据库连接
  - 测试数据库连接

- [ ] **数据库迁移**
  - 运行 Alembic 迁移：`alembic upgrade head`

### Phase 3: Systemd 服务配置

- [ ] **安装 systemd 服务**
  - 复制服务文件到 `/etc/systemd/system/`
  - 刷新 systemd daemon
  - 启用开机启动

- [ ] **启动服务**
  - 启动 Redis
  - 启动 API
  - 启动前端

### Phase 4: 验证和监控

- [ ] **健康检查**
  - 检查各服务状态
  - 验证 API 响应
  - 检查日志

---

## 快速执行命令

### 1. 检查当前状态

```bash
cd /opt/myTrader

# 检查 Nginx
nginx -v

# 检查 Redis
redis-cli ping

# 检查 Python
python3 --version
pip list | grep -i flask

# 检查 Node.js
node --version
npm --version
```

### 2. 安装依赖（如果需要）

```bash
cd /opt/myTrader

# Python 依赖
pip install -r requirements.txt

# 前端依赖
cd web && npm install && npm run build && cd ..
```

### 3. 配置 .env

```bash
# 编辑环境配置
vi /opt/myTrader/.env

# 需要填写的关键项目：
# DB_ENV=online
# ONLINE_DB_HOST=your-db-host
# ONLINE_DB_PORT=3306
# ONLINE_DB_USER=root
# ONLINE_DB_PASSWORD=your-password
# ONLINE_DB_NAME=trade
# REDIS_HOST=127.0.0.1
# REDIS_PORT=6379
# JWT_SECRET_KEY=your-secret-key (最少 32 字符)
```

### 4. 数据库迁移

```bash
cd /opt/myTrader
alembic upgrade head
```

### 5. 安装 systemd 服务

```bash
cd /opt/myTrader

# 复制服务文件
sudo cp scripts/mytrader-api.service /etc/systemd/system/
sudo cp scripts/mytrader-web.service /etc/systemd/system/
sudo cp scripts/mytrader-redis.service /etc/systemd/system/

# 刷新 systemd
sudo systemctl daemon-reload

# 启用开机启动
sudo systemctl enable mytrader-redis
sudo systemctl enable mytrader-api
sudo systemctl enable mytrader-web

# 启动服务
sudo systemctl start mytrader-redis
sudo systemctl start mytrader-api
sudo systemctl start mytrader-web
```

### 6. 配置 Nginx

```bash
# 复制 Nginx 配置
sudo cp /opt/myTrader/nginx.conf /etc/nginx/conf.d/mytrader.conf

# 检查配置
sudo nginx -t

# 重启 Nginx
sudo systemctl restart nginx
```

### 7. 验证部署

```bash
# 检查服务状态
sudo systemctl status mytrader-api
sudo systemctl status mytrader-web
sudo systemctl status mytrader-redis

# 健康检查
curl http://localhost:8000/health
curl http://localhost:3000/
curl http://localhost/health

# 查看日志
sudo journalctl -u mytrader-api -f
```

---

## 建议执行顺序

1. **检查当前环境**（5 分钟）
   ```bash
   nginx -v
   redis-cli ping
   python3 --version
   ```

2. **安装项目依赖**（10-15 分钟）
   ```bash
   pip install -r requirements.txt
   cd web && npm install && npm run build
   ```

3. **配置环境变量**（5 分钟）
   ```bash
   vi .env
   ```

4. **数据库迁移**（5 分钟）
   ```bash
   alembic upgrade head
   ```

5. **配置 Nginx**（5 分钟）
   ```bash
   sudo cp nginx.conf /etc/nginx/conf.d/mytrader.conf
   sudo nginx -t
   sudo systemctl restart nginx
   ```

6. **安装 systemd 服务**（5 分钟）
   ```bash
   sudo cp scripts/*.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable mytrader-*
   sudo systemctl start mytrader-*
   ```

7. **验证部署**（5 分钟）
   ```bash
   curl http://localhost:8000/health
   sudo journalctl -u mytrader-api -f
   ```

**总耗时**：约 40-50 分钟

---

## 关键问题

- **Nginx 是否已安装？** 
  - 是 → 直接复制配置
  - 否 → 需要 `yum install nginx`

- **Redis 是否已启动？**
  - 是 → 检查连接
  - 否 → `systemctl start redis` 或用我们的 service 文件

- **数据库是否可用？**
  - 需要在 `.env` 中配置正确的连接信息

---

## 守护进程说明

**我们已经为你准备好了 systemd 服务**：

```
scripts/mytrader-api.service      ← API 守护进程
scripts/mytrader-web.service      ← 前端守护进程
scripts/mytrader-redis.service    ← Redis 守护进程（可选）
```

**特点**：
- ✅ 自动重启（进程崩溃时）
- ✅ 开机启动
- ✅ 统一日志管理（journalctl）
- ✅ 依赖关系管理
- ✅ 无需手动脚本

---

## 下一步

告诉我：

1. **Nginx 是否已装？** （`nginx -v`）
2. **Redis 是否已装？** （`redis-cli ping`）
3. **你的数据库地址是什么？** （用于填写 `.env`）

我根据你的回答，给你一个 **一键部署脚本** 或 **逐步指导**。

