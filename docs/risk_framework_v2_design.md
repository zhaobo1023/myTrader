# 风控框架 V2 -- 分层风控体系设计

## 1. 背景与目标

### 1.1 现状

当前 `risk_manager` 模块包含 7 条扁平规则，主要面向交易执行层面的风控：

| 规则 | 层级 | 覆盖范围 |
|---|---|---|
| ConcentrationLimit | 组合 | 持仓数上限 |
| SinglePositionLimit | 组合 | 单股仓位占比 |
| STBlacklist | 个股 | ST 退市风险 |
| PriceLimitGuard | 个股 | 涨跌停异常 |
| OrderAmountCap | 交易 | 单笔金额上限 |
| ATRPositionScaler | 个股 | 波动率仓位缩放 |
| DailyLossCircuitBreaker | 组合 | 日亏损熔断 |

**不足之处：**
- 缺少宏观环境评估（系统性风险）
- 缺少市场状态/相关性分析（齐涨齐跌时整体暴露过高）
- 缺少行业层面的风险集中度检查
- 缺少个股基本面恶化预警（财报、负面新闻）
- 缺少数据依赖的自动触发机制
- 规则之间没有层级关系，无法区分"系统性风险"和"个股噪音"

### 1.2 目标

参考胡猛《风和投资笔记》的多层风控思想（跨市场分散、跨行业对冲、仓位梯度 2%-8%、3D-5M 分析模型），构建**从宏观到微观的 5 层风控体系**：

```
L1 宏观/系统性风险  -->  整体仓位水位
L2 市场状态/相关性  -->  组合分散度
L3 行业风险暴露     -->  行业集中度
L4 个股基本面       -->  个股持仓建议
L5 交易执行         -->  下单拦截（现有规则）
```

每一层输出**风险评分 (0-100)** 和 **建议动作**，上层风险可覆盖下层判断（例如宏观恐慌时，个股再好也应降仓）。

---

## 2. 分层架构

### 2.1 总体流程

```
                    +-------------------+
                    | 数据依赖检查/触发  |
                    | (DataDependency)  |
                    +--------+----------+
                             |
                    +--------v----------+
                    |  L1 宏观环境评估    |
                    |  macro_risk_score  |
                    +--------+----------+
                             |
                    +--------v----------+
                    |  L2 市场状态/相关性  |
                    |  regime_risk_score |
                    +--------+----------+
                             |
                    +--------v----------+
                    |  L3 行业风险暴露    |
                    |  sector_risk_score |
                    +--------+----------+
                             |
                    +--------v----------+
                    |  L4 个股基本面      |
                    |  stock_risk_score  |
                    +--------+----------+
                             |
                    +--------v----------+
                    |  L5 交易执行规则    |
                    |  (现有 7 条规则)    |
                    +--------+----------+
                             |
                    +--------v----------+
                    |  综合风控报告       |
                    +-------------------+
```

### 2.2 L1 -- 宏观/系统性风险

**目的：** 评估当前宏观环境对持仓的系统性威胁，决定整体仓位水位。

**数据源：**

| 数据 | 表 | 关键字段 | 更新频率 |
|---|---|---|---|
| 恐惧指数 | `trade_fear_index` | `fear_greed_score`, `market_regime`, `vix_level` | 日 |
| VIX | `macro_data` (indicator='vix') | value | 日 |
| 中国波指 | `macro_data` (indicator='qvix') | value | 日 |
| 北向资金 | `macro_data` (indicator='north_flow') | value | 日 |
| 美债利差 | `macro_data` (indicator='us_10y_2y_spread') | value | 日 |
| 美元指数 | `macro_data` (indicator='dxy') | value | 日 |
| 衍生因子 | `macro_factors` | oil_mom_20, gold_mom_20, vix_ma5, north_flow_5d | 日 |

**评估逻辑：**

```python
class MacroRiskAssessor:
    """L1: 宏观环境风险评估"""

    def assess(self) -> MacroRiskResult:
        # 1. 恐惧指数 (权重 30%)
        #    extreme_fear -> 90分, fear -> 70, neutral -> 40, greed -> 20, extreme_greed -> 10
        fear_score = self._score_fear_index()

        # 2. VIX 水平 (权重 20%)
        #    >30 -> 90分, 20-30 -> 60, 15-20 -> 40, <15 -> 20
        vix_score = self._score_vix()

        # 3. 北向资金趋势 (权重 15%)
        #    连续5日净流出 -> 80分, 单日大幅流出(>50亿) -> 70, 正常 -> 30
        northflow_score = self._score_northflow()

        # 4. 美债利差 (权重 15%)
        #    倒挂 -> 80分, 利差收窄 -> 60, 正常 -> 30
        spread_score = self._score_yield_spread()

        # 5. 大宗商品异动 (权重 10%)
        #    油价急涨/急跌(20d动量 >10%) -> 70分, 正常 -> 30
        commodity_score = self._score_commodities()

        # 6. 人民币汇率 (权重 10%)
        #    快速贬值 -> 70分, 正常 -> 30
        fx_score = self._score_fx()

        total = weighted_sum([fear, vix, northflow, spread, commodity, fx],
                             [0.30, 0.20, 0.15, 0.15, 0.10, 0.10])
        return MacroRiskResult(
            score=total,
            level=classify(total),     # LOW/MEDIUM/HIGH/CRITICAL
            suggested_max_exposure=exposure_curve(total),  # 0.3~1.0
            details={...},
        )
```

**输出：**
- `macro_risk_score`: 0-100（越高越危险）
- `suggested_max_exposure`: 建议最高仓位水位（0.3 = 最多三成仓, 1.0 = 满仓可）
- `level`: LOW / MEDIUM / HIGH / CRITICAL

**仓位水位映射（参考胡猛仓位梯度思想）：**

| 宏观风险分 | 建议仓位上限 | 含义 |
|---|---|---|
| 0-30 | 100% | 环境友好，可满仓 |
| 30-50 | 80% | 略有风险，适度保守 |
| 50-70 | 60% | 风险偏高，保留较多现金 |
| 70-85 | 40% | 高风险，大幅减仓 |
| 85-100 | 30% | 极端风险，仅保留底仓 |

---

### 2.3 L2 -- 市场状态/相关性

**目的：** 判断当前市场是齐涨齐跌还是分化行情，评估持仓相关性风险。齐涨齐跌时持仓分散化的保护效果会大幅降低。

**数据源：**

| 数据 | 表 | 关键字段 |
|---|---|---|
| SVD 市场状态 | `trade_svd_market_state` | `top1_var_ratio`, `market_state`, `is_mutation` |
| 个股日线 | `trade_stock_daily` | close_price（计算持仓相关性矩阵） |

**评估逻辑：**

```python
class RegimeRiskAssessor:
    """L2: 市场状态与相关性风险"""

    def assess(self, position_codes: List[str]) -> RegimeRiskResult:
        # 1. 全A市场状态 (权重 40%)
        svd = self._get_svd_state(universe='全A', window=20)
        #   齐涨齐跌(F1>50%) -> 85分 (分散化失效)
        #   板块分化(35-50%)  -> 50分 (需关注行业分散)
        #   个股行情(F1<35%)  -> 20分 (分散化有效)
        regime_score = self._score_regime(svd)

        # 2. 突变检测 (权重 15%)
        #   is_mutation=1 -> 80分 (市场结构突变，需警惕)
        mutation_score = 80 if svd.is_mutation else 20

        # 3. 持仓相关性矩阵 (权重 45%)
        #   计算持仓中所有股票过去60天的收益率相关性
        #   平均相关系数 >0.6 -> 85分 (高度同质化)
        #   0.4-0.6 -> 55分
        #   <0.4 -> 25分 (分散化良好)
        corr_score = self._score_portfolio_correlation(position_codes)

        total = weighted_sum([regime, mutation, corr],
                             [0.40, 0.15, 0.45])
        return RegimeRiskResult(
            score=total,
            market_state=svd.market_state,
            avg_correlation=avg_corr,
            high_corr_pairs=high_pairs,   # 相关系数>0.7的股票对
            suggestion=self._generate_suggestion(total, svd),
        )
```

**输出：**
- `regime_risk_score`: 0-100
- `market_state`: 齐涨齐跌 / 板块分化 / 个股行情
- `avg_correlation`: 持仓平均相关系数
- `high_corr_pairs`: 高相关股票对列表（需考虑换仓）
- `suggestion`: 文字建议

---

### 2.4 L3 -- 行业风险暴露

**目的：** 检查持仓在行业维度的集中度和估值风险。即使个股分散，如果全部集中在同一行业（如消费），行业性利空会导致整体回撤。

**数据源：**

| 数据 | 表 | 关键字段 |
|---|---|---|
| 行业分类 | `trade_stock_basic` | `sw_level1` |
| 行业估值 | `sw_industry_valuation` | `valuation_score`, `valuation_label`, `pe_pct_5y` |
| 行业SVD | `trade_svd_market_state` (universe_type='SW_L1') | `top1_var_ratio`, `market_state` |

**评估逻辑：**

```python
class SectorRiskAssessor:
    """L3: 行业风险暴露评估"""

    def assess(self, positions: List[Position]) -> SectorRiskResult:
        # 1. 行业集中度 (权重 35%)
        #   按申万一级行业分组，计算各行业持仓市值占比
        #   最大行业占比 >50% -> 85分
        #   >30% -> 60分
        #   <30% -> 25分
        concentration = self._calc_industry_concentration(positions)

        # 2. 高估行业暴露 (权重 30%)
        #   持仓中处于"高估"行业(valuation_score>70)的市值占比
        #   >50% -> 80分
        #   >30% -> 55分
        #   <30% -> 25分
        overvalued_exposure = self._calc_overvalued_exposure(positions)

        # 3. 行业内聚性 (权重 20%)
        #   持仓最大行业的SVD F1值
        #   行业齐涨齐跌(F1高) + 高集中度 -> 双重风险
        cohesion_risk = self._calc_industry_cohesion(positions)

        # 4. 跨行业对冲度 (权重 15%)
        #   胡猛思想：持仓应覆盖不相关的行业（周期/消费/科技/金融）
        #   行业数 <3 -> 70分
        #   行业分布跨大类 -> 25分
        diversification = self._calc_cross_sector_hedge(positions)

        return SectorRiskResult(
            score=total,
            industry_breakdown={...},    # 各行业占比
            overvalued_industries=[...],  # 高估行业列表
            suggestions=[...],
        )
```

**输出：**
- `sector_risk_score`: 0-100
- `industry_breakdown`: {行业名: 市值占比}
- `overvalued_industries`: 处于高估区间的持仓行业
- `underrepresented_sectors`: 缺少对冲的大类行业

---

### 2.5 L4 -- 个股基本面

**目的：** 逐只检查持仓股票的基本面健康度，识别财务恶化、负面新闻、估值极端等信号。

**数据源：**

| 数据 | 表 | 关键字段 |
|---|---|---|
| 财报 | `trade_stock_financial`, `financial_income` | revenue, net_profit, roe, gross_margin |
| 实时估值 | `trade_stock_daily_basic` | pe_ttm, pb, ps_ttm, dv_ttm |
| 新闻情绪 | `trade_news_sentiment` | sentiment, sentiment_strength |
| 事件信号 | `trade_event_signal` | event_type, signal |
| RPS动量 | `trade_stock_rps` | rps_20, rps_60, rps_250, rps_slope |
| 技术指标 | `trade_technical_indicator` | macd_histogram, rsi_6, volume_ratio |
| 因子 | `trade_stock_factor` | momentum_20d, volatility, adx_14 |

**评估逻辑（每只股票独立评估）：**

```python
class StockFundamentalAssessor:
    """L4: 个股基本面风险评估"""

    def assess(self, stock_code: str, cost_price: float) -> StockRiskResult:
        # 1. 财务健康 (权重 25%)
        #   - 净利润同比下降 >30% -> 80分
        #   - ROE < 5% -> 70分
        #   - 毛利率下滑 >5pct -> 65分
        #   - 营收负增长 -> 60分
        financial_score = self._score_financials(stock_code)

        # 2. 估值水平 (权重 20%)
        #   - PE_TTM > 行业PE分位80% -> 75分
        #   - PB > 行业PB分位80% -> 70分
        #   - PE为负(亏损) -> 85分
        valuation_score = self._score_valuation(stock_code)

        # 3. 新闻情绪 (权重 15%)
        #   - 近7天有 strong_sell 事件信号 -> 85分
        #   - 近7天负面新闻 >= 3条 -> 70分
        #   - 近7天有 bearish 事件 -> 60分
        #   - 无负面信息 -> 20分
        news_score = self._score_news_sentiment(stock_code)

        # 4. 技术面止损 (权重 25%)
        #   - 当前价 < 成本价 * (1 - 止损线)
        #     L1级(核心持仓): 止损线 15%
        #     L2级(卫星持仓): 止损线 8%
        #   - 跌破MA60 -> 60分
        #   - RSI < 20 (超卖) -> 50分 (反转信号，不一定是风险)
        #   - MACD死叉 + 量能萎缩 -> 70分
        technical_score = self._score_technicals(stock_code, cost_price)

        # 5. 动量衰减 (权重 15%)
        #   - rps_slope < -1.5 (动量急剧衰减) -> 75分
        #   - rps_250 < 20 (长期弱势) -> 70分
        #   - rps_20 < 10 (短期极弱) -> 65分
        momentum_score = self._score_momentum(stock_code)

        return StockRiskResult(
            stock_code=stock_code,
            score=total,
            sub_scores={
                'financial': financial_score,
                'valuation': valuation_score,
                'news': news_score,
                'technical': technical_score,
                'momentum': momentum_score,
            },
            alerts=[...],       # 触发的预警列表
            stop_loss_hit=...,  # 是否触及止损
        )
```

**止损策略（参考胡猛仓位管理）：**

| 持仓级别 | 单股仓位范围 | 止损线 | 说明 |
|---|---|---|---|
| L1 核心 | 5%-8% | -15% | 经过深度研究的长期持仓 |
| L2 卫星 | 2%-5% | -8% | 趋势跟随或短期机会 |

---

### 2.6 L5 -- 交易执行（现有规则）

保留现有 7 条规则不变，作为最终交易执行层的守门员。L1-L4 的输出会影响 L5 的配置参数：

- L1 宏观风险高 -> 降低 `max_positions`、收紧 `single_position_limit`
- L2 高相关性 -> 收紧 `single_position_limit`
- L4 个股风险高 -> 降低该股的 `max_pct`

---

## 3. 数据依赖与自动触发

### 3.1 问题

生成完整风控报告依赖多张表的最新数据。如果某张表数据缺失（如行业估值没有计算），报告就不完整。

### 3.2 设计

```python
class DataDependencyChecker:
    """在执行风控扫描前，检查所有依赖数据的新鲜度，缺失时自动触发补充。"""

    DEPENDENCIES = [
        {
            'name': '行情数据',
            'table': 'trade_stock_daily',
            'date_column': 'trade_date',
            'max_delay_days': 1,
            'trigger': None,  # 依赖外部数据源(Tushare)，无法自动补充
            'critical': True,
        },
        {
            'name': '行业估值',
            'table': 'sw_industry_valuation',
            'date_column': 'trade_date',
            'max_delay_days': 1,
            'trigger': 'data_analyst.fetchers.sw_industry_valuation_fetcher.run_daily',
            'critical': False,
        },
        {
            'name': 'SVD市场状态',
            'table': 'trade_svd_market_state',
            'date_column': 'calc_date',
            'max_delay_days': 1,
            'trigger': 'data_analyst.market_monitor.run_monitor.main',
            'critical': False,
        },
        {
            'name': '恐惧指数',
            'table': 'trade_fear_index',
            'date_column': 'trade_date',
            'max_delay_days': 2,  # 周末可能延迟
            'trigger': None,  # 由sentiment scheduler自动更新
            'critical': False,
        },
        {
            'name': '技术指标',
            'table': 'trade_technical_indicator',
            'date_column': 'trade_date',
            'max_delay_days': 1,
            'trigger': None,  # 由指标计算任务自动更新
            'critical': False,
        },
        {
            'name': 'RPS指标',
            'table': 'trade_stock_rps',
            'date_column': 'trade_date',
            'max_delay_days': 1,
            'trigger': None,
            'critical': False,
        },
    ]

    def check_and_trigger(self) -> List[DataStatus]:
        """检查各依赖数据的最新日期，缺失且可触发的自动补充。"""
        results = []
        for dep in self.DEPENDENCIES:
            latest_date = self._get_latest_date(dep['table'], dep['date_column'])
            delay = (today - latest_date).days
            is_stale = delay > dep['max_delay_days']

            if is_stale and dep['trigger']:
                try:
                    self._invoke_trigger(dep['trigger'])
                    status = 'auto_triggered'
                except Exception as e:
                    status = 'trigger_failed'
            elif is_stale:
                status = 'stale'
            else:
                status = 'ok'

            results.append(DataStatus(
                name=dep['name'],
                latest_date=latest_date,
                delay_days=delay,
                status=status,
            ))
        return results
```

### 3.3 报告中的数据状态展示

风控报告的开头会展示数据依赖状态：

```markdown
## 数据状态
| 数据源 | 最新日期 | 延迟 | 状态 |
|---|---|---|---|
| 行情数据 | 2026-04-18 | 0天 | OK |
| 行业估值 | 2026-04-18 | 0天 | OK |
| SVD市场状态 | 2026-04-17 | 1天 | OK |
| 恐惧指数 | 2026-04-16 | 2天 | 已自动触发 |
```

---

## 4. 综合风控报告格式

```markdown
# 持仓风控日报 (2026-04-20)

## 数据状态
[数据依赖状态表]

## L1 宏观环境 [风险: 中等 | 建议仓位: <=80%]
- 恐惧指数: 45 (中性)
- VIX: 18.5 (正常)
- 北向资金: 近5日累计净流入+32亿
- 美债10Y-2Y利差: 0.45% (正常)
- 综合评分: 42/100

## L2 市场状态 [风险: 偏高]
- 全A市场: 板块分化 (F1=42%)
- 持仓平均相关性: 0.58 (偏高)
- 高相关对: 600519/000858 (0.82), 601318/600036 (0.76)
- 建议: 考虑减持白酒板块中的一只，降低消费行业内部相关性

## L3 行业暴露 [风险: 偏高]
| 行业 | 持仓占比 | 估值分位 | 估值标签 |
|---|---|---|---|
| 食品饮料 | 35% | 72% | 高估 |
| 银行 | 20% | 15% | 低估 |
| 电子 | 15% | 45% | 合理 |
- 食品饮料占比过高(>30%)，且处于高估区间
- 缺少周期类行业对冲

## L4 个股预警 [2只触发]

### 600519.SH 贵州茅台 [风险: 55/100]
- 财务: ROE 30.2% (优秀)
- 估值: PE_TTM 35.2，行业分位78% (偏高)
- 新闻: 近7天无负面
- 技术: 跌破MA20，MACD死叉 (注意)
- 动量: rps_slope -0.8 (动量减弱)

### 000001.SZ 平安银行 [风险: 68/100]
- 财务: 净利润同比-12% (下滑)
- 技术: 价格接近止损线(-7.5%, L2止损线-8%)
- 建议: 关注是否触发止损

## L5 交易规则 [正常]
- 持仓数: 8/10
- 日亏损: -0.3% (正常)
- 无熔断触发

## 综合建议
1. 宏观环境中性，可维持当前仓位水平
2. 食品饮料行业集中度过高，建议适度减仓贵州茅台或五粮液
3. 平安银行接近止损位，密切关注
4. 持仓相关性偏高，考虑增加周期或公用事业行业标的
```

---

## 5. 代码组织

### 5.1 新增文件

```
risk_manager/
    assessors/
        __init__.py
        base.py            # BaseAssessor 基类，定义 assess() 接口
        macro.py           # L1 MacroRiskAssessor
        regime.py          # L2 RegimeRiskAssessor
        sector.py          # L3 SectorRiskAssessor
        stock.py           # L4 StockFundamentalAssessor
    data_deps.py           # DataDependencyChecker
    report_v2.py           # 新版分层报告生成器
    scanner_v2.py          # 新版扫描器（调用 L1-L5）
```

### 5.2 保留文件（不变）

```
risk_manager/
    base.py         # BaseRule
    config.py       # RiskConfig
    engine.py       # RiskEngine (L5)
    rules.py        # 7条内置规则 (L5)
    models.py       # 数据模型（需扩展）
    scanner.py      # V1扫描器（保留兼容）
    daily_report.py # V1报告（保留兼容）
```

### 5.3 models.py 扩展

```python
@dataclass
class RiskScore:
    """统一的风险评分结构"""
    score: float          # 0-100
    level: str            # LOW / MEDIUM / HIGH / CRITICAL
    details: dict         # 各维度明细
    suggestions: List[str]

@dataclass
class LayeredRiskResult:
    """分层风控评估结果"""
    scan_time: str
    user_id: int
    data_status: List[DataStatus]
    macro: MacroRiskResult       # L1
    regime: RegimeRiskResult     # L2
    sector: SectorRiskResult     # L3
    stocks: List[StockRiskResult]  # L4
    execution: AggregatedDecision  # L5
    overall_score: float
    overall_suggestions: List[str]
```

---

## 6. 任务拆分

### Phase 1: 基础设施

| 任务 | 说明 | 预计改动 |
|---|---|---|
| T1.1 | 创建 `assessors/` 包结构 + `base.py` 基类 | 新建 2 文件 |
| T1.2 | 扩展 `models.py`：新增 RiskScore, LayeredRiskResult 等数据结构 | 改 1 文件 |
| T1.3 | 实现 `data_deps.py` 数据依赖检查器 | 新建 1 文件 |

### Phase 2: L1-L3 评估器

| 任务 | 说明 | 依赖 |
|---|---|---|
| T2.1 | 实现 `assessors/macro.py` -- 宏观风险评估 | T1.1, T1.2 |
| T2.2 | 实现 `assessors/regime.py` -- 市场状态/相关性评估 | T1.1, T1.2 |
| T2.3 | 实现 `assessors/sector.py` -- 行业风险暴露评估 | T1.1, T1.2 |

### Phase 3: L4 个股评估器

| 任务 | 说明 | 依赖 |
|---|---|---|
| T3.1 | 实现 `assessors/stock.py` -- 个股基本面评估 | T1.1, T1.2 |
| T3.2 | 止损策略: 基于持仓级别(L1/L2)的差异化止损 | T3.1 |

### Phase 4: 整合

| 任务 | 说明 | 依赖 |
|---|---|---|
| T4.1 | 实现 `scanner_v2.py` -- 整合 L1-L5 的新版扫描器 | T2.*, T3.* |
| T4.2 | 实现 `report_v2.py` -- 分层 Markdown 报告生成 | T4.1 |
| T4.3 | 更新 `__init__.py` 导出新 API | T4.2 |

### Phase 5: 测试与前端

| 任务 | 说明 | 依赖 |
|---|---|---|
| T5.1 | 单元测试: 每个 Assessor + DataDependencyChecker | T4.* |
| T5.2 | myTrader 后端: 更新 `/api/positions/risk-scan` 端点使用 V2 | T4.3 |
| T5.3 | myTrader 前端: 更新风控扫描结果展示（分层卡片布局） | T5.2 |

---

## 7. 关键设计决策

### 7.1 评分体系统一

所有层级使用统一的 0-100 分制：
- 0-30: LOW（低风险，绿色）
- 30-50: MEDIUM（中等，黄色）
- 50-70: HIGH（偏高，橙色）
- 70-100: CRITICAL（严重，红色）

### 7.2 数据缺失降级

当某一层的数据不可用时，该层返回"数据不足"状态，不影响其他层的评估。报告中明确标注哪些层的评估是不完整的。

### 7.3 渐进式上线

- V2 扫描器与 V1 并存，通过 `version` 参数切换
- 先上线 L1（宏观）+ L3（行业）+ L4（个股基本面），因为数据源最成熟
- L2（相关性矩阵计算）性能开销较大，后续优化后上线

### 7.4 性能考虑

- 相关性矩阵计算（60天 x N只股票）: 对于 <30 只持仓可接受，使用 numpy 矩阵运算
- 行业估值查询: 批量查询，一次取所有持仓行业
- 新闻情绪: 限制为近7天，按股票批量查询
- 总体目标: 单次扫描 <5秒（不含数据触发）

---

## 8. 参考

- 胡猛《风和投资笔记》: 多层风控、跨市场分散、仓位梯度 2%-8%、3D-5M 分析模型
- 现有 `risk_manager/` 模块文档和源码
- myTrader 数据库 55+ 张表的数据资产
