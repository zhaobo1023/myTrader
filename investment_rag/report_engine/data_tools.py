# -*- coding: utf-8 -*-
"""
ReportDataTools - Unified data collection layer for report generation.

Integrates three data sources:
1. RAG:       ChromaDB vector search + BM25 + Reranker (existing investment_rag/retrieval/)
2. Financial: AKShare financial summary (investment_rag/ingest/loaders/)
3. Technical: K-line + indicators + signals (strategist/tech_scan/)

DESIGN RULES:
- Technical K-line data MUST go through DataFetcher (not raw SQL). DataFetcher handles
  column name mapping (open_price -> open etc.) and ETF vs stock table routing.
- SignalLevel.name (RED/YELLOW/GREEN/INFO) is used instead of .value to avoid emoji.
- All methods return plain formatted strings for direct Prompt embedding.
"""
import logging
from typing import List, Optional

import pandas as pd

# DataFetcher is imported at module level so that tests can patch
# "investment_rag.report_engine.data_tools.DataFetcher".
# The import is guarded so the module stays importable even if
# strategist.tech_scan is not on the path.
try:
    from strategist.tech_scan.data_fetcher import DataFetcher
except ImportError:
    DataFetcher = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

# DB access for valuation data -- imported at module level to allow test mocking
try:
    from config.db import execute_query as _execute_query
except ImportError:
    _execute_query = None  # allows import in environments without DB config


def _safe_float(val) -> "float | None":
    """Safely convert a DB value (possibly Decimal/None/NaN) to float."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f  # NaN check
    except (TypeError, ValueError):
        return None


class ReportDataTools:
    """Unified data collection tools for research report generation."""

    def __init__(self, db_env: str = "online"):
        # Lazy imports to avoid mandatory heavy dependencies at module import time.
        # Tests use __new__ + manual attribute injection, bypassing __init__.
        from investment_rag.retrieval.hybrid_retriever import HybridRetriever
        from investment_rag.retrieval.reranker import Reranker
        from investment_rag.ingest.loaders.akshare_loader import AKShareLoader

        self._db_env = db_env
        self._retriever = HybridRetriever()
        self._reranker = Reranker()
        self._financial_loader = AKShareLoader()

    # ----------------------------------------------------------
    # 1. RAG Retrieval
    # ----------------------------------------------------------

    def query_rag(
        self,
        query: str,
        stock_code: Optional[str] = None,
        collection: str = "reports",
        top_k: int = 5,
    ) -> str:
        """
        Retrieve relevant document chunks via HybridRetriever + Reranker.

        Args:
            query: Search query
            stock_code: If specified, filter ChromaDB by stock_code metadata
            collection: ChromaDB collection name (reports/announcements/notes/macro)
            top_k: Final number of results

        Returns:
            Formatted text with source annotations
        """
        where = {"stock_code": stock_code} if stock_code else None

        try:
            hits = self._retriever.retrieve(
                query=query,
                collection=collection,
                top_k=top_k * 2,
                where=where,
            )
            hits = self._reranker.rerank(query, hits, top_k=top_k)
        except Exception as e:
            logger.warning("[ReportDataTools] RAG retrieve failed: %s", e)
            return "[RAG retrieval failed, skipping]"

        if not hits:
            return "[RAG: no relevant content found]"

        parts = []
        for i, h in enumerate(hits, 1):
            source = h.get("metadata", {}).get("source", "unknown source")
            text = h.get("text", "")[:600]
            parts.append(f"[Source {i}: {source}]\n{text}")

        return "\n\n".join(parts)

    def query_rag_multi(
        self,
        queries: List[str],
        stock_name: str,
        stock_code: Optional[str] = None,
        collection: str = "reports",
        top_k_per_query: int = 3,
    ) -> str:
        """
        Multi-query retrieval with deduplication and merge.

        Args:
            queries: Query template list (supports {stock_name} placeholder)
            stock_name: Company name for template substitution
            stock_code: Optional stock filter
            collection: Collection name
            top_k_per_query: Results per query

        Returns:
            Deduplicated merged text
        """
        seen_ids: set = set()
        all_hits: list = []
        where = {"stock_code": stock_code} if stock_code else None

        for q_tpl in queries:
            q = q_tpl.format(stock_name=stock_name)
            try:
                hits = self._retriever.retrieve(
                    query=q,
                    collection=collection,
                    top_k=top_k_per_query * 2,
                    where=where,
                )
                hits = self._reranker.rerank(q, hits, top_k=top_k_per_query)
            except Exception as e:
                logger.warning("[ReportDataTools] multi-query failed '%s': %s", q, e)
                continue

            for h in hits:
                uid = h.get("id") or h.get("text", "")[:80]
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    all_hits.append(h)

        if not all_hits:
            return "[RAG multi-query: no relevant content found]"

        parts = []
        limit = top_k_per_query * len(queries)
        for i, h in enumerate(all_hits[:limit], 1):
            source = h.get("metadata", {}).get("source", "unknown source")
            text = h.get("text", "")[:500]
            parts.append(f"[Source {i}: {source}]\n{text}")

        return "\n\n".join(parts)

    # ----------------------------------------------------------
    # 2. Financial Data
    # ----------------------------------------------------------

    def get_financial_data(self, stock_code: str, years: int = 3) -> str:
        """
        Get AKShare financial summary, return formatted text.

        Args:
            stock_code: Stock code (numeric, e.g. "000858")
            years: Number of years

        Returns:
            Formatted financial summary text
        """
        clean_code = stock_code.split(".")[0]
        result = self._financial_loader.get_financial_data(clean_code, years)
        if result.get("error"):
            logger.warning("[ReportDataTools] Financial data error: %s", result["error"])
        summary = result.get("summary", "")
        return summary if summary else f"[Financial Data] {clean_code} no data available"

    # ----------------------------------------------------------
    # 4. Valuation Historical Percentile (capital cycle integration)
    # ----------------------------------------------------------

    def get_valuation_snapshot(self, stock_code: str, years: int = 5) -> str:
        """
        Query trade_stock_daily_basic for historical PE/PB/dv_ttm, compute {years}-year percentile.

        Data table: trade_stock_daily_basic
        Stock code format: supports "000858" or "000858.SZ" (auto-extracts numeric part)

        Returns:
            Formatted text with current PE/PB/dv_ttm and historical percentile labels
        """
        clean_code = stock_code.split(".")[0]

        if _execute_query is None:
            return f"[Valuation Data] DB module not loaded, skipping"

        from datetime import date, timedelta

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
            return f"[估值数据] {clean_code} 数据不足（{len(rows) if rows else 0} 行，需 >= 20）"

        df = pd.DataFrame(rows)
        latest = df.iloc[-1]
        date_range = f"{df['trade_date'].iloc[0]} 至 {df['trade_date'].iloc[-1]}"
        lines = [f"[估值历史分位] {clean_code}，{years}年数据范围: {date_range}（{len(df)} 个交易日）"]

        # PE(TTM) -- exclude negatives (loss periods)
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
        else:
            lines.append("PB: 无效或数据不足")

        # Dividend yield (TTM)
        dv_series = df["dv_ttm"].dropna()
        dv_current = _safe_float(latest.get("dv_ttm")) or 0.0
        if len(dv_series) >= 20:
            dv_pct = float((dv_series < dv_current).mean() * 100) if dv_current > 0 else 0.0
            lines.append(f"股息率(TTM): {dv_current:.2f}%，历史分位 {dv_pct:.0f}%")
        else:
            lines.append("股息率(TTM): 数据不足")

        return "\n".join(lines)

    def get_expected_return_context(
        self,
        stock_code: str,
        earnings_growth_2yr: float = 0.0,
        target_pe_quantile: float = 0.40,
        years: int = 5,
    ) -> str:
        """
        Compute 2-year expected return (3-part decomposition: earnings + valuation reversion + dividend).

        Formula:
          earnings_contribution = (1 + earnings_growth_2yr)^2 - 1
          target_pe = PE historical series at target_pe_quantile
          valuation_contribution = target_pe / current_pe - 1
          dividend_contribution = dv_ttm% * 2
          total = earnings + valuation + dividend

        Args:
            stock_code: Stock code
            earnings_growth_2yr: 2-year net profit CAGR estimate (e.g. 0.10 = 10%/year)
                                  Default 0.0 (conservative, no growth)
            target_pe_quantile: Valuation reversion target percentile (default 40%, conservative)
            years: Historical data years

        Returns:
            Formatted text with 3-part breakdown and total expected return
        """
        clean_code = stock_code.split(".")[0]

        if _execute_query is None:
            return "[预期回报] DB module not loaded, skipping"

        from datetime import date, timedelta

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
        df["pe_ttm"] = pd.to_numeric(df["pe_ttm"], errors="coerce")
        pe_series = df["pe_ttm"].dropna()
        pe_series = pe_series[pe_series > 0]
        current_pe = _safe_float(df.iloc[-1].get("pe_ttm"))
        current_dv = _safe_float(df.iloc[-1].get("dv_ttm")) or 0.0

        if not current_pe or current_pe <= 0:
            return "[预期回报] 当前 PE 无效（亏损），无法计算"

        # 3-part decomposition (simplified additive, no cross-term)
        earnings_contribution = (1 + earnings_growth_2yr) ** 2 - 1
        target_pe = float(pe_series.quantile(target_pe_quantile))
        pe_change = target_pe / current_pe - 1
        valuation_contribution = pe_change   # no earnings scaling -- simplified additive
        dividend_contribution = (current_dv / 100) * 2  # dv_ttm is percentage, x2 years
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
        """Map historical percentile (0~100) to valuation label."""
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

    # ----------------------------------------------------------
    # 3. Technical Analysis
    # ----------------------------------------------------------

    def get_tech_analysis(self, stock_code: str, lookback_days: int = 120) -> str:
        """
        Load K-line via DataFetcher, compute indicators with IndicatorCalculator,
        detect signals with SignalDetector, return formatted text for LLM.

        Uses DataFetcher (not raw SQL) because:
        - DataFetcher correctly maps open_price/high_price/low_price/close_price column names
        - DataFetcher handles ETF (trade_etf_daily) vs stock (trade_stock_daily) routing

        Args:
            stock_code: Stock code (with or without suffix)
            lookback_days: Calendar days to look back

        Returns:
            Formatted technical analysis text
        """
        try:
            from strategist.tech_scan.indicator_calculator import IndicatorCalculator
            from strategist.tech_scan.signal_detector import SignalDetector
        except ImportError as e:
            logger.error("[ReportDataTools] tech_scan import failed: %s", e)
            return f"[Technical] tech_scan import failed: {e}"

        if DataFetcher is None:
            return "[Technical] DataFetcher not available (strategist.tech_scan not installed)"

        fetcher = DataFetcher(env=self._db_env)
        try:
            df = fetcher.fetch_daily_data([stock_code], lookback_days=lookback_days)
        except Exception as e:
            logger.warning("[ReportDataTools] DataFetcher failed for %s: %s", stock_code, e)
            return f"[Technical] {stock_code} data fetch failed: {e}"

        if df is None or df.empty:
            return f"[Technical] {stock_code} no K-line data available"

        try:
            calc = IndicatorCalculator()
            df = calc.calculate_all(df)
            latest = df.iloc[-1]
            detector = SignalDetector()
            signals = detector.detect_all(latest)
            kdj_signals = detector.detect_kdj_signals(latest)
            all_signals = signals + kdj_signals
            trend = detector.get_trend_status(latest)
            macd_div = detector.detect_macd_divergence(df)
        except Exception as e:
            logger.warning("[ReportDataTools] Indicator calculation failed: %s", e)
            return f"[Technical] {stock_code} indicator calculation failed: {e}"

        return self._format_tech_text(latest, all_signals, trend, macd_div)

    # ----------------------------------------------------------
    # 5. Bank Industry Specific Data
    # ----------------------------------------------------------

    def get_bank_indicators(self, stock_code: str) -> str:
        """
        获取银行行业专项指标，用于 Step1 银行资产质量分析。

        数据来源：
        - financial_balance：NPL率、拨备覆盖率、CAR、NIM（由 financial_fetcher 写入）
        - bank_asset_quality：NPL率2（逾期90d+ + 重组贷款/总贷款）、逾期/不良比

        Returns:
            Formatted text for LLM consumption
        """
        if _execute_query is None:
            return "[银行指标] DB模块未加载"

        clean_code = stock_code.split(".")[0]
        lines = [f"[银行专项指标] {clean_code}"]

        # -- 1. 标准财务指标（来自 financial_balance）--
        sql_std = """
            SELECT
                report_date,
                npl_ratio,
                provision_coverage,
                cap_adequacy_ratio,
                nim,
                tier1_ratio
            FROM financial_balance
            WHERE stock_code = %s
            ORDER BY report_date DESC
            LIMIT 8
        """
        try:
            rows = _execute_query(sql_std, params=(clean_code,), env=self._db_env)
            if rows:
                lines.append("\n-- 资产质量与经营指标（近8期）--")
                lines.append(
                    f"{'报告期':<12} {'官方NPL率':>10} {'拨备覆盖':>10} "
                    f"{'NIM(%)':>8} {'CET1(%)':>8} {'CAR(%)':>8}"
                )
                for r in rows:
                    npl = f"{float(r['npl_ratio']):.2f}%" if r.get('npl_ratio') else "N/A"
                    prov = f"{float(r['provision_coverage']):.1f}%" if r.get('provision_coverage') else "N/A"
                    nim = f"{float(r['nim']):.2f}%" if r.get('nim') else "N/A"
                    t1 = f"{float(r['tier1_ratio']):.2f}%" if r.get('tier1_ratio') else "N/A"
                    car = f"{float(r['cap_adequacy_ratio']):.2f}%" if r.get('cap_adequacy_ratio') else "N/A"
                    lines.append(
                        f"{str(r.get('report_date','')):<12} {npl:>10} {prov:>10} "
                        f"{nim:>8} {t1:>8} {car:>8}"
                    )
            else:
                lines.append("[financial_balance] 无数据（需运行 financial_fetcher）")
        except Exception as e:
            logger.warning("[ReportDataTools] bank_std query failed for %s: %s", stock_code, e)
            lines.append(f"[financial_balance] 查询失败: {e}")

        # -- 2. 扩展资产质量（来自 bank_asset_quality）--
        sql_ext = """
            SELECT
                report_date,
                npl_ratio2,
                overdue_91,
                restructured,
                provision_adj,
                profit_adj_est
            FROM bank_asset_quality
            WHERE stock_code = %s
            ORDER BY report_date DESC
            LIMIT 8
        """
        try:
            rows2 = _execute_query(sql_ext, params=(clean_code,), env=self._db_env)
            if rows2:
                lines.append("\n-- Flitter方法：扩展不良指标 --")
                lines.append(
                    f"{'报告期':<12} {'NPL率2(%)':>12} {'逾期90d(亿)':>12} "
                    f"{'重组贷款(亿)':>12} {'拨备调整(亿)':>12} {'利润调整(亿)':>12}"
                )
                for r in rows2:
                    npl2 = f"{float(r['npl_ratio2']):.2f}%" if r.get('npl_ratio2') else "N/A"
                    ov91 = f"{float(r['overdue_91']):.1f}亿" if r.get('overdue_91') else "N/A"
                    restr = f"{float(r['restructured']):.1f}亿" if r.get('restructured') else "N/A"
                    padj = f"{float(r['provision_adj']):.1f}亿" if r.get('provision_adj') is not None else "N/A"
                    prof = f"{float(r['profit_adj_est']):.1f}亿" if r.get('profit_adj_est') is not None else "N/A"
                    lines.append(
                        f"{str(r.get('report_date','')):<12} {npl2:>12} {ov91:>12} "
                        f"{restr:>12} {padj:>12} {prof:>12}"
                    )
                lines.append(
                    "注：NPL率2 = (逾期90d+ + 重组贷款) / 总贷款；"
                    "拨备调整 = (NPL率2-NPL率) x 总贷款 x 150%拨备要求；"
                    "利润调整 = 若按NPL率2计提，税后利润受损估算"
                )
            else:
                lines.append("[bank_asset_quality] 无数据（需运行 financial_fetcher 的 Flitter 模块）")
        except Exception as e:
            logger.warning("[ReportDataTools] bank_ext query failed for %s: %s", stock_code, e)
            lines.append(f"[bank_asset_quality] 查询失败: {e}")

        return "\n".join(lines)

    def _format_tech_text(
        self,
        latest: pd.Series,
        signals: list,
        trend: str,
        macd_divergence: dict,
    ) -> str:
        """Format technical indicators as LLM-readable plain text. No emoji."""

        def _v(val, fmt=".2f"):
            if val is None:
                return "N/A"
            try:
                f = float(val)
                if f != f:  # NaN check
                    return "N/A"
                return f"{f:{fmt}}"
            except (TypeError, ValueError):
                return "N/A"

        lines = [
            f"[Technical Indicators] Latest date: {latest.get('trade_date', 'N/A')}",
            f"Close: {_v(latest.get('close'))}",
            f"MA5/20/60/250: {_v(latest.get('ma5'))}/{_v(latest.get('ma20'))}/{_v(latest.get('ma60'))}/{_v(latest.get('ma250'))}",
            f"MACD DIF/DEA: {_v(latest.get('macd_dif'), '.4f')}/{_v(latest.get('macd_dea'), '.4f')}",
            f"RSI(14): {_v(latest.get('rsi'), '.1f')}",
            f"KDJ K/D/J: {_v(latest.get('kdj_k'), '.1f')}/{_v(latest.get('kdj_d'), '.1f')}/{_v(latest.get('kdj_j'), '.1f')}",
            f"BOLL Upper/Middle/Lower: {_v(latest.get('boll_upper'))}/{_v(latest.get('boll_middle'))}/{_v(latest.get('boll_lower'))}",
            f"ATR(14): {_v(latest.get('atr_14'))}",
            f"Volume Ratio (5-day): {_v(latest.get('volume_ratio'), '.2f')}",
            f"Trend: {trend}",
            f"MACD Divergence: {macd_divergence.get('type', 'None')} "
            f"(confidence={macd_divergence.get('confidence', 'N/A')}, "
            f"{macd_divergence.get('description', '')})",
            "",
            "[Signal List]",
        ]

        if not signals:
            lines.append("  (no signals triggered)")
        else:
            for sig in signals:
                # Use .name (RED/YELLOW/GREEN/INFO) NOT .value (has emoji)
                level_tag = f"[{sig.level.name}]"
                lines.append(f"  {level_tag} {sig.name}: {sig.description}")

        return "\n".join(lines)

    # ----------------------------------------------------------
    # 6. Consensus Forecast & Earnings Preview
    # ----------------------------------------------------------

    def get_consensus_forecast(self, stock_code: str) -> str:
        """
        获取分析师一致预期（EPS、ROE 预测）。

        数据源：AKShare stock_profit_forecast_ths（同花顺数据）
        适用于所有行业。

        Returns:
            Formatted text with consensus forecast for 2-3 years
        """
        clean_code = stock_code.split(".")[0]
        try:
            import akshare as ak
            df = ak.stock_profit_forecast_ths(symbol=clean_code)
            if df is None or df.empty:
                return "[一致预期] 无数据"

            lines = [f"[分析师一致预期] {clean_code}（同花顺数据）"]
            lines.append(f"\n{'年度':<8} {'预测机构数':>8} {'EPS最小值':>10} {'EPS均值':>10} {'EPS最大值':>10} {'行业均值':>10}")

            for _, row in df.iterrows():
                year = str(row.get("年度", "N/A"))
                count = str(row.get("预测机构数", "N/A"))
                min_val = f"{float(row['最小值']):.2f}" if row.get("最小值") else "N/A"
                avg_val = f"{float(row['均值']):.2f}" if row.get("均值") else "N/A"
                max_val = f"{float(row['最大值']):.2f}" if row.get("最大值") else "N/A"
                ind_avg = f"{float(row['行业平均数']):.2f}" if row.get("行业平均数") else "N/A"

                lines.append(
                    f"{year:<8} {count:>8} {min_val:>10} {avg_val:>10} "
                    f"{max_val:>10} {ind_avg:>10}"
                )

            return "\n".join(lines)
        except Exception as e:
            logger.warning("[ReportDataTools] Consensus forecast failed for %s: %s", stock_code, e)
            return f"[一致预期] {clean_code} 获取失败: {e}"

    def get_earnings_preview(self, stock_code: str) -> str:
        """
        获取最新业绩预告（预增/略增/略减/预减）。

        数据源：AKShare stock_yjyg_em（网易数据）
        目前 API 稳定性有限，返回 fallback 文本。

        Returns:
            Formatted text with latest earnings preview info (或 fallback)
        """
        return "[业绩预告] 数据源暂不可用，建议查看公司公告"

    def get_top_shareholders(self, stock_code: str, top_n: int = 10) -> str:
        """
        获取十大流通股东信息。

        数据源：AKShare stock_gdfx_free_holding_detail_em（网易数据）
        目前 API 稳定性有限，返回 fallback 文本。

        Args:
            stock_code: Stock code
            top_n: Number of top shareholders to return

        Returns:
            Formatted text with top shareholders (或 fallback)
        """
        return "[流通股东] 数据源暂不可用，建议查看最新年报附注"

    def get_bank_cross_section(self) -> str:
        """
        获取全A股银行的横截面对标数据。

        暂时返回提示文本（完整实现需汇总全行业数据）。

        Returns:
            Formatted text noting data limitation
        """
        return """[银行行业对标表]
代表性银行估值位置（按PB排序）：
- 城商行：PB 0.6-0.8x，隐含ROE 12-15%，风险较高
- 股份制银行：PB 0.8-1.1x，隐含ROE 13-18%，增速中等
- 大型银行：PB 0.9-1.2x，隐含ROE 12-17%，稳定性强

当前个股在同业中的位置：低估(PB<0.8) / 合理(0.8-1.2) / 高估(PB>1.2)

注：完整对标表需汇总全部上市银行数据，建议结合年度行业研究报告查阅。"""
