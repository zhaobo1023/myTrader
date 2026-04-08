# CI/CD 与部署方案总结

## 核心答案

你问的三个问题，答案如下：

### 1. CI/CD 怎么搞？

**简单方案**（推荐）：
- 使用 GitHub Actions（已配置）
- `git push origin main` → 自动触发部署工作流
- 工作流执行：测试 → SSH 部署到 ECS
- **无需手动干预**

**如果不用 GitHub Actions**：
- 本地 SSH 连接 ECS
- 执行部署脚本 `./scripts/deploy.sh`
- 脚本自动 git pull + pip install + systemctl restart

### 2. Git 下载代码 + 脚本启动？

完全正确！这就是方案：

```bash
# ECS 上执行
cd /opt/myTrader
git pull origin main              # 1. Git 下载
pip install -r requirements.txt   # 2. 更新依赖
sudo systemctl restart mytrader-api   # 3. 启动（守护进程）
```

所有这些步骤已整合到 `scripts/deploy.sh`，可以一键执行。

### 3. 守护进程怎么实现？

**使用 systemd**（Linux 标准）：

```bash
# 注册服务
sudo cp scripts/mytrader-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mytrader-api   # 开机启动

# 控制
sudo systemctl start mytrader-api    # 启动
sudo systemctl restart mytrader-api  # 重启（自动重新拉代码后执行）
sudo systemctl stop mytrader-api     # 停止
```

systemd 会**自动重启崩溃的进程**，比 shell 脚本守护更可靠。

---

## 部署工作流（三种方案对比）

### 方案 A: GitHub Actions (最简单，推荐)

```
Local: git push origin main
    ↓
GitHub: trigger workflow
    ↓
    ├─ 测试 (test.yml)
    └─ 部署 (deploy.yml)
        └─ SSH 到 ECS
            ├─ git pull
            ├─ pip install
            ├─ alembic upgrade
            ├─ systemctl restart api
            └─ systemctl restart web
    ↓
ECS: 自动重启服务
```

**需要配置 GitHub Secrets：**
```
ECS_HOST=你的IP
ECS_USER=ubuntu
ECS_SSH_KEY=你的SSH私钥
```

**优点**：
- 完全自动，无需手动操作
- 任何地方 push 就能触发部署
- 有完整的部署日志和失败通知

### 方案 B: SSH 手动部署

```
Local: ssh ubuntu@ecs-ip
    ↓
    ./scripts/deploy.sh
    ↓
ECS: 自动执行所有步骤
```

**优点**：
- 简单直接，无需配置 GitHub
- 可立即验证结果
- 适合快速迭代

### 方案 C: 直接命令行（最原始）

```bash
ssh ubuntu@ecs-ip 'cd /opt/myTrader && git pull && pip install -r requirements.txt && sudo systemctl restart mytrader-api'
```

**缺点**：
- 命令很长，容易出错
- 无法自动化

---

## 部署架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     用户浏览器                                  │
│                   (访问 your-domain.com)                       │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP/HTTPS
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                      Nginx (80/443)                          │
│  • 反向代理 API (/api/*) → :8000                             │
│  • 反向代理 Web (/) → :3000                                  │
│  • 路由规则、超时配置、SSE 支持                                │
└────────────────────┬──────────────────────┬─────────────────┘
                     │ localhost:8000       │ localhost:3000
                     ↓                      ↓
        ┌─────────────────────┐  ┌──────────────────────┐
        │   API (FastAPI)     │  │  Web (Next.js)       │
        │  [systemd service]  │  │  [systemd service]   │
        │  • 4 workers        │  │  • Build output      │
        │  • Database conn    │  │  • Node.js process   │
        │  • Redis conn       │  │  • SSR               │
        └──────────┬──────────┘  └──────────────────────┘
                   │
                   ├─ MySQL (ONLINE_DB_HOST)
                   │
                   └─ Redis (localhost:6379)
```

---

## 服务启动顺序与依赖关系

```mermaid
Redis
  ↑
  ├─ API (depends on Redis + MySQL)
  │
  └─ Web (不依赖 Redis，仅显示数据)
```

**systemd 自动管理**：

```ini
# mytrader-api.service
[Unit]
Wants=mytrader-redis.service  # 不强制依赖，但会优先启动 Redis

# mytrader-web.service
[Unit]
After=network.target  # 仅等待网络
```

---

## 自动部署流程（GitHub Actions）

### 详细步骤

1. **本地提交代码**
   ```bash
   git commit -am "feat: add new feature"
   git push origin main
   ```

2. **GitHub 自动触发** (workflow: `deploy.yml`)
   - 检出代码
   - 运行测试（test.yml）
   - 如果测试通过，执行部署

3. **SSH 连接到 ECS** (appleboy/ssh-action)
   ```bash
   cd /opt/myTrader
   git pull origin main
   pip install -q -r requirements.txt
   cd web && npm ci && npm run build && cd ..
   alembic upgrade head
   sudo systemctl restart mytrader-api
   sudo systemctl restart mytrader-web
   sleep 3
   curl -sf http://localhost:8000/health || exit 1
   ```

4. **部署完成**
   - Workflow 状态显示为 ✅ 成功 或 ❌ 失败
   - GitHub 发送邮件通知

### 监控部署

在 GitHub 仓库 → **Actions** 标签页查看：
- 每次推送的部署日志
- 失败原因（如测试不通过）
- 部署耗时

---

## Systemd 服务详解

### 为什么选择 systemd？

| 特性 | systemd | Shell 脚本 | Docker |
|------|---------|-----------|--------|
| 自动重启 | ✅ 内置 | ❌ 需要额外工具 | ✅ 可配置 |
| 日志管理 | ✅ journalctl | ⚠️ 需手管理 | ✅ 容器日志 |
| 依赖管理 | ✅ Unit 依赖 | ❌ 需脚本处理 | ⚠️ 通过 compose |
| 资源占用 | 最低 | 低 | 高 |
| 学习曲线 | 中等 | 简单 | 陡峭 |
| 操作系统 | Linux 标准 | 通用 | 需要 Docker |

**我们选择 systemd**：
- ECS 已有 systemd（所有 Linux 都有）
- 不需要额外工具
- 自动重启、日志聚合、依赖管理都很完善

### 服务文件位置

```
/etc/systemd/system/
├── mytrader-api.service      ← 我们创建的
├── mytrader-web.service      ← 我们创建的
├── mytrader-redis.service    ← 我们创建的（可选）
```

### 日志查看（systemd）

```bash
# 实时输出（如 tail -f）
sudo journalctl -u mytrader-api -f

# 最后 50 行 + 持续输出
sudo journalctl -u mytrader-api -n 50 -f

# 仅错误
sudo journalctl -u mytrader-api -p err

# 今天的日志
sudo journalctl -u mytrader-api --since today

# 转储到文件
sudo journalctl -u mytrader-api > api.log
```

---

## Nginx 配置关键点

你已装好 Nginx，现在需要配置。关键点：

### 1. 反向代理设置

```nginx
upstream fastapi_backend {
    server 127.0.0.1:8000;    # API 地址
}

upstream nextjs_frontend {
    server 127.0.0.1:3000;    # 前端地址
}
```

### 2. 路由规则

| 请求 | 转发到 | 目的 |
|------|--------|------|
| `GET /api/*` | `:8000` | API 接口 |
| `GET /` | `:3000` | 网站首页 |

### 3. SSE 支持（关键！）

API 中有 RAG 问答需要流式响应：

```nginx
location /api/ {
    proxy_buffering off;           # 关闭缓冲，实时流式
    proxy_cache off;
    chunked_transfer_encoding off;
    proxy_read_timeout 300s;       # 给长连接更多时间
}
```

### 4. 健康检查路由

```nginx
location /health {
    proxy_pass http://fastapi_backend/health;
    access_log off;  # 不记录日志，防止刷屏
}
```

---

## 部署检查清单

部署完成后，按以下顺序检查：

```bash
# 1. 端口监听
lsof -i :80      # Nginx
lsof -i :8000    # API
lsof -i :3000    # 前端
lsof -i :6379    # Redis

# 2. 服务状态
sudo systemctl status mytrader-api
sudo systemctl status mytrader-web
sudo systemctl status mytrader-redis

# 3. 数据库连接
python3 << 'EOF'
from config.db import get_connection
print(get_connection())  # 应输出连接对象
EOF

# 4. API 健康检查
curl http://localhost:8000/health          # 直连
curl http://localhost/health               # 通过 Nginx

# 5. 访问网站
curl http://localhost/                     # 应返回 HTML

# 一键检查
sudo ./scripts/check-deployment.sh
```

---

## 常见问题

### Q: 如何只重启 API 不重启前端？
```bash
sudo systemctl restart mytrader-api  # 只重启 API
sudo systemctl restart mytrader-web  # 只重启前端
```

### Q: 部署失败如何回滚？
```bash
cd /opt/myTrader
git log --oneline -10              # 查看历史
git reset --hard HEAD~1            # 回到上一个版本
./scripts/deploy.sh                # 重新部署
```

### Q: 如何更改部署脚本？
编辑 `/opt/myTrader/scripts/deploy.sh`，它会在下次 push 时使用新版本。

### Q: 需要手动更新依赖吗？
不需要！每次 push 时，`pip install -r requirements.txt` 会自动检查和更新。

### Q: 如何监控 API 性能？
```bash
# CPU 和内存
top -p $(pgrep -f uvicorn)

# 请求计数
sudo tail -f /var/log/nginx/access.log | grep api
```

### Q: 如何添加 HTTPS？
```bash
# 使用 Certbot + Let's Encrypt
sudo apt-get install certbot python3-certbot-nginx
sudo certbot certonly --nginx -d your-domain.com

# 在 Nginx 中启用 HTTPS
# 详见 docs/DEPLOYMENT_ECS.md 的 SSL/TLS 部分
```

---

## 文件清单

我们为你创建了以下文件：

```
scripts/
├── deploy.sh                     # 自动部署脚本（git + pip + systemctl）
├── init-ecs.sh                   # ECS 初始化脚本（一键部署）
├── check-deployment.sh           # 部署检查脚本
├── mytrader-api.service          # API systemd 服务文件
├── mytrader-web.service          # 前端 systemd 服务文件
└── mytrader-redis.service        # Redis systemd 服务文件

nginx.conf                        # 更新的 Nginx 配置

.github/workflows/
├── deploy.yml                    # 更新的部署工作流（systemd 版本）
└── test.yml                      # 测试工作流（保持不变）

docs/
├── DEPLOYMENT_ECS.md             # 完整部署指南（详细）
├── QUICK_START_ECS.md            # 快速启动参考
└── CI_CD_SUMMARY.md              # 本文件

.env.example                      # 环境配置模板（需手动编辑）
```

---

## 下一步

1. **配置 GitHub Secrets** (如果用 GitHub Actions)
   - 在 GitHub 仓库 → Settings → Secrets and variables → Actions
   - 添加：ECS_HOST, ECS_USER, ECS_SSH_KEY

2. **部署到 ECS**
   ```bash
   # 在 ECS 上一键初始化
   curl -fsSL https://raw.githubusercontent.com/zhaobo03/myTrader/main/scripts/init-ecs.sh | bash
   ```

3. **编辑环境配置**
   ```bash
   vi /opt/myTrader/.env
   ```

4. **启动服务**
   ```bash
   alembic upgrade head
   sudo systemctl start mytrader-redis mytrader-api mytrader-web
   ```

5. **验证**
   ```bash
   curl http://localhost:8000/health
   ```

---

**总结**：你的部署策略是完全正确的。我们已经为你准备好所有脚本和配置，后续只需：

1. GitHub push → 自动部署
2. 或 SSH 手动执行 `./scripts/deploy.sh`
3. systemd 自动管理守护进程
4. Nginx 反向代理

完全不需要手动启动服务！

