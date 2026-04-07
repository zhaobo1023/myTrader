# 五截面分析框架 v2.0 优化方案

> 基于实际报告诊断 + 专业评审反馈，对 FiveSectionFramework v1.0 进行系统性优化  
> 文档版本：v2.0 | 2026-04-07

---

## 一、问题诊断汇总

### 1.1 数据层问题（P0 紧急）

| 问题 | 影响案例 | 根因分析 | 严重程度 |
|------|----------|----------|----------|
| **财务数据严重过时** | 云铝股份显示 2020 年数据，实际 2025 年报已发布 | `trade_stock_financial` 表数据未更新 | [CRITICAL] 基本面+周期评分完全失真 |
| **主力资金流向全为 0** | 中国海油/云铝均显示 +0.00 亿 | `trade_stock_moneyflow` 表无数据 | [CRITICAL] 资金面 50 分默认值参与评分 |
| **情绪面多维度使用默认值** | 一致预期/宏观情绪写死 50 分 | 无数据源接入，代码硬编码 | [HIGH] 情绪面评分可信度低 |
| **财务数据只显示单年** | 报告缺少同比对照 | renderer 未展示多年数据 | [MEDIUM] 信息不完整 |

### 1.2 模型层问题（P0/P1）

| 问题 | 描述 | 评审来源 |
|------|------|----------|
| **周期股估值陷阱** | 对周期资源股使用 PE 分位打分，逻辑完全相反（周期股应"高 PE 买，低 PE 卖"） | 外部评审 |
| **长短周期指标混合** | MA5（日级别）与 5 年 ROE（年级别）线性加权，信号互相抵消 | 外部评审 |
| **指标多重共线性** | 情绪面的"资金流向情绪"与资金面重复，"量价动量情绪"与技术面重复 | 外部评审 |
| **规则引擎逻辑冲突** | `P1 泡沫期: Phase==4 AND PE分位>80%` 在周期股上永远不会触发 | 外部评审 |

### 1.3 展示层问题（P2）

| 问题 | 描述 |
|------|------|
| ROE 轨迹年份标注模糊 | "T-5, T-4, T-3..." 不如直接写 "2020, 2021, 2022..." |
| 规则引擎永远显示"需人工监控" | 大股东减仓数据无自动化来源 |
| 缺少数据健康度提示 | 用户无法判断哪些数据可信、哪些缺失 |

---

## 二、优化方案总览

### 2.1 架构升级：双维度评估体系

**核心改动**：将原有单一综合分拆分为"资产质地"和"交易择时"两个独立维度。

```
原架构（v1.0）：
  综合分 = 技术15% + 资金20% + 基本30% + 情绪15% + 周期20%
  输出：47分，中性观望

新架构（v2.0）：
  ┌─────────────────────────────────────────────────────┐
  │  第一维度：资产质地（决定"买不买"）                   │
  │  ├── 基本面得分 (权重 60%)                           │
  │  └── 资本周期定位 (权重 40%)                         │
  │  输出：质地分 72分 - 优质资产                         │
  └─────────────────────────────────────────────────────┘
  ┌─────────────────────────────────────────────────────┐
  │  第二维度：交易择时（决定"什么时候买"）               │
  │  ├── 技术面得分 (权重 40%)                           │
  │  ├── 资金面得分 (权重 35%)                           │
  │  └── 情绪面得分 (权重 25%)                           │
  │  输出：择时分 38分 - 短期回调中                       │
  └─────────────────────────────────────────────────────┘
  
  综合建议：优质资产回调，关注 MA20 企稳后左侧建仓
```

**好处**：
- 避免长短周期信号互相抵消
- 优质资产在回调时不会被误判为"中性观望"
- 决策逻辑更清晰（先选池子，再择时机）

### 2.2 行业异质性处理

**核心改动**：对不同行业类型使用不同的估值评分逻辑。

```python
INDUSTRY_TYPE_MAP = {
    "周期资源": ["石油", "煤炭", "有色金属", "钢铁", "化工", "航运"],
    "金融地产": ["银行", "保险", "证券", "房地产"],
    "成长科技": ["半导体", "软件", "互联网", "新能源"],
    "消费医药": ["食品饮料", "医药", "家电", "零售"],
}

def get_valuation_score(stock_code, pe_quantile, pb_quantile, roe, industry_type):
    if industry_type == "周期资源":
        # 周期股：用 PB-ROE 模型，忽略 PE 分位
        # 高 ROE + 低 PB = 景气高点但估值合理 = 高分
        # 低 ROE + 高 PB = 景气低点但估值偏高 = 低分
        return pb_roe_score(pb_quantile, roe)
    
    elif industry_type == "金融地产":
        # 金融股：主要看 PB 分位，PE 参考性弱
        return pb_dominant_score(pb_quantile, pe_quantile)
    
    else:
        # 成长/消费：传统 PE 分位逻辑
        return pe_quantile_score(pe_quantile, pb_quantile)
```

### 2.3 数据健康度检测

**核心改动**：在报告生成前检测数据完整性，对缺失/过时数据降权或标记。

```python
@dataclass
class DataHealthReport:
    """数据健康度报告"""
    technical_ok: bool = True
    technical_date: str = ""
    
    fund_flow_ok: bool = True
    fund_flow_missing: bool = False
    
    financial_ok: bool = True
    financial_stale: bool = False      # 超过 18 个月
    financial_report_date: str = ""
    
    valuation_ok: bool = True
    rps_ok: bool = True
    
    @property
    def completeness_score(self) -> float:
        """数据完整度 0-100%"""
        checks = [
            self.technical_ok,
            self.fund_flow_ok and not self.fund_flow_missing,
            self.financial_ok and not self.financial_stale,
            self.valuation_ok,
            self.rps_ok,
        ]
        return sum(checks) / len(checks) * 100
    
    @property
    def confidence_level(self) -> str:
        score = self.completeness_score
        if score >= 80:
            return "HIGH"
        elif score >= 60:
            return "MEDIUM"
        else:
            return "LOW"
```

---

## 三、详细设计

### 3.1 数据层修复

#### 3.1.1 财务数据过时检测

**文件**：`data_analyst/research_pipeline/fetcher.py`

```python
from datetime import datetime
from dataclasses import dataclass

@dataclass
class FinancialSeries:
    # ... 现有字段 ...
    
    # 新增
    is_stale: bool = False           # 数据是否过时
    stale_months: int = 0            # 过时月数
    data_warning: str = ""           # 警告信息

def fetch_financial(self, stock_code: str) -> FinancialSeries:
    # ... 现有逻辑 ...
    
    # 新增：检测数据是否过时
    if rows:
        latest_date = rows[-1]["report_date"]
        report_year = int(str(latest_date)[:4])
        current_date = datetime.now()
        
        # 计算距今月数
        months_diff = (current_date.year - report_year) * 12 + current_date.month
        
        # 超过 18 个月视为过时（正常年报周期 + 6 个月缓冲）
        is_stale = months_diff > 18
        
        warning = ""
        if is_stale:
            warning = f"[STALE] 财务数据距今 {months_diff} 个月，最新年报: {latest_date}"
    
    return FinancialSeries(
        # ... 现有字段 ...
        is_stale=is_stale,
        stale_months=months_diff,
        data_warning=warning,
    )
```

#### 3.1.2 资金流数据缺失检测

**文件**：`data_analyst/research_pipeline/fetcher.py`

```python
@dataclass
class FundFlowData:
    # ... 现有字段 ...
    
    # 新增
    is_missing: bool = False         # 数据是否缺失
    data_warning: str = ""

def fetch_fund_flow(self, stock_code: str, rps_120: float = 50.0) -> FundFlowData:
    rows = self._query(...)
    
    if not rows:
        return FundFlowData(
            rps_120=rps_120,
            is_missing=True,
            data_warning=f"[MISSING] 无资金流向数据，资金面评分不可用"
        )
    
    amounts = [float(r["net_mf_amount"] or 0) for r in rows]
    
    # 检测是否全为 0（可能是数据异常）
    if all(abs(a) < 1e-6 for a in amounts):
        return FundFlowData(
            rps_120=rps_120,
            is_missing=True,
            data_warning=f"[MISSING] 资金流向数据全为 0，可能是数据源异常"
        )
    
    # ... 正常逻辑 ...
```

#### 3.1.3 数据健康度报告模块

**新文件**：`data_analyst/research_pipeline/health_checker.py`

```python
"""
数据健康度检测器

在生成报告前检测所有数据源的完整性和时效性，
输出健康度报告并决定哪些截面的评分可信。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class DataHealthReport:
    stock_code: str
    check_date: str
    
    # 各数据源状态
    technical: dict = field(default_factory=dict)
    fund_flow: dict = field(default_factory=dict)
    financial: dict = field(default_factory=dict)
    valuation: dict = field(default_factory=dict)
    rps: dict = field(default_factory=dict)
    
    @property
    def completeness_pct(self) -> int:
        """数据完整度百分比"""
        checks = [
            self.technical.get("ok", False),
            self.fund_flow.get("ok", False) and not self.fund_flow.get("missing", True),
            self.financial.get("ok", False) and not self.financial.get("stale", True),
            self.valuation.get("ok", False),
            self.rps.get("ok", False),
        ]
        return int(sum(checks) / len(checks) * 100)
    
    @property
    def confidence(self) -> str:
        pct = self.completeness_pct
        if pct >= 80:
            return "HIGH"
        elif pct >= 60:
            return "MEDIUM"
        else:
            return "LOW"
    
    @property
    def warnings(self) -> list:
        """收集所有警告信息"""
        warns = []
        if self.fund_flow.get("missing"):
            warns.append(self.fund_flow.get("warning", "资金流数据缺失"))
        if self.financial.get("stale"):
            warns.append(self.financial.get("warning", "财务数据过时"))
        if not self.rps.get("ok"):
            warns.append("RPS 数据缺失")
        return warns
    
    def get_weight_adjustments(self) -> dict:
        """根据数据健康度调整各截面权重"""
        adjustments = {
            "technical": 1.0,
            "fund_flow": 1.0,
            "fundamental": 1.0,
            "sentiment": 1.0,
            "capital_cycle": 1.0,
        }
        
        # 资金流缺失：权重降为 0，重新分配
        if self.fund_flow.get("missing"):
            adjustments["fund_flow"] = 0.0
        
        # 财务数据过时：基本面和周期权重减半
        if self.financial.get("stale"):
            adjustments["fundamental"] = 0.5
            adjustments["capital_cycle"] = 0.5
        
        return adjustments


class HealthChecker:
    """数据健康度检测器"""
    
    def check(
        self,
        stock_code: str,
        tech_data: dict,
        fund_flow_data: "FundFlowData",
        financial_data: "FinancialSeries",
        valuation_data: "ValuationData",
        rps_value: float,
    ) -> DataHealthReport:
        
        report = DataHealthReport(
            stock_code=stock_code,
            check_date=datetime.now().strftime("%Y-%m-%d"),
        )
        
        # 技术面检测
        report.technical = {
            "ok": bool(tech_data and tech_data.get("price", 0) > 0),
            "date": tech_data.get("data_date", ""),
        }
        
        # 资金流检测
        report.fund_flow = {
            "ok": not fund_flow_data.is_missing,
            "missing": fund_flow_data.is_missing,
            "warning": fund_flow_data.data_warning,
        }
        
        # 财务数据检测
        report.financial = {
            "ok": bool(financial_data.roe_series),
            "stale": financial_data.is_stale,
            "stale_months": financial_data.stale_months,
            "report_date": financial_data.report_date,
            "warning": financial_data.data_warning,
        }
        
        # 估值数据检测
        report.valuation = {
            "ok": valuation_data.pe_ttm > 0 and valuation_data.pb > 0,
            "date": valuation_data.trade_date,
        }
        
        # RPS 检测
        report.rps = {
            "ok": rps_value != 50.0,  # 50.0 是默认值
            "value": rps_value,
        }
        
        return report
```

### 3.2 模型层修复

#### 3.2.1 行业类型识别

**新文件**：`research/industry_classifier.py`

```python
"""
行业类型分类器

将申万行业分类映射到估值模型适用的行业类型：
- 周期资源：石油、煤炭、有色、钢铁、化工、航运
- 金融地产：银行、保险、证券、房地产
- 成长科技：半导体、软件、互联网、新能源
- 消费医药：食品饮料、医药、家电、零售
"""
from enum import Enum
from typing import Optional

class IndustryType(Enum):
    CYCLICAL = "周期资源"
    FINANCIAL = "金融地产"
    GROWTH = "成长科技"
    CONSUMER = "消费医药"
    UNKNOWN = "未分类"


# 申万一级行业 -> 行业类型映射
SW_INDUSTRY_MAP = {
    # 周期资源
    "石油石化": IndustryType.CYCLICAL,
    "煤炭": IndustryType.CYCLICAL,
    "有色金属": IndustryType.CYCLICAL,
    "钢铁": IndustryType.CYCLICAL,
    "基础化工": IndustryType.CYCLICAL,
    "交通运输": IndustryType.CYCLICAL,  # 航运
    "建筑材料": IndustryType.CYCLICAL,
    "建筑装饰": IndustryType.CYCLICAL,
    
    # 金融地产
    "银行": IndustryType.FINANCIAL,
    "非银金融": IndustryType.FINANCIAL,
    "房地产": IndustryType.FINANCIAL,
    
    # 成长科技
    "电子": IndustryType.GROWTH,
    "计算机": IndustryType.GROWTH,
    "通信": IndustryType.GROWTH,
    "传媒": IndustryType.GROWTH,
    "电力设备": IndustryType.GROWTH,  # 新能源
    "国防军工": IndustryType.GROWTH,
    
    # 消费医药
    "食品饮料": IndustryType.CONSUMER,
    "医药生物": IndustryType.CONSUMER,
    "家用电器": IndustryType.CONSUMER,
    "美容护理": IndustryType.CONSUMER,
    "商贸零售": IndustryType.CONSUMER,
    "社会服务": IndustryType.CONSUMER,
    "农林牧渔": IndustryType.CONSUMER,
    "纺织服饰": IndustryType.CONSUMER,
    "轻工制造": IndustryType.CONSUMER,
    
    # 公用事业归为周期（电力价格周期性）
    "公用事业": IndustryType.CYCLICAL,
    "环保": IndustryType.CYCLICAL,
    
    # 机械设备视情况，偏周期
    "机械设备": IndustryType.CYCLICAL,
    "汽车": IndustryType.CYCLICAL,
}


class IndustryClassifier:
    """行业类型分类器"""
    
    def __init__(self, env: str = "online"):
        self.env = env
        self._cache = {}
    
    def get_industry_type(self, stock_code: str) -> IndustryType:
        """获取股票的行业类型"""
        if stock_code in self._cache:
            return self._cache[stock_code]
        
        # 从数据库查询申万行业
        sw_industry = self._fetch_sw_industry(stock_code)
        
        industry_type = SW_INDUSTRY_MAP.get(sw_industry, IndustryType.UNKNOWN)
        self._cache[stock_code] = industry_type
        
        return industry_type
    
    def _fetch_sw_industry(self, stock_code: str) -> str:
        """从数据库查询申万一级行业"""
        from config.db import execute_query
        
        rows = execute_query(
            """
            SELECT sw_industry_name 
            FROM trade_stock_basic 
            WHERE stock_code = %s 
            LIMIT 1
            """,
            [stock_code],
            env=self.env,
        )
        
        if rows and rows[0].get("sw_industry_name"):
            return rows[0]["sw_industry_name"]
        
        return ""
```

#### 3.2.2 周期股估值模型

**修改文件**：`research/fundamental/scorer.py`

```python
"""
基本面评分器 v2.0

新增：
- 行业类型识别
- 周期股 PB-ROE 估值模型
- 估值安全边际动态计算
"""
from dataclasses import dataclass
from typing import Optional
from research.industry_classifier import IndustryClassifier, IndustryType


@dataclass
class ScorerInput:
    pe_quantile: float
    pb_quantile: float
    roe: Optional[float]
    roe_prev: Optional[float]
    ocf_to_profit: Optional[float]
    debt_ratio: Optional[float]
    revenue_yoy: Optional[float]
    profit_yoy: Optional[float]
    
    # 新增
    industry_type: IndustryType = IndustryType.UNKNOWN
    commodity_price_quantile: Optional[float] = None  # 商品价格分位（周期股用）


class FundamentalScorer:
    """基本面评分器"""
    
    def __init__(self):
        self.industry_classifier = IndustryClassifier()
    
    def score(self, inp: ScorerInput) -> "ScorerResult":
        # 盈利质量评分（通用）
        eq_score = self._score_earnings_quality(inp)
        
        # 估值安全边际评分（按行业类型分流）
        va_score = self._score_valuation(inp)
        
        # 成长确定性评分（通用）
        gc_score = self._score_growth(inp)
        
        composite = int(eq_score * 0.4 + va_score * 0.4 + gc_score * 0.2)
        
        return ScorerResult(
            earnings_quality_score=eq_score,
            valuation_score=va_score,
            growth_score=gc_score,
            composite_score=composite,
            industry_type=inp.industry_type,
        )
    
    def _score_valuation(self, inp: ScorerInput) -> int:
        """
        估值安全边际评分
        
        - 周期股：PB-ROE 模型
        - 金融股：PB 主导
        - 成长/消费：PE 分位主导
        """
        if inp.industry_type == IndustryType.CYCLICAL:
            return self._score_valuation_cyclical(inp)
        elif inp.industry_type == IndustryType.FINANCIAL:
            return self._score_valuation_financial(inp)
        else:
            return self._score_valuation_growth(inp)
    
    def _score_valuation_cyclical(self, inp: ScorerInput) -> int:
        """
        周期股估值评分 - PB-ROE 模型
        
        逻辑：
        - 景气高点（高 ROE）+ 低 PB = 估值合理，给高分
        - 景气高点（高 ROE）+ 高 PB = 估值偏高，给中分
        - 景气低点（低 ROE）+ 低 PB = 可能是底部，给中高分
        - 景气低点（低 ROE）+ 高 PB = 估值陷阱，给低分
        
        注意：周期股不用 PE 分位，因为 PE 在景气高点反而很低
        """
        roe = inp.roe or 0
        pb_q = inp.pb_quantile
        
        # ROE > 15% 视为景气期
        is_boom = roe > 0.15
        
        # PB 分位 < 40% 视为低估
        is_cheap = pb_q < 0.4
        
        if is_boom and is_cheap:
            # 景气期 + 低 PB = 最佳买点
            base_score = 35
        elif is_boom and not is_cheap:
            # 景气期 + 高 PB = 需要谨慎
            base_score = 15
        elif not is_boom and is_cheap:
            # 低谷期 + 低 PB = 可能在底部
            base_score = 25
        else:
            # 低谷期 + 高 PB = 估值陷阱
            base_score = 5
        
        # 如果有商品价格分位数据，额外调整
        if inp.commodity_price_quantile is not None:
            if inp.commodity_price_quantile > 0.8:
                # 商品价格历史高位，景气可能见顶
                base_score -= 10
            elif inp.commodity_price_quantile < 0.3:
                # 商品价格历史低位，景气可能触底
                base_score += 5
        
        return max(0, min(40, base_score))
    
    def _score_valuation_financial(self, inp: ScorerInput) -> int:
        """
        金融股估值评分 - PB 主导
        
        金融股 PE 波动大，PB 更稳定可靠
        """
        pb_q = inp.pb_quantile
        
        if pb_q < 0.2:
            return 35  # 历史底部
        elif pb_q < 0.4:
            return 28
        elif pb_q < 0.6:
            return 20
        elif pb_q < 0.8:
            return 10
        else:
            return 0   # 历史高位
    
    def _score_valuation_growth(self, inp: ScorerInput) -> int:
        """
        成长/消费股估值评分 - PE 分位主导
        
        传统逻辑：低 PE 分位 = 低估 = 高分
        """
        pe_q = inp.pe_quantile
        pb_q = inp.pb_quantile
        
        # PE 权重 70%，PB 权重 30%
        pe_score = (1 - pe_q) * 28  # 0-28 分
        pb_score = (1 - pb_q) * 12  # 0-12 分
        
        return int(pe_score + pb_score)
```

#### 3.2.3 规则引擎修复

**修改文件**：`research/composite/aggregator.py`

```python
"""
综合评分聚合器 v2.0

修复：
- 泡沫期规则对周期股的逻辑错误
- 新增行业类型感知的规则
"""
from dataclasses import dataclass
from typing import Optional
from research.industry_classifier import IndustryType


@dataclass
class FiveSectionScores:
    score_technical: int
    score_fund_flow: int
    score_fundamental: int
    score_sentiment: int
    score_capital_cycle: int
    pe_quantile: float
    pb_quantile: float
    capital_cycle_phase: int
    founder_reducing: bool
    technical_breakdown: bool
    
    # 新增
    industry_type: IndustryType = IndustryType.UNKNOWN
    roe_current: Optional[float] = None
    commodity_price_quantile: Optional[float] = None


class RuleEngine:
    """跨截面规则引擎"""
    
    def evaluate_rules(self, scores: FiveSectionScores) -> list:
        """评估所有规则，返回触发的规则列表"""
        triggered = []
        
        # P1 泡沫期检测（区分行业类型）
        p1_result = self._check_bubble_risk(scores)
        if p1_result:
            triggered.append(p1_result)
        
        # P2 减仓破位
        if scores.founder_reducing and scores.technical_breakdown:
            triggered.append({
                "rule": "P2_REDUCE_BREAKDOWN",
                "signal": "strong_bear",
                "message": "创始人减持 + 技术破位，建议减仓",
                "override": True,
            })
        
        # BOOST 扩张期（需要基本面配合）
        if scores.capital_cycle_phase == 3 and scores.score_fundamental > 70:
            triggered.append({
                "rule": "BOOST_EXPANSION",
                "signal": "strong_bull",
                "message": "扩张高峰期 + 基本面优秀，可加仓",
                "weight_boost": 1.3,
            })
        
        return triggered
    
    def _check_bubble_risk(self, scores: FiveSectionScores) -> Optional[dict]:
        """
        泡沫风险检测
        
        周期股逻辑：
        - Phase 3/4 + 商品价格高位 + PB 高位 = 泡沫风险
        - 不用 PE 分位（周期股 PE 在景气高点反而很低）
        
        成长/消费股逻辑：
        - Phase 4 + PE 分位高位 = 泡沫风险
        """
        is_cyclical = scores.industry_type == IndustryType.CYCLICAL
        
        if is_cyclical:
            # 周期股泡沫检测
            is_late_cycle = scores.capital_cycle_phase in (3, 4)
            pb_high = scores.pb_quantile > 0.75
            commodity_high = (
                scores.commodity_price_quantile is not None 
                and scores.commodity_price_quantile > 0.85
            )
            
            if is_late_cycle and (pb_high or commodity_high):
                return {
                    "rule": "P1_BUBBLE_CYCLICAL",
                    "signal": "bear",
                    "message": f"周期股景气高点警告：Phase={scores.capital_cycle_phase}, "
                               f"PB分位={scores.pb_quantile:.0%}",
                    "triggered": True,
                }
        else:
            # 成长/消费股泡沫检测
            if scores.capital_cycle_phase == 4 and scores.pe_quantile > 0.8:
                return {
                    "rule": "P1_BUBBLE_GROWTH",
                    "signal": "bear",
                    "message": f"估值泡沫警告：Phase=4, PE分位={scores.pe_quantile:.0%}",
                    "triggered": True,
                }
        
        return None
```

### 3.3 情绪面去重与另类数据

#### 3.3.1 情绪面重构

**修改文件**：`research/sentiment/scorer.py`

```python
"""
情绪面评分器 v2.0

重构：
- 移除与技术面/资金面重复的指标
- 引入另类数据源（融资融券、北向偏离度）
- 保留无法自动获取的维度，但标记为"需手动输入"
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class SentimentInput:
    # 可自动获取的另类数据
    margin_balance_growth: Optional[float] = None   # 融资余额 5 日增速
    northbound_deviation: Optional[float] = None    # 北向资金偏离度（vs 20日均值）
    
    # 行业/板块动量（RPS）
    rps_120: float = 50.0
    
    # 需手动输入的数据（默认 50，标记为"待补充"）
    analyst_sentiment: Optional[int] = None         # 分析师情绪（上调/下调评级数）
    social_heat: Optional[int] = None               # 社交热度（雪球讨论量）
    macro_sentiment: Optional[int] = None           # 宏观情绪（政策环境）


@dataclass
class SentimentResult:
    composite_score: int
    
    # 各维度得分
    score_margin: int           # 融资余额动量
    score_northbound: int       # 北向资金偏离
    score_sector: int           # 板块动量（RPS）
    score_analyst: int          # 分析师情绪
    score_macro: int            # 宏观情绪
    
    # 数据可用性标记
    margin_available: bool
    northbound_available: bool
    analyst_manual: bool        # 是否需要手动输入
    macro_manual: bool
    
    label: str
    confidence: str             # HIGH/MEDIUM/LOW


class SentimentScorer:
    """
    情绪面评分器 v2.0
    
    权重分配（去重后）：
    - 融资余额动量: 25%（新增，替代原"资金流向情绪"）
    - 北向资金偏离: 25%（新增，替代原"资金流向情绪"）
    - 板块动量(RPS): 25%（保留）
    - 分析师情绪: 15%（保留，需手动）
    - 宏观情绪: 10%（保留，需手动）
    """
    
    WEIGHTS = {
        "margin": 0.25,
        "northbound": 0.25,
        "sector": 0.25,
        "analyst": 0.15,
        "macro": 0.10,
    }
    
    def score(self, inp: SentimentInput, stock_code: str = "") -> SentimentResult:
        scores = {}
        available = {}
        
        # 融资余额动量
        if inp.margin_balance_growth is not None:
            scores["margin"] = self._score_margin_growth(inp.margin_balance_growth)
            available["margin"] = True
        else:
            scores["margin"] = 50  # 默认中性
            available["margin"] = False
        
        # 北向资金偏离度
        if inp.northbound_deviation is not None:
            scores["northbound"] = self._score_northbound(inp.northbound_deviation)
            available["northbound"] = True
        else:
            scores["northbound"] = 50
            available["northbound"] = False
        
        # 板块动量（RPS）
        scores["sector"] = self._score_rps(inp.rps_120)
        
        # 分析师情绪（需手动输入）
        if inp.analyst_sentiment is not None:
            scores["analyst"] = inp.analyst_sentiment
        else:
            scores["analyst"] = 50
        
        # 宏观情绪（需手动输入）
        if inp.macro_sentiment is not None:
            scores["macro"] = inp.macro_sentiment
        else:
            scores["macro"] = 50
        
        # 加权计算
        composite = sum(
            scores[k] * self.WEIGHTS[k] for k in self.WEIGHTS
        )
        
        # 判断置信度
        auto_available = available.get("margin", False) or available.get("northbound", False)
        if auto_available and inp.analyst_sentiment is not None:
            confidence = "HIGH"
        elif auto_available:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        
        return SentimentResult(
            composite_score=int(composite),
            score_margin=scores["margin"],
            score_northbound=scores["northbound"],
            score_sector=scores["sector"],
            score_analyst=scores["analyst"],
            score_macro=scores["macro"],
            margin_available=available.get("margin", False),
            northbound_available=available.get("northbound", False),
            analyst_manual=(inp.analyst_sentiment is None),
            macro_manual=(inp.macro_sentiment is None),
            label=self._get_label(int(composite)),
            confidence=confidence,
        )
    
    def _score_margin_growth(self, growth: float) -> int:
        """融资余额 5 日增速评分"""
        # growth > 5% = 强看多，< -5% = 强看空
        if growth > 0.05:
            return 80
        elif growth > 0.02:
            return 65
        elif growth > -0.02:
            return 50
        elif growth > -0.05:
            return 35
        else:
            return 20
    
    def _score_northbound(self, deviation: float) -> int:
        """北向资金偏离度评分（相对 20 日均值的标准差倍数）"""
        # deviation > 2 sigma = 强买入，< -2 sigma = 强卖出
        if deviation > 2:
            return 85
        elif deviation > 1:
            return 70
        elif deviation > -1:
            return 50
        elif deviation > -2:
            return 30
        else:
            return 15
    
    def _score_rps(self, rps_120: float) -> int:
        """RPS120 评分"""
        if rps_120 >= 90:
            return 85
        elif rps_120 >= 70:
            return 65
        elif rps_120 >= 50:
            return 50
        elif rps_120 >= 30:
            return 35
        else:
            return 20
    
    def _get_label(self, score: int) -> str:
        if score >= 70:
            return "偏多"
        elif score >= 55:
            return "中性偏多"
        elif score >= 45:
            return "中性"
        elif score >= 30:
            return "中性偏空"
        else:
            return "偏空"
```

### 3.4 报告渲染层更新

#### 3.4.1 数据健康度模块

**修改文件**：`data_analyst/research_pipeline/renderer.py`

在报告顶部新增数据健康度展示：

```python
def _section_data_health(self, d: ReportData) -> str:
    """渲染数据健康度模块"""
    health = d.data_health
    
    # 状态图标
    def status_icon(ok: bool, warning: str = "") -> str:
        if ok and not warning:
            return '<span style="color:#27ae60;">[OK]</span>'
        elif warning:
            return f'<span style="color:#e74c3c;">[WARN]</span>'
        else:
            return '<span style="color:#f39c12;">[N/A]</span>'
    
    rows = []
    
    # 技术面
    rows.append(f"""
    <tr>
        <td>技术面数据</td>
        <td>{status_icon(health.technical.get('ok', False))}</td>
        <td>{health.technical.get('date', '-')}</td>
    </tr>
    """)
    
    # 资金流
    ff_ok = health.fund_flow.get('ok', False) and not health.fund_flow.get('missing', True)
    ff_warn = health.fund_flow.get('warning', '')
    rows.append(f"""
    <tr>
        <td>资金流数据</td>
        <td>{status_icon(ff_ok, ff_warn)}</td>
        <td>{ff_warn if ff_warn else 'OK'}</td>
    </tr>
    """)
    
    # 财务数据
    fin_ok = health.financial.get('ok', False) and not health.financial.get('stale', True)
    fin_warn = health.financial.get('warning', '')
    rows.append(f"""
    <tr>
        <td>财务数据</td>
        <td>{status_icon(fin_ok, fin_warn)}</td>
        <td>{fin_warn if fin_warn else f"最新年报: {health.financial.get('report_date', '-')}"}</td>
    </tr>
    """)
    
    # 估值数据
    rows.append(f"""
    <tr>
        <td>估值数据</td>
        <td>{status_icon(health.valuation.get('ok', False))}</td>
        <td>{health.valuation.get('date', '-')}</td>
    </tr>
    """)
    
    # RPS
    rps_ok = health.rps.get('ok', False)
    rows.append(f"""
    <tr>
        <td>RPS数据</td>
        <td>{status_icon(rps_ok)}</td>
        <td>{'OK' if rps_ok else '使用默认值 50'}</td>
    </tr>
    """)
    
    # 置信度
    confidence = health.confidence
    conf_color = {"HIGH": "#27ae60", "MEDIUM": "#f39c12", "LOW": "#e74c3c"}.get(confidence, "#888")
    
    return f"""
    <div class="info-card" style="border-left:4px solid {conf_color};">
        <h2>数据健康度检查</h2>
        <div class="badge-row">
            <span class="badge" style="background:{conf_color};">
                置信度: {confidence} ({health.completeness_pct}%)
            </span>
        </div>
        <div class="table-wrap">
            <table>
                <thead><tr><th>数据源</th><th>状态</th><th>说明</th></tr></thead>
                <tbody>{''.join(rows)}</tbody>
            </table>
        </div>
        {self._render_warnings(health.warnings)}
    </div>
    """
    
def _render_warnings(self, warnings: list) -> str:
    if not warnings:
        return ""
    
    items = "".join(f'<div class="danger-alert">{w}</div>' for w in warnings)
    return f'<h3>数据警告</h3>{items}'
```

#### 3.4.2 双维度评分展示

```python
def _overview_v2(self, d: ReportData) -> str:
    """
    v2.0 综合评分总览
    
    展示双维度：资产质地 + 交易择时
    """
    # 资产质地分 = 基本面 60% + 周期 40%
    quality_score = int(d.score_fundamental * 0.6 + d.score_capital_cycle * 0.4)
    
    # 交易择时分 = 技术 40% + 资金 35% + 情绪 25%
    timing_score = int(
        d.score_technical * 0.4 + 
        d.score_fund_flow * 0.35 + 
        d.score_sentiment * 0.25
    )
    
    quality_color = _score_color(quality_score)
    timing_color = _score_color(timing_score)
    
    quality_label = self._quality_label(quality_score)
    timing_label = self._timing_label(timing_score)
    
    # 综合建议
    suggestion = self._generate_suggestion(quality_score, timing_score, d)
    
    return f"""
    <div class="info-card" style="border:2px solid #3498db;">
        <h2>双维度评估总览 (v2.0)</h2>
        
        <div class="two-col">
            <div class="composite-score-box" style="border-right:1px solid #ddd;">
                <div style="font-size:12px;color:#888;">资产质地（买不买）</div>
                <div class="big-score" style="color:{quality_color};">{quality_score}</div>
                <div class="direction-label" style="color:{quality_color};">{quality_label}</div>
                <div class="hint">基本面 60% + 周期 40%</div>
            </div>
            <div class="composite-score-box">
                <div style="font-size:12px;color:#888;">交易择时（何时买）</div>
                <div class="big-score" style="color:{timing_color};">{timing_score}</div>
                <div class="direction-label" style="color:{timing_color};">{timing_label}</div>
                <div class="hint">技术 40% + 资金 35% + 情绪 25%</div>
            </div>
        </div>
        
        <div class="opportunity-alert" style="margin-top:15px;font-size:14px;">
            <strong>综合建议：</strong>{suggestion}
        </div>
        
        <div class="score-breakdown" style="margin-top:10px;">
            {self._breakdown_badges(d)}
        </div>
    </div>
    """
    
def _quality_label(self, score: int) -> str:
    if score >= 75:
        return "优质资产"
    elif score >= 60:
        return "质地良好"
    elif score >= 45:
        return "质地一般"
    else:
        return "质地较差"

def _timing_label(self, score: int) -> str:
    if score >= 70:
        return "择时偏多"
    elif score >= 55:
        return "企稳等待"
    elif score >= 40:
        return "短期回调"
    else:
        return "择时偏空"

def _generate_suggestion(self, quality: int, timing: int, d: ReportData) -> str:
    """根据双维度生成综合建议"""
    if quality >= 70 and timing >= 60:
        return "优质资产 + 择时偏多，可考虑加仓"
    elif quality >= 70 and timing < 45:
        return "优质资产回调中，关注支撑位企稳后左侧建仓"
    elif quality >= 60 and 45 <= timing < 60:
        return "质地良好，短期震荡，持仓观望"
    elif quality < 50 and timing >= 60:
        return "质地一般但短期强势，谨慎追高，控制仓位"
    elif quality < 50 and timing < 45:
        return "质地一般 + 短期弱势，建议减仓或回避"
    else:
        return "维持现有仓位，等待信号明确"
```

---

## 四、数据库表更新

### 4.1 新增字段

```sql
-- trade_stock_basic 新增申万行业字段（如果没有）
ALTER TABLE trade_stock_basic 
ADD COLUMN IF NOT EXISTS sw_industry_name VARCHAR(50) COMMENT '申万一级行业';

-- composite_scores 新增双维度字段
ALTER TABLE composite_scores
ADD COLUMN quality_score TINYINT COMMENT '资产质地分',
ADD COLUMN timing_score TINYINT COMMENT '交易择时分',
ADD COLUMN industry_type VARCHAR(20) COMMENT '行业类型',
ADD COLUMN data_confidence VARCHAR(10) COMMENT '数据置信度 HIGH/MEDIUM/LOW';
```

### 4.2 新增表

```sql
-- 数据健康度日志
CREATE TABLE IF NOT EXISTS data_health_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    stock_code VARCHAR(20),
    check_date DATE,
    completeness_pct TINYINT,
    confidence VARCHAR(10),
    technical_ok BOOLEAN,
    fund_flow_ok BOOLEAN,
    fund_flow_missing BOOLEAN,
    financial_ok BOOLEAN,
    financial_stale BOOLEAN,
    financial_report_date DATE,
    valuation_ok BOOLEAN,
    rps_ok BOOLEAN,
    warnings_json JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_code_date (stock_code, check_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据健康度检测日志';

-- 行业类型映射表（便于维护）
CREATE TABLE IF NOT EXISTS industry_type_map (
    id INT PRIMARY KEY AUTO_INCREMENT,
    sw_industry_name VARCHAR(50) UNIQUE,
    industry_type ENUM('周期资源','金融地产','成长科技','消费医药','未分类'),
    valuation_model VARCHAR(20) COMMENT '适用估值模型',
    notes VARCHAR(200),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万行业到估值类型映射';

-- 初始化映射数据
INSERT INTO industry_type_map (sw_industry_name, industry_type, valuation_model) VALUES
('石油石化', '周期资源', 'PB-ROE'),
('煤炭', '周期资源', 'PB-ROE'),
('有色金属', '周期资源', 'PB-ROE'),
('钢铁', '周期资源', 'PB-ROE'),
('基础化工', '周期资源', 'PB-ROE'),
('银行', '金融地产', 'PB'),
('非银金融', '金融地产', 'PB'),
('房地产', '金融地产', 'PB'),
('电子', '成长科技', 'PE'),
('计算机', '成长科技', 'PE'),
('电力设备', '成长科技', 'PE'),
('食品饮料', '消费医药', 'PE'),
('医药生物', '消费医药', 'PE')
ON DUPLICATE KEY UPDATE industry_type = VALUES(industry_type);
```

---

## 五、实现计划

### Phase 1: 数据层修复（P0，2天）

| 任务 | 文件 | 预估 |
|------|------|------|
| 财务数据过时检测 | `fetcher.py` | 2h |
| 资金流缺失检测 | `fetcher.py` | 2h |
| 数据健康度检测器 | `health_checker.py` (新建) | 4h |
| 报告渲染数据健康度模块 | `renderer.py` | 3h |
| 单元测试 | `tests/test_health_checker.py` | 2h |

### Phase 2: 行业异质性处理（P0，2天）

| 任务 | 文件 | 预估 |
|------|------|------|
| 行业类型分类器 | `industry_classifier.py` (新建) | 3h |
| 周期股 PB-ROE 估值模型 | `fundamental/scorer.py` | 4h |
| 规则引擎周期股适配 | `composite/aggregator.py` | 3h |
| 数据库表更新 | SQL migration | 1h |
| 单元测试 | `tests/test_industry_scorer.py` | 2h |

### Phase 3: 双维度评估体系（P1，2天）

| 任务 | 文件 | 预估 |
|------|------|------|
| 双维度聚合逻辑 | `composite/aggregator.py` | 4h |
| 报告渲染双维度展示 | `renderer.py` | 4h |
| 综合建议生成器 | `composite/suggestion.py` (新建) | 3h |
| 单元测试 | `tests/test_dual_dimension.py` | 2h |

### Phase 4: 情绪面重构（P1，2天）

| 任务 | 文件 | 预估 |
|------|------|------|
| 融资余额数据接入 | `fetcher.py` | 3h |
| 北向资金偏离度计算 | `fetcher.py` | 3h |
| 情绪面评分器重构 | `sentiment/scorer.py` | 4h |
| 报告渲染情绪面更新 | `renderer.py` | 2h |
| 单元测试 | `tests/test_sentiment_v2.py` | 2h |

### Phase 5: 集成测试与上线（1天）

| 任务 | 描述 | 预估 |
|------|------|------|
| 端到端测试 | 用中国海油、云铝股份验证修复效果 | 3h |
| 回归测试 | 对比 v1.0 和 v2.0 的评分差异 | 2h |
| 文档更新 | 更新 CLAUDE.md 和 README | 1h |
| 发布 | 合并到 main 分支 | 1h |

---

## 六、验收标准

### 6.1 数据层修复验收

- [ ] 云铝股份报告显示 `[STALE] 财务数据距今 XX 个月` 警告
- [ ] 中国海油报告资金面显示 `[MISSING] 无资金流向数据` 而非 `+0.00亿`
- [ ] 数据健康度模块在报告顶部正确展示
- [ ] 缺失数据的截面评分标记为 `N/A` 或降低权重

### 6.2 模型层修复验收

- [ ] 中国海油（石油石化）识别为"周期资源"类型
- [ ] 云铝股份（有色金属）识别为"周期资源"类型
- [ ] 周期股使用 PB-ROE 模型评分，不使用 PE 分位
- [ ] 规则引擎 P1 泡沫期对周期股使用正确逻辑

### 6.3 双维度验收

- [ ] 报告展示"资产质地"和"交易择时"两个独立分数
- [ ] 综合建议根据双维度组合生成差异化文案
- [ ] 优质资产回调时不再被判为"中性观望"

### 6.4 情绪面验收

- [ ] 情绪面不再与技术面/资金面重复计分
- [ ] 融资余额动量、北向偏离度正确计算（如有数据）
- [ ] 需手动输入的维度标记为"待补充"

---

## 七、风险与依赖

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 申万行业数据不完整 | 无法识别行业类型 | 提供默认类型 + 手动配置入口 |
| 融资余额数据源不稳定 | 情绪面部分维度缺失 | 降级为使用默认值 + 标记 |
| 商品价格数据无接入 | 周期股景气判断不精确 | Phase 1 暂用 ROE 替代，后续接入 |
| 用户习惯单一综合分 | v2.0 双维度可能造成困惑 | 同时保留综合分作为参考 |

---

## 八、附录：外部评审意见原文

> **1. 周期股的"估值陷阱"（最核心的问题）**
> 你选取的两只股票（铝、石油）都是强周期资源股。在你的"基本面"截面中，使用了 PE(TTM) 和 PB 的 5 年历史分位来评价估值。潜在问题：周期股的估值逻辑与成长股/消费股完全相反，通常是"高市盈率买入，低市盈率卖出"。

> **2. 长短周期指标的"大杂烩"导致信号中和**
> 你的综合得分是将极短期的交易指标（MA5、5日资金流向、RSI14）与极长期的投资指标（5年 ROE 轨迹、资本周期 Phase）进行线性加权。如果一只股票基本面和资本周期处于极佳的长线买点，但短期刚好在回调洗盘，加权后就会变成"50分左右的中性"。

> **3. 指标存在"多重共线性"（重复计分）**
> 在"截面四：情绪面"中，你包含了"资金流向情绪（30%）"和"量价动量情绪（25%）"。这两个维度与"截面一：技术面"和"截面二：资金面"存在严重的重叠。

> **4. 数据管道可能存在的 Bug**
> 在两份报告的"资金面"中，近 5 日和近 20 日的主力净流入金额和占市值比全部为 `+0.00亿` 和 `+0.00%`。

> **5. 规则引擎（触发检测）的逻辑冲突**
> `P1 泡沫期：Phase==4 AND PE分位>80%`。当资本周期进入 Phase 4 时，由于过剩产能刚释放，通常利润还在高位，此时的 PE 分位往往是极低的（低估值陷阱）。

---

> 文档维护：本方案为 FiveSectionFramework v2.0 的完整技术设计，后续迭代请更新版本号。
