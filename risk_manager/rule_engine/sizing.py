# -*- coding: utf-8 -*-
"""
ATR 仓位计算（海龟法则）
"""
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .atr import calc_atr
from .config import RiskConfig


@dataclass
class ATRSizingResult:
    """ATR 仓位计算结果"""
    shares: float
    stop_price: float
    stop_distance: float
    risk_amount: float
    position_value: float


def calc_atr_position(
    price: float,
    portfolio_value: float,
    ohlcv_df: pd.DataFrame,
    config: RiskConfig,
) -> Optional[ATRSizingResult]:
    """
    基于 ATR 计算仓位大小（海龟法则）

    公式:
        risk_amount = portfolio_value * atr_risk_per_trade
        stop_distance = ATR * atr_multiplier
        shares = risk_amount / stop_distance
        stop_price = price - stop_distance

    Args:
        price: 入场价格
        portfolio_value: 组合总价值
        ohlcv_df: OHLCV 历史数据
        config: 风控配置

    Returns:
        ATRSizingResult 或 None（数据不足时）
    """
    if ohlcv_df is None or len(ohlcv_df) < config.atr_period:
        return None

    atr_series = calc_atr(ohlcv_df, config.atr_period)
    current_atr = atr_series.iloc[-1]

    if current_atr <= 0 or pd.isna(current_atr):
        return None

    risk_amount = portfolio_value * config.atr_risk_per_trade
    stop_distance = current_atr * config.atr_multiplier

    if stop_distance <= 0:
        return None

    shares = risk_amount / stop_distance
    stop_price = price - stop_distance
    position_value = shares * price

    # 不超过单只仓位上限
    max_value = portfolio_value * config.single_position_limit
    if position_value > max_value:
        shares = max_value / price
        position_value = shares * price

    return ATRSizingResult(
        shares=shares,
        stop_price=stop_price,
        stop_distance=stop_distance,
        risk_amount=risk_amount,
        position_value=position_value,
    )
