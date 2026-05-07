# myTrader 个人投研平台 — 技术方案与任务拆分

> 版本：v1.0 · 生成日期：2026-04-04  
> 服务端：FastAPI · 前端：Next.js 14 · 部署：阿里云 ECS · 容器：Docker Compose

---

## 一、整体架构概览

### 分层架构

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| 客户端层 | Next.js 14 (App Router) + TypeScript | Web SPA，支持 PWA；Feishu Bot 保留 |
| API 网关层 | Nginx | 反向代理、SSL 终止、限流 |
| 服务层 | FastAPI + Uvicorn | REST API + SSE 流式 + WebSocket |
| 业务引擎层 | 复用现有模块 | data_analyst / strategist / investment_rag / executor |
| 任务队列 | Celery + Redis | 异步回测、日频数据调度 |
| 数据存储 | MySQL + Qdrant + Redis | 结构化数据 / 向量索引 / 缓存队列 |
| 数据采集 | akshare / tushare / 爬虫 | 行情、研报、财报 |
| 基础设施 | Docker Compose + GitHub Actions | CI/CD、Prometheus + Grafana 监控 |

### 前端核心依赖

| 依赖 | 用途 |
|------|------|
| TanStack Query | 接口缓存、后台轮询（行情/回测进度） |
| Zustand | 全局状态（用户信息、持仓快照） |
| ECharts / Lightweight Charts | K线、因子走势、净值曲线 |
| Tailwind CSS + shadcn/ui | 数据看板 UI |
| React Hook Form + Zod | 策略参数表单校验 |
| Socket.IO client | 实时行情 tick、回测进度推送 |

---

## 二、页面模块规划

### Phase 1：个人投研看板（自用）

| 路由 | 核心功能 |
|------|----------|
| `/dashboard` | 持仓总览、PnL 曲线、今日信号摘要 |
| `/market` | 行情看板、RPS 筛股、板块轮动热力图 |
| `/strategy` | 策略列表、回测发起、IC/IR 报告 |
| `/analysis` | 技术面 + 基本面分析报告 |
| `/rag` | 研报/财报问答（RAG 对话） |
| `/portfolio` | 多账户持仓聚合（招商/东方/华宝/富途/长桥） |
| `/daily` | 每日复盘，接 daily_run.py 输出 |

### Phase 2：对外开放（SaaS）

| 路由 | 功能 | 计费 |
|------|------|------|
| `/public/screener` | 技术面筛股（RPS + 动量） | 免费 |
| `/public/analysis/:code` | 技术分析报告（每日限 3 次） | Freemium |
| `/public/strategy-builder` | 因子组合 + 策略构建 | 付费订阅 |
| `/public/backtest` | 回测提交 + 结果查看 | 付费订阅 |
| `/admin` | 用户管理、使用配额、订阅状态 | 内部 |

---

## 三、后端服务层结构

```
api/
├── routers/
│   ├── auth.py          # 注册、登录、JWT 刷新
│   ├── market.py        # 行情、因子、筛股
│   ├── analysis.py      # 技术面/基本面分析
│   ├── strategy.py      # 策略 CRUD、回测触发
│   ├── rag.py           # 研报问答（SSE 流式）
│   ├── portfolio.py     # 持仓聚合、PnL 计算
│   ├── user.py          # 配额查询、订阅管理
│   ├── subscription.py  # 支付、订阅升降级
│   ├── api_keys.py      # API Key 管理
│   └── admin.py         # 后台管理
├── middleware/
│   ├── auth.py          # JWT 验证依赖
│   ├── rate_limit.py    # 滑动窗口限流（Redis）
│   └── quota.py         # Freemium 用量扣减
├── models/              # SQLAlchemy ORM
│   ├── user.py
│   ├── subscription.py
│   ├── usage_log.py
│   ├── api_key.py
│   ├── strategy.py
│   └── backtest_job.py
├── tasks/               # Celery 任务
│   ├── backtest.py
│   └── expire_subscriptions.py
└── core/
    ├── security.py      # bcrypt / JWT
    ├── api_key_auth.py  # X-API-Key 鉴权
    └── metrics.py       # Prometheus metrics
```

### 用户体系数据库表

```sql
-- 用户主表
users (id, email, hashed_password, tier ENUM('free','pro'), created_at)

-- 订阅记录
subscriptions (user_id, plan, start_date, end_date, stripe_subscription_id)

-- API 使用日志（配额计数）
usage_logs (user_id, api_endpoint, date, count)

-- API Key（程序化接入）
api_keys (user_id, key_hash, name, last_used, revoked_at)
```

---

## 四、部署架构

### Docker Compose 服务清单

```yaml
services:
  nginx:      # 80/443，Let's Encrypt 证书
  nextjs:     # port 3000，生产 build
  api:        # uvicorn --workers 2
  worker:     # celery -A tasks worker（复用 api 镜像）
  beat:       # celery beat（替代 daily_run.py cron）
  mysql:      # 已有，挂载数据卷
  qdrant:     # 已有，挂载数据卷
  redis:      # 新增，轻量缓存/MQ
  prometheus: # 指标采集
  grafana:    # 监控面板
```

### CI/CD 流程

```
push to main
  → GitHub Actions
    → lint + pytest（单元测试）
    → docker build
    → SSH 到阿里云 ECS
    → docker compose up -d --build api nextjs worker
    → healthcheck 验证
```

### 目录结构（增量改造）

```
mytrader/
├── api/                    # 新增 —— FastAPI 路由层
├── web/                    # 新增 —— Next.js 前端
│   ├── app/
│   │   ├── dashboard/
│   │   ├── market/
│   │   ├── strategy/
│   │   ├── rag/
│   │   ├── analysis/
│   │   ├── portfolio/
│   │   ├── public/         # 对外开放页面
│   │   └── (auth)/
│   ├── components/
│   ├── hooks/
│   └── lib/                # API client, auth
├── data/                   # 已有
├── data_analyst/           # 已有，直接 import
├── strategist/             # 已有
├── investment_rag/         # 已有
├── executor/               # 已有
├── tests/
│   ├── unit/
│   ├── e2e/                # Playwright
│   ├── load/               # Locust
│   └── security/
├── deploy/
│   ├── grafana/dashboards/
│   ├── alertmanager.yml
│   └── rollback.sh
├── docker-compose.yml      # 新增
├── nginx.conf              # 新增
└── .github/workflows/      # 新增 CI/CD
```

---

## 五、任务拆分（小步迭代）

> 总计 28 个任务，4 个阶段，约 14 周  
> 每个任务包含：目标、关键文件、单元测试覆盖点

---

### Phase 0 — 基础设施搭建（第 1 周）

#### T01 · Docker Compose 环境搭建（2d）`基础设施`

**目标**：搭建本地与服务器统一的容器编排环境，含 MySQL / Redis / Qdrant / FastAPI / Nginx 服务

**关键文件**
- `docker-compose.yml`
- `nginx.conf`
- `.env.example`
- `Makefile`

**单元测试**
- `docker compose up` 全服务健康检查（healthcheck 通过）
- Nginx 反代到 FastAPI 8000 端口 200 响应
- MySQL / Redis / Qdrant 连接性 smoke test
- Makefile dev/prod 命令验证

---

#### T02 · FastAPI 骨架 + 配置管理（1d）`后端`

**目标**：api/ 目录初始化，Pydantic Settings 读取 .env，统一 lifespan 启动数据库连接池

**关键文件**
- `api/main.py`
- `api/config.py`
- `api/dependencies.py`

**单元测试**
- `GET /health` 返回 `{status: ok, db: ok, redis: ok}`
- Settings 读取缺失环境变量时启动失败并打印清晰错误
- 数据库连接池 min/max 配置单测

**依赖**：T01

---

#### T03 · CI/CD GitHub Actions 流水线（1d）`基础设施`

**目标**：push main 触发：lint → pytest → docker build → SSH 部署到阿里云 ECS

**关键文件**
- `.github/workflows/deploy.yml`
- `.github/workflows/test.yml`

**单元测试**
- dry-run 工作流在 PR 分支只跑 test 不部署
- SSH 部署步骤幂等验证（重复触发不产生脏状态）
- Secrets 缺失时 job 提前失败

**依赖**：T01, T02

---

### Phase 1 — 核心后端 API（第 2-5 周）

#### T04 · SQLAlchemy ORM 模型 + Alembic 迁移（2d）`后端`

**目标**：定义 users / subscriptions / usage_logs / api_keys / strategy / backtest_jobs 表，Alembic 管理版本

**关键文件**
- `api/models/*.py`
- `alembic/versions/*.py`

**单元测试**
- 每张表 CRUD 单测（pytest + 测试数据库）
- Alembic upgrade/downgrade 往返一致性
- unique constraint / FK 约束边界测试

**依赖**：T02

---

#### T05 · 用户认证模块 JWT（2d）`后端`

**目标**：注册 / 登录 / 刷新 token / 登出，bcrypt 密码哈希，access + refresh 双 token 方案

**关键文件**
- `api/routers/auth.py`
- `api/core/security.py`
- `api/schemas/auth.py`

**单元测试**
- 正常注册 → 登录 → 刷新 token 流程单测
- 重复邮箱注册返回 409
- 过期 token 返回 401
- 篡改 token 签名返回 401
- bcrypt 哈希不可逆验证

**依赖**：T04

---

#### T06 · Redis 限流 + 配额中间件（1d）`后端`

**目标**：按用户 + endpoint 滑动窗口计数，Free tier 每日配额，超限返回 429 含 Retry-After

**关键文件**
- `api/middleware/rate_limit.py`
- `api/middleware/quota.py`

**单元测试**
- 单用户 N+1 次请求第 N+1 次返回 429
- 不同用户配额独立隔离
- Redis 宕机时 fail-open 降级策略
- 配额重置 cron 单测（mock 时间）

**依赖**：T05

---

#### T07 · 行情 & 因子 API（3d）`后端`

**目标**：封装现有 data/ 和 data_analyst/ 模块，暴露 K线、技术指标、因子截面数据接口，Redis 缓存日频数据

**关键文件**
- `api/routers/market.py`
- `api/services/market_service.py`
- `api/schemas/market.py`

**单元测试**
- `GET /market/kline?code=600519&period=daily` 字段完整性校验
- 无效股票代码返回 404
- 缓存命中率：第 2 次请求响应 < 20ms
- 数据日期连续性检查（无跳空）

**依赖**：T04, T06

---

#### T08 · 技术面 & 基本面分析 API（2d）`后端`

**目标**：封装 data_analyst/ 模块，POST /analysis/technical 和 /analysis/fundamental，返回结构化分析报告 JSON

**关键文件**
- `api/routers/analysis.py`
- `api/services/analysis_service.py`

**单元测试**
- 分析报告包含必填字段（signal, score, summary）
- 非交易日请求处理（返回最近交易日数据）
- 并发 10 请求无竞态（asyncio.gather 测试）
- LLM 超时时返回 partial result 而非 500

**依赖**：T07

---

#### T09 · Celery 异步回测任务（3d）`后端`

**目标**：回测提交返回 task_id，Worker 执行 strategist/ 模块，结果写入 MySQL，SSE 推送进度

**关键文件**
- `api/routers/strategy.py`
- `api/tasks/backtest.py`
- `api/services/backtest_service.py`

**单元测试**
- `POST /backtest` 返回 task_id，`GET /backtest/{id}/status` 状态流转
- Worker 异常时 task status=failed + error_msg
- 重复提交同参数幂等（返回已有 task）
- 回测结果 IC/IR/MaxDD 字段数值范围校验
- SSE 连接断开后 Worker 继续执行

**依赖**：T04, T06

---

#### T10 · RAG 问答 API SSE 流式（2d）`后端`

**目标**：封装 investment_rag/ 模块，POST /rag/query 返回 Server-Sent Events 流，含 source 引用

**关键文件**
- `api/routers/rag.py`
- `api/services/rag_service.py`

**单元测试**
- SSE 流首个 chunk 延迟 < 2s
- 空 Qdrant 集合时返回 no-context 兜底回答
- source 字段含有效文件名和页码
- 并发 3 个流式请求不互相干扰

**依赖**：T04, T06

---

#### T11 · 持仓聚合 & PnL API（2d）`后端`

**目标**：多账户持仓读取（CSV 导入或手动录入），聚合计算 PnL / 持仓分布，日频快照写入 MySQL

**关键文件**
- `api/routers/portfolio.py`
- `api/services/portfolio_service.py`

**单元测试**
- 多账户持仓合并去重逻辑单测
- PnL 计算精度测试（与 Excel 手算对比）
- CSV 导入格式错误时返回具体字段错误
- 历史快照按日期查询准确性

**依赖**：T07

---

### Phase 2 — 前端看板（第 6-9 周）

#### T12 · Next.js 项目初始化 + API Client（1d）`前端`

**目标**：Next.js 14 App Router，TypeScript，Tailwind，shadcn/ui，TanStack Query，Axios 封装 + JWT 拦截器

**关键文件**
- `web/app/layout.tsx`
- `web/lib/api-client.ts`
- `web/lib/auth.ts`
- `web/providers.tsx`

**单元测试**
- API client 401 自动刷新 token 单测（msw mock）
- JWT 过期时跳转 /login 不死循环
- 环境变量 `NEXT_PUBLIC_API_URL` 缺失时构建报错

**依赖**：T05

---

#### T13 · 认证页面（登录 / 注册）（1d）`前端`

**目标**：React Hook Form + Zod 校验，登录成功写 cookie，受保护路由 middleware 拦截

**关键文件**
- `web/app/(auth)/login/page.tsx`
- `web/app/(auth)/register/page.tsx`
- `web/middleware.ts`

**单元测试**
- 表单提交空字段显示错误提示
- 登录成功后 redirect 到 /dashboard
- 已登录用户访问 /login 重定向 /dashboard
- 网络错误显示友好提示而非 JSON

**依赖**：T12

---

#### T14 · Dashboard 持仓总览页（3d）`前端`

**目标**：持仓卡片、PnL 折线图（ECharts）、今日信号摘要、多账户切换 Tab，TanStack Query 轮询 30s

**关键文件**
- `web/app/dashboard/page.tsx`
- `web/components/portfolio/PnlChart.tsx`
- `web/components/portfolio/PositionTable.tsx`

**单元测试**
- ECharts 在 SSR 中不报 window undefined（动态 import）
- 轮询在页面隐藏时暂停（visibilitychange）
- 持仓数据为空时显示 empty state 而非空表格
- 数值格式化（万元/百分比）单测

**依赖**：T11, T13

---

#### T15 · 行情看板 & RPS 筛股页（3d）`前端`

**目标**：K线图（Lightweight Charts）、技术指标叠加、RPS 因子热力图、筛股结果表格排序过滤

**关键文件**
- `web/app/market/page.tsx`
- `web/components/chart/KlineChart.tsx`
- `web/components/screener/ResultTable.tsx`

**单元测试**
- K线图时间轴连续性测试（无断点）
- 筛股结果排序前后数据一致性
- 股票代码输入防抖（300ms）
- 图表 resize 时不抖动（ResizeObserver 单测）

**依赖**：T07, T13

---

#### T16 · 策略管理 & 回测页（3d）`前端`

**目标**：策略列表 CRUD、参数配置表单、回测提交 + 进度条（SSE）、结果报告展示（IC/MaxDD/净值曲线）

**关键文件**
- `web/app/strategy/page.tsx`
- `web/components/backtest/ParamForm.tsx`
- `web/components/backtest/ResultReport.tsx`
- `web/hooks/useBacktestSSE.ts`

**单元测试**
- SSE 连接断开时自动重连（3 次）后显示错误
- 进度条 0→100% 动画不跳帧
- 回测结果为空时不崩溃
- 参数范围校验（日期合法性）

**依赖**：T09, T13

---

#### T17 · RAG 研报问答页（2d）`前端`

**目标**：对话气泡 UI，打字机流式渲染，消息历史，来源文档引用卡片

**关键文件**
- `web/app/rag/page.tsx`
- `web/components/rag/ChatBubble.tsx`
- `web/hooks/useSSEStream.ts`

**单元测试**
- 流式文字追加不闪烁（RAF 测试）
- 发送中禁用输入框
- 来源引用点击展开文件名 + 页码
- 空响应（no context）显示提示语

**依赖**：T10, T13

---

#### T18 · 技术/基本面分析页（2d）`前端`

**目标**：股票代码输入、分析类型选择、报告卡片展示（信号灯、评分雷达图、文字摘要）

**关键文件**
- `web/app/analysis/page.tsx`
- `web/components/analysis/SignalCard.tsx`
- `web/components/analysis/RadarChart.tsx`

**单元测试**
- 无效代码输入前端拦截（A 股格式校验）
- 加载超时 10s 显示 retry 按钮
- 报告中信号颜色与枚举值映射单测

**依赖**：T08, T13

---

### Phase 3 — 多用户 SaaS（第 10-13 周）

#### T19 · 用户管理后台 /admin（2d）`前端`

**目标**：用户列表、使用量图表、手动调整配额、禁用账户，仅 admin role 可访问

**关键文件**
- `web/app/admin/page.tsx`
- `api/routers/admin.py`

**单元测试**
- 非 admin 用户访问 /admin 返回 403
- 配额修改后立即生效（Redis 失效）
- 用户列表分页单测

**依赖**：T05, T06, T13

---

#### T20 · 公开筛股页（Freemium）（2d）`前端`

**目标**：无需登录可访问，免费用户每日 3 次完整报告，超限引导注册/升级，SEO meta 标签

**关键文件**
- `web/app/public/screener/page.tsx`
- `web/app/public/analysis/[code]/page.tsx`

**单元测试**
- 未登录用户第 4 次请求跳转注册引导
- SSR 页面 meta description 含股票代码
- 配额计数按 IP + 用户双维度

**依赖**：T06, T12

---

#### T21 · 订阅 & 支付集成（3d）`后端`

**目标**：微信支付或 Stripe，Webhook 处理支付成功事件，自动升级 subscription tier，到期自动降级

**关键文件**
- `api/routers/subscription.py`
- `api/services/payment_service.py`
- `api/tasks/expire_subscriptions.py`

**单元测试**
- Webhook 签名验证（mock 请求）
- 支付成功后 tier 升级 + 配额重置
- 到期 Celery beat 任务降级准确性
- 重复 Webhook 幂等处理

**依赖**：T04, T05

---

#### T22 · API Key 管理（程序化接入）（1d）`后端`

**目标**：用户可生成 named API key，请求头 X-API-Key 鉴权，与 JWT 配额共享，支持吊销

**关键文件**
- `api/routers/api_keys.py`
- `api/core/api_key_auth.py`

**单元测试**
- API key 与 JWT 配额互通单测
- 吊销后立即失效（Redis 黑名单）
- key 哈希存储，明文只显示一次

**依赖**：T05, T06

---

#### T23 · 监控告警接入（2d）`基础设施`

**目标**：FastAPI 接入 Prometheus metrics，Grafana 配置 API 延迟/错误率/回测队列深度面板，钉钉/微信告警

**关键文件**
- `api/middleware/metrics.py`
- `deploy/grafana/dashboards/*.json`
- `deploy/alertmanager.yml`

**单元测试**
- `/metrics` 端点返回有效 Prometheus 格式
- 模拟 500 错误率告警触发
- 队列积压超阈值告警

**依赖**：T01, T09

---

### Phase 4 — 集成测试 & 上线（第 14 周）

#### T24 · E2E 集成测试：个人投研全流程（2d）`测试`

**目标**：Playwright 脚本：登录 → 查行情 → 发起回测 → 等待完成 → 查看报告 → RAG 提问

**关键文件**
- `tests/e2e/investment_flow.spec.ts`

**测试覆盖**
- 完整流程 < 3min 完成
- 回测状态机 pending → running → done 全覆盖
- RAG 返回含 source 引用

**依赖**：T14, T15, T16, T17

---

#### T25 · E2E 集成测试：多用户 SaaS 流程（2d）`测试`

**目标**：Playwright：注册 → 免费配额耗尽 → 订阅升级 → Pro 功能解锁 → API Key 创建并使用

**关键文件**
- `tests/e2e/saas_flow.spec.ts`

**测试覆盖**
- 配额隔离（用户 A 操作不影响用户 B）
- 支付 Webhook mock 后 tier 升级
- API Key 请求头鉴权 E2E

**依赖**：T19, T20, T21, T22

---

#### T26 · 性能压测（1d）`测试`

**目标**：Locust 并发 50 用户：行情接口 < 200ms P95，回测提交 < 500ms，RAG 首字节 < 2s

**关键文件**
- `tests/load/locustfile.py`

**测试覆盖**
- 行情 API P95 < 200ms
- 回测队列 50 并发不丢任务
- Redis 缓存命中率 > 80%

**依赖**：T07, T09, T10

---

#### T27 · 安全审计（1d）`测试`

**目标**：OWASP Top10 覆盖：SQL 注入 / XSS / CSRF / 越权访问 / 敏感数据泄漏检查

**关键文件**
- `tests/security/auth_bypass.py`
- `tests/security/injection.py`

**测试覆盖**
- 用户 A 无法读取用户 B 持仓（越权）
- SQL 注入参数返回 422 而非 500
- JWT secret 不出现在任何响应头

**依赖**：T05, T06, T11

---

#### T28 · 生产上线 & 灰度验证（1d）`基础设施`

**目标**：数据库全量备份，蓝绿切换，监控面板 30min 静默观察，回滚预案文档

**关键文件**
- `deploy/rollback.sh`
- `docs/go-live-checklist.md`

**测试覆盖**
- 备份恢复演练（恢复到测试环境验证数据一致）
- Nginx reload 零停机验证
- 回滚脚本 < 5min 完成

**依赖**：T24, T25, T26, T27

---

## 六、任务依赖关系总览

```
T01 → T02 → T03
           T04 → T05 → T06 → T07 → T08
                              T07 → T11
                        T06 → T09
                        T06 → T10
               T05 → T12 → T13 → T14 (←T11)
                                → T15 (←T07)
                                → T16 (←T09)
                                → T17 (←T10)
                                → T18 (←T08)
               T05 → T21 → T25
               T06 → T20
               T01 → T23 (←T09)
T14+T15+T16+T17 → T24
T19+T20+T21+T22 → T25
T07+T09+T10     → T26
T05+T06+T11     → T27
T24+T25+T26+T27 → T28
```

---

## 七、优先级说明

T05（JWT 认证）和 T12（前端 API Client）是两个关键路径节点，质量要重点把关，下游任务全部依赖这两个模块。

T09（异步回测）放在 Phase 1 而非 Phase 2，确保前端联调时后端已稳定。

集成测试（T24-T27）并行执行，不互相依赖，可安排 2 人分工。

Phase 0 的 CI/CD（T03）在第 1 周就跑通，后续每次提交自动部署，杜绝环境差异积累。
