# myTrader 项目代码完成度评估

> 评估日期: 2026-04-20（4-26 追加更新）

---

## 一、总体结论

项目整体完成度很高，绝大部分模块包含真实业务逻辑，属于生产级代码。
**两个明确的半成品是 `executor/`（交易执行）和 `risk_manager/`（风控）**，
只有骨架代码。这两个模块恰恰是实盘交易的最后一环，补齐才能形成完整闭环。

---

## 二、完成度高的模块（生产可用）

### 2.1 基础设施

| 模块 | 代码量 | 状态 | 说明 |
|------|--------|------|------|
| config/ | ~460 行 | 完整 | 双环境 DB 连接、全局配置，无遗漏 |
| scheduler/ | 9 文件 | 完整 | DAG 拓扑排序、重试、状态持久化、Webhook 报警 |
| alembic/ | 28 个迁移 | 完整 | 覆盖全部表结构演进 |

### 2.2 API 后端 (FastAPI)

| 子模块 | 规模 | 状态 | 说明 |
|--------|------|------|------|
| routers/ | 25 个路由文件 | 完整 | auth/market/portfolio/strategy/rag/sentiment/agent 等全部有真实逻辑 |
| services/ | 30+ 文件 | 完整 | ReAct AI Agent、SSE 流式、Feishu 集成、LLM 技能链 |
| middleware/ | 6 文件 | 完整 | JWT 认证、Redis 滑动窗口限流、Prometheus 指标、配额管理 |
| models/schemas/ | 各 14 文件 | 完整 | 全部 ORM 模型和 Pydantic schema |
| tasks/ (Celery) | 15 文件 | 完整 | 25+ 定时任务（晨报/晚报/因子/指标/恐慌指数/宏观数据等） |
| core/ | 安全模块 | 完整 | bcrypt + JWT (access/refresh token) |

### 2.3 Web 前端 (Next.js + TypeScript + Tailwind)

| 子模块 | 规模 | 状态 | 说明 |
|--------|------|------|------|
| src/app/ | 20 个页面路由 | 完整 | dashboard/market/strategy/rag/agent/positions/theme-pool 等 |
| src/components/ | 15+ 组件 | 完整 | Agent 聊天面板、信号 Badge、迷你 Sparkline、回测组件等 |
| src/lib/ | API client + stores | 完整 | Axios 拦截器、Zustand 状态管理、TanStack Query |
| src/hooks/ | 6 个自定义 Hook | 完整 | SSE、Agent 聊天、认证守卫等 |

### 2.4 数据分析师 (data_analyst)

| 子模块 | 代码量 | 状态 | 说明 |
|--------|--------|------|------|
| fetchers/ | 4 文件 | 基本完整 | AKShare/Tushare/宏观数据全链路；QMT 路径为 TODO 空壳 |
| indicators/ | 2 文件 | 完整 | 技术指标 + RPS，TA-Lib/pandas 双通道降级 |
| factors/ | 8 文件 | 基本完整 | 6 个因子计算器全部实现；factor_storage 有 2 个运行时 Bug |
| market_monitor/ | 9 文件 | 完整 | SVD 多尺度监控，含重试/降级/冷却期逻辑 |
| sentiment/ | 9 文件 | 完整 | 恐慌指数(7 维)、新闻情感(LLM)、事件检测、Polymarket |
| sw_rotation/ | 2 文件 | 完整 | 两版行业轮动分析 (v1 基础版 + v2 增强版) |

### 2.5 策略师 (strategist)

| 子模块 | 代码量 | 状态 | 说明 |
|--------|--------|------|------|
| xgboost_strategy/ | ~5,285 行 (22 文件) | 完整 | 项目最完整模块，52 维因子 + 滚动训练 + 模拟交易子系统 |
| tech_scan/ | ~4,681 行 (14 文件) | 完整 | 信号检测(725 行)、单股扫描(946 行)、报告 + 图表生成 |
| doctor_tao/ | ~3,612 行 (14 文件) | 基本完整 | RPS 动量策略核心完整；industry_integration.py 为占位 |
| multi_factor/ | ~2,749 行 (8 文件) | 完整 | 因子打分、IC/ICIR 评估、月度再平衡回测 |
| backtest/ | ~1,719 行 (8 文件) | 完整 | 事件驱动引擎，Sharpe/Sortino/Calmar/MaxDD 指标齐全 |
| universe_scanner/ | ~1,261 行 (7 文件) | 完整 | 三层漏斗（全市场->观察池->高优先级） |
| log_bias/ | ~990 行 (12 文件) | 完整 | 含单元测试，5 状态机信号检测 |

### 2.6 投研 RAG (investment_rag)

| 子模块 | 状态 | 说明 |
|--------|------|------|
| report_engine/ | 完整 | 五步法研报 + 技术面分析，Markdown 组装 + 持久化 |
| retrieval/ | 完整 | 混合检索 (ChromaDB dense + BM25 sparse + RRF 融合 + Reranker) |
| embeddings/ | 完整 | DashScope LLMClient + EmbeddingClient |
| ingest/ | 完整 | 文档摄入管道 (loaders/parsers/crawlers) |

### 2.7 测试

| 类型 | 规模 | 说明 |
|------|------|------|
| 单元测试 | 30+ 文件 | 覆盖 auth/agent/portfolio/sentiment/market 等 |
| E2E 测试 | Playwright | 完整用户流程（登录->看板->行情->分析->RAG） |
| 压力测试 | Locust | 登录/K线/RPS/分析多场景 |
| 安全测试 | pytest | 认证绕过、SQL 注入检测 |

---

## 三、半成品 / 骨架模块

### 3.1 executor/（交易执行）-- 纯骨架

- **现状**: 仅 1 个 `__init__.py`（100 行），包含 `Order` dataclass 和 `QMTTrader` 类
- **问题**: `connect()`、`submit_order()`、`cancel_order()`、`get_positions()`、`get_account_info()` 全部为 `TODO + pass`
- **缺失**: 无 QMT API 对接、无网络通信、无订单状态管理、无异常处理
- **评估**: 完成度约 5%

### 3.2 risk_manager/（风控管理）-- 纯骨架

- **现状**: 仅 1 个 `__init__.py`（78 行），包含 `RiskManager` 类
- **问题**: 仅 4 个简单算术方法（止损=入场价x(1-比例)、止盈=入场价x(1+比例)等）
- **缺失**: 无实时监控、无报警、无组合级风控、无回撤管理、无仓位上限强制执行、无 DB 集成
- **评估**: 完成度约 10%

### 3.3 doctor_tao/industry_integration.py -- 占位文件

- **现状**: 3 个核心方法全部返回 dummy 数据
- `get_industry_strength()` 返回硬编码行业代码
- `run_integrated_screener()` 返回空 DataFrame
- **影响**: 行业轮动数据未接入陶博士策略选股流程

---

## 四、已知 Bug（影响运行时）

| 文件 | 行号 | 问题 | 严重度 |
|------|------|------|--------|
| `data_analyst/factors/factor_storage.py` | ~107 | `save_factors()` 缺少 `cursor = conn.cursor()`，运行时 NameError | 高 |
| `data_analyst/factors/factor_storage.py` | ~64 | `CREATE_TABLE_sql` vs `CREATE_table_sql` 变量名大小写不一致，NameError | 高 |
| `data_analyst/fetchers/data_fetch_manager.py` | ~153 | QMT 拉取路径为 TODO 空壳，不执行实际操作 | 中 |
| `data_analyst/sentiment/run_monitor.py` | ~34-43 | CLI 引用 v1 字段（`result.vix` 等），但 fear_index.py 已升为 v2 schema，AttributeError | 高 |

---

## 五、模块完成度概览

```
config/                 [##########] 100%
scheduler/              [##########] 100%
alembic/                [##########] 100%
api/                    [######### ] 95%
web/                    [######### ] 92%
investment_rag/         [######### ] 95%
data_analyst/indicators [##########] 100%
data_analyst/monitor    [##########] 100%
data_analyst/sentiment  [######### ] 95%  (CLI schema 不匹配)
data_analyst/factors    [########  ] 85%  (2 个运行时 Bug)
data_analyst/fetchers   [########  ] 85%  (QMT 路径空壳)
data_analyst/sw_rotation[##########] 100%
strategist/xgboost      [##########] 100%
strategist/tech_scan    [##########] 100%
strategist/multi_factor [##########] 100%
strategist/backtest     [##########] 100%
strategist/doctor_tao   [########  ] 85%  (行业集成占位)
strategist/log_bias     [##########] 100%
strategist/universe_scan[##########] 100%
risk_manager/           [#         ] 10%  -- 纯骨架
executor/               [          ] 5%   -- 纯骨架
tests/                  [######### ] 90%
```

---

## 六、建议优先级

1. **P0 - 修复已知 Bug**: factor_storage 和 sentiment CLI 的运行时错误会阻塞日常数据流水线
2. **P1 - 补齐 risk_manager**: 至少实现组合级风控（最大持仓比例、单日最大亏损、回撤熔断）
3. **P1 - 补齐 executor**: 对接 QMT API，实现订单提交/撤单/持仓查询
4. **P2 - 接入行业轮动**: 将 sw_rotation 数据接入 doctor_tao 策略选股
5. **P2 - 前端增强**: 集成 ECharts/Lightweight Charts 替代表格展示 K 线

---

## 七、2026-04-20 之后新增功能（截至 2026-04-26）

### 7.1 本地模型服务（model-service）[新模块]

**完成度：95%**

新增独立 Docker 服务容器 `mytrader-model-service`（端口 8500），部署两个本地推理模型，
将原本需要调用付费 LLM API 的嵌入和情感分析任务本地化：

| 模型 | 来源 | 用途 | 替换目标 |
|------|------|------|---------|
| BGE-large-zh-v1.5 | BAAI/bge-large-zh-v1.5 | 中文文本嵌入（1024维） | DashScope text-embedding-v4 |
| XLM-RoBERTa Sentiment | cardiffnlp/twitter-xlm-roberta-base-sentiment-multilingual | 多语言情感分类 | qwen3.6-plus LLM |

**降级策略**：本地服务不可用时（5 分钟冷却重试），自动回退到 DashScope API，业务不中断。

**新增文件**：
- `model_service/app/main.py` — FastAPI 应用 + 生命周期管理
- `model_service/app/services/embedding_service.py` — BGE 嵌入实现
- `model_service/app/services/sentiment_service.py` — RoBERTa 情感分类
- `model_service/Dockerfile` — CPU-only 推理容器
- `scripts/download_models.py` — 模型下载工具

### 7.2 微信公众号订阅管理 [新功能]

**完成度：95%**

集成 wechat2rss（本地 SQLite）与 myTrader MySQL，实现公众号内容的订阅管理与 AI 文章筛选同步。

**架构**：
- 后端：`api/routers/wechat_feed.py`（5 个管理端点：列表/添加/删除/同步/导出）
- 同步任务：`api/tasks/ai_wechat_sync.py`（按 34 个 AI 关键词过滤，写入 `ai_wechat_articles` 表）
- 前端：`/data-health` 页面新增"公众号订阅"标签页

**新增 DB 表**：`wechat_feeds`（订阅源）、`ai_wechat_articles`（AI 文章库）

### 7.3 S&P GSCI 商品指数接入 [数据扩充]

通过 yfinance（本机抓取写入线上 DB）新增 S&P GSCI 系列指标：

| 指标 | Ticker | 说明 |
|------|--------|------|
| spgsci | ^SPGSCI | 总指数 |
| spgsci_energy | ^SPGSENTR | 能源（原油/天然气） |
| spgsci_pm | ^SPGSPM | 贵金属（黄金/白银） |
| spgsci_ag | ^SPGSAG | 农产品（小麦/玉米/豆类） |
| spgsci_livestock | ^SPGSLV | 牲畜（活牛/猪肉） |
| spgsci_softs | ^SPGSSO | 软商品（咖啡/糖/棉花） |

另补充单品种期货：天然气(NG=F) / 铜(HG=F) / 白银(SI=F) / 小麦(ZW=F) / 玉米(ZC=F) / 大豆(ZS=F)

### 7.4 AI 晨报 V2（盘前早咖）[流水线升级]

将原有简单晨报升级为三阶段 LLM 管道：

1. **阶段 A**：从公众号原文提取结构化条目（type/direction/tickers）
2. **阶段 B**：批量查询技术因子（RSI/动量/RPS/MACD）+ 近 7 日公告
3. **阶段 C**：LLM 综合生成完整晨报（市场研判/个股信号/板块方向/操作提示/风险提示）

持久化到 `trade_briefing` 表（session=`morning_v2`），同日不重复生成。

### 7.5 零停机部署方案 [基础设施]

- **API**：Gunicorn USR2 信号热重载（替代 docker restart）
- **前端**：蓝绿双容器（nextjs-blue / nextjs-green）+ nginx upstream 热切换
- **容器内无 kill**：使用宿主机 PID 发送信号（slim 镜像无 kill 命令）

### 7.6 前端页面扩充

较 2026-04-20 评估新增/重构页面：

| 路由 | 新增内容 |
|------|---------|
| /data-health | 新增"公众号订阅"标签页（WechatSubscriptionsPanel 组件） |
| /market | 新增 GSCI 商品子指数展示 |
| /candidate-pool | 新增标签系统 + 多维筛选器 + 用户 filter 偏好持久化 |

### 7.7 更新后模块完成度

```
model-service/          [######### ] 95%   新增
data_analyst/fetchers   [#########  ] 88%  (GSCI 指标新增)
data_analyst/sentiment  [######### ] 95%   (本地模型接入)
investment_rag/         [######### ] 97%   (本地 BGE 嵌入接入)
web/                    [######### ] 93%   (20+ 页面，含公众号管理)
api/                    [######### ] 96%   (微信订阅/晨报V2 路由完整)
risk_manager/           [#         ] 10%   -- 仍为骨架，未动
executor/               [          ] 5%    -- 仍为骨架，未动
```
