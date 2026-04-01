# -*- coding: utf-8 -*-
"""log bias calculator: (ln(close) - EMA(ln(close), 20)) * 100"""

import numpy as np
import pandas as pd


def calculate_log_bias(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """
    calculate log bias

    Args:
        df: must have 'close' column
        window: EMA span, default 20

    Returns:
        DataFrame with columns: [close, ln_close, ema_ln, log_bias]
    """
    out = df.copy()
    out['ln_close'] = np.log(out['close'])
    out['ema_ln'] = out['ln_close'].ewm(span=window, adjust=False).mean()
    out['log_bias'] = (out['ln_close'] - out['ema_ln']) * 100
    return out
