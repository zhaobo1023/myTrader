# CI/CD 部署方案（2026-04-15 定稿）

## 架构概览

```
本地开发
  └─ git push origin main
       └─ GitHub Actions (.github/workflows/deploy.yml)
            ├─ test job:  lint + tsc + build
            └─ deploy job: SSH → /root/app → git pull → restart
```

## 服务器部署结构

| 项目 | 值 |
|------|-----|
| 服务器 | 阿里云 ECS，IP: 123.56.3.1 |
| 代码目录 | `/root/app`（不是 /opt/myTrader，不是 /app/myTrader）|
| 部署方式 | Docker 容器，**无 docker-compose**（直接 docker run）|
| API 容器 | `mytrader-api`，卷挂载 `/root/app:/app`，代码实时生效 |
| Web 容器 | `mytrader-web`，代码打进镜像，需重建才生效 |
| Nginx | `mytrader-nginx`，监听 80/443，反代到 api:8000 + web:3000 |
| Redis | `mytrader-redis` |
| Celery | `app-celery-worker-1` + `app-celery-beat` |
| 网络 | `app_mytrader-network` |

## GitHub Actions 流程

### 触发条件
- push 到 `main` 分支时自动触发

### test job（约 2-3 分钟）
1. Python lint (ruff)
2. TypeScript type check (tsc --noEmit)
3. Next.js build

### deploy job（test 通过后，约 20 秒，前端变更时约 4 分钟）
1. SSH 进服务器
2. `git pull origin main`
3. `docker restart mytrader-api`（等待 healthy）
4. 检测 `web/` 是否有变更：
   - **有变更**：`docker build --no-cache` 重建镜像 + 重启容器
   - **无变更**：跳过，节省 3 分钟
5. `curl -sf http://localhost:8000/health` 最终验证

## GitHub Secrets 配置

位置：`github.com/zhaobo1023/myTrader/settings/secrets/actions`

| Secret | 值 | 说明 |
|--------|-----|------|
| `ECS_HOST` | `123.56.3.1` | 已配置 |
| `ECS_USER` | `root` | 已配置 |
| `ECS_SSH_KEY` | ed25519 私钥 | 已配置 |
| `POSTHOG_KEY` | `phc_xxx...` | PostHog Project API Key，见下方获取步骤 |
| `POSTHOG_HOST` | `http://123.56.3.1/analytics` | PostHog 自托管地址 |

对应公钥已添加到服务器 `~/.ssh/authorized_keys`。

## PostHog 埋点系统（一次性初始化）

PostHog 是自托管的产品分析服务，需要在首次部署时手动初始化一次，之后全自动。

### 第一步：启动 PostHog 容器

```bash
ssh aliyun-ecs
cd /root/app

# 启动 PostHog 三个容器（PostgreSQL + Redis + PostHog 主服务）
docker compose up -d posthog-db posthog-redis posthog

# 等待约 30 秒后初始化数据库（只需执行一次）
docker compose exec posthog python manage.py migrate
```

### 第二步：获取 Project API Key

1. 浏览器访问 `http://123.56.3.1/analytics`
2. 完成注册（填邮箱 + 密码，自托管无需验证）
3. 进入控制台后：**Settings（左下角齿轮）→ Project Settings → Project API Key**
4. 复制 `phc_` 开头的字符串

### 第三步：配置 GitHub Secrets

在 `github.com/zhaobo1023/myTrader/settings/secrets/actions` 添加两个 Secret：

```
POSTHOG_KEY  =  phc_你复制的key
POSTHOG_HOST =  http://123.56.3.1/analytics
```

**完成后 push 任意代码触发一次部署**，前端镜像会带上这两个变量重建，埋点自动生效。

### 前端重建说明

`NEXT_PUBLIC_*` 变量在 Next.js 构建时被内联进 JS bundle，因此：
- **修改了 PostHog Key** → 需要触发前端重建（改动 `web/` 任意文件 push 即可）
- **正常业务改动** → deploy.yml 自动判断 `web/` 是否有变更，有则重建（约 4 分钟），无则跳过（约 20 秒）

## 手动部署（紧急时）

```bash
ssh aliyun-ecs
cd /root/app
git pull origin main

# API 只需重启（卷挂载，代码即时生效）
docker restart mytrader-api

# 前端需要重建镜像（带上 PostHog 变量）
POSTHOG_KEY="phc_你的key"
POSTHOG_HOST="http://123.56.3.1/analytics"

docker build --no-cache \
  --build-arg NEXT_PUBLIC_POSTHOG_KEY="$POSTHOG_KEY" \
  --build-arg NEXT_PUBLIC_POSTHOG_HOST="$POSTHOG_HOST" \
  -t mytrader-web:latest ./web

docker stop mytrader-web && docker rm mytrader-web
docker run -d \
  --name mytrader-web \
  --network app_mytrader-network \
  -p 127.0.0.1:3000:3000 \
  -e NEXT_PUBLIC_API_BASE_URL=http://123.56.3.1:8000 \
  -e NEXT_PUBLIC_POSTHOG_KEY="$POSTHOG_KEY" \
  -e NEXT_PUBLIC_POSTHOG_HOST="$POSTHOG_HOST" \
  --restart unless-stopped \
  mytrader-web:latest
```

## 常见操作

```bash
# 查看所有容器状态
ssh aliyun-ecs "docker ps"

# 查看 API 日志
ssh aliyun-ecs "docker logs -f mytrader-api"

# 查看 Actions 执行记录
# github.com/zhaobo1023/myTrader/actions

# 验证 API 健康
curl http://123.56.3.1/api/health
```

## 注意事项

- 服务器上没有 `.env` 文件，环境变量通过 `docker run -e` 注入（见 `/root/app/restart_v2.sh`）
- `docker compose` 命令在服务器上会因为缺少 `.env` 报错，用 `docker` 命令直接操作
- `trade_stock_basic` 的 `stock_code` 带 `.SH/.SZ` 后缀（如 `000001.SZ`）
- `trade_stock_valuation_factor` 目前为空，市值字段均为 null
