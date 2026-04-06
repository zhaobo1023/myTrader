"""
五截面批量分析运行器

对持仓的所有 A 股逐一执行五截面分析，输出 HTML 报告到 output/research/
同时生成汇总 index.html

用法：
    PYTHONPATH=. DB_ENV=online python data_analyst/research_pipeline/batch_runner.py
    PYTHONPATH=. DB_ENV=online python data_analyst/research_pipeline/batch_runner.py --stock 600989
    PYTHONPATH=. DB_ENV=online python data_analyst/research_pipeline/batch_runner.py --date 20260406
"""
import sys
import os
import logging
import argparse
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/batch_research.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("batch_runner")

# ETF code prefixes to skip (no financial reports)
ETF_PREFIXES = ("159", "510", "511", "512", "513", "515", "516", "517", "518", "588")

PORTFOLIO_PATH = "/Users/zhaobo/Documents/notes/Finance/Positions/00-Current-Portfolio-Audit.md"


# ---------------------------------------------------------------------------
# Pre-flight: check DB connectivity
# ---------------------------------------------------------------------------

def check_db_connection(env: str = "online", timeout: int = 4) -> bool:
    """
    Quick socket-level check to see if the DB host is reachable.
    Returns True if reachable, False otherwise.
    """
    import socket
    from config.db import ONLINE_DB_CONFIG, LOCAL_DB_CONFIG

    cfg = ONLINE_DB_CONFIG if env == "online" else LOCAL_DB_CONFIG
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 3306)

    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Helper: normalize code to XXXXXX.SH/SZ format
# ---------------------------------------------------------------------------

def _fmt_code(raw: str) -> str:
    raw = raw.strip()
    if "." in raw:
        return raw.upper()
    if raw.startswith(("6", "9")):
        return f"{raw}.SH"
    return f"{raw}.SZ"


def _bare_code(code_with_suffix: str) -> str:
    return code_with_suffix.split(".")[0]


def _is_etf(code_bare: str) -> bool:
    return any(code_bare.startswith(p) for p in ETF_PREFIXES)


# ---------------------------------------------------------------------------
# Get portfolio stocks
# ---------------------------------------------------------------------------

def get_portfolio_stocks(portfolio_path: str) -> dict:
    """Returns {bare_code: name} for non-ETF A-shares."""
    from strategist.tech_scan.portfolio_parser import PortfolioParser

    parser = PortfolioParser(portfolio_path)
    positions = parser.parse()

    watch_list = {}
    skipped_etf = []

    for pos in positions:
        code_bare = pos.code.split(".")[0]
        if _is_etf(code_bare):
            skipped_etf.append(f"{code_bare}({pos.name})")
            continue
        watch_list[code_bare] = pos.name

    if skipped_etf:
        logger.info(f"Skip ETFs: {', '.join(skipped_etf)}")

    return watch_list


# ---------------------------------------------------------------------------
# Fetch technical data
# ---------------------------------------------------------------------------

def _safe_float(val, default=0.0) -> float:
    """Safely convert a possibly NaN/None value to float."""
    import math as _math
    try:
        v = float(val)
        if _math.isnan(v) or _math.isinf(v):
            return default
        return v
    except Exception:
        return default


def fetch_tech_data(code_bare: str) -> dict:
    """
    Returns dict with keys:
        price, ma5, ma20, ma60, ma250, rsi, macd_hist, kdj_j,
        boll_pct_b, boll_lower, vol_ratio, rps_120,
        score_raw (0-10), score_100 (0-100), data_date
    """
    import pandas as pd
    from strategist.tech_scan.data_fetcher import DataFetcher
    from strategist.tech_scan.indicator_calculator import IndicatorCalculator
    from strategist.tech_scan.report_engine import ReportEngine

    code = _fmt_code(code_bare)
    fetcher = DataFetcher(env="online")
    calc = IndicatorCalculator()
    engine = ReportEngine()

    try:
        df = fetcher.fetch_daily_data([code], lookback_days=350)
        if df is None or df.empty:
            logger.warning(f"[{code}] No daily data found")
            return {}

        df = calc.calculate_all(df)

        # Merge RPS
        try:
            rps_df = fetcher.fetch_rps_data([code])
            if rps_df is not None and not rps_df.empty:
                rps_cols = ["stock_code", "trade_date"]
                for col in ["rps_120", "rps_250", "rps_slope"]:
                    if col in rps_df.columns:
                        rps_cols.append(col)
                df = df.merge(rps_df[rps_cols], on=["stock_code", "trade_date"], how="left")
        except Exception:
            pass

        latest = df.iloc[-1]
        score_result = engine.calc_score(latest)

        # Get latest non-NaN RPS120
        rps_120 = 50.0
        if "rps_120" in df.columns:
            valid = df["rps_120"].dropna()
            if not valid.empty:
                rps_120 = _safe_float(valid.iloc[-1], 50.0)

        # BOLL %B: (close - lower) / (upper - lower)
        boll_pct_b = 0.5
        boll_lower = 0.0
        try:
            upper = _safe_float(latest.get("boll_upper"), 0)
            lower = _safe_float(latest.get("boll_lower"), 0)
            close = _safe_float(latest.get("close"), 0)
            if upper > lower > 0:
                boll_pct_b = (close - lower) / (upper - lower)
                boll_lower = lower
        except Exception:
            pass

        # KDJ J value
        kdj_j = _safe_float(latest.get("kdj_j"), 50.0)

        score_raw = _safe_float(score_result.score, 5.0)
        score_100 = max(0, min(100, int(round(score_raw * 10))))

        data_date = ""
        try:
            data_date = latest["trade_date"].strftime("%Y-%m-%d")
        except Exception:
            pass

        return {
            "price":       _safe_float(latest.get("close")),
            "ma5":         _safe_float(latest.get("ma5")),
            "ma20":        _safe_float(latest.get("ma20")),
            "ma60":        _safe_float(latest.get("ma60")),
            "ma250":       _safe_float(latest.get("ma250")),
            "rsi":         _safe_float(latest.get("rsi"), 50.0),
            "macd_hist":   _safe_float(latest.get("macd_hist")),
            "kdj_j":       kdj_j,
            "boll_pct_b":  _safe_float(boll_pct_b, 0.5),
            "boll_lower":  _safe_float(boll_lower),
            "vol_ratio":   _safe_float(latest.get("volume_ratio"), 1.0),
            "rps_120":     rps_120,
            "score_raw":   score_raw,
            "score_100":   score_100,
            "data_date":   data_date,
        }

    except Exception as e:
        logger.error(f"[{code}] fetch_tech_data failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# Build ReportData and run all scorers
# ---------------------------------------------------------------------------

def build_report_data(code_bare: str, name: str, date_str: str) -> Optional["ReportData"]:
    """
    Fetch all data and score all 5 sections, returning a ReportData.
    Returns None on critical failure.
    """
    from data_analyst.research_pipeline.fetcher import ResearchDataFetcher
    from data_analyst.research_pipeline.renderer import ReportData

    from research.fundamental.scorer import FundamentalScorer, ScorerInput as FundInput
    from research.sentiment.scorer import SentimentScorer, SentimentInput
    from research.capital_cycle.scorer import CapitalCycleScorer, CapitalCycleInput
    from research.fund_flow.scorer import FundFlowScorer, FundFlowInput
    from research.composite.aggregator import CompositeAggregator, FiveSectionScores

    logger.info(f"  [1/5] Fetching tech data ...")
    tech = fetch_tech_data(code_bare)

    logger.info(f"  [2/5] Fetching financial/valuation/fund-flow ...")
    research_fetcher = ResearchDataFetcher(env="online")

    code_with_suffix = _fmt_code(code_bare)

    financial = research_fetcher.fetch_financial(code_with_suffix)
    valuation = research_fetcher.fetch_valuation(code_with_suffix)
    rps_120 = tech.get("rps_120", 50.0)
    fund_flow_data = research_fetcher.fetch_fund_flow(code_with_suffix, rps_120=rps_120)

    # ---- Fundamental scoring ----
    logger.info(f"  [3/5] Scoring fundamental ...")
    fund_scorer = FundamentalScorer()
    ocf_to_profit = 0.0
    if financial.net_profit_latest and financial.net_profit_latest != 0:
        ocf_to_profit = financial.ocf_latest / financial.net_profit_latest
    else:
        ocf_to_profit = 0.0

    fund_input = FundInput(
        pe_quantile=valuation.pe_quantile,
        pb_quantile=valuation.pb_quantile,
        roe=financial.roe_latest / 100.0 if financial.roe_latest else None,
        roe_prev=financial.roe_prev / 100.0 if financial.roe_prev else None,
        ocf_to_profit=ocf_to_profit,
        debt_ratio=financial.debt_ratio_latest / 100.0 if financial.debt_ratio_latest else None,
        revenue_yoy=financial.revenue_yoy,
        profit_yoy=financial.profit_yoy,
    )
    fund_result = fund_scorer.score(fund_input)
    score_fundamental = fund_result.composite_score

    # ---- Capital cycle scoring ----
    logger.info(f"  [4/5] Scoring capital cycle ...")
    cc_scorer = CapitalCycleScorer()
    cc_input = CapitalCycleInput(
        roe_series=financial.roe_series,
        revenue_growth_series=financial.revenue_growth_series,
        gross_margin_series=financial.gross_margin_series,
        stock_code=code_bare,
        stock_name=name,
    )
    cc_result = cc_scorer.score(cc_input)
    score_capital_cycle = cc_result.score

    # ---- Fund flow scoring ----
    ff_scorer = FundFlowScorer()
    ff_input = FundFlowInput(
        net_5d_amount=fund_flow_data.net_5d_amount,
        net_10d_amount=fund_flow_data.net_10d_amount,
        net_20d_amount=fund_flow_data.net_20d_amount,
        total_mv=fund_flow_data.total_mv_yuan,
        rps_120=rps_120,
    )
    ff_result = ff_scorer.score(ff_input)
    score_fund_flow = ff_result.score

    # ---- Sentiment scoring ----
    logger.info(f"  [5/5] Scoring sentiment ...")
    sent_scorer = SentimentScorer()
    sent_input = SentimentInput(
        rsi=tech.get("rsi"),
        macd_hist=tech.get("macd_hist"),
        vol_ratio=tech.get("vol_ratio"),
        rps_120=rps_120,
        score_fund=score_fund_flow,    # use fund flow as proxy for capital flow sentiment
    )
    sent_result = sent_scorer.score(sent_input, code=code_with_suffix)
    score_sentiment = sent_result.composite_score

    # ---- Tech score ----
    score_technical = tech.get("score_100", 50)

    # ---- Composite aggregation ----
    five_scores = FiveSectionScores(
        score_technical=score_technical,
        score_fund_flow=score_fund_flow,
        score_fundamental=score_fundamental,
        score_sentiment=score_sentiment,
        score_capital_cycle=score_capital_cycle,
        pe_quantile=valuation.pe_quantile,
        capital_cycle_phase=cc_result.phase,
        founder_reducing=False,
        technical_breakdown=tech.get("price", 0) < tech.get("ma20", 0),
    )
    aggregator = CompositeAggregator()
    agg_result = aggregator.aggregate(five_scores)

    composite_score = float(agg_result.composite_score)
    direction = agg_result.direction

    # ---- Build ReportData ----
    report_data = ReportData(
        stock_code=code_bare,
        stock_name=name,
        report_date=date_str,
        # Scores
        score_technical=score_technical,
        score_fund_flow=score_fund_flow,
        score_fundamental=score_fundamental,
        score_sentiment=score_sentiment,
        score_capital_cycle=score_capital_cycle,
        composite_score=composite_score,
        direction=direction,
        # Technical
        tech_price=tech.get("price", 0),
        tech_ma5=tech.get("ma5", 0),
        tech_ma20=tech.get("ma20", 0),
        tech_ma60=tech.get("ma60", 0),
        tech_ma250=tech.get("ma250", 0),
        tech_rsi=tech.get("rsi", 50),
        tech_macd_hist=tech.get("macd_hist", 0),
        tech_kdj_j=tech.get("kdj_j", 50),
        tech_boll_pct_b=tech.get("boll_pct_b", 0.5),
        tech_boll_lower=tech.get("boll_lower", 0),
        tech_vol_ratio=tech.get("vol_ratio", 1.0),
        tech_rps120=rps_120,
        tech_score_raw=tech.get("score_raw", 5.0),
        # Fund flow
        ff_net_5d_yi=ff_result.net_5d_yi,
        ff_net_10d_yi=fund_flow_data.net_10d_amount / 1e8,
        ff_net_20d_yi=ff_result.net_20d_yi,
        ff_net_5d_pct=ff_result.net_5d_pct,
        ff_net_20d_pct=ff_result.net_20d_pct,
        ff_label=ff_result.label,
        # Fundamental
        fund_revenue_yi=financial.revenue_latest,
        fund_revenue_yoy=financial.revenue_yoy,
        fund_profit_yi=financial.net_profit_latest,
        fund_profit_yoy=financial.profit_yoy,
        fund_roe=financial.roe_latest,
        fund_roe_prev=financial.roe_prev,
        fund_gross_margin=financial.gross_margin_latest,
        fund_ocf_to_profit=ocf_to_profit,
        fund_debt_ratio=financial.debt_ratio_latest,
        fund_report_date=financial.report_date,
        fund_pe_ttm=valuation.pe_ttm,
        fund_pb=valuation.pb,
        fund_pe_quantile=valuation.pe_quantile,
        fund_pb_quantile=valuation.pb_quantile,
        fund_total_mv=valuation.total_mv,
        fund_eq_score=fund_result.earnings_quality_score,
        fund_va_score=fund_result.valuation_score,
        fund_gc_score=fund_result.growth_score,
        # Sentiment
        sent_score_fund=sent_result.score_fund,
        sent_score_pricevol=sent_result.score_price_vol,
        sent_score_consensus=sent_result.score_consensus,
        sent_score_sector=sent_result.score_sector,
        sent_score_macro=sent_result.score_macro,
        sent_label=sent_result.label,
        # Capital cycle
        cc_phase=cc_result.phase,
        cc_phase_label=cc_result.phase_label,
        cc_roe_trend=cc_result.roe_trend,
        cc_detail=cc_result.detail,
        cc_label=cc_result.label,
        cc_roe_series=financial.roe_series,
        cc_rev_growth_series=financial.revenue_growth_series,
    )

    return report_data


# ---------------------------------------------------------------------------
# Index HTML generator
# ---------------------------------------------------------------------------

def _direction_badge(direction: str) -> str:
    colors = {
        "strong_bull": "#27ae60",
        "bull": "#2ecc71",
        "neutral": "#f39c12",
        "bear": "#e67e22",
        "strong_bear": "#e74c3c",
    }
    labels = {
        "strong_bull": "强多",
        "bull": "偏多",
        "neutral": "中性",
        "bear": "偏空",
        "strong_bear": "强空",
    }
    color = colors.get(direction, "#888")
    label = labels.get(direction, "中性")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:10px;font-size:12px;">{label}</span>'


def build_index_html(summary_rows: list, date_str: str) -> str:
    """
    summary_rows: list of dicts with keys:
        code, name, composite_score, direction, score_tech, score_ff,
        score_fund, score_sent, score_cc, filename
    """
    rows_html = ""
    for r in sorted(summary_rows, key=lambda x: x["composite_score"], reverse=True):
        comp = r["composite_score"]
        comp_color = "#27ae60" if comp >= 65 else ("#f39c12" if comp >= 45 else "#e74c3c")
        rows_html += f"""<tr>
<td><a href="{r['filename']}" target="_blank"><strong>{r['code']}</strong></a></td>
<td>{r['name']}</td>
<td style="color:{comp_color};font-weight:bold;font-size:16px;">{comp:.1f}</td>
<td>{_direction_badge(r['direction'])}</td>
<td>{r['score_tech']}</td>
<td>{r['score_ff']}</td>
<td>{r['score_fund']}</td>
<td>{r['score_sent']}</td>
<td>{r['score_cc']}</td>
</tr>"""

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>五截面分析 - 持仓汇总 {date_str}</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 1100px; margin: 0 auto; padding: 20px; background: #f5f5f5; color: #333; }}
h1 {{ border-bottom: 3px solid #3498db; padding-bottom: 10px; font-size: 1.4em; }}
.table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 10px 0; }}
table {{ border-collapse: collapse; width: 100%; background: white; }}
th, td {{ border: 1px solid #ddd; padding: 10px 14px; text-align: center; white-space: nowrap; }}
th {{ background: #3498db; color: white; }}
tr:nth-child(even) {{ background: #f9f9f9; }}
tr:hover {{ background: #ecf0f1; }}
td:nth-child(1), td:nth-child(2) {{ text-align: left; }}
a {{ color: #2980b9; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.meta {{ color: #888; font-size: 13px; margin-bottom: 15px; }}
@media (prefers-color-scheme: dark) {{
    body {{ background: #1a1a2e; color: #e0e0e0; }}
    table {{ background: #16213e; }}
    th {{ background: #2c3e6b; }}
    td {{ border-color: #3a3a5c; }}
    tr:nth-child(even) {{ background: #1a2744; }}
    tr:hover {{ background: #1e3060; }}
    a {{ color: #5dade2; }}
}}
</style>
</head>
<body>
<h1>持仓五截面分析汇总 - {date_str}</h1>
<div class="meta">生成时间: {now_str} &nbsp;|&nbsp; 共 {len(summary_rows)} 支持仓股票</div>
<div class="table-wrap">
<table>
<thead>
<tr>
  <th>代码</th><th>名称</th><th>综合分</th><th>方向</th>
  <th>技术(15%)</th><th>资金(20%)</th><th>基本(30%)</th><th>情绪(15%)</th><th>周期(20%)</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</div>
<p style="font-size:11px;color:#999;margin-top:20px;">
本汇总由系统自动生成，仅供个人研究参考，不构成任何投资建议。五截面评分模型为实验性框架，存在模型风险与数据局限性。
</p>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main batch runner
# ---------------------------------------------------------------------------

def run_batch(
    watch_list: dict,
    date_str: str,
    output_dir: Path,
    single_code: str = None,
) -> list:
    """
    Run five-section analysis for all stocks in watch_list.
    Returns list of summary dicts.
    """
    from data_analyst.research_pipeline.renderer import FiveSectionRenderer

    output_dir.mkdir(parents=True, exist_ok=True)
    renderer = FiveSectionRenderer()
    summary_rows = []

    stocks = list(watch_list.items())
    if single_code:
        stocks = [(k, v) for k, v in stocks if k == single_code]
        if not stocks:
            logger.error(f"Code {single_code} not found in portfolio")
            return []

    total = len(stocks)
    for idx, (code, name) in enumerate(stocks, 1):
        logger.info(f"[{idx}/{total}] ===== {name}({code}) =====")
        try:
            report_data = build_report_data(code, name, date_str)
            if report_data is None:
                logger.warning(f"  Skipping {code}: build_report_data returned None")
                continue

            html = renderer.render(report_data)
            filename = f"{code}_{name}_{date_str}.html"
            filepath = output_dir / filename
            filepath.write_text(html, encoding="utf-8")
            logger.info(
                f"  Saved: {filename}  composite={report_data.composite_score:.1f} {report_data.direction}"
            )

            summary_rows.append({
                "code": code,
                "name": name,
                "composite_score": report_data.composite_score,
                "direction": report_data.direction,
                "score_tech": report_data.score_technical,
                "score_ff": report_data.score_fund_flow,
                "score_fund": report_data.score_fundamental,
                "score_sent": report_data.score_sentiment,
                "score_cc": report_data.score_capital_cycle,
                "filename": filename,
            })

        except Exception as e:
            logger.error(f"  [FAIL] {code} {name}: {e}", exc_info=True)

    return summary_rows


def main():
    parser = argparse.ArgumentParser(description="Batch five-section analysis for portfolio")
    parser.add_argument("--portfolio", default=PORTFOLIO_PATH)
    parser.add_argument("--date", type=str, default=None,
                        help="Analysis date YYYYMMDD (default: today)")
    parser.add_argument("--stock", type=str, default=None,
                        help="Single stock code to analyze (default: all portfolio)")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory (default: output/research/)")
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime("%Y%m%d")
    output_dir = Path(args.output_dir) if args.output_dir else Path(ROOT) / "output" / "research"

    logger.info(f"Analysis date: {date_str}")
    logger.info(f"Output dir: {output_dir}")

    # Pre-flight: verify DB connectivity
    db_env = os.getenv("DB_ENV", "local")
    logger.info(f"Checking DB connectivity ({db_env}) ...")
    if not check_db_connection(env=db_env, timeout=4):
        from config.db import ONLINE_DB_CONFIG, LOCAL_DB_CONFIG
        cfg = ONLINE_DB_CONFIG if db_env == "online" else LOCAL_DB_CONFIG
        host = cfg.get("host", "localhost")
        port = cfg.get("port", 3306)
        logger.error(
            f"Cannot reach {db_env} DB at {host}:{port}.\n"
            f"  - If using online DB, ensure VPN / home network is connected.\n"
            f"  - If using local DB, ensure MySQL server is running.\n"
            f"  Then re-run: PYTHONPATH=. DB_ENV={db_env} python data_analyst/research_pipeline/batch_runner.py"
        )
        sys.exit(1)
    logger.info(f"DB reachable OK")

    watch_list = get_portfolio_stocks(args.portfolio)
    logger.info(f"Non-ETF A-shares: {len(watch_list)}")
    for code, name in watch_list.items():
        logger.info(f"  {code}  {name}")

    summary_rows = run_batch(watch_list, date_str, output_dir, single_code=args.stock)

    if summary_rows:
        index_html = build_index_html(summary_rows, date_str)
        index_path = output_dir / f"index_{date_str}.html"
        index_path.write_text(index_html, encoding="utf-8")
        logger.info(f"Index saved: {index_path}")

    logger.info(f"\n[DONE] Generated {len(summary_rows)}/{len(watch_list)} reports")
    logger.info(f"Reports in: {output_dir}")

    # Print summary table
    print("\n=== Batch Summary ===")
    for r in sorted(summary_rows, key=lambda x: x["composite_score"], reverse=True):
        print(
            f"  {r['code']:8s} {r['name']:12s}  "
            f"composite={r['composite_score']:5.1f}  {r['direction']}"
        )


if __name__ == "__main__":
    main()
