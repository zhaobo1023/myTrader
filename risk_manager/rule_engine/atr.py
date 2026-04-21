# -*- coding: utf-8 -*-
"""
独立 ATR 计算（不依赖 TA-Lib）
"""
import pandas as pd


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算 ATR（Average True Range）

    Args:
        df: OHLCV DataFrame，需要包含 high, low, close 列
        period: ATR 周期，默认 14

    Returns:
        ATR Series
    """
    high = df['high']
    low = df['low']
    close = df['close']

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = true_range.ewm(span=period, adjust=False).mean()
    return atr
