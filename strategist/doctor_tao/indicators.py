# -*- coding: utf-8 -*-
"""
陶博士策略 - 核心指标计算

实现指标：
1. RPS (Relative Price Strength) - 截面排名分位（250日涨幅全市场排名）
2. MA20/60/250 - 移动平均线
3. 价格分位 - 纵向历史价格分位（750日）
4. RPS动量斜率 - RPS的周度线性回归斜率Z-Score
5. 成交量比 - 近4周均量 vs 52周均量
6. 60日涨幅排名 - 截面排名分位
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional
from datetime import datetime
from scipy import stats


class IndicatorCalculator:
    """指标计算器"""

    def __init__(self):
        pass

    @staticmethod
    def calc_rps(price_df: pd.DataFrame, window: int = 250) -> pd.DataFrame:
        """
        计算 RPS (Relative Price Strength) - 截面排名分位
        
        RPS = 过去 window 个交易日涨幅，在当日全市场A股中的排名百分位（0～100）
        """
        print(f"计算 RPS (window={window})...")

        price_df = price_df.copy()
        price_df = price_df.sort_values(['stock_code', 'trade_date'])

        # 正确计算 window 日涨幅（直接用 pct_change(periods=window)）
        price_df['rolling_return'] = price_df.groupby('stock_code')['close'].transform(
            lambda x: x.pct_change(periods=window)
        )

        # 每个交易日对所有股票的滚动收益率进行截面排名
        # 使用向量化方式提升效率
        price_df['rps'] = price_df.groupby('trade_date')['rolling_return'].transform(
            lambda x: x.rank(pct=True, na_option='keep') * 100
        )

        result = price_df[['stock_code', 'trade_date', 'rps']].copy()
        result = result.sort_values(['stock_code', 'trade_date'])
        result = result.reset_index(drop=True)

        print(f"  RPS 计算完成，共 {len(result)} 条记录")

        return result

    @staticmethod
    def calc_ma(price_df: pd.DataFrame, windows: list = [20, 50, 60, 120, 250]) -> pd.DataFrame:
        """
        计算移动平均线 MA20, MA50, MA60, MA120, MA250
        
        MA50/MA120 用于大盘条件判断
        MA250 用于动量筛选（股价站上年线）
        """
        print(f"计算 MA {windows}...")

        price_df = price_df.copy()
        price_df = price_df.sort_values(['stock_code', 'trade_date'])

        result = price_df[['stock_code', 'trade_date', 'close']].copy()

        for window in windows:
            col_name = f'ma{window}'
            result[col_name] = result.groupby('stock_code')['close'].transform(
                lambda x: x.rolling(window=window, min_periods=1).mean()
            )

        print(f"  MA 计算完成")
        return result

    @staticmethod
    def calc_price_percentile(price_df: pd.DataFrame, window: int = 750) -> pd.DataFrame:
        """
        计算价格分位 - 纵向历史价格分位
        
        过去 N 年（默认 3 年/750 日）收盘价的历史百分位
        - < 30%：历史低位，可能是反转候选
        - > 70%：历史高位，动量区间
        """
        print(f"计算价格分位 (window={window})...")

        price_df = price_df.copy()
        price_df = price_df.sort_values(['stock_code', 'trade_date'])

        # 使用向量化方式计算，提升效率
        def rolling_percentile(x):
            """计算当前值在滚动窗口中的百分位"""
            if len(x) < 2:
                return np.nan
            current = x.iloc[-1]
            historical = x.iloc[:-1]
            return (historical <= current).sum() / len(historical) * 100

        price_df['price_percentile'] = price_df.groupby('stock_code')['close'].transform(
            lambda x: x.rolling(window=window, min_periods=20).apply(rolling_percentile, raw=False)
        )

        result = price_df[['stock_code', 'trade_date', 'price_percentile']].copy()
        result = result.sort_values(['stock_code', 'trade_date'])
        result = result.reset_index(drop=True)

        print(f"  价格分位计算完成，共 {len(result)} 条记录")
        return result

    @staticmethod
    def calc_rps_slope(rps_df: pd.DataFrame, window: int = 4) -> pd.DataFrame:
        """
        计算 RPS 动量斜率 Z-Score
        
        近 4～8 周 RPS 变化的线性斜率，标准化为 Z-Score
        - Z > 1.5：RPS 快速拉升，趋势启动信号
        - Z < -1.5：RPS 快速下滑，退出信号
        
        Args:
            rps_df: 包含 stock_code, trade_date, rps 的 DataFrame
            window: 周数（默认4周，约20个交易日）
        """
        print(f"计算 RPS 动量斜率 (window={window}周)...")

        rps_df = rps_df.copy()
        rps_df = rps_df.sort_values(['stock_code', 'trade_date'])
        
        # 转换为周频数据（每5个交易日取一个）
        days_per_week = 5
        actual_window = window * days_per_week

        def calc_slope_zscore(x):
            """计算斜率并返回Z-Score"""
            if len(x) < actual_window or x.isna().any():
                return np.nan
            
            y = x.values
            x_vals = np.arange(len(y))
            
            if np.std(y) == 0:
                return 0.0
            
            try:
                slope, _, _, _, _ = stats.linregress(x_vals, y)
                return slope
            except:
                return np.nan

        # 计算每只股票的 RPS 斜率
        rps_df['rps_slope_raw'] = rps_df.groupby('stock_code')['rps'].transform(
            lambda x: x.rolling(window=actual_window, min_periods=actual_window).apply(calc_slope_zscore, raw=False)
        )

        # 对每个交易日的斜率进行 Z-Score 标准化
        rps_df['rps_slope'] = rps_df.groupby('trade_date')['rps_slope_raw'].transform(
            lambda x: (x - x.mean()) / x.std() if x.std() > 0 else 0
        )

        result = rps_df[['stock_code', 'trade_date', 'rps_slope']].copy()
        result = result.sort_values(['stock_code', 'trade_date'])
        result = result.reset_index(drop=True)

        print(f"  RPS 动量斜率计算完成，共 {len(result)} 条记录")
        return result

    @staticmethod
    def calc_return_rank(price_df: pd.DataFrame, window: int = 60) -> pd.DataFrame:
        """
        计算 N 日涨幅的截面排名分位
        
        用于动量筛选：近60日涨幅排名前30%
        """
        print(f"计算 {window} 日涨幅排名...")

        price_df = price_df.copy()
        price_df = price_df.sort_values(['stock_code', 'trade_date'])

        # 计算 N 日涨幅
        price_df['return_n'] = price_df.groupby('stock_code')['close'].transform(
            lambda x: x.pct_change(periods=window)
        )

        # 截面排名（百分位）
        col_name = f'return_{window}d_rank'
        price_df[col_name] = price_df.groupby('trade_date')['return_n'].transform(
            lambda x: x.rank(pct=True, na_option='keep') * 100
        )

        result = price_df[['stock_code', 'trade_date', col_name]].copy()
        result = result.sort_values(['stock_code', 'trade_date'])
        result = result.reset_index(drop=True)

        print(f"  {window}日涨幅排名计算完成，共 {len(result)} 条记录")
        return result

    @staticmethod
    def calc_volume_ratio(price_df: pd.DataFrame, short_window: int = 20, long_window: int = 250) -> pd.DataFrame:
        """
        计算成交量比
        
        近4周均量 vs 52周均量的比值
        - 动量筛选：比值 > 1.2（资金关注度提升）
        - 反转候选：比值 > 1.5（底部放量）
        """
        print(f"计算成交量比 ({short_window}日 vs {long_window}日)...")

        price_df = price_df.copy()
        price_df = price_df.sort_values(['stock_code', 'trade_date'])

        # 计算短期均量
        price_df['vol_short'] = price_df.groupby('stock_code')['volume'].transform(
            lambda x: x.rolling(window=short_window, min_periods=1).mean()
        )

        # 计算长期均量
        price_df['vol_long'] = price_df.groupby('stock_code')['volume'].transform(
            lambda x: x.rolling(window=long_window, min_periods=20).mean()
        )

        # 计算比值
        price_df['volume_ratio'] = price_df['vol_short'] / price_df['vol_long']
        price_df['volume_ratio'] = price_df['volume_ratio'].replace([np.inf, -np.inf], np.nan)

        result = price_df[['stock_code', 'trade_date', 'volume_ratio']].copy()
        result = result.sort_values(['stock_code', 'trade_date'])
        result = result.reset_index(drop=True)

        print(f"  成交量比计算完成，共 {len(result)} 条记录")
        return result

    @staticmethod
    def calc_all_indicators(price_df: pd.DataFrame) -> pd.DataFrame:
        """
        计算所有指标
        
        返回的 DataFrame 包含：
        - rps: 250日涨幅截面排名分位
        - ma20, ma50, ma60, ma120, ma250: 移动平均线
        - price_percentile: 750日历史价格分位
        - rps_slope: RPS动量斜率Z-Score
        - return_60d_rank: 60日涨幅截面排名分位
        - volume_ratio: 成交量比（20日均量/250日均量）
        """
        print("=" * 60)
        print("开始计算所有指标...")
        print("=" * 60)

        # 确保数据排序
        price_df = price_df.copy()
        price_df = price_df.sort_values(['stock_code', 'trade_date'])

        # 1. RPS（250日涨幅截面排名）
        rps_df = IndicatorCalculator.calc_rps(price_df, window=250)

        # 2. MA20/50/60/120/250
        ma_df = IndicatorCalculator.calc_ma(price_df, windows=[20, 50, 60, 120, 250])

        # 3. 价格分位（750日历史分位）
        price_pct_df = IndicatorCalculator.calc_price_percentile(price_df, window=750)

        # 4. RPS动量斜率（4周Z-Score）
        rps_slope_df = IndicatorCalculator.calc_rps_slope(rps_df, window=4)

        # 5. 60日涨幅排名
        return_rank_df = IndicatorCalculator.calc_return_rank(price_df, window=60)

        # 6. 成交量比（20日均量 vs 250日均量）
        volume_ratio_df = IndicatorCalculator.calc_volume_ratio(price_df, short_window=20, long_window=250)

        # 合并所有指标
        print("\n合并所有指标...")
        result = price_df[['stock_code', 'trade_date', 'close']].copy()

        # 合并 RPS
        result = result.merge(
            rps_df[['stock_code', 'trade_date', 'rps']],
            on=['stock_code', 'trade_date'],
            how='left'
        )

        # 合并 MA
        result = result.merge(
            ma_df[['stock_code', 'trade_date', 'ma20', 'ma50', 'ma60', 'ma120', 'ma250']],
            on=['stock_code', 'trade_date'],
            how='left'
        )

        # 合并价格分位
        result = result.merge(
            price_pct_df[['stock_code', 'trade_date', 'price_percentile']],
            on=['stock_code', 'trade_date'],
            how='left'
        )

        # 合并 RPS 动量斜率
        result = result.merge(
            rps_slope_df[['stock_code', 'trade_date', 'rps_slope']],
            on=['stock_code', 'trade_date'],
            how='left'
        )

        # 合并 60日涨幅排名
        result = result.merge(
            return_rank_df[['stock_code', 'trade_date', 'return_60d_rank']],
            on=['stock_code', 'trade_date'],
            how='left'
        )

        # 合并成交量比
        result = result.merge(
            volume_ratio_df[['stock_code', 'trade_date', 'volume_ratio']],
            on=['stock_code', 'trade_date'],
            how='left'
        )

        print("\n" + "=" * 60)
        print("所有指标计算完成！")
        print(f"共 {len(result)} 条记录")
        print("=" * 60)

        return result
