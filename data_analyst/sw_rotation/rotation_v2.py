"""
申万31行业轮动周报 v2
────────────────────────────────────────────────────────
改进点：
  1. 增加「截面排名分位」 —— 和参考图对齐，31个行业互相比
  2. 增加「动量得分」 —— 最近4周得分变化斜率，捕捉趋势
  3. 信号逻辑升级：上升/退潮/背离（年强月弱/年弱月强）
  4. 输出HTML周报，无需额外工具，浏览器直接看
  5. 保留原有热力图 + 排名图

依赖：pip install akshare pandas numpy scipy
      (matplotlib 仅在生成图片时需要，非必需)
"""

import warnings; warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
from datetime import datetime
from scipy import stats
import json, os, platform, sys

# Optional dependencies - imported inside functions that need them
# - akshare: only for fetch_data()
# - matplotlib: only for plot_heatmap() and plot_quadrant()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TODAY = datetime.today().strftime("%Y-%m-%d")
TODAY_COMPACT = datetime.today().strftime("%Y%m%d")


# ══════════════════════════════════════════════════════════════
# 1. 数据获取
# ══════════════════════════════════════════════════════════════

def fetch_data(start_date="20230101") -> pd.DataFrame:
    """Fetch SW industry data from AKShare."""
    try:
        import akshare as ak
    except ImportError:
        raise ImportError("fetch_data requires akshare. Install it with: pip install akshare")

    print("拉取申万一级行业数据...")
    sw_df = ak.sw_index_first_info()
    all_close = {}
    for _, row in sw_df.iterrows():
        code, name = row["指数代码"], row["指数名称"]
        try:
            df = ak.sw_index_daily_indicator(
                symbol=code, start_date=start_date,
                end_date=TODAY_COMPACT
            )
            if df is not None and len(df) > 0:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                col = "close" if "close" in df.columns else df.columns[0]
                all_close[name] = df[col].astype(float)
                print(f"  ✓ {name}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")
    price_df = pd.DataFrame(all_close).sort_index().dropna(how="all")
    print(f"完成：{len(price_df.columns)} 个行业 / {len(price_df)} 个交易日\n")
    return price_df


# ══════════════════════════════════════════════════════════════
# 2. 核心指标计算
# ══════════════════════════════════════════════════════════════

def rolling_hist_pct(series: pd.Series, ret_window: int, lookback: int) -> pd.Series:
    """纵向分位：自己和自己的历史比"""
    ret = series.pct_change(ret_window) * 100
    def rank(x):
        if len(x) < 10: return np.nan
        return (x[-1] > x[:-1]).sum() / (len(x)-1) * 100
    return ret.rolling(lookback, min_periods=max(20, lookback//5)).apply(rank, raw=True)


def cross_section_pct(price_df: pd.DataFrame, ret_window: int) -> pd.DataFrame:
    """
    横向截面分位：每个交易日，该行业涨幅在31个行业中排第几百分位
    ——和参考图逻辑一致
    """
    ret = price_df.pct_change(ret_window)
    def row_pct(row):
        valid = row.dropna()
        if len(valid) < 5: return pd.Series(np.nan, index=row.index)
        ranks = valid.rank(pct=True) * 100
        return ranks.reindex(row.index)
    return ret.apply(row_pct, axis=1)


def momentum_slope(weekly_scores: pd.DataFrame, window: int = 4) -> pd.Series:
    """
    近 window 周得分的线性斜率 → 正=上升趋势 负=下降趋势
    标准化为 z-score 方便横向比较
    """
    recent = weekly_scores.tail(window)
    slopes = {}
    x = np.arange(len(recent))
    for col in recent.columns:
        y = recent[col].values
        if np.isnan(y).sum() > len(y)//2:
            slopes[col] = np.nan
        else:
            mask = ~np.isnan(y)
            if mask.sum() < 2:
                slopes[col] = np.nan
            else:
                slope, *_ = np.polyfit(x[mask], y[mask], 1)
                slopes[col] = slope
    s = pd.Series(slopes)
    # z-score 标准化
    return (s - s.mean()) / (s.std() + 1e-9)


def calc_all_metrics(price_df: pd.DataFrame,
                     short_w=20, long_w=250, lookback=250) -> dict:
    """计算所有指标，返回字典"""
    print("计算纵向历史分位...")
    hist_short = pd.DataFrame({c: rolling_hist_pct(price_df[c], short_w, lookback)
                                for c in price_df.columns})
    hist_long  = pd.DataFrame({c: rolling_hist_pct(price_df[c], long_w, lookback)
                                for c in price_df.columns})

    print("计算横向截面分位...")
    cross_short = cross_section_pct(price_df, short_w)
    cross_long  = cross_section_pct(price_df, long_w)

    return dict(hist_short=hist_short, hist_long=hist_long,
                cross_short=cross_short, cross_long=cross_long)


# ══════════════════════════════════════════════════════════════
# 3. 信号检测（升级版）
# ══════════════════════════════════════════════════════════════

def detect_signals_v2(weekly_hist: pd.DataFrame,
                      current_hist_short: pd.Series,
                      current_hist_long:  pd.Series,
                      current_cross_short: pd.Series,
                      hot_thr=85, cold_thr=15,
                      rise_w=3, rise_min=5) -> pd.DataFrame:
    """
    返回 DataFrame，每行一个行业，列为各信号
    信号说明：
      rising     — 近 rise_w 周持续上升
      hot        — 当前历史长期分位 > hot_thr
      cooling    — 上周 > hot_thr，本周 < hot_thr
      diverge_up — 短期（20日）远强于长期（250日），可能是趋势启动初期
      diverge_dn — 长期强但短期弱，高位退潮信号
    """
    slope_z = momentum_slope(weekly_hist, window=rise_w+1)
    rows = []
    industries = current_hist_short.index.intersection(current_hist_long.index)

    for name in industries:
        cur_s = current_hist_short.get(name, np.nan)
        cur_l = current_hist_long.get(name, np.nan)
        cur_c = current_cross_short.get(name, np.nan)
        slp   = slope_z.get(name, 0)

        series = weekly_hist[name].dropna() if name in weekly_hist.columns else pd.Series()

        # 连续上升
        rising = False
        if len(series) >= rise_w:
            recent = series.iloc[-rise_w:]
            rising = (all(recent.iloc[i] < recent.iloc[i+1] for i in range(len(recent)-1))
                      and (recent.iloc[-1] - recent.iloc[0]) >= rise_min)

        # 过热: 长期分位高 AND 短期分位也高（当前依然强势）
        # 修正: 只看长期分位不够，必须短期也强才算"过热"
        # 长期高但短期低 = 高位退潮，不是过热
        hot = (pd.notna(cur_l) and pd.notna(cur_s)
               and cur_l >= hot_thr and cur_s >= 60)

        # 降温: 上周过热，本周不过热
        cooling = False
        if len(series) >= 2:
            prev_l = series.iloc[-2] if len(series) >= 2 else np.nan
            cooling = (pd.notna(prev_l) and prev_l >= hot_thr and pd.notna(cur_l) and cur_l < hot_thr)

        # 背离信号
        # 短强长弱: 短期突然发力，历史上低位 → 趋势启动候选
        diverge_up = (pd.notna(cur_s) and pd.notna(cur_l)
                      and cur_s >= 60 and cur_l <= 40)

        # 长强短弱: 长期高位但近期动能不足 → 高位退潮/减仓信号
        # 放宽条件: 长期>=70 且 短期<=35 (覆盖更多"高位回调"情况)
        diverge_dn = (pd.notna(cur_s) and pd.notna(cur_l)
                      and cur_l >= 70 and cur_s <= 35)

        # 互斥: 高位退潮/过热优先，取消连续上升标记
        # 语义上"退潮/过热"和"持续上升"矛盾，风险信号应优先展示
        if diverge_dn or hot:
            rising = False

        rows.append(dict(
            行业=name,
            短期分位=round(cur_s, 1) if pd.notna(cur_s) else None,
            长期分位=round(cur_l, 1) if pd.notna(cur_l) else None,
            截面分位=round(cur_c, 1) if pd.notna(cur_c) else None,
            动量斜率=round(float(slp), 2),
            过热=hot, 降温=cooling, 连续上升=rising,
            短强长弱=diverge_up, 长强短弱=diverge_dn,
        ))

    df = pd.DataFrame(rows).set_index("行业")
    return df


# ══════════════════════════════════════════════════════════════
# 4. 绘图
# ══════════════════════════════════════════════════════════════

def plot_heatmap(weekly_scores: pd.DataFrame, sig_df: pd.DataFrame, fname: str):
    # Import matplotlib only when plotting (soft dependency)
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import seaborn as sns
        from matplotlib import rcParams
    except ImportError:
        raise ImportError("plot_heatmap requires matplotlib. Install it with: pip install matplotlib")

    # Configure font for Chinese characters
    if platform.system() == "Darwin":
        rcParams["font.family"] = ["PingFang SC", "Heiti TC"]
    elif platform.system() == "Windows":
        rcParams["font.family"] = ["SimHei", "Microsoft YaHei"]
    else:
        rcParams["font.family"] = ["Noto Sans CJK SC", "DejaVu Sans"]
    rcParams["axes.unicode_minus"] = False

    sorted_cols = weekly_scores.iloc[-1].sort_values(ascending=False).index.tolist()
    data = weekly_scores[sorted_cols].T
    col_labels = [d.strftime("%m/%d") for d in data.columns]

    fig_h = max(10, len(sorted_cols) * 0.38)
    fig, ax = plt.subplots(figsize=(18, fig_h))
    cmap = sns.diverging_palette(220, 10, as_cmap=True)

    sns.heatmap(data, ax=ax, cmap=cmap, vmin=0, vmax=100, center=50,
                linewidths=0.4, linecolor="#cccccc",
                annot=True, fmt=".0f", annot_kws={"size": 7},
                cbar_kws={"label": "历史分位得分 (0-100)", "shrink": 0.6},
                xticklabels=col_labels)

    ylabels = []
    for name in sorted_cols:
        tags = []
        if name in sig_df.index:
            r = sig_df.loc[name]
            if r["过热"]:          tags.append("🔥")
            if r["连续上升"]:      tags.append("↑")
            if r["降温"]:          tags.append("❄")
            if r["短强长弱"]:      tags.append("★")  # 趋势启动候选
            if r["长强短弱"]:      tags.append("⚠")   # 高位退潮
        ylabels.append(name + (" " + "".join(tags) if tags else ""))

    ax.set_yticklabels(ylabels, fontsize=9, rotation=0)
    ax.set_xticklabels(ax.get_xticklabels(), fontsize=8, rotation=45, ha="right")
    ax.set_title(f"申万31行业 周度强弱热力图（20日收益/250日历史分位）  {TODAY}",
                 fontsize=13, fontweight="bold", pad=12)

    legend_items = [
        mpatches.Patch(color="none", label="🔥 过热（长期>85）"),
        mpatches.Patch(color="none", label="↑  连续上升中"),
        mpatches.Patch(color="none", label="❄  高位降温"),
        mpatches.Patch(color="none", label="★  短强长弱（趋势启动候选）"),
        mpatches.Patch(color="none", label="⚠  长强短弱（高位退潮警告）"),
    ]
    ax.legend(handles=legend_items, loc="lower right",
              bbox_to_anchor=(1.22, -0.06), fontsize=8, framealpha=0.8)

    plt.tight_layout()
    plt.savefig(fname, dpi=150, bbox_inches="tight")
    print(f"  热力图：{fname}")
    plt.close()


def plot_quadrant(sig_df: pd.DataFrame, fname: str):
    """
    四象限图：X轴=长期分位（年线强弱），Y轴=短期分位（月线动量）
    四个区域：
      右上 — 长强短强（强者恒强，但警惕过热）
      右下 — 长强短弱（高位退潮，减仓信号）
      左上 — 长弱短强（趋势启动，进攻信号）
      左下 — 长弱短弱（持续弱势，回避）
    """
    # Import matplotlib only when plotting (soft dependency)
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from matplotlib import rcParams
    except ImportError:
        raise ImportError("plot_quadrant requires matplotlib. Install it with: pip install matplotlib")

    # Configure font for Chinese characters
    if platform.system() == "Darwin":
        rcParams["font.family"] = ["PingFang SC", "Heiti TC"]
    elif platform.system() == "Windows":
        rcParams["font.family"] = ["SimHei", "Microsoft YaHei"]
    else:
        rcParams["font.family"] = ["Noto Sans CJK SC", "DejaVu Sans"]
    rcParams["axes.unicode_minus"] = False

    df = sig_df.dropna(subset=["短期分位", "长期分位"])
    x = df["长期分位"]
    y = df["短期分位"]

    fig, ax = plt.subplots(figsize=(12, 10))

    # 背景四象限
    ax.axhspan(50, 105, xmin=0, xmax=0.5, alpha=0.06, color="green")   # 左上
    ax.axhspan(50, 105, xmin=0.5, xmax=1,  alpha=0.06, color="red")    # 右上
    ax.axhspan(-5, 50,  xmin=0.5, xmax=1,  alpha=0.08, color="orange") # 右下
    ax.axhspan(-5, 50,  xmin=0, xmax=0.5,  alpha=0.04, color="gray")   # 左下

    # 参考线
    ax.axvline(50, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.axhline(50, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.axvline(85, color="red",  linewidth=0.8, linestyle="-.", alpha=0.4)
    ax.axhline(85, color="red",  linewidth=0.8, linestyle="-.", alpha=0.4)

    # 散点
    colors = []
    for name in df.index:
        r = df.loc[name]
        if r["过热"]:       colors.append("#e74c3c")
        elif r["短强长弱"]: colors.append("#27ae60")
        elif r["长强短弱"]: colors.append("#e67e22")
        elif r["连续上升"]: colors.append("#2980b9")
        else:               colors.append("#95a5a6")

    sc = ax.scatter(x, y, c=colors, s=120, alpha=0.85, zorder=3, edgecolors="white", linewidths=0.6)

    # 标签
    for name in df.index:
        xi, yi = df.loc[name, "长期分位"], df.loc[name, "短期分位"]
        ax.annotate(name, (xi, yi), fontsize=8,
                    xytext=(4, 4), textcoords="offset points",
                    color="#2c3e50")

    # 象限标注
    for txt, tx, ty in [("强者恒强\n(过热警戒区)", 88, 88),
                         ("趋势启动候选\n(进攻区)", 8, 88),
                         ("高位退潮\n(减仓区)", 88, 8),
                         ("持续弱势\n(回避区)", 8, 8)]:
        ax.text(tx, ty, txt, fontsize=8, color="#7f8c8d", ha="left", va="bottom", alpha=0.7)

    # 图例
    legend_items = [
        mpatches.Patch(color="#e74c3c", label="🔥 过热（长期>85）"),
        mpatches.Patch(color="#27ae60", label="★ 趋势启动候选（短强长弱）"),
        mpatches.Patch(color="#e67e22", label="⚠ 高位退潮（长强短弱）"),
        mpatches.Patch(color="#2980b9", label="↑ 连续上升中"),
        mpatches.Patch(color="#95a5a6", label="中性"),
    ]
    ax.legend(handles=legend_items, fontsize=9, loc="upper left")

    ax.set_xlim(-5, 105)
    ax.set_ylim(-5, 105)
    ax.set_xlabel("长期分位（250日收益/250日历史）", fontsize=11)
    ax.set_ylabel("短期分位（20日收益/250日历史）", fontsize=11)
    ax.set_title(f"申万31行业 强弱四象限  {TODAY}", fontsize=13, fontweight="bold")

    plt.tight_layout()
    plt.savefig(fname, dpi=150, bbox_inches="tight")
    print(f"  四象限图：{fname}")
    plt.close()


# ══════════════════════════════════════════════════════════════
# 5. HTML 周报生成
# ══════════════════════════════════════════════════════════════

def gen_html_report(sig_df: pd.DataFrame,
                    heatmap_file: str, quadrant_file: str,
                    out_file: str):
    """生成可直接在浏览器查看的 HTML 周报"""

    hot     = sig_df[sig_df["过热"]].index.tolist()
    rising  = sig_df[sig_df["连续上升"] & ~sig_df["过热"]].index.tolist()
    cooling = sig_df[sig_df["降温"]].index.tolist()
    startup = sig_df[sig_df["短强长弱"] & ~sig_df["过热"]].index.tolist()
    retreat = sig_df[sig_df["长强短弱"]].index.tolist()

    def tag(label, color, items):
        if not items: return ""
        badges = "".join(f'<span class="badge" style="background:{color}">{i}</span>' for i in items)
        return f'<div class="signal-row"><span class="sig-label">{label}</span>{badges}</div>'

    # 排名表格
    tbl_df = sig_df.sort_values("长期分位", ascending=False)[
        ["短期分位", "长期分位", "截面分位", "动量斜率"]
    ].reset_index()

    def fmt_row(r):
        tags = []
        row = sig_df.loc[r["行业"]]
        if row["过热"]:      tags.append('<span style="color:#e74c3c">🔥过热</span>')
        if row["连续上升"]:  tags.append('<span style="color:#2980b9">↑上升</span>')
        if row["降温"]:      tags.append('<span style="color:#3498db">❄降温</span>')
        if row["短强长弱"]:  tags.append('<span style="color:#27ae60">★启动</span>')
        if row["长强短弱"]:  tags.append('<span style="color:#e67e22">⚠退潮</span>')
        sig_html = " ".join(tags)
        ls = r["长期分位"]
        color = ("#fdecea" if ls >= 85 else
                 "#eaf4fb" if ls >= 50 else
                 "#f9f9f9")
        return (f'<tr style="background:{color}">'
                f'<td>{r["行业"]}</td>'
                f'<td>{r["短期分位"]}</td>'
                f'<td><b>{r["长期分位"]}</b></td>'
                f'<td>{r["截面分位"]}</td>'
                f'<td>{r["动量斜率"]}</td>'
                f'<td>{sig_html}</td>'
                f'</tr>')

    rows_html = "\n".join(tbl_df.apply(fmt_row, axis=1))

    # 图片 base64 嵌入
    import base64
    def img_b64(path):
        if not os.path.exists(path): return ""
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    hm_b64 = img_b64(heatmap_file)
    qd_b64 = img_b64(quadrant_file)

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>申万行业轮动周报 {TODAY}</title>
<style>
  body {{ font-family: "PingFang SC","Microsoft YaHei",sans-serif; background:#f4f6f9; margin:0; padding:20px; color:#2c3e50; }}
  h1 {{ font-size:22px; font-weight:700; margin-bottom:4px; }}
  .subtitle {{ color:#7f8c8d; font-size:13px; margin-bottom:24px; }}
  .card {{ background:#fff; border-radius:10px; padding:20px; margin-bottom:20px; box-shadow:0 1px 4px rgba(0,0,0,0.08); }}
  .card h2 {{ font-size:15px; font-weight:600; margin:0 0 14px; color:#34495e; border-left:4px solid #3498db; padding-left:10px; }}
  .signal-row {{ margin:6px 0; display:flex; align-items:center; flex-wrap:wrap; gap:6px; }}
  .sig-label {{ font-size:12px; color:#7f8c8d; width:130px; flex-shrink:0; }}
  .badge {{ display:inline-block; padding:3px 10px; border-radius:20px; color:#fff; font-size:12px; font-weight:500; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ background:#34495e; color:#fff; padding:8px 10px; text-align:left; font-weight:500; }}
  td {{ padding:7px 10px; border-bottom:1px solid #eee; }}
  img {{ max-width:100%; border-radius:8px; }}
  .row2 {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
  @media(max-width:800px) {{ .row2 {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<h1>📊 申万31行业轮动周报</h1>
<div class="subtitle">更新日期：{TODAY} &nbsp;|&nbsp; 分位计算：250日历史 &nbsp;|&nbsp; 短期窗口：20日 &nbsp;|&nbsp; 长期窗口：250日</div>

<div class="card">
  <h2>本周信号汇总</h2>
  {tag("🔥 过热预警", "#e74c3c", hot)}
  {tag("⚠ 高位退潮", "#e67e22", retreat)}
  {tag("❄ 降温信号", "#3498db", cooling)}
  {tag("↑ 连续上升中", "#2980b9", rising)}
  {tag("★ 趋势启动候选", "#27ae60", startup)}
  <p style="font-size:12px;color:#95a5a6;margin-top:10px">
    🔥过热预警：长期分位≥85 且 短期分位≥60（历史高位且当前依然强势，警惕追高风险）<br>
    ⚠高位退潮：长期分位≥70 且 短期分位≤35（长线高位但近期动能不足，注意减仓止盈）<br>
    ★趋势启动候选：短期分位≥60 且 长期分位≤40（短期突然发力，历史上少见，可能是趋势初期）
  </p>
</div>

<div class="card">
  <h2>行业详细得分排名（按长期分位降序）</h2>
  <table>
    <tr>
      <th>行业</th>
      <th>短期分位（20日）</th>
      <th>长期分位（250日）</th>
      <th>截面排名分位</th>
      <th>动量斜率(z)</th>
      <th>信号</th>
    </tr>
    {rows_html}
  </table>
</div>

<div class="row2">
  <div class="card">
    <h2>强弱四象限</h2>
    <img src="data:image/png;base64,{qd_b64}" alt="四象限">
    <p style="font-size:11px;color:#95a5a6;margin-top:8px">
      X轴=长期分位（年线视角）/ Y轴=短期分位（月线动量）<br>
      左上绿区=趋势启动候选 / 右上红区=过热警戒 / 右下橙区=高位退潮
    </p>
  </div>
  <div class="card">
    <h2>说明 & 操作框架</h2>
    <table>
      <tr><th>信号</th><th>含义</th><th>参考操作</th></tr>
      <tr><td>🔥过热</td><td>长期≥85且短期≥60，高位强势</td><td>警惕追高，考虑减仓</td></tr>
      <tr><td>⚠退潮</td><td>长期≥70但短期≤35，高位回调</td><td>关注止损位，逐步撤退</td></tr>
      <tr><td>❄降温</td><td>上周过热，本周跌破阈值</td><td>及时止盈，等待再入</td></tr>
      <tr><td>↑上升</td><td>近3周持续上升</td><td>趋势跟随，关注破位</td></tr>
      <tr><td>★启动</td><td>短期突然发力，历史低位</td><td>小仓试探，确认趋势后加仓</td></tr>
    </table>
    <p style="font-size:11px;color:#95a5a6;margin-top:12px">
      ⚡ 动量斜率(z)：近4周分位得分的线性斜率z值<br>
      &gt;1.5 = 强上升趋势 / &lt;-1.5 = 强下降趋势<br><br>
      📌 截面排名分位：当日20日涨幅在31个行业中的排名百分位，和参考图（申万行业图）逻辑一致
    </p>
  </div>
</div>

<div class="card">
  <h2>周度热力图（近16周）</h2>
  <img src="data:image/png;base64,{hm_b64}" alt="热力图">
</div>

</body></html>"""

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  HTML周报：{out_file}")


# ══════════════════════════════════════════════════════════════
# 6. 主流程
# ══════════════════════════════════════════════════════════════

def main():
    # ── 参数 ────────────────────────
    START_DATE    = "20230101"
    SHORT_W       = 20     # 月线收益窗口
    LONG_W        = 250    # 年线收益窗口
    LOOKBACK      = 250    # 历史分位回望
    N_WEEKS       = 16     # 热力图展示周数
    HOT_THR       = 85
    RISE_W        = 3      # 连续上升检测周数
    # ────────────────────────────────

    price_df = fetch_data(START_DATE)

    metrics = calc_all_metrics(price_df, SHORT_W, LONG_W, LOOKBACK)

    hist_short  = metrics["hist_short"]
    hist_long   = metrics["hist_long"]
    cross_short = metrics["cross_short"]

    # 周度采样（热力图用短期历史分位）
    weekly_hist = hist_short.resample("W-FRI").last().iloc[:-1].tail(N_WEEKS)

    cur_hs = hist_short.iloc[-1].dropna()
    cur_hl = hist_long.iloc[-1].dropna()
    cur_cs = cross_short.iloc[-1].dropna()

    print("生成信号...")
    sig_df = detect_signals_v2(weekly_hist, cur_hs, cur_hl, cur_cs,
                                hot_thr=HOT_THR, rise_w=RISE_W)

    print("\n绘图中...")
    OUTPUT_DIR = os.path.join(ROOT, "output", "sw_rotation")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    hm_file = os.path.join(OUTPUT_DIR, f"sw_heatmap_{TODAY}.png")
    qd_file = os.path.join(OUTPUT_DIR, f"sw_quadrant_{TODAY}.png")
    html_file = os.path.join(OUTPUT_DIR, f"sw_weekly_report_{TODAY}.html")

    plot_heatmap(weekly_hist, sig_df, hm_file)
    plot_quadrant(sig_df, qd_file)

    print("生成HTML周报...")
    gen_html_report(sig_df, hm_file, qd_file, html_file)

    # CSV
    csv_file = os.path.join(OUTPUT_DIR, f"sw_scores_{TODAY}.csv")
    sig_df.reset_index().to_csv(csv_file, index=False, encoding="utf-8-sig")
    print(f"  CSV：{csv_file}")

    print(f"\n✅ 完成！打开 {html_file} 查看周报")

    # 控制台输出关键信号
    print("\n══ 本周信号 ══")
    for label, col in [("🔥 过热", "过热"), ("⚠ 退潮", "长强短弱"),
                        ("❄ 降温", "降温"), ("↑ 上升", "连续上升"),
                        ("★ 启动候选", "短强长弱")]:
        items = sig_df[sig_df[col]].index.tolist()
        print(f"{label}: {', '.join(items) if items else '无'}")


if __name__ == "__main__":
    main()
