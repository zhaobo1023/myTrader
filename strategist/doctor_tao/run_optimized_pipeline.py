# -*- coding: utf-8 -*-
"""
优化版本：分批获取数据 + 筛选 + 回测
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from data_fetcher import DoctorTaoDataFetcher
from indicators import IndicatorCalculator
from signal_screener import ScreenerParams
import pandas as pd
from datetime import datetime

print("=" * 80)
print("陶博士策略 - 优化版完整流程")
print("=" * 80)

# Step 1: 分批获取数据
print("\n[Step 1] 分批获取全量数据...")

fetcher = DoctorTaoDataFetcher(use_cache=True)

# 获取股票列表
all_stocks = fetcher.fetch_all_stocks()
print(f"总股票数: {len(all_stocks)}")

# 分批处理（每批500只）
batch_size = 500
all_indicators = []

for i in range(0, min(len(all_stocks), 1000), batch_size):  # 先处理前1000只
    batch_stocks = all_stocks[i:i+batch_size]
    print(f"\n处理第 {i//batch_size + 1} 批: {len(batch_stocks)} 只股票...")

    try:
        # 批量获取价格数据
        price_dict = fetcher.fetch_daily_price_batch(
            batch_stocks,
            start_date='2023-01-01'
        )

        # 转换为DataFrame
        price_list = []
        for code, df in price_dict.items():
            if len(df) > 0:
                df['stock_code'] = code
                price_list.append(df)

        if not price_list:
            continue

        price_df = pd.concat(price_list, ignore_index=True)

        # 计算指标
        indicators_df = IndicatorCalculator.calc_all_indicators(price_df)
        all_indicators.append(indicators_df)

        print(f"  完成，累计指标数据: {sum(len(df) for df in all_indicators)} 条")

    except Exception as e:
        print(f"  批次失败: {e}")
        continue

if not all_indicators:
    print("\n无法获取有效数据")
    sys.exit(1)

# 合并所有指标
print("\n合并所有指标数据...")
full_indicators_df = pd.concat(all_indicators, ignore_index=True)
print(f"总指标数据: {len(full_indicators_df)} 条")

# Step 2: 信号筛选
print("\n[Step 2] 信号筛选...")

# 获取最新日期的数据
latest_date = full_indicators_df['trade_date'].max()
latest_df = full_indicators_df[full_indicators_df['trade_date'] == latest_date].copy()

print(f"最新日期: {latest_date}")
print(f"有效股票数: {len(latest_df)}")

# 动量筛选
momentum_mask = (
    (latest_df['rps'] >= 90) &
    (latest_df['ma20'] > latest_df['ma60']) &
    (latest_df['momentum_slope'] > 0)
)
momentum_df = latest_df[momentum_mask].copy()
momentum_df['signal_type'] = 'momentum'

print(f"\n动量信号: {len(momentum_df)} 只")

# 反转筛选
reversal_mask = (
    (latest_df['rps'] >= 80) &
    (latest_df['price_percentile'] < 30)
)
reversal_df = latest_df[reversal_mask].copy()
reversal_df['signal_type'] = 'reversal'

print(f"反转候选: {len(reversal_df)} 只")

# 合并信号
if len(momentum_df) > 0 or len(reversal_df) > 0:
    signals_list = []
    if len(momentum_df) > 0:
        signals_list.append(momentum_df)
    if len(reversal_df) > 0:
        signals_list.append(reversal_df)

    signals_df = pd.concat(signals_list, ignore_index=True)

    # 保存结果
    output_dir = os.path.join(os.path.dirname(__file__), 'output')
    os.makedirs(output_dir, exist_ok=True)

    signal_file = os.path.join(output_dir, f"signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    signals_df.to_csv(signal_file, index=False, encoding='utf-8-sig')
    print(f"\n信号已保存: {signal_file}")

    # 显示前10只股票
    print("\n前10只股票:")
    print(signals_df[['stock_code', 'trade_date', 'signal_type', 'rps', 'close']].head(10))

else:
    print("\n未筛选出符合条件的股票")

print("\n" + "=" * 80)
print("✓ 完整流程执行完毕！")
print("=" * 80)
