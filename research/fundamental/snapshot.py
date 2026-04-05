# -*- coding: utf-8 -*-
"""
research/fundamental/snapshot.py

FundamentalSnapshot: orchestrates valuation + scoring, builds a DB row,
and upserts it into fundamental_snapshots.

DB/heavy imports are guarded so tests can mock them.
"""
import json
import logging
import re
from datetime import date
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ReportDataTools is imported at module level so tests can patch
# 'research.fundamental.snapshot.ReportDataTools'.
# The import is guarded so this module stays importable even if
# investment_rag is not available.
try:
    from investment_rag.report_engine.data_tools import ReportDataTools
except ImportError:
    ReportDataTools = None  # type: ignore[assignment,misc]

# 1 yi (100 million yuan) in yuan
YI = 1_0000_0000


class FundamentalSnapshot:
    """
    Orchestrates FundamentalValuator + FundamentalScorer and persists
    a snapshot row to the fundamental_snapshots DB table.
    """

    def __init__(self):
        from research.fundamental.valuation import FundamentalValuator
        from research.fundamental.scorer import FundamentalScorer

        self._valuator = FundamentalValuator()
        self._scorer = FundamentalScorer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, code: str, snap_date: Optional[date] = None) -> dict:
        """Build snapshot row and upsert to fundamental_snapshots.

        Args:
            code: Stock code, e.g. '300750'
            snap_date: Snapshot date. Defaults to today.

        Returns:
            The row dict that was upserted.
        """
        row = self._build_row(code, snap_date=snap_date)
        self._upsert(row)
        return row

    def save_batch(self, codes: List[str]) -> List[str]:
        """Save snapshots for multiple codes.

        Args:
            codes: List of stock codes.

        Returns:
            List of codes that succeeded.
        """
        succeeded = []
        for code in codes:
            try:
                self.save(code)
                succeeded.append(code)
            except Exception as exc:
                logger.warning("[FundamentalSnapshot] save failed for %s: %s", code, exc)
        return succeeded

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_row(self, code: str, snap_date: Optional[date] = None) -> dict:
        """Compute all fields and return the row dict (no DB call)."""
        if snap_date is None:
            snap_date = date.today()

        # Step 1: run valuation
        val_result = self._valuator.compute(code)

        # Step 2: get market data
        market = self._valuator._get_market_data(code)

        # Step 3: get financials
        fin = self._valuator._get_financial_data(code)

        # Step 4: get PE/PB history series
        pe_series = self._valuator._get_pe_series(code)
        pb_series = self._valuator._get_pb_series(code)

        # Extract scalar market values
        current_pe = market.get('pe_ttm') if market else None
        current_pb = market.get('pb') if market else None

        # Step 5: compute PE quantile (fraction of history <= current PE)
        pe_quantile = None
        if pe_series is not None and not pe_series.empty and current_pe is not None:
            try:
                pe_quantile = float((pe_series <= current_pe).mean())
            except Exception:
                pe_quantile = None

        # Step 6: compute PB quantile
        pb_quantile = None
        if pb_series is not None and not pb_series.empty and current_pb is not None:
            try:
                pb_quantile = float((pb_series <= current_pb).mean())
            except Exception:
                pb_quantile = None

        # Extract financial metrics
        roe = None
        revenue_yoy = None
        profit_yoy = None
        fcf = None
        ocf_to_profit = None
        debt_ratio = None
        fcf_yield = None

        if fin is not None:
            roe = fin.get('roe')
            revenue_yoy = fin.get('revenue_yoy')
            profit_yoy = fin.get('profit_yoy')

            operating_cashflow = fin.get('operating_cashflow', 0) or 0
            capex = fin.get('capex', 0) or 0
            fcf_raw = operating_cashflow - capex
            fcf = fcf_raw / YI  # convert to 亿元

            net_profit = fin.get('net_profit_ttm')
            if net_profit and net_profit != 0:
                ocf_to_profit = operating_cashflow / net_profit

            total_assets = fin.get('total_assets')
            total_liabilities = fin.get('total_liabilities')
            if total_assets and total_assets > 0 and total_liabilities is not None:
                debt_ratio = total_liabilities / total_assets

            if market:
                total_mv_yi = (market.get('total_mv', 0) or 0) / 10_000
                if total_mv_yi > 0:
                    fcf_yield = (fcf_raw / YI) / total_mv_yi if total_mv_yi else None

        # Step 7: build ScorerInput
        from research.fundamental.scorer import ScorerInput
        scorer_input = ScorerInput(
            pe_quantile=pe_quantile,
            pb_quantile=pb_quantile,
            fcf_yield=fcf_yield,
            roe=roe,
            roe_prev=None,
            ocf_to_profit=ocf_to_profit,
            debt_ratio=debt_ratio,
            revenue_yoy=revenue_yoy,
            profit_yoy=profit_yoy,
        )

        # Step 8: score
        score_result = self._scorer.score(scorer_input)

        # Step 9: parse expected_return_2yr from ReportDataTools
        expected_return_2yr = None
        try:
            context_text = ReportDataTools().get_expected_return_context(code)
            match = re.search(r'2年预期总回报[：:]\s*([\-\d.]+)%', context_text)
            if match:
                expected_return_2yr = float(match.group(1))
        except Exception as exc:
            logger.warning("[FundamentalSnapshot] expected_return parse failed for %s: %s", code, exc)

        # Step 10: build valuation_json
        valuation_json = json.dumps(
            {
                'current_market_cap_yi': val_result.current_market_cap_yi,
                'methods': val_result.methods,
            },
            ensure_ascii=False,
            default=str,
        )

        return {
            'code': code,
            'snap_date': snap_date.strftime('%Y-%m-%d'),
            'fundamental_score': score_result.composite_score,
            'pe_ttm': current_pe,
            'pe_quantile_5yr': pe_quantile,
            'pb': current_pb,
            'pb_quantile_5yr': pb_quantile,
            'roe': roe,
            'revenue_yoy': revenue_yoy,
            'profit_yoy': profit_yoy,
            'fcf': fcf,
            'net_cash': None,
            'expected_return_2yr': expected_return_2yr,
            'valuation_json': valuation_json,
        }

    def _upsert(self, row: dict) -> None:
        """Upsert a row into fundamental_snapshots using INSERT ... ON DUPLICATE KEY UPDATE."""
        from config.db import execute_query

        sql = """
            INSERT INTO fundamental_snapshots
                (code, snap_date, fundamental_score, pe_ttm, pe_quantile_5yr,
                 pb, pb_quantile_5yr, roe, revenue_yoy, profit_yoy,
                 fcf, net_cash, expected_return_2yr, valuation_json)
            VALUES
                (%s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s,
                 %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                fundamental_score    = VALUES(fundamental_score),
                pe_ttm               = VALUES(pe_ttm),
                pe_quantile_5yr      = VALUES(pe_quantile_5yr),
                pb                   = VALUES(pb),
                pb_quantile_5yr      = VALUES(pb_quantile_5yr),
                roe                  = VALUES(roe),
                revenue_yoy          = VALUES(revenue_yoy),
                profit_yoy           = VALUES(profit_yoy),
                fcf                  = VALUES(fcf),
                net_cash             = VALUES(net_cash),
                expected_return_2yr  = VALUES(expected_return_2yr),
                valuation_json       = VALUES(valuation_json)
        """
        params = (
            row['code'],
            row['snap_date'],
            row['fundamental_score'],
            row['pe_ttm'],
            row['pe_quantile_5yr'],
            row['pb'],
            row['pb_quantile_5yr'],
            row['roe'],
            row['revenue_yoy'],
            row['profit_yoy'],
            row['fcf'],
            row['net_cash'],
            row['expected_return_2yr'],
            row['valuation_json'],
        )
        execute_query(sql, params)
