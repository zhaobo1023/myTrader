# -*- coding: utf-8 -*-
"""
SVD 市场状态可视化 - 多尺度叠加图 + 解释度视角
"""
import os
import logging
import platform

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# 中文字体配置
if platform.system() == "Darwin":
    matplotlib.rcParams['font.family'] = ["Heiti TC", "STHeiti", "Arial Unicode MS", "sans-serif"]
elif platform.system() == "Windows":
    matplotlib.rcParams['font.family'] = ["SimHei", "Microsoft YaHei", "sans-serif"]
else:
    matplotlib.rcParams['font.family'] = ["Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans"]
matplotlib.rcParams['axes.unicode_minus'] = False

logger = logging.getLogger(__name__)


STATE_COLORS = {
    '齐涨齐跌': '#e74c3c',
    '板块分化': '#f39c12',
    '个股行情': '#27ae60',
}


def plot_regime_chart(results_df: pd.DataFrame, regimes: list,
                      output_path: str = None, output_dir: str = 'output/svd_monitor'):
    """
    绘制多尺度市场状态监控图

    上半区: F1 方差占比 (三窗口 + 综合线 + 阈值线 + 突变标记)
    下半区: Top1/Top3/Top5 累计解释度
    """
    if results_df.empty:
        logger.warning("无数据，跳过可视化")
        return None

    os.makedirs(output_dir, exist_ok=True)
    if output_path is None:
        output_path = os.path.join(output_dir, 'svd_market_regime.png')

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), height_ratios=[3, 2], sharex=True)

    results_df['calc_date'] = pd.to_datetime(results_df['calc_date'])

    # 上半区: F1 方差占比
    window_styles = {
        20: {'color': '#3498db', 'alpha': 0.3, 'linewidth': 1, 'label': '20日窗口'},
        60: {'color': '#9b59b6', 'alpha': 0.5, 'linewidth': 1.5, 'label': '60日窗口'},
        120: {'color': '#e74c3c', 'alpha': 0.8, 'linewidth': 2.5, 'label': '120日窗口'},
    }

    for ws, style in window_styles.items():
        subset = results_df[results_df['window_size'] == ws].sort_values('calc_date')
        if subset.empty:
            continue
        ax1.fill_between(subset['calc_date'], subset['top1_var_ratio'] * 100,
                         alpha=style['alpha'], color=style['color'])
        ax1.plot(subset['calc_date'], subset['top1_var_ratio'] * 100,
                 color=style['color'], linewidth=style['linewidth'], label=style['label'])

    # 综合状态线
    if regimes:
        regime_df = pd.DataFrame([r.model_dump() for r in regimes])
        regime_df['calc_date'] = pd.to_datetime(regime_df['calc_date'])
        regime_df = regime_df.sort_values('calc_date')
        ax1.plot(regime_df['calc_date'], regime_df['final_score'] * 100,
                 color='#2c3e50', linewidth=2, linestyle='-', label='综合得分')

        mutations = regime_df[regime_df['is_mutation'] == True]
        if not mutations.empty:
            ax1.scatter(mutations['calc_date'], mutations['final_score'] * 100,
                        color='red', marker='^', s=100, zorder=5, label='突变警报')

    ax1.axhline(y=50, color='red', linestyle='--', alpha=0.5, linewidth=1)
    ax1.axhline(y=35, color='green', linestyle='--', alpha=0.5, linewidth=1)

    ylim = ax1.get_ylim()
    ax1.axhspan(50, ylim[1], alpha=0.05, color='red')
    ax1.axhspan(35, 50, alpha=0.05, color='orange')
    ax1.axhspan(ylim[0], 35, alpha=0.05, color='green')

    ax1.set_ylabel('Factor 1 方差占比 (%)', fontsize=12)
    ax1.set_title('滚动 SVD 市场状态监控', fontsize=14, fontweight='bold')
    ax1.legend(fontsize=9, loc='upper right', ncol=3)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(0, max(80, ax1.get_ylim()[1]))

    # 下半区: 解释度视角 (120日窗口)
    for ws in [120]:
        subset = results_df[results_df['window_size'] == ws].sort_values('calc_date')
        if subset.empty:
            continue
        ax2.fill_between(subset['calc_date'], subset['top5_var_ratio'] * 100,
                         alpha=0.1, color='gray')
        ax2.plot(subset['calc_date'], subset['top1_var_ratio'] * 100,
                 color='#e74c3c', linewidth=2, label='Top 1')
        ax2.plot(subset['calc_date'], subset['top3_var_ratio'] * 100,
                 color='#3498db', linewidth=1.5, label='Top 3')
        ax2.plot(subset['calc_date'], subset['top5_var_ratio'] * 100,
                 color='#95a5a6', linewidth=1, linestyle='--', label='Top 5')

    ax2.set_xlabel('日期', fontsize=12)
    ax2.set_ylabel('累计解释度 (%)', fontsize=12)
    ax2.set_title('因子解释度分布 (120日窗口)', fontsize=12)
    ax2.legend(fontsize=9, loc='upper right')
    ax2.grid(True, alpha=0.3)
    ax2.set_ylim(0, 100)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    fig.autofmt_xdate()

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    logger.info(f"图表已保存: {output_path}")
    return output_path
