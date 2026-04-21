# Web 平台 & API 服务

新增于 2026-04-05，基于 `docs/myTrader_tech_plan.md` 技术方案，完成 28 个任务中的 27 个（T28 生产上线需服务器环境）。

## 技术栈

- 后端: FastAPI + SQLAlchemy (aiomysql) + Redis + Celery + JWT
- 前端: Next.js 16 (App Router) + TypeScript + Tailwind CSS + TanStack Query + Zustand
- 基础设施: Docker Compose + Nginx + GitHub Actions CI/CD

## 后端 API 路由（40 个）

| Router | 前缀 | 说明 |
|--------|------|------|
| health | /health | 健康检查 |
| auth | /api/auth/* | 注册/登录/刷新/me |
| market | /api/market/* | K线/指标/因子/RPS/搜索 |
| analysis | /api/analysis/* | 技术面/基本面分析 |
| strategy | /api/strategy/* | 策略 CRUD/回测提交/SSE 进度 |
| rag | /api/rag/* | RAG 问答 SSE 流式 |
| portfolio | /api/portfolio/* | 持仓汇总/PnL |
| admin | /api/admin/* | 用户管理(仅 admin) |
| api_keys | /api/api-keys/* | API Key CRUD/X-API-Key 鉴权 |
| subscription | /api/subscription/* | 订阅计划/升级/Webhook |

## 前端页面（11 个路由）

| 路由 | 说明 | 认证 |
|------|------|------|
| /dashboard | 持仓总览 + PnL 卡片 | 登录 |
| /market | K线表格 + RPS 排名 | 登录 |
| /analysis | 技术/基本面分析 | 登录 |
| /strategy | 策略管理 + 回测(SSE 进度) | 登录 |
| /rag | RAG 对话(SSE 流式) | 登录 |
| /admin | 用户管理后台 | Admin |
| /public/screener | 公开筛股(RPS + 技术分析) | 公开 |
| /login, /register | 认证页面 | 公开 |

## 数据库新增表（6 张）

- `users` - 用户主表 (tier/role/is_active)
- `subscriptions` - 订阅记录 (plan/start_date/end_date)
- `usage_logs` - API 使用日志 (配额计数)
- `api_keys` - API Key (key_hash/key_prefix/revoked_at)
- `strategies` - 策略配置 (name/params/is_active)
- `backtest_jobs` - 回测任务 (status/progress/IC/ICIR/MaxDD)

## 快速启动

```bash
# 启动 Redis
docker compose up -d redis

# 数据库迁移
make migrate

# 启动 API (本地开发)
make api-local

# 启动前端
cd web && npm install && npm run dev

# 完整 Docker 部署
make dev
```

## 环境变量（.env 新增）

```bash
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# JWT
JWT_SECRET_KEY=your-secret-key
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# API
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=true
APP_VERSION=0.1.0

# Celery
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

## 测试

```bash
# 安全测试
pytest tests/security/ -v

# 压力测试
locust -f tests/load/locustfile.py --host=http://localhost:8000

# E2E 测试 (需安装 Playwright)
npx playwright test tests/e2e/
```

## CI/CD

- push 到 main 分支自动触发: lint -> build -> pytest -> SSH deploy
- PR 分支仅运行 test (不部署)
- 需配置 GitHub Secrets: ECS_HOST, ECS_USER, ECS_SSH_KEY

## 已知限制

1. 支付集成为占位实现，需对接 Stripe 或微信支付
2. ECharts 图表、shadcn/ui 组件库尚未集成，当前使用 Tailwind 原生样式
3. K 线图使用表格展示，Lightweight Charts 待集成
4. T28 生产上线（蓝绿切换、备份恢复、监控面板）需服务器环境执行

[返回主文档](../../CLAUDE.md)
