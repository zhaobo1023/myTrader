# -*- coding: utf-8 -*-
"""
微盘股策略 v3.0 全量回测

测试矩阵：
  - v2.0 基线（pure_mv + h20 + 风控）
  - v3.0 增强1：日历择时（弱月减仓）
  - v3.0 增强2：动态市值止盈
  - v3.0 增强3：动量反转因子（pure_mv_mom）
  - v3.0 增强4：全组合叠加

输出：
  - output/microcap/v3_full_summary_<daterange>.json
  - output/microcap/v3_full_report_<daterange>.md
  - output/microcap/v3_<label>_<daterange>_daily.csv
  - output/microcap/v3_<label>_<daterange>_monthly.csv

用法：
  DB_ENV=online python -m strategist.microcap.run_v3_fulltest \
    --start 2024-01-01 --end 2026-04-10
"""
import os
import sys
import json
import logging
import argparse
from datetime import datetime

import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from strategist.microcap.config import MicrocapConfig
from strategist.microcap.backtest import MicrocapBacktest

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(ROOT, 'output', 'microcap')


# ---------------------------------------------------------------------------
# 策略矩阵定义
# ---------------------------------------------------------------------------

def build_strategy_matrix(start: str, end: str) -> list:
    """返回所有要测试的策略配置列表。"""
    common = dict(
        start_date=start,
        end_date=end,
        top_n=15,
        hold_days=20,
        market_cap_percentile=0.20,
        buy_cost_rate=0.0003,
        sell_cost_rate=0.0013,
        slippage_rate=0.001,
        exclude_st=True,
        min_avg_turnover=5_000_000,
        exclude_risk=True,
        benchmark_code='',  # 跳过基准拉取（网络受限时避免阻塞）
    )

    strategies = [
        # ---- v2.0 基线 ----
        {
            'label': 'v2_baseline',
            'desc':  'v2.0 基线: pure_mv + h20 + 风控',
            'config': MicrocapConfig(
                **{**common, 'factor': 'pure_mv'},
            ),
        },

        # ---- v3.0 增强1：日历择时 ----
        {
            'label': 'v3_calendar',
            'desc':  'v3.1 日历择时: 弱月(1/4/8/12)持仓减半',
            'config': MicrocapConfig(
                **{**common,
                   'factor': 'pure_mv',
                   'calendar_timing': True,
                   'weak_months': (1, 4, 8, 12),
                   'weak_month_ratio': 0.5},
            ),
        },

        # ---- v3.0 增强1b：日历择时（仅1/12月）----
        {
            'label': 'v3_calendar_1_12',
            'desc':  'v3.1b 日历择时: 弱月(1/12)持仓减半',
            'config': MicrocapConfig(
                **{**common,
                   'factor': 'pure_mv',
                   'calendar_timing': True,
                   'weak_months': (1, 12),
                   'weak_month_ratio': 0.5},
            ),
        },

        # ---- v3.0 增强2：动态市值止盈 ----
        {
            'label': 'v3_cap_exit_50',
            'desc':  'v3.2 动态市值止盈: 超过全市场50%分位即出',
            'config': MicrocapConfig(
                **{**common,
                   'factor': 'pure_mv',
                   'dynamic_cap_exit': True,
                   'cap_exit_percentile': 0.50},
            ),
        },
        {
            'label': 'v3_cap_exit_40',
            'desc':  'v3.2b 动态市值止盈: 超过全市场40%分位即出',
            'config': MicrocapConfig(
                **{**common,
                   'factor': 'pure_mv',
                   'dynamic_cap_exit': True,
                   'cap_exit_percentile': 0.40},
            ),
        },

        # ---- v3.0 增强3：动量反转因子 ----
        {
            'label': 'v3_mom_w03',
            'desc':  'v3.3 动量反转因子: pure_mv_mom w=0.3 lookback=20',
            'config': MicrocapConfig(
                **{**common,
                   'factor': 'pure_mv_mom',
                   'momentum_lookback': 20,
                   'momentum_weight': 0.3},
            ),
        },
        {
            'label': 'v3_mom_w05',
            'desc':  'v3.3b 动量反转因子: pure_mv_mom w=0.5 lookback=20',
            'config': MicrocapConfig(
                **{**common,
                   'factor': 'pure_mv_mom',
                   'momentum_lookback': 20,
                   'momentum_weight': 0.5},
            ),
        },

        # ---- v3.0 增强4：组合叠加 ----
        {
            'label': 'v3_combined_A',
            'desc':  'v3.4A 组合: 日历择时 + 市值止盈(50%)',
            'config': MicrocapConfig(
                **{**common,
                   'factor': 'pure_mv',
                   'calendar_timing': True,
                   'weak_months': (1, 4, 8, 12),
                   'weak_month_ratio': 0.5,
                   'dynamic_cap_exit': True,
                   'cap_exit_percentile': 0.50},
            ),
        },
        {
            'label': 'v3_combined_B',
            'desc':  'v3.4B 组合: 日历择时 + 动量反转(w=0.3)',
            'config': MicrocapConfig(
                **{**common,
                   'factor': 'pure_mv_mom',
                   'momentum_lookback': 20,
                   'momentum_weight': 0.3,
                   'calendar_timing': True,
                   'weak_months': (1, 4, 8, 12),
                   'weak_month_ratio': 0.5},
            ),
        },
        {
            'label': 'v3_combined_C',
            'desc':  'v3.4C 全组合: 日历择时 + 市值止盈 + 动量反转',
            'config': MicrocapConfig(
                **{**common,
                   'factor': 'pure_mv_mom',
                   'momentum_lookback': 20,
                   'momentum_weight': 0.3,
                   'calendar_timing': True,
                   'weak_months': (1, 4, 8, 12),
                   'weak_month_ratio': 0.5,
                   'dynamic_cap_exit': True,
                   'cap_exit_percentile': 0.50},
            ),
        },
    ]
    return strategies


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def calc_monthly_returns(daily_df: pd.DataFrame) -> pd.DataFrame:
    df = daily_df.copy()
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['month'] = df['trade_date'].dt.to_period('M')
    records = []
    for month, group in df.groupby('month'):
        nav_start = float(group.iloc[0]['nav'])
        nav_end = float(group.iloc[-1]['nav'])
        records.append({
            'month': str(month),
            'monthly_return': round((nav_end / nav_start) - 1.0, 6),
            'trade_days': len(group),
        })
    return pd.DataFrame(records)


def run_single(label: str, desc: str, config: MicrocapConfig, date_str: str) -> dict:
    logger.info("")
    logger.info("=" * 70)
    logger.info(f"[RUN] {label}  -  {desc}")
    logger.info("=" * 70)

    try:
        backtest = MicrocapBacktest(config)
        result = backtest.run()
    except Exception as e:
        logger.error(f"[ERROR] {label} 运行异常: {e}")
        return {'label': label, 'desc': desc, 'status': 'error', 'message': str(e)}

    if result['status'] != 'ok':
        msg = result.get('message', 'unknown error')
        logger.error(f"[ERROR] {label} failed: {msg}")
        return {'label': label, 'desc': desc, 'status': 'error', 'message': msg}

    summary = result['backtest_summary']
    daily_df = result['daily_values_df']

    # 保存每日净值
    daily_file = os.path.join(OUTPUT_DIR, f'v3_{label}_{date_str}_daily.csv')
    daily_df.to_csv(daily_file, index=False)

    # 月度收益
    monthly_df = calc_monthly_returns(daily_df)
    monthly_file = os.path.join(OUTPUT_DIR, f'v3_{label}_{date_str}_monthly.csv')
    monthly_df.to_csv(monthly_file, index=False)

    row = {
        'label':              label,
        'desc':               desc,
        'status':             'ok',
        'total_return':       round(summary['total_return'], 4),
        'annual_return':      round(summary['annual_return'], 4),
        'sharpe':             round(summary['sharpe_ratio'], 3),
        'sortino':            round(summary.get('sortino_ratio', 0), 3),
        'calmar':             round(summary.get('calmar_ratio', 0), 3),
        'max_drawdown':       round(summary['max_drawdown'], 4),
        'win_rate':           round(summary['win_rate'], 4),
        'avg_win':            round(summary.get('avg_win', 0), 4),
        'avg_loss':           round(summary.get('avg_loss', 0), 4),
        'profit_loss_ratio':  round(summary.get('profit_loss_ratio', 0), 3),
        'total_trades':       summary['total_trades'],
        'avg_hold_days':      round(summary.get('avg_hold_days', 0), 1),
        'limit_up_skipped':   summary.get('limit_up_skipped', 0),
        'limit_down_delayed': summary.get('limit_down_delayed', 0),
        'benchmark_annual':   round(summary.get('benchmark_annual_return') or 0, 4),
        'excess_annual':      round(summary.get('excess_annual_return') or 0, 4),
        'information_ratio':  round(summary.get('information_ratio') or 0, 3),
        'alpha':              round(summary.get('alpha') or 0, 4),
        'beta':               round(summary.get('beta') or 0, 3),
        'daily_file':         daily_file,
        'monthly_file':       monthly_file,
        'monthly_df':         monthly_df,
    }

    logger.info(
        f"[OK] {label}: total={row['total_return']:+.2%}, "
        f"annual={row['annual_return']:+.2%}, sharpe={row['sharpe']:.3f}, "
        f"sortino={row['sortino']:.3f}, calmar={row['calmar']:.3f}, "
        f"maxdd={row['max_drawdown']:.2%}, winrate={row['win_rate']:.1%}, "
        f"PL={row['profit_loss_ratio']:.2f}"
    )

    return row


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------

def print_summary_table(results: list):
    ok = [r for r in results if r.get('status') == 'ok']
    if not ok:
        return

    print()
    print("=" * 110)
    print("微盘股策略 v3.0 全量回测 - 汇总对比")
    print("=" * 110)
    header = (
        f"{'策略标签':<22} {'总收益':>8} {'年化':>8} {'Sharpe':>7} "
        f"{'Sortino':>8} {'Calmar':>7} {'最大回撤':>9} "
        f"{'胜率':>7} {'盈亏比':>7} {'超额年化':>9} {'IR':>6}"
    )
    print(header)
    print("-" * 110)
    for r in ok:
        total_sign = '+' if r['total_return'] >= 0 else ''
        annual_sign = '+' if r['annual_return'] >= 0 else ''
        excess_sign = '+' if r['excess_annual'] >= 0 else ''
        print(
            f"{r['label']:<22} "
            f"{total_sign}{r['total_return']:.2%}  "
            f"{annual_sign}{r['annual_return']:.2%}  "
            f"{r['sharpe']:>7.3f}  "
            f"{r['sortino']:>8.3f}  "
            f"{r['calmar']:>7.3f}  "
            f"{r['max_drawdown']:>9.2%}  "
            f"{r['win_rate']:>7.1%}  "
            f"{r['profit_loss_ratio']:>7.2f}  "
            f"{excess_sign}{r['excess_annual']:>8.2%}  "
            f"{r['information_ratio']:>6.3f}"
        )
    print("=" * 110)


def print_monthly_matrix(results: list):
    ok = [r for r in results if r.get('status') == 'ok' and 'monthly_df' in r]
    if not ok:
        return

    monthly_map = {}
    for r in ok:
        mdf = r['monthly_df']
        monthly_map[r['label']] = dict(zip(mdf['month'], mdf['monthly_return']))

    all_months = sorted({m for d in monthly_map.values() for m in d})
    labels = [r['label'] for r in ok]
    col_w = 11

    print()
    print("=" * (18 + col_w * len(labels)))
    print("月度收益对比矩阵")
    print("=" * (18 + col_w * len(labels)))

    header = f"{'月份':<18}"
    for lbl in labels:
        header += f"{lbl:>{col_w}}"
    print(header)
    print("-" * (18 + col_w * len(labels)))

    pos_counts = {lbl: 0 for lbl in labels}
    neg_counts = {lbl: 0 for lbl in labels}

    for month in all_months:
        line = f"{month:<18}"
        for lbl in labels:
            val = monthly_map[lbl].get(month)
            if val is None:
                line += f"{'N/A':>{col_w}}"
            else:
                sign = '+' if val >= 0 else ''
                line += f"{sign}{val:.2%}".rjust(col_w)
                if val > 0:
                    pos_counts[lbl] += 1
                else:
                    neg_counts[lbl] += 1
        print(line)

    print("-" * (18 + col_w * len(labels)))
    pos_line = f"{'正收益月份':<18}"
    neg_line = f"{'负收益月份':<18}"
    for lbl in labels:
        pos_line += f"{pos_counts[lbl]:>{col_w}}"
        neg_line += f"{neg_counts[lbl]:>{col_w}}"
    print(pos_line)
    print(neg_line)
    print("=" * (18 + col_w * len(labels)))


def generate_markdown_report(results: list, start: str, end: str, date_str: str) -> str:
    today = datetime.now().strftime('%Y-%m-%d')
    ok = [r for r in results if r.get('status') == 'ok']

    lines = [
        f"# 微盘股策略 v3.0 全量回测报告",
        "",
        f"**生成日期**: {today}",
        f"**回测区间**: {start} ~ {end}",
        f"**策略总数**: {len(results)} 个（成功 {len(ok)} 个）",
        "",
        "---",
        "",
        "## 一、汇总对比",
        "",
        "| 策略 | 描述 | 总收益 | 年化 | Sharpe | Sortino | Calmar | 最大回撤 | 胜率 | 盈亏比 | 超额年化 | IR |",
        "|------|------|--------|------|--------|---------|--------|----------|------|--------|----------|----|",
    ]

    for r in results:
        if r.get('status') != 'ok':
            lines.append(f"| {r['label']} | {r.get('desc', '')} | ERROR | - | - | - | - | - | - | - | - | - |")
            continue
        total_sign = '+' if r['total_return'] >= 0 else ''
        annual_sign = '+' if r['annual_return'] >= 0 else ''
        excess_sign = '+' if r['excess_annual'] >= 0 else ''
        lines.append(
            f"| **{r['label']}** | {r['desc']} "
            f"| {total_sign}{r['total_return']:.2%} "
            f"| {annual_sign}{r['annual_return']:.2%} "
            f"| {r['sharpe']:.3f} "
            f"| {r['sortino']:.3f} "
            f"| {r['calmar']:.3f} "
            f"| {r['max_drawdown']:.2%} "
            f"| {r['win_rate']:.1%} "
            f"| {r['profit_loss_ratio']:.2f} "
            f"| {excess_sign}{r['excess_annual']:.2%} "
            f"| {r['information_ratio']:.3f} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 二、详细指标",
        "",
    ]

    for r in ok:
        lines += [
            f"### {r['label']}",
            f"> {r['desc']}",
            "",
            "| 指标 | 数值 |",
            "|------|------|",
            f"| 总收益率 | {r['total_return']:+.2%} |",
            f"| 年化收益率 | {r['annual_return']:+.2%} |",
            f"| Sharpe | {r['sharpe']:.3f} |",
            f"| Sortino | {r['sortino']:.3f} |",
            f"| Calmar | {r['calmar']:.3f} |",
            f"| 最大回撤 | {r['max_drawdown']:.2%} |",
            f"| 胜率 | {r['win_rate']:.1%} |",
            f"| 盈亏比 | {r['profit_loss_ratio']:.2f} |",
            f"| 平均盈利 | {r['avg_win']:+.2%} |",
            f"| 平均亏损 | {r['avg_loss']:+.2%} |",
            f"| 总交易数 | {r['total_trades']} |",
            f"| 平均持仓天数 | {r['avg_hold_days']:.1f} |",
            f"| 涨停跳过买入 | {r['limit_up_skipped']} |",
            f"| 跌停顺延卖出 | {r['limit_down_delayed']} |",
            f"| 基准年化(国证2000) | {r['benchmark_annual']:+.2%} |",
            f"| 超额年化 | {r['excess_annual']:+.2%} |",
            f"| 信息比率(IR) | {r['information_ratio']:.3f} |",
            f"| Alpha(年化) | {r['alpha']:+.2%} |",
            f"| Beta | {r['beta']:.3f} |",
            "",
        ]

    lines += [
        "---",
        "",
        "## 三、月度收益矩阵",
        "",
    ]

    monthly_map = {}
    for r in ok:
        if 'monthly_df' in r:
            mdf = r['monthly_df']
            monthly_map[r['label']] = dict(zip(mdf['month'], mdf['monthly_return']))

    all_months = sorted({m for d in monthly_map.values() for m in d})
    labels = [r['label'] for r in ok]

    if all_months and labels:
        header_cols = ' | '.join(f"**{lbl}**" for lbl in labels)
        lines.append(f"| 月份 | {header_cols} |")
        sep_cols = ' | '.join([':---:'] * len(labels))
        lines.append(f"| :--- | {sep_cols} |")

        for month in all_months:
            row_vals = []
            for lbl in labels:
                val = monthly_map[lbl].get(month)
                if val is None:
                    row_vals.append('N/A')
                else:
                    sign = '+' if val >= 0 else ''
                    row_vals.append(f"{sign}{val:.2%}")
            row_str = ' | '.join(row_vals)
            lines.append(f"| {month} | {row_str} |")

    lines += [
        "",
        "---",
        "",
        "## 四、v3.0 增强分析",
        "",
        "### 各项增强效果（对比 v2.0 基线）",
        "",
        "| 增强项 | 策略标签 | 年化变化 | Sharpe 变化 | 最大回撤变化 | 盈亏比变化 |",
        "|--------|----------|----------|-------------|--------------|------------|",
    ]

    baseline = next((r for r in ok if r['label'] == 'v2_baseline'), None)
    if baseline:
        for r in ok:
            if r['label'] == 'v2_baseline':
                continue
            annual_delta = r['annual_return'] - baseline['annual_return']
            sharpe_delta = r['sharpe'] - baseline['sharpe']
            dd_delta = r['max_drawdown'] - baseline['max_drawdown']
            pl_delta = r['profit_loss_ratio'] - baseline['profit_loss_ratio']
            a_sign = '+' if annual_delta >= 0 else ''
            s_sign = '+' if sharpe_delta >= 0 else ''
            d_sign = '+' if dd_delta >= 0 else ''
            p_sign = '+' if pl_delta >= 0 else ''
            lines.append(
                f"| {r['desc'].split(':')[0]} | {r['label']} "
                f"| {a_sign}{annual_delta:.2%} "
                f"| {s_sign}{sharpe_delta:.3f} "
                f"| {d_sign}{dd_delta:.2%} "
                f"| {p_sign}{pl_delta:.2f} |"
            )
    else:
        lines.append("| (基线数据缺失，无法计算差值) | - | - | - | - | - |")

    lines += [
        "",
        "---",
        "",
        "## 五、附录",
        "",
        "### 回测参数",
        "",
        "```",
        f"初始资金: 1,000,000 元",
        f"市值百分位: 20%（后20%微盘股）",
        f"选股数量: 15 只",
        f"持有天数: 20 个交易日",
        f"买入费率: 0.03%",
        f"卖出费率: 0.13%（含印花税）",
        f"单边滑点: 0.1%",
        f"流动性过滤: 近5日均成交额 >= 500万",
        f"财务风控: 开启（排除亏损+高负债+负现金流）",
        f"基准: 国证2000 (399303)",
        "```",
        "",
        "### 输出文件",
        "",
    ]

    for r in results:
        if r.get('status') == 'ok':
            lines.append(f"- `{os.path.basename(r['daily_file'])}` - {r['desc']} 每日净值")
            lines.append(f"- `{os.path.basename(r['monthly_file'])}` - {r['desc']} 月度收益")

    lines += [
        "",
        "---",
        "",
        f"**报告生成时间**: {today}",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='微盘股策略 v3.0 全量回测')
    parser.add_argument('--start', default='2024-01-01', help='开始日期')
    parser.add_argument('--end',   default='2026-04-10', help='结束日期')
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    date_str = f"{args.start.replace('-', '')}_{args.end.replace('-', '')}"

    logger.info("=" * 70)
    logger.info(f"微盘股策略 v3.0 全量回测")
    logger.info(f"日期范围: {args.start} ~ {args.end}")
    logger.info("=" * 70)

    strategies = build_strategy_matrix(args.start, args.end)
    logger.info(f"共 {len(strategies)} 个策略组合待测试")

    results = []
    for i, strat in enumerate(strategies, 1):
        logger.info(f"\n[{i}/{len(strategies)}] 开始: {strat['label']}")
        row = run_single(strat['label'], strat['desc'], strat['config'], date_str)
        results.append(row)

    # 打印汇总表
    print_summary_table(results)
    print_monthly_matrix(results)

    # 保存 JSON 摘要（不含 monthly_df 对象）
    json_results = []
    for r in results:
        jr = {k: v for k, v in r.items() if k != 'monthly_df'}
        json_results.append(jr)
    summary_file = os.path.join(OUTPUT_DIR, f'v3_full_summary_{date_str}.json')
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(json_results, f, indent=2, ensure_ascii=False)
    logger.info(f"\n[OK] JSON 摘要已保存: {summary_file}")

    # 生成 Markdown 报告
    md_content = generate_markdown_report(results, args.start, args.end, date_str)
    md_file = os.path.join(OUTPUT_DIR, f'v3_full_report_{date_str}.md')
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(md_content)
    logger.info(f"[OK] Markdown 报告已保存: {md_file}")

    ok_count = sum(1 for r in results if r.get('status') == 'ok')
    logger.info(f"\n[DONE] 完成 {ok_count}/{len(results)} 个策略回测")
    logger.info(f"       输出目录: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
