# -*- coding: utf-8 -*-
"""
Paper Trading 手动运行入口

用法:
    # 初始化数据库表
    python -m strategist.xgboost_strategy.paper_trading.run_paper_trading --action init

    # 生成今日信号（周五收盘后运行）
    python -m strategist.xgboost_strategy.paper_trading.run_paper_trading --action signal --index 沪深300

    # 结算并填入买入价（每日盘后运行）
    python -m strategist.xgboost_strategy.paper_trading.run_paper_trading --action settle

    # 查看评估报告
    python -m strategist.xgboost_strategy.paper_trading.run_paper_trading --action report --index 沪深300

    # 全自动（结算 + 如果今天是周五则生成信号）
    python -m strategist.xgboost_strategy.paper_trading.run_paper_trading --action auto

    # 查看当前状态
    python -m strategist.xgboost_strategy.paper_trading.run_paper_trading --action status

    # 历史回放测试
    python -m strategist.xgboost_strategy.paper_trading.run_paper_trading --action replay --index 沪深300 --start 2024-01-05 --end 2024-06-28
"""
import argparse
import logging
import sys
import os
from datetime import date, timedelta

# 确保 myTrader 根目录在 sys.path
mytrader_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, mytrader_root)

from strategist.xgboost_strategy.paper_trading.config import PaperTradingConfig
from strategist.xgboost_strategy.paper_trading.scheduler import PaperTradingScheduler
from strategist.xgboost_strategy.paper_trading.evaluator import PerformanceEvaluator
from strategist.xgboost_strategy.paper_trading.position_manager import PositionManager
from strategist.xgboost_strategy.paper_trading.db_schema import init_tables


def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def action_init(args):
    """初始化数据库表"""
    print("初始化 Paper Trading 数据库表...")
    init_tables()
    print("初始化完成")


def action_signal(args):
    """生成信号"""
    today = date.fromisoformat(args.date) if args.date else date.today()
    scheduler = PaperTradingScheduler()
    result = scheduler.run(today, args.index, is_signal_day=True)

    if result.get('signal_generated'):
        print(f"\n信号生成成功:")
        print(f"  轮次 ID: {result['signal_round_id']}")
        print(f"  指数池: {args.index}")
        print(f"  信号日: {today}")
    elif result.get('signal_error'):
        print(f"\n信号生成失败: {result['signal_error']}")


def action_settle(args):
    """结算"""
    today = date.fromisoformat(args.date) if args.date else date.today()
    scheduler = PaperTradingScheduler()
    result = scheduler.run(today, args.index, is_signal_day=False)

    print(f"\n结算完成:")
    print(f"  填入买入价: {result['buys_filled']} 轮")
    print(f"  完成结算: {result['rounds_settled']} 轮")
    for detail in result.get('settlement_details', []):
        print(f"    {detail['round_id']}: "
              f"策略 {detail['portfolio_ret']:.2f}%, "
              f"超额 {detail['excess_ret']:.2f}%, "
              f"IC={detail['ic']:.4f}")


def action_report(args):
    """查看评估报告"""
    ev = PerformanceEvaluator()
    ev.print_report(args.index, min_rounds=1)


def action_auto(args):
    """全自动模式"""
    today = date.fromisoformat(args.date) if args.date else date.today()
    is_friday = today.weekday() == 4
    scheduler = PaperTradingScheduler()
    result = scheduler.run(today, args.index, is_signal_day=is_friday)

    print(f"\n自动运行完成 (日期={today}, 周五={is_friday}):")
    print(f"  填入买入价: {result['buys_filled']} 轮")
    print(f"  完成结算: {result['rounds_settled']} 轮")
    print(f"  新信号: {'是' if result['signal_generated'] else '否'}")


def action_status(args):
    """查看当前状态"""
    config = PaperTradingConfig()
    pm = PositionManager(config)

    print(f"\n{'='*50}")
    print(f"  Paper Trading 状态概览")
    print(f"{'='*50}")

    for status_name in ['pending', 'active', 'settled', 'cancelled']:
        rounds = pm.get_rounds_by_status(status_name)
        print(f"\n  [{status_name.upper()}] {len(rounds)} 轮")
        for r in rounds[:5]:  # 最多显示 5 条
            print(f"    {r['round_id']}: signal={r['signal_date']}, "
                  f"buy={r['buy_date']}, sell={r['sell_date']}")
        if len(rounds) > 5:
            print(f"    ... 还有 {len(rounds)-5} 轮")

    # 查看可用指数
    print(f"\n  可用指数池: {', '.join(config.get_available_indexes())}")
    print(f"  默认持仓天数: {config.hold_days} 交易日")
    print(f"  默认选股数量: Top {config.top_n}")


def action_replay(args):
    """历史回放"""
    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)

    # 生成周五列表
    signal_dates = []
    current = start_date
    while current <= end_date:
        if current.weekday() == 4:  # 周五
            signal_dates.append(current)
        current += timedelta(days=1)

    if not signal_dates:
        print(f"指定日期范围内没有周五: {args.start} ~ {args.end}")
        return

    print(f"历史回放: {len(signal_dates)} 个周五 ({args.start} ~ {args.end})")
    print(f"指数池: {args.index}")

    scheduler = PaperTradingScheduler()
    results = scheduler.run_history_replay(signal_dates, args.index)

    # 打印摘要
    n_success = sum(1 for r in results if 'settlement' in r and r['settlement'])
    n_fail = sum(1 for r in results if 'error' in r)
    print(f"\n回放结果: {n_success} 成功, {n_fail} 失败, 共 {len(results)} 轮")


def main():
    parser = argparse.ArgumentParser(
        description='Paper Trading 实盘验证系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --action init
  %(prog)s --action signal --index 沪深300
  %(prog)s --action settle
  %(prog)s --action report --index 沪深300
  %(prog)s --action auto
  %(prog)s --action status
  %(prog)s --action replay --index 沪深300 --start 2024-01-05 --end 2024-06-28
        """
    )

    parser.add_argument(
        '--action',
        choices=['init', 'signal', 'settle', 'report', 'auto', 'status', 'replay'],
        required=True,
        help='执行动作'
    )
    parser.add_argument(
        '--index', default='沪深300',
        help='指数池名称 (默认: 沪深300)'
    )
    parser.add_argument(
        '--date', default=None,
        help='指定日期 YYYY-MM-DD (默认: 今天)'
    )
    parser.add_argument(
        '--start', default=None,
        help='回放起始日期 YYYY-MM-DD (仅 replay 模式)'
    )
    parser.add_argument(
        '--end', default=None,
        help='回放结束日期 YYYY-MM-DD (仅 replay 模式)'
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='详细日志输出'
    )

    args = parser.parse_args()

    # 参数校验
    if args.action == 'replay' and (not args.start or not args.end):
        parser.error("replay 模式需要 --start 和 --end 参数")

    setup_logging(args.verbose)

    action_map = {
        'init': action_init,
        'signal': action_signal,
        'settle': action_settle,
        'report': action_report,
        'auto': action_auto,
        'status': action_status,
        'replay': action_replay,
    }

    action_map[args.action](args)


if __name__ == '__main__':
    main()
