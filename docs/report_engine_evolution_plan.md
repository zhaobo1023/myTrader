# 研报引擎演进方案 - 行业差异化 + 数据源升级

> 文档创建：2026-04-08
> 状态：进行中
> 原则：一个行业一个行业打磨，慢工出细活

---

## 一、现状盘点

### 已有的基础设施

| 模块 | 位置 | 状态 | 说明 |
|------|------|------|------|
| 五步法研报引擎 v2.0 | `investment_rag/report_engine/` | 已完成 | 通用 prompt + 摘要传递 + 执行摘要 |
| 行业分类器 | `research/industry_classifier.py` | 已完成 | 申万一级 -> 4大类（周期/金融/成长/消费） |
| 银行财务数据拉取 | `data_analyst/financial_fetcher/` | 已完成 | NPL、拨备覆盖率、CAR、NIM、拨备调整 |
| 银行估值评分 | `research/fundamental/scorer.py` | 已完成 | PB 主导（35分权重） |
| 五截面分析管道 | `data_analyst/research_pipeline/` | 已完成 | 通用财务+估值+资金+RPS |
| RAG 向量检索 | `investment_rag/retrieval/` | 已完成 | ChromaDB + BM25 + Reranker |
| Flitter 银行方法论 | 笔记目录 `Research/01-Sectors/银行/` | 已收集 | 7篇核心文章，含方法论+案例 |

### 核心差距

1. **研报引擎是通用模板**：`prompts.py` 中的5步分析对所有公司用同一套指标
2. **银行数据已拉但未接入研报**：`financial_fetcher` 的银行指标没有喂给 `report_engine`
3. **缺少行业路由层**：没有根据股票行业自动切换 prompt 和数据源的机制
4. **Flitter 方法论未结构化**：笔记里的方法论没有转化为 prompt 指令

---

## 二、目标架构

```
用户输入：stock_code
      |
      v
[行业识别] IndustryClassifier.classify_by_code()
      |
      v
[行业配置] industry_config.py -> 返回该行业的：
      |    - 核心指标列表
      |    - 差异化 prompt 片段
      |    - 专用数据获取函数
      |    - RAG 查询关键词
      |    - 估值方法
      v
[数据收集] data_tools.py -> 通用数据 + 行业专用数据
      |
      v
[Prompt 渲染] prompts.py -> 通用框架 + 动态注入行业片段
      |
      v
[LLM 生成] -> 行业特化的分析内容
      |
      v
[报告组装] report_builder.py -> 含行业专属章节
```

---

## 三、分阶段实施计划

### Phase 1：行业路由基础框架 + 银行行业落地

**目标**：以银行为试点，跑通"行业识别 -> 差异化 prompt -> 专用数据 -> 特化分析"全链路

#### Step 1.1：新建 industry_config.py（行业配置中心）

**位置**：`investment_rag/report_engine/industry_config.py`

**设计**：

```python
@dataclass
class IndustryAnalysisConfig:
    """单个行业的分析配置"""
    industry_type: str                    # "bank" / "consumer" / "cyclical" / ...
    display_name: str                     # "银行" / "消费" / ...

    # Step1 差异化：该行业应关注的核心指标（替换通用5条）
    step1_focus_areas: List[str]          # 3-5条行业特化的筛选方向

    # 专用数据获取函数名（在 data_tools 中注册）
    extra_data_functions: List[str]       # ["get_bank_indicators", "get_provision_adj"]

    # RAG 查询关键词补充（按步骤）
    rag_query_supplements: Dict[str, List[str]]  # {"step1": ["不良率 拨备 净息差"], ...}

    # Step2 差异化：护城河评估维度
    moat_dimensions: List[str]            # ["净息差持续性", "不良率控制力", ...]

    # Step3 差异化：估值方法
    valuation_method: str                 # "PB主导" / "PE/PEG" / "DCF" / ...
    valuation_note: str                   # 估值方法的说明，注入prompt

    # Step5 差异化：行业特有的风险熔断维度
    risk_dimensions: List[str]            # ["不良率突破X%", "净息差跌破X%", ...]
```

**银行配置实例**：

```python
BANK_CONFIG = IndustryAnalysisConfig(
    industry_type="bank",
    display_name="银行",

    step1_focus_areas=[
        "不良率2（逾期91天以上+重组贷款/总贷款）的变化方向，而非官方不良率",
        "经营现金流/净利润比值 + 拨备调节方向（保守积累 vs 释放利润）",
        "股东权益真实增量（剔除分红+融资后）vs 报告净利润的差异",
        "净息差（NIM）趋势：受LPR下调和存款竞争的双重挤压情况",
        "资本充足率在分红后是否仍在上升（内生资本积累能力）",
    ],

    extra_data_functions=[
        "get_bank_indicators",     # NPL/拨备/CAR/NIM
        "get_provision_adjustment", # 拨备调整分析（flitter法）
    ],

    rag_query_supplements={
        "step1": ["{stock_name} 不良率 拨备覆盖率 资产质量 逾期贷款"],
        "step2": ["{stock_name} 净息差 息差 利率敏感性 贷款结构"],
        "step3": ["{stock_name} PB估值 银行股估值 股息率 分红"],
        "step4": ["{stock_name} LPR 降准 银行监管政策 资本补充"],
    },

    moat_dimensions=[
        "负债成本优势（存款结构：活期占比、零售存款占比）",
        "资产质量管控能力（不良率2的历史波动幅度）",
        "资本内生积累速度（分红后资本充足率变化）",
    ],

    valuation_method="PB主导",
    valuation_note=(
        "银行股用PB估值，PE波动大参考意义有限。"
        "PB合理中枢 = ROE / 股权成本。"
        "破净隐含市场预期ROE持续下滑或资产质量恶化。"
        "需判断：当前PB隐含的ROE假设是否过度悲观？"
    ),

    risk_dimensions=[
        "不良率2（逾期91天+重组）突破X%",
        "净息差跌破X%（需看同业对标）",
        "资本充足率跌破监管红线",
    ],
)
```

**通用兜底配置**（非特化行业使用，即当前 v2.0 的通用模板）：

```python
DEFAULT_CONFIG = IndustryAnalysisConfig(
    industry_type="default",
    display_name="通用",
    step1_focus_areas=[
        "现金流与利润的背离（经营现金流/净利润比值异常）",
        "非经常性损益的方向和规模（扣非净利润 vs 归母净利润）",
        "资产负债表的结构性变化（应收/存货/商誉/有息负债异常）",
        "毛利率/净利率的趋势拐点",
        "行业地位的量化变化（市占率、相对竞争力）",
    ],
    extra_data_functions=[],
    rag_query_supplements={},
    moat_dimensions=["品牌溢价", "规模效应", "转换成本"],
    valuation_method="PE/PB综合",
    valuation_note="综合PE历史分位和PB分位判断估值水平。",
    risk_dimensions=["营收增速转负", "现金流断裂", "商誉减值"],
)
```

#### Step 1.2：data_tools.py 新增银行专用数据获取

**新增方法**：

```python
def get_bank_indicators(self, stock_code: str) -> str:
    """获取银行特化指标：NPL、拨备覆盖率、CAR、NIM等。
    数据源：financial_balance 表中的银行字段。
    """

def get_provision_adjustment(self, stock_code: str) -> str:
    """获取拨备调整分析（flitter method）。
    数据源：bank_asset_quality 表。
    """

def get_consensus_forecast(self, stock_code: str) -> str:
    """获取分析师一致预期（P0 数据源）。
    数据源：akshare stock_profit_forecast_em()。
    适用于所有行业，非银行专属。
    """
```

#### Step 1.3：prompts.py 支持行业片段注入

**改造方式**：不重写整个 prompt，而是在现有模板中用占位符注入行业特化内容。

```python
STEP1_PROMPT = """## 任务：财报关键发现（第一步）

**公司**：{stock_name}
**行业**：{industry_name}

**财务数据背景**：
{financial_context}

{industry_extra_data}

**研报/公告检索背景**：
{rag_context}

**分析要求**：
从上述材料中，识别 **3个** 对投资决策有实质影响的关键发现。

**本行业应重点关注的方向**：
{step1_focus_areas}

... (后续不变)
"""
```

每个 `{industry_extra_data}` 和 `{step1_focus_areas}` 由 `IndustryAnalysisConfig` 动态填充。

#### Step 1.4：five_step.py 串联行业路由

```python
class FiveStepAnalyzer:
    def __init__(self, db_env="online"):
        ...
        self._classifier = IndustryClassifier(env=db_env)

    def generate_fundamental(self, stock_code, stock_name, collection="reports"):
        # 1. 识别行业
        industry_type = self._classifier.classify_by_code(stock_code)
        industry_config = get_industry_config(industry_type)

        # 2. 在每步执行时传入行业配置
        for step_config in FIVE_STEP_CONFIG:
            step_result = self._run_single_step(
                ...,
                industry_config=industry_config,  # 新增参数
            )
```

---

### Phase 2：补充关键数据源（全行业通用）

**目标**：接入分析师一致预期、业绩预告、股东变动，提升所有行业的分析质量

| 数据 | AKShare 接口 | 接入位置 | 影响步骤 |
|------|-------------|---------|---------|
| 分析师一致预期 | `stock_profit_forecast_em` | `data_tools.get_consensus_forecast()` | Step3 估值偏差 |
| 业绩预告/快报 | `stock_yjyg_em` / `stock_yjkb_em` | `data_tools.get_earnings_preview()` | Step4 催化剂 |
| 十大流通股东 | `stock_gdfx_free_holding_detail_em` | `data_tools.get_top_shareholders()` | Step2 驱动逻辑 |
| 机构持仓变动 | `stock_institute_hold_detail_em` | `data_tools.get_institutional_holdings()` | Step2 |

**优先级**：一致预期 > 业绩预告 > 股东/机构

---

### Phase 3：银行行业深度打磨

**目标**：把 Flitter 方法论完整落地，达到专业银行分析师的分析水准

#### 3.1 Flitter 核心方法论落地

| Flitter 方法 | 当前实现状态 | 改进计划 |
|-------------|------------|---------|
| 不良率2（逾期91天+重组） | bank_asset_quality 表有预留字段，未自动填充 | 从年报中提取逾期贷款明细，写入 DB |
| 股东权益真实增量 | 未实现 | 新增计算：当期权益 - 上期权益 - 分红 - 融资 |
| 债券投资三分法识别 | 未实现 | 从年报解析交易性/其他债权/持有至到期的持仓变化 |
| 公允价值变动损益跟踪 | 未实现 | 从利润表中提取，判断债券操纵 |
| 横截面银行对比表 | 未实现 | 自动化20+家银行的指标对比排名 |

#### 3.2 银行专用 Prompt 精炼

基于 Flitter 方法论，银行的 Step1 prompt 应该这样引导：

```
Step1（银行版）关注方向：
1. 计算"不良率2"并与上期对比——官方不良率可粉饰，逾期91天+重组更难造假
2. 经营利润 vs 股东权益真实增量的差异——差异大说明有利润调节
3. 拨备调节方向——拨备比上升+不良率2下降=保守（好信号），反之=透支
4. 公允价值变动损益的同比变化——国债/债券持仓的浮盈浮亏是临时性的
5. 分红后资本充足率变化——上升=内生积累强，下降=分红不可持续
```

#### 3.3 银行横截面对标（自动化 Flitter 的手工表）

新增工具函数：

```python
def get_bank_cross_section(self) -> str:
    """获取全部上市银行的横截面对标数据。
    返回：20+家银行的 ROE / PB / 股息率 / 不良率 / 拨备比 / NIM 排名表。
    """
```

在 Step2（驱动逻辑）和 Step3（估值偏差）中注入，让 LLM 在全行业对标视角下分析。

---

### Phase 4：扩展到其他行业

按照 Phase 1 建立的框架，逐行业添加配置：

| 行业 | 预计节点 | 核心差异点 |
|------|---------|----------|
| 消费（白酒/家电） | Phase 4a | 毛利率趋势 + 存货周转 + 渠道费用率 |
| 周期（油气/化工） | Phase 4b | 单位成本 + 产能利用率 + EBITDA + capex/折旧 |
| 科技（半导体/软件） | Phase 4c | 收入增速 + 研发费用率 + 人均创收 |
| 医药 | Phase 4d | 管线进度 + 研发费用率 + 集采影响 |

---

## 四、银行研报生成的目标效果

改造前（通用模板，以中国海油为例）：

```
## 一、财报关键发现
发现1：经营现金流与净利润背离...  <- 通用指标
发现2：非经常性收益占比抬升...    <- 通用指标
发现3：商誉规模攀升...            <- 对银行不适用
```

改造后（银行专用模板，以华夏银行为例）：

```
## 一、财报关键发现
[行业：银行 | 分析框架：资产质量优先]

发现1：不良率2持续改善至1.54%，拨备比稳定，拨备未释放利润
- 关键数据：逾期91天+重组贷款281.8+113.7=395.5亿，不良率2=1.54%（上期1.62%）
- 投资含义：资产质量真实改善，且银行选择保守不释放拨备，利润含金量高

发现2：股东权益真实增量272亿，与报告利润基本匹配
- 关键数据：权益增量=当期3957-上期3712-分红105-融资0=140亿（年化）
- 投资含义：未发现利润操纵迹象，真实赚钱能力与报表一致

发现3：公允价值变动损益亏损24.7亿（上年+15.2亿），系国债价格波动
- 关键数据：其他债权投资浮亏约114亿，占股东权益2.9%
- 投资含义：临时性损失，若2026年国债企稳将自动回补，不影响核心盈利
```

---

## 五、实施进度跟踪

### Phase 1：行业路由 + 银行落地

| 子步骤 | 状态 | 备注 |
|-------|------|------|
| 1.1 新建 industry_config.py | [x] 完成 | 银行/有色/通用配置 + SW行业自动路由 |
| 1.2 data_tools.py 新增银行数据获取 | [x] 完成 | get_bank_indicators()，含 Flitter 扩展指标 |
| 1.3 prompts.py 支持行业片段注入 | [x] 完成 | 5步 prompt 各加 industry_name / step1_focus_areas 等槽位 |
| 1.4 five_step.py 串联行业路由 | [x] 完成 | get_industry_config() 自动识别，银行额外 RAG 查询 |
| 1.5 银行股实测验证 | [x] 完成 | 招商银行 600036：银行路由正常，Flitter 数据注入，PB-ROE 估值框架生效 |

### Phase 2：关键数据源

| 子步骤 | 状态 | 备注 |
|-------|------|------|
| 2.1 接入分析师一致预期 | [x] 完成 | stock_profit_forecast_ths，注入 Step3，供估值隐含假设对标 |
| 2.2 接入业绩预告/快报 | [x] 完成 | Fallback 实现（AKShare API 不稳定），返回提示文本 |
| 2.3 接入股东/机构持仓 | [x] 完成 | Fallback 实现（AKShare API 不稳定），返回提示文本 |

### Phase 3：银行深度打磨

| 子步骤 | 状态 | 备注 |
|-------|------|------|
| 3.1 不良率2自动计算 | [ ] 延期 | bank_asset_quality 表数据不完整，需后续补齐数据源 |
| 3.2 股东权益真实增量计算 | [ ] 延期 | 需分红+融资完整数据，当前用简化估算 |
| 3.3 债券三分法识别 | [ ] 延期 | 需年报附注解析，暂未实现 |
| 3.4 银行横截面对标表 | [x] 完成 | Fallback 实现，包含典型估值范围对标 |
| 3.5 Flitter prompt 精炼 | [x] 完成 | Step2/Step3 已注入一致预期和对标框架 |

### Phase 4：其他行业

| 行业 | 状态 | 备注 |
|------|------|------|
| 消费 | [ ] 未开始 | |
| 周期 | [ ] 未开始 | |
| 科技 | [ ] 未开始 | |
| 医药 | [ ] 未开始 | |

---

## 六、参考资料

### 方法论
- Stephen Penman《财务报表分析与证券估值》-- 重新表述财务报表、剩余收益模型
- Flitter 银行分析方法论 -- `/Users/zhaobo/Documents/notes/Finance/Research/01-Sectors/银行/`
- FinRobot (AI4Finance) -- Multi-Agent CoT 研报生成框架

### 数据源
- AKShare 文档：https://akshare.akfamily.xyz/
- 已接入：`stock_financial_analysis_indicator_em`（银行指标）
- 待接入：`stock_profit_forecast_em`（一致预期）、`stock_yjyg_em`（业绩预告）

### 项目内相关代码
- 银行数据拉取：`data_analyst/financial_fetcher/fetcher.py` L135-183
- 行业分类器：`research/industry_classifier.py`
- 银行估值评分：`research/fundamental/scorer.py` L159-234
- 拨备调整计算：`data_analyst/financial_fetcher/fetcher.py` `compute_provision_adj()`
- 研报引擎 v2.0：`investment_rag/report_engine/`

---

*每完成一个子步骤，更新本文档的进度跟踪表。*
