# -*- coding: utf-8 -*-
"""Momentum strategy adapter: wraps doctor_tao.SignalScreener."""

import json
import logging
import os
import sys
from typing import Optional

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from strategist.sim_pool.strategies.base import BaseStrategyAdapter

logger = logging.getLogger('myTrader.sim_pool')


class MomentumAdapter(BaseStrategyAdapter):
    """Wraps doctor_tao.SignalScreener for momentum/reversal signals."""

    def strategy_type(self) -> str:
        return 'momentum'

    def run(self, signal_date: str, params: dict) -> pd.DataFrame:
        """
        params:
            signal_type: 'momentum' | 'reversal' | 'all'  (default: 'all')
            max_results: int (default: 20)
        """
        from strategist.doctor_tao.signal_screener import SignalScreener

        signal_type_filter = params.get('signal_type', 'all')

        screener = SignalScreener()
        try:
            signals = screener.run_screener(date=signal_date, output_csv=False)
        except Exception as e:
            logger.error('[MomentumAdapter] SignalScreener failed: %s', e)
            return pd.DataFrame(columns=['stock_code', 'stock_name'])

        if signals is None or signals.empty:
            logger.info('[MomentumAdapter] no signals on %s', signal_date)
            return pd.DataFrame(columns=['stock_code', 'stock_name'])

        # Filter by signal_type
        if signal_type_filter != 'all' and 'signal_type' in signals.columns:
            signals = signals[signals['signal_type'] == signal_type_filter]

        if signals.empty:
            return pd.DataFrame(columns=['stock_code', 'stock_name'])

        max_results = int(params.get('max_results', 20))
        signals = signals.head(max_results).copy()

        # Build signal_meta from available columns
        meta_cols = [c for c in ['signal_type', 'rps', 'ma20', 'ma60', 'ma250',
                                   'volume_ratio', 'price_percentile', 'rps_slope',
                                   'return_60d_rank', 'market_status']
                     if c in signals.columns]

        def _build_meta(row):
            return json.dumps({c: row.get(c) for c in meta_cols}, ensure_ascii=False, default=str)

        result = pd.DataFrame({
            'stock_code': signals['stock_code'],
            'stock_name': signals.get('stock_name', signals['stock_code']),
            'signal_meta': signals.apply(_build_meta, axis=1),
        })
        return result.reset_index(drop=True)
