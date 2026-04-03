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

for i in range(0, len(all_stocks), batch_size):  # 处理全部股票
    batch_stocks = all_stocks[i:i+batch_size]
    print(f"\n处理第 {i//batch_size + 1} 批: {len(batch_stocks)} 只股票...")

    try:
        # 批量获取价格数据
        price_dict = fetcher.fetch_daily_price_batch(
            batch_stocks,
            start_date='2020-01-01'
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
    (latest_df['rps_slope'] > 0)
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

    # Step 3: 增量对比，输出新增标的
    print("\n[Step 3] 增量对比 - 查找新增标的...")
    _save_new_signals(signals_df, output_dir)

else:
    print("\n未筛选出符合条件的股票")

print("\n" + "=" * 80)
print("完整流程执行完毕！")
print("=" * 80)


def _save_new_signals(signals_df: pd.DataFrame, output_dir: str):
    """
    与上一次信号对比，将新增标的整理到 CSV 和 Markdown 文档中。
    每次增量追加，不会覆盖历史记录。
    """
    import glob
    import akshare as ak

    latest_date = signals_df['trade_date'].iloc[0]
    current_codes = set(signals_df['stock_code'].tolist())

    # 找上一次的信号文件
    signal_files = sorted(glob.glob(os.path.join(output_dir, 'signals_*.csv')))
    # 排除 new_signals_ 开头的文件
    signal_files = [f for f in signal_files if not os.path.basename(f).startswith('new_signals_')]

    prev_codes = set()
    if len(signal_files) >= 2:
        prev_file = signal_files[-2]  # 倒数第二个是上一次
        prev_df = pd.read_csv(prev_file)
        prev_codes = set(prev_df['stock_code'].tolist())

    new_codes = current_codes - prev_codes
    if not new_codes:
        print("  无新增标的")
        return

    print(f"  新增标的: {len(new_codes)} 只")

    # 获取股票名称
    new_df = signals_df[signals_df['stock_code'].isin(new_codes)].copy()
    try:
        name_df = ak.stock_info_a_code_name()
        name_map = dict(zip(name_df['code'], name_df['name']))
        new_df['stock_name'] = new_df['stock_code'].apply(
            lambda c: name_map.get(c.split('.')[0], '未知')
        )
    except Exception as e:
        print(f"  获取股票名称失败: {e}")
        new_df['stock_name'] = '未知'

    new_df = new_df.sort_values('rps', ascending=False).reset_index(drop=True)

    # 保存增量 CSV（按日期）
    csv_path = os.path.join(output_dir, f"new_signals_{latest_date.strftime('%Y%m%d')}.csv")
    cols = ['stock_code', 'stock_name', 'signal_type', 'close', 'rps',
            'rps_slope', 'return_60d_rank', 'volume_ratio', 'price_percentile']
    new_df[cols].to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"  新增标的 CSV: {csv_path}")

    # 追加到 Markdown 文档
    md_path = os.path.join(output_dir, 'new_signals_tracker.md')
    date_str = latest_date.strftime('%Y-%m-%d')

    if not os.path.exists(md_path):
        # 首次创建
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('# 陶博士策略 - 新增信号标的追踪\n\n')
            f.write('> 筛选条件: RPS >= 90, MA20 > MA60, RPS斜率 > 0\n\n')
            f.write('## 指标说明\n\n')
            f.write('| 指标 | 说明 |\n|------|------|\n')
            f.write('| RPS | 250日涨幅截面排名分位（0-100），越高越强 |\n')
            f.write('| RPS斜率 | RPS的4周线性回归斜率Z-Score，>0 表示趋势向上 |\n')
            f.write('| 60日涨幅排名 | 近60日涨幅在全市场的百分位排名 |\n')
            f.write('| 成交量比 | 近20日均量/近250日均量，>1表示近期放量 |\n')
            f.write('| 价格分位 | 750日历史价格百分位，越低越接近底部 |\n\n')
            f.write('---\n\n')

    # 追加本次新增
    with open(md_path, 'a', encoding='utf-8') as f:
        f.write(f'## {date_str} 新增 {len(new_df)} 只\n\n')
        f.write('| 序号 | 股票代码 | 股票名称 | 收盘价 | RPS | RPS斜率 | 60日涨幅排名 | 成交量比 | 价格分位 |\n')
        f.write('|------|----------|----------|--------|-----|---------|-------------|----------|----------|\n')
        for i, row in new_df.iterrows():
            f.write(f'| {i+1} | {row["stock_code"]} | {row["stock_name"]} '
                    f'| {row["close"]:.2f} | {row["rps"]:.2f} | {row["rps_slope"]:.4f} '
                    f'| {row["return_60d_rank"]:.2f} | {row["volume_ratio"]:.4f} '
                    f'| {row["price_percentile"]:.2f} |\n')
        f.write('\n---\n\n')

    print(f"  追加到追踪文档: {md_path}")
