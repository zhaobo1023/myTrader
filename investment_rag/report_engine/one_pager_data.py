# -*- coding: utf-8 -*-
"""
OnePagerDataCollector - 一页纸研究数据收集层

从线上 MySQL 提取所有可用数据，预计算派生指标，
输出结构化文本块供 LLM 解读（LLM 不做计算，只做判断）。

数据来源：
- trade_stock_daily          K线(OHLCV)
- trade_stock_daily_basic    估值(PE/PB/PS/DV/市值)
- financial_income           利润表(营收/净利/YoY/ROE/EPS)
- financial_balance          资产负债表(总资产/净资产)
- financial_dividend         分红历史
- financial_cashflow         现金流量表（部分股票有）
- financial_income_detail    利润明细（部分股票有）
- trade_stock_rps            相对强度
- trade_stock_extended_factor  扩展因子
- trade_stock_quality_factor   质量因子
- trade_stock_basic          基本信息
"""
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _sf(val) -> Optional[float]:
    """Safe float conversion for DB values (Decimal/None/NaN)."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _pct(val, digits=2) -> str:
    """Format as percentage string."""
    f = _sf(val)
    if f is None:
        return "(数据缺失)"
    return f"{f:.{digits}f}%"


def _yuan(val, digits=2) -> str:
    """Format as 亿元 string."""
    f = _sf(val)
    if f is None:
        return "(数据缺失)"
    return f"{f:.{digits}f}亿元"


def _num(val, digits=2) -> str:
    """Format a number."""
    f = _sf(val)
    if f is None:
        return "(数据缺失)"
    return f"{f:.{digits}f}"


class OnePagerDataCollector:
    """从 DB 收集并预计算一页纸研究所需的全部数据。"""

    def __init__(self, db_env: str = "online"):
        from config.db import execute_query as _eq
        self._eq = _eq
        self._env = db_env

    def _q(self, sql: str, params: tuple = ()) -> List[Dict]:
        """Execute query and return list of dicts."""
        return list(self._eq(sql, params, env=self._env))

    # ==============================================================
    # Public API: collect all data for a stock
    # ==============================================================

    def collect(self, stock_code: str, stock_name: str = "") -> Dict[str, str]:
        """
        Collect all available data and return structured text blocks.

        Returns dict with keys:
            - company_profile: 公司基本信息
            - financial_summary: 财务数据摘要(营收/利润/增速/ROE)
            - balance_sheet: 资产负债表摘要
            - valuation_snapshot: 估值数据(PE/PB/PS及历史分位)
            - price_technical: 价格与技术面数据
            - dividend_analysis: 分红历史分析
            - cashflow_analysis: 现金流分析(如有)
            - income_detail: 利润明细(如有)
            - rps_momentum: 动量与相对强度
            - quality_factors: 质量因子
            - growth_analysis: 增长趋势分析(预计算)
            - roe_decomposition: ROE趋势与杜邦拆解
            - valuation_verdict: 估值结论(预计算分位/历史对比)
        """
        # Normalize code: some tables use bare code, some use .SH/.SZ
        bare = stock_code.split(".")[0] if "." in stock_code else stock_code
        full = stock_code

        result: Dict[str, str] = {}

        result["company_profile"] = self._collect_profile(full, bare, stock_name)
        result["financial_summary"] = self._collect_financial(bare)
        result["balance_sheet"] = self._collect_balance(bare)
        result["valuation_snapshot"] = self._collect_valuation(bare, full)
        result["price_technical"] = self._collect_technical(full)
        result["dividend_analysis"] = self._collect_dividend(bare, full)
        result["cashflow_analysis"] = self._collect_cashflow(bare)
        result["income_detail"] = self._collect_income_detail(bare)
        result["rps_momentum"] = self._collect_rps(full)
        result["quality_factors"] = self._collect_quality(full)
        result["growth_analysis"] = self._compute_growth(bare)
        result["roe_decomposition"] = self._compute_roe_trend(bare)
        result["valuation_verdict"] = self._compute_valuation_verdict(bare, full)

        return result

    # ==============================================================
    # 1. Company Profile
    # ==============================================================

    def _collect_profile(self, full: str, bare: str, name: str) -> str:
        rows = self._q(
            "SELECT stock_code, stock_name, industry, is_st "
            "FROM trade_stock_basic WHERE stock_code=%s LIMIT 1",
            (full,),
        )
        if not rows:
            return f"公司: {name}({full}), 行业: (未知)"

        r = rows[0]
        industry = r.get("industry", "(未知)")
        st = " [ST]" if r.get("is_st") else ""
        return (
            f"公司: {r['stock_name']}{st}\n"
            f"股票代码: {r['stock_code']}\n"
            f"行业分类: {industry}"
        )

    # ==============================================================
    # 2. Financial Summary (financial_income)
    # ==============================================================

    def _collect_financial(self, bare: str) -> str:
        rows = self._q(
            "SELECT report_date, revenue, net_profit, net_profit_yoy, roe, "
            "gross_margin, eps FROM financial_income "
            "WHERE stock_code=%s ORDER BY report_date DESC LIMIT 12",
            (bare,),
        )
        if not rows:
            return "[无利润表数据]"

        lines = ["### 利润表摘要（近12期）\n"]
        lines.append("| 报告期 | 营收(亿) | 净利(亿) | 净利YoY | ROE | 毛利率 | EPS |")
        lines.append("|--------|---------|---------|---------|-----|--------|-----|")
        for r in rows:
            rd = str(r["report_date"])
            rev = _num(r["revenue"])
            np_ = _num(r["net_profit"])
            yoy = _pct(r["net_profit_yoy"])
            roe = _pct(r["roe"])
            gm = _pct(r["gross_margin"]) if r.get("gross_margin") else "(缺失)"
            eps = _num(r["eps"])
            lines.append(f"| {rd} | {rev} | {np_} | {yoy} | {roe} | {gm} | {eps} |")

        # Pre-compute: annual revenue/profit trend
        annual = [r for r in rows if str(r["report_date"]).endswith("12-31")]
        if len(annual) >= 2:
            lines.append("\n**年度趋势**:")
            for a in annual:
                lines.append(
                    f"- {a['report_date']}: 营收{_yuan(a['revenue'])}, "
                    f"净利{_yuan(a['net_profit'])}, YoY {_pct(a['net_profit_yoy'])}, "
                    f"ROE {_pct(a['roe'])}"
                )

        # TTM calculation from latest 4 quarters
        q_rows = [r for r in rows if not str(r["report_date"]).endswith("12-31")]
        latest = rows[0] if rows else None
        latest_rd = str(latest["report_date"]) if latest else ""
        if latest_rd.endswith("09-30") and len(rows) >= 5:
            # Q3 of current year: TTM = Q3_curr + Q4_prev
            q3_rev = _sf(rows[0]["revenue"]) or 0
            q3_np = _sf(rows[0]["net_profit"]) or 0
            # Find previous year annual
            prev_annual = next((r for r in rows if str(r["report_date"]).endswith("12-31")), None)
            prev_q3 = next((r for r in rows if str(r["report_date"])[5:] == "09-30" and r != rows[0]), None)
            if prev_annual and prev_q3:
                annual_rev = _sf(prev_annual["revenue"]) or 0
                annual_np = _sf(prev_annual["net_profit"]) or 0
                pq3_rev = _sf(prev_q3["revenue"]) or 0
                pq3_np = _sf(prev_q3["net_profit"]) or 0
                ttm_rev = q3_rev + (annual_rev - pq3_rev)
                ttm_np = q3_np + (annual_np - pq3_np)
                lines.append(f"\n**TTM估算**: 营收 {ttm_rev:.2f}亿元, 净利 {ttm_np:.2f}亿元")

        return "\n".join(lines)

    # ==============================================================
    # 3. Balance Sheet
    # ==============================================================

    def _collect_balance(self, bare: str) -> str:
        rows = self._q(
            "SELECT report_date, total_assets, total_equity "
            "FROM financial_balance WHERE stock_code=%s "
            "ORDER BY report_date DESC LIMIT 8",
            (bare,),
        )
        if not rows:
            return "[无资产负债表数据]"

        lines = ["### 资产负债表摘要\n"]
        lines.append("| 报告期 | 总资产(亿) | 净资产(亿) | 资产负债率 |")
        lines.append("|--------|-----------|-----------|-----------|")
        for r in rows:
            ta = _sf(r["total_assets"])
            te = _sf(r["total_equity"])
            debt_ratio = f"{(1 - te / ta) * 100:.1f}%" if ta and te and ta > 0 else "(缺失)"
            lines.append(
                f"| {r['report_date']} | {_yuan(ta)} | {_yuan(te)} | {debt_ratio} |"
            )

        # Pre-compute: asset growth rate
        if len(rows) >= 2:
            latest_ta = _sf(rows[0]["total_assets"])
            oldest_ta = _sf(rows[-1]["total_assets"])
            if latest_ta and oldest_ta and oldest_ta > 0:
                asset_growth = (latest_ta / oldest_ta - 1) * 100
                lines.append(f"\n**资产增速**: 从{_yuan(oldest_ta)}到{_yuan(latest_ta)}, "
                             f"增长{asset_growth:.1f}%（{rows[-1]['report_date']}至{rows[0]['report_date']}）")

        # Net asset per share (if we know total shares)
        latest_equity = _sf(rows[0]["total_equity"])
        if latest_equity:
            lines.append(f"**最新净资产**: {_yuan(latest_equity)}（{rows[0]['report_date']}）")

        return "\n".join(lines)

    # ==============================================================
    # 4. Valuation Snapshot (PE/PB/PS percentiles)
    # ==============================================================

    def _collect_valuation(self, bare: str, full: str) -> str:
        # Latest valuation
        latest = self._q(
            "SELECT trade_date, pe_ttm, pb, ps_ttm, dv_ttm, total_mv, circ_mv "
            "FROM trade_stock_daily_basic WHERE stock_code LIKE %s "
            "ORDER BY trade_date DESC LIMIT 1",
            (bare + "%",),
        )
        if not latest:
            return "[无估值数据]"

        v = latest[0]
        pe = _sf(v["pe_ttm"])
        pb = _sf(v["pb"])
        ps = _sf(v["ps_ttm"])
        dv = _sf(v["dv_ttm"])
        mv = _sf(v["total_mv"])

        # Latest close price
        price_rows = self._q(
            "SELECT close_price FROM trade_stock_daily WHERE stock_code=%s "
            "ORDER BY trade_date DESC LIMIT 1",
            (full,),
        )
        close_price = _sf(price_rows[0]["close_price"]) if price_rows else None

        # Historical percentiles (all available data)
        pct_sql = """
            SELECT
                (SELECT COUNT(*) FROM trade_stock_daily_basic b2
                 WHERE b2.stock_code=b1.stock_code AND b2.pe_ttm <= b1.pe_ttm AND b2.pe_ttm > 0) * 100.0 /
                NULLIF((SELECT COUNT(*) FROM trade_stock_daily_basic b3
                 WHERE b3.stock_code=b1.stock_code AND b3.pe_ttm > 0), 0) as pe_pct,
                (SELECT COUNT(*) FROM trade_stock_daily_basic b2
                 WHERE b2.stock_code=b1.stock_code AND b2.pb <= b1.pb AND b2.pb > 0) * 100.0 /
                NULLIF((SELECT COUNT(*) FROM trade_stock_daily_basic b3
                 WHERE b3.stock_code=b1.stock_code AND b3.pb > 0), 0) as pb_pct
            FROM trade_stock_daily_basic b1
            WHERE stock_code LIKE %s
            ORDER BY trade_date DESC LIMIT 1
        """
        pct_rows = self._q(pct_sql, (bare + "%",))
        pe_pct = _sf(pct_rows[0]["pe_pct"]) if pct_rows else None
        pb_pct = _sf(pct_rows[0]["pb_pct"]) if pct_rows else None

        # PE/PB range (min/max/median)
        range_rows = self._q(
            "SELECT MIN(pe_ttm) as pe_min, MAX(pe_ttm) as pe_max, "
            "MIN(pb) as pb_min, MAX(pb) as pb_max "
            "FROM trade_stock_daily_basic WHERE stock_code LIKE %s AND pe_ttm > 0 AND pb > 0",
            (bare + "%",),
        )
        rng = range_rows[0] if range_rows else {}

        # Data date range
        date_range = self._q(
            "SELECT MIN(trade_date) as mn, MAX(trade_date) as mx, COUNT(*) as cnt "
            "FROM trade_stock_daily_basic WHERE stock_code LIKE %s",
            (bare + "%",),
        )
        dr = date_range[0] if date_range else {}

        lines = ["### 估值快照\n"]
        lines.append(f"**数据日期**: {v['trade_date']}")
        if close_price:
            lines.append(f"**最新收盘价**: {close_price:.2f}元")
        lines.append(f"**总市值**: {mv / 10000:.2f}亿元" if mv else "**总市值**: (缺失)")
        lines.append("")
        lines.append("| 指标 | 当前值 | 历史分位 | 历史最低 | 历史最高 |")
        lines.append("|------|-------|---------|---------|---------|")
        lines.append(
            f"| PE(TTM) | {_num(pe)} | {_pct(pe_pct, 1)} | {_num(rng.get('pe_min'))} | {_num(rng.get('pe_max'))} |"
        )
        lines.append(
            f"| PB | {_num(pb)} | {_pct(pb_pct, 1)} | {_num(rng.get('pb_min'))} | {_num(rng.get('pb_max'))} |"
        )
        lines.append(f"| PS(TTM) | {_num(ps)} | -- | -- | -- |")
        lines.append(f"| 股息率(TTM) | {_pct(dv) if dv else '(缺失)'} | -- | -- | -- |")
        lines.append(
            f"\n**分位数据区间**: {dr.get('mn', '?')} 至 {dr.get('mx', '?')}，共{dr.get('cnt', '?')}个交易日"
        )

        # Pre-computed verdict
        if pe_pct is not None:
            if pe_pct >= 90:
                verdict = f"PE处于历史{pe_pct:.0f}%分位，属于极度偏高区间"
            elif pe_pct >= 70:
                verdict = f"PE处于历史{pe_pct:.0f}%分位，属于偏高区间"
            elif pe_pct >= 30:
                verdict = f"PE处于历史{pe_pct:.0f}%分位，属于合理区间"
            else:
                verdict = f"PE处于历史{pe_pct:.0f}%分位，属于偏低区间"
            lines.append(f"\n**估值分位判断**: {verdict}")

        return "\n".join(lines)

    # ==============================================================
    # 5. Price & Technical
    # ==============================================================

    def _collect_technical(self, full: str) -> str:
        # Fetch recent 250 days K-line for MA calculation
        rows = self._q(
            "SELECT trade_date, open_price, high_price, low_price, close_price, "
            "volume, amount, turnover_rate FROM trade_stock_daily "
            "WHERE stock_code=%s ORDER BY trade_date DESC LIMIT 260",
            (full,),
        )
        if not rows:
            return "[无K线数据]"

        rows.reverse()  # chronological order
        closes = [_sf(r["close_price"]) for r in rows]
        volumes = [_sf(r["volume"]) for r in rows]
        highs = [_sf(r["high_price"]) for r in rows]
        lows = [_sf(r["low_price"]) for r in rows]

        latest = rows[-1]
        close = _sf(latest["close_price"])

        lines = ["### 价格与技术面\n"]
        lines.append(f"**最新交易日**: {latest['trade_date']}")
        lines.append(f"**收盘价**: {_num(close)}元")
        lines.append(f"**成交量**: {_num(_sf(latest['volume']), 0)}手")
        lines.append(f"**成交额**: {_num(_sf(latest['amount']), 0)}元")
        lines.append(f"**换手率**: {_pct(latest.get('turnover_rate'))}")

        # Moving averages
        def _ma(n):
            if len(closes) < n:
                return None
            valid = [c for c in closes[-n:] if c is not None]
            return sum(valid) / len(valid) if valid else None

        ma5 = _ma(5)
        ma20 = _ma(20)
        ma60 = _ma(60)
        ma120 = _ma(120)
        ma250 = _ma(250)

        lines.append("\n**均线系统**:")
        lines.append(f"- MA5: {_num(ma5)}元")
        lines.append(f"- MA20: {_num(ma20)}元")
        lines.append(f"- MA60: {_num(ma60)}元")
        lines.append(f"- MA120: {_num(ma120)}元")
        lines.append(f"- MA250: {_num(ma250)}元")

        # MA alignment judgment
        if all(v is not None for v in [ma5, ma20, ma60]):
            if ma5 > ma20 > ma60:
                lines.append("- **均线排列**: 多头排列（MA5 > MA20 > MA60）")
            elif ma5 < ma20 < ma60:
                lines.append("- **均线排列**: 空头排列（MA5 < MA20 < MA60）")
            else:
                lines.append("- **均线排列**: 交叉/震荡排列")

        # Price vs MA bias
        if close and ma20:
            bias20 = (close / ma20 - 1) * 100
            lines.append(f"- **MA20偏离度**: {bias20:+.2f}%")
        if close and ma60:
            bias60 = (close / ma60 - 1) * 100
            lines.append(f"- **MA60偏离度**: {bias60:+.2f}%")

        # 52-week high/low (250 trading days)
        valid_highs = [h for h in highs[-250:] if h is not None]
        valid_lows = [l for l in lows[-250:] if l is not None]
        if valid_highs and valid_lows and close:
            h52 = max(valid_highs)
            l52 = min(valid_lows)
            pos = (close - l52) / (h52 - l52) * 100 if h52 != l52 else 50
            lines.append(f"\n**52周价格区间**: {l52:.2f} ~ {h52:.2f}元")
            lines.append(f"**当前位置**: {pos:.1f}%（0%=52周最低, 100%=52周最高）")

        # Recent volatility (20-day)
        if len(closes) >= 21:
            recent = closes[-21:]
            valid_recent = [c for c in recent if c is not None]
            if len(valid_recent) >= 20:
                returns = [(valid_recent[i] / valid_recent[i - 1] - 1) for i in range(1, len(valid_recent))]
                avg_ret = sum(returns) / len(returns)
                var = sum((r - avg_ret) ** 2 for r in returns) / len(returns)
                vol_20d = var ** 0.5 * (252 ** 0.5) * 100  # annualized
                lines.append(f"**20日年化波动率**: {vol_20d:.1f}%")

        # Volume trend
        if len(volumes) >= 20:
            vol_5 = sum(v for v in volumes[-5:] if v) / max(sum(1 for v in volumes[-5:] if v), 1)
            vol_20 = sum(v for v in volumes[-20:] if v) / max(sum(1 for v in volumes[-20:] if v), 1)
            if vol_20 > 0:
                vol_ratio = vol_5 / vol_20
                lines.append(f"**量比(5日/20日)**: {vol_ratio:.2f}")
                if vol_ratio > 1.5:
                    lines.append("  -> 近期明显放量")
                elif vol_ratio < 0.7:
                    lines.append("  -> 近期明显缩量")

        # MACD simple calculation
        if len(closes) >= 35:
            valid_c = [c for c in closes if c is not None]
            if len(valid_c) >= 35:
                ema12 = self._ema(valid_c, 12)
                ema26 = self._ema(valid_c, 26)
                dif = ema12 - ema26
                # DEA is 9-period EMA of DIF series
                dif_series = []
                e12, e26 = valid_c[0], valid_c[0]
                for c in valid_c[1:]:
                    e12 = e12 * (11 / 13) + c * (2 / 13)
                    e26 = e26 * (25 / 27) + c * (2 / 27)
                    dif_series.append(e12 - e26)
                if len(dif_series) >= 9:
                    dea = dif_series[0]
                    for d in dif_series[1:]:
                        dea = dea * (8 / 10) + d * (2 / 10)
                    macd_hist = (dif_series[-1] - dea) * 2
                    lines.append(f"\n**MACD**: DIF={dif_series[-1]:.3f}, DEA={dea:.3f}, 柱={macd_hist:.3f}")
                    if dif_series[-1] > dea and (len(dif_series) > 1 and dif_series[-2] <= dea * (8/10) + dif_series[-2] * (2/10)):
                        lines.append("  -> MACD金叉信号")
                    elif dif_series[-1] > 0 and dea > 0:
                        lines.append("  -> MACD零轴上方，偏多")
                    elif dif_series[-1] < 0 and dea < 0:
                        lines.append("  -> MACD零轴下方，偏空")

        # RSI
        if len(closes) >= 15:
            valid_c = [c for c in closes if c is not None]
            if len(valid_c) >= 15:
                rsi14 = self._rsi(valid_c, 14)
                lines.append(f"**RSI(14)**: {rsi14:.1f}")
                if rsi14 >= 80:
                    lines.append("  -> 超买区域（>=80）")
                elif rsi14 >= 70:
                    lines.append("  -> 偏强区域（70-80）")
                elif rsi14 <= 20:
                    lines.append("  -> 超卖区域（<=20）")
                elif rsi14 <= 30:
                    lines.append("  -> 偏弱区域（20-30）")

        return "\n".join(lines)

    # ==============================================================
    # 6. Dividend
    # ==============================================================

    def _collect_dividend(self, bare: str, full: str) -> str:
        rows = self._q(
            "SELECT ex_date, cash_div FROM financial_dividend "
            "WHERE stock_code=%s ORDER BY ex_date DESC LIMIT 6",
            (bare,),
        )
        if not rows:
            return "[无分红数据]"

        # Get latest close for yield calculation
        price_rows = self._q(
            "SELECT close_price FROM trade_stock_daily WHERE stock_code=%s "
            "ORDER BY trade_date DESC LIMIT 1",
            (full,),
        )
        close = _sf(price_rows[0]["close_price"]) if price_rows else None

        lines = ["### 分红历史\n"]
        lines.append("| 除权日 | 每股派息(元/10股) | 股息率 |")
        lines.append("|--------|-----------------|--------|")
        for r in rows:
            div = _sf(r["cash_div"])
            if div is not None and close:
                # cash_div is per 10 shares (元/10股)
                yield_pct = div / 10 / close * 100
                lines.append(f"| {r['ex_date']} | {div:.2f} | {yield_pct:.2f}% |")
            else:
                lines.append(f"| {r['ex_date']} | {_num(div)} | -- |")

        # Average payout
        divs = [_sf(r["cash_div"]) for r in rows if _sf(r["cash_div"])]
        if divs:
            avg_div = sum(divs) / len(divs)
            lines.append(f"\n**近{len(divs)}次平均派息**: {avg_div:.2f}元/10股")
            if close:
                lines.append(f"**平均股息率**: {avg_div / 10 / close * 100:.2f}%")

            # Trend
            if len(divs) >= 3:
                if divs[0] < divs[-1]:
                    lines.append("**趋势**: 派息金额呈下降趋势")
                elif divs[0] > divs[-1]:
                    lines.append("**趋势**: 派息金额呈上升趋势")
                else:
                    lines.append("**趋势**: 派息金额基本稳定")

        return "\n".join(lines)

    # ==============================================================
    # 7. Cash Flow
    # ==============================================================

    def _collect_cashflow(self, bare: str) -> str:
        rows = self._q(
            "SELECT report_date, operating_cashflow, investing_cashflow, "
            "financing_cashflow, net_cashflow FROM financial_cashflow "
            "WHERE stock_code=%s ORDER BY report_date DESC LIMIT 4",
            (bare,),
        )
        if not rows:
            return "[无现金流量表数据 - 该维度分析时请注明数据缺失]"

        lines = ["### 现金流量表\n"]
        lines.append("| 报告期 | 经营现金流(亿) | 投资现金流(亿) | 筹资现金流(亿) | 净现金流(亿) |")
        lines.append("|--------|-------------|-------------|-------------|------------|")
        for r in rows:
            lines.append(
                f"| {r['report_date']} | {_yuan(r['operating_cashflow'])} | "
                f"{_yuan(r['investing_cashflow'])} | {_yuan(r['financing_cashflow'])} | "
                f"{_yuan(r['net_cashflow'])} |"
            )
        return "\n".join(lines)

    # ==============================================================
    # 8. Income Detail
    # ==============================================================

    def _collect_income_detail(self, bare: str) -> str:
        rows = self._q(
            "SELECT * FROM financial_income_detail "
            "WHERE stock_code=%s ORDER BY report_date DESC LIMIT 4",
            (bare,),
        )
        if not rows:
            return "[无利润明细数据 - 该维度分析时请注明数据缺失]"

        lines = ["### 利润明细\n"]
        for r in rows:
            lines.append(f"**{r['report_date']}**:")
            if r.get("operating_revenue"):
                lines.append(f"  营业收入: {_yuan(r['operating_revenue'])}")
            if r.get("operating_cost"):
                lines.append(f"  营业成本: {_yuan(r['operating_cost'])}")
            if r.get("rd_expense"):
                lines.append(f"  研发费用: {_yuan(r['rd_expense'])}")
            if r.get("asset_impairment"):
                lines.append(f"  资产减值: {_yuan(r['asset_impairment'])}")
            if r.get("credit_impairment"):
                lines.append(f"  信用减值: {_yuan(r['credit_impairment'])}")
            if r.get("investment_income"):
                lines.append(f"  投资收益: {_yuan(r['investment_income'])}")
            if r.get("fair_value_change"):
                lines.append(f"  公允价值变动: {_yuan(r['fair_value_change'])}")
            if r.get("non_operating_income"):
                lines.append(f"  营业外收入: {_yuan(r['non_operating_income'])}")
        return "\n".join(lines)

    # ==============================================================
    # 9. RPS & Momentum
    # ==============================================================

    def _collect_rps(self, full: str) -> str:
        rows = self._q(
            "SELECT trade_date, rps_20, rps_60, rps_120, rps_250, rps_slope "
            "FROM trade_stock_rps WHERE stock_code=%s "
            "ORDER BY trade_date DESC LIMIT 5",
            (full,),
        )
        if not rows:
            return "[无RPS数据]"

        lines = ["### 相对强度(RPS)\n"]
        lines.append("| 日期 | RPS20 | RPS60 | RPS120 | RPS250 |")
        lines.append("|------|-------|-------|--------|--------|")
        for r in rows:
            lines.append(
                f"| {r['trade_date']} | {_num(r['rps_20'], 1)} | {_num(r['rps_60'], 1)} | "
                f"{_num(r['rps_120'], 1)} | {_num(r['rps_250'], 1)} |"
            )

        # Extended factor (momentum, liquidity)
        ext = self._q(
            "SELECT calc_date, mom_5, mom_10, turnover_20_mean, amihud_illiquidity, "
            "roe_ttm, gross_margin, net_profit_growth, revenue_growth "
            "FROM trade_stock_extended_factor WHERE stock_code=%s "
            "ORDER BY calc_date DESC LIMIT 1",
            (full,),
        )
        if ext:
            e = ext[0]
            lines.append(f"\n**扩展因子**（{e['calc_date']}）:")
            lines.append(f"- 5日动量: {_pct((_sf(e['mom_5']) or 0) * 100)}")
            lines.append(f"- 10日动量: {_pct((_sf(e['mom_10']) or 0) * 100)}")
            lines.append(f"- 20日平均换手率: {_pct(e['turnover_20_mean'])}")
            lines.append(f"- ROE(TTM): {_pct(e['roe_ttm'])}")
            lines.append(f"- 毛利率: {_pct(e['gross_margin'])}")
            lines.append(f"- 净利增速: {_pct((_sf(e['net_profit_growth']) or 0) * 100)}")
            lines.append(f"- 营收增速: {_pct((_sf(e['revenue_growth']) or 0) * 100)}")

        # Momentum judgment
        latest = rows[0]
        rps250 = _sf(latest["rps_250"])
        rps60 = _sf(latest["rps_60"])
        rps20 = _sf(latest["rps_20"])
        if rps250 is not None:
            lines.append(f"\n**动量判断**:")
            if rps250 >= 90:
                lines.append(f"- 长期强势（RPS250={rps250:.0f}，超过{rps250:.0f}%的股票）")
            elif rps250 >= 70:
                lines.append(f"- 长期偏强（RPS250={rps250:.0f}）")
            elif rps250 <= 30:
                lines.append(f"- 长期弱势（RPS250={rps250:.0f}）")
            if rps20 and rps250 and rps20 < rps250 - 30:
                lines.append(f"- [WARN] 短期动量衰减：RPS20({rps20:.0f}) << RPS250({rps250:.0f})")

        return "\n".join(lines)

    # ==============================================================
    # 10. Quality Factors
    # ==============================================================

    def _collect_quality(self, full: str) -> str:
        rows = self._q(
            "SELECT calc_date, cash_flow_ratio, accrual, current_ratio, roa, debt_ratio "
            "FROM trade_stock_quality_factor WHERE stock_code=%s "
            "ORDER BY calc_date DESC LIMIT 3",
            (full,),
        )
        if not rows:
            return "[无质量因子数据]"

        r = rows[0]
        cfr = _sf(r["cash_flow_ratio"])

        lines = ["### 质量因子\n"]
        lines.append(f"**数据日期**: {r['calc_date']}")
        lines.append(f"- 现金流比率(经营现金流/净利): {_num(cfr)}")
        lines.append(f"- 应计比率: {_num(r['accrual'])}")
        lines.append(f"- 流动比率: {_num(r['current_ratio'])}")
        lines.append(f"- ROA: {_pct(r['roa'])}")
        lines.append(f"- 资产负债率: {_pct(r['debt_ratio'])}")

        # Pre-computed quality judgments
        if cfr is not None:
            if cfr < 0:
                lines.append("\n**现金流质量**: [RED] 经营现金流为负，利润含金量存疑")
            elif cfr < 0.5:
                lines.append("\n**现金流质量**: [WARN] 经营现金流低于净利50%，利润转化效率偏低")
            elif cfr >= 0.8:
                lines.append("\n**现金流质量**: [OK] 经营现金流充足，利润含金量高")

        debt = _sf(r["debt_ratio"])
        if debt is not None:
            if debt >= 70:
                lines.append(f"**负债水平**: [WARN] 资产负债率{debt:.1f}%，偏高")
            elif debt <= 30:
                lines.append(f"**负债水平**: [OK] 资产负债率{debt:.1f}%，稳健")

        return "\n".join(lines)

    # ==============================================================
    # 11. Growth Analysis (pre-computed)
    # ==============================================================

    def _compute_growth(self, bare: str) -> str:
        rows = self._q(
            "SELECT report_date, revenue, net_profit, net_profit_yoy, roe, eps "
            "FROM financial_income WHERE stock_code=%s "
            "AND report_date LIKE '%%12-31' ORDER BY report_date DESC LIMIT 4",
            (bare,),
        )
        if len(rows) < 2:
            return "[年度数据不足，无法计算增长趋势]"

        lines = ["### 增长趋势分析（预计算）\n"]

        # Revenue CAGR
        newest = rows[0]
        oldest = rows[-1]
        n_years = len(rows) - 1
        rev_new = _sf(newest["revenue"])
        rev_old = _sf(oldest["revenue"])
        if rev_new and rev_old and rev_old > 0 and n_years > 0:
            cagr_rev = ((rev_new / rev_old) ** (1 / n_years) - 1) * 100
            lines.append(f"**营收CAGR({oldest['report_date']}~{newest['report_date']})**: {cagr_rev:.1f}%")

        # Net profit CAGR
        np_new = _sf(newest["net_profit"])
        np_old = _sf(oldest["net_profit"])
        if np_new and np_old and np_old > 0 and n_years > 0:
            cagr_np = ((np_new / np_old) ** (1 / n_years) - 1) * 100
            lines.append(f"**净利CAGR({oldest['report_date']}~{newest['report_date']})**: {cagr_np:.1f}%")

        # ROE trend
        roe_list = [(str(r["report_date"]), _sf(r["roe"])) for r in rows if _sf(r["roe"]) is not None]
        if len(roe_list) >= 2:
            lines.append("\n**ROE年度趋势**:")
            for rd, roe in roe_list:
                lines.append(f"- {rd}: ROE {roe:.2f}%")
            # Direction
            if roe_list[0][1] > roe_list[-1][1]:
                lines.append("-> ROE趋势: 上升")
            elif roe_list[0][1] < roe_list[-1][1]:
                lines.append("-> ROE趋势: 下降")
            else:
                lines.append("-> ROE趋势: 基本持平")

        # Latest quarter YoY
        latest_q = self._q(
            "SELECT report_date, net_profit_yoy, revenue FROM financial_income "
            "WHERE stock_code=%s ORDER BY report_date DESC LIMIT 1",
            (bare,),
        )
        if latest_q:
            lq = latest_q[0]
            lines.append(
                f"\n**最新季报({lq['report_date']})净利YoY**: {_pct(lq['net_profit_yoy'])}"
            )

        # Growth quality: revenue vs profit divergence
        if len(rows) >= 2:
            rev_growth = ((rev_new / rev_old) - 1) * 100 if rev_new and rev_old and rev_old > 0 else None
            np_growth = ((np_new / np_old) - 1) * 100 if np_new and np_old and np_old > 0 else None
            if rev_growth is not None and np_growth is not None:
                if np_growth > rev_growth + 10:
                    lines.append("\n**增长质量**: 利润增速显著快于营收，可能存在降本增效或一次性收益")
                elif rev_growth > np_growth + 10:
                    lines.append("\n**增长质量**: 营收增速显著快于利润，可能存在增收不增利")

        return "\n".join(lines)

    # ==============================================================
    # 12. ROE Trend
    # ==============================================================

    def _compute_roe_trend(self, bare: str) -> str:
        # ROE from financial_income
        rows = self._q(
            "SELECT report_date, roe, revenue, net_profit FROM financial_income "
            "WHERE stock_code=%s AND report_date LIKE '%%12-31' "
            "ORDER BY report_date DESC LIMIT 5",
            (bare,),
        )
        # Balance sheet for equity
        bal_rows = self._q(
            "SELECT report_date, total_assets, total_equity FROM financial_balance "
            "WHERE stock_code=%s AND report_date LIKE '%%12-31' "
            "ORDER BY report_date DESC LIMIT 5",
            (bare,),
        )

        if not rows:
            return "[无年度ROE数据]"

        lines = ["### ROE与杜邦拆解\n"]

        # Merge by report_date
        bal_map = {str(r["report_date"]): r for r in bal_rows}

        lines.append("| 年度 | ROE | 净利率 | 资产周转率 | 权益乘数 |")
        lines.append("|------|-----|--------|-----------|---------|")

        for r in rows:
            rd = str(r["report_date"])
            roe = _sf(r["roe"])
            rev = _sf(r["revenue"])
            np_ = _sf(r["net_profit"])
            bal = bal_map.get(rd)

            net_margin = (np_ / rev * 100) if (rev and np_ and rev > 0) else None
            ta = _sf(bal["total_assets"]) if bal else None
            te = _sf(bal["total_equity"]) if bal else None
            asset_turnover = (rev / ta) if (rev and ta and ta > 0) else None
            equity_mult = (ta / te) if (ta and te and te > 0) else None

            lines.append(
                f"| {rd} | {_pct(roe)} | {_pct(net_margin)} | "
                f"{_num(asset_turnover) + 'x' if asset_turnover else '(缺失)'} | "
                f"{_num(equity_mult) + 'x' if equity_mult else '(缺失)'} |"
            )

        return "\n".join(lines)

    # ==============================================================
    # 13. Valuation Verdict (pre-computed)
    # ==============================================================

    def _compute_valuation_verdict(self, bare: str, full: str) -> str:
        # Latest valuation
        v = self._q(
            "SELECT pe_ttm, pb, ps_ttm, dv_ttm, total_mv FROM trade_stock_daily_basic "
            "WHERE stock_code LIKE %s ORDER BY trade_date DESC LIMIT 1",
            (bare + "%",),
        )
        if not v:
            return "[无估值数据]"

        pe = _sf(v[0]["pe_ttm"])
        pb = _sf(v[0]["pb"])
        mv = _sf(v[0]["total_mv"])

        # Latest ROE
        roe_row = self._q(
            "SELECT roe FROM financial_income WHERE stock_code=%s "
            "AND report_date LIKE '%%12-31' ORDER BY report_date DESC LIMIT 1",
            (bare,),
        )
        roe = _sf(roe_row[0]["roe"]) if roe_row else None

        # Latest net profit for PEG
        np_rows = self._q(
            "SELECT net_profit_yoy FROM financial_income WHERE stock_code=%s "
            "ORDER BY report_date DESC LIMIT 1",
            (bare,),
        )
        np_yoy = _sf(np_rows[0]["net_profit_yoy"]) if np_rows else None

        lines = ["### 估值综合判断（预计算）\n"]

        if pe and pe > 0:
            lines.append(f"**PE(TTM)**: {pe:.1f}x")
            if np_yoy and np_yoy > 0:
                peg = pe / np_yoy
                lines.append(f"**PEG**: {peg:.2f} (PE / 净利增速)")
                if peg > 2:
                    lines.append("  -> PEG>2, 估值相对增速偏贵")
                elif peg < 1:
                    lines.append("  -> PEG<1, 估值相对增速偏低")
                else:
                    lines.append("  -> PEG在1-2之间, 估值与增速基本匹配")
            elif np_yoy and np_yoy < 0:
                lines.append(f"  -> 净利负增长({np_yoy:.1f}%), PE参考价值下降")

        if pb and roe:
            lines.append(f"\n**PB**: {pb:.2f}x, **ROE**: {roe:.2f}%")
            pb_roe_ratio = pb / (roe / 100) if roe > 0 else None
            if pb_roe_ratio:
                lines.append(f"**PB/ROE比**: {pb_roe_ratio:.1f}")
                if pb_roe_ratio > 200:
                    lines.append("  -> PB相对ROE显著偏高")
                elif pb_roe_ratio < 50:
                    lines.append("  -> PB相对ROE显著偏低")

        if mv:
            lines.append(f"\n**总市值**: {mv / 10000:.1f}亿元")

        return "\n".join(lines)

    # ==============================================================
    # Helper: EMA / RSI calculation
    # ==============================================================

    @staticmethod
    def _ema(data: List[float], period: int) -> float:
        multiplier = 2 / (period + 1)
        ema = data[0]
        for val in data[1:]:
            ema = (val - ema) * multiplier + ema
        return ema

    @staticmethod
    def _rsi(data: List[float], period: int = 14) -> float:
        gains, losses = [], []
        for i in range(1, len(data)):
            diff = data[i] - data[i - 1]
            gains.append(diff if diff > 0 else 0)
            losses.append(-diff if diff < 0 else 0)

        if len(gains) < period:
            return 50.0

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - 100 / (1 + rs)
