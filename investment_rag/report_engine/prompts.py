# -*- coding: utf-8 -*-
"""
Five-step research report Prompt templates.

Design principles:
- Each step's output becomes {prev_analysis} context for next step (progressive chain)
- Each step has independent RAG query list for targeted multi-angle retrieval
- No emoji characters (use plain text: [RED]/[OK]/[WARN])
- All prompts output Markdown format for easy assembly
"""
from dataclasses import dataclass, field
from typing import List

# ============================================================
# System prompt
# ============================================================

ANALYST_SYSTEM_PROMPT = """You are a professional investment research analyst focused on the A-share market.
Analysis is fact-based, logically clear, combining quantitative and qualitative methods.
Output format is Markdown, well-structured, suitable for professional research reports.
No exaggeration, no unfounded predictions; clearly mark uncertain content as "needs verification".
Today's date: {today}
"""

# ============================================================
# Step 1: Information Gap
# ============================================================

STEP1_PROMPT = """## Task: Information Gap Analysis (Step 1)

**Company**: {stock_name}

**Financial Data Context**:
{financial_context}

**Research Report/Announcement Retrieval Context**:
{rag_context}

**Instructions**:
From the above materials, identify 3-5 key information points that the market may have overlooked (information gap):
1. Hidden highlights or risks in financial report footnotes (accounting policy changes, impairment details)
2. Divergence between cash flow and profit (high profit, low cash flow warning)
3. Impact of non-recurring items on net profit and true earning power after exclusion
4. Structural changes in balance sheet (abnormal growth in receivables/inventory)
5. Quantitative evidence of industry position changes (market share, gross margin trends)

**Output Format** (strictly follow):
### Information Gap Analysis

#### Key Information Point 1: [Title]
- Data: [specific numbers or ratios]
- Market Common Understanding: [...]
- Actual Situation: [what you found different]
- Importance: [High/Medium/Low]

(Repeat for 3-5 points)

#### Data Limitations
[Data limitations for this analysis, what needs additional verification]
"""

STEP1_RAG_QUERIES = [
    "{stock_name} financial indicators revenue net profit gross margin cash flow",
    "{stock_name} annual report quarterly report accounts receivable impairment non-recurring items",
    "{stock_name} accounting policy financial footnotes subsidies impairment",
]

# ============================================================
# Step 2: Logic Gap
# ============================================================

STEP2_PROMPT = """## Task: Logic Gap Analysis (Step 2)

**Company**: {stock_name}

**Previous Step Analysis (Information Gap)**:
{prev_analysis}

**Supplementary Retrieval Context**:
{rag_context}

**Instructions**:
Based on the information gap from Step 1, identify market logic misconceptions and build correct analytical framework:
1. Point out 1-3 most common linear thinking or false analogies in the market
2. Build correct driver factor chain (A causes B causes C causal logic)
3. Identify the company's true core competitive moat (quantifiable)
4. Assess completeness and sustainability of current logic chain

**Output Format**:
### Logic Gap Analysis

#### Market Misconceptions
| Misconception | Reason for Error | Correct Logic |
|--------------|-----------------|---------------|
| [misconception 1] | [reason] | [correct analysis] |

#### Correct Driver Logic Chain
[A] -> [B] -> [C] -> [stock price driver]

#### Core Competitive Moat Assessment
[Qualitative description + quantifiable metrics]

#### Logic Sustainability Judgment
[Expected duration of current driver logic and key variables]
"""

STEP2_RAG_QUERIES = [
    "{stock_name} competitive advantage moat market share industry position",
    "{stock_name} business model profit model core competitiveness",
    "{stock_name} industry landscape competitors peer companies",
]

# ============================================================
# Step 3: Expectation Gap
# ============================================================

STEP3_PROMPT = """## Task: Expectation Gap Analysis (Step 3)

**Company**: {stock_name}

**Accumulated Previous Analysis**:
{prev_analysis}

**Financial Data Context**:
{financial_context}

**Valuation Historical Percentile**:
{valuation_context}

**Instructions**:
Build comparison between consensus expectations and reality, quantify expectation gap:
1. Summarize market consensus expectations for core metrics (revenue/net profit/gross margin/ROE)
2. Compare with actual data, quantify deviation magnitude
3. Assess scale (large/medium/small) and expected duration of expectation gap
4. Judge whether current valuation already reflects this expectation gap

**Output Format**:
### Expectation Gap Analysis

| Metric | Market Consensus | Actual/Forecast | Deviation | Confidence |
|--------|-----------------|-----------------|-----------|------------|
| Revenue Growth | X% | Y% | +/- Z% | High/Medium/Low |
| Net Profit Growth | X% | Y% | +/- Z% | High/Medium/Low |
| Gross Margin | X% | Y% | +/- Z pct | High/Medium/Low |
| ROE | X% | Y% | +/- Z pct | High/Medium/Low |

#### Valuation Implied Expectations
[Growth assumption implied by current PE/PB vs your judgment]

#### Expectation Gap Realization Window
[When will this gap be recognized by market, key observation nodes]
"""

STEP3_RAG_QUERIES = [
    "{stock_name} performance expectations consensus analyst forecast",
    "{stock_name} valuation PE PB historical percentile valuation center",
    "{stock_name} revenue growth net profit growth forecast",
]

# ============================================================
# Step 4: Catalysts
# ============================================================

STEP4_PROMPT = """## Task: Catalyst Identification (Step 4)

**Company**: {stock_name}

**Accumulated Previous Analysis**:
{prev_analysis}

**Retrieval Context (Policy/Events/Announcements)**:
{rag_context}

**Instructions**:
Identify catalysts that drive expectation gap realization, arranged by timeline:
1. Short-term catalysts (1-3 months): earnings guidance, important meetings, industry policy
2. Medium-term catalysts (3-12 months): new product ramp-up, overseas expansion, M&A integration
3. Negative catalysts (risk events to watch, with probability)

**Output Format**:
### Catalyst Analysis

#### Short-term Catalysts (1-3 months)
| Event | Expected Time | Direction | Magnitude |
|-------|--------------|-----------|-----------|
| [event 1] | [time] | [Positive/Negative] | [Large/Medium/Small] |

#### Medium-term Catalysts (3-12 months)
| Event | Expected Time | Direction | Magnitude |
|-------|--------------|-----------|-----------|

#### Negative Catalysts (Risks)
| Risk Event | Probability | Impact Level | Response Suggestion |
|-----------|------------|--------------|---------------------|
"""

STEP4_RAG_QUERIES = [
    "{stock_name} policy benefits industry policy regulation policy risk",
    "{stock_name} new products new projects strategic plan expansion",
    "{stock_name} risks uncertainties challenges competitive pressure",
]

# ============================================================
# Step 5: Comprehensive Conclusion
# ============================================================

STEP5_PROMPT = """## Task: Comprehensive Conclusion (Step 5)

**Company**: {stock_name}

**Complete Previous Analysis (Info Gap + Logic Gap + Expectation Gap + Catalysts)**:
{prev_analysis}

**Technical Data**:
{technical_context}

**Valuation Historical Percentile**:
{valuation_context}

**Expected Return Estimate**:
{expected_return_context}

**Instructions**:
Synthesize all four previous steps into actionable investment conclusion:
1. Investment rating (Strong Buy / Buy / Neutral / Sell)
2. Core investment thesis (2-3 concise sentences)
3. Key assumptions (conditions for logic to hold)
4. Risk circuit breaker (3 conditions that invalidate the thesis)
5. Reference price levels (combined with technical support/resistance)

**Output Format**:
### Comprehensive Conclusion

**Rating**: [Strong Buy / Buy / Neutral / Sell]

**Core Thesis**:
[2-3 sentence core investment logic with quantitative support]

#### Key Assumptions
1. [assumption 1]
2. [assumption 2]
3. [assumption 3]

#### Risk Circuit Breaker (Invalidation Conditions)
| Invalidation Condition | Probability | Recommended Action |
|----------------------|------------|-------------------|
| [condition 1] | High/Medium/Low | Stop-loss/Reduce/Hold |
| [condition 2] | High/Medium/Low | ... |
| [condition 3] | High/Medium/Low | ... |

#### Reference Price Levels (Technical)
- Support: [price] (source: [MA20/BOLL lower/previous low])
- Resistance: [price] (source: [MA60/BOLL upper/previous high])
- Suggested Stop-loss: [price] (source: [ATR/MA20])
"""

# ============================================================
# Technical Analysis Prompt
# ============================================================

TECH_ANALYSIS_PROMPT = """## Technical Analysis Task

**Company**: {stock_name} ({stock_code})

**Technical Indicator Data**:
{technical_data}

**Instructions**:
Based on the above technical data, provide concise technical judgment:
1. Current trend (uptrend/downtrend/consolidation) and strength
2. Key support/resistance levels (based on MA/BOLL/previous high-low)
3. Main signal interpretation (golden cross/death cross/divergence/overbought/oversold)
4. Short-term operational suggestion (hold/add/reduce/wait)

**Output Format**:
### Technical Analysis

**Trend**: [Uptrend / Downtrend / Consolidation] - [Strong / Moderate / Weak]

**Key Price Levels**:
| Type | Level | Source |
|------|-------|--------|
| Support 1 | XXX | MA20 |
| Support 2 | XXX | BOLL Lower |
| Resistance 1 | XXX | MA60 |
| Resistance 2 | XXX | BOLL Upper |

**Signal Interpretation**:
[Explain each major signal and its implications]

**MACD Divergence**:
[Divergence type and confidence description]

**Short-term Suggestion**: [Hold / Add / Reduce / Wait], Reason: [...]
"""

# ============================================================
# StepConfig and FIVE_STEP_CONFIG
# ============================================================

@dataclass
class StepConfig:
    """Configuration for a single analysis step."""
    step_id: str
    name: str
    prompt_template: str
    rag_queries: List[str] = field(default_factory=list)
    needs_financial: bool = False
    needs_technical: bool = False
    needs_valuation: bool = False


FIVE_STEP_CONFIG: List[StepConfig] = [
    StepConfig(
        step_id="step1",
        name="信息差",
        prompt_template=STEP1_PROMPT,
        rag_queries=STEP1_RAG_QUERIES,
        needs_financial=True,
    ),
    StepConfig(
        step_id="step2",
        name="逻辑差",
        prompt_template=STEP2_PROMPT,
        rag_queries=STEP2_RAG_QUERIES,
    ),
    StepConfig(
        step_id="step3",
        name="预期差",
        prompt_template=STEP3_PROMPT,
        rag_queries=STEP3_RAG_QUERIES,
        needs_financial=True,
        needs_valuation=True,
    ),
    StepConfig(
        step_id="step4",
        name="催化剂",
        prompt_template=STEP4_PROMPT,
        rag_queries=STEP4_RAG_QUERIES,
    ),
    StepConfig(
        step_id="step5",
        name="综合结论",
        prompt_template=STEP5_PROMPT,
        rag_queries=[],
        needs_technical=True,
        needs_valuation=True,
    ),
]
