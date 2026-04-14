# -*- coding: utf-8 -*-
"""Industry rotation strategy adapter: wraps universe_scanner.ScoringEngine."""

import json
import logging
import os
import sys

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from strategist.sim_pool.strategies.base import BaseStrategyAdapter

logger = logging.getLogger('myTrader.sim_pool')


class IndustryAdapter(BaseStrategyAdapter):
    """
    Wraps universe_scanner.ScoringEngine.
    Filters by Shenwan industry name(s) and returns high-priority stocks.
    """

    def strategy_type(self) -> str:
        return 'industry'

    def run(self, signal_date: str, params: dict) -> pd.DataFrame:
        """
        params:
            industry_names: List[str]  Shenwan L1 industry names, e.g. ['银行', '电力设备']
                            Empty = no industry filter (returns all high_priority)
            max_results: int (default: 20)
        """
        from strategist.universe_scanner.scoring_engine import ScoringEngine

        industry_names = params.get('industry_names', [])
        max_results = int(params.get('max_results', 20))

        engine = ScoringEngine()
        try:
            results = engine.run(date=signal_date)
        except Exception as e:
            logger.error('[IndustryAdapter] ScoringEngine failed: %s', e)
            return pd.DataFrame(columns=['stock_code', 'stock_name'])

        if results is None or (hasattr(results, 'empty') and results.empty):
            return pd.DataFrame(columns=['stock_code', 'stock_name'])

        # Normalise to DataFrame
        if not isinstance(results, pd.DataFrame):
            try:
                results = pd.DataFrame([vars(r) if hasattr(r, '__dict__') else r
                                        for r in results])
            except Exception:
                return pd.DataFrame(columns=['stock_code', 'stock_name'])

        # Filter high_priority tier
        if 'tier' in results.columns:
            results = results[results['tier'] == 'high_priority']

        # Filter by industry
        if industry_names and 'industry' in results.columns:
            results = results[results['industry'].isin(industry_names)]

        if results.empty:
            logger.info('[IndustryAdapter] no results after filters on %s', signal_date)
            return pd.DataFrame(columns=['stock_code', 'stock_name'])

        # Sort by score
        if 'total_score' in results.columns:
            results = results.sort_values('total_score', ascending=False)

        results = results.head(max_results).copy()

        meta_cols = [c for c in ['industry', 'total_score', 'rps_120', 'rps_250',
                                   'close', 'trend', 'signals']
                     if c in results.columns]

        def _build_meta(row):
            return json.dumps({c: row.get(c) for c in meta_cols}, ensure_ascii=False, default=str)

        code_col = 'code' if 'code' in results.columns else 'stock_code'
        name_col = 'name' if 'name' in results.columns else 'stock_name'

        out = pd.DataFrame({
            'stock_code': results[code_col],
            'stock_name': results.get(name_col, results[code_col]),
            'signal_meta': results.apply(_build_meta, axis=1),
        })
        return out.reset_index(drop=True)
