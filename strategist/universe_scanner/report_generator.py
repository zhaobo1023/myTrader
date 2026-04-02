# -*- coding: utf-8 -*-
"""
报告生成器

生成 Top_100_Focus.md 报告，包含:
  - 核心监控池 (Top 30)
  - 动态关注池 (Top 100)
  - 海选池统计
  - 剔除清单
"""
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from .scoring_engine import StockScore
from .config import UniverseScanConfig


class UniverseReportGenerator:
    """全量扫描报告生成器"""

    def __init__(self, config: UniverseScanConfig = None):
        self.cfg = config or UniverseScanConfig()
        self.output_dir = Path(self.cfg.output_dir)

    def generate(
        self,
        results: Dict[str, List[StockScore]],
        hk_other: List,
        scan_date: Optional[datetime] = None,
    ) -> str:
        """
        生成 Top_100_Focus.md 报告

        Returns:
            报告文件路径
        """
        if scan_date is None:
            scan_date = datetime.now()

        high_priority = results.get('high_priority', [])
        watchlist = results.get('watchlist', [])
        universe = results.get('universe', [])
        filtered_out = results.get('filtered_out', [])

        lines = []

        # ---- 标题 ----
        lines.append(f"# Top 100 Focus - {scan_date.strftime('%Y-%m-%d')}")
        lines.append("")
        lines.append(f"> 扫描时间: {scan_date.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"> 海选池: {len(universe)} | 动态关注池: {len(watchlist)} | 核心监控池: {len(high_priority)}")
        lines.append(f"> 剔除: {len(filtered_out)} (流动性不足 / MA250 下方)")
        if hk_other:
            lines.append(f"> 港股/其他: {len(hk_other)} 只 (不在分层范围内)")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ---- 核心监控池 ----
        lines.append("## 核心监控池 (Top 30)")
        lines.append("")
        lines.append("> 随时准备下单或已持有的标的。形态契合 + 权重叠加得分最高。")
        lines.append("")
        self._append_score_table(lines, high_priority, show_score=True)
        lines.append("")

        # ---- 动态关注池 ----
        lines.append("## 动态关注池 (Watchlist)")
        lines.append("")
        lines.append(f"> RPS > {self.cfg.rps_min} + 趋势对齐 (MA20/60 上方)。按得分降序排列。")
        lines.append("")

        # 只展示 watchlist 中非 high_priority 的
        hp_codes = {s.code for s in high_priority}
        watchlist_only = [s for s in watchlist if s.code not in hp_codes]
        # 最多展示 70 只（加上 30 只核心 = 100 只）
        self._append_score_table(lines, watchlist_only[:70], show_score=True)
        lines.append("")

        # ---- 核心监控池评分明细 ----
        if high_priority:
            lines.append("## 核心池评分明细")
            lines.append("")
            for s in high_priority:
                lines.append(f"### {s.code} {s.name}")
                lines.append("")
                lines.append(f"- 行业: {s.industry}")
                lines.append(f"- 最新价: {s.close:.2f} ({s.pct_change:+.2f}%)")
                if s.ma20:
                    ma20_str = f"{s.ma20:.2f}" if s.ma20 else "-"
                ma60_str = f"{s.ma60:.2f}" if s.ma60 else "-"
                ma250_str = f"{s.ma250:.2f}" if s.ma250 else "-"
                lines.append(f"- MA20: {ma20_str} | MA60: {ma60_str} | MA250: {ma250_str}")
                rps_str = []
                if s.rps_120 is not None:
                    rps_str.append(f"RPS120={s.rps_120:.0f}")
                if s.rps_250 is not None:
                    rps_str.append(f"RPS250={s.rps_250:.0f}")
                if s.rps_slope is not None:
                    rps_str.append(f"斜率Z={s.rps_slope:.2f}")
                if rps_str:
                    lines.append(f"- RPS: {' | '.join(rps_str)}")
                if s.rsi is not None:
                    lines.append(f"- RSI(14): {s.rsi:.1f}")
                if s.volume_ratio is not None:
                    lines.append(f"- 量比: {s.volume_ratio:.2f}x")
                if s.avg_amount_60d is not None:
                    lines.append(f"- 60日均额: {self._fmt_amount(s.avg_amount_60d)}")
                if s.trend:
                    lines.append(f"- 趋势: {s.trend}")
                if s.signals:
                    lines.append(f"- 信号: {', '.join(s.signals)}")
                lines.append(f"- **总分: {s.total_score}** | {', '.join(s.score_details)}")
                lines.append("")

        # ---- 港股/其他 ----
        if hk_other:
            lines.append("---")
            lines.append("")
            lines.append("## 港股 / 其他标的")
            lines.append("")
            lines.append("| 代码 | 名称 | 行业 |")
            lines.append("|------|------|------|")
            for s in hk_other:
                lines.append(f"| {s.code} | {s.name} | {s.industry} |")
            lines.append("")

        # ---- 剔除清单摘要 ----
        if filtered_out:
            lines.append("---")
            lines.append("")
            lines.append("## 剔除清单 (前 50)")
            lines.append("")
            lines.append("| 代码 | 名称 | 行业 | 最新价 | 原因 |")
            lines.append("|------|------|------|--------|------|")
            for s in filtered_out[:50]:
                reason = self._get_filter_reason(s)
                close_str = f"{s.close:.2f}" if s.close else "-"
                lines.append(f"| {s.code} | {s.name} | {s.industry} | {close_str} | {reason} |")
            lines.append("")

        # ---- 写入文件 ----
        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"Top_100_Focus_{scan_date.strftime('%Y%m%d')}.md"
        filepath = self.output_dir / filename
        filepath.write_text("\n".join(lines), encoding='utf-8')

        return str(filepath)

    def _append_score_table(
        self,
        lines: List[str],
        scores: List[StockScore],
        show_score: bool = True,
    ):
        """添加评分表格"""
        if not scores:
            lines.append("> (无)")
            return

        if show_score:
            lines.append("| 排名 | 代码 | 名称 | 行业 | 最新价 | 涨跌幅 | RPS120 | RPS250 | RSI | 量比 | 趋势 | 信号 | 总分 |")
            lines.append("|------|------|------|------|--------|--------|--------|--------|-----|------|------|------|------|")
        else:
            lines.append("| 代码 | 名称 | 行业 | 最新价 | 涨跌幅 | RPS120 | RPS250 | RSI | 量比 | 趋势 | 信号 |")
            lines.append("|------|------|------|--------|--------|--------|--------|-----|------|------|------|")

        for i, s in enumerate(scores, 1):
            pct = f"{s.pct_change:+.2f}%" if s.pct_change else "-"
            rps120 = f"{s.rps_120:.0f}" if s.rps_120 is not None else "-"
            rps250 = f"{s.rps_250:.0f}" if s.rps_250 is not None else "-"
            rsi = f"{s.rsi:.0f}" if s.rsi is not None else "-"
            vol = f"{s.volume_ratio:.1f}" if s.volume_ratio is not None else "-"
            trend = s.trend or "-"
            sigs = ", ".join(s.signals[:3]) if s.signals else "-"
            close = f"{s.close:.2f}" if s.close else "-"

            if show_score:
                score_str = f"**{s.total_score}**" if s.total_score >= 3 else str(s.total_score)
                lines.append(
                    f"| {i} | {s.code} | {s.name} | {s.industry} | {close} | {pct} | "
                    f"{rps120} | {rps250} | {rsi} | {vol} | {trend} | {sigs} | {score_str} |"
                )
            else:
                lines.append(
                    f"| {s.code} | {s.name} | {s.industry} | {close} | {pct} | "
                    f"{rps120} | {rps250} | {rsi} | {vol} | {trend} | {sigs} |"
                )

    def _get_filter_reason(self, s: StockScore) -> str:
        """获取被剔除的原因"""
        reasons = []
        if s.ma250 is not None and s.close < s.ma250:
            reasons.append("MA250下方")
        if s.avg_amount_60d is not None and s.avg_amount_60d < self.cfg.min_avg_amount:
            reasons.append(f"均额{s.avg_amount_60d / 10000:.0f}万<5000万")
        return ", ".join(reasons) if reasons else "未通过筛选"

    @staticmethod
    def _fmt_amount(val: float) -> str:
        """格式化金额"""
        if val >= 1e8:
            return f"{val / 1e8:.2f}亿"
        elif val >= 1e4:
            return f"{val / 1e4:.0f}万"
        return f"{val:.0f}"

    def save_daily_csv(
        self,
        results: Dict[str, List[StockScore]],
        scan_date: datetime,
    ):
        """保存每日分层 CSV，用于连续性追踪"""
        rows = []
        for tier_name, scores in results.items():
            for s in scores:
                rows.append({
                    'date': scan_date.strftime('%Y-%m-%d'),
                    'tier': tier_name,
                    'code': s.code,
                    'name': s.name,
                    'industry': s.industry,
                    'close': s.close,
                    'pct_change': s.pct_change,
                    'rps_120': s.rps_120,
                    'rps_250': s.rps_250,
                    'rsi': s.rsi,
                    'volume_ratio': s.volume_ratio,
                    'total_score': s.total_score,
                    'trend': s.trend,
                    'signals': "; ".join(s.signals),
                    'score_details': "; ".join(s.score_details),
                })

        if not rows:
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = self.output_dir / "Universe_Daily.csv"

        df_new = pd.DataFrame(rows)

        # 追加模式：去除同日数据后合并
        if csv_path.exists():
            existing = pd.read_csv(csv_path)
            existing = existing[existing['date'] != scan_date.strftime('%Y-%m-%d')]
            df_new = pd.concat([existing, df_new], ignore_index=True)

        df_new.to_csv(csv_path, index=False)
