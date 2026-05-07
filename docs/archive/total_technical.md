# myTrader 个人投研平台 — 技术方案（现状版）

> 最后更新：2026-04-26
> 本文档描述的是**当前实际落地状态**，不再是规划草稿。

---

## 一、项目定位

myTrader 是一个面向个人量化投研的全栈平台，分四大角色：

| 角色 | 模块 | 核心职责 |
|------|------|---------|
| 数据分析师 | `data_analyst/` | 行情抓取、技术指标、因子计算、市场监控、舆情分析 |
| 策略师 | `strategist/` | 选股策略、回测框架、信号生成 |
| 风控师 | `risk_manager/` | 持仓风控（骨架，待补齐） |
| 交易员 | `executor/` | 订单执行（骨架，待补齐） |

另有：统一调度器 `scheduler/`（YAML DAG）、FastAPI Web API、Next.js 前端、投研 RAG、本地模型服务。

---

## 二、实际技术栈

### 后端
- **FastAPI** + SQLAlchemy (aiomysql 异步) + Pydantic v2
- **Celery** + Redis（定时任务 + 异步任务）
- **MySQL**（主存储，双环境：local/online）
- **Qdrant**（向量库，投研 RAG 检索）
- **ChromaDB**（另一套向量存储，RAG 混合检索）
- **JWT**（bcrypt 密码 + access/refresh token 双令牌）

### 前端
- **Next.js 16**（App Router）+ TypeScript
- **Tailwind CSS** + 自研 Design Token 系统
- **TanStack Query**（接口缓存 + 后台刷新）
- **Zustand**（全局状态）
- **Axios**（HTTP 客户端，拦截器自动注入 JWT）
- **ECharts**（K 线图 + 技术指标面板）

### 基础设施
- **Docker Compose**（7 个服务：nginx / nextjs / api / worker / beat / model-service / redis）
- **Nginx**（反向代理，蓝绿部署前端切换）
- **GitHub Actions CI/CD**（push to main → lint/build/test → SSH deploy）
- **Gunicorn + USR2**（API 零停机热重载）
- **蓝绿部署**（Next.js 前端双容器切换，零停机）

---

## 三、系统架构（数据流）

```
数据源层
  AKShare / Tushare / yfinance (本机) / wechat2rss (SQLite)
        |
        v
数据采集层  data_analyst/fetchers/
  macro_fetcher (宏观/商品)  tushare_fetcher  ai_wechat_sync
        |
        v
存储层
  MySQL (主业务数据)    Qdrant/ChromaDB (向量)    Redis (缓存/锁/队列)
        |
        v
计算层  data_analyst/indicators & factors & market_monitor
  技术指标   因子计算   SVD 市场监控   情感分析
        |
        v
策略层  strategist/
  XGBoost 截面预测   多因子   Doctor Tao RPS   技术面扫描   回测引擎
        |
        v
API 层  api/routers/   (FastAPI + Celery)
        |
        v
展示层  web/   (Next.js 16)
```

---

## 四、部署架构

### docker-compose 服务清单

| 服务 | 端口 | 说明 |
|------|------|------|
| nginx | 80/443 | 反向代理，Let's Encrypt 证书，蓝绿前端路由 |
| nextjs | 3000 | Next.js 生产 build |
| api | 8000 | Gunicorn + Uvicorn workers，USR2 热重载 |
| worker | - | Celery worker，与 api 同镜像 |
| beat | - | Celery beat，驱动所有定时任务 |
| model-service | 8500 | 本地模型服务（BGE + RoBERTa），3G 内存限制 |
| redis | 6379 | Broker + Result Backend + 分布式锁 |

### 零停机部署策略

- **API**：Gunicorn USR2 信号热重载，不中断连接
- **前端**：蓝绿双容器（nextjs-blue / nextjs-green），nginx upstream 热切换
- **CI/CD**：GitHub Actions → SSH → git pull + docker compose up --build

---

## 五、调度体系

### 5.1 Celery Beat（服务器端定时任务）

| 任务 | 频率 | 说明 |
|------|------|------|
| `fetch_macro_data_hourly` | 每小时 | AKShare 宏观数据增量拉取（Redis 分布式锁 3300s） |
| `fetch_stock_daily` | 盘后 | 个股日线数据拉取 |
| `calc_factors` | 盘后 | 因子计算（RPS/技术/质量） |
| `calc_svd_monitor` | 盘后 | SVD 市场状态监控 |
| `publish_morning_briefing_v2` | 08:30 Mon-Fri | AI 晨报 V2（盘前早咖三阶段 LLM 管道） |
| `publish_evening_briefing` | 17:00 Mon-Fri | 盘后复盘报告 |
| `sync_ai_wechat_articles` | 定时 | 从 wechat2rss 同步 AI 相关文章 |
| `run_tech_scan` | 盘后 | 技术面扫描，生成预警报告 |

### 5.2 YAML DAG 调度器（scheduler/）

本地按序执行复杂依赖链，补充 Celery Beat 的拓扑编排能力：

```
tasks/
├── 02_macro.yaml      # 宏观数据拉取 → 宏观因子计算 → 仪表盘数据
├── 03_factors.yaml    # 质量因子 → 价值因子 → 动量因子 → 综合评分
├── 04_indicators.yaml # 技术指标 → RPS → 恐慌指数
└── 05_strategy.yaml   # 技术面扫描 → 策略信号 → 飞书推送
```

### 5.3 本机 macOS Crontab

```bash
# 07:30 工作日，yfinance 数据同步（阿里云 ECS 被封 IP，改在本机抓取）
30 7 * * 1-5 DB_ENV=online python /path/to/scripts/yfinance_sync.py
```

---

## 六、数据源全景

### 6.1 AKShare（服务器端）

| 类别 | 代表指标 |
|------|---------|
| A 股指数 | 中证全A / 沪深300 / 中证500 / 中证1000 / 中证红利 |
| 风险指标 | QVIX（50ETF期权波指）、AH 溢价指数 |
| 债券利率 | 中国10Y / 美国2Y/10Y/30Y / 美债期限利差 |
| 货币信贷 | M0/M1/M2 同比、M2 货币供应量 |
| 宏观景气 | 制造业 PMI、CPI 同比、PPI 同比 |
| 资金面 | 北向资金日净流入 |
| 大宗商品 | 布伦特原油、黄金（期货合约价格） |

### 6.2 yfinance（本机抓取，写入线上 DB）

| 分类 | 指标 | Ticker |
|------|------|--------|
| 恐慌系列 | VIX（股票）、GVZ（黄金）、OVX（原油） | ^VIX / ^GVZ / ^OVX |
| 美股 ETF | SPY / QQQ / DIA | 标普500 / 纳指100 / 道指 |
| 大宗 | BTC-USD / 布伦特原油 / 美元指数 DXY | BZ=F / DX-Y.NYB |
| GSCI 商品 | 总指数 + 5 个子指数 | ^SPGSCI / ^SPGSENTR / ^SPGSPM / ^SPGSAG / ^SPGSLV / ^SPGSSO |
| 单品种期货 | 天然气 / 铜 / 白银 / 小麦 / 玉米 / 大豆 | NG=F / HG=F / SI=F / ZW=F / ZC=F / ZS=F |
| A 股 fallback | 中证全A / 上证指数 / 创业板 | 000985.SS / 000001.SS / 399006.SZ |

### 6.3 Tushare
个股日线 OHLCV、基本面数据（财务三表）、RPS 基础行情。

### 6.4 wechat2rss（SQLite）
微信公众号订阅内容，通过本地 SQLite 读取文章，同步 AI 相关文章到 MySQL。

---

## 七、本地模型服务（model-service）

### 7.1 背景与动机

原有嵌入（embedding）和情感分析均依赖 DashScope API，每次调用付费且有延迟。
引入独立 `model-service` 容器，部署两个本地小模型，**对嵌入和情感分析实现本地化替代**，
DashScope 仅作降级备份。

### 7.2 模型清单

| 模型 | 来源 | 维度 | 用途 |
|------|------|------|------|
| BGE-large-zh-v1.5 | BAAI/bge-large-zh-v1.5 | 1024 维 | 中文文本嵌入、投研文献检索 |
| XLM-RoBERTa | cardiffnlp/twitter-xlm-roberta-base-sentiment-multilingual | - | 多语言情感分类（含中文） |

- 纯 CPU 推理（`device=-1`），镜像约 3G 内存限制
- 模型文件挂载到 `/data/models`（只读），独立于代码
- 下载工具：`scripts/download_models.py`

### 7.3 服务接口

**端口**：8500（容器内），Docker Compose 服务名 `mytrader-model-service`

```
GET  /health      → {status, models, memory_mb}
POST /embed       → {texts, text_type}  → {embeddings, dimensions, model, count}
POST /sentiment   → {title, content}    → {sentiment, confidence, sentiment_strength}
```

嵌入时 `text_type="query"` 会自动添加 BGE 检索指令前缀，提升检索精度。

### 7.4 功能替换对照

| 功能 | 替换前 | 替换后 | 收益 |
|------|--------|--------|------|
| 文本嵌入 | DashScope text-embedding-v4（付费） | 本地 BGE-large-zh（免费） | 延迟降低、零 API 费用 |
| 情感分析 | DashScope qwen3.6-plus（付费） | 本地 XLM-RoBERTa（免费） | 高吞吐批量处理 |
| 批量摄入 | 受 API 配额限制 | 本地无限制 | 可全量重算 |

### 7.5 降级策略（双通道）

`investment_rag/embeddings/embed_model.py` 的 `EmbeddingClient`：

1. 首先调用本地 `/embed`（超时 3s）
2. 失败后标记 `_local_available=False`，5 分钟内不再重试
3. 自动降级至 DashScope `text-embedding-v4`

`data_analyst/sentiment/sentiment_analyzer.py` 的 `SentimentAnalyzer`：

1. 首先调用本地 `/sentiment`
2. 失败后降级至 qwen3.6-plus LLM 调用

---

## 八、AI 早报系统（V2 盘前早咖）

### 8.1 三阶段 LLM 管道

**阶段 A — 结构化提取**
- 输入：公众号晨报原文（JSON 导出或 DB 摘要）
- 输出：JSON 条目数组，字段含 type / content / direction / tickers
- 若提取条目 < 3 条，整个流程中止

**阶段 B — 数据聚合**
- 从条目 tickers 查询技术因子（RSI / 动量 / RPS / MACD）
- 查询近 7 日重大公告（research_announcements）

**阶段 C — 晨报生成**
- LLM 综合条目摘要 + 技术数据 + 公告 → 生成完整晨报
- 格式：市场研判 / 个股信号分析 / 板块方向 / 操作提示 / 风险提示
- 字数控制：每只个股 <= 150 字，全文 <= 600 字

### 8.2 缓存与持久化

- 表：`trade_briefing`，字段：session / brief_date / content / structured_data
- 同日同 session 不重复生成（force=True 可强制重算）
- 晨报 session 类型：`morning_v2`

---

## 九、前端页面（Next.js 16 App Router）

| 路由 | 功能 | 认证 |
|------|------|------|
| /dashboard | 宏观总览 + 大宗资产 + 持仓快照 | 登录 |
| /market | 全球资产行情（含 GSCI 子指数） | 登录 |
| /portfolio | 组合管理 + PnL 分析 | 登录 |
| /positions | 个仓位持仓明细 | 登录 |
| /analysis | 个股技术面 + 因子 + 公告分析 | 登录 |
| /strategy | XGBoost / 多因子策略 + 回测 | 登录 |
| /rag | 智能研报（RAG 问答 + 五步法） | 登录 |
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

---

## 十、API 后端（FastAPI 路由）

| Router 文件 | 前缀 | 主要功能 |
|-------------|------|---------|
| health.py | /health | 健康检查 |
| auth.py | /api/auth | 注册 / 登录 / 刷新 / 获取当前用户 |
| market.py | /api/market | K 线 / RPS / 指标 / 搜索 |
| analysis.py | /api/analysis | 技术面 / 基本面分析 |
| strategy.py | /api/strategy | 策略 CRUD / 回测提交（SSE 进度） |
| rag.py | /api/rag | 研报问答（SSE 流式） |
| portfolio.py | /api/portfolio | 持仓聚合 / PnL |
| admin.py | /api/admin | 用户管理（仅 admin） |
| api_keys.py | /api/api-keys | API Key CRUD / X-API-Key 鉴权 |
| subscription.py | /api/subscription | 订阅计划 / 升级 / Webhook |
| wechat_feed.py | /api/wechat-feed | 公众号订阅管理（列表/添加/删除/同步） |
| agent.py | /api/agent | AI Agent 对话（ReAct 框架，内置多工具） |
| briefing.py | /api/briefing | 晨报 / 复盘报告生成与查询 |
| sentiment.py | /api/sentiment | 舆情分析 API |

---

## 十一、微信公众号订阅管理

### 架构

```
wechat2rss (Docker / SQLite)          myTrader MySQL
  ├─ rsses 表（订阅源）     ────→    wechat_feeds 表（镜像）
  └─ articles 表（文章库）  ────→    ai_wechat_articles 表（AI 筛选后）
```

### 数据流

1. wechat2rss 自动抓取订阅公众号文章，存入 SQLite `articles` 表
2. `sync_ai_wechat_articles` Celery 任务每日读取 SQLite，按 34 个 AI 关键词过滤
3. 命中文章写入 MySQL `ai_wechat_articles`（o_id 唯一键防重复）
4. `/data-health` 页面公众号标签页提供订阅管理 UI（添加/删除/同步）

---

## 十二、投研 RAG 系统

| 组件 | 技术 | 说明 |
|------|------|------|
| 文档摄入 | loaders / parsers / crawlers | 研报 PDF、财报、公告、网页 |
| 嵌入 | BGE-large-zh（本地优先）/ DashScope fallback | 1024 维向量 |
| 向量检索 | ChromaDB dense + BM25 sparse + RRF 融合 + Reranker | 混合检索 |
| 生成 | qwen3.6-plus（统一 LLM） | SSE 流式输出 |
| 报告框架 | 五步法（商业模式/护城河/管理层/财务/估值）+ 一页纸研报 | Markdown 组装 |

---

## 十三、XGBoost 截面预测策略

### 13.1 核心思路

基于 MASTER 论文（AAAI 2024），构建 52 维技术因子截面，用 XGBoost 预测个股未来 5 日收益排名，
每 5 天调仓选 Top-N 只股票等权持有。

### 13.2 因子体系（52 维）

| 类别 | 数量 | 代表因子 |
|------|------|---------|
| 价量 | 10 | ret_1d / ret_5d / amplitude_5d / vol_ratio_5d |
| 动量 | 8 | momentum_20d / momentum_slope_10d / momentum_accel |
| 波动率 | 6 | atr_norm_14 / hist_vol_20d / vol_change_10d |
| 技术指标 | 12 | rsi_14 / macd_hist / kdj_k / cci_14 / obv_slope |
| 均线形态 | 10 | ma5_bias / ma_bull_score / body_ratio / new_high_20d |
| 交互因子 | 6 | mom_vol_cross / adx_rsi_cross（两个因子的乘积/比值） |

截面预处理：**MAD 去极值（5 倍阈值）+ Z-Score 标准化**

### 13.3 模型训练参数

| 参数 | 值 | 说明 |
|------|-----|------|
| train_window | 120 交易日 | 约 6 个月训练数据 |
| predict_horizon | 5 | 预测未来 5 日收益率 |
| roll_step | 5 | 每 5 天重训一次 |
| n_estimators | 50 | 树数量 |
| max_depth | 4 | 防过拟合 |
| learning_rate | 0.05 | |
| subsample | 0.8 | 行采样率 |
| colsample_bytree | 0.8 | 列采样率 |

训练窗口严格不含预测日期，避免信息泄露。

### 13.4 IC 评估体系

| 指标 | 含义 | A 股预期范围 |
|------|------|------------|
| IC | Pearson 预测-实际相关系数 | 0.03 ~ 0.05 |
| ICIR | IC 均值 / IC 标准差 | 0.3 ~ 0.5 |
| RankIC | Spearman 秩相关 | 0.04 ~ 0.06 |
| RankICIR | RankIC 稳定性 | - |

### 13.5 模拟交易子系统

`strategist/xgboost_strategy/paper_trading/` 提供完整的纸面交易流程：
信号生成 → 仓位管理 → 每日结算 → 绩效评估，可独立运行验证策略实盘可行性。

### 13.6 使用方式

```bash
# 安装依赖
pip install xgboost scipy scikit-learn
brew install ta-lib && pip install TA-Lib

# 运行策略（回测 + IC 评估 + 可视化）
python -m strategist.xgboost_strategy.run_strategy

# 输出产物（output/xgboost/）
# signals.csv / portfolio_returns.csv / factor_ic.csv
# ic_analysis.png / portfolio_performance.png / factor_ic.png
# strategy_report.md
```

---

## 十四、模块完成度（截至 2026-04-26）

```
config/                 [##########] 100%
scheduler/              [##########] 100%
alembic/                [##########] 100%
api/                    [######### ] 95%   (支付集成为占位)
web/                    [######### ] 93%   (20+ 页面)
model-service/          [######### ] 95%   新增
investment_rag/         [######### ] 95%
data_analyst/indicators [##########] 100%
data_analyst/monitor    [##########] 100%
data_analyst/sentiment  [######### ] 95%
data_analyst/factors    [########  ] 85%   (factor_storage 有 2 个 Bug)
data_analyst/fetchers   [########  ] 85%   (QMT 路径空壳)
data_analyst/sw_rotation[##########] 100%
strategist/xgboost      [##########] 100%
strategist/tech_scan    [##########] 100%
strategist/multi_factor [##########] 100%
strategist/backtest     [##########] 100%
strategist/doctor_tao   [########  ] 85%   (行业集成占位)
strategist/log_bias     [##########] 100%
strategist/universe_scan[##########] 100%
risk_manager/           [#         ] 10%   -- 纯骨架
executor/               [          ] 5%    -- 纯骨架
tests/                  [######### ] 90%
```

---

## 十五、待完成事项（P0-P2）

| 优先级 | 事项 |
|--------|------|
| P0 | `factor_storage.py` 两处 NameError Bug（cursor / CREATE_TABLE_sql 大小写） |
| P0 | `sentiment/run_monitor.py` CLI 字段与 v2 schema 不匹配（AttributeError） |
| P1 | `risk_manager/` 补充组合级风控（最大持仓比例、单日亏损熔断、回撤管理） |
| P1 | `executor/` 对接 QMT API（订单提交/撤单/持仓查询） |
| P2 | `doctor_tao/industry_integration.py` 接入真实行业轮动数据 |
| P2 | 一页纸研报导出下载功能（.md 文件） |
| P2 | 支付集成（Stripe 或微信支付） |
