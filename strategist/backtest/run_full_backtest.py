# -*- coding: utf-8 -*-
"""
陶博士策略 - 全量回测

执行完整的3年历史回测（2023-2026）
"""
import sys
import os
import pandas as pd
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from strategist.backtest import BacktestEngine, BacktestConfig, ReportGenerator
from strategist.doctor_tao.data_fetcher import DoctorTaoDataFetcher
from strategist.doctor_tao.indicators import IndicatorCalculator
import time


def print_step(step, title, estimated_time=""):
    """打印步骤标题"""
    print("\n" + "=" * 70)
    print(f"[{step}] {title}")
    if estimated_time:
        print(f"预计耗时: {estimated_time}")
    print("=" * 70)


def main():
    print("=" * 70)
    print("陶博士策略 - 全量3年回测")
    print("=" * 70)

    total_start = time.time()

    # ============================================================
    # [1/5] 数据准备
    # ============================================================
    print_step(1, "数据准备", "10-30秒（使用缓存）")

    fetcher = DoctorTaoDataFetcher(use_cache=True)

    # 回测时间范围：3年
    backtest_start = '2023-01-01'
    backtest_end = '2026-03-31'

    # 提前拉取400天数据用于计算指标
    data_start = (pd.to_datetime(backtest_start) - timedelta(days=400)).strftime('%Y-%m-%d')

    print(f"\n数据范围:")
    print(f"  拉取范围: {data_start} ~ {backtest_end}")
    print(f"  回测范围: {backtest_start} ~ {backtest_end}")

    # 选择股票池（使用不同市值和行业的代表性股票）
    stock_codes = [
        # 大盘蓝筹
        '600519.SH',  # 贵州茅台
        '000858.SZ',  # 五粮液
        '600036.SH',  # 招商银行
        '000001.SZ',  # 平安银行
        '601318.SH',  # 中国平安

        # 科技成长
        '300750.SZ',  # 宁德时代
        '002415.SZ',  # 海康威视
        '000063.SZ',  # 中兴通讯
        '002594.SZ',  # 比亚迪

        # 医药
        '000661.SZ',  # 长春高新
        '600276.SH',  # 恒瑞医药

        # 消费
        '000568.SZ',  # 泸州老窖
        '600887.SH',  # 伊利股份

        # 周期
        '600048.SH',  # 保利发展
        '601012.SH',  # 隆基绿能

        # 其他
        '600009.SH',  # 上海机场
        '000333.SZ',  # 美的集团
    ]

    print(f"\n股票池: {len(stock_codes)} 只")
    print(f"  {', '.join(stock_codes[:5])}...")

    step_start = time.time()
    price_dict = fetcher.fetch_daily_price_batch(
        stock_codes,
        start_date=data_start,
        end_date=backtest_end
    )
    print(f"\n获取到 {len(price_dict)} 只股票的价格数据")
    for code, df in list(price_dict.items())[:3]:
        print(f"  {code}: {len(df)} 条 ({df['trade_date'].min()} ~ {df['trade_date'].max()})")

    print(f"\n[耗时: {time.time() - step_start:.1f}秒]")

    # ============================================================
    # [2/5] 计算指标
    # ============================================================
    print_step(2, "计算技术指标", "30-60秒")

    step_start = time.time()

    # 合并价格数据
    price_list = []
    for code, df in price_dict.items():
        if len(df) > 0:
            df = df.copy()
            df['stock_code'] = code
            price_list.append(df)

    price_df = pd.concat(price_list, ignore_index=True)
    print(f"\n合并后数据: {len(price_df)} 条")

    # 计算所有指标
    indicators_df = IndicatorCalculator.calc_all_indicators(price_df)

    # 只保留回测时间范围内的数据
    indicators_df = indicators_df[
        (indicators_df['trade_date'] >= backtest_start) &
        (indicators_df['trade_date'] <= backtest_end)
    ]

    print(f"\n回测范围内数据: {len(indicators_df)} 条")
    print(f"日期范围: {indicators_df['trade_date'].min()} ~ {indicators_df['trade_date'].max()}")

    print(f"\n[耗时: {time.time() - step_start:.1f}秒]")

    # ============================================================
    # [3/5] 生成信号
    # ============================================================
    print_step(3, "生成交易信号", "5-10秒")

    step_start = time.time()

    # 每20个交易日采样一次
    all_dates = sorted(indicators_df['trade_date'].unique())
    sample_interval = 20
    sample_dates = all_dates[::sample_interval]

    print(f"\n采样策略:")
    print(f"  总交易日: {len(all_dates)}")
    print(f"  采样间隔: 每 {sample_interval} 个交易日")
    print(f"  采样次数: {len(sample_dates)}")

    all_signals = []

    for date in sample_dates:
        date_df = indicators_df[indicators_df['trade_date'] == date].copy()

        if len(date_df) == 0:
            continue

        # 价格过滤
        date_df = date_df[date_df['close'] >= 3.0]

        # 动量信号：RPS≥90, MA20>MA60, RPS斜率>0
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

        # 反转候选：RPS 80-90, 价格分位<30
        reversal_mask = (
            (date_df['rps'] >= 80) &
            (date_df['rps'] < 90) &
            (date_df.get('price_percentile', pd.Series([99]*len(date_df))) < 30)
        )

        if reversal_mask.sum() > 0:
            reversal_df = date_df[reversal_mask].copy()
            reversal_df['signal_type'] = 'reversal'
            reversal_df['date'] = reversal_df['trade_date']
            all_signals.append(reversal_df[['date', 'stock_code', 'signal_type']])

    if not all_signals:
        print("\n[WARN] 未生成任何信号")
        return

    signals_df = pd.concat(all_signals, ignore_index=True)

    print(f"\n生成信号统计:")
    print(f"  总信号数: {len(signals_df)}")
    print(f"  动量信号: {(signals_df['signal_type']=='momentum').sum()}")
    print(f"  反转信号: {(signals_df['signal_type']=='reversal').sum()}")
    print(f"  日期范围: {signals_df['date'].min()} ~ {signals_df['date'].max()}")

    print(f"\n[耗时: {time.time() - step_start:.1f}秒]")

    # ============================================================
    # [4/5] 运行回测
    # ============================================================
    print_step(4, "执行回测", "10-30秒")

    step_start = time.time()

    config = BacktestConfig(
        initial_cash=1_000_000,
        commission=0.0003,
        slippage=0.001,
        stamp_tax=0.001,
        max_positions=8,
        position_sizing='equal',
        single_position_limit=0.15,
        default_hold_days=60,
        default_stop_loss=-0.10,
        default_take_profit=0.20,
    )

    print(f"\n回测配置:")
    print(f"  初始资金: {config.initial_cash:,.0f}")
    print(f"  最大持仓: {config.max_positions}")
    print(f"  持仓天数: {config.default_hold_days}")
    print(f"  止损/止盈: {config.default_stop_loss*100:.0f}% / {config.default_take_profit*100:.0f}%")

    engine = BacktestEngine(config)

    result = engine.run(
        signals=signals_df,
        price_data=price_dict,
        benchmark_data=None
    )

    print(f"\n[耗时: {time.time() - step_start:.1f}秒]")

    # ============================================================
    # [5/5] 生成报告
    # ============================================================
    print_step(5, "生成回测报告", "5-10秒")

    step_start = time.time()

    output_dir = os.path.join(ROOT, 'output', 'doctor_tao')
    os.makedirs(output_dir, exist_ok=True)

    ReportGenerator.generate_full_report(
        result=result,
        output_dir=output_dir,
        strategy_name=f"陶博士策略_全量回测_{backtest_start}_{backtest_end}"
    )

    print(f"\n报告已保存: {output_dir}")
    print(f"\n[耗时: {time.time() - step_start:.1f}秒]")

    # ============================================================
    # 总结
    # ============================================================
    total_time = time.time() - total_start

    print("\n" + "=" * 70)
    print("全量回测完成!")
    print("=" * 70)

    print(f"\n核心指标:")
    print(f"  总收益率: {result.total_return*100:.2f}%")
    print(f"  年化收益率: {result.annual_return*100:.2f}%")
    print(f"  最大回撤: {result.max_drawdown*100:.2f}%")
    print(f"  夏普比率: {result.sharpe_ratio:.2f}")
    print(f"  索提诺比率: {result.sortino_ratio:.2f}")
    print(f"  卡玛比率: {result.calmar_ratio:.2f}")

    print(f"\n交易统计:")
    print(f"  总交易数: {result.total_trades}")
    print(f"  胜率: {result.win_rate*100:.2f}%")
    print(f"  平均收益/笔: {result.avg_return_per_trade*100:.2f}%")
    print(f"  盈亏比: {result.profit_loss_ratio:.2f}")
    print(f"  平均持仓天数: {result.avg_hold_days:.1f}")

    if result.momentum_stats:
        print(f"\n动量信号:")
        print(f"  交易数: {result.momentum_stats.get('count', 0)}")
        print(f"  胜率: {result.momentum_stats.get('win_rate', 0)*100:.2f}%")
        print(f"  平均收益: {result.momentum_stats.get('avg_return', 0)*100:.2f}%")

    if result.reversal_stats:
        print(f"\n反转信号:")
        print(f"  交易数: {result.reversal_stats.get('count', 0)}")
        print(f"  胜率: {result.reversal_stats.get('win_rate', 0)*100:.2f}%")
        print(f"  平均收益: {result.reversal_stats.get('avg_return', 0)*100:.2f}%")

    print(f"\n总耗时: {total_time:.1f}秒 ({total_time/60:.1f}分钟)")
    print("=" * 70)


if __name__ == '__main__':
    main()
