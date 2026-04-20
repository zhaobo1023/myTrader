# 风控框架 V2 -- 分层风控体系设计

## 1. 背景与目标

### 1.1 现状

myTrader 项目中风控能力分散在多处：

| 位置 | 能力 | 局限 |
|---|---|---|
| `risk_manager/__init__.py` | 止损/止盈/仓位大小计算 | 纯数学函数，无 DB 集成，无实际扫描 |
| `config/settings.py` | 风控参数 (MAX_POSITION_PCT 等) | 仅静态阈值 |
| `api/routers/positions.py` | `/risk-scan` 端点 | 依赖外部 trader 项目的 scanner，跨项目导入 |
| `data_analyst/sentiment/fear_index.py` | 恐慌指数 (7维) | 宏观信号，未与持仓风控联动 |
| `data_analyst/market_monitor/` | SVD 市场状态 | 市场结构分析，未参与风控决策 |
| `api/services/llm_skills/portfolio_doctor.py` | LLM 持仓诊断 | 集中度计算，但依赖 LLM 调用 |

**核心问题：**
- 风控能力外挂在 trader 项目，跨项目导入不可靠
- 宏观(fear_index)、市场结构(SVD)、行业估值等信号已有，但未形成分层决策链
- 缺少个股基本面恶化预警（财报、负面新闻）
- 缺少数据依赖的自动检查/触发

### 1.2 目标

在 myTrader 项目内构建完整的**5 层风控体系**，复用已有数据资产：

```
L1 宏观/系统性风险  -->  整体仓位水位
L2 市场状态/相关性  -->  组合分散度
L3 行业风险暴露     -->  行业集中度
L4 个股基本面       -->  个股持仓建议
L5 交易执行         -->  下单拦截
```

参考胡猛《风和投资笔记》多层风控思想：跨市场分散、跨行业对冲、仓位梯度 2%-8%、3D-5M 分析模型。

---

## 2. 代码组织

### 2.1 模块位置

遵循项目惯例，分析计算模块放在 `data_analyst/` 下，API 层放在 `api/` 下：

```
data_analyst/
    risk_assessment/                  # 新建 -- 风控评估核心
        __init__.py
        config.py                     # 阈值配置
        schemas.py                    # 数据结构 (dataclass)
        data_deps.py                  # 数据依赖检查 + 自动触发
        assessors/
            __init__.py
            base.py                   # BaseAssessor 基类
            macro.py                  # L1 宏观风险
            regime.py                 # L2 市场状态/相关性
            sector.py                 # L3 行业风险暴露
            stock.py                  # L4 个股基本面
            execution.py              # L5 交易执行规则
        scanner.py                    # 扫描器 -- 串联 L1-L5
        report.py                     # Markdown 报告生成
        storage.py                    # 结果持久化

api/
    routers/risk.py                   # 新建 -- /api/risk/ 路由
    services/risk_service.py          # 新建 -- 风控业务逻辑

scheduler/
    adapters.py                       # 追加 run_risk_assessment 适配器

tasks/
    10_risk.yaml                      # 新建 -- 风控扫描调度
```

### 2.2 与现有模块的关系

```
                     data_analyst/risk_assessment/
                              |
            +-------+---------+---------+--------+
            |       |         |         |        |
     fear_index  svd_state  sw_valuation  financials  news_sentiment
     (已有)      (已有)      (已有)        (已有)       (已有)
```

新模块是现有数据管道的**消费者**，不修改任何已有模块，仅读取它们产出的表。

---

## 3. 分层架构详细设计

### 3.1 L1 -- 宏观/系统性风险

**目的：** 评估系统性威胁，决定整体仓位水位。

**数据源（全部已有）：**

| 数据 | 表 | 字段 | 产出模块 |
|---|---|---|---|
| 恐惧指数 | `trade_fear_index` | `fear_greed_score`, `market_regime` | `sentiment/fear_index.py` |
| VIX / QVIX | `macro_data` | indicator='vix' / 'qvix' | `fetchers/macro_fetcher.py` |
| 北向资金 | `macro_data` | indicator='north_flow' | `fetchers/macro_fetcher.py` |
| 美债利差 | `macro_data` | indicator='us_10y_2y_spread' | `fetchers/macro_fetcher.py` |
| 美元指数 | `macro_data` | indicator='dxy' | `fetchers/macro_fetcher.py` |
| 衍生因子 | `macro_factors` | oil_mom_20, north_flow_5d | `factors/macro_factor_calculator.py` |

**评分逻辑：**

```python
class MacroRiskAssessor(BaseAssessor):
    """
    6 个维度加权评分，输出 0-100 风险分。
    直接复用 fear_index 的计算结果 + macro_data 原始指标。
    """

    WEIGHTS = {
        'fear_index': 0.30,      # 恐惧指数 (已是7维合成)
        'vix': 0.20,             # 波动率
        'northflow': 0.15,       # 北向资金趋势
        'yield_spread': 0.15,    # 美债利差
        'commodity': 0.10,       # 大宗异动
        'fx': 0.10,              # 人民币汇率
    }
```

**仓位水位映射：**

| 宏观风险分 | 建议仓位上限 | 说明 |
|---|---|---|
| 0-30 | 100% | 环境友好 |
| 30-50 | 80% | 略有风险 |
| 50-70 | 60% | 风险偏高 |
| 70-85 | 40% | 高风险 |
| 85-100 | 30% | 极端风险，仅保留底仓 |

---

### 3.2 L2 -- 市场状态/相关性

**目的：** 判断市场齐涨齐跌程度 + 持仓相关性，评估分散化是否有效。

**数据源：**

| 数据 | 表 | 产出模块 |
|---|---|---|
| SVD 市场状态 | `trade_svd_market_state` | `market_monitor/run_monitor.py` |
| 个股日线 | `trade_stock_daily` | `fetchers/tushare_fetcher.py` |

**评分逻辑：**

```python
class RegimeRiskAssessor(BaseAssessor):
    """
    市场状态 (40%) + 突变检测 (15%) + 持仓相关性矩阵 (45%)
    """
    def assess(self, position_codes: List[str]) -> RegimeRiskResult:
        # 1. 全A市场状态 -- 直接读 trade_svd_market_state
        #    齐涨齐跌(F1>50%) -> 85分, 板块分化 -> 50分, 个股行情 -> 20分
        # 2. is_mutation 突变 -> 80分
        # 3. 持仓相关性 -- 从 trade_stock_daily 取60天收盘价，计算 pairwise correlation
        #    avg_corr > 0.6 -> 85分, 0.4-0.6 -> 55分, <0.4 -> 25分
```

**输出：** 风险分 + 市场状态 + 高相关股票对列表

---

### 3.3 L3 -- 行业风险暴露

**目的：** 检查持仓在行业维度的集中度和估值风险。

**数据源：**

| 数据 | 表 | 产出模块 |
|---|---|---|
| 行业分类 | `trade_stock_basic` | `fetchers/sw_industry_fetcher.py` |
| 行业估值 | `sw_industry_valuation` | `fetchers/sw_industry_valuation_fetcher.py` |
| 行业 SVD | `trade_svd_market_state` (universe_type='SW_L1') | `market_monitor/` |

**评分逻辑：**

```python
class SectorRiskAssessor(BaseAssessor):
    """
    行业集中度 (35%) + 高估暴露 (30%) + 行业内聚性 (20%) + 跨行业对冲 (15%)
    """
    def assess(self, positions: List[dict]) -> SectorRiskResult:
        # 1. 最大行业占比 >50% -> 85分, >30% -> 60分
        # 2. 高估行业(valuation_score>70)持仓占比
        # 3. 最大行业的 SVD F1 (内部齐涨齐跌 = 更高风险)
        # 4. 持仓覆盖几个不相关大类(周期/消费/科技/金融)
```

---

### 3.4 L4 -- 个股基本面

**目的：** 逐只检查财务健康、估值、新闻、技术面、动量。

**数据源（全部已有）：**

| 数据 | 表 | 产出模块 |
|---|---|---|
| 财报 | `trade_stock_financial`, `financial_income` | `financial_fetcher/` |
| 实时估值 | `trade_stock_daily_basic` | `fetchers/daily_basic_fetcher.py` |
| 新闻情绪 | `trade_news_sentiment` | `sentiment/news_fetcher.py` + `sentiment_analyzer.py` |
| 事件信号 | `trade_event_signal` | `sentiment/event_detector.py` |
| RPS 动量 | `trade_stock_rps` | `indicators/rps_calculator.py` |
| 技术指标 | `trade_technical_indicator` | `indicators/technical.py` |
| 因子 | `trade_stock_factor` | `factors/` |

**评分逻辑（每只股票）：**

```python
class StockFundamentalAssessor(BaseAssessor):
    """
    5 个维度, 每只股票独立评分:
    - 财务健康 (25%): 净利润增速, ROE, 毛利率变化
    - 估值水平 (20%): PE/PB vs 行业分位
    - 新闻情绪 (15%): 近7天负面新闻/事件信号
    - 技术止损 (25%): 价格vs成本价, MA60, MACD, RSI
    - 动量衰减 (15%): rps_slope, rps_250/20
    """
```

**止损策略（参考胡猛仓位梯度）：**

| 持仓级别 | 仓位范围 | 止损线 | 说明 |
|---|---|---|---|
| L1 核心 | 5%-8% | -15% | 深度研究的长期持仓 |
| L2 卫星 | 2%-5% | -8% | 趋势跟随/短期机会 |

---

### 3.5 L5 -- 交易执行

**目的：** 下单前的最后拦截，保留现有 `risk_manager/` 的逻辑并扩展。

将现有 `risk_manager/RiskManager` 的 4 个方法整合进 `ExecutionRiskAssessor`，并增加：
- 持仓数上限检查 (ConcentrationLimit)
- ST 黑名单检查
- 涨跌停检测 (PriceLimitGuard)
- 单笔金额上限 (OrderAmountCap)
- ATR 仓位缩放
- 日亏损熔断

L1-L4 的输出会动态调整 L5 的参数：
- L1 宏观风险高 -> 降低 max_positions、收紧 single_position_limit
- L2 高相关性 -> 收紧 single_position_limit
- L4 个股风险高 -> 降低该股的 max_pct

---

## 4. 数据依赖与自动触发

### 4.1 设计

生成完整风控报告需要多张表最新数据。扫描前先检查，缺失时自动触发对应 fetcher。

```python
class DataDependencyChecker:
    DEPENDENCIES = [
        {
            'name': '行情数据',
            'table': 'trade_stock_daily',
            'date_column': 'trade_date',
            'max_delay_days': 1,
            'trigger': None,  # 依赖 Tushare，无法自动补充
            'critical': True,
        },
        {
            'name': '行业估值',
            'table': 'sw_industry_valuation',
            'date_column': 'trade_date',
            'max_delay_days': 1,
            'trigger': 'data_analyst.fetchers.sw_industry_valuation_fetcher.run_daily',
        },
        {
            'name': 'SVD市场状态',
            'table': 'trade_svd_market_state',
            'date_column': 'calc_date',
            'max_delay_days': 1,
            'trigger': 'data_analyst.market_monitor.run_monitor.main',
        },
        {
            'name': '恐惧指数',
            'table': 'trade_fear_index',
            'date_column': 'trade_date',
            'max_delay_days': 2,
            'trigger': None,  # 由 sentiment scheduler 自动更新
        },
        {
            'name': '技术指标',
            'table': 'trade_technical_indicator',
            'date_column': 'trade_date',
            'max_delay_days': 1,
            'trigger': None,
        },
        {
            'name': 'RPS指标',
            'table': 'trade_stock_rps',
            'date_column': 'trade_date',
            'max_delay_days': 1,
            'trigger': None,
        },
        {
            'name': '新闻情绪',
            'table': 'trade_news_sentiment',
            'date_column': 'publish_time',
            'max_delay_days': 3,
            'trigger': None,
        },
    ]

    def check_and_trigger(self) -> List[DataStatus]:
        """检查各表最新日期，缺失且可触发的自动补充。"""
        ...
```

### 4.2 报告中展示数据状态

```markdown
## 数据状态
| 数据源 | 最新日期 | 延迟 | 状态 |
|---|---|---|---|
| 行情数据 | 2026-04-18 | 0天 | OK |
| 行业估值 | 2026-04-17 | 1天 | OK |
| SVD市场状态 | 2026-04-16 | 2天 | 已自动触发 |
```

---

## 5. API 与调度集成

### 5.1 API 端点

新建 `api/routers/risk.py`，替代现有的 `/api/positions/risk-scan`：

```python
# GET /api/risk/scan          -- 触发完整分层扫描
# GET /api/risk/macro          -- 仅宏观层
# GET /api/risk/report         -- Markdown 报告
# POST /api/risk/trigger-deps  -- 手动触发数据依赖检查
```

路由使用 `run_in_executor` 包装同步计算（与现有 positions/risk-scan 模式一致）。

### 5.2 Service 层

新建 `api/services/risk_service.py`：

```python
from data_analyst.risk_assessment.scanner import scan_portfolio_v2
from data_analyst.risk_assessment.report import generate_report_v2

class RiskService:
    @staticmethod
    def run_scan(user_id: int, env: str = 'online') -> dict:
        return scan_portfolio_v2(user_id=user_id, env=env)

    @staticmethod
    def get_report(user_id: int, env: str = 'online') -> str:
        return generate_report_v2(user_id=user_id, env=env)
```

### 5.3 调度任务

新建 `tasks/10_risk.yaml`：

```yaml
tasks:
  - id: risk_scan_report
    name: "Daily risk assessment report"
    module: scheduler.adapters
    func: run_risk_assessment
    tags: [risk, daily]
    schedule: "18:30"
    depends_on:
      - calc_technical_indicator
      - calc_rps
      - calc_log_bias
    params:
      user_id: 7
```

在 `scheduler/adapters.py` 追加：

```python
def run_risk_assessment(user_id: int = 7, dry_run: bool = False, env: str = 'online'):
    if dry_run:
        logger.info("[DRY-RUN] run_risk_assessment")
        return
    from scheduler.task_logger import TaskLogger
    from data_analyst.risk_assessment.scanner import scan_portfolio_v2
    from data_analyst.risk_assessment.report import generate_report_v2

    with TaskLogger('risk_assessment', 'risk', env=env):
        result = scan_portfolio_v2(user_id=user_id, env=env)
        report = generate_report_v2(user_id=user_id, env=env)
        # 推送到 inbox
        from api.services.inbox_service import create_message
        create_message(user_id=user_id, title='持仓风控日报', content=report, msg_type='risk_report')
```

---

## 6. 数据结构

```python
# data_analyst/risk_assessment/schemas.py

@dataclass
class RiskScore:
    """统一风险评分"""
    score: float          # 0-100
    level: str            # LOW / MEDIUM / HIGH / CRITICAL
    details: dict
    suggestions: List[str]

@dataclass
class MacroRiskResult(RiskScore):
    suggested_max_exposure: float  # 0.3~1.0

@dataclass
class RegimeRiskResult(RiskScore):
    market_state: str          # 齐涨齐跌 / 板块分化 / 个股行情
    avg_correlation: float
    high_corr_pairs: List[tuple]

@dataclass
class SectorRiskResult(RiskScore):
    industry_breakdown: dict   # {行业名: 占比}
    overvalued_industries: List[str]

@dataclass
class StockRiskResult:
    stock_code: str
    stock_name: str
    score: float
    sub_scores: dict           # {financial, valuation, news, technical, momentum}
    alerts: List[str]
    stop_loss_hit: bool

@dataclass
class DataStatus:
    name: str
    latest_date: str
    delay_days: int
    status: str                # ok / stale / auto_triggered / trigger_failed

@dataclass
class LayeredRiskResult:
    """完整分层风控结果"""
    scan_time: str
    user_id: int
    data_status: List[DataStatus]
    macro: MacroRiskResult
    regime: RegimeRiskResult
    sector: SectorRiskResult
    stocks: List[StockRiskResult]
    overall_score: float
    overall_suggestions: List[str]
```

风险分级统一标准：

| 分数 | 级别 | 颜色 |
|---|---|---|
| 0-30 | LOW | 绿 |
| 30-50 | MEDIUM | 黄 |
| 50-70 | HIGH | 橙 |
| 70-100 | CRITICAL | 红 |

---

## 7. 报告格式

```markdown
# 持仓风控日报 (2026-04-20)

## 数据状态
| 数据源 | 最新日期 | 延迟 | 状态 |
|---|---|---|---|

## L1 宏观环境 [风险: 中等 42/100 | 建议仓位: <=80%]
- 恐惧指数: 45 (中性)
- VIX: 18.5 (正常)
- 北向资金: 近5日累计净流入+32亿
- 美债利差: 0.45% (正常)

## L2 市场状态 [风险: 偏高 62/100]
- 全A市场: 板块分化 (F1=42%)
- 持仓平均相关性: 0.58
- 高相关对: 600519/000858 (0.82)
- 建议: 减持白酒板块中的一只

## L3 行业暴露 [风险: 偏高 58/100]
| 行业 | 占比 | 估值分位 | 标签 |
|---|---|---|---|
| 食品饮料 | 35% | 72% | 高估 |
| 银行 | 20% | 15% | 低估 |
- 食品饮料占比超30%且高估

## L4 个股预警 [2只触发]
### 600519.SH 贵州茅台 [55/100]
- 财务: ROE 30.2% | 估值: PE分位78%(偏高)
- 技术: 跌破MA20, MACD死叉 | 动量: rps_slope -0.8

### 000001.SZ 平安银行 [68/100]
- 财务: 净利润同比-12% | 技术: 接近L2止损线(-7.5%/-8%)

## L5 交易规则 [正常]
- 持仓数: 8/10 | 日亏损: -0.3%

## 综合建议
1. 食品饮料行业集中度过高，建议适度减仓
2. 平安银行接近止损位，密切关注
3. 持仓相关性偏高，考虑增加周期类标的
```

---

## 8. 前端展示

更新 `web/src/app/positions/PositionsContent.tsx` 的风控扫描结果区域，从当前的扁平 chip 布局改为分层卡片：

```
+--------------------------------------------------+
| L1 宏观环境                    风险: 中等  42/100  |
| 恐惧指数 45 | VIX 18.5 | 北向+32亿 | 利差 0.45%   |
+--------------------------------------------------+
| L2 市场状态                    风险: 偏高  62/100  |
| 板块分化 (F1=42%) | 持仓相关性 0.58               |
| 高相关: 600519/000858 (0.82)                      |
+--------------------------------------------------+
| L3 行业暴露                    风险: 偏高  58/100  |
| 食品饮料 35% [高估] | 银行 20% [低估] | ...       |
+--------------------------------------------------+
| L4 个股预警 (2只)                                 |
| 贵州茅台 [55] PE偏高/MACD死叉                      |
| 平安银行 [68] 利润下滑/接近止损                     |
+--------------------------------------------------+
| L5 交易规则 [正常] 持仓8/10 日亏-0.3%              |
+--------------------------------------------------+
```

---

## 9. 任务拆分

### Phase 1: 基础设施

| ID | 任务 | 文件 | 说明 |
|---|---|---|---|
| T1.1 | 创建包结构 + BaseAssessor 基类 | `data_analyst/risk_assessment/` | 定义 assess() 接口 |
| T1.2 | 数据结构定义 | `schemas.py` | RiskScore, LayeredRiskResult 等 |
| T1.3 | 配置模块 | `config.py` | 阈值参数，从 settings.py 读取 |
| T1.4 | 数据依赖检查器 | `data_deps.py` | 检查 + 自动触发 |

### Phase 2: L1-L3 评估器

| ID | 任务 | 文件 | 依赖 |
|---|---|---|---|
| T2.1 | L1 宏观风险评估 | `assessors/macro.py` | 读 trade_fear_index + macro_data |
| T2.2 | L2 市场状态/相关性 | `assessors/regime.py` | 读 trade_svd_market_state + trade_stock_daily |
| T2.3 | L3 行业风险暴露 | `assessors/sector.py` | 读 trade_stock_basic + sw_industry_valuation |

### Phase 3: L4-L5 评估器

| ID | 任务 | 文件 | 依赖 |
|---|---|---|---|
| T3.1 | L4 个股基本面 (财务+估值) | `assessors/stock.py` | 读 trade_stock_financial + daily_basic |
| T3.2 | L4 个股基本面 (新闻+技术+动量) | `assessors/stock.py` | 读 news_sentiment + technical + rps |
| T3.3 | L5 交易执行规则 | `assessors/execution.py` | 整合现有 risk_manager/ |

### Phase 4: 整合

| ID | 任务 | 文件 | 依赖 |
|---|---|---|---|
| T4.1 | 扫描器 (串联 L1-L5) | `scanner.py` | T2.* + T3.* |
| T4.2 | Markdown 报告 | `report.py` | T4.1 |
| T4.3 | 结果持久化 | `storage.py` | T4.1 |

### Phase 5: API + 调度 + 前端

| ID | 任务 | 文件 | 依赖 |
|---|---|---|---|
| T5.1 | API 路由 + Service | `api/routers/risk.py`, `api/services/risk_service.py` | T4.* |
| T5.2 | 调度任务 | `tasks/10_risk.yaml`, `scheduler/adapters.py` | T4.* |
| T5.3 | 前端分层展示 | `PositionsContent.tsx` | T5.1 |
| T5.4 | 旧 `/risk-scan` 端点迁移 | `api/routers/positions.py` | T5.1 |

### Phase 6: 测试

| ID | 任务 | 依赖 |
|---|---|---|
| T6.1 | 各 Assessor 单元测试 (mock DB) | T3.* |
| T6.2 | 扫描器集成测试 | T4.* |
| T6.3 | API 端点测试 | T5.1 |

---

## 10. 渐进式上线策略

1. **第一批**: L1(宏观) + L3(行业) + L4(个股) -- 数据源最成熟，可直接上线
2. **第二批**: L2(相关性矩阵) -- 需优化性能（60天 x N股 的相关性计算）
3. **第三批**: L5(交易执行) + 数据自动触发 -- 需要与实盘对接
4. V1 `/api/positions/risk-scan` 保留，新增 `/api/risk/scan` 返回分层结果
5. 前端通过 `version` 参数切换新旧展示

---

## 11. 性能目标

| 操作 | 目标 |
|---|---|
| L1 宏观评估 | <500ms (3次 SQL 查询) |
| L2 相关性矩阵 (30股 x 60天) | <2s |
| L3 行业评估 | <500ms |
| L4 个股评估 (30股) | <3s (批量查询) |
| 完整扫描 (不含数据触发) | <5s |
| 数据依赖检查 | <1s |

---

## 12. 参考

- 胡猛《风和投资笔记》: 多层风控、跨市场分散、仓位梯度 2%-8%、3D-5M 分析模型
- 现有 `data_analyst/sentiment/fear_index.py`: 7 维恐慌指数 (L1 数据源)
- 现有 `data_analyst/market_monitor/`: SVD 市场状态 (L2 数据源)
- 现有 `data_analyst/fetchers/sw_industry_valuation_fetcher.py`: 行业估值 (L3 数据源)
- 现有 `risk_manager/__init__.py`: 止损/止盈计算 (L5 基础)
