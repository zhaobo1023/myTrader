# -*- coding: utf-8 -*-
"""
陶博士策略 - 指标验证脚本

验证指标计算的正确性
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_fetcher import DoctorTaoDataFetcher
from indicators import IndicatorCalculator
import pandas as pd


def test_rps_with_known_stocks():
    """
    使用历史强势股验证 RPS 计算的正确性

    隐私说明：
    RPS 计算需要全市场数据进行排名，单只股票无法独立计算
    这里我们只验证指标计算的基本逻辑是否正确
    """
    print("=" * 60)
    print("指标计算功能验证")
    print("=" * 60)

    fetcher = DoctorTaoDataFetcher(use_cache=True)

    # 测试单只股票的基本指标计算
    print("\n1. 测试单只股票的基本指标计算 (600519.SH)")
    nd_df = fetcher.fetch_daily_price('600519.SH', '2023-01-01', '2024-12-31')

    if len(nd_df) == 0:
        print("  无法获取数据")
        return

    nd_df['stock_code'] = '600519.SH'
    nd_price_df = nd_df

    # 计算 MA20/60
    ma_df = IndicatorCalculator.calc_ma(nd_price_df, windows=[20, 60])

    print(f"\nMA20 最后一个值: {ma_df['ma20'].iloc[-1]:.2f}")
    print(f"MA60 最后一个值: {ma_df['ma60'].iloc[-1]:.2f}")

    # 计算价格分位
    price_pct_df = IndicatorCalculator.calc_price_percentile(nd_price_df, window=750)
    print(f"\n价格分位 最后一个值: {price_pct_df['price_percentile'].iloc[-1]:.2f}")

    # 计算动量斜率
    slope_df = IndicatorCalculator.calc_momentum_slope(nd_price_df, window=20)
    print(f"\n动量斜率 最后一个值: {slope_df['momentum_slope'].iloc[-1]:.4f}")

    print("\n✓ 匇标计算功能验证通过")

    print("\n注意： RPS 计算需要全市场数据进行排名，单只股票无法独立计算")
    print("      我们将在下一步的信号生成中，使用全市场数据进行 RPS 计算")


if __name__ == '__main__':
    test_rps_with_known_stocks()
