"""
五截面分析 HTML 报告渲染器

使用与技术面扫描报告相同的 CSS 设计系统：
- info-card / badge / badge-row / score-bar / score-marker
- table-wrap with overflow-x:auto + -webkit-overflow-scrolling:touch
- danger-alert / opportunity-alert / neutral-alert
- 移动端适配 (max-width 640px breakpoint)
- 暗色模式 (prefers-color-scheme: dark)
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any


# ---------------------------------------------------------------------------
# Input data container
# ---------------------------------------------------------------------------

@dataclass
class ReportData:
    """五截面 HTML 报告所需的全部数据"""
    stock_code: str
    stock_name: str
    report_date: str              # 分析日期 YYYY-MM-DD

    # Section scores (0-100)
    score_technical: int = 50
    score_fund_flow: int = 50
    score_fundamental: int = 60
    score_sentiment: int = 50
    score_capital_cycle: int = 50
    composite_score: float = 50.0
    direction: str = "neutral"    # strong_bull/bull/neutral/bear/strong_bear

    # Technical details
    tech_price: float = 0.0
    tech_ma5: float = 0.0
    tech_ma20: float = 0.0
    tech_ma60: float = 0.0
    tech_ma250: float = 0.0
    tech_rsi: float = 50.0
    tech_macd_hist: float = 0.0
    tech_kdj_j: float = 50.0
    tech_boll_pct_b: float = 0.5
    tech_boll_lower: float = 0.0
    tech_vol_ratio: float = 1.0
    tech_rps120: float = 50.0
    tech_score_raw: float = 5.0   # 0-10 from tech scan engine

    # Fund flow details
    ff_net_5d_yi: float = 0.0     # 亿元
    ff_net_10d_yi: float = 0.0
    ff_net_20d_yi: float = 0.0
    ff_net_5d_pct: float = 0.0    # % of market cap
    ff_net_20d_pct: float = 0.0
    ff_label: str = "中性"

    # Fundamental details
    fund_revenue_yi: float = 0.0
    fund_revenue_yoy: float = 0.0
    fund_profit_yi: float = 0.0
    fund_profit_yoy: float = 0.0
    fund_roe: float = 0.0
    fund_roe_prev: float = 0.0
    fund_gross_margin: float = 0.0
    fund_ocf_to_profit: float = 0.0
    fund_debt_ratio: float = 0.0
    fund_report_date: str = ""
    fund_pe_ttm: float = 0.0
    fund_pb: float = 0.0
    fund_pe_quantile: float = 0.5
    fund_pb_quantile: float = 0.5
    fund_total_mv: float = 0.0    # 亿元
    fund_eq_score: int = 0
    fund_va_score: int = 0
    fund_gc_score: int = 0

    # Sentiment details
    sent_score_fund: int = 50
    sent_score_pricevol: int = 50
    sent_score_consensus: int = 50
    sent_score_sector: int = 50
    sent_score_macro: int = 50
    sent_label: str = "中性"

    # Capital cycle details
    cc_phase: int = 0
    cc_phase_label: str = "未知"
    cc_roe_trend: str = ""
    cc_detail: str = ""
    cc_label: str = "中性"
    cc_roe_series: list = field(default_factory=list)
    cc_rev_growth_series: list = field(default_factory=list)

    # Alerts (list of dicts with keys: type='danger'|'opportunity'|'neutral', text)
    alerts: list = field(default_factory=list)

    # Rules triggered
    rules_triggered: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# CSS (shared with tech scan)
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #f5f5f5; color: #333; word-break: break-word; }
h1 { border-bottom: 3px solid #3498db; padding-bottom: 10px; font-size: 1.4em; line-height: 1.3; }
h2 { color: #2c3e50; border-left: 4px solid #3498db; padding-left: 10px; margin-top: 25px; font-size: 1.1em; }
h3 { color: #34495e; margin-top: 15px; font-size: 1em; }
.meta { color: #888; margin-bottom: 15px; font-size: 13px; }
.table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 10px 0; }
table { border-collapse: collapse; width: 100%; min-width: 360px; background: white; }
th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; white-space: nowrap; }
th { background: #3498db; color: white; }
tr:nth-child(even) { background: #f9f9f9; }
.info-card { background: white; padding: 15px; border-radius: 8px; margin: 10px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.badge { display: inline-block; padding: 4px 12px; border-radius: 12px; color: white; font-weight: bold; font-size: 14px; margin: 2px 0; }
.badge-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 10px 0; }
.score-bar { height: 20px; border-radius: 10px; background: linear-gradient(to right, #e74c3c, #f1c40f, #27ae60); position: relative; margin: 10px 0; }
.score-marker { position: absolute; top: -4px; width: 4px; height: 28px; background: #2c3e50; border-radius: 2px; }
.score-breakdown { font-size: 12px; color: #888; display: flex; flex-wrap: wrap; gap: 6px; margin: 5px 0; }
.score-breakdown span { white-space: nowrap; }
.danger-alert { border-left: 4px solid #e74c3c; background: #ffeaea; padding: 8px 12px; margin: 4px 0; border-radius: 4px; font-size: 13px; }
.opportunity-alert { border-left: 4px solid #27ae60; background: #eafaf1; padding: 8px 12px; margin: 4px 0; border-radius: 4px; font-size: 13px; }
.neutral-alert { border-left: 4px solid #f39c12; background: #fef9e7; padding: 8px 12px; margin: 4px 0; border-radius: 4px; font-size: 13px; }
.key-info { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; font-size: 14px; }
.key-info span { white-space: nowrap; }
.section-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin: 12px 0; }
.section-card { background: #f8f9fa; border-radius: 8px; padding: 12px; text-align: center; }
.section-card .sec-label { font-size: 12px; color: #888; margin-bottom: 4px; }
.section-card .sec-score { font-size: 28px; font-weight: bold; }
.section-card .sec-weight { font-size: 11px; color: #aaa; margin-top: 2px; }
.composite-score-box { text-align: center; padding: 20px; }
.composite-score-box .big-score { font-size: 52px; font-weight: bold; line-height: 1; }
.composite-score-box .direction-label { font-size: 18px; margin-top: 6px; font-weight: bold; }
.composite-score-box .hint { font-size: 12px; color: #888; margin-top: 4px; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 10px 0; }
.disclaimer { font-size: 12px; color: #999; background: #fffff0; border: 1px solid #ddd; padding: 10px 14px; border-radius: 6px; margin-top: 20px; line-height: 1.6; }
@media (max-width: 640px) {
    body { padding: 10px 8px; font-size: 14px; }
    h1 { font-size: 1.15em; }
    h2 { font-size: 1em; padding-left: 8px; }
    .info-card { padding: 10px; border-radius: 6px; }
    th, td { padding: 6px 8px; font-size: 12px; }
    .badge { font-size: 12px; padding: 3px 8px; }
    .danger-alert, .opportunity-alert, .neutral-alert { font-size: 12px; padding: 6px 10px; }
    .composite-score-box .big-score { font-size: 40px; }
    .composite-score-box .direction-label { font-size: 15px; }
    .two-col { grid-template-columns: 1fr; }
    .section-grid { grid-template-columns: repeat(3, 1fr); }
    .section-card .sec-score { font-size: 22px; }
    .section-card { padding: 8px 6px; }
    .disclaimer { font-size: 11px; padding: 8px; }
}
@media (prefers-color-scheme: dark) {
    body { background: #1a1a2e; color: #e0e0e0; }
    .info-card { background: #16213e; box-shadow: 0 1px 3px rgba(255,255,255,0.05); }
    .section-card { background: #1e2a44; }
    h1 { border-bottom-color: #4a90d9; }
    h2 { color: #e0e0e0; border-left-color: #4a90d9; }
    h3 { color: #c0c0c0; }
    th { background: #2c3e6b; }
    td { border-color: #3a3a5c; }
    table { background: #16213e; }
    tr:nth-child(even) { background: #1a2744; }
    .meta, .score-breakdown { color: #888; }
    .danger-alert { background: #3d1f1f; }
    .opportunity-alert { background: #1f3d2a; }
    .neutral-alert { background: #3d3510; }
    .section-card .sec-label { color: #aaa; }
    .section-card .sec-weight { color: #666; }
    .disclaimer { background: #1e1e10; border-color: #3a3a20; color: #888; }
    .score-marker { background: #e0e0e0; }
}
"""


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _score_color(score: int) -> str:
    if score >= 65:
        return "#27ae60"
    if score >= 50:
        return "#f39c12"
    return "#e74c3c"


def _direction_label(direction: str) -> str:
    return {
        "strong_bull": "强多",
        "bull": "偏多",
        "neutral": "中性观望",
        "bear": "偏空",
        "strong_bear": "强空",
    }.get(direction, "中性观望")


def _direction_color(direction: str) -> str:
    return {
        "strong_bull": "#27ae60",
        "bull": "#2ecc71",
        "neutral": "#f39c12",
        "bear": "#e67e22",
        "strong_bear": "#e74c3c",
    }.get(direction, "#f39c12")


def _score_bar(score: int) -> str:
    pct = max(2, min(98, score))
    return (
        f'<div class="score-bar">'
        f'<div class="score-marker" style="left: calc({pct}% - 2px);"></div>'
        f"</div>"
    )


def _badge(text: str, color: str) -> str:
    return f'<span class="badge" style="background:{color};">{text}</span>'


def _alert(atype: str, text: str) -> str:
    css = {"danger": "danger-alert", "opportunity": "opportunity-alert"}.get(
        atype, "neutral-alert"
    )
    return f'<div class="{css}">{text}</div>'


def _td_color(value, is_positive: bool) -> str:
    color = "#27ae60" if is_positive else "#e74c3c"
    return f'<td style="color:{color};">{value}</td>'


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

class FiveSectionRenderer:
    """将 ReportData 渲染为移动端友好的 HTML 字符串"""

    def render(self, d: ReportData) -> str:
        sections = [
            self._header(d),
            self._overview(d),
            self._section_technical(d),
            self._section_fund_flow(d),
            self._section_fundamental(d),
            self._section_sentiment(d),
            self._section_capital_cycle(d),
            self._section_rules(d),
            self._section_decision(d),
            self._disclaimer(d),
        ]
        body = "\n".join(sections)
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0">
<title>{d.stock_code} {d.stock_name} - 五截面分析</title>
<style>{_CSS}</style>
</head>
<body>
{body}
</body>
</html>"""

    # ------------------------------------------------------------------

    def _header(self, d: ReportData) -> str:
        return (
            f"<h1>{d.stock_name} ({d.stock_code}) - 五截面深度分析</h1>\n"
            f'<div class="meta">分析日期: {d.report_date} &nbsp;|&nbsp; 框架: FiveSectionFramework v1.0</div>'
        )

    # ------------------------------------------------------------------

    def _overview(self, d: ReportData) -> str:
        comp = d.composite_score
        comp_color = _direction_color(d.direction)
        dir_label = _direction_label(d.direction)

        # weighted breakdown
        bd = (
            f"技术 {d.score_technical}x15%={d.score_technical*0.15:.1f} &nbsp;"
            f"资金 {d.score_fund_flow}x20%={d.score_fund_flow*0.20:.1f} &nbsp;"
            f"基本 {d.score_fundamental}x30%={d.score_fundamental*0.30:.1f} &nbsp;"
            f"情绪 {d.score_sentiment}x15%={d.score_sentiment*0.15:.1f} &nbsp;"
            f"周期 {d.score_capital_cycle}x20%={d.score_capital_cycle*0.20:.1f} &nbsp;"
            f"<strong>= {comp:.1f}</strong>"
        )

        cards = ""
        for label, score, weight in [
            ("技术面", d.score_technical, "x15%"),
            ("资金面", d.score_fund_flow, "x20%"),
            ("基本面", d.score_fundamental, "x30%"),
            ("情绪面", d.score_sentiment, "x15%"),
            ("资本周期", d.score_capital_cycle, "x20%"),
        ]:
            c = _score_color(score)
            top_color = c
            cards += (
                f'<div class="section-card" style="border-top:3px solid {top_color};">'
                f'<div class="sec-label">{label}</div>'
                f'<div class="sec-score" style="color:{c};">{score}</div>'
                f'<div class="sec-weight">{weight}</div>'
                f"</div>"
            )

        # auto-generate alerts based on scores
        badge_html = ""
        if d.score_technical < 35:
            badge_html += _badge("[WARN] 技术弱势", "#e74c3c") + " "
        if d.score_fund_flow < 40:
            badge_html += _badge("[WARN] 主力流出", "#e74c3c") + " "
        if d.fund_pe_quantile > 0.85:
            badge_html += _badge("[WARN] 估值高位", "#e74c3c") + " "
        if d.score_fundamental >= 65:
            badge_html += _badge("[OK] 基本面强劲", "#27ae60") + " "
        if d.cc_phase == 3:
            badge_html += _badge("[OK] 扩张周期高峰", "#27ae60") + " "
        elif d.cc_phase == 2:
            badge_html += _badge("[OK] 需求扩张期", "#27ae60") + " "
        if d.score_technical >= 65:
            badge_html += _badge("[OK] 技术强势", "#27ae60") + " "

        return f"""<div class="info-card" style="border:2px solid #e67e22;">
<h2>综合评分总览</h2>
<div class="two-col">
<div class="composite-score-box">
  <div style="font-size:13px;color:#888;margin-bottom:6px;">五截面加权综合分</div>
  <div class="big-score" style="color:{comp_color};">{comp:.1f}</div>
  <div class="direction-label" style="color:{comp_color};">{dir_label}</div>
  <div class="hint">45-60=中性 | &lt;30强空 / &gt;75强多</div>
</div>
<div>
  {_score_bar(int(comp))}
  <div class="score-breakdown" style="margin-top:8px;">{bd}</div>
  <div class="section-grid" style="margin-top:14px;">{cards}</div>
</div>
</div>
<div class="badge-row" style="margin-top:10px;">{badge_html}</div>
</div>"""

    # ------------------------------------------------------------------

    def _section_technical(self, d: ReportData) -> str:
        s = d.score_technical
        c = _score_color(s)

        # MA table
        price = d.tech_price
        ma_rows = ""
        for label, val in [
            ("MA5", d.tech_ma5), ("MA20", d.tech_ma20),
            ("MA60", d.tech_ma60), ("MA250", d.tech_ma250),
        ]:
            if val <= 0:
                continue
            dev = (price - val) / val * 100
            broken = dev < 0
            dev_html = f'<td style="color:{"#e74c3c" if broken else "#27ae60"};">{dev:+.2f}%</td>'
            status = f'<td style="color:{"#e74c3c" if broken else "#27ae60"};">{"已跌破" if broken else "上方支撑"}</td>'
            ma_rows += f"<tr><td>{label}</td><td>{val:.2f}</td>{dev_html}{status}</tr>"

        ind_rows = ""
        indicators = [
            ("RSI14", f"{d.tech_rsi:.1f}", "超卖(<30)" if d.tech_rsi < 30 else ("超买(>70)" if d.tech_rsi > 70 else "正常区间"),
             "#27ae60" if d.tech_rsi < 35 else ("#e74c3c" if d.tech_rsi > 65 else "#888")),
            ("MACD Hist", f"{d.tech_macd_hist:.3f}", "多头" if d.tech_macd_hist > 0 else "空头",
             "#27ae60" if d.tech_macd_hist > 0 else "#e74c3c"),
            ("KDJ J", f"{d.tech_kdj_j:.1f}", "极度超卖(<10)" if d.tech_kdj_j < 10 else ("超买(>90)" if d.tech_kdj_j > 90 else "正常"),
             "#27ae60" if d.tech_kdj_j < 15 else ("#e74c3c" if d.tech_kdj_j > 85 else "#888")),
            ("BOLL %B", f"{d.tech_boll_pct_b:.2f}", "近下轨" if d.tech_boll_pct_b < 0.2 else ("近上轨" if d.tech_boll_pct_b > 0.8 else "轨道中部"),
             "#27ae60" if d.tech_boll_pct_b < 0.2 else "#888"),
            ("成交量比", f"{d.tech_vol_ratio:.2f}", "放量" if d.tech_vol_ratio > 1.5 else ("缩量" if d.tech_vol_ratio < 0.7 else "正常量"),
             "#888"),
            ("RPS120", f"{d.tech_rps120:.1f}", "历史强势品种" if d.tech_rps120 > 80 else "普通",
             "#27ae60" if d.tech_rps120 > 80 else "#888"),
        ]
        for name, val, desc, col in indicators:
            ind_rows += f'<tr><td>{name}</td><td>{val}</td><td>{desc}</td><td style="color:{col};">{desc}</td></tr>'

        badge_dir = "偏空" if s < 45 else ("偏多" if s >= 60 else "中性")
        badge_color = "#e74c3c" if s < 45 else ("#27ae60" if s >= 60 else "#f39c12")
        oversold_badge = _badge("极度超卖", "#27ae60") if d.tech_rsi < 30 else ""

        return f"""<div class="info-card">
<h2>截面一：技术面（权重 15%，得分 {s}/100）</h2>
<div class="badge-row">{_badge(badge_dir, badge_color)} {oversold_badge}</div>
{_score_bar(s)}
<div class="score-breakdown"><span>系统评分: {d.tech_score_raw:.1f}/10</span><span>RSI14: {d.tech_rsi:.1f}</span><span>MACD Hist: {d.tech_macd_hist:.3f}</span></div>
<h3>均线系统（当前价: {price:.2f}）</h3>
<div class="table-wrap"><table>
<thead><tr><th>均线</th><th>数值</th><th>偏离</th><th>状态</th></tr></thead>
<tbody>{ma_rows}</tbody></table></div>
<h3>核心技术指标</h3>
<div class="table-wrap"><table>
<thead><tr><th>指标</th><th>数值</th><th>区间</th><th>信号</th></tr></thead>
<tbody>{ind_rows}</tbody></table></div>
</div>"""

    # ------------------------------------------------------------------

    def _section_fund_flow(self, d: ReportData) -> str:
        s = d.score_fund_flow
        c = _score_color(s)

        net5_color = "#27ae60" if d.ff_net_5d_yi >= 0 else "#e74c3c"
        net20_color = "#27ae60" if d.ff_net_20d_yi >= 0 else "#e74c3c"

        return f"""<div class="info-card">
<h2>截面二：资金面（权重 20%，得分 {s}/100）</h2>
<div class="badge-row">{_badge(d.ff_label, c)}</div>
{_score_bar(s)}
<h3>主力资金净流向</h3>
<div class="table-wrap"><table>
<thead><tr><th>统计周期</th><th>主力净流入</th><th>占市值</th><th>趋势</th></tr></thead>
<tbody>
<tr><td>近5日</td><td style="color:{net5_color};font-weight:bold;">{d.ff_net_5d_yi:+.2f}亿</td><td style="color:{net5_color};">{d.ff_net_5d_pct:+.2f}%</td><td style="color:{net5_color};">{"净流入" if d.ff_net_5d_yi>=0 else "净流出"}</td></tr>
<tr><td>近20日</td><td style="color:{net20_color};font-weight:bold;">{d.ff_net_20d_yi:+.2f}亿</td><td style="color:{net20_color};">{d.ff_net_20d_pct:+.2f}%</td><td style="color:{net20_color};">{"净流入" if d.ff_net_20d_yi>=0 else "净流出"}</td></tr>
</tbody></table></div>
{_alert("danger" if d.ff_net_5d_yi < -5 else "neutral", f"[资金] 5日净流入{d.ff_net_5d_yi:+.2f}亿；RPS120={d.tech_rps120:.1f}")}
</div>"""

    # ------------------------------------------------------------------

    def _section_fundamental(self, d: ReportData) -> str:
        s = d.score_fundamental
        c = _score_color(s)
        pe_q_pct = d.fund_pe_quantile * 100
        pb_q_pct = d.fund_pb_quantile * 100
        pe_color = "#e74c3c" if d.fund_pe_quantile > 0.8 else ("#27ae60" if d.fund_pe_quantile < 0.4 else "#888")
        pb_color = "#e74c3c" if d.fund_pb_quantile > 0.8 else ("#27ae60" if d.fund_pb_quantile < 0.4 else "#888")

        roe_delta = d.fund_roe - d.fund_roe_prev
        ocf_ratio = d.fund_ocf_to_profit

        return f"""<div class="info-card">
<h2>截面三：基本面（权重 30%，得分 {s}/100）</h2>
<div class="badge-row">
{_badge("盈利质量", _score_color(d.fund_eq_score * 100 // 40))}
{_badge("估值" + ("高位" if d.fund_pe_quantile > 0.8 else "合理"), "#e74c3c" if d.fund_pe_quantile > 0.8 else "#27ae60")}
{_badge("成长性", _score_color(d.fund_gc_score * 100 // 20))}
</div>
{_score_bar(s)}
<div class="score-breakdown">
<span>盈利质量EQ: {d.fund_eq_score}/40</span>
<span>估值安全边际VA: {d.fund_va_score}/40</span>
<span>成长确定性GC: {d.fund_gc_score}/20</span>
<span>= {s}/100</span>
</div>
<h3>核心财务数据（{d.fund_report_date}）</h3>
<div class="table-wrap"><table>
<thead><tr><th>指标</th><th>最新值</th><th>同比</th><th>评价</th></tr></thead>
<tbody>
<tr><td>营业收入</td><td>{d.fund_revenue_yi:.1f}亿</td>{_td_color(f"{d.fund_revenue_yoy*100:+.1f}%", d.fund_revenue_yoy>0)}<td style="color:{'#27ae60' if d.fund_revenue_yoy>0.15 else '#888'};">{"强劲增长" if d.fund_revenue_yoy>0.2 else ("增长" if d.fund_revenue_yoy>0 else "下滑")}</td></tr>
<tr><td>归母净利润</td><td>{d.fund_profit_yi:.1f}亿</td>{_td_color(f"{d.fund_profit_yoy*100:+.1f}%", d.fund_profit_yoy>0)}<td style="color:{'#27ae60' if d.fund_profit_yoy>0.15 else '#888'};">{"超预期" if d.fund_profit_yoy>0.3 else ("增长" if d.fund_profit_yoy>0 else "下滑")}</td></tr>
<tr><td>ROE</td><td>{d.fund_roe:.2f}%</td>{_td_color(f"{roe_delta:+.1f}pct", roe_delta>0)}<td style="color:{'#27ae60' if d.fund_roe>=15 else '#888'};">{"优秀" if d.fund_roe>=20 else ("良好" if d.fund_roe>=12 else "偏低")}</td></tr>
<tr><td>毛利率</td><td>{d.fund_gross_margin:.1f}%</td><td>-</td><td style="color:{'#27ae60' if d.fund_gross_margin>30 else '#888'};">{"高毛利" if d.fund_gross_margin>35 else ("中等" if d.fund_gross_margin>20 else "偏低")}</td></tr>
<tr><td>OCF/净利润</td><td>{ocf_ratio:.2f}x</td><td>-</td><td style="color:{'#27ae60' if ocf_ratio>=1.0 else ('#e74c3c' if ocf_ratio<0.5 else '#888')};">{"利润高质量" if ocf_ratio>=1.0 else ("一般" if ocf_ratio>=0.5 else "含金量低")}</td></tr>
<tr><td>资产负债率</td><td>{d.fund_debt_ratio:.1f}%</td><td>-</td><td style="color:{'#e74c3c' if d.fund_debt_ratio>70 else ('#f39c12' if d.fund_debt_ratio>50 else '#27ae60')};">{"偏高" if d.fund_debt_ratio>70 else ("适中" if d.fund_debt_ratio>40 else "偏低")}</td></tr>
</tbody></table></div>
<h3>估值分析（5年历史分位）</h3>
<div class="table-wrap"><table>
<thead><tr><th>指标</th><th>当前值</th><th>5年分位</th><th>评价</th></tr></thead>
<tbody>
<tr><td>PE(TTM)</td><td>{d.fund_pe_ttm:.2f}x</td><td style="color:{pe_color};font-weight:bold;">{pe_q_pct:.1f}%</td><td style="color:{pe_color};">{"历史高位" if d.fund_pe_quantile>0.8 else ("合理" if d.fund_pe_quantile<0.5 else "偏高")}</td></tr>
<tr><td>PB</td><td>{d.fund_pb:.2f}x</td><td style="color:{pb_color};font-weight:bold;">{pb_q_pct:.1f}%</td><td style="color:{pb_color};">{"历史高位" if d.fund_pb_quantile>0.8 else ("合理" if d.fund_pb_quantile<0.5 else "偏高")}</td></tr>
<tr><td>总市值</td><td>{d.fund_total_mv:.1f}亿</td><td>-</td><td>-</td></tr>
</tbody></table></div>
</div>"""

    # ------------------------------------------------------------------

    def _section_sentiment(self, d: ReportData) -> str:
        s = d.score_sentiment
        c = _score_color(s)
        rows = [
            ("资金流向情绪", "30%", d.sent_score_fund, "主力流向驱动"),
            ("量价动量情绪", "25%", d.sent_score_pricevol, "RSI/MACD/量比"),
            ("一致预期情绪", "20%", d.sent_score_consensus, "分析师预期"),
            ("行业板块动量", "20%", d.sent_score_sector, f"RPS={d.tech_rps120:.1f}"),
            ("宏观情绪",     "5%",  d.sent_score_macro,    "宏观政策环境"),
        ]
        rows_html = ""
        for name, weight, sc, desc in rows:
            col = _score_color(sc)
            rows_html += f'<tr><td>{name}</td><td>{weight}</td><td style="color:{col};">{sc}</td><td>{desc}</td></tr>'

        return f"""<div class="info-card">
<h2>截面四：情绪面（权重 15%，得分 {s}/100）</h2>
<div class="badge-row">{_badge(d.sent_label, c)}</div>
{_score_bar(s)}
<div class="table-wrap"><table>
<thead><tr><th>维度</th><th>权重</th><th>分值</th><th>观察</th></tr></thead>
<tbody>{rows_html}
<tr style="font-weight:bold;"><td>加权合计</td><td>100%</td><td>{s}</td><td>-</td></tr>
</tbody></table></div>
</div>"""

    # ------------------------------------------------------------------

    def _section_capital_cycle(self, d: ReportData) -> str:
        s = d.score_capital_cycle
        c = _score_color(s)
        phase_color = {1: "#888", 2: "#27ae60", 3: "#27ae60", 4: "#e74c3c", 5: "#e74c3c"}.get(d.cc_phase, "#888")

        # ROE series table
        roe_rows = ""
        if d.cc_roe_series:
            for i, roe in enumerate(d.cc_roe_series):
                year_label = f"T-{len(d.cc_roe_series)-1-i}" if i < len(d.cc_roe_series)-1 else "最新年报"
                rev_g = d.cc_rev_growth_series[i-1] * 100 if i > 0 and d.cc_rev_growth_series and i-1 < len(d.cc_rev_growth_series) else None
                rev_str = f"{rev_g:+.1f}%" if rev_g is not None else "-"
                roe_rows += f"<tr><td>{year_label}</td><td>{roe:.1f}%</td><td>{rev_str}</td></tr>"

        phase_rows = ""
        for ph, lbl, desc in [
            (1, "低谷整合", "ROE低位，出清阶段"),
            (2, "需求扩张", "ROE上行，盈利改善"),
            (3, "扩张高峰", "ROE高位，产能高效"),
            (4, "供过于求", "ROE下滑，竞争加剧"),
            (5, "激烈内卷", "ROE极低，价格战"),
        ]:
            is_cur = ph == d.cc_phase
            row_style = 'style="background:#eafaf1;"' if is_cur else ""
            cur_tag = f'<td style="color:{phase_color};font-weight:bold;">[当前]</td>' if is_cur else "<td></td>"
            phase_rows += f"<tr {row_style}><td>Phase {ph}</td><td>{lbl}</td><td>{desc}</td>{cur_tag}</tr>"

        return f"""<div class="info-card">
<h2>截面五：资本周期（权重 20%，得分 {s}/100）</h2>
<div class="badge-row">{_badge(f"Phase {d.cc_phase}: {d.cc_phase_label}", phase_color)} {_badge(d.cc_roe_trend, "#27ae60" if d.cc_roe_trend == "上行" else "#e74c3c" if d.cc_roe_trend == "下行" else "#888")}</div>
{_score_bar(s)}
<div class="score-breakdown"><span>{d.cc_detail}</span></div>
<h3>资本周期五阶段定位</h3>
<div class="table-wrap"><table>
<thead><tr><th>阶段</th><th>标签</th><th>特征</th><th>定位</th></tr></thead>
<tbody>{phase_rows}</tbody></table></div>
{"<h3>ROE轨迹</h3><div class='table-wrap'><table><thead><tr><th>年份</th><th>ROE</th><th>收入增速</th></tr></thead><tbody>" + roe_rows + "</tbody></table></div>" if roe_rows else ""}
{_alert("neutral", f"[评分依据] {d.cc_detail}")}
</div>"""

    # ------------------------------------------------------------------

    def _section_rules(self, d: ReportData) -> str:
        p1_triggered = d.cc_phase == 4 and d.fund_pe_quantile > 0.8
        p2_triggered = False  # founder_reducing not available in auto mode
        boost_triggered = d.cc_phase == 3 and d.score_fundamental > 70

        rows = f"""
<tr><td>P1 泡沫期</td><td>Phase==4 AND PE分位&gt;80%</td><td>Phase={d.cc_phase}, PE分位={d.fund_pe_quantile*100:.0f}%</td>
<td style="color:{'#e74c3c' if p1_triggered else '#27ae60'};">{"触发" if p1_triggered else "未触发"}</td>
<td>{"资本周期4+高估值 => 强空" if p1_triggered else "-"}</td></tr>
<tr><td>P2 减仓破位</td><td>大股东减仓 AND 技术破位</td><td>需人工监控</td>
<td style="color:#27ae60;">未触发</td><td>-</td></tr>
<tr><td>BOOST 扩张期</td><td>Phase==3 AND 基本面&gt;70</td><td>Phase={d.cc_phase}, 基本面={d.score_fundamental}</td>
<td style="color:{'#27ae60' if boost_triggered else '#f39c12'};">{"触发 +1.3x基本面权重" if boost_triggered else "未达阈值"}</td>
<td>{"基本面权重提升" if boost_triggered else "-"}</td></tr>"""

        return f"""<div class="info-card">
<h2>规则引擎触发检测</h2>
<div class="table-wrap"><table>
<thead><tr><th>规则</th><th>条件</th><th>当前状态</th><th>触发</th><th>说明</th></tr></thead>
<tbody>{rows}</tbody></table></div>
</div>"""

    # ------------------------------------------------------------------

    def _section_decision(self, d: ReportData) -> str:
        comp = d.composite_score
        direction = d.direction
        dir_label = _direction_label(direction)

        if comp >= 75:
            action = "积极加仓，趋势确认后满仓操作"
            add_cond = "技术面确认上行 + 成交量配合"
            cut_cond = "综合分跌破60分"
        elif comp >= 60:
            action = "逐步加仓，等待回踩"
            add_cond = "技术面回踩支撑 + 主力净流入回正"
            cut_cond = "技术面破位 + 综合分跌破45分"
        elif comp >= 45:
            action = "维持现有仓位，不加仓，等待信号"
            add_cond = "综合分升至60+ 且技术面企稳"
            cut_cond = "技术面关键支撑跌破 或 综合分跌破35分"
        elif comp >= 30:
            action = "逐步减仓至防御仓位"
            add_cond = "综合分反弹至50+ 且基本面改善"
            cut_cond = "综合分跌破25分 或 基本面恶化"
        else:
            action = "清仓或空仓，规避风险"
            add_cond = "综合分重返45分以上"
            cut_cond = "已建议清仓"

        return f"""<div class="info-card" style="border:2px solid #27ae60;">
<h2>综合投资决策建议</h2>
<div class="table-wrap"><table>
<thead><tr><th>评级</th><th>建议操作</th><th>加仓条件</th><th>减仓/止损条件</th></tr></thead>
<tbody>
<tr style="background:#fef9e7;">
  <td><strong>{dir_label}</strong><br><small>综合分 {comp:.1f}</small></td>
  <td>{action}</td>
  <td>{add_cond}</td>
  <td>{cut_cond}</td>
</tr>
</tbody></table></div>
</div>"""

    # ------------------------------------------------------------------

    def _disclaimer(self, d: ReportData) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        return (
            f'<div class="disclaimer">'
            f"本报告由系统自动生成，仅供个人研究参考，不构成任何投资建议。股市有风险，投资需谨慎。"
            f"所有分析基于历史数据，不代表未来表现。五截面评分模型为实验性框架，存在模型风险与数据局限性。"
            f"<br>生成时间：{now} &nbsp;|&nbsp; 数据来源：在线数据库 &nbsp;|&nbsp; 框架: FiveSectionFramework v1.0"
            f"</div>"
        )
