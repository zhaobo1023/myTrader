# -*- coding: utf-8 -*-
"""
XGBoost 截面预测策略 - 批量运行脚本

支持对多个指数成分股分别运行回测，输出按日期组织到子目录。

运行: python -m strategist.xgboost_strategy.batch_run
"""
import sys
import os
import shutil
import logging
import pandas as pd
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from strategist.xgboost_strategy.config import StrategyConfig
from strategist.xgboost_strategy.data_loader import DataLoader
from strategist.xgboost_strategy.backtest import XGBoostBacktest
from strategist.xgboost_strategy.visualizer import Visualizer
from strategist.xgboost_strategy.feature_engine import get_all_feature_cols, FACTOR_TAXONOMY

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_OUTPUT_DIR = os.path.join(ROOT, 'output', 'xgboost')


def load_index_constituents(index_code):
    """
    通过 AKShare 获取指数成分股

    参数:
        index_code: 指数代码 (如 '000300', '000905', '000906')

    返回:
        list of stock_code strings (如 '600519.SH')
    """
    import akshare as ak

    df = ak.index_stock_cons(symbol=index_code)
    codes = df['品种代码'].tolist()
    # 转换格式: 600519 -> 600519.SH, 000001 -> 000001.SZ
    stock_codes = []
    for code in codes:
        code_str = str(code).zfill(6)
        if code_str.startswith('6'):
            stock_codes.append(f'{code_str}.SH')
        else:
            stock_codes.append(f'{code_str}.SZ')
    return stock_codes


def load_index_daily(index_code, start_date, end_date):
    """
    通过 AKShare 获取指数日线行情，返回日收益率 Series

    参数:
        index_code: 指数代码 (如 '000300')
        start_date: 开始日期 (如 '2023-01-01')
        end_date: 结束日期 (如 '2025-12-31')

    返回:
        pd.Series, index=Timestamp(交易日), values=日收益率(小数)
    """
    import akshare as ak

    start_fmt = start_date.replace('-', '')
    end_fmt = end_date.replace('-', '')

    df = ak.index_zh_a_hist(
        symbol=index_code, period='daily',
        start_date=start_fmt, end_date=end_fmt
    )

    df['日期'] = pd.to_datetime(df['日期'])
    df = df.set_index('日期')
    # '涨跌幅' 列是百分比，转为小数
    daily_ret = df['涨跌幅'] / 100.0

    return daily_ret


def organize_old_output():
    """将 output 根目录下散落的文件整理到日期子目录"""
    if not os.path.exists(BASE_OUTPUT_DIR):
        return

    loose_files = [
        'signals.csv', 'portfolio_returns.csv', 'factor_ic.csv',
        'ic_analysis.png', 'portfolio_performance.png', 'factor_ic.png',
        'strategy_report.md',
    ]

    for f in loose_files:
        src = os.path.join(BASE_OUTPUT_DIR, f)
        if os.path.exists(src):
            # 移到 _archive 子目录
            archive_dir = os.path.join(BASE_OUTPUT_DIR, '_archive')
            os.makedirs(archive_dir, exist_ok=True)
            dst = os.path.join(archive_dir, f)
            if not os.path.exists(dst):
                shutil.move(src, dst)
                print(f"  归档: {f} -> _archive/{f}")


def run_single_index(index_name, index_code, run_date=None):
    """
    运行单个指数的回测

    参数:
        index_name: 指数名称 (如 'CSI300')
        index_code: 指数代码 (如 '000300')
        run_date: 运行日期 (默认当天)

    返回:
        (metrics_dict, report_path) 或 (None, None) 如果失败
    """
    if run_date is None:
        run_date = datetime.now().strftime('%Y%m%d')

    print(f"\n{'='*80}")
    print(f"  {index_name} ({index_code})")
    print(f"{'='*80}")

    # 创建输出目录: output/20260327/CSI300/
    output_dir = os.path.join(BASE_OUTPUT_DIR, run_date, index_name)
    os.makedirs(output_dir, exist_ok=True)
    print(f"输出目录: {output_dir}")

    # 1. 获取成分股
    print(f"\n[1/5] 获取 {index_name} 成分股...")
    try:
        stock_pool = load_index_constituents(index_code)
    except Exception as e:
        print(f"  获取成分股失败: {e}")
        return None, None
    print(f"  成分股数量: {len(stock_pool)}")

    # 2. 配置
    config = StrategyConfig()
    config.stock_pool = stock_pool
    # 大盘股多时缩短回测日期以控制运行时间
    if len(stock_pool) > 400:
        config.end_date = '2025-06-30'

    print(f"  日期范围: {config.start_date} ~ {config.end_date}")
    print(f"  训练窗口: {config.train_window} 天")

    # 3. 加载数据
    print(f"\n[2/5] 加载数据并计算因子...")
    data_loader = DataLoader(config)
    try:
        panel, feature_cols = data_loader.load_and_compute_factors()
    except Exception as e:
        print(f"  数据加载失败: {e}")
        return None, None

    # 4. 获取指数基准收益
    print(f"\n[3/5] 获取 {index_name} 指数基准...")
    try:
        benchmark_ret_series = load_index_daily(index_code, config.start_date, config.end_date)
        print(f"  基准数据: {len(benchmark_ret_series)} 个交易日")
    except Exception as e:
        print(f"  获取基准失败: {e}，将使用全市场等权")
        benchmark_ret_series = None

    # 5. 运行回测
    print(f"\n[4/5] 运行回测...")
    backtest = XGBoostBacktest(config)
    try:
        result = backtest.run_backtest(panel, feature_cols, benchmark_ret_series)
    except Exception as e:
        print(f"  回测失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None

    if not result:
        print("  回测结果为空")
        return None, None

    metrics = result['metrics']
    portfolio_returns = result['portfolio_returns']

    # 6. 单因子 IC 分析
    print(f"\n[5/6] 单因子 IC 分析...")
    factor_ic_df = backtest.analyze_factor_ic(panel, feature_cols)

    if not factor_ic_df.empty:
        print(f"\n  Top 10 因子 (按 |ICIR|):")
        print(f"  {'因子':<28} {'IC':>8} {'ICIR':>8} {'RankIC':>8} {'RICIR':>8}")
        print(f"  {'-'*65}")
        for _, row in factor_ic_df.head(10).iterrows():
            print(f"  {row['factor']:<28} {row['IC']:>8.4f} {row['ICIR']:>8.4f} "
                  f"{row['RankIC']:>8.4f} {row['RankICIR']:>8.4f}")

    # 7. 保存结果
    print(f"\n[6/6] 保存结果到 {output_dir}...")

    # CSV
    result['signals'].to_csv(os.path.join(output_dir, 'signals.csv'), index=False, encoding='utf-8-sig')
    if not portfolio_returns.empty:
        portfolio_returns.to_csv(os.path.join(output_dir, 'portfolio_returns.csv'), index=False, encoding='utf-8-sig')
    if not factor_ic_df.empty:
        factor_ic_df.to_csv(os.path.join(output_dir, 'factor_ic.csv'), index=False, encoding='utf-8-sig')

    # 图表
    visualizer = Visualizer(output_dir)
    visualizer.plot_ic_analysis(metrics)
    if not portfolio_returns.empty:
        visualizer.plot_portfolio_performance(portfolio_returns)
    if not factor_ic_df.empty:
        visualizer.plot_factor_ic(factor_ic_df)

    # 报告
    report_path = os.path.join(output_dir, 'strategy_report.md')
    generate_report(index_name, index_code, config, metrics, portfolio_returns, factor_ic_df, report_path)

    print(f"\n  {index_name} 完成!")
    print(f"  IC={metrics['IC']:.4f}  ICIR={metrics['ICIR']:.4f}  "
          f"RankIC={metrics['RankIC']:.4f}  RankICIR={metrics['RankICIR']:.4f}")

    return metrics, report_path, len(stock_pool)


def generate_report(index_name, index_code, config, metrics, portfolio_returns, factor_ic_df, report_path):
    """生成 Markdown 报告"""
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"# XGBoost 截面预测策略报告 — {index_name}\n\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"指数代码: {index_code}\n")
        f.write(f"成分股数: {len(config.stock_pool)}\n\n")

        f.write("## 一、策略概述\n\n")
        f.write("基于 MASTER 论文思想，使用 XGBoost 进行股票截面预测。\n\n")
        f.write(f"- **指数**: {index_name} ({index_code})\n")
        f.write(f"- **成分股**: {len(config.stock_pool)} 只\n")
        f.write(f"- **因子维度**: 52 维技术因子\n")
        f.write(f"- **预处理**: MAD 去极值 + Z-Score 标准化\n")
        f.write(f"- **模型**: XGBoost (n={config.n_estimators}, depth={config.max_depth}, lr={config.learning_rate})\n")
        f.write(f"- **训练窗口**: {config.train_window} 交易日\n")
        f.write(f"- **预测周期**: 未来 {config.predict_horizon} 日收益率\n")
        f.write(f"- **回测区间**: {config.start_date} ~ {config.end_date}\n")
        f.write(f"- **交易成本**: 0.20% (双边)\n")
        f.write(f"- **基准**: {index_name} 指数实际收益\n\n")

        f.write("## 二、IC 评估结果\n\n")
        f.write("| 指标 | 值 |\n")
        f.write("|------|----|\n")
        f.write(f"| IC | {metrics['IC']:.4f} |\n")
        f.write(f"| ICIR | {metrics['ICIR']:.4f} |\n")
        f.write(f"| RankIC | {metrics['RankIC']:.4f} |\n")
        f.write(f"| RankICIR | {metrics['RankICIR']:.4f} |\n")
        f.write(f"| IC>0 占比 | {metrics['IC_positive_rate']:.1%} |\n")
        f.write(f"| IC 最大值 | {metrics['IC_max']:.4f} |\n")
        f.write(f"| IC 最小值 | {metrics['IC_min']:.4f} |\n")
        f.write(f"| 有效天数 | {metrics['n_days']} |\n\n")

        if not portfolio_returns.empty:
            f.write("## 三、组合表现\n\n")
            total_ret = portfolio_returns['cum_portfolio'].iloc[-1] - 1
            benchmark_ret = portfolio_returns['cum_benchmark'].iloc[-1] - 1
            excess_ret = total_ret - benchmark_ret

            f.write("| 指标 | 值 |\n")
            f.write("|------|----|\n")
            f.write(f"| 策略总收益 | {total_ret*100:+.2f}% |\n")
            f.write(f"| 基准总收益 | {benchmark_ret*100:+.2f}% |\n")
            f.write(f"| 超额收益 | {excess_ret*100:+.2f}% |\n")
            f.write(f"| 平均持仓 | {portfolio_returns['n_stocks'].mean():.1f} 只 |\n\n")

        if not factor_ic_df.empty:
            f.write("## 四、Top 10 因子\n\n")
            f.write("| 因子 | IC | ICIR | RankIC | RankICIR |\n")
            f.write("|------|----:|-----:|-------:|---------:|\n")
            for _, row in factor_ic_df.head(10).iterrows():
                f.write(f"| {row['factor']} | {row['IC']:.4f} | {row['ICIR']:.4f} | "
                       f"{row['RankIC']:.4f} | {row['RankICIR']:.4f} |\n")
            f.write("\n")

        f.write("## 五、可视化图表\n\n")
        f.write("- [IC 分析图](ic_analysis.png)\n")
        f.write("- [组合表现图](portfolio_performance.png)\n")
        f.write("- [因子 IC 图](factor_ic.png)\n\n")


def print_comparison_summary(all_results):
    """打印多指数对比汇总"""
    print(f"\n\n{'='*80}")
    print("  多指数对比汇总")
    print(f"{'='*80}")
    print(f"\n{'指数':<12} {'股票数':>6} {'IC':>8} {'ICIR':>8} {'RankIC':>8} {'RICIR':>8} {'IC>0':>6} {'策略收益':>10} {'超额收益':>10}")
    print("-" * 85)

    for name, info in all_results.items():
        m = info['metrics']
        pr = info.get('portfolio_returns')
        if pr is not None and not pr.empty:
            strat_ret = pr['cum_portfolio'].iloc[-1] - 1
            bench_ret = pr['cum_benchmark'].iloc[-1] - 1
            excess = strat_ret - bench_ret
            print(f"{name:<12} {info['n_stocks']:>6} {m['IC']:>8.4f} {m['ICIR']:>8.4f} "
                  f"{m['RankIC']:>8.4f} {m['RankICIR']:>8.4f} {m['IC_positive_rate']:>5.1%} "
                  f"{strat_ret*100:>+9.2f}% {excess*100:>+9.2f}%")
        else:
            print(f"{name:<12} {info['n_stocks']:>6} {m['IC']:>8.4f} {m['ICIR']:>8.4f} "
                  f"{m['RankIC']:>8.4f} {m['RankICIR']:>8.4f} {m['IC_positive_rate']:>5.1%}")

    print("-" * 85)


def main():
    run_date = datetime.now().strftime('%Y%m%d')

    # 整理旧 output
    print("整理旧 output 文件...")
    organize_old_output()

    # 定义要运行的指数
    indices = [
        ('CSI300',  '000300'),
        ('CSI500',  '000905'),
        ('CSI800',  '000906'),
    ]

    all_results = {}

    for index_name, index_code in indices:
        metrics, report_path, n_stocks = run_single_index(index_name, index_code, run_date)
        if metrics is not None:
            # 获取 portfolio_returns 用于汇总
            pr_path = os.path.join(BASE_OUTPUT_DIR, run_date, index_name, 'portfolio_returns.csv')
            pr = pd.read_csv(pr_path) if os.path.exists(pr_path) else None
            all_results[index_name] = {
                'metrics': metrics,
                'portfolio_returns': pr,
                'n_stocks': n_stocks,
                'report_path': report_path,
            }
        else:
            print(f"\n  {index_name} 运行失败，跳过")

    # 对比汇总
    if all_results:
        print_comparison_summary(all_results)

    print(f"\n{'='*80}")
    print(f"  全部完成! 输出目录: {os.path.join(BASE_OUTPUT_DIR, run_date)}")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
