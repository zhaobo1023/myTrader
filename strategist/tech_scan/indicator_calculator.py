# -*- coding: utf-8 -*-
"""
技术指标计算器

计算 MA、MACD、RSI、KDJ、BOLL 等技术指标
"""
import pandas as pd
import numpy as np
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class IndicatorCalculator:
    """技术指标计算器"""
    
    def __init__(
        self,
        ma_windows: List[int] = [5, 20, 60, 250],
        rsi_period: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9
    ):
        self.ma_windows = ma_windows
        self.rsi_period = rsi_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
    
    def calculate_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算所有技术指标
        
        Args:
            df: 包含 stock_code, trade_date, open, high, low, close, volume 的 DataFrame
            
        Returns:
            添加了技术指标列的 DataFrame
        """
        if df.empty:
            return df
        
        df = df.copy()
        df = df.sort_values(['stock_code', 'trade_date'])
        
        # 按股票分组计算
        result_dfs = []
        for stock_code, group in df.groupby('stock_code'):
            group = group.copy()
            group = self._calc_indicators_for_stock(group)
            result_dfs.append(group)
        
        result = pd.concat(result_dfs, ignore_index=True)
        logger.info(f"技术指标计算完成: {len(result)} 条记录")
        return result
    
    def _calc_indicators_for_stock(self, df: pd.DataFrame) -> pd.DataFrame:
        """为单只股票计算所有指标"""
        close = df['close']
        volume = df['volume']
        
        # 1. 移动平均线
        for window in self.ma_windows:
            df[f'ma{window}'] = close.rolling(window=window, min_periods=window).mean()
        
        # 2. MACD
        ema_fast = close.ewm(span=self.macd_fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.macd_slow, adjust=False).mean()
        df['macd_dif'] = ema_fast - ema_slow
        df['macd_dea'] = df['macd_dif'].ewm(span=self.macd_signal, adjust=False).mean()
        df['macd_hist'] = (df['macd_dif'] - df['macd_dea']) * 2
        
        # 3. RSI
        df['rsi'] = self._calc_rsi(close, self.rsi_period)
        
        # 4. 成交量均线
        df['vol_ma5'] = volume.rolling(window=5, min_periods=1).mean()
        df['vol_ma20'] = volume.rolling(window=20, min_periods=1).mean()
        df['volume_ratio'] = volume / df['vol_ma5']
        
        # 5. 20日高点/低点
        df['high_20'] = df['high'].rolling(window=20, min_periods=1).max()
        df['low_20'] = df['low'].rolling(window=20, min_periods=1).min()
        
        # 6. 涨跌幅
        df['pct_change'] = close.pct_change() * 100
        
        # 7. 均线偏离度
        if 'ma20' in df.columns:
            df['ma20_bias'] = (close / df['ma20'] - 1) * 100
        if 'ma60' in df.columns:
            df['ma60_bias'] = (close / df['ma60'] - 1) * 100
        
        # 8. ATR (Average True Range) - 14日
        high = df['high']
        low = df['low']
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr_14'] = tr.rolling(window=14, min_periods=14).mean()

        # 9. 前一日数据（用于判断金叉/死叉）
        df['prev_close'] = prev_close
        df['prev_ma5'] = df['ma5'].shift(1)
        df['prev_ma20'] = df['ma20'].shift(1)
        df['prev_macd_dif'] = df['macd_dif'].shift(1)
        df['prev_macd_dea'] = df['macd_dea'].shift(1)
        df['prev_macd_hist'] = df['macd_hist'].shift(1)

        # 10. KDJ (9, 3, 3) - pandas EWM 实现，符合东方财富惯例
        kdj_n = 9
        low_n = df['low'].rolling(window=kdj_n, min_periods=kdj_n).min()
        high_n = df['high'].rolling(window=kdj_n, min_periods=kdj_n).max()
        rsv = (close - low_n) / (high_n - low_n) * 100
        df['kdj_k'] = rsv.ewm(com=2, adjust=False).mean()
        df['kdj_d'] = df['kdj_k'].ewm(com=2, adjust=False).mean()
        df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']
        df['prev_kdj_k'] = df['kdj_k'].shift(1)
        df['prev_kdj_d'] = df['kdj_d'].shift(1)

        # 11. BOLL (20, 2)
        boll_window = 20
        boll_std_mult = 2
        boll_middle = close.rolling(window=boll_window, min_periods=boll_window).mean()
        boll_std = close.rolling(window=boll_window, min_periods=boll_window).std()
        df['boll_upper'] = boll_middle + boll_std_mult * boll_std
        df['boll_middle'] = boll_middle
        df['boll_lower'] = boll_middle - boll_std_mult * boll_std
        df['boll_pctb'] = (close - df['boll_lower']) / (df['boll_upper'] - df['boll_lower'])
        df['boll_bandwidth'] = (df['boll_upper'] - df['boll_lower']) / df['boll_middle']

        return df
    
    def _calc_rsi(self, close: pd.Series, period: int = 14) -> pd.Series:
        """计算 RSI"""
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calc_rps(
        self, 
        df: pd.DataFrame, 
        window: int = 250
    ) -> pd.DataFrame:
        """
        计算 RPS（相对强度）
        
        注意：RPS 需要全市场数据作为基准，这里仅计算持仓股票之间的相对排名
        如果需要全市场 RPS，应从数据库读取预计算的值
        
        Args:
            df: 包含 stock_code, trade_date, close 的 DataFrame
            window: 计算周期（交易日）
            
        Returns:
            添加了 rps 列的 DataFrame
        """
        df = df.copy()
        df = df.sort_values(['stock_code', 'trade_date'])
        
        # 计算 N 日涨幅
        df['return_n'] = df.groupby('stock_code')['close'].transform(
            lambda x: x.pct_change(periods=window)
        )
        
        # 截面排名（百分位）
        df['rps'] = df.groupby('trade_date')['return_n'].transform(
            lambda x: x.rank(pct=True, na_option='keep') * 100
        )
        
        return df


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """便捷函数：计算技术指标"""
    calculator = IndicatorCalculator()
    return calculator.calculate_all(df)
