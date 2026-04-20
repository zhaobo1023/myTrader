# -*- coding: utf-8 -*-
"""牛熊状态综合判断"""
import logging
import pandas as pd
from typing import List
from .config import BullBearConfig
from .schemas import BullBearSignal

logger = logging.getLogger(__name__)


class RegimeJudge:
    def __init__(self, config: BullBearConfig = None):
        self.config = config or BullBearConfig()

    def judge(self, bond_df: pd.DataFrame, usdcny_df: pd.DataFrame,
              dividend_df: pd.DataFrame, start_date: str = None) -> List[BullBearSignal]:
        """
        Merge 3 indicator signals and determine regime for each date.

        Returns list of BullBearSignal for dates where all 3 signals are available.
        """
        # Merge on date index
        merged = bond_df.join(usdcny_df, how='outer').join(dividend_df, how='outer')

        # Only keep dates where at least bond+usdcny available
        merged = merged.dropna(subset=['cn_10y_signal', 'usdcny_signal'])

        # Fill dividend signal with 0 if missing
        merged['dividend_signal'] = merged['dividend_signal'].fillna(0)

        # Filter by start_date if provided
        if start_date:
            merged = merged[merged.index >= pd.Timestamp(start_date)]

        if merged.empty:
            return []

        # Compute composite score
        merged['composite_score'] = (
            merged['cn_10y_signal'].astype(int) +
            merged['usdcny_signal'].astype(int) +
            merged['dividend_signal'].astype(int)
        )

        # Determine regime
        merged['regime'] = 'NEUTRAL'
        merged.loc[merged['composite_score'] >= self.config.bull_threshold, 'regime'] = 'BULL'
        merged.loc[merged['composite_score'] <= self.config.bear_threshold, 'regime'] = 'BEAR'

        # Build result list
        signals = []
        for dt, row in merged.iterrows():
            calc_date = dt.date() if hasattr(dt, 'date') else dt
            signal = BullBearSignal(
                calc_date=calc_date,
                cn_10y_value=float(row['cn_10y_value']) if pd.notna(row.get('cn_10y_value')) else None,
                cn_10y_ma20=float(row['cn_10y_ma20']) if pd.notna(row.get('cn_10y_ma20')) else None,
                cn_10y_trend=row.get('cn_10y_trend') if pd.notna(row.get('cn_10y_trend')) else None,
                cn_10y_signal=int(row['cn_10y_signal']),
                usdcny_value=float(row['usdcny_value']) if pd.notna(row.get('usdcny_value')) else None,
                usdcny_ma20=float(row['usdcny_ma20']) if pd.notna(row.get('usdcny_ma20')) else None,
                usdcny_trend=row.get('usdcny_trend') if pd.notna(row.get('usdcny_trend')) else None,
                usdcny_signal=int(row['usdcny_signal']),
                dividend_relative=float(row['dividend_relative']) if pd.notna(row.get('dividend_relative')) else None,
                dividend_rel_ma20=float(row['dividend_rel_ma20']) if pd.notna(row.get('dividend_rel_ma20')) else None,
                dividend_trend=row.get('dividend_trend') if pd.notna(row.get('dividend_trend')) else None,
                dividend_signal=int(row['dividend_signal']),
                composite_score=int(row['composite_score']),
                regime=row['regime'],
            )
            signals.append(signal)

        logger.info(f"Generated {len(signals)} bull/bear signals")
        regime_counts = merged['regime'].value_counts().to_dict()
        logger.info(f"Regime distribution: {regime_counts}")

        return signals
