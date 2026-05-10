# -*- coding: utf-8 -*-
"""
EightSectionDataCollector - 八章节全面分析数据收集层

从 MySQL 提取八章节分析所需的全部数据，预计算派生指标。
所有数值计算在此完成，LLM 只做文字解读。

数据来源表：
- trade_stock_info         公司简介(主营业务/公司介绍)
- trade_stock_basic        公司基本信息(申万行业)
- financial_income         利润表(营收/净利/ROE/毛利率)
- financial_balance        资产负债表
- financial_cashflow       现金流量表
- trade_stock_daily_basic  估值(PE/PB/PS/市值)
- trade_stock_daily        K线行情
- trade_stock_basic_factor 基础因子(动量/换手/波动率)
- trade_technical_indicator 技术指标(MA/MACD/RSI/KDJ)
- research_announcements   公司公告
- stock_news               公司新闻
"""
import logging
from typing import Dict, List, Optional

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
    f = _sf(val)
    if f is None:
        return "(数据缺失)"
    return f"{f:.{digits}f}%"


def _yuan(val, digits=2) -> str:
    f = _sf(val)
    if f is None:
        return "(数据缺失)"
    return f"{f:.{digits}f}亿"


def _num(val, digits=2) -> str:
    f = _sf(val)
    if f is None:
        return "(数据缺失)"
    return f"{f:.{digits}f}"


class EightSectionDataCollector:
    """八章节全面分析数据收集器。"""

    def __init__(self, db_env: str = "online"):
        from config.db import execute_query as _eq
        self._eq = _eq
        self._env = db_env
        self._beta_reason = "默认"

    def _q(self, sql: str, params: tuple = ()) -> List[Dict]:
        """Execute query and return list of dicts."""
        return list(self._eq(sql, params, env=self._env))

    # ==============================================================
    # Public API
    # ==============================================================

    def collect(self, stock_code: str, stock_name: str = "") -> Dict[str, str]:
        """
        Collect all data for eight-section analysis.

        Returns dict with keys for each chapter's data.
        """
        bare = stock_code.split(".")[0] if "." in stock_code else stock_code
        if "." not in stock_code:
            full = self._resolve_full_code(bare)
        else:
            full = stock_code

        result: Dict[str, str] = {}

        collectors = [
            ("company_profile",      lambda: self._collect_company_profile(full, bare, stock_name)),
            ("financial_summary",    lambda: self._collect_financial_summary(bare)),
            ("balance_sheet",        lambda: self._collect_balance_sheet(bare)),
            ("cashflow",             lambda: self._collect_cashflow(bare)),
            ("valuation_snapshot",   lambda: self._collect_valuation(bare)),
            ("daily_quotes",         lambda: self._collect_daily_quotes(full)),
            ("technical_factors",    lambda: self._collect_technical_factors(full)),
            ("announcements",        lambda: self._collect_announcements(bare)),
            ("news",                 lambda: self._collect_news(bare)),
            ("comparable_companies", lambda: self._find_comparables(full, bare)),
            ("dcf_inputs",           lambda: self._prepare_dcf_inputs(bare, full)),
        ]

        for key, fn in collectors:
            try:
                result[key] = fn()
            except Exception as e:
                logger.warning("[EightSection] %s failed for %s: %s", key, stock_code, e)
                result[key] = f"[{key} 数据暂不可用]"

        # Data completeness check
        result["data_completeness"] = self._check_completeness(result)

        return result

    def _resolve_full_code(self, bare: str) -> str:
        """Resolve bare code to full code with suffix."""
        row = self._q(
            "SELECT stock_code FROM trade_stock_daily "
            "WHERE stock_code LIKE %s ORDER BY trade_date DESC LIMIT 1",
            (bare + ".%",),
        )
        if row:
            return row[0]["stock_code"]
        return bare + (".SH" if bare.startswith("6") else ".SZ")

    # ==============================================================
    # 1. Company Profile (Ch1)
    # ==============================================================

    def _collect_company_profile(self, full: str, bare: str, name: str) -> str:
        # Try trade_stock_info first (has main_business, company_intro, listed_date)
        info = self._q(
            "SELECT stock_code, stock_name, industry, main_business, business_scope, "
            "company_intro, listed_date FROM trade_stock_info WHERE stock_code=%s LIMIT 1",
            (full,),
        )
        # Also get trade_stock_basic for sw_industry classification
        basic = self._q(
            "SELECT stock_code, stock_name, sw_level1, sw_level2, is_st "
            "FROM trade_stock_basic WHERE stock_code=%s LIMIT 1",
            (full,),
        )

        if not basic and not info:
            return f"公司: {name}({full}), 行业: (未知)"

        b = basic[0] if basic else {}
        i = info[0] if info else {}
        stock_name = b.get("stock_name") or i.get("stock_name") or name
        industry = b.get("sw_level2") or b.get("sw_level1") or i.get("industry") or "(未知)"
        st_tag = " [ST]" if b.get("is_st") else ""

        lines = [
            f"**公司名称**: {stock_name}{st_tag}",
            f"**股票代码**: {full}",
            f"**行业分类**: {industry}",
        ]

        # Latest market cap and close price
        val = self._q(
            "SELECT total_mv, pe_ttm, pb FROM trade_stock_daily_basic "
            "WHERE stock_code=%s ORDER BY trade_date DESC LIMIT 1",
            (full,),
        )
        if val:
            v = val[0]
            if _sf(v.get("total_mv")):
                lines.append(f"**最新市值**: {_num(v['total_mv'])}亿元")
            if _sf(v.get("pe_ttm")):
                lines.append(f"**PE(TTM)**: {_num(v['pe_ttm'])}")

        # Listed date
        listed = i.get("listed_date")
        if listed:
            lines.append(f"**上市时间**: {listed}")

        main_biz = i.get("main_business")
        if main_biz:
            lines.append(f"**主营业务**: {main_biz}")

        intro = i.get("company_intro")
        if intro:
            if len(intro) > 300:
                intro = intro[:300] + "..."
            lines.append(f"**公司简介**: {intro}")

        return "\n".join(lines)

    # ==============================================================
    # 2. Financial Summary (Ch2) - annual + latest quarter
    # ==============================================================

    def _collect_financial_summary(self, bare: str) -> str:
        # Annual reports (up to 8 years)
        annual = self._q(
            "SELECT report_date, revenue, net_profit, net_profit_yoy, roe, gross_margin "
            "FROM financial_income WHERE stock_code=%s AND report_date LIKE '%%12-31' "
            "ORDER BY report_date DESC LIMIT 8",
            (bare,),
        )
        # All recent periods (up to 12)
        all_periods = self._q(
            "SELECT report_date, revenue, net_profit, net_profit_yoy, roe, gross_margin, eps "
            "FROM financial_income WHERE stock_code=%s "
            "ORDER BY report_date DESC LIMIT 12",
            (bare,),
        )

        if not all_periods:
            return "[无财务数据]"

        lines = ["### 财务数据汇总\n"]

        # Recent 12 periods table
        lines.append("| 报告期 | 营收(亿) | 净利(亿) | 净利YoY | ROE | 毛利率 | EPS |")
        lines.append("|--------|---------|---------|---------|-----|--------|-----|")
        for r in all_periods:
            lines.append(
                f"| {r['report_date']} | {_num(r['revenue'])} | {_num(r['net_profit'])} | "
                f"{_pct(r['net_profit_yoy'])} | {_pct(r['roe'])} | {_pct(r['gross_margin'])} | "
                f"{_num(r['eps'])} |"
            )

        # Annual trend summary
        if annual and len(annual) >= 2:
            lines.append("\n**年度趋势**:")
            for a in annual[:5]:
                lines.append(
                    f"- {a['report_date']}: 营收{_yuan(a['revenue'])}, "
                    f"净利{_yuan(a['net_profit'])}, YoY {_pct(a['net_profit_yoy'])}, "
                    f"ROE {_pct(a['roe'])}, 毛利率 {_pct(a['gross_margin'])}"
                )

            # Revenue CAGR
            n = len(annual)
            rev_new = _sf(annual[0]["revenue"])
            rev_old = _sf(annual[-1]["revenue"])
            if rev_new and rev_old and rev_old > 0 and n > 1:
                cagr = ((rev_new / rev_old) ** (1 / (n - 1)) - 1) * 100
                lines.append(f"\n**营收CAGR({annual[-1]['report_date']}~{annual[0]['report_date']})**: {cagr:.1f}%")

        # Latest quarter vs same quarter last year
        if len(all_periods) >= 5:
            latest = all_periods[0]
            latest_rd = str(latest["report_date"])
            # Find same quarter previous year
            month_day = latest_rd[4:]  # e.g. "-03-31"
            prev_same = next(
                (r for r in all_periods[1:] if str(r["report_date"]).endswith(month_day[1:])),
                None,
            )
            if prev_same:
                lr = _sf(latest["revenue"]) or 0
                pr = _sf(prev_same["revenue"]) or 0
                lnp = _sf(latest["net_profit"]) or 0
                pnp = _sf(prev_same["net_profit"]) or 0
                if pr > 0:
                    rev_chg = (lr / pr - 1) * 100
                    lines.append(f"\n**最新季度对比** ({latest_rd} vs {prev_same['report_date']}):")
                    lines.append(f"- 营收: {_yuan(lr)} vs {_yuan(pr)}, 同比{rev_chg:+.1f}%")
                    if pnp != 0:
                        np_chg = (lnp / abs(pnp) - 1) * 100
                        if pnp < 0:
                            lines.append(f"- 净利: {_yuan(lnp)} vs {_yuan(pnp)}, 亏损同比变化{np_chg:+.1f}%")
                        else:
                            lines.append(f"- 净利: {_yuan(lnp)} vs {_yuan(pnp)}, 同比{np_chg:+.1f}%")
                    lines.append(f"- 毛利率: {_pct(latest['gross_margin'])} vs {_pct(prev_same['gross_margin'])}")

        return "\n".join(lines)

    # ==============================================================
    # 3. Balance Sheet (Ch2)
    # ==============================================================

    def _collect_balance_sheet(self, bare: str) -> str:
        rows = self._q(
            "SELECT report_date, total_assets, total_equity "
            "FROM financial_balance WHERE stock_code=%s "
            "ORDER BY report_date DESC LIMIT 8",
            (bare,),
        )
        if not rows:
            return "[无资产负债表数据]"

        lines = ["### 资产负债表\n"]
        lines.append("| 报告期 | 总资产(亿) | 净资产(亿) | 资产负债率 |")
        lines.append("|--------|-----------|-----------|-----------|")
        for r in rows:
            ta = _sf(r["total_assets"])
            te = _sf(r["total_equity"])
            if ta and te and ta > 0:
                dr = (1 - te / ta) * 100
                lines.append(f"| {r['report_date']} | {_yuan(ta)} | {_yuan(te)} | {dr:.1f}% |")
            else:
                lines.append(f"| {r['report_date']} | {_yuan(ta)} | {_yuan(te)} | (缺失) |")

        return "\n".join(lines)

    # ==============================================================
    # 4. Cash Flow (Ch2 - profit quality)
    # ==============================================================

    def _collect_cashflow(self, bare: str) -> str:
        rows = self._q(
            "SELECT report_date, operating_cashflow, investing_cashflow, "
            "financing_cashflow FROM financial_cashflow "
            "WHERE stock_code=%s ORDER BY report_date DESC LIMIT 8",
            (bare,),
        )
        if not rows:
            return "[无现金流量表数据]"

        lines = ["### 现金流量表\n"]
        lines.append("| 报告期 | 经营(亿) | 投资(亿) | 筹资(亿) |")
        lines.append("|--------|---------|---------|---------|")
        for r in rows:
            lines.append(
                f"| {r['report_date']} | {_yuan(r['operating_cashflow'])} | "
                f"{_yuan(r['investing_cashflow'])} | {_yuan(r['financing_cashflow'])} |"
            )

        # OCF / net profit ratio (profit quality)
        annual_cf = [r for r in rows if str(r["report_date"]).endswith("12-31")]
        if annual_cf:
            np_rows = self._q(
                "SELECT report_date, net_profit FROM financial_income "
                "WHERE stock_code=%s AND report_date LIKE '%%12-31' "
                "ORDER BY report_date DESC LIMIT 8",
                (bare,),
            )
            np_map = {str(r["report_date"]): _sf(r["net_profit"]) for r in np_rows}

            lines.append("\n**盈利质量（经营现金流/净利润）**:")
            for r in annual_cf[:5]:
                ocf = _sf(r["operating_cashflow"])
                np_ = np_map.get(str(r["report_date"]))
                if ocf is not None and np_ is not None and np_ != 0:
                    ratio = ocf / np_
                    lines.append(f"- {r['report_date']}: OCF {_yuan(ocf)}, 净利 {_yuan(np_)}, 比率 {ratio:.2f}x")
                elif ocf is not None:
                    lines.append(f"- {r['report_date']}: OCF {_yuan(ocf)}, 净利数据缺失")

        return "\n".join(lines)

    # ==============================================================
    # 5. Valuation Snapshot (Ch3, Ch4, Ch8)
    # ==============================================================

    def _collect_valuation(self, bare: str) -> str:
        rows = self._q(
            "SELECT trade_date, total_mv, circ_mv, pe_ttm, pb, ps_ttm "
            "FROM trade_stock_daily_basic WHERE stock_code LIKE %s "
            "ORDER BY trade_date DESC LIMIT 5",
            (bare + "%",),
        )
        if not rows:
            return "[无估值数据]"

        lines = ["### 估值数据（近5个交易日）\n"]
        lines.append("| 日期 | 总市值(亿) | PE(TTM) | PB | PS(TTM) |")
        lines.append("|------|-----------|---------|------|---------|")
        for r in rows:
            mv = _sf(r["total_mv"])
            pe = _sf(r["pe_ttm"])
            pb = _sf(r["pb"])
            ps = _sf(r["ps_ttm"])
            lines.append(f"| {r['trade_date']} | {_num(mv)} | {_num(pe)} | {_num(pb)} | {_num(ps)} |")

        return "\n".join(lines)

    # ==============================================================
    # 6. Daily Quotes (Ch7)
    # ==============================================================

    def _collect_daily_quotes(self, full: str) -> str:
        rows = self._q(
            "SELECT trade_date, open_price, high_price, low_price, close_price, "
            "volume, amount FROM trade_stock_daily "
            "WHERE stock_code=%s ORDER BY trade_date DESC LIMIT 20",
            (full,),
        )
        if not rows:
            return "[无行情数据]"

        lines = ["### 近期行情（近20个交易日）\n"]
        lines.append("| 日期 | 开盘 | 最高 | 最低 | 收盘 | 成交量(手) | 成交额(万) |")
        lines.append("|------|------|------|------|------|-----------|-----------|")
        for r in rows:
            vol = _sf(r["volume"])
            amt = _sf(r["amount"])
            amt_wan = amt / 10000 if amt else None
            lines.append(
                f"| {r['trade_date']} | {_num(r['open_price'])} | {_num(r['high_price'])} | "
                f"{_num(r['low_price'])} | {_num(r['close_price'])} | "
                f"{_num(vol, 0)} | {_num(amt_wan, 0)} |"
            )

        # Simple momentum calculation
        if len(rows) >= 2:
            latest_close = _sf(rows[0]["close_price"])
            # 20-day momentum
            if len(rows) >= 20:
                close_20d_ago = _sf(rows[19]["close_price"])
                if latest_close and close_20d_ago and close_20d_ago > 0:
                    mom_20 = (latest_close / close_20d_ago - 1) * 100
                    lines.append(f"\n**20日涨幅**: {mom_20:+.1f}%")
            # 5-day momentum
            if len(rows) >= 5:
                close_5d_ago = _sf(rows[4]["close_price"])
                if latest_close and close_5d_ago and close_5d_ago > 0:
                    mom_5 = (latest_close / close_5d_ago - 1) * 100
                    lines.append(f"**5日涨幅**: {mom_5:+.1f}%")

        return "\n".join(lines)

    # ==============================================================
    # 7. Technical Factors (Ch7)
    # ==============================================================

    def _collect_technical_factors(self, full: str) -> str:
        # Basic factors (momentum, turnover, volatility)
        bf = self._q(
            "SELECT calc_date, mom_20, mom_60, turnover, volatility_20, close "
            "FROM trade_stock_basic_factor WHERE stock_code=%s "
            "ORDER BY calc_date DESC LIMIT 5",
            (full,),
        )

        lines = ["### 技术指标\n"]

        if bf:
            b = bf[0]
            lines.append(f"**数据日期**: {b['calc_date']}")
            lines.append(f"- 收盘价: {_num(b['close'])}")
            lines.append(f"- 20日动量: {_pct(_sf(b['mom_20']) * 100 if _sf(b['mom_20']) else None)}")
            lines.append(f"- 60日动量: {_pct(_sf(b['mom_60']) * 100 if _sf(b['mom_60']) else None)}")
            lines.append(f"- 换手率: {_num(b['turnover'])}%")
            lines.append(f"- 20日波动率: {_pct(_sf(b['volatility_20']) * 100 if _sf(b['volatility_20']) else None)}")
        else:
            return "[无技术面数据]"

        # Try trade_technical_indicator (may not exist in all DB environments)
        try:
            ti = self._q(
                "SELECT trade_date, ma5, ma10, ma20, ma60, ma120, ma250, "
                "macd_dif, macd_dea, macd_histogram, rsi_6, rsi_12, rsi_24, "
                "kdj_k, kdj_d, kdj_j, bollinger_upper, bollinger_middle, bollinger_lower "
                "FROM trade_technical_indicator WHERE stock_code=%s "
                "ORDER BY trade_date DESC LIMIT 1",
                (full,),
            )
            if ti:
                t = ti[0]
                lines.append(f"\n**均线系统** ({t['trade_date']}):")
                lines.append(f"- MA5/MA10/MA20: {_num(t['ma5'])} / {_num(t['ma10'])} / {_num(t['ma20'])}")
                lines.append(f"- MA60/MA120/MA250: {_num(t['ma60'])} / {_num(t['ma120'])} / {_num(t['ma250'])}")

                ma5 = _sf(t["ma5"])
                ma10 = _sf(t["ma10"])
                ma20 = _sf(t["ma20"])
                ma60 = _sf(t["ma60"])
                if all(v is not None for v in [ma5, ma10, ma20, ma60]):
                    if ma5 > ma10 > ma20 > ma60:
                        lines.append("- **均线排列**: 多头排列（MA5 > MA10 > MA20 > MA60）")
                    elif ma5 < ma10 < ma20 < ma60:
                        lines.append("- **均线排列**: 空头排列")
                    else:
                        lines.append("- **均线排列**: 交叉/震荡")

                lines.append(f"\n**MACD**: DIF={_num(t['macd_dif'], 3)}, DEA={_num(t['macd_dea'], 3)}, 柱={_num(t['macd_histogram'], 3)}")
                dif = _sf(t["macd_dif"])
                dea = _sf(t["macd_dea"])
                if dif is not None and dea is not None:
                    if dif > dea:
                        lines.append("- MACD金叉/红柱")
                    else:
                        lines.append("- MACD死叉/绿柱")

                lines.append(f"\n**RSI**: 6日={_num(t['rsi_6'], 1)}, 12日={_num(t['rsi_12'], 1)}, 24日={_num(t['rsi_24'], 1)}")
                rsi6 = _sf(t["rsi_6"])
                if rsi6 is not None:
                    if rsi6 >= 80:
                        lines.append("- RSI超买区域(>=80)")
                    elif rsi6 >= 70:
                        lines.append("- RSI偏强区域(70-80)")
                    elif rsi6 <= 20:
                        lines.append("- RSI超卖区域(<=20)")

                lines.append(f"\n**KDJ**: K={_num(t['kdj_k'], 1)}, D={_num(t['kdj_d'], 1)}, J={_num(t['kdj_j'], 1)}")
                lines.append(f"\n**布林带**: 上轨={_num(t['bollinger_upper'])}, 中轨={_num(t['bollinger_middle'])}, 下轨={_num(t['bollinger_lower'])}")
        except Exception:
            pass  # trade_technical_indicator not available, skip advanced indicators

        return "\n".join(lines)

    # ==============================================================
    # 8. Announcements (supplementary)
    # ==============================================================

    def _collect_announcements(self, bare: str, limit: int = 10) -> str:
        rows = self._q(
            "SELECT ann_date, title FROM research_announcements "
            "WHERE code=%s ORDER BY ann_date DESC LIMIT %s",
            (bare, limit),
        )
        if not rows:
            return "[暂无公告数据]"

        lines = ["### 公司公告（近10条）\n"]
        for r in rows:
            lines.append(f"- {r.get('ann_date', '')}: {r.get('title', '(无标题)')}")
        return "\n".join(lines)

    # ==============================================================
    # 9. News (supplementary)
    # ==============================================================

    def _collect_news(self, bare: str, limit: int = 5) -> str:
        # stock_news uses full code format (e.g. 688012.SH)
        rows = self._q(
            "SELECT title, publish_time FROM stock_news "
            "WHERE stock_code IN (%s, %s, %s) ORDER BY id DESC LIMIT %s",
            (bare + ".SH", bare + ".SZ", bare, limit),
        )
        if not rows:
            return "[暂无新闻数据]"

        lines = ["### 最新新闻\n"]
        for r in rows:
            lines.append(f"- {r.get('publish_time', '')}: {r.get('title', '(无标题)')}")
        return "\n".join(lines)

    # ==============================================================
    # 10. Comparable Companies (Ch3)
    # ==============================================================

    def _find_comparables(self, full: str, bare: str) -> str:
        # Strategy: use trade_stock_info.industry for most precise matching
        # (e.g. "专用设备制造业" matches semiconductor equipment peers, not chip designers)
        # Fallback to sw_level2, then sw_level1
        info_row = self._q(
            "SELECT i.industry, b.sw_level1, b.sw_level2 "
            "FROM trade_stock_basic b "
            "LEFT JOIN trade_stock_info i ON b.stock_code = i.stock_code "
            "WHERE b.stock_code=%s LIMIT 1",
            (full,),
        )
        if not info_row:
            return "[无法确定行业，跳过可比公司分析]"

        r = info_row[0]
        industry_label = r.get("sw_level2") or r.get("sw_level1") or "(未知)"

        # Strategy 1: Double-filter with trade_stock_info.industry + sw_level2 (most precise)
        tsi_industry = r.get("industry")
        sw2 = r.get("sw_level2")
        peers = []
        if tsi_industry and sw2:
            peers = self._q(
                "SELECT b.stock_code, b.stock_name "
                "FROM trade_stock_basic b "
                "JOIN trade_stock_info i ON b.stock_code = i.stock_code "
                "JOIN trade_stock_daily_basic d ON b.stock_code COLLATE utf8mb4_unicode_ci = d.stock_code "
                "WHERE i.industry = %s AND b.sw_level2 = %s AND b.stock_code != %s "
                "AND d.trade_date = (SELECT MAX(trade_date) FROM trade_stock_daily_basic) "
                "ORDER BY d.total_mv DESC LIMIT 5",
                (tsi_industry, sw2, full),
            )

        # Strategy 2: Only trade_stock_info.industry (if sw_level2 filter too restrictive)
        if len(peers) < 3 and tsi_industry:
            peers = self._q(
                "SELECT b.stock_code, b.stock_name "
                "FROM trade_stock_basic b "
                "JOIN trade_stock_info i ON b.stock_code = i.stock_code "
                "JOIN trade_stock_daily_basic d ON b.stock_code COLLATE utf8mb4_unicode_ci = d.stock_code "
                "WHERE i.industry = %s AND b.stock_code != %s "
                "AND d.trade_date = (SELECT MAX(trade_date) FROM trade_stock_daily_basic) "
                "ORDER BY d.total_mv DESC LIMIT 5",
                (tsi_industry, full),
            )

        # Fallback to sw_level2 if too few peers from trade_stock_info
        if len(peers) < 3:
            sw2 = r.get("sw_level2")
            if sw2:
                peers = self._q(
                    "SELECT b.stock_code, b.stock_name "
                    "FROM trade_stock_basic b "
                    "JOIN trade_stock_daily_basic d ON b.stock_code COLLATE utf8mb4_unicode_ci = d.stock_code "
                    "WHERE b.sw_level2 = %s AND b.stock_code != %s "
                    "AND d.trade_date = (SELECT MAX(trade_date) FROM trade_stock_daily_basic) "
                    "ORDER BY d.total_mv DESC LIMIT 5",
                    (sw2, full),
                )
                if len(peers) >= 3:
                    industry_label = sw2

        # Final fallback to sw_level1
        if len(peers) < 3:
            sw1 = r.get("sw_level1")
            if sw1:
                peers = self._q(
                    "SELECT b.stock_code, b.stock_name "
                    "FROM trade_stock_basic b "
                    "JOIN trade_stock_daily_basic d ON b.stock_code COLLATE utf8mb4_unicode_ci = d.stock_code "
                    "WHERE b.sw_level1 = %s AND b.stock_code != %s "
                    "AND d.trade_date = (SELECT MAX(trade_date) FROM trade_stock_daily_basic) "
                    "ORDER BY d.total_mv DESC LIMIT 5",
                    (sw1, full),
                )
                if len(peers) >= 3:
                    industry_label = sw1

        if not peers:
            return f"[同行业({industry_label})无可比公司数据]"

        # Get latest date for consistent comparison
        date_row = self._q(
            "SELECT MAX(trade_date) as max_date FROM trade_stock_daily_basic "
            "WHERE stock_code = %s", (full,)
        )
        target_date = str(date_row[0]["max_date"]) if date_row else None

        lines = [f"### 可比公司分析（同行业: {industry_label}）\n"]
        lines.append(f"**估值对比日**: {target_date}\n")

        # Build comparison table: valuation
        lines.append("| 公司 | 市值(亿) | PE(TTM) | PB | PS(TTM) |")
        lines.append("|------|---------|---------|------|---------|")

        # Target stock first
        target_val = self._q(
            "SELECT total_mv, pe_ttm, pb, ps_ttm FROM trade_stock_daily_basic "
            "WHERE stock_code=%s ORDER BY trade_date DESC LIMIT 1",
            (full,),
        )
        if target_val:
            tv = target_val[0]
            lines.append(
                f"| **{bare}** | **{_num(tv['total_mv'])}** | **{_num(tv['pe_ttm'])}** | "
                f"**{_num(tv['pb'])}** | **{_num(tv['ps_ttm'])}** |"
            )

        # Peers
        peer_codes = []
        for p in peers:
            pcode = p["stock_code"]
            peer_codes.append(pcode)
            pv = self._q(
                "SELECT total_mv, pe_ttm, pb, ps_ttm FROM trade_stock_daily_basic "
                "WHERE stock_code=%s ORDER BY trade_date DESC LIMIT 1",
                (pcode,),
            )
            if pv:
                v = pv[0]
                pbare = pcode.split(".")[0] if "." in pcode else pcode
                lines.append(
                    f"| {p['stock_name']}({pbare}) | {_num(v['total_mv'])} | "
                    f"{_num(v['pe_ttm'])} | {_num(v['pb'])} | {_num(v['ps_ttm'])} |"
                )
            else:
                lines.append(f"| {p['stock_name']} | (无估值) | - | - | - |")

        # Financial comparison (latest annual)
        lines.append("\n### 财务对比（最新年报）\n")
        lines.append("| 公司 | 营收(亿) | 净利(亿) | 毛利率 | ROE |")
        lines.append("|------|---------|---------|--------|-----|")

        # Target financial
        target_fin = self._q(
            "SELECT revenue, net_profit, gross_margin, roe FROM financial_income "
            "WHERE stock_code=%s AND report_date LIKE '%%12-31' "
            "ORDER BY report_date DESC LIMIT 1",
            (bare,),
        )
        if target_fin:
            tf = target_fin[0]
            lines.append(
                f"| **{bare}** | **{_num(tf['revenue'])}** | **{_num(tf['net_profit'])}** | "
                f"**{_pct(tf['gross_margin'])}** | **{_pct(tf['roe'])}** |"
            )

        for pcode in peer_codes:
            pbare = pcode.split(".")[0] if "." in pcode else pcode
            pf = self._q(
                "SELECT revenue, net_profit, gross_margin, roe FROM financial_income "
                "WHERE stock_code=%s AND report_date LIKE '%%12-31' "
                "ORDER BY report_date DESC LIMIT 1",
                (pbare,),
            )
            if pf:
                f = pf[0]
                # Get name
                pname_row = self._q(
                    "SELECT stock_name FROM trade_stock_basic WHERE stock_code=%s LIMIT 1",
                    (pcode,),
                )
                pname = pname_row[0]["stock_name"] if pname_row else pbare
                lines.append(
                    f"| {pname} | {_num(f['revenue'])} | {_num(f['net_profit'])} | "
                    f"{_pct(f['gross_margin'])} | {_pct(f['roe'])} |"
                )

        # Statistical summary (peers only)
        pe_vals = []
        pb_vals = []
        ps_vals = []
        for pcode in peer_codes:
            pv = self._q(
                "SELECT pe_ttm, pb, ps_ttm FROM trade_stock_daily_basic "
                "WHERE stock_code=%s ORDER BY trade_date DESC LIMIT 1",
                (pcode,),
            )
            if pv:
                pe_v = _sf(pv[0]["pe_ttm"])
                pb_v = _sf(pv[0]["pb"])
                ps_v = _sf(pv[0]["ps_ttm"])
                if pe_v and pe_v > 0:
                    pe_vals.append(pe_v)
                if pb_v and pb_v > 0:
                    pb_vals.append(pb_v)
                if ps_v and ps_v > 0:
                    ps_vals.append(ps_v)

        if pe_vals or pb_vals:
            lines.append("\n### 统计摘要（同行业已盈利公司）\n")
            lines.append("| 指标 | 最大值 | 75%分位 | 中位数 | 25%分位 | 最小值 |")
            lines.append("|------|--------|---------|--------|---------|--------|")
            for name, vals in [("PE(TTM)", pe_vals), ("PB", pb_vals), ("PS", ps_vals)]:
                if vals:
                    s = sorted(vals)
                    n = len(s)
                    lines.append(
                        f"| {name} | {max(s):.1f} | {s[min(int(n*0.75), n-1)]:.1f} | "
                        f"{s[n//2]:.1f} | {s[min(int(n*0.25), n-1)]:.1f} | {min(s):.1f} |"
                    )

        return "\n".join(lines)

    # ==============================================================
    # 11. DCF Inputs (Ch4) - pre-computed parameters
    # ==============================================================

    # Industry -> Beta mapping for A-share DCF
    _BETA_INDUSTRY_MAP = {
        # Cyclical / commodities
        "有色金属": 1.1, "采掘": 1.1, "钢铁": 1.1, "化工": 1.1,
        "建筑材料": 1.1, "交通运输": 1.0,
        # Technology / growth
        "电子": 1.3, "计算机": 1.3, "通信": 1.3, "传媒": 1.3,
        "国防军工": 1.2, "电气设备": 1.2,
        # Defensive / stable
        "食品饮料": 0.9, "医药生物": 1.0, "公用事业": 0.9,
        "银行": 0.8, "非银金融": 1.1, "房地产": 1.2,
        # Consumer
        "家用电器": 0.9, "休闲服务": 1.0, "商业贸易": 1.0,
        "纺织服装": 1.0, "汽车": 1.1,
        # Manufacturing
        "机械设备": 1.1, "综合": 1.1, "农林牧渔": 1.0,
        "轻工制造": 1.0, "建筑装饰": 1.0,
    }

    def _calculate_beta(self, bare: str, full: str = "") -> float:
        """Calculate dynamic Beta based on industry classification."""
        self._beta_reason = "默认"

        # Resolve full code if needed
        if not full:
            full = self._resolve_full_code(bare)

        # Get industry from trade_stock_basic
        info = self._q(
            "SELECT sw_level1, sw_level2 FROM trade_stock_basic WHERE stock_code=%s LIMIT 1",
            (full,),
        )
        if not info:
            self._beta_reason = "行业未知，使用默认值"
            return 1.1

        sw1 = info[0].get("sw_level1", "") or ""
        sw2 = info[0].get("sw_level2", "") or ""

        # Lookup Beta from industry map
        beta = self._BETA_INDUSTRY_MAP.get(sw1)
        if beta is not None:
            self._beta_reason = f"{sw1}行业默认"
            return beta

        # Try sw_level2 as fallback
        beta = self._BETA_INDUSTRY_MAP.get(sw2)
        if beta is not None:
            self._beta_reason = f"{sw2}行业默认"
            return beta

        self._beta_reason = f"{sw1}行业未匹配，使用默认值"
        return 1.1

    def _calculate_base_fcf(self, bare: str, annual: list) -> tuple:
        """Calculate base FCF from actual cashflow data.

        Returns (fcf_value, fcf_source) tuple where fcf_source describes
        the derivation method for LLM context.
        """
        # Get latest annual cashflow
        cf_row = self._q(
            "SELECT operating_cashflow, investing_cashflow "
            "FROM financial_cashflow WHERE stock_code=%s "
            "AND report_date LIKE '%%12-31' ORDER BY report_date DESC LIMIT 1",
            (bare,),
        )

        if cf_row:
            ocf = _sf(cf_row[0]["operating_cashflow"])
            icf = _sf(cf_row[0]["investing_cashflow"])
            if ocf is not None and icf is not None:
                capex = abs(icf) if icf < 0 else 0
                fcf = ocf - capex
                if fcf > 0:
                    return (fcf, f"OCF({ocf:.1f}亿) - 资本支出({capex:.1f}亿) = {fcf:.1f}亿")
                else:
                    # Heavy capex: capex > OCF, likely expansionary investment
                    # Use sustainable FCF = OCF * 0.5 (assume ~half capex is maintenance)
                    sustainable_fcf = ocf * 0.5
                    return (
                        sustainable_fcf,
                        f"OCF({ocf:.1f}亿) < 资本支出({capex:.1f}亿)，属于重资本开支企业，"
                        f"假设约50%为维持性capex，可持续FCF = OCF x 0.5 = {sustainable_fcf:.1f}亿"
                    )

        # Fallback: if cashflow data unavailable, estimate from net profit
        if annual:
            np_val = _sf(annual[0]["net_profit"])
            if np_val and np_val > 0:
                return (np_val * 0.7, f"现金流量表数据缺失，以净利({np_val:.1f}亿) x 0.7估算")

        return (None, "数据不足")

    def _prepare_dcf_inputs(self, bare: str, full: str = "") -> str:
        # Current market cap + close price
        mv_row = self._q(
            "SELECT total_mv FROM trade_stock_daily_basic "
            "WHERE stock_code LIKE %s ORDER BY trade_date DESC LIMIT 1",
            (bare + "%",),
        )
        mv = _sf(mv_row[0]["total_mv"]) if mv_row else None

        # Revenue growth history for scenario building
        annual = self._q(
            "SELECT report_date, revenue, net_profit, gross_margin, roe "
            "FROM financial_income WHERE stock_code=%s "
            "AND report_date LIKE '%%12-31' ORDER BY report_date DESC LIMIT 5",
            (bare,),
        )

        lines = ["### DCF估值参数预计算\n"]

        if mv:
            lines.append(f"**当前市值**: {_num(mv)}亿元")

        # A-share DCF parameters with dynamic Beta
        rf = 1.7  # China 10Y bond yield
        beta = self._calculate_beta(bare, full)
        erp = 6.0  # Equity risk premium
        wacc = rf + beta * erp

        beta_reason = self._beta_reason
        lines.append(f"\n**DCF核心参数**:")
        lines.append(f"- 无风险利率(Rf): {rf}%")
        lines.append(f"- Beta: {beta} ({beta_reason})")
        lines.append(f"- 股权风险溢价(ERP): {erp}%")
        lines.append(f"- WACC: {wacc:.1f}% = {rf}% + {beta} x {erp}%")

        # Revenue growth for scenario building
        base_growth = 20.0  # default assumption
        rev_new = None
        rev_old = None
        if len(annual) >= 2:
            rev_new = _sf(annual[0]["revenue"])
            rev_old = _sf(annual[-1]["revenue"])
            n_years = len(annual) - 1
            if rev_new and rev_old and rev_old > 0 and n_years > 0:
                hist_cagr = ((rev_new / rev_old) ** (1 / n_years) - 1) * 100
                lines.append(f"\n**历史营收CAGR**: {hist_cagr:.1f}%")

                # Three scenarios
                bear_growth = max(hist_cagr * 0.5, 5)
                base_growth = hist_cagr * 0.8
                bull_growth = hist_cagr * 1.2

                lines.append(f"\n**三情景营收增速假设(5年)**:")
                lines.append(f"- Bear: {bear_growth:.0f}%")
                lines.append(f"- Base: {base_growth:.0f}%")
                lines.append(f"- Bull: {bull_growth:.0f}%")

        # Sensitivity matrix - output actual valuation range
        lines.append(f"\n### 敏感性分析表（WACC vs 永续增长率）\n")

        # Calculate base FCF from actual cashflow data
        base_fcf, fcf_source = self._calculate_base_fcf(bare, annual)
        lines.append(f"\n**FCF计算**: {fcf_source}")

        if base_fcf and mv:
            # Project FCF 5 years forward using base_growth, then terminal value
            lines.append("| WACC \\ g | 1.0% | 1.5% | 2.0% | 2.5% | 3.0% |")
            lines.append("|----------|------|------|------|------|------|")
            growth_rate = base_growth / 100
            for w_pct in [8.5, 9.0, 9.5, 10.0, 10.5]:
                w = w_pct / 100
                row_vals = []
                for g_pct in [1.0, 1.5, 2.0, 2.5, 3.0]:
                    g = g_pct / 100
                    # 5-year projected FCF
                    projected_fcf = base_fcf * ((1 + growth_rate) ** 5)
                    # Terminal value = FCF_5 * (1+g) / (WACC - g)
                    tv = projected_fcf * (1 + g) / (w - g)
                    # PV of terminal value
                    pv_tv = tv / ((1 + w) ** 5)
                    # PV of 5-year FCFs (simplified: annuity with growth)
                    pv_fcf = sum(
                        base_fcf * ((1 + growth_rate) ** i) / ((1 + w) ** i)
                        for i in range(1, 6)
                    )
                    total_val = pv_fcf + pv_tv
                    row_vals.append(f"{total_val:.0f}")
                lines.append(f"| {w_pct:.1f}% | {' | '.join(row_vals)} |")

            lines.append(f"\n注: 表中数值为合理市值(亿元)估算，基于FCF={_yuan(base_fcf)}和{growth_rate*100:.0f}%五年增速假设")
            if mv:
                lines.append(f"当前市值: {_num(mv)}亿元")
        else:
            # Fallback: show terminal value multipliers
            lines.append("| WACC \\ g | 1.0% | 1.5% | 2.0% | 2.5% | 3.0% |")
            lines.append("|----------|------|------|------|------|------|")
            for w_pct in [8.5, 9.0, 9.5, 10.0, 10.5]:
                row_vals = []
                for g_pct in [1.0, 1.5, 2.0, 2.5, 3.0]:
                    factor = 1 / (w_pct - g_pct)
                    row_vals.append(f"{factor:.1f}x")
                lines.append(f"| {w_pct:.1f}% | {' | '.join(row_vals)} |")
            lines.append(f"\n注: 表中数值为永续价值乘数(=1/(WACC-g))，需乘以终端FCF得到实际估值")
            lines.append(f"当前市值{f' ({_num(mv)}亿)' if mv else ''}在估值区间的位置需结合FCF预测判断")

        # Profitability context
        if annual:
            latest = annual[0]
            lines.append(f"\n**最新年报参考**:")
            lines.append(f"- 营收: {_yuan(latest['revenue'])}")
            lines.append(f"- 净利: {_yuan(latest['net_profit'])}")
            lines.append(f"- 毛利率: {_pct(latest['gross_margin'])}")
            lines.append(f"- ROE: {_pct(latest['roe'])}")

        return "\n".join(lines)

    # ==============================================================
    # Data completeness check
    # ==============================================================

    def _check_completeness(self, data: Dict[str, str]) -> str:
        """Check data completeness and report issues."""
        issues = []

        def _is_empty(text: str) -> bool:
            return text.startswith("[无") or text.startswith("[暂无") or text.startswith("[数据")

        # Financial data: need at least 4 annual reports
        fin = data.get("financial_summary", "")
        if _is_empty(fin):
            issues.append("[CRITICAL] 无财务数据")
        elif fin.count("-12-31") < 4:
            issues.append("[WARN] 年度财务数据不足4年，趋势分析受限")

        # Cashflow
        cf = data.get("cashflow", "")
        if _is_empty(cf):
            issues.append("[WARN] 无现金流数据，盈利质量分析受限")

        # Balance sheet
        bs = data.get("balance_sheet", "")
        if _is_empty(bs):
            issues.append("[WARN] 无资产负债数据，杠杆评估受限")

        # Valuation
        val = data.get("valuation_snapshot", "")
        if _is_empty(val):
            issues.append("[WARN] 无估值数据")

        # Quotes
        qt = data.get("daily_quotes", "")
        if _is_empty(qt):
            issues.append("[WARN] 无行情数据")

        # Technical
        tf = data.get("technical_factors", "")
        if _is_empty(tf):
            issues.append("[INFO] 无技术指标数据")

        if not issues:
            return "数据完备性检查: [OK] 所有核心数据齐全"

        return "数据完备性检查:\n" + "\n".join(f"- {i}" for i in issues)
