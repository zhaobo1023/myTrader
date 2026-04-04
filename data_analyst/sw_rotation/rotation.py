"""
申万31行业轮动监控工具
功能：
  1. 自动拉取申万一级行业历史行情（akshare）
  2. 计算20日/250日相对强弱历史分位得分
  3. 生成周度热力图（行业趋势追踪）
  4. 生成当前排名图（含过热/上升预警标注）

依赖安装：
  pip install akshare pandas numpy matplotlib seaborn

作者：Claude for 铂
"""

import warnings
warnings.filterwarnings("ignore")

import akshare as ak
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from matplotlib import rcParams
from datetime import datetime, timedelta
import os

# ── 中文字体配置 ──────────────────────────────────────────────
# macOS 用 Heiti TC / Arial Unicode MS，Windows 用 SimHei，Linux 用 Noto Sans CJK
import platform
if platform.system() == "Darwin":
    rcParams["font.family"] = ["Heiti TC", "STHeiti", "Arial Unicode MS", "sans-serif"]
elif platform.system() == "Windows":
    rcParams["font.family"] = ["SimHei", "Microsoft YaHei", "sans-serif"]
else:
    rcParams["font.family"] = ["Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans"]
rcParams["axes.unicode_minus"] = False


# ══════════════════════════════════════════════════════════════
# 1. 数据获取
# ══════════════════════════════════════════════════════════════

def fetch_sw_industry_data(start_date: str = "20230101") -> pd.DataFrame:
    """
    拉取申万一级行业指数行情
    返回：DataFrame，index=日期，columns=行业名称，值=收盘点位
    """
    print("正在获取申万一级行业列表...")

    # 获取申万一级行业列表
    sw_df = ak.sw_index_first_info()
    print(f"共找到 {len(sw_df)} 个一级行业")

    all_close = {}

    for _, row in sw_df.iterrows():
        index_code = row["行业代码"]  # 更新后的列名
        index_name = row["行业名称"]

        try:
            # 使用 index_hist_sw 获取历史数据
            df = ak.index_hist_sw(symbol=index_code.replace('.SI', ''), period='day')
            if df is not None and len(df) > 0:
                df["日期"] = pd.to_datetime(df["日期"])
                df = df.set_index("日期").sort_index()

                # 过滤起始日期
                start_dt = pd.to_datetime(start_date)
                df = df[df.index >= start_dt]

                all_close[index_name] = df["收盘"]
                print(f"  ✓ {index_name} ({index_code}): {len(df)} 条记录")
        except Exception as e:
            print(f"  ✗ {index_name} ({index_code}): 获取失败 - {e}")

    price_df = pd.DataFrame(all_close).sort_index()
    price_df = price_df.dropna(how="all")
    print(f"\n数据获取完成，共 {len(price_df.columns)} 个行业，{len(price_df)} 个交易日")
    return price_df


# ══════════════════════════════════════════════════════════════
# 2. 指标计算
# ══════════════════════════════════════════════════════════════

def calc_return(price_df: pd.DataFrame, window: int) -> pd.DataFrame:
    """计算N日收益率"""
    return price_df.pct_change(window) * 100


def calc_percentile_rank(series: pd.Series, lookback: int = 250) -> pd.Series:
    """
    对收益率序列做滚动历史分位数排名（0-100）
    即：当前值在过去 lookback 天中比多少%的时候更强
    """
    def rank_pct(x):
        if len(x) < 10:
            return np.nan
        return (x[-1] > x[:-1]).sum() / (len(x) - 1) * 100

    return series.rolling(lookback, min_periods=max(20, lookback // 5)).apply(rank_pct, raw=True)


def calc_scores(price_df: pd.DataFrame,
                return_window: int = 20,
                rank_lookback: int = 250) -> pd.DataFrame:
    """
    计算每个行业的历史分位得分
    return_window:  计算收益率用的窗口（20=月收益，250=年收益）
    rank_lookback:  滚动排名回望窗口（用过去多少天的分布来打分）
    """
    ret = calc_return(price_df, return_window)
    scores = {}
    for col in ret.columns:
        scores[col] = calc_percentile_rank(ret[col], lookback=rank_lookback)
    return pd.DataFrame(scores)


def get_weekly_scores(scores_df: pd.DataFrame, n_weeks: int = 16) -> pd.DataFrame:
    """
    将日度得分重采样为周度（取每周最后一个交易日），取最近 n_weeks 周
    """
    weekly = scores_df.resample("W-FRI").last()
    # 去掉最新一周（可能不完整）
    weekly = weekly.iloc[:-1]
    return weekly.tail(n_weeks)


# ══════════════════════════════════════════════════════════════
# 3. 信号检测
# ══════════════════════════════════════════════════════════════

def detect_signals(weekly_scores: pd.DataFrame,
                   rising_window: int = 3,
                   hot_threshold: float = 85.0,
                   rising_min_gain: float = 5.0) -> dict:
    """
    检测行业信号：
    - rising:  最近 rising_window 周连续上升且累计涨幅 > rising_min_gain
    - hot:     当前得分 > hot_threshold（过热预警）
    - cooling: 上周得分 > hot_threshold，本周 < hot_threshold（降温信号）
    """
    current = weekly_scores.iloc[-1]
    signals = {"rising": [], "hot": [], "cooling": []}

    for col in weekly_scores.columns:
        series = weekly_scores[col].dropna()
        if len(series) < rising_window + 1:
            continue

        recent = series.iloc[-(rising_window):]
        # 连续上升
        is_rising = all(recent.iloc[i] < recent.iloc[i+1] for i in range(len(recent)-1))
        gain = recent.iloc[-1] - recent.iloc[-rising_window]

        if is_rising and gain >= rising_min_gain:
            signals["rising"].append(col)

        score = current.get(col, np.nan)
        if pd.notna(score):
            if score >= hot_threshold:
                signals["hot"].append(col)
            elif len(series) >= 2 and series.iloc[-2] >= hot_threshold and score < hot_threshold:
                signals["cooling"].append(col)

    return signals


def detect_signals_for_week(weekly_scores: pd.DataFrame,
                            week_idx: int,
                            rising_window: int = 3,
                            hot_threshold: float = 85.0,
                            rising_min_gain: float = 5.0) -> dict:
    """
    检测指定周的信号（用于历史回溯）
    week_idx: 从最新周往前数，0=最新周，1=上周，以此类推
    """
    if week_idx >= len(weekly_scores):
        return {"rising": [], "hot": [], "cooling": []}

    # 截取到目标周的数据
    scores_up_to_week = weekly_scores.iloc[:len(weekly_scores) - week_idx]
    if len(scores_up_to_week) < 2:
        return {"rising": [], "hot": [], "cooling": []}

    current = scores_up_to_week.iloc[-1]
    signals = {"rising": [], "hot": [], "cooling": []}

    for col in scores_up_to_week.columns:
        series = scores_up_to_week[col].dropna()
        if len(series) < rising_window + 1:
            continue

        recent = series.iloc[-(rising_window):]
        is_rising = all(recent.iloc[i] < recent.iloc[i+1] for i in range(len(recent)-1))
        gain = recent.iloc[-1] - recent.iloc[-rising_window]

        if is_rising and gain >= rising_min_gain:
            signals["rising"].append(col)

        score = current.get(col, np.nan)
        if pd.notna(score):
            if score >= hot_threshold:
                signals["hot"].append(col)
            elif len(series) >= 2 and series.iloc[-2] >= hot_threshold and score < hot_threshold:
                signals["cooling"].append(col)

    return signals


def get_historical_signals(weekly_scores: pd.DataFrame,
                           n_weeks: int = 4,
                           rising_window: int = 3,
                           hot_threshold: float = 85.0) -> pd.DataFrame:
    """
    获取过去N周的信号历史
    返回：DataFrame，index=行业，columns=各周的信号状态
    """
    all_industries = weekly_scores.columns.tolist()
    history = {ind: [] for ind in all_industries}
    week_labels = []

    for week_idx in range(n_weeks):
        if week_idx >= len(weekly_scores):
            break

        week_date = weekly_scores.index[-(week_idx + 1)].strftime("%m/%d")
        week_labels.append(week_date)

        signals = detect_signals_for_week(
            weekly_scores, week_idx,
            rising_window=rising_window,
            hot_threshold=hot_threshold
        )

        for ind in all_industries:
            if ind in signals["hot"]:
                history[ind].append("🔥")
            elif ind in signals["cooling"]:
                history[ind].append("❄")
            elif ind in signals["rising"]:
                history[ind].append("↑")
            else:
                history[ind].append("")

    df = pd.DataFrame(history, index=week_labels).T
    return df


def print_signal_history(weekly_scores: pd.DataFrame,
                         n_weeks: int = 4,
                         rising_window: int = 3,
                         hot_threshold: float = 85.0):
    """
    打印过去N周的信号变化表格
    """
    print(f"\n{'='*80}")
    print(f"📊 过去 {n_weeks} 周信号变化追踪")
    print(f"{'='*80}")

    # 获取周度得分
    week_dates = []
    for week_idx in range(min(n_weeks, len(weekly_scores))):
        week_date = weekly_scores.index[-(week_idx + 1)].strftime("%Y-%m-%d")
        week_dates.append(week_date)

    # 按最新周得分排序
    sorted_industries = weekly_scores.iloc[-1].sort_values(ascending=False).index.tolist()

    # 打印表头
    header = f"{'行业':<10}"
    for i, wd in enumerate(week_dates):
        if i == 0:
            header += f" | {wd}(最新)"
        else:
            header += f" | {wd}"
    print(header)
    print("-" * len(header))

    # 打印每个行业
    for ind in sorted_industries:
        row = f"{ind:<10}"
        for week_idx in range(min(n_weeks, len(weekly_scores))):
            signals = detect_signals_for_week(
                weekly_scores, week_idx,
                rising_window=rising_window,
                hot_threshold=hot_threshold
            )
            score = weekly_scores.iloc[-(week_idx + 1)][ind]

            signal_str = ""
            if ind in signals["hot"]:
                signal_str = "🔥"
            elif ind in signals["cooling"]:
                signal_str = "❄"
            elif ind in signals["rising"]:
                signal_str = "↑"

            row += f" | {score:5.1f}{signal_str}"
        print(row)

    print("-" * len(header))
    print("图例: 🔥过热(>85) | ❄降温 | ↑上升中\n")


def get_signal_changes(weekly_scores: pd.DataFrame,
                       n_weeks: int = 4,
                       hot_threshold: float = 85.0) -> dict:
    """
    分析信号变化：新增、消失、持续
    """
    changes = {
        "new_hot": [],       # 新增过热
        "exit_hot": [],      # 退出过热
        "sustained_hot": [], # 持续过热
        "new_rising": [],    # 新增上升
        "new_cooling": [],   # 新增降温
    }

    if len(weekly_scores) < 2:
        return changes

    current_signals = detect_signals_for_week(weekly_scores, 0, hot_threshold=hot_threshold)
    prev_signals = detect_signals_for_week(weekly_scores, 1, hot_threshold=hot_threshold)

    # 过热变化
    changes["new_hot"] = list(set(current_signals["hot"]) - set(prev_signals["hot"]))
    changes["exit_hot"] = list(set(prev_signals["hot"]) - set(current_signals["hot"]))
    changes["sustained_hot"] = list(set(current_signals["hot"]) & set(prev_signals["hot"]))

    # 上升变化
    changes["new_rising"] = list(set(current_signals["rising"]) - set(prev_signals["rising"]))

    # 降温信号
    changes["new_cooling"] = current_signals["cooling"]

    return changes


# ══════════════════════════════════════════════════════════════
# 4. 绘图
# ══════════════════════════════════════════════════════════════

def plot_weekly_heatmap(weekly_scores: pd.DataFrame,
                        signals: dict,
                        title_suffix: str = "20日收益 / 250日分位",
                        output_dir: str = "."):
    """
    周度热力图：行业（行）× 周（列），颜色=得分
    右侧标注信号图标
    """
    # 按最新一周得分降序排列
    sorted_cols = weekly_scores.iloc[-1].sort_values(ascending=False).index.tolist()
    data = weekly_scores[sorted_cols].T  # 行=行业，列=周

    # 列标签：周结束日期
    col_labels = [d.strftime("%m/%d") for d in data.columns]

    fig_h = max(10, len(sorted_cols) * 0.38)
    fig, ax = plt.subplots(figsize=(16, fig_h))

    # 自定义颜色：蓝(弱) → 白(中) → 红(强)
    cmap = sns.diverging_palette(220, 10, as_cmap=True)

    sns.heatmap(
        data,
        ax=ax,
        cmap=cmap,
        vmin=0, vmax=100,
        center=50,
        linewidths=0.4,
        linecolor="#cccccc",
        annot=True,
        fmt=".0f",
        annot_kws={"size": 7},
        cbar_kws={"label": "历史分位得分 (0-100)", "shrink": 0.6},
        xticklabels=col_labels,
    )

    # 行业名称：附加信号图标
    ylabels = []
    for name in sorted_cols:
        tag = ""
        if name in signals["hot"]:
            tag = " 🔥"
        elif name in signals["rising"]:
            tag = " ↑"
        elif name in signals["cooling"]:
            tag = " ❄"
        ylabels.append(name + tag)

    ax.set_yticklabels(ylabels, fontsize=9, rotation=0)
    ax.set_xticklabels(ax.get_xticklabels(), fontsize=8, rotation=45, ha="right")
    ax.set_xlabel("周（结束日）", fontsize=10)
    ax.set_ylabel("")

    today = datetime.today().strftime("%Y-%m-%d")
    ax.set_title(f"申万31行业 周度强弱热力图  [{title_suffix}]  更新：{today}",
                 fontsize=13, fontweight="bold", pad=12)

    # 图例
    legend_items = [
        mpatches.Patch(color="none", label="🔥 过热预警（分位 > 85）"),
        mpatches.Patch(color="none", label="↑  连续上升中"),
        mpatches.Patch(color="none", label="❄  高位降温"),
    ]
    ax.legend(handles=legend_items, loc="lower right",
              bbox_to_anchor=(1.18, -0.08), fontsize=9, framealpha=0.8)

    plt.tight_layout()
    filename = os.path.join(output_dir, f"sw_heatmap_{today}.png")
    plt.savefig(filename, dpi=150, bbox_inches="tight")
    print(f"热力图已保存：{filename}")
    plt.close()


def plot_rank_bar(current_scores_20: pd.Series,
                  current_scores_250: pd.Series,
                  signals: dict,
                  output_dir: str = "."):
    """
    双周期横向条形图：
    - 深色=250日分位（年线视角）
    - 浅色=20日分位（月线视角）
    - 标注过热/上升信号
    """
    # 按250日分位排序
    sorted_idx = current_scores_250.sort_values(ascending=True).index
    y = np.arange(len(sorted_idx))

    fig, ax = plt.subplots(figsize=(12, max(10, len(sorted_idx) * 0.38)))

    # 250日（深蓝）
    bars_250 = ax.barh(y - 0.2, current_scores_250[sorted_idx],
                        height=0.35, color="#1f6bb0", alpha=0.9, label="250日分位（年线）")
    # 20日（浅蓝）
    bars_20 = ax.barh(y + 0.2, current_scores_20[sorted_idx],
                       height=0.35, color="#74b9e8", alpha=0.85, label="20日分位（月线）")

    # 数值标注
    for bar in bars_250:
        w = bar.get_width()
        if pd.notna(w):
            ax.text(w + 0.5, bar.get_y() + bar.get_height()/2,
                    f"{w:.0f}", va="center", ha="left", fontsize=7, color="#1f6bb0")
    for bar in bars_20:
        w = bar.get_width()
        if pd.notna(w):
            ax.text(w + 0.5, bar.get_y() + bar.get_height()/2,
                    f"{w:.0f}", va="center", ha="left", fontsize=7, color="#2980b9")

    # Y轴标签 + 信号标注
    ylabels = []
    for name in sorted_idx:
        tag = ""
        if name in signals["hot"]:
            tag = " 🔥"
        elif name in signals["rising"]:
            tag = " ↑"
        elif name in signals["cooling"]:
            tag = " ❄"
        ylabels.append(name + tag)
    ax.set_yticks(y)
    ax.set_yticklabels(ylabels, fontsize=9)

    # 参考线
    for xv, ls, c, lbl in [(50, "--", "gray", "中位线(50)"),
                             (85, "-.", "red", "过热线(85)"),
                             (15, "-.", "green", "超卖线(15)")]:
        ax.axvline(xv, linestyle=ls, color=c, alpha=0.6, linewidth=1.2, label=lbl)

    ax.set_xlim(0, 110)
    ax.set_xlabel("历史分位得分 (0-100)", fontsize=10)
    today = datetime.today().strftime("%Y-%m-%d")
    ax.set_title(f"申万31行业 当前相对强弱排名  更新：{today}",
                 fontsize=13, fontweight="bold", pad=12)
    ax.legend(loc="lower right", fontsize=9)

    plt.tight_layout()
    filename = os.path.join(output_dir, f"sw_rank_{today}.png")
    plt.savefig(filename, dpi=150, bbox_inches="tight")
    print(f"排名图已保存：{filename}")
    plt.close()


# ══════════════════════════════════════════════════════════════
# 5. 主流程
# ══════════════════════════════════════════════════════════════

def main():
    # ── 参数配置 ──────────────────────────────────────────────
    START_DATE = "20230101"     # 数据起始日（越早分位计算越准，但拉取越慢）
    RETURN_WINDOW_SHORT = 20    # 月线收益窗口
    RETURN_WINDOW_LONG = 250    # 年线收益窗口（仅用于排名图对比）
    RANK_LOOKBACK = 250         # 历史分位回望窗口（用多少天分布打分）
    N_WEEKS_HEATMAP = 16        # 热力图展示最近几周
    HOT_THRESHOLD = 85          # 过热预警阈值
    RISING_WINDOW = 3           # 连续上升检测窗口（周）

    # 输出目录
    OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "sw_rotation")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # ──────────────────────────────────────────────────────────

    # 1. 获取数据
    price_df = fetch_sw_industry_data(START_DATE)

    if price_df.empty:
        print("数据获取失败，请检查网络或akshare版本")
        return

    # 2. 计算两个周期得分
    print("\n计算20日收益 / 250日历史分位得分...")
    scores_20d = calc_scores(price_df, return_window=RETURN_WINDOW_SHORT, rank_lookback=RANK_LOOKBACK)

    print("计算250日收益 / 250日历史分位得分...")
    scores_250d = calc_scores(price_df, return_window=RETURN_WINDOW_LONG, rank_lookback=RANK_LOOKBACK)

    # 3. 提取当前值
    current_20 = scores_20d.iloc[-1].dropna()
    current_250 = scores_250d.iloc[-1].dropna()

    # 4. 周度序列（用20日收益分位做热力图，更敏感）
    weekly_20 = get_weekly_scores(scores_20d, n_weeks=N_WEEKS_HEATMAP)

    # 5. 检测信号
    signals = detect_signals(weekly_20, rising_window=RISING_WINDOW, hot_threshold=HOT_THRESHOLD)

    print("\n══ 当前信号汇总 ══")
    print(f"🔥 过热预警（250日分位 > {HOT_THRESHOLD}）: {signals['hot'] if signals['hot'] else '无'}")
    print(f"↑  连续上升（近{RISING_WINDOW}周）: {signals['rising'] if signals['rising'] else '无'}")
    print(f"❄  高位降温: {signals['cooling'] if signals['cooling'] else '无'}")

    # 5.5 打印历史信号变化
    print_signal_history(weekly_20, n_weeks=4, rising_window=RISING_WINDOW, hot_threshold=HOT_THRESHOLD)

    # 分析信号变化
    changes = get_signal_changes(weekly_20, n_weeks=4, hot_threshold=HOT_THRESHOLD)
    print("📈 信号变化分析:")
    if changes["new_hot"]:
        print(f"  🆕 新增过热: {changes['new_hot']}")
    if changes["exit_hot"]:
        print(f"  📉 退出过热: {changes['exit_hot']}")
    if changes["sustained_hot"]:
        print(f"  ⚠️  持续过热: {changes['sustained_hot']}")
    if changes["new_rising"]:
        print(f"  🆕 新增上升: {changes['new_rising']}")
    if changes["new_cooling"]:
        print(f"  🧊 新增降温: {changes['new_cooling']}")

    # 6. 绘图
    print("\n绘制热力图...")
    plot_weekly_heatmap(weekly_20, signals, title_suffix=f"{RETURN_WINDOW_SHORT}日收益 / {RANK_LOOKBACK}日分位", output_dir=OUTPUT_DIR)

    print("绘制排名对比图...")
    # 取两个得分的公共行业
    common = current_20.index.intersection(current_250.index)
    plot_rank_bar(current_20[common], current_250[common], signals, output_dir=OUTPUT_DIR)

    # 7. 输出CSV方便自己二次分析
    today = datetime.today().strftime("%Y-%m-%d")

    # 获取过去4周的得分
    weekly_scores_history = []
    for week_idx in range(min(4, len(weekly_20))):
        week_date = weekly_20.index[-(week_idx + 1)].strftime("%Y-%m-%d")
        week_scores = weekly_20.iloc[-(week_idx + 1)]
        weekly_scores_history.append((week_date, week_scores))

    out = pd.DataFrame({
        "行业": common,
        "20日分位得分": current_20[common].values,
        "250日分位得分": current_250[common].values,
        "过热": [1 if c in signals["hot"] else 0 for c in common],
        "连续上升": [1 if c in signals["rising"] else 0 for c in common],
        "高位降温": [1 if c in signals["cooling"] else 0 for c in common],
    })

    # 添加过去4周的得分
    for week_date, week_scores in weekly_scores_history:
        col_name = f"得分_{week_date}"
        out[col_name] = [week_scores.get(c, np.nan) for c in out["行业"]]

    out = out.sort_values("250日分位得分", ascending=False)
    csv_name = os.path.join(OUTPUT_DIR, f"sw_scores_{today}.csv")
    out.to_csv(csv_name, index=False, encoding="utf-8-sig")
    print(f"\n得分数据已导出：{csv_name}")
    print("\n完成！")


if __name__ == "__main__":
    main()
