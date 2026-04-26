# Web 平台 & API 服务

新增于 2026-04-05，持续迭代中。最后更新：2026-04-26。

## 技术栈

- 后端: FastAPI + SQLAlchemy (aiomysql) + Redis + Celery + JWT
- 前端: Next.js 16 (App Router) + TypeScript + Tailwind CSS + TanStack Query + Zustand
- 基础设施: Docker Compose + Nginx + GitHub Actions CI/CD

## 后端 API 路由

| Router | 前缀 | 说明 |
|--------|------|------|
| health | /health | 健康检查 |
| auth | /api/auth/* | 注册/登录/刷新/me |
| market | /api/market/* | K线/指标/因子/RPS/搜索 |
| analysis | /api/analysis/* | 技术面/基本面分析 + 一页纸研报（SSE） |
| strategy | /api/strategy/* | 策略 CRUD/回测提交/SSE 进度 |
| rag | /api/rag/* | RAG 问答 SSE 流式 |
| portfolio | /api/portfolio/* | 持仓汇总/PnL |
| agent | /api/agent/* | ReAct AI Agent（内置工具：smart_search/theme_pool/candidate_pool等） |
| briefing | /api/briefing/* | AI 晨报/复盘报告生成与查询（V2 三阶段管道） |
| sentiment | /api/sentiment/* | 舆情分析 |
| wechat_feed | /api/wechat-feed/* | 公众号订阅管理（列表/添加/删除/同步）|
| admin | /api/admin/* | 用户管理(仅 admin) |
| api_keys | /api/api-keys/* | API Key CRUD/X-API-Key 鉴权 |
| subscription | /api/subscription/* | 订阅计划/升级/Webhook |

## 前端页面（20+ 路由）

| 路由 | 说明 | 认证 |
|------|------|------|
| /dashboard | 宏观总览 + 大宗资产 + 持仓快照 | 登录 |
| /market | 全球资产行情（含 GSCI 子指数） | 登录 |
| /portfolio | 组合管理 + PnL 分析 | 登录 |
| /positions | 个仓位持仓明细 + 风险概览 | 登录 |
| /analysis | 技术面 + 因子 + 一页纸研报（SSE） | 登录 |
| /strategy | XGBoost/多因子策略 + 回测（SSE 进度） | 登录 |
| /rag | 智能研报（RAG 问答 SSE 流式） | 登录 |
| /sentiment | 舆情监控（新闻情感 + Polymarket） | 登录 |
| /theme-pool | 主题池 + 概念轮动 | 登录 |
| /candidate-pool | 候选股票池（多维筛选 + 标签系统） | 登录 |
| /sim-pool | 模拟组合管理 | 登录 |
| /trade-log | 交易流水记录 | 登录 |
| /inbox | 系统通知 + 预警推送 | 登录 |
| /data-health | 数据管道监控 + 公众号订阅管理 | Admin |
| /admin | 用户管理后台 | Admin |
| /settings | 个人设置 + API Key 管理 | 登录 |
| /public/screener | 公开筛股（RPS + 技术） | 公开 |
| /(auth)/login | 登录页 | 公开 |
| /(auth)/register | 注册页 | 公开 |

## 数据库主要表

**用户体系（6 张）**
- `users` - 用户主表 (tier/role/is_active)
- `subscriptions` - 订阅记录 (plan/start_date/end_date)
- `usage_logs` - API 使用日志 (配额计数)
- `api_keys` - API Key (key_hash/key_prefix/revoked_at)
- `strategies` - 策略配置 (name/params/is_active)
- `backtest_jobs` - 回测任务 (status/progress/IC/ICIR/MaxDD)

**微信订阅（2 张，后续新增）**
- `wechat_feeds` - 公众号订阅源 (feed_id/name/is_active)
- `ai_wechat_articles` - AI 相关文章库 (o_id/feed_id/title/content_text/matched_keywords)

**报告缓存**
- `trade_briefing` - AI 晨报/复盘 (session/brief_date/content/structured_data)

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

# 完整 Docker 部署（含本地模型服务）
make dev

# 下载本地模型（首次需要）
python scripts/download_models.py
```

## 环境变量（.env）

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

# 本地模型服务
LOCAL_MODEL_SERVICE_URL=http://mytrader-model-service:8500
MODEL_BASE_DIR=/data/models

# 微信订阅
WECHAT_RSS_DB=/root/wechat2rss/data/res.db
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

## 已完成（原已知限制）

- ECharts K 线图 + 技术指标面板：已集成（含 RSI/MACD/布林带/KDJ 解读面板）
- 蓝绿部署 + 零停机：已实现（Gunicorn USR2 热重载 + nextjs-blue/green 双容器切换）

## 当前限制

1. 支付集成为占位实现，需对接 Stripe 或微信支付
2. 一页纸研报缺少导出/下载功能（.md 文件下载）
3. 历史报告列表未分页

[返回主文档](../../CLAUDE.md)
