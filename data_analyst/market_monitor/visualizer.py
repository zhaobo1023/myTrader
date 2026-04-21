# -*- coding: utf-8 -*-
"""
SVD 市场状态可视化 - 多尺度叠加图 + 解释度视角
"""
import os
import logging
import platform

import numpy as np
import pandas as pd

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import matplotlib.colors as mcolors
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# 中文字体配置 - 自动检测可用字体
def _find_chinese_font():
    """从系统已安装字体中查找第一个可用的中文字体"""
    if not HAS_MATPLOTLIB:
        return None
    available = {f.name for f in matplotlib.font_manager.fontManager.ttflist}
    candidates = [
        # macOS
        "PingFang SC", "PingFang HK", "Hiragino Sans GB", "Heiti TC",
        "Songti SC", "STHeiti", "STSong", "Apple SD Gothic Neo",
        # Windows
        "SimHei", "Microsoft YaHei", "Microsoft YaHei UI",
        # Linux
        "Noto Sans CJK SC", "Noto Sans SC", "WenQuanYi Zen Hei",
        "WenQuanYi Micro Hei", "Source Han Sans SC",
        # 通用 fallback
        "Arial Unicode MS",
    ]
    for font in candidates:
        if font in available:
            return font
    return None

if HAS_MATPLOTLIB:
    _chinese_font = _find_chinese_font()
    if _chinese_font:
        matplotlib.rcParams['font.sans-serif'] = [_chinese_font] + matplotlib.rcParams.get('font.sans-serif', [])
    else:
        if platform.system() == "Darwin":
            matplotlib.rcParams['font.sans-serif'] = ["Heiti TC", "Arial Unicode MS"] + matplotlib.rcParams.get('font.sans-serif', [])
        elif platform.system() == "Windows":
            matplotlib.rcParams['font.sans-serif'] = ["SimHei", "Microsoft YaHei"] + matplotlib.rcParams.get('font.sans-serif', [])
        else:
            matplotlib.rcParams['font.sans-serif'] = ["Noto Sans CJK SC", "WenQuanYi Zen Hei"] + matplotlib.rcParams.get('font.sans-serif', [])
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
    if not HAS_MATPLOTLIB:
        logger.warning("matplotlib 未安装，跳过可视化")
        return None
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


def plot_industry_heatmap(industry_results: dict,
                          output_dir: str = 'output/svd_monitor') -> str:
    """
    行业 F1 热力图: 纵轴=行业, 横轴=日期, 颜色=F1 占比

    一眼看出:
    - 哪些行业 Beta 共振强 (红色)
    - 哪些行业个股分化 (绿色)
    - 市场压力的传导路径 (红色从哪些行业开始蔓延)
    """
    if not HAS_MATPLOTLIB:
        logger.warning("matplotlib 未安装，跳过行业热力图")
        return None
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'svd_industry_heatmap.png')

    # 收集所有行业的 120 日窗口 F1 数据
    rows = []
    for industry_name, data in industry_results.items():
        records = data.get('records', [])
        for r in records:
            if r.window_size == 120:
                rows.append({
                    'industry': industry_name,
                    'date': r.calc_date,
                    'f1': r.top1_var_ratio,
                    'state': r.market_state,
                })

    if not rows:
        logger.warning("无行业数据，跳过热力图")
        return None

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])

    # 构建透视表: index=行业, columns=日期, values=F1
    pivot = df.pivot_table(index='industry', columns='date', values='f1', aggfunc='first')
    pivot = pivot.sort_index()

    # 计算图大小: 根据行业数量动态调整
    n_industries = len(pivot)
    fig_height = max(10, n_industries * 0.35)
    fig, ax = plt.subplots(figsize=(18, fig_height))

    # 绘制热力图
    # 颜色映射: 绿(低F1/个股行情) -> 黄(板块分化) -> 红(高F1/齐涨齐跌)
    cmap = plt.cm.RdYlGn_r
    norm = mcolors.Normalize(vmin=20, vmax=80)

    im = ax.imshow(pivot.values * 100, aspect='auto', cmap=cmap, norm=norm,
                   interpolation='nearest')

    # 坐标轴
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([d.strftime('%m-%d') for d in pivot.columns],
                       rotation=45, ha='right', fontsize=8)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=9)

    # 在格子中标注数值
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.values[i, j]
            if not np.isnan(val):
                text_color = 'white' if val * 100 > 60 or val * 100 < 25 else 'black'
                ax.text(j, i, f'{val*100:.0f}', ha='center', va='center',
                        fontsize=6, color=text_color)

    # 色标
    cbar = plt.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
    cbar.set_label('F1 方差占比 (%)', fontsize=10)

    ax.set_title('申万一级行业 F1 方差占比热力图 (120日窗口)', fontsize=14, fontweight='bold')
    ax.set_xlabel('日期', fontsize=12)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    logger.info(f"行业热力图已保存: {output_path}")
    return output_path
