# -*- coding: utf-8 -*-
"""
陶博士策略 - 使用新回测框架

演示如何使用通用回测框架进行回测
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strategist.backtest import BacktestEngine, BacktestConfig, ReportGenerator
from strategist.doctor_tao.data_fetcher import DoctorTaoDataFetcher
from strategist.doctor_tao.indicators import IndicatorCalculator
from strategist.doctor_tao.signal_screener import SignalScreener
import pandas as pd
import glob


def main():
    print("=" * 70)
    print("陶博士策略 - 新回测框架测试")
    print("=" * 70)
    
    # 1. 配置回测参数
    config = BacktestConfig(
        initial_cash=1_000_000,
        commission=0.0003,
        slippage=0.001,
        stamp_tax=0.001,
        max_positions=10,
        position_sizing='equal',
        single_position_limit=0.15,
        default_hold_days=60,
        default_stop_loss=-0.10,
        default_take_profit=0.20,
        benchmark='000300.SH',
    )
    
    print("\n回测配置:")
    print(f"  初始资金: {config.initial_cash:,.0f}")
    print(f"  最大持仓数: {config.max_positions}")
    print(f"  持仓天数: {config.default_hold_days}")
    print(f"  止损: {config.default_stop_loss*100:.0f}%")
    print(f"  止盈: {config.default_take_profit*100:.0f}%")
    
    # 2. 获取数据
    print("\n[1/4] 获取股票数据...")
    fetcher = DoctorTaoDataFetcher(use_cache=True)
    
    start_date = '2024-09-24'
    end_date = '2026-03-25'
    
    # 从CSV读取陶博士选出的股票（自动查找最新的信号文件）
    output_dir = os.path.join(os.path.dirname(__file__), 'output')
    signal_files = glob.glob(os.path.join(output_dir, 'signals_*.csv'))
    if not signal_files:
        print("错误：未找到信号文件，请先运行 signal_screener.py 生成信号")
        return
    signal_file = max(signal_files, key=os.path.getmtime)  # 使用最新的文件
    print(f"  使用信号文件: {os.path.basename(signal_file)}")
    signals_raw = pd.read_csv(signal_file)
    test_stocks = signals_raw['stock_code'].unique().tolist()
    print(f"  陶博士选股数: {len(test_stocks)}")
    
    price_dict = fetcher.fetch_daily_price_batch(
        test_stocks,
        start_date=start_date,
        end_date=end_date
    )
    print(f"  获取到 {len(price_dict)} 只股票的价格数据")
    
    # 3. 计算指标
    print("\n[2/4] 计算指标...")
    price_list = []
    for code, df in price_dict.items():
        if len(df) > 0:
            df['stock_code'] = code
            price_list.append(df)
    
    if not price_list:
        print("无有效价格数据")
        return
    
    price_df = pd.concat(price_list, ignore_index=True)
    indicators_df = IndicatorCalculator.calc_all_indicators(price_df)
    print(f"  计算完成，共 {len(indicators_df)} 条记录")
    
    # 4. 生成信号
    print("\n[3/4] 生成交易信号...")
    screener = SignalScreener()
    
    # 获取所有交易日期
    all_dates = sorted(indicators_df['trade_date'].unique())
    
    # 每20个交易日采样一次
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
        
        # 动量信号：RPS≥90, MA20>MA60, 动量斜率>0
        momentum_mask = (
            (date_df['rps'] >= 90) &
            (date_df['ma20'] > date_df['ma60']) &
            (date_df['rps_slope'] > 0)
        )
        
        if momentum_mask.sum() > 0:
            momentum_df = date_df[momentum_mask].copy()
            momentum_df['signal_type'] = 'momentum'
            momentum_df['date'] = momentum_df['trade_date']
            all_signals.append(momentum_df[['date', 'stock_code', 'signal_type']])
        
        # 反转候选：RPS≥80, 价格分位<30
        reversal_mask = (
            (date_df['rps'] >= 80) &
            (date_df['price_percentile'] < 30)
        )
        
        if reversal_mask.sum() > 0:
            reversal_df = date_df[reversal_mask].copy()
            reversal_df['signal_type'] = 'reversal'
            reversal_df['date'] = reversal_df['trade_date']
            all_signals.append(reversal_df[['date', 'stock_code', 'signal_type']])
    
    if not all_signals:
        print("无有效信号")
        return
    
    signals_df = pd.concat(all_signals, ignore_index=True)
    print(f"  总信号数: {len(signals_df)}")
    print(f"  动量信号: {len(signals_df[signals_df['signal_type']=='momentum'])}")
    print(f"  反转信号: {len(signals_df[signals_df['signal_type']=='reversal'])}")
    
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
        strategy_name="陶博士策略"
    )
    
    print("\n" + "=" * 70)
    print("回测完成!")
    print("=" * 70)


if __name__ == '__main__':
    main()
