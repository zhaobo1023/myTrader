# -*- coding: utf-8 -*-
"""
陶博士18只股票历史回测

使用最新选出的18只股票进行历史回测
"""
import sys
import os
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strategist.backtest import BacktestEngine, BacktestConfig, ReportGenerator
from strategist.doctor_tao.data_fetcher import DoctorTaoDataFetcher
from strategist.doctor_tao.indicators import IndicatorCalculator


def main():
    print("=" * 70)
    print("陶博士18只股票历史回测")
    print("=" * 70)

    # 1. 读取信号文件
    signal_file = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                               'doctor_tao', 'output', 'signals_20260325_152820.csv')
    print(f"\n[1/4] 读取信号文件: {signal_file}")

    signals_raw = pd.read_csv(signal_file)
    stock_codes = signals_raw['stock_code'].unique().tolist()
    print(f"  股票数量: {len(stock_codes)}")
    print(f"  股票代码: {stock_codes}")

    # 2. 配置回测参数（使用默认配置）
    config = BacktestConfig(
        initial_cash=1_000_000,      # 初始资金100万
        commission=0.0003,           # 手续费 0.03%
        slippage=0.001,              # 滑点 0.1%
        stamp_tax=0.001,             # 印花税 0.1%
        max_positions=10,            # 最大持仓10只
        position_sizing='equal',     # 等权重
        single_position_limit=0.15,  # 单只股票最大仓位15%
        default_hold_days=60,        # 持仓60天
        default_stop_loss=-0.10,     # 止损-10%
        default_take_profit=0.20,    # 止盈+20%
        benchmark='000300.SH',       # 沪深300基准
    )

    print("\n回测配置:")
    print(f"  初始资金: {config.initial_cash:,.0f}")
    print(f"  最大持仓数: {config.max_positions}")
    print(f"  持仓天数: {config.default_hold_days}")
    print(f"  止损: {config.default_stop_loss*100:.0f}%")
    print(f"  止盈: {config.default_take_profit*100:.0f}%")

    # 3. 获取历史价格数据
    print("\n[2/4] 获取历史价格数据...")
    fetcher = DoctorTaoDataFetcher(use_cache=True)

    # 回测时间范围：2023-01-01 到最新
    start_date = '2023-01-01'
    end_date = '2026-03-24'

    price_dict = fetcher.fetch_daily_price_batch(
        stock_codes,
        start_date=start_date,
        end_date=end_date
    )
    print(f"  获取到 {len(price_dict)} 只股票的价格数据")

    # 4. 计算指标并生成历史信号
    print("\n[3/4] 计算指标并生成历史信号...")

    # 合并价格数据
    price_list = []
    for code, df in price_dict.items():
        if len(df) > 0:
            df = df.copy()
            df['stock_code'] = code
            price_list.append(df)

    if not price_list:
        print("无有效价格数据")
        return

    price_df = pd.concat(price_list, ignore_index=True)

    # 计算指标
    indicators_df = IndicatorCalculator.calc_all_indicators(price_df)
    print(f"  指标计算完成，共 {len(indicators_df)} 条记录")

    # 生成历史信号（每20个交易日采样）
    all_dates = sorted(indicators_df['trade_date'].unique())
    sample_interval = 20
    sample_dates = all_dates[::sample_interval]
    print(f"  采样日期数: {len(sample_dates)}")

    all_signals = []

    for date in sample_dates:
        date_df = indicators_df[indicators_df['trade_date'] == date].copy()

        if len(date_df) == 0:
            continue

        # 价格过滤
        date_df = date_df[date_df['close'] >= 3.0]

        # 动量信号：RPS>=90, MA20>MA60, 动量斜率>0
        momentum_mask = (
            (date_df['rps'] >= 90) &
            (date_df['ma20'] > date_df['ma60']) &
            (date_df['momentum_slope'] > 0)
        )

        if momentum_mask.sum() > 0:
            momentum_df = date_df[momentum_mask].copy()
            momentum_df['signal_type'] = 'momentum'
            momentum_df['date'] = momentum_df['trade_date']
            all_signals.append(momentum_df[['date', 'stock_code', 'signal_type']])

    if not all_signals:
        print("无有效信号")
        return

    signals_df = pd.concat(all_signals, ignore_index=True)
    print(f"  总信号数: {len(signals_df)}")
    print(f"  信号日期范围: {signals_df['date'].min()} ~ {signals_df['date'].max()}")

    # 5. 运行回测
    print("\n[4/4] 运行回测...")
    engine = BacktestEngine(config)

    result = engine.run(
        signals=signals_df,
        price_data=price_dict,
        benchmark_data=None
    )

    # 6. 生成报告
    print("\n生成回测报告...")
    output_dir = os.path.join(os.path.dirname(__file__), 'output')

    ReportGenerator.generate_full_report(
        result=result,
        output_dir=output_dir,
        strategy_name="陶博士18只股票回测"
    )

    # 打印关键指标
    print("\n" + "=" * 70)
    print("回测结果摘要")
    print("=" * 70)
    print(f"总收益率: {result['metrics']['total_return']*100:.2f}%")
    print(f"年化收益率: {result['metrics']['annual_return']*100:.2f}%")
    print(f"最大回撤: {result['metrics']['max_drawdown']*100:.2f}%")
    print(f"夏普比率: {result['metrics']['sharpe_ratio']:.2f}")
    print(f"胜率: {result['metrics']['win_rate']*100:.2f}%")
    print(f"总交易数: {result['metrics']['total_trades']}")
    print("=" * 70)

    print(f"\n报告已保存到: {output_dir}")


if __name__ == '__main__':
    main()
