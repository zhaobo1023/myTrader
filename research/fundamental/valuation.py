# -*- coding: utf-8 -*-
"""
FundamentalValuator - 8-method parallel valuation for A-share stocks.

Methods:
  1. PE-earnings      : fair_pe (40th pct of 5yr PE history) x TTM net profit
  2. PB-netasset      : fair_pb (40th pct of 5yr PB history) x book value
  3. FCF-yield        : FCF / 6% hurdle rate
  4. DCF-3stage       : PV of 3-stage cash flows
  5. Gordon-implied-g : diagnostic implied growth rate (no fair cap)
  6. Ceiling-matrix   : 3x3 scenario matrix
  7. Liquidation      : max(0, total_assets*0.60 - liabilities)
  8. Replacement      : max(0, total_assets*0.80 - liabilities)
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 1 yi (100 million yuan) in yuan
YI = 1_0000_0000

# Cost of equity used in Gordon model and DCF terminal value
COST_OF_EQUITY = 0.08

# FCF hurdle rate
FCF_HURDLE = 0.06

# DCF default growth assumptions: [(rate, years), ...] + terminal
DCF_STAGE1_RATE = 0.15
DCF_STAGE1_YEARS = 5
DCF_STAGE2_RATE = 0.08
DCF_STAGE2_YEARS = 5
DCF_TERMINAL_RATE = 0.03


def _to_tushare(code: str) -> str:
    """Convert bare stock code to tushare format with market suffix.

    '300750' -> '300750.SZ'  (starts with 0 or 3)
    '600519' -> '600519.SH'  (starts with 6)
    If already contains '.' return as-is.
    """
    if '.' in code:
        return code
    if code.startswith('6'):
        return f"{code}.SH"
    return f"{code}.SZ"


@dataclass
class ValuationResult:
    """Container for 8-method valuation output."""
    code: str
    current_market_cap_yi: float
    methods: list = field(default_factory=list)
    notes: str = ''


class FundamentalValuator:
    """Compute 8 fundamental valuation methods for a given A-share stock code."""

    def __init__(self):
        pass

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def compute(self, code: str) -> ValuationResult:
        """Run all 8 valuation methods for *code* and return a ValuationResult.

        Args:
            code: Pure numeric A-share code, e.g. '300750', or with suffix '300750.SZ'.
        """
        market = self._get_market_data(code)
        financials = self._get_financial_data(code)
        pe_series = self._get_pe_series(code)
        pb_series = self._get_pb_series(code)

        # current market cap in yi
        current_mv_yi = (market['total_mv'] / 10_000) if market else 0.0

        result = ValuationResult(
            code=code,
            current_market_cap_yi=current_mv_yi,
        )

        result.methods = [
            self._method_pe_earnings(market, financials, pe_series, current_mv_yi),
            self._method_pb_netasset(market, financials, pb_series, current_mv_yi),
            self._method_fcf_yield(market, financials, current_mv_yi),
            self._method_dcf_3stage(market, financials, current_mv_yi),
            self._method_gordon_implied_g(market),
            self._method_ceiling_matrix(market, financials, current_mv_yi),
            self._method_liquidation(financials, current_mv_yi),
            self._method_replacement(financials, current_mv_yi),
        ]

        return result

    # ------------------------------------------------------------------
    # Valuation methods
    # ------------------------------------------------------------------

    def _method_pe_earnings(
        self,
        market: Optional[Dict],
        financials: Optional[Dict],
        pe_series: Optional[pd.Series],
        current_mv_yi: float,
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {'method': 'PE-earnings', 'fair_market_cap_yi': None, 'vs_current': None, 'fair_pe': None}
        try:
            if financials is None or pe_series is None or pe_series.empty:
                return entry
            net_profit_yi = financials['net_profit_ttm'] / YI
            fair_pe = float(np.percentile(pe_series.dropna(), 40))
            fair_mv_yi = fair_pe * net_profit_yi
            entry['fair_pe'] = fair_pe
            entry['fair_market_cap_yi'] = fair_mv_yi
            if current_mv_yi and current_mv_yi > 0:
                entry['vs_current'] = fair_mv_yi / current_mv_yi - 1
        except Exception as exc:
            logger.warning("[PE-earnings] error: %s", exc)
        return entry

    def _method_pb_netasset(
        self,
        market: Optional[Dict],
        financials: Optional[Dict],
        pb_series: Optional[pd.Series],
        current_mv_yi: float,
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {'method': 'PB-netasset', 'fair_market_cap_yi': None, 'vs_current': None, 'fair_pb': None}
        try:
            if financials is None or pb_series is None or pb_series.empty:
                return entry
            net_assets_yi = financials['net_assets'] / YI
            fair_pb = float(np.percentile(pb_series.dropna(), 40))
            fair_mv_yi = fair_pb * net_assets_yi
            entry['fair_pb'] = fair_pb
            entry['fair_market_cap_yi'] = fair_mv_yi
            if current_mv_yi and current_mv_yi > 0:
                entry['vs_current'] = fair_mv_yi / current_mv_yi - 1
        except Exception as exc:
            logger.warning("[PB-netasset] error: %s", exc)
        return entry

    def _method_fcf_yield(
        self,
        market: Optional[Dict],
        financials: Optional[Dict],
        current_mv_yi: float,
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            'method': 'FCF-yield',
            'fair_market_cap_yi': None,
            'vs_current': None,
            'fcf_yi': None,
            'fcf_yield_current': None,
        }
        try:
            if financials is None:
                return entry
            fcf = financials['operating_cashflow'] - financials['capex']
            fcf_yi = fcf / YI
            entry['fcf_yi'] = fcf_yi
            fair_mv_yi = fcf_yi / FCF_HURDLE
            entry['fair_market_cap_yi'] = fair_mv_yi
            if current_mv_yi and current_mv_yi > 0:
                entry['vs_current'] = fair_mv_yi / current_mv_yi - 1
                entry['fcf_yield_current'] = fcf_yi / current_mv_yi
        except Exception as exc:
            logger.warning("[FCF-yield] error: %s", exc)
        return entry

    def _method_dcf_3stage(
        self,
        market: Optional[Dict],
        financials: Optional[Dict],
        current_mv_yi: float,
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            'method': 'DCF-3stage',
            'fair_market_cap_yi': None,
            'vs_current': None,
            'stage1_rate': DCF_STAGE1_RATE,
            'stage2_rate': DCF_STAGE2_RATE,
            'terminal_rate': DCF_TERMINAL_RATE,
        }
        try:
            if financials is None:
                return entry
            fcf0 = financials['operating_cashflow'] - financials['capex']
            discount = COST_OF_EQUITY

            pv = 0.0
            # Stage 1
            for t in range(1, DCF_STAGE1_YEARS + 1):
                cf = fcf0 * ((1 + DCF_STAGE1_RATE) ** t)
                pv += cf / ((1 + discount) ** t)

            # Stage 2
            cf_end_s1 = fcf0 * ((1 + DCF_STAGE1_RATE) ** DCF_STAGE1_YEARS)
            for t in range(1, DCF_STAGE2_YEARS + 1):
                cf = cf_end_s1 * ((1 + DCF_STAGE2_RATE) ** t)
                pv += cf / ((1 + discount) ** (DCF_STAGE1_YEARS + t))

            # Terminal value (Gordon)
            cf_end_s2 = cf_end_s1 * ((1 + DCF_STAGE2_RATE) ** DCF_STAGE2_YEARS)
            terminal_cf = cf_end_s2 * (1 + DCF_TERMINAL_RATE)
            terminal_value = terminal_cf / (discount - DCF_TERMINAL_RATE)
            pv += terminal_value / ((1 + discount) ** (DCF_STAGE1_YEARS + DCF_STAGE2_YEARS))

            fair_mv_yi = pv / YI
            entry['fair_market_cap_yi'] = fair_mv_yi
            if current_mv_yi and current_mv_yi > 0:
                entry['vs_current'] = fair_mv_yi / current_mv_yi - 1
        except Exception as exc:
            logger.warning("[DCF-3stage] error: %s", exc)
        return entry

    def _method_gordon_implied_g(
        self,
        market: Optional[Dict],
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            'method': 'Gordon-implied-g',
            'fair_market_cap_yi': None,   # diagnostic only
            'vs_current': None,
            'implied_growth_rate': None,
        }
        try:
            if market is None:
                return entry
            pe = market.get('pe_ttm')
            if pe and pe > 0:
                implied_g = COST_OF_EQUITY - 1.0 / pe
                entry['implied_growth_rate'] = implied_g
        except Exception as exc:
            logger.warning("[Gordon-implied-g] error: %s", exc)
        return entry

    def _method_ceiling_matrix(
        self,
        market: Optional[Dict],
        financials: Optional[Dict],
        current_mv_yi: float,
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            'method': 'Ceiling-matrix',
            'fair_market_cap_yi': None,
            'vs_current': None,
            'scenarios': [],
        }
        try:
            if financials is None or market is None:
                return entry

            rev_yi = financials['revenue_ttm'] / YI
            current_net_margin = (
                financials['net_profit_ttm'] / financials['revenue_ttm']
                if financials['revenue_ttm'] > 0 else 0.0
            )
            current_pe = market.get('pe_ttm', 20.0) or 20.0

            # 3x3 grid: rev_mult in [0.8, 1.0, 1.2], net_margin in [-0.2, 0, +0.2] relative change
            rev_mults = [0.8, 1.0, 1.2]
            margin_deltas = [-0.2, 0.0, 0.2]   # relative change to current net margin

            # Build 9 scenarios: row = rev_mult, col = margin_delta (exit PE = current PE)
            scenarios = []
            for rev_mult in rev_mults:
                for margin_delta in margin_deltas:
                    new_margin = current_net_margin * (1 + margin_delta)
                    new_rev = rev_yi * rev_mult
                    new_profit = new_rev * new_margin
                    exit_pe = current_pe
                    fair_mv = new_profit * exit_pe
                    vs = (fair_mv / current_mv_yi - 1) if current_mv_yi > 0 else None
                    scenarios.append({
                        'rev_mult': rev_mult,
                        'margin_delta': margin_delta,
                        'fair_market_cap_yi': fair_mv,
                        'vs_current': vs,
                    })

            entry['scenarios'] = scenarios
            # Middle scenario (index 4 in 0-indexed 9-element list) is the base case
            base = scenarios[4]
            entry['fair_market_cap_yi'] = base['fair_market_cap_yi']
            entry['vs_current'] = base['vs_current']
        except Exception as exc:
            logger.warning("[Ceiling-matrix] error: %s", exc)
        return entry

    def _method_liquidation(
        self,
        financials: Optional[Dict],
        current_mv_yi: float,
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {'method': 'Liquidation', 'fair_market_cap_yi': None, 'vs_current': None}
        try:
            if financials is None:
                return entry
            liq = max(0.0, financials['total_assets'] * 0.60 - financials['total_liabilities'])
            fair_mv_yi = liq / YI
            entry['fair_market_cap_yi'] = fair_mv_yi
            if current_mv_yi and current_mv_yi > 0:
                entry['vs_current'] = fair_mv_yi / current_mv_yi - 1
        except Exception as exc:
            logger.warning("[Liquidation] error: %s", exc)
        return entry

    def _method_replacement(
        self,
        financials: Optional[Dict],
        current_mv_yi: float,
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {'method': 'Replacement', 'fair_market_cap_yi': None, 'vs_current': None}
        try:
            if financials is None:
                return entry
            rep = max(0.0, financials['total_assets'] * 0.80 - financials['total_liabilities'])
            fair_mv_yi = rep / YI
            entry['fair_market_cap_yi'] = fair_mv_yi
            if current_mv_yi and current_mv_yi > 0:
                entry['vs_current'] = fair_mv_yi / current_mv_yi - 1
        except Exception as exc:
            logger.warning("[Replacement] error: %s", exc)
        return entry

    # ------------------------------------------------------------------
    # Data access methods (real DB / AKShare in production)
    # ------------------------------------------------------------------

    def _get_market_data(self, code: str) -> Optional[Dict]:
        """Fetch current market data from DB.

        Returns dict with keys: pe_ttm, pb, total_mv (万元), dv_ttm, close.
        Returns None on failure.
        """
        try:
            from config.db import execute_query  # lazy import
            ts_code = _to_tushare(code)
            sql = """
                SELECT pe_ttm, pb, total_mv, dv_ttm, close
                FROM trade_daily_basic
                WHERE ts_code = %s
                ORDER BY trade_date DESC
                LIMIT 1
            """
            rows = execute_query(sql, (ts_code,))
            if not rows:
                return None
            row = rows[0]
            return {
                'pe_ttm': float(row[0]) if row[0] is not None else None,
                'pb': float(row[1]) if row[1] is not None else None,
                'total_mv': float(row[2]) if row[2] is not None else 0.0,
                'dv_ttm': float(row[3]) if row[3] is not None else None,
                'close': float(row[4]) if row[4] is not None else None,
            }
        except Exception as exc:
            logger.warning("[_get_market_data] %s: %s", code, exc)
            return None

    def _get_financial_data(self, code: str) -> Optional[Dict]:
        """Fetch latest TTM financial data via AKShare.

        Returns dict with keys: net_profit_ttm, total_assets, total_liabilities,
        net_assets, operating_cashflow, capex, revenue_ttm (all in yuan).
        Returns None on failure.
        """
        try:
            import akshare as ak

            # Use akshare stock_financial_abstract for TTM data
            df = ak.stock_financial_abstract(symbol=code)
            if df is None or df.empty:
                return None

            # Map column names - akshare returns Chinese column names
            # Try to get the most recent annual/TTM record
            row = df.iloc[0].to_dict()

            # Build a unified mapping from various possible akshare column names
            def _get_val(d: dict, *keys) -> float:
                for k in keys:
                    v = d.get(k)
                    if v is not None and str(v).strip() not in ('', 'nan', 'None', '--'):
                        try:
                            return float(v)
                        except (ValueError, TypeError):
                            continue
                return 0.0

            return {
                'net_profit_ttm': _get_val(row, 'net_profit', '净利润', 'netprofit'),
                'total_assets': _get_val(row, 'total_assets', '总资产', 'totalassets'),
                'total_liabilities': _get_val(row, 'total_liab', '总负债', 'totalliab'),
                'net_assets': _get_val(row, 'total_hldr_eqy_inc_min_int', '净资产', 'netassets'),
                'operating_cashflow': _get_val(row, 'n_cashflow_act', '经营现金流', 'operatingcashflow'),
                'capex': _get_val(row, 'c_pay_acq_const_fiolta', '资本支出', 'capex'),
                'revenue_ttm': _get_val(row, 'total_revenue', '营业收入', 'revenue'),
            }
        except Exception as exc:
            logger.warning("[_get_financial_data] %s: %s", code, exc)
            return None

    def _get_pe_series(self, code: str) -> Optional[pd.Series]:
        """Fetch 5-year historical PE series from DB.

        Returns pd.Series of PE values or None on failure.
        """
        try:
            from config.db import execute_query  # lazy import
            ts_code = _to_tushare(code)
            sql = """
                SELECT pe_ttm
                FROM trade_daily_basic
                WHERE ts_code = %s
                  AND pe_ttm > 0
                  AND trade_date >= DATE_SUB(CURDATE(), INTERVAL 5 YEAR)
                ORDER BY trade_date ASC
            """
            rows = execute_query(sql, (ts_code,))
            if not rows:
                return None
            values = [float(r[0]) for r in rows if r[0] is not None]
            return pd.Series(values) if values else None
        except Exception as exc:
            logger.warning("[_get_pe_series] %s: %s", code, exc)
            return None

    def _get_pb_series(self, code: str) -> Optional[pd.Series]:
        """Fetch 5-year historical PB series from DB.

        Returns pd.Series of PB values or None on failure.
        """
        try:
            from config.db import execute_query  # lazy import
            ts_code = _to_tushare(code)
            sql = """
                SELECT pb
                FROM trade_daily_basic
                WHERE ts_code = %s
                  AND pb > 0
                  AND trade_date >= DATE_SUB(CURDATE(), INTERVAL 5 YEAR)
                ORDER BY trade_date ASC
            """
            rows = execute_query(sql, (ts_code,))
            if not rows:
                return None
            values = [float(r[0]) for r in rows if r[0] is not None]
            return pd.Series(values) if values else None
        except Exception as exc:
            logger.warning("[_get_pb_series] %s: %s", code, exc)
            return None
