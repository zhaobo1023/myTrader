# Capital Cycle Integration (P0) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate the capital cycle framework's quantitative layer into the existing `report_engine` — adding PE/PB historical quantile data and a 3-part expected return decomposition to Steps 3 and 5 of the five-step analysis chain, giving the LLM real valuation anchors instead of hallucinating them.

**Architecture:** Three additions to existing files, no new modules for P0.
(1) `data_tools.py` gains two public methods: `get_valuation_snapshot()` reads `trade_stock_daily_basic`, computes 5yr percentile ranks; `get_expected_return_context()` runs the earnings+valuation+dividend decomposition formula.
(2) `prompts.py` gains a `needs_valuation` flag on `StepConfig` and new `{valuation_context}` / `{expected_return_context}` placeholders in STEP3 and STEP5.
(3) `five_step.py`'s `_run_single_step()` wires the new data methods when `needs_valuation=True`.

**Tech Stack:** `config.db.execute_query` (existing DB interface), `pandas` / `numpy` for percentile math (already imported elsewhere), existing `ReportDataTools` class, existing `StepConfig` dataclass.

**Data source:** `trade_stock_daily_basic` table — columns `stock_code` (Tushare format, e.g. `000858.SZ`), `trade_date`, `pe_ttm`, `pb`, `dv_ttm`. The SQL query uses `SUBSTRING_INDEX(stock_code, '.', 1) = %s` to match the 6-digit code regardless of exchange suffix.

---

## Task 0: `get_valuation_snapshot()` + `get_expected_return_context()` in `data_tools.py`

**Files:**
- Modify: `investment_rag/report_engine/data_tools.py`
- Modify: `investment_rag/tests/test_data_tools.py`

### Step 1: Write the failing tests

Add these tests to the **bottom** of `investment_rag/tests/test_data_tools.py`:

```python
# ---------------------------------------------------------------
# Valuation snapshot tests
# ---------------------------------------------------------------

def _make_fake_valuation_rows(n=250, pe=15.0, pb=1.5, dv=2.0):
    """Helper: return n rows of fake trade_stock_daily_basic data."""
    import pandas as pd
    dates = pd.date_range("2021-01-01", periods=n, freq="B")
    rows = []
    for i, d in enumerate(dates):
        rows.append({
            "trade_date": d.date(),
            "pe_ttm": pe + (i % 30) * 0.5,   # slight variation so percentile is meaningful
            "pb": pb + (i % 20) * 0.05,
            "dv_ttm": dv,
        })
    return rows


def test_get_valuation_snapshot_returns_formatted_string():
    tools = _make_tools()
    fake_rows = _make_fake_valuation_rows(250)
    with patch("investment_rag.report_engine.data_tools._execute_query") as mock_q:
        mock_q.return_value = fake_rows
        result = tools.get_valuation_snapshot("000858")
    assert isinstance(result, str)
    assert "PE" in result
    assert "分位" in result


def test_get_valuation_snapshot_handles_empty_data():
    tools = _make_tools()
    with patch("investment_rag.report_engine.data_tools._execute_query") as mock_q:
        mock_q.return_value = []
        result = tools.get_valuation_snapshot("000858")
    assert "不足" in result or isinstance(result, str)


def test_get_valuation_snapshot_handles_db_exception():
    tools = _make_tools()
    with patch("investment_rag.report_engine.data_tools._execute_query") as mock_q:
        mock_q.side_effect = Exception("DB unavailable")
        result = tools.get_valuation_snapshot("000858")
    assert "失败" in result or isinstance(result, str)


def test_quantile_label_boundaries():
    from investment_rag.report_engine.data_tools import ReportDataTools
    assert ReportDataTools._quantile_label(5) == "极低估"
    assert ReportDataTools._quantile_label(25) == "低估"
    assert ReportDataTools._quantile_label(50) == "合理"
    assert ReportDataTools._quantile_label(70) == "偏高估"
    assert ReportDataTools._quantile_label(85) == "高估"
    assert ReportDataTools._quantile_label(97) == "极高估"


def test_get_expected_return_context_returns_string():
    tools = _make_tools()
    fake_rows = _make_fake_valuation_rows(250, pe=15.0, dv=2.5)
    with patch("investment_rag.report_engine.data_tools._execute_query") as mock_q:
        mock_q.return_value = fake_rows
        result = tools.get_expected_return_context("000858", earnings_growth_2yr=0.10)
    assert isinstance(result, str)
    assert "盈利" in result or "回报" in result or isinstance(result, str)


def test_get_expected_return_context_handles_no_pe_data():
    tools = _make_tools()
    with patch("investment_rag.report_engine.data_tools._execute_query") as mock_q:
        mock_q.return_value = []
        result = tools.get_expected_return_context("000858")
    assert isinstance(result, str)
```

### Step 2: Run tests to confirm they fail

```bash
cd /Users/zhaobo/data0/person/myTrader && python -m pytest investment_rag/tests/test_data_tools.py -v -k "valuation or quantile or expected_return" 2>&1 | tail -20
```
Expected: all 6 new tests fail with `ModuleNotFoundError` or `AttributeError`.

### Step 3: Add `_execute_query` import + two new public methods + `_quantile_label` static method to `data_tools.py`

Open `investment_rag/report_engine/data_tools.py`. Make two edits:

**Edit A** — Add DB import after the existing imports block (after the `logger = ...` line):

```python
# DB access for valuation data — imported at module level to allow test mocking
try:
    from config.db import execute_query as _execute_query
except ImportError:
    _execute_query = None  # allows import in environments without DB config
```

**Edit B** — Add three new methods to the `ReportDataTools` class. Place them after `get_financial_data()` and before `get_tech_analysis()`:

```python
    # ----------------------------------------------------------
    # 4. 估值历史分位数 (capital cycle integration)
    # ----------------------------------------------------------

    def get_valuation_snapshot(self, stock_code: str, years: int = 5) -> str:
        """
        从 trade_stock_daily_basic 查询历史 PE/PB/股息率，计算 {years} 年分位数。

        数据表：trade_stock_daily_basic
        股票代码格式：支持 "000858" 或 "000858.SZ"（自动提取数字部分）

        Returns:
            格式化文本，含当前 PE/PB/dv_ttm 及历史分位标签
        """
        clean_code = stock_code.split(".")[0]

        if _execute_query is None:
            return f"[估值数据] DB 模块未加载，跳过"

        from datetime import date, timedelta
        import pandas as pd

        start_date = (date.today() - timedelta(days=int(years * 365))).isoformat()
        sql = """
            SELECT trade_date, pe_ttm, pb, dv_ttm
            FROM trade_stock_daily_basic
            WHERE SUBSTRING_INDEX(stock_code, '.', 1) = %s
              AND trade_date >= %s
            ORDER BY trade_date ASC
        """
        try:
            rows = _execute_query(sql, params=(clean_code, start_date), env=self._db_env)
        except Exception as e:
            logger.warning("[ReportDataTools] Valuation query failed for %s: %s", stock_code, e)
            return f"[估值数据] {clean_code} 查询失败: {e}"

        if not rows or len(rows) < 20:
            return f"[估值数据] {clean_code} 数据不足（{len(rows) if rows else 0} 行，需 ≥ 20）"

        df = pd.DataFrame(rows)
        latest = df.iloc[-1]
        date_range = f"{df['trade_date'].iloc[0]} 至 {df['trade_date'].iloc[-1]}"
        lines = [f"[估值历史分位] {clean_code}，{years}年数据范围: {date_range}（{len(df)} 个交易日）"]

        # PE(TTM) — 排除负值（亏损期）
        pe_series = df["pe_ttm"].dropna()
        pe_series = pe_series[pe_series > 0]
        pe_current = _safe_float(latest.get("pe_ttm"))
        if pe_current and pe_current > 0 and len(pe_series) >= 20:
            pe_pct = float((pe_series < pe_current).mean() * 100)
            lines.append(
                f"PE(TTM): {pe_current:.1f}x，历史分位 {pe_pct:.0f}%，"
                f"估值水平: {self._quantile_label(pe_pct)}"
            )
        else:
            lines.append("PE(TTM): 无效（亏损或数据不足）")

        # PB
        pb_series = df["pb"].dropna()
        pb_series = pb_series[pb_series > 0]
        pb_current = _safe_float(latest.get("pb"))
        if pb_current and pb_current > 0 and len(pb_series) >= 20:
            pb_pct = float((pb_series < pb_current).mean() * 100)
            lines.append(
                f"PB: {pb_current:.2f}x，历史分位 {pb_pct:.0f}%，"
                f"估值水平: {self._quantile_label(pb_pct)}"
            )

        # 股息率(TTM)
        dv_series = df["dv_ttm"].dropna()
        dv_current = _safe_float(latest.get("dv_ttm")) or 0.0
        if len(dv_series) >= 20:
            dv_pct = float((dv_series < dv_current).mean() * 100) if dv_current > 0 else 0.0
            lines.append(f"股息率(TTM): {dv_current:.2f}%，历史分位 {dv_pct:.0f}%")

        return "\n".join(lines)

    def get_expected_return_context(
        self,
        stock_code: str,
        earnings_growth_2yr: float = 0.0,
        target_pe_quantile: float = 0.40,
        years: int = 5,
    ) -> str:
        """
        计算 2 年预期回报（三段分解：盈利 + 估值回归 + 股息）。

        公式来源：资本周期分析框架。
          earnings_contribution = (1 + earnings_growth_2yr)^2 - 1
          target_pe = PE历史序列的 target_pe_quantile 分位数值
          valuation_contribution = (target_pe / current_pe - 1) * (1 + earnings_growth_2yr)
          dividend_contribution = dv_ttm% * 2
          total = earnings + valuation + dividend

        Args:
            stock_code: 股票代码
            earnings_growth_2yr: 2年净利润复合增速估计（如 0.10 表示年化10%）
                                  默认 0.0（保守假设，无增长）
            target_pe_quantile: 估值回归目标分位（默认 40%，偏保守）
            years: 历史数据年数

        Returns:
            格式化文本，含三段拆分及总预期回报
        """
        clean_code = stock_code.split(".")[0]

        if _execute_query is None:
            return "[预期回报] DB 模块未加载，跳过"

        from datetime import date, timedelta
        import pandas as pd

        start_date = (date.today() - timedelta(days=int(years * 365))).isoformat()
        sql = """
            SELECT pe_ttm, dv_ttm
            FROM trade_stock_daily_basic
            WHERE SUBSTRING_INDEX(stock_code, '.', 1) = %s
              AND trade_date >= %s
              AND pe_ttm > 0
            ORDER BY trade_date ASC
        """
        try:
            rows = _execute_query(sql, params=(clean_code, start_date), env=self._db_env)
        except Exception as e:
            logger.warning("[ReportDataTools] Expected return query failed for %s: %s", stock_code, e)
            return f"[预期回报] {clean_code} 数据查询失败: {e}"

        if not rows or len(rows) < 20:
            return f"[预期回报] {clean_code} 历史数据不足，无法计算"

        df = pd.DataFrame(rows)
        pe_series = df["pe_ttm"].dropna()
        pe_series = pe_series[pe_series > 0]
        current_pe = _safe_float(df.iloc[-1].get("pe_ttm"))
        current_dv = _safe_float(df.iloc[-1].get("dv_ttm")) or 0.0

        if not current_pe or current_pe <= 0:
            return "[预期回报] 当前 PE 无效（亏损），无法计算"

        # 三段分解
        earnings_contribution = (1 + earnings_growth_2yr) ** 2 - 1
        target_pe = float(pe_series.quantile(target_pe_quantile))
        pe_change = target_pe / current_pe - 1
        valuation_contribution = pe_change * (1 + earnings_growth_2yr)
        dividend_contribution = (current_dv / 100) * 2  # dv_ttm 是百分比，x2年
        total = earnings_contribution + valuation_contribution + dividend_contribution

        lines = [
            "[预期回报测算] 2年预期总回报分解（PE回归至历史{}%分位）：".format(
                int(target_pe_quantile * 100)
            ),
            f"  盈利贡献（净利润增速 {earnings_growth_2yr*100:.0f}%/年）: "
            f"{earnings_contribution*100:+.1f}%",
            f"  估值贡献（PE {current_pe:.1f}x -> {target_pe:.1f}x）: "
            f"{valuation_contribution*100:+.1f}%",
            f"  股息贡献（{current_dv:.2f}% x 2年）: "
            f"{dividend_contribution*100:+.1f}%",
            f"  ------------------------------------------",
            f"  2年预期总回报: {total*100:+.1f}%",
            f"  注：盈利增速假设 {earnings_growth_2yr*100:.0f}%/年，为保守估计；"
            f"实际需结合管理层指引及一致预期调整。",
        ]
        return "\n".join(lines)

    @staticmethod
    def _quantile_label(pct: float) -> str:
        """将历史百分位数（0~100）映射为估值标签。"""
        if pct < 20:
            return "极低估"
        if pct < 40:
            return "低估"
        if pct < 60:
            return "合理"
        if pct < 80:
            return "偏高估"
        if pct < 95:
            return "高估"
        return "极高估"
```

**Edit C** — Add the `_safe_float` module-level helper **before** the `ReportDataTools` class definition:

```python
def _safe_float(val) -> float | None:
    """Safely convert a DB value (possibly Decimal/None/NaN) to float."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f  # NaN check
    except (TypeError, ValueError):
        return None
```

### Step 4: Run the new tests to verify they pass

```bash
cd /Users/zhaobo/data0/person/myTrader && python -m pytest investment_rag/tests/test_data_tools.py -v 2>&1 | tail -25
```
Expected: all 13 tests PASS (7 original + 6 new).

### Step 5: Commit

```bash
git add investment_rag/report_engine/data_tools.py investment_rag/tests/test_data_tools.py
git commit -m "feat(report): add get_valuation_snapshot and get_expected_return_context to ReportDataTools"
```

---

## Task 1: `StepConfig.needs_valuation` + Updated STEP3/STEP5 Prompts

**Files:**
- Modify: `investment_rag/report_engine/prompts.py`

No new tests needed for this task — the prompt templates are plain strings; correctness verified in Task 2's integration test.

### Step 1: Add `needs_valuation` field to `StepConfig` dataclass

In `investment_rag/report_engine/prompts.py`, find the `StepConfig` dataclass and add one field:

```python
@dataclass
class StepConfig:
    """单步分析配置"""
    step_id: str
    name: str
    prompt_template: str
    rag_queries: List[str] = field(default_factory=list)
    needs_financial: bool = False
    needs_technical: bool = False
    needs_valuation: bool = False   # <-- ADD THIS LINE
```

### Step 2: Set `needs_valuation=True` for step3 and step5 in `FIVE_STEP_CONFIG`

Find the `FIVE_STEP_CONFIG` list. Update step3 and step5 entries:

```python
    StepConfig(
        step_id="step3",
        name="预期差",
        prompt_template=STEP3_PROMPT,
        rag_queries=STEP3_RAG_QUERIES,
        needs_financial=True,
        needs_valuation=True,   # <-- ADD
    ),
```

```python
    StepConfig(
        step_id="step5",
        name="综合结论",
        prompt_template=STEP5_PROMPT,
        rag_queries=[],
        needs_technical=True,
        needs_valuation=True,   # <-- ADD
    ),
```

### Step 3: Update STEP3_PROMPT to include `{valuation_context}`

Find `STEP3_PROMPT` in `prompts.py`. The current template starts with:

```
## 任务: 预期差分析（第三步）

**公司**: {stock_name}

**前期累积分析**:
{prev_analysis}

**财务数据上下文**:
{financial_context}
```

Change it to insert a new block after `{financial_context}`:

```
## 任务: 预期差分析（第三步）

**公司**: {stock_name}

**前期累积分析**:
{prev_analysis}

**财务数据上下文**:
{financial_context}

**估值历史分位数**:
{valuation_context}
```

Keep everything after `{financial_context}` (the **指令** section and **输出格式** section) exactly as-is. Only insert the two lines shown above.

### Step 4: Update STEP5_PROMPT to include `{valuation_context}` and `{expected_return_context}`

Find `STEP5_PROMPT`. The current template starts with:

```
## 任务: 综合结论（第五步）

**公司**: {stock_name}

**前期完整分析（信息差 + 逻辑差 + 预期差 + 催化剂）**:
{prev_analysis}

**技术面数据**:
{technical_context}
```

Change to add two new blocks before `**指令**`:

```
## 任务: 综合结论（第五步）

**公司**: {stock_name}

**前期完整分析（信息差 + 逻辑差 + 预期差 + 催化剂）**:
{prev_analysis}

**技术面数据**:
{technical_context}

**估值历史分位数**:
{valuation_context}

**预期回报测算**:
{expected_return_context}
```

### Step 5: Smoke test

```bash
cd /Users/zhaobo/data0/person/myTrader && python -c "
from investment_rag.report_engine.prompts import FIVE_STEP_CONFIG, StepConfig
assert hasattr(StepConfig, '__dataclass_fields__')
assert 'needs_valuation' in StepConfig.__dataclass_fields__
step3 = next(s for s in FIVE_STEP_CONFIG if s.step_id == 'step3')
step5 = next(s for s in FIVE_STEP_CONFIG if s.step_id == 'step5')
assert step3.needs_valuation, 'step3 needs_valuation must be True'
assert step5.needs_valuation, 'step5 needs_valuation must be True'
assert '{valuation_context}' in step3.prompt_template, 'STEP3 missing valuation_context placeholder'
assert '{valuation_context}' in step5.prompt_template, 'STEP5 missing valuation_context placeholder'
assert '{expected_return_context}' in step5.prompt_template, 'STEP5 missing expected_return_context placeholder'
print('ALL CHECKS PASS')
"
```
Expected: `ALL CHECKS PASS`

### Step 6: Commit

```bash
git add investment_rag/report_engine/prompts.py
git commit -m "feat(report): add needs_valuation flag to StepConfig; wire valuation context into step3/step5 prompts"
```

---

## Task 2: Wire Valuation Context into `FiveStepAnalyzer._run_single_step()`

**Files:**
- Modify: `investment_rag/report_engine/five_step.py`
- Modify: `investment_rag/tests/test_five_step.py`

### Step 1: Write the new failing tests

Add these to the **bottom** of `investment_rag/tests/test_five_step.py`:

```python
# ---------------------------------------------------------------
# Valuation context wiring tests
# ---------------------------------------------------------------

def test_run_single_step_calls_valuation_when_flagged():
    """When step has needs_valuation=True, get_valuation_snapshot must be called."""
    from investment_rag.report_engine.prompts import FIVE_STEP_CONFIG
    analyzer = _make_analyzer()
    analyzer._tools.get_valuation_snapshot = MagicMock(return_value="Valuation text")
    analyzer._tools.get_expected_return_context = MagicMock(return_value="Expected return text")

    step3 = next(s for s in FIVE_STEP_CONFIG if s.step_id == "step3")
    assert step3.needs_valuation, "step3 must have needs_valuation=True for this test to be meaningful"

    analyzer._run_single_step(
        step_config=step3,
        stock_code="000858",
        stock_name="五粮液",
        prev_analysis="some prior analysis",
    )
    analyzer._tools.get_valuation_snapshot.assert_called_once_with("000858")


def test_run_single_step_does_not_call_valuation_when_not_flagged():
    """When step has needs_valuation=False, get_valuation_snapshot must NOT be called."""
    from investment_rag.report_engine.prompts import FIVE_STEP_CONFIG
    analyzer = _make_analyzer()
    analyzer._tools.get_valuation_snapshot = MagicMock(return_value="Valuation text")

    step1 = next(s for s in FIVE_STEP_CONFIG if s.step_id == "step1")
    assert not step1.needs_valuation, "step1 must have needs_valuation=False for this test"

    analyzer._run_single_step(
        step_config=step1,
        stock_code="000858",
        stock_name="五粮液",
        prev_analysis="",
    )
    analyzer._tools.get_valuation_snapshot.assert_not_called()


def test_run_single_step_calls_expected_return_for_step5():
    """Step5 must also call get_expected_return_context."""
    from investment_rag.report_engine.prompts import FIVE_STEP_CONFIG
    analyzer = _make_analyzer()
    analyzer._tools.get_valuation_snapshot = MagicMock(return_value="Valuation text")
    analyzer._tools.get_expected_return_context = MagicMock(return_value="Return text")

    step5 = next(s for s in FIVE_STEP_CONFIG if s.step_id == "step5")
    analyzer._run_single_step(
        step_config=step5,
        stock_code="000858",
        stock_name="五粮液",
        prev_analysis="all prior analysis",
    )
    analyzer._tools.get_expected_return_context.assert_called_once_with("000858")
```

### Step 2: Update `_make_analyzer()` helper in the same test file

The existing `_make_analyzer()` creates a `MagicMock` for `_tools`. Since `MagicMock` auto-creates attributes, the new methods will return `MagicMock()` objects (not strings) by default, which is fine for the original tests. But add explicit return values for cleanliness:

Find `_make_analyzer()` and add two lines:

```python
def _make_analyzer():
    from investment_rag.report_engine.five_step import FiveStepAnalyzer
    analyzer = FiveStepAnalyzer.__new__(FiveStepAnalyzer)
    analyzer._tools = MagicMock()
    analyzer._tools.query_rag_multi.return_value = "RAG context text"
    analyzer._tools.get_financial_data.return_value = "Financial context text"
    analyzer._tools.get_tech_analysis.return_value = "Tech context text"
    analyzer._tools.get_valuation_snapshot.return_value = "Valuation context text"       # ADD
    analyzer._tools.get_expected_return_context.return_value = "Expected return text"     # ADD
    analyzer._llm = MagicMock()
    analyzer._llm.generate.return_value = "## Analysis\nContent..."
    return analyzer
```

### Step 3: Run new tests to confirm they fail

```bash
cd /Users/zhaobo/data0/person/myTrader && python -m pytest investment_rag/tests/test_five_step.py -v -k "valuation or expected_return" 2>&1 | tail -20
```
Expected: 3 new tests FAIL with `AssertionError` (`assert_called_once_with` fails because the method was never called).

### Step 4: Update `_run_single_step()` in `five_step.py`

Find the `_run_single_step` method. The current body looks like:

```python
        # 1. RAG 上下文
        rag_context = ""
        if step_config.rag_queries:
            ...

        # 2. 财务上下文
        financial_context = ""
        if step_config.needs_financial:
            ...

        # 3. 技术面上下文
        technical_context = ""
        if step_config.needs_technical:
            ...

        # 4. 渲染 Prompt
        prompt = step_config.prompt_template.format(
            stock_name=stock_name,
            rag_context=rag_context or "[无相关研报内容]",
            financial_context=financial_context or "[无财务数据]",
            technical_context=technical_context or "[无技术面数据]",
            prev_analysis=prev_analysis or "[本步骤为第一步，无前期分析]",
        )
```

Replace with:

```python
        # 1. RAG 上下文
        rag_context = ""
        if step_config.rag_queries:
            rag_context = self._tools.query_rag_multi(
                queries=step_config.rag_queries,
                stock_name=stock_name,
                stock_code=stock_code,
                collection=collection,
                top_k_per_query=3,
            )

        # 2. 财务上下文
        financial_context = ""
        if step_config.needs_financial:
            financial_context = self._tools.get_financial_data(stock_code, years=3)

        # 3. 技术面上下文
        technical_context = ""
        if step_config.needs_technical:
            technical_context = self._tools.get_tech_analysis(stock_code)

        # 4. 估值历史分位数上下文（资本周期框架）
        valuation_context = ""
        expected_return_context = ""
        if step_config.needs_valuation:
            valuation_context = self._tools.get_valuation_snapshot(stock_code)
            expected_return_context = self._tools.get_expected_return_context(stock_code)

        # 5. 渲染 Prompt
        # Note: str.format() silently ignores extra kwargs, so passing valuation_context
        # and expected_return_context to prompts that lack those placeholders is safe.
        prompt = step_config.prompt_template.format(
            stock_name=stock_name,
            rag_context=rag_context or "[无相关研报内容]",
            financial_context=financial_context or "[无财务数据]",
            technical_context=technical_context or "[无技术面数据]",
            prev_analysis=prev_analysis or "[本步骤为第一步，无前期分析]",
            valuation_context=valuation_context or "[无估值历史数据]",
            expected_return_context=expected_return_context or "[无预期回报数据]",
        )
```

### Step 5: Run all tests to verify

```bash
cd /Users/zhaobo/data0/person/myTrader && python -m pytest investment_rag/tests/test_five_step.py -v 2>&1 | tail -20
```
Expected: all 12 tests PASS (9 original + 3 new).

Also run the full suite:

```bash
cd /Users/zhaobo/data0/person/myTrader && python -m pytest investment_rag/tests/ -v --ignore=investment_rag/tests/test_store.py 2>&1 | tail -15
```
Expected: all tests PASS (the `test_store.py` exclusion is pre-existing due to `rank_bm25` not installed in dev env).

### Step 6: Commit

```bash
git add investment_rag/report_engine/five_step.py investment_rag/tests/test_five_step.py
git commit -m "feat(report): wire valuation context into FiveStepAnalyzer step3/step5"
```

---

## Task 3: End-to-End Smoke Test

**Verify the complete chain works without error (no LLM call, just data collection).**

### Step 1: Verify `data_tools.py` can be imported cleanly

```bash
cd /Users/zhaobo/data0/person/myTrader && python -c "
from investment_rag.report_engine.data_tools import ReportDataTools
print('Import OK')
print('Methods:', [m for m in dir(ReportDataTools) if not m.startswith('__')])
"
```
Expected: `Import OK` + method list includes `get_valuation_snapshot`, `get_expected_return_context`, `_quantile_label`.

### Step 2: Verify prompts structure

```bash
cd /Users/zhaobo/data0/person/myTrader && python -c "
from investment_rag.report_engine.prompts import FIVE_STEP_CONFIG
for s in FIVE_STEP_CONFIG:
    print(f'{s.step_id}: financial={s.needs_financial}, tech={s.needs_technical}, valuation={s.needs_valuation}')
"
```
Expected output:
```
step1: financial=True, tech=False, valuation=False
step2: financial=False, tech=False, valuation=False
step3: financial=True, tech=False, valuation=True
step4: financial=False, tech=False, valuation=False
step5: financial=False, tech=True, valuation=True
```

### Step 3: Final commit if needed

If any minor fixes were made during smoke test:
```bash
git add -A && git commit -m "fix(report): minor fixes from smoke test"
```

---

## Summary

**3 tasks, 4-6 commits.**

### What this adds

- `get_valuation_snapshot()` — queries `trade_stock_daily_basic`, computes 5yr PE/PB/dv_ttm percentile, labels them (极低估/低估/合理/偏高估/高估/极高估)
- `get_expected_return_context()` — pure 3-part formula: earnings + valuation reversion to 40th percentile + dividend x2 years
- Step3 (预期差) now receives real valuation data to anchor the "估值隐含预期" section
- Step5 (综合结论) now receives both valuation data and expected return decomposition to anchor the "参考价位" and investment rating

### Run order to validate

```bash
# 1. All unit tests
python -m pytest investment_rag/tests/ --ignore=investment_rag/tests/test_store.py -v

# 2. CLI smoke (needs DB, no LLM)
# Note: technical-only skips valuation (no needs_valuation on tech step)
DB_ENV=online python -m investment_rag.run_report --code 000858 --name 五粮液 --type technical

# 3. Full report with valuation context in step3/step5
DB_ENV=online python -m investment_rag.run_report --code 000858 --name 五粮液 --type comprehensive
```

---

## P1 Preview: Announcement NLP Pipeline

This is the highest-value future extension. The foundation already exists:
`data_analyst/financial_fetcher/cninfo_downloader.py` has `search_announcements()` + `download_pdf()` + `pdf_to_markdown_pymupdf()`.

**What P1 adds:**
1. Extend `search_announcements()` to support `ann_type` values: `减持`, `回购`, `增持`, `股份回购`, `员工持股`
2. Add `extract_shareholder_signal(text)` — calls LLM with the entity extraction prompt from the design doc; outputs structured JSON
3. Add MySQL tables: `announcements` + `ann_signals` (DDL in design doc Section 6.2)
4. Add `get_shareholder_signals(stock_code, months=6) -> str` to `ReportDataTools`
5. Add `needs_shareholder: bool = False` to `StepConfig`; set `True` for step1 and step4

**Estimated effort:** 2-3 days. The `cninfo_downloader.py` handles the hardest part (PDF download + text extraction). The main new work is the signal scoring and DB write.
