# -*- coding: utf-8 -*-
"""
SVD 市场状态 Markdown 报告生成
"""
import os
import logging
from datetime import date
from typing import List, Optional

import pandas as pd

from .schemas import MarketRegime, WindowSVDResult

logger = logging.getLogger(__name__)


ADVICE_MAP = {
    '齐涨齐跌': (
        '当前市场齐涨齐跌特征明显，Beta 因子主导。\n'
        '- **建议**: 指数增强策略更有效，个股选择的 alpha 空间有限\n'
        '- **操作**: 可考虑增大仓位跟随大盘趋势，减少个股博弈\n'
        '- **风险**: 板块普跌时需注意系统性风险'
    ),
    '板块分化': (
        '当前市场处于板块分化阶段，行业轮动特征显著。\n'
        '- **建议**: 行业配置是关键，选对板块比选对个股更重要\n'
        '- **操作**: 关注行业动量因子，超配强势板块\n'
        '- **风险**: 轮动速度过快时容易被两头打脸'
    ),
    '个股行情': (
        '当前市场个股分化明显，Alpha 机会丰富。\n'
        '- **建议**: 选股策略更有效，多因子模型价值凸显\n'
        '- **操作**: 精选个股，降低对大盘方向的依赖\n'
        '- **风险**: 需要更严格的风控和止损'
    ),
}


def generate_report(regime: MarketRegime, results_df: pd.DataFrame,
                    chart_path: Optional[str] = None,
                    output_dir: str = 'output/svd_monitor') -> str:
    """
    生成 Markdown 报告
    """
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, f"svd_report_{regime.calc_date}.md")

    lines = []
    lines.append(f"# SVD 市场状态监控报告")
    lines.append(f"\n**观测日期**: {regime.calc_date} (120日窗口中点)")
    lines.append(f"**市场状态**: {regime.market_state}")
    lines.append(f"**综合得分**: {regime.final_score:.1%}")
    lines.append(f"**突变警报**: {'是' if regime.is_mutation else '否'}")
    lines.append("")

    # 多尺度明细
    lines.append("## 多尺度因子集中度")
    lines.append("")
    lines.append("| 窗口 | F1 占比 | 权重 |")
    lines.append("|------|---------|------|")
    for ws, weight in regime.weights_used.items():
        f1 = getattr(regime, f'f1_{_ws_label(ws)}', 'N/A')
        if f1 is not None:
            lines.append(f"| {ws}日 | {f1:.1%} | {weight:.0%} |")
    lines.append("")

    # 策略建议
    lines.append("## 策略建议")
    lines.append("")
    advice = ADVICE_MAP.get(regime.market_state, '数据不足，无法给出建议。')
    lines.append(advice)
    lines.append("")

    # 突变警报
    if regime.is_mutation:
        lines.append("## 突变警报")
        lines.append("")
        lines.append("> 当前市场结构发生剧烈变化，短窗口指标偏离长期均值 2\u03c3 以上。")
        lines.append("> 建议: 降低仓位，观察市场方向，等待结构稳定后再入场。")
        lines.append("")

    # 图表
    if chart_path and os.path.exists(chart_path):
        lines.append("## 市场状态图")
        lines.append("")
        lines.append(f"![SVD 市场状态]({chart_path})")
        lines.append("")

    # 历史状态变化: 用 120日窗口的详细数据展示趋势
    lines.append("## 近期状态变化 (120日窗口)")
    lines.append("")
    recent_120 = results_df[results_df['window_size'] == 120].sort_values('calc_date')
    if not recent_120.empty:
        lines.append("| 日期 | F1 占比 | Top3 占比 | 重构误差 | 股票数 |")
        lines.append("|------|---------|----------|---------|--------|")
        for _, row in recent_120.iterrows():
            d = row['calc_date']
            date_str = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)
            lines.append(
                f"| {date_str} | {row['top1_var_ratio']:.1%} | "
                f"{row['top3_var_ratio']:.1%} | {row['reconstruction_error']:.1%} | "
                f"{row['stock_count']} |"
            )
    lines.append("")

    report_text = "\n".join(lines)

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)

    logger.info(f"报告已保存: {report_path}")
    return report_path


def _ws_label(ws: int) -> str:
    return {20: 'short', 60: 'mid', 120: 'long'}.get(ws, str(ws))


def generate_industry_report(industry_results: dict,
                             output_dir: str = 'output/svd_monitor') -> str:
    """
    生成行业 SVD 总览报告

    内容:
    1. 各行业最新状态排名表 (按 F1 从高到低)
    2. 齐涨齐跌行业列表 (Beta 共振强)
    3. 个股行情行业列表 (Alpha 机会多)
    4. 突变警报行业
    """
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, 'svd_industry_report.md')

    # 收集各行业最新状态
    industry_summary = []
    for ind_name, data in industry_results.items():
        records = data.get('records', [])
        regimes = data.get('regimes', [])
        if not records or not regimes:
            continue
        latest = regimes[-1]
        # 最新 120 日窗口的 F1
        r120 = [r for r in records if r.window_size == 120]
        latest_f1 = r120[-1].top1_var_ratio if r120 else None
        latest_stock_count = r120[-1].stock_count if r120 else 0

        industry_summary.append({
            'industry': ind_name,
            'state': latest.market_state,
            'score': latest.final_score,
            'f1_120': latest_f1,
            'stock_count': latest_stock_count,
            'is_mutation': latest.is_mutation,
        })

    if not industry_summary:
        logger.warning("无行业数据，跳过报告生成")
        return None

    # 按 F1 从高到低排序
    industry_summary.sort(key=lambda x: x['f1_120'] or 0, reverse=True)

    lines = []
    lines.append("# 申万一级行业 SVD 监控总览")
    lines.append("")
    lines.append(f"**行业数量**: {len(industry_summary)}")
    lines.append(f"**阈值说明**: 行业分类使用历史分位数 (70%/30%)，非绝对阈值")
    lines.append("")

    # 1. 全行业排名表
    lines.append("## 行业 F1 排名 (120日窗口, 最新)")
    lines.append("")
    lines.append("| 排名 | 行业 | F1 占比 | 状态 | 股票数 | 突变 |")
    lines.append("|------|------|---------|------|--------|------|")
    for i, ind in enumerate(industry_summary, 1):
        mutation_flag = "**!!**" if ind['is_mutation'] else ""
        f1_str = f"{ind['f1_120']:.1%}" if ind['f1_120'] is not None else "N/A"
        lines.append(
            f"| {i} | {ind['industry']} | {f1_str} | "
            f"{ind['state']} | {ind['stock_count']} | {mutation_flag} |"
        )
    lines.append("")

    # 2. 齐涨齐跌行业 (Beta 共振)
    beta_industries = [d for d in industry_summary if d['state'] == '齐涨齐跌']
    if beta_industries:
        lines.append("## Beta 共振行业 (齐涨齐跌)")
        lines.append("")
        lines.append("> 这些行业内部高度一致，资金合力明显。适合指数增强/ETF，不适合选股。")
        lines.append("")
        for ind in beta_industries:
            f1_str = f"{ind['f1_120']:.1%}" if ind['f1_120'] is not None else "N/A"
            lines.append(f"- **{ind['industry']}**: F1={f1_str}, {ind['stock_count']} 只")
        lines.append("")

    # 3. 个股行情行业 (Alpha 机会)
    alpha_industries = [d for d in industry_summary if d['state'] == '个股行情']
    if alpha_industries:
        lines.append("## Alpha 机会行业 (个股行情)")
        lines.append("")
        lines.append("> 这些行业内部分化明显，选股策略有效。适合多因子选股/强弱对冲。")
        lines.append("")
        for ind in alpha_industries:
            f1_str = f"{ind['f1_120']:.1%}" if ind['f1_120'] is not None else "N/A"
            lines.append(f"- **{ind['industry']}**: F1={f1_str}, {ind['stock_count']} 只")
        lines.append("")

    # 4. 突变警报
    mutation_industries = [d for d in industry_summary if d['is_mutation']]
    if mutation_industries:
        lines.append("## 突变警报行业")
        lines.append("")
        lines.append("> 这些行业的市场结构近期发生剧烈变化，需重点关注。")
        lines.append("")
        for ind in mutation_industries:
            lines.append(f"- **{ind['industry']}**: {ind['state']}, score={ind['score']:.1%}")
        lines.append("")

    report_text = "\n".join(lines)

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)

    logger.info(f"行业报告已保存: {report_path}")
    return report_path
