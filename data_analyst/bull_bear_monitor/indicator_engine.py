# -*- coding: utf-8 -*-
"""牛熊三指标计算引擎"""
import logging
import pandas as pd
import numpy as np
from .config import BullBearConfig

logger = logging.getLogger(__name__)


class IndicatorEngine:
    def __init__(self, config: BullBearConfig = None):
        self.config = config or BullBearConfig()

    def compute_bond_signal(self, bond_df: pd.DataFrame) -> pd.DataFrame:
        """
        10Y国债收益率信号
        - MA20 < MA60 且 value < 2.5% => bullish (+1) for stocks (low rates good for equity)
        - MA20 > MA60 且 value > 3.0% => bearish (-1)
        - else => neutral (0)
        """
        if bond_df.empty:
            return pd.DataFrame()

        df = bond_df.copy()
        df['ma20'] = df['value'].rolling(window=self.config.ma_short, min_periods=self.config.ma_short).mean()
        df['ma60'] = df['value'].rolling(window=self.config.ma_long, min_periods=self.config.ma_long).mean()

        df['trend'] = 'FLAT'
        df.loc[df['ma20'] < df['ma60'], 'trend'] = 'DOWN'
        df.loc[df['ma20'] > df['ma60'], 'trend'] = 'UP'

        df['signal'] = 0
        # Bond yield down + low level = bullish for stocks
        df.loc[(df['trend'] == 'DOWN') & (df['value'] < self.config.bond_bull_threshold), 'signal'] = 1
        # Bond yield up + high level = bearish for stocks
        df.loc[(df['trend'] == 'UP') & (df['value'] > self.config.bond_bear_threshold), 'signal'] = -1

        return df[['value', 'ma20', 'trend', 'signal']].rename(columns={
            'value': 'cn_10y_value', 'ma20': 'cn_10y_ma20',
            'trend': 'cn_10y_trend', 'signal': 'cn_10y_signal'
        })

    def compute_usdcny_signal(self, usdcny_df: pd.DataFrame) -> pd.DataFrame:
        """
        USDCNY信号
        - MA20 < MA60 (人民币升值) => bullish (+1)
        - MA20 > MA60 且 20d涨幅 > 1% => bearish (-1)
        - else => neutral (0)
        """
        if usdcny_df.empty:
            return pd.DataFrame()

        df = usdcny_df.copy()
        df['ma20'] = df['value'].rolling(window=self.config.ma_short, min_periods=self.config.ma_short).mean()
        df['ma60'] = df['value'].rolling(window=self.config.ma_long, min_periods=self.config.ma_long).mean()

        # 20d change
        df['pct_20d'] = df['value'].pct_change(periods=20)

        df['trend'] = 'FLAT'
        df.loc[df['ma20'] < df['ma60'], 'trend'] = 'DOWN'  # RMB appreciating
        df.loc[df['ma20'] > df['ma60'], 'trend'] = 'UP'    # RMB depreciating

        df['signal'] = 0
        # RMB appreciating = bullish
        df.loc[df['trend'] == 'DOWN', 'signal'] = 1
        # RMB depreciating with momentum = bearish
        df.loc[(df['trend'] == 'UP') & (df['pct_20d'] > self.config.usdcny_rise_pct), 'signal'] = -1

        return df[['value', 'ma20', 'trend', 'signal']].rename(columns={
            'value': 'usdcny_value', 'ma20': 'usdcny_ma20',
            'trend': 'usdcny_trend', 'signal': 'usdcny_signal'
        })

    def compute_dividend_signal(self, dividend_df: pd.DataFrame, csi300_df: pd.DataFrame) -> pd.DataFrame:
        """
        红利相对收益信号 (dividend / csi300 ratio)
        - Relative ratio MA20 < MA60 (红利跑输, risk-on) => bullish (+1)
        - Relative ratio MA20 > MA60 (红利跑赢, risk-off) => bearish (-1)
        - else => neutral (0)
        """
        if dividend_df.empty or csi300_df.empty:
            return pd.DataFrame()

        # Align dates
        merged = dividend_df[['value']].join(
            csi300_df[['value']], lsuffix='_div', rsuffix='_csi', how='inner'
        )

        if merged.empty:
            return pd.DataFrame()

        # Compute relative ratio
        merged['relative'] = merged['value_div'] / merged['value_csi']
        merged['rel_ma20'] = merged['relative'].rolling(window=self.config.ma_short, min_periods=self.config.ma_short).mean()
        merged['rel_ma60'] = merged['relative'].rolling(window=self.config.ma_long, min_periods=self.config.ma_long).mean()

        merged['trend'] = 'FLAT'
        merged.loc[merged['rel_ma20'] < merged['rel_ma60'], 'trend'] = 'DOWN'  # Dividend underperforming = risk-on
        merged.loc[merged['rel_ma20'] > merged['rel_ma60'], 'trend'] = 'UP'    # Dividend outperforming = risk-off

        merged['signal'] = 0
        merged.loc[merged['trend'] == 'DOWN', 'signal'] = 1   # risk-on = bullish
        merged.loc[merged['trend'] == 'UP', 'signal'] = -1    # risk-off = bearish

        result = merged[['relative', 'rel_ma20', 'trend', 'signal']].rename(columns={
            'relative': 'dividend_relative', 'rel_ma20': 'dividend_rel_ma20',
            'trend': 'dividend_trend', 'signal': 'dividend_signal'
        })
        return result
