# myTrader 测试流程说明

## 当前服务状态

| 服务 | 地址 | 状态 | 说明 |
|------|------|------|------|
| myTrader API | http://localhost:8001 | **运行中** | FastAPI 后端，DB 离线 |
| Next.js 前端 | http://localhost:3001 | **运行中** | React 前端 |
| Redis | localhost:6379 | **运行中** | 限流/缓存 |
| MySQL | 100.119.128.104:3306 | **离线** | 需 VPN/内网连接 |

> **注意**: MySQL 当前无法连接。所有需要数据库的接口（登录、注册、研究数据）将返回 500 错误。
> 无需 DB 的接口（健康检查、文档、订阅套餐）可正常访问。

---

## 服务启动命令

```bash
# 1. 确认 Redis 已运行
redis-cli PING   # 应返回 PONG

# 2. 启动 myTrader API (port 8001)
cd /Users/zhaobo/data0/person/myTrader
PYTHONPATH=. DB_ENV=online uvicorn api.main:app --reload --host 0.0.0.0 --port 8001

# 3. 启动前端 (port 3001)
cd /Users/zhaobo/data0/person/myTrader/web
node_modules/.bin/next dev --port 3001
```

---

## 阶段一：无 DB 可测试的接口

### 1.1 健康检查 & 基础信息

```bash
# 服务根路径
curl http://localhost:8001/
# 返回: {"name":"myTrader API","version":"0.1.0","docs":"/docs"}

# 健康检查
curl http://localhost:8001/health
# 返回: {"status":"degraded","redis":"ok","db":"<error>"}
# 说明: status=degraded 是正常的（DB 离线）

# 应用指标
curl http://localhost:8001/metrics

# Swagger API 文档 (浏览器打开)
open http://localhost:8001/docs

# ReDoc 文档
open http://localhost:8001/redoc
```

### 1.2 订阅套餐（无需认证）

```bash
# 查看所有套餐
curl http://localhost:8001/api/subscription/plans
# 返回: {"plans":{"free":{"price":0,"daily_quota":50},"pro":{"price":99,"daily_quota":1000}}}
```

---

## 阶段二：需要 DB 的完整测试流程（DB 在线后执行）

### 2.1 用户注册 & 登录

```bash
# 注册新用户
curl -X POST http://localhost:8001/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"Test1234!"}'

# 登录获取 JWT Token
curl -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test1234!"}'
# 返回: {"access_token":"eyJ...","token_type":"bearer","user":{"id":1,"tier":"free"}}

# 保存 Token（后续接口使用）
TOKEN="eyJ..."
```

### 2.2 查看当前用户信息

```bash
curl http://localhost:8001/api/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

---

## 阶段三：五截面分析框架 API 测试

所有研究类接口都需要 JWT 认证。以 **600519**（贵州茅台）为示例。

### 3.1 基本面分析

```bash
# 查询已缓存的基本面快照（从 fundamental_snapshots 表读取）
curl "http://localhost:8001/api/research/fundamental/600519" \
  -H "Authorization: Bearer $TOKEN"

# 强制刷新：重新计算并写入数据库
curl -X POST "http://localhost:8001/api/research/fundamental/600519/refresh" \
  -H "Authorization: Bearer $TOKEN"
# 返回: {code, snap_date, pe_ttm, roe, revenue_yoy, earnings_quality_score,
#         valuation_score, growth_score, composite_score, label}
```

### 3.2 估值分析（8 种方法并行）

```bash
curl "http://localhost:8001/api/research/valuation/600519" \
  -H "Authorization: Bearer $TOKEN"
# 返回: {code, current_market_cap_yi, methods:[{name, fair_value, upside, confidence}]}
# 涵盖: PE收益法, PB净资产法, FCF收益率法, 三阶段DCF, Gordon隐含增长率,
#        天花板矩阵, 清算价值法, 重置成本法
```

### 3.3 情绪面分析

```bash
# 查看情绪事件列表（最近30条）
curl "http://localhost:8001/api/research/sentiment/600519/events" \
  -H "Authorization: Bearer $TOKEN"

# 新增情绪事件
curl -X POST "http://localhost:8001/api/research/sentiment/events" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "600519",
    "event_text": "茅台宣布提价10%，超预期",
    "direction": "positive",
    "magnitude": "high",
    "category": "earnings"
  }'
# direction 可选: positive / negative / neutral
# magnitude 可选: high / medium / low
# category 可选: capital / earnings / policy / geopolitical / industry / technical / shareholder

# 验证事件（标记为已核实）
curl -X PUT "http://localhost:8001/api/research/sentiment/events/1/verify" \
  -H "Authorization: Bearer $TOKEN"
```

### 3.4 综合评分（五截面加权）

```bash
# 查询综合评分（从 composite_scores 表读取最新记录）
curl "http://localhost:8001/api/research/composite/600519" \
  -H "Authorization: Bearer $TOKEN"

# 重新计算综合评分
curl -X POST "http://localhost:8001/api/research/composite/600519/compute" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "technical_score": 72,
    "fund_flow_score": 65,
    "fundamental_score": 80,
    "sentiment_score": 55,
    "capital_cycle_phase": 3,
    "pe_quantile": 0.45,
    "founder_reducing": false,
    "technical_breakdown": false
  }'
# 返回: {
#   composite_score: 70.5,       -- 五截面加权分
#   direction: "bull",           -- strong_bull/bull/neutral/bear/strong_bear
#   rule_override: null,         -- 规则覆盖（如有）
#   weight_boost: 1.0,           -- 权重加成
#   notes: []                    -- 提示信息
# }
```

**综合评分权重**:

| 截面 | 权重 |
|------|------|
| 技术面 | 15% |
| 资金面 | 20% |
| 基本面 | 30% |
| 情绪面 | 15% |
| 资本周期 | 20% |

**跨截面规则（优先级从高到低）**:

| 条件 | 结果 |
|------|------|
| 资本周期 Phase 4 且 PE 分位数 > 80% | 强制 strong_bear |
| 创始人减持 且 技术面破位 | 强制 bear |
| Phase 3 且 基本面 > 70 | 得分 ×1.3 加成 |
| Phase 2 且 情绪面 < 45 | 提示等待入场时机 |

### 3.5 自选股管理

```bash
# 查看活跃自选股列表
curl "http://localhost:8001/api/research/watchlist" \
  -H "Authorization: Bearer $TOKEN"

# 添加自选股
curl -X POST "http://localhost:8001/api/research/watchlist" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "600519",
    "tier": "deep",
    "thesis": "消费升级核心标的，ROE稳定，资本周期处于 Phase2 成长期"
  }'
# tier 可选: deep（深度研究） / standard（标准跟踪） / watch（观察池）

# 调整观察层级
curl -X PUT "http://localhost:8001/api/research/watchlist/600519/tier" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tier": "standard"}'

# 更新投资论点
curl -X PUT "http://localhost:8001/api/research/watchlist/600519/thesis" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"thesis": "估值合理，等待情绪面改善"}'

# 移除自选股（软删除）
curl -X DELETE "http://localhost:8001/api/research/watchlist/600519" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 阶段四：市场数据 API 测试

```bash
# K线数据（最近30条）
curl "http://localhost:8001/api/market/kline?code=600519&limit=30" \
  -H "Authorization: Bearer $TOKEN"

# 技术指标
curl "http://localhost:8001/api/market/indicators?code=600519" \
  -H "Authorization: Bearer $TOKEN"

# RPS 强度（相对强度）
curl "http://localhost:8001/api/market/rps?code=600519" \
  -H "Authorization: Bearer $TOKEN"

# 搜索股票
curl "http://localhost:8001/api/market/search?q=茅台" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 阶段五：前端页面测试

访问 http://localhost:3001

| 页面 | 路径 | 说明 |
|------|------|------|
| 登录 | /login | 使用注册账号登录 |
| 注册 | /register | 新用户注册 |
| 主页/Dashboard | / | 登录后的主面板 |
| K线行情 | /market | 股票行情查看 |
| 策略回测 | /strategy | 回测任务管理 |
| 投研报告 | /research | RAG 投研系统 |

前端 API 接口地址配置在 `web/.env.local`（或 `web/next.config.ts`）中，如与后端端口不匹配，
需修改 `NEXT_PUBLIC_API_BASE_URL=http://localhost:8001`。

---

## 故障排查

### MySQL 连接失败

```
症状: GET /health 返回 status=degraded，db 字段有 OperationalError
原因: MySQL 服务器 100.119.128.104 在当前网络环境下不可达
解决: 连接 VPN / 切换到有访问权限的网络，或本地启动 MySQL
```

### aiomysql 模块缺失

```bash
pip install aiomysql
```

### 前端 next 命令找不到

```bash
cd web && npm install
```

### 端口被占用

```bash
# 查看端口占用
lsof -i :8001
# 换用其他端口
PYTHONPATH=. uvicorn api.main:app --port 8002
```

---

## Swagger UI 完整测试流程（推荐）

1. 打开 http://localhost:8001/docs
2. 找到 `POST /api/auth/register` → 注册账号
3. 找到 `POST /api/auth/login` → 登录，复制 `access_token`
4. 点击右上角 **Authorize** 按钮 → 输入 `Bearer <token>`
5. 依次测试各 `/api/research/*` 接口
