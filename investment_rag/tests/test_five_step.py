# -*- coding: utf-8 -*-
import pytest
from unittest.mock import MagicMock, patch


def _make_analyzer():
    from investment_rag.report_engine.five_step import FiveStepAnalyzer
    analyzer = FiveStepAnalyzer.__new__(FiveStepAnalyzer)
    analyzer._tools = MagicMock()
    analyzer._tools.query_rag_multi.return_value = "RAG context text"
    analyzer._tools.get_financial_data.return_value = "Financial context text"
    analyzer._tools.get_tech_analysis.return_value = "Tech context text"
    analyzer._tools.get_valuation_snapshot.return_value = "Valuation context text"
    analyzer._tools.get_expected_return_context.return_value = "Expected return text"
    analyzer._llm = MagicMock()
    analyzer._llm.generate.return_value = "## Analysis\nContent..."
    return analyzer


def test_five_step_config_has_5_steps():
    from investment_rag.report_engine.prompts import FIVE_STEP_CONFIG
    assert len(FIVE_STEP_CONFIG) == 5
    ids = [s.step_id for s in FIVE_STEP_CONFIG]
    assert ids == ["step1", "step2", "step3", "step4", "step5"]


def test_run_single_step_returns_string():
    from investment_rag.report_engine.prompts import FIVE_STEP_CONFIG
    analyzer = _make_analyzer()
    result = analyzer._run_single_step(
        step_config=FIVE_STEP_CONFIG[0],
        stock_code="000858",
        stock_name="五粮液",
        prev_analysis="",
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_fundamental_calls_all_5_steps():
    analyzer = _make_analyzer()
    called_steps = []

    def mock_step(step_config, **kwargs):
        called_steps.append(step_config.step_id)
        return f"Result of {step_config.step_id}"

    analyzer._run_single_step = mock_step
    results = analyzer.generate_fundamental("000858", "五粮液")
    assert len(called_steps) == 5
    assert set(called_steps) == {"step1", "step2", "step3", "step4", "step5"}
    assert "full_report" in results
    assert isinstance(results["full_report"], str)


def test_generate_fundamental_accumulates_context():
    """Each step's result must appear in the prev_analysis of subsequent steps."""
    analyzer = _make_analyzer()
    prev_analyses = {}

    def mock_step(step_config, prev_analysis, **kwargs):
        prev_analyses[step_config.step_id] = prev_analysis
        return f"Result of {step_config.step_id}"

    analyzer._run_single_step = mock_step
    analyzer.generate_fundamental("000858", "五粮液")
    assert prev_analyses["step1"] == ""
    assert "Result of step1" in prev_analyses["step2"]
    assert "Result of step2" in prev_analyses["step3"]


def test_generate_tech_section_returns_string():
    analyzer = _make_analyzer()
    result = analyzer.generate_tech_section("000858", "五粮液")
    assert isinstance(result, str)
    analyzer._tools.get_tech_analysis.assert_called_once_with("000858")
    analyzer._llm.generate.assert_called_once()


def test_report_builder_comprehensive():
    from investment_rag.report_engine.report_builder import ReportBuilder
    builder = ReportBuilder()
    results = {f"step{i}": f"## Step {i}\n内容{i}" for i in range(1, 6)}
    report = builder.build_comprehensive(
        stock_code="000858",
        stock_name="五粮液",
        fundamental_results=results,
        tech_section="## 技术面\n技术内容",
    )
    assert "五粮液" in report
    assert "000858" in report
    assert "## 一、信息差分析" in report
    assert "## 六、技术面分析" in report
    assert "技术内容" in report


def test_report_builder_fundamental_only():
    from investment_rag.report_engine.report_builder import ReportBuilder
    builder = ReportBuilder()
    results = {f"step{i}": f"内容{i}" for i in range(1, 6)}
    report = builder.build_fundamental_only(
        stock_code="000858",
        stock_name="五粮液",
        fundamental_results=results,
    )
    assert "五粮液" in report
    assert "000858" in report
    assert "技术面" not in report


def test_report_store_save_and_retrieve(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "investment_rag.report_engine.report_store.REPORT_DIR", str(tmp_path)
    )
    monkeypatch.setattr(
        "investment_rag.report_engine.report_store.INDEX_FILE",
        str(tmp_path / "index.json"),
    )
    from investment_rag.report_engine.report_store import ReportStore
    store = ReportStore()
    rid = store.save("000858", "五粮液", "comprehensive", "# Test\nContent here")
    assert store.get(rid) == "# Test\nContent here"
    assert store.get("nonexistent") is None
    reports = store.list_reports(stock_code="000858")
    assert len(reports) == 1
    assert reports[0]["id"] == rid


def test_report_store_list_filters_by_stock(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "investment_rag.report_engine.report_store.REPORT_DIR", str(tmp_path)
    )
    monkeypatch.setattr(
        "investment_rag.report_engine.report_store.INDEX_FILE",
        str(tmp_path / "index.json"),
    )
    from investment_rag.report_engine.report_store import ReportStore
    store = ReportStore()
    store.save("000858", "五粮液", "comprehensive", "report A")
    store.save("300750", "宁德时代", "fundamental", "report B")
    all_reports = store.list_reports()
    assert len(all_reports) == 2
    filtered = store.list_reports(stock_code="000858")
    assert len(filtered) == 1
    assert filtered[0]["stock_code"] == "000858"


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
