好的，我来做一个完整的 myTrader 个人投研平台的技术方案设计，包含架构图和详细规划。接下来是前端页面结构和部署方案的详细设计。

---

## myTrader 个人投研平台 — 技术方案

### 一、整体定位与阶段规划

分两个阶段：**Phase 1** 自用投研看板（1~2个月），**Phase 2** 对外开放多用户SaaS（3~6个月）。服务端保持现有 FastAPI 体系，前端新建 Next.js 项目，部署在同一台阿里云 ECS 上。

---

### 二、前端技术栈

**Next.js 14 (App Router) + TypeScript**，理由是 SSR 对 SEO 友好（后续可公开落地页），与 FastAPI 的 REST/WebSocket 接口天然兼容，部署简单（静态导出或 Node server）。

核心依赖：

- **TanStack Query** — 接口缓存与后台轮询（行情刷新、回测进度）
- **Zustand** — 轻量全局状态（用户信息、持仓快照）
- **ECharts / TradingView Lightweight Charts** — K线、因子走势、组合净值曲线
- **Tailwind CSS + shadcn/ui** — 快速搭建专业的数据看板风格 UI
- **React Hook Form + Zod** — 策略参数配置表单校验
- **Socket.IO client** — 实时推送（行情 tick、回测进度条）

---

### 三、页面模块规划

**个人投研看板（Phase 1，无需登录）**

| 页面 | 核心功能 |
|---|---|
| `/dashboard` | 持仓总览、PnL曲线、今日信号摘要 |
| `/market` | 行情看板、RPS筛股、板块轮动热力图 |
| `/strategy` | 策略列表、回测发起、IC/IR报告 |
| `/analysis` | 技术面 + 基本面分析报告，支持输入股票代码 |
| `/rag` | 研报/财报问答，RAG 对话界面 |
| `/portfolio` | 多账户持仓聚合（招商/东方/华宝/富途/长桥） |
| `/daily` | 每日复盘，接 daily_run.py 输出 |

**对外开放（Phase 2，需注册登录）**

| 页面 | 功能 | 计费方式 |
|---|---|---|
| `/public/screener` | 技术面筛股（RPS + 动量） | 免费 |
| `/public/analysis/:code` | 技术分析报告（每日限3次） | Freemium |
| `/public/strategy-builder` | 因子组合 + 策略构建 | 付费订阅 |
| `/public/backtest` | 回测提交 + 结果查看 | 付费订阅 |
| `/admin` | 用户管理、使用配额、订阅状态 | 内部 |

---

### 四、后端服务层改造

现有模块直接复用，在外层包一层 **FastAPI Router**，按业务域拆分：

```
api/
├── routers/
│   ├── market.py        # 行情、因子、筛股
│   ├── strategy.py      # 策略CRUD、回测触发
│   ├── analysis.py      # 技术面/基本面分析
│   ├── rag.py           # 研报问答（流式 SSE）
│   ├── portfolio.py     # 持仓聚合、PnL计算
│   ├── auth.py          # 注册、登录、JWT刷新
│   └── user.py          # 配额检查、订阅管理
├── middleware/
│   ├── auth.py          # JWT 验证依赖
│   ├── rate_limit.py    # 每用户 API 限流（Redis）
│   └── quota.py         # Freemium 用量扣减
├── models/              # SQLAlchemy ORM (用户/订阅/使用记录)
└── tasks/               # Celery 任务（回测异步、数据拉取）
```

**回测异步化**是关键点：前端 POST 触发回测 → 返回 `task_id` → 前端轮询 `/tasks/{task_id}/status` → Celery Worker 跑完后写结果到 MySQL → 前端拉取报告。

**RAG 问答流式输出**：FastAPI 用 `StreamingResponse` + Server-Sent Events，前端用 `EventSource` 接收，实现打字机效果。

---

### 五、用户体系与 Freemium 设计

```
MySQL 新增表：
users           — id, email, hashed_password, tier(free/pro), created_at
subscriptions   — user_id, plan, start_date, end_date, stripe_subscription_id
usage_logs      — user_id, api_endpoint, date, count
api_keys        — user_id, key_hash, name, last_used
```

配额控制在 FastAPI Dependency 层做，Redis 存当日计数，每次请求原子 `INCR`，超限返回 429。

付费方案建议：Free（每日3次分析 + 只读看板）、Pro（无限分析 + 策略构建 + 回测）、API Key（程序化接入）。

---

### 六、部署架构（阿里云单机）**docker-compose.yml 服务清单**（基于现有目录直接挂载）：

```yaml
services:
  nginx:       # 443/80，挂载 Let's Encrypt 证书
  nextjs:      # port 3000，生产 build
  api:         # uvicorn --workers 2，挂载现有代码目录
  worker:      # celery -A tasks worker，复用 api 同一镜像
  beat:        # celery beat，替代现有 daily_run.py cron
  mysql:       # 已有，挂载数据卷
  qdrant:      # 已有，挂载数据卷
  redis:       # 新增，轻量
  prometheus:  # 监控
  grafana:     # 面板
```

---

### 七、CI/CD 流程

GitHub Actions：push to `main` → SSH 到 ECS → `git pull` + `docker compose up -d --build api nextjs worker`，零停机滚动更新。敏感配置（API Key、数据库密码）全部走 GitHub Secrets → 注入为环境变量，不进代码仓库。

---

### 八、目录结构建议（增量改造）

```
mytrader/
├── api/                    # 新增 —— FastAPI 路由层
│   ├── routers/
│   ├── middleware/
│   ├── models/
│   └── tasks/              # Celery 任务
├── web/                    # 新增 —— Next.js 前端
│   ├── app/
│   │   ├── dashboard/
│   │   ├── market/
│   │   ├── strategy/
│   │   ├── rag/
│   │   └── (auth)/
│   ├── components/
│   └── lib/                # API client, hooks
├── data/                   # 已有
├── data_analyst/           # 已有，直接 import
├── strategist/             # 已有
├── investment_rag/         # 已有
├── executor/               # 已有
├── docker-compose.yml      # 新增
├── nginx.conf              # 新增
└── .github/workflows/      # 新增 CI/CD
```

---

### 九、实施路径（推荐顺序）

Phase 1（4~6周，自用看板优先）：

1. **第1周**：搭 `api/routers/` 骨架，把现有 `data_analyst`、`strategist` 包成 REST 接口，Postman 验通
2. **第2周**：Next.js 初始化，做 `/dashboard` + `/market` 两个核心页面，接通行情和持仓数据
3. **第3周**：Celery 异步回测 + `/strategy` 页面，支持在页面上发起回测并查看进度
4. **第4周**：RAG 流式问答界面，Nginx + Docker Compose 上线，配域名和 HTTPS

Phase 2（另起排期，对外开放）：

5. **用户认证**：`/auth` JWT 体系，注册/登录页
6. **配额中间件**：Redis 计数 + 订阅表
7. **付费集成**：Stripe 或国内微信支付/支付宝

如果想先细化某个模块（比如回测的前后端交互设计，或者 RAG 流式接口的实现），可以继续展开。
