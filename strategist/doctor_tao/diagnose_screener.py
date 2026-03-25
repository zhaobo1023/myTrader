# -*- coding: utf-8 -*-
"""
诊断版本：详细日志输出，定位筛选问题
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from data_fetcher import DoctorTaoDataFetcher
from indicators import IndicatorCalculator
import pandas as pd
import numpy as np

print("=" * 80)
print("陶博士策略 - 诊断版（详细日志）")
print("=" * 80)

# Step 1: 获取测试数据
print("\n[Step 1] 获取测试数据...")
fetcher = DoctorTaoDataFetcher(use_cache=True)

# 获取股票列表
all_stocks = fetcher.fetch_all_stocks()
print(f"总股票数: {len(all_stocks)}")

# 只取前100只测试
test_stocks = all_stocks[:100]
print(f"测试股票数: {len(test_stocks)}")

# 获取价格数据
print("\n[Step 2] 获取价格数据...")
price_dict = fetcher.fetch_daily_price_batch(
    test_stocks,
    start_date='2023-01-01'
)

# 转换为DataFrame
price_list = []
for code, df in price_dict.items():
    if len(df) > 0:
        df['stock_code'] = code
        price_list.append(df)

if not price_list:
    print("❌ 无有效价格数据")
    sys.exit(1)

price_df = pd.concat(price_list, ignore_index=True)
print(f"✓ 获取到 {len(price_df)} 条价格数据")
print(f"  日期范围: {price_df['trade_date'].min()} ~ {price_df['trade_date'].max()}")
print(f"  股票数量: {price_df['stock_code'].nunique()}")

# Step 2: 计算指标
print("\n[Step 3] 计算指标...")
indicators_df = IndicatorCalculator.calc_all_indicators(price_df)

# 获取最新日期的数据
latest_date = indicators_df['trade_date'].max()
latest_df = indicators_df[indicators_df['trade_date'] == latest_date].copy()

print(f"\n最新日期: {latest_date}")
print(f"有效股票数: {len(latest_df)}")

# Step 3: 详细诊断每个指标
print("\n" + "=" * 80)
print("指标诊断")
print("=" * 80)

# 3.1 RPS 诊断
print("\n[诊断1] RPS 指标:")
print(f"  总记录数: {len(latest_df)}")
print(f"  RPS 非空值: {latest_df['rps'].notna().sum()}")
print(f"  RPS 统计:")
if latest_df['rps'].notna().sum() > 0:
    rps_stats = latest_df['rps'].describe()
    print(f"    均值: {rps_stats['mean']:.2f}")
    print(f"    中位数: {rps_stats['50%']:.2f}")
    print(f"    最大值: {rps_stats['max']:.2f}")
    print(f"    最小值: {rps_stats['min']:.2f}")
    print(f"    ≥90的股票数: {(latest_df['rps'] >= 90).sum()}")
    print(f"    ≥80的股票数: {(latest_df['rps'] >= 80).sum()}")
else:
    print("    ⚠️ 所有RPS值为空！")

# 3.2 MA 诊断
print("\n[诊断2] MA20/60 指标:")
print(f"  MA20 非空值: {latest_df['ma20'].notna().sum()}")
print(f"  MA60 非空值: {latest_df['ma60'].notna().sum()}")
if latest_df['ma20'].notna().sum() > 0 and latest_df['ma60'].notna().sum() > 0:
    ma20_above_ma60 = (latest_df['ma20'] > latest_df['ma60']).sum()
    print(f"  MA20 > MA60 的股票数: {ma20_above_ma60}")
    print(f"  比例: {ma20_above_ma60 / len(latest_df) * 100:.1f}%")
else:
    print("    ⚠️ MA值为空！")

# 3.3 动量斜率 诊断
print("\n[诊断3] 动量斜率指标:")
print(f"  动量斜率 非空值: {latest_df['momentum_slope'].notna().sum()}")
if latest_df['momentum_slope'].notna().sum() > 0:
    slope_stats = latest_df['momentum_slope'].describe()
    print(f"  统计:")
    print(f"    均值: {slope_stats['mean']:.4f}")
    print(f"    中位数: {slope_stats['50%']:.4f}")
    print(f"    最大值: {slope_stats['max']:.4f}")
    print(f"    最小值: {slope_stats['min']:.4f}")
    print(f"    >0 的股票数: {(latest_df['momentum_slope'] > 0).sum()}")
    print(f"    ≤0 的股票数: {(latest_df['momentum_slope'] <= 0).sum()}")

    # 查看一些样例
    print(f"\n  样例（前10个非空值）:")
    sample = latest_df[latest_df['momentum_slope'].notna()].head(10)[['stock_code', 'close', 'momentum_slope']]
    for idx, row in sample.iterrows():
        print(f"    {row['stock_code']}: close={row['close']:.2f}, slope={row['momentum_slope']:.4f}")
else:
    print("    ⚠️ 所有动量斜率为空！")

# 3.4 价格分位 诊断
print("\n[诊断4] 价格分位指标:")
print(f"  价格分位 非空值: {latest_df['price_percentile'].notna().sum()}")
if latest_df['price_percentile'].notna().sum() > 0:
    pct_stats = latest_df['price_percentile'].describe()
    print(f"  统计:")
    print(f"    均值: {pct_stats['mean']:.2f}")
    print(f"    中位数: {pct_stats['50%']:.2f}")
    print(f"    最大值: {pct_stats['max']:.2f}")
    print(f"    最小值: {pct_stats['min']:.2f}")
    print(f"    <30 的股票数: {(latest_df['price_percentile'] < 30).sum()}")
    print(f"    <50 的股票数: {(latest_df['price_percentile'] < 50).sum()}")

    # 查看一些样例
    print(f"\n  样例（前10个非空值）:")
    sample = latest_df[latest_df['price_percentile'].notna()].head(10)[['stock_code', 'close', 'price_percentile']]
    for idx, row in sample.iterrows():
        print(f"    {row['stock_code']}: close={row['close']:.2f}, percentile={row['price_percentile']:.2f}")
else:
    print("    ⚠️ 所有价格分位为空！")

# Step 4: 模拟筛选过程
print("\n" + "=" * 80)
print("模拟筛选过程")
print("=" * 80)

print("\n[动量信号筛选]")
print(f"Step 1: 总股票数 = {len(latest_df)}")

# 条件1: RPS >= 90
cond1 = latest_df['rps'] >= 90
print(f"Step 2: RPS >= 90: {cond1.sum()} 只")

# 条件2: MA20 > MA60
cond2 = latest_df['ma20'] > latest_df['ma60']
print(f"Step 3: MA20 > MA60: {cond2.sum()} 只")

# 条件3: 动量斜率 > 0
cond3 = latest_df['momentum_slope'] > 0
print(f"Step 4: 动量斜率 > 0: {cond3.sum()} 只")

# 组合条件
momentum_mask = cond1 & cond2 & cond3
print(f"Step 5: 组合条件 (RPS≥90 AND MA20>MA60 AND 斜率>0): {momentum_mask.sum()} 只")

print("\n[反转候选筛选]")
print(f"Step 1: 总股票数 = {len(latest_df)}")

# 条件1: RPS >= 80
cond1_rev = latest_df['rps'] >= 80
print(f"Step 2: RPS >= 80: {cond1_rev.sum()} 只")

# 条件2: 价格分位 < 30
cond2_rev = latest_df['price_percentile'] < 30
print(f"Step 3: 价格分位 < 30: {cond2_rev.sum()} 只")

# 组合条件
reversal_mask = cond1_rev & cond2_rev
print(f"Step 4: 组合条件 (RPS≥80 AND 价格分位<30): {reversal_mask.sum()} 只")

# Step 5: 问题总结
print("\n" + "=" * 80)
print("问题总结")
print("=" * 80)

issues = []

if latest_df['rps'].notna().sum() == 0:
    issues.append("❌ RPS全部为空 - 可能是数据窗口不足（需要250天）")
elif (latest_df['rps'] >= 90).sum() == 0:
    issues.append("⚠️ RPS无≥90的股票 - 当前市场可能没有强势股")

if latest_df['momentum_slope'].notna().sum() == 0:
    issues.append("❌ 动量斜率全部为空 - 可能是数据窗口不足（需要20天）")
elif (latest_df['momentum_slope'] > 0).sum() == 0:
    issues.append("⚠️ 动量斜率全部≤0 - 当前市场可能处于下跌趋势")

if latest_df['price_percentile'].notna().sum() == 0:
    issues.append("❌ 价格分位全部为空 - 可能是数据窗口不足（建议使用1.5年也可以，但效果会降低）")
elif (latest_df['price_percentile'] < 30).sum() == 0:
    issues.append("⚠️ 价格分位无<30的股票 - 当前市场可能处于高位")

if len(issues) > 0:
    print("\n发现的问题:")
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")
else:
    print("\n✓ 未发现明显问题，可能是当前市场环境不满足策略条件")

print("\n" + "=" * 80)
print("建议:")
print("=" * 80)
print("1. 价格分位窗口可以调整为 360天（1.5年）以适应当前数据")
print("2. 如果动量斜率全部≤0，可以暂时移除这个条件")
print("3. 补充2020-2024年的历史数据会显著改善筛选效果")
print("=" * 80)
