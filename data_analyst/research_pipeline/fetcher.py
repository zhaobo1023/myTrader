"""
五截面分析数据获取层

从在线数据库中读取所有评分所需的原始数据：
- trade_stock_financial  → 基本面 + 资本周期
- trade_stock_daily_basic → 估值分位
- trade_stock_moneyflow  → 资金面
- trade_stock_rps        → RPS120
"""
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import execute_query

logger = logging.getLogger(__name__)


@dataclass
class FinancialSeries:
    """多年财务序列（年报，oldest first）"""
    roe_series: list            # ROE (%)
    revenue_growth_series: list # 收入YoY (ratio, e.g. 0.45)
    gross_margin_series: list   # 毛利率 (%)
    # Latest annual snapshot
    revenue_latest: float = 0.0
    net_profit_latest: float = 0.0
    roe_latest: float = 0.0
    roe_prev: float = 0.0       # previous year ROE
    gross_margin_latest: float = 0.0
    net_margin_latest: float = 0.0
    debt_ratio_latest: float = 0.0
    ocf_latest: float = 0.0     # operating cash flow
    revenue_yoy: float = 0.0    # revenue YoY growth (ratio)
    profit_yoy: float = 0.0     # profit YoY growth (ratio)
    report_date: str = ""
    # v2: 数据时效性
    is_stale: bool = False       # 距今超过 18 个月视为过时
    stale_months: int = 0        # 实际距今月数
    data_warning: str = ""       # 供 HealthChecker 使用的警告文本
    # v2: 上年度快照（用于报告对比列）
    revenue_prev: float = 0.0
    net_profit_prev: float = 0.0
    gross_margin_prev: float = 0.0
    debt_ratio_prev: float = 0.0
    report_date_prev: str = ""
    # v2: 年份列表（供渲染层直接使用，避免 T-3/T-2 标注）
    report_years: list = field(default_factory=list)


@dataclass
class ValuationData:
    """估值历史分位"""
    pe_ttm: float = 0.0
    pb: float = 0.0
    total_mv: float = 0.0       # 总市值（亿元）
    pe_quantile: float = 0.5    # 5年PE分位 0-1
    pb_quantile: float = 0.5    # 5年PB分位 0-1
    trade_date: str = ""


@dataclass
class FundFlowData:
    """资金流数据"""
    net_5d_amount: float = 0.0  # 近5日净流入（元）
    net_10d_amount: float = 0.0
    net_20d_amount: float = 0.0
    total_mv_yuan: float = 0.0  # 市值（元）
    rps_120: float = 50.0
    # v2: 缺失标记
    is_missing: bool = False
    data_warning: str = ""


class ResearchDataFetcher:
    """五截面分析数据获取器"""

    def __init__(self, env: str = "online"):
        self.env = env

    def _query(self, sql: str, params=None) -> list:
        try:
            return execute_query(sql, params or [], env=self.env)
        except Exception as e:
            logger.warning(f"Query failed: {e} | sql={sql[:100]}")
            return []

    # ------------------------------------------------------------------
    # Financial series (for fundamental + capital cycle)
    # ------------------------------------------------------------------

    def fetch_financial(self, stock_code: str) -> FinancialSeries:
        """
        Fetch annual financial data from trade_stock_financial.
        Returns up to 5 years of annual reports (report_date ending 12-31).
        """
        rows = self._query(
            """
            SELECT report_date, revenue, net_profit, roe, gross_margin,
                   net_margin, debt_ratio, operating_cashflow
            FROM (
                SELECT report_date, revenue, net_profit, roe, gross_margin,
                       net_margin, debt_ratio, operating_cashflow
                FROM trade_stock_financial
                WHERE stock_code = %s
                  AND report_date LIKE %s
                ORDER BY report_date DESC
                LIMIT 6
            ) t
            ORDER BY report_date ASC
            """,
            [stock_code, "%-12-31"],
        )

        if not rows:
            logger.warning(f"[{stock_code}] No annual financial data found")
            return FinancialSeries(
                roe_series=[], revenue_growth_series=[], gross_margin_series=[]
            )

        # Build time series
        revenues = []
        roe_series = []
        margin_series = []
        for r in rows:
            roe_series.append(float(r["roe"] or 0))
            margin_series.append(float(r["gross_margin"] or 0))
            revenues.append(float(r["revenue"] or 0))

        # Revenue growth series
        rev_growth = []
        for i in range(1, len(revenues)):
            prev = revenues[i - 1]
            if prev and prev > 0:
                rev_growth.append((revenues[i] - prev) / prev)
            else:
                rev_growth.append(0.0)

        latest = rows[-1]
        prev = rows[-2] if len(rows) >= 2 else rows[-1]

        rev_latest = float(latest["revenue"] or 0)
        rev_prev_val = float(prev["revenue"] or 0)
        profit_latest = float(latest["net_profit"] or 0)
        profit_prev = float(
            rows[-2]["net_profit"] if len(rows) >= 2 and rows[-2]["net_profit"] else 0
        )

        revenue_yoy = (
            (rev_latest - rev_prev_val) / rev_prev_val if rev_prev_val > 0 else 0.0
        )
        profit_yoy = (
            (profit_latest - profit_prev) / abs(profit_prev)
            if profit_prev and profit_prev != 0
            else 0.0
        )

        # v2: 计算数据时效性（按 report_date 实际距今月数）
        latest_date_str = str(latest["report_date"])
        from datetime import date as _date
        report_date_obj = latest["report_date"] if hasattr(latest["report_date"], 'year') else _date.fromisoformat(latest_date_str)
        now = datetime.now()
        stale_months = (now.year - report_date_obj.year) * 12 + (now.month - report_date_obj.month)
        is_stale = stale_months > 18
        data_warning = (
            f"[STALE] 财务数据距今 {stale_months} 个月（最新年报: {latest_date_str}），"
            f"基本面/周期评分可信度低"
            if is_stale else ""
        )

        # v2: 提取上年度快照
        prev_row = rows[-2] if len(rows) >= 2 else None
        revenue_prev = float(prev_row["revenue"] or 0) / 1e8 if prev_row else 0.0
        net_profit_prev = float(prev_row["net_profit"] or 0) / 1e8 if prev_row else 0.0
        gross_margin_prev = float(prev_row["gross_margin"] or 0) if prev_row else 0.0
        debt_ratio_prev = float(prev_row["debt_ratio"] or 0) if prev_row else 0.0
        report_date_prev = str(prev_row["report_date"]) if prev_row else ""

        # v2: 实际年份列表（格式 "2021"）
        report_years = [str(r["report_date"])[:4] for r in rows]

        return FinancialSeries(
            roe_series=roe_series,
            revenue_growth_series=rev_growth,
            gross_margin_series=margin_series,
            revenue_latest=rev_latest / 1e8,         # convert to 亿元
            net_profit_latest=profit_latest / 1e8,
            roe_latest=float(latest["roe"] or 0),
            roe_prev=float(prev["roe"] or 0),
            gross_margin_latest=float(latest["gross_margin"] or 0),
            net_margin_latest=float(latest["net_margin"] or 0),
            debt_ratio_latest=float(latest["debt_ratio"] or 0),
            ocf_latest=float(latest["operating_cashflow"] or 0) / 1e8,
            revenue_yoy=revenue_yoy,
            profit_yoy=profit_yoy,
            report_date=latest_date_str,
            is_stale=is_stale,
            stale_months=stale_months,
            data_warning=data_warning,
            revenue_prev=revenue_prev,
            net_profit_prev=net_profit_prev,
            gross_margin_prev=gross_margin_prev,
            debt_ratio_prev=debt_ratio_prev,
            report_date_prev=report_date_prev,
            report_years=report_years,
        )

    # ------------------------------------------------------------------
    # Valuation quantile
    # ------------------------------------------------------------------

    def fetch_valuation(self, stock_code: str, years: int = 5) -> ValuationData:
        """
        Fetch PE/PB history and compute quantile position.
        Uses last `years` years of daily_basic data.
        """
        cutoff = (datetime.now() - timedelta(days=years * 366)).strftime("%Y-%m-%d")

        rows = self._query(
            """
            SELECT trade_date, pe_ttm, pb, total_mv
            FROM trade_stock_daily_basic
            WHERE stock_code = %s
              AND trade_date >= %s
              AND pe_ttm > 0
              AND pb > 0
            ORDER BY trade_date ASC
            """,
            [stock_code, cutoff],
        )

        if not rows:
            logger.warning(f"[{stock_code}] No valuation data found")
            return ValuationData()

        pe_list = [float(r["pe_ttm"]) for r in rows]
        pb_list = [float(r["pb"]) for r in rows]
        latest = rows[-1]

        pe_cur = float(latest["pe_ttm"])
        pb_cur = float(latest["pb"])
        mv_cur = float(latest["total_mv"] or 0)  # in 亿元

        pe_q = sum(1 for x in pe_list if x <= pe_cur) / len(pe_list)
        pb_q = sum(1 for x in pb_list if x <= pb_cur) / len(pb_list)

        return ValuationData(
            pe_ttm=pe_cur,
            pb=pb_cur,
            total_mv=mv_cur,
            pe_quantile=round(pe_q, 4),
            pb_quantile=round(pb_q, 4),
            trade_date=str(latest["trade_date"]),
        )

    # ------------------------------------------------------------------
    # Fund flow
    # ------------------------------------------------------------------

    def fetch_fund_flow(self, stock_code: str, rps_120: float = 50.0) -> FundFlowData:
        """
        Fetch net money flow from trade_stock_moneyflow.
        Sums last 5/10/20 trading days.
        Note: net_mf_amount unit needs probing - try 元 first, fallback to 万元.
        """
        rows = self._query(
            """
            SELECT trade_date, net_mf_amount
            FROM trade_stock_moneyflow
            WHERE stock_code = %s
            ORDER BY trade_date DESC
            LIMIT 20
            """,
            [stock_code],
        )

        if not rows:
            logger.warning(f"[{stock_code}] No moneyflow data found, using neutral score")
            return FundFlowData(
                rps_120=rps_120,
                is_missing=False,
                data_warning="[WARN] 资金流向数据暂缺，资金面使用中性评分",
            )

        amounts = [float(r["net_mf_amount"] or 0) for r in rows]

        # v2: 检测是否全为 0（数据异常）
        import statistics
        abs_vals = [abs(x) for x in amounts if x != 0]
        if not abs_vals:
            logger.warning(f"[{stock_code}] Moneyflow data all zeros")
            return FundFlowData(
                rps_120=rps_120,
                is_missing=True,
                data_warning="[MISSING] 资金流向数据全为 0，可能是数据源异常，资金面评分不可用",
            )

        median_abs = statistics.median(abs_vals) if abs_vals else 0
        # Heuristic: reasonable daily net flow for mid/large cap is 1M-500M yuan
        # If median_abs < 100000, it's probably in 万元
        multiplier = 1e4 if median_abs > 0 and median_abs < 1e5 else 1.0

        amounts_yuan = [x * multiplier for x in amounts]

        net_5d = sum(amounts_yuan[:5])
        net_10d = sum(amounts_yuan[:10])
        net_20d = sum(amounts_yuan[:20])

        # Get total_mv from daily_basic for normalization
        mv_rows = self._query(
            "SELECT total_mv FROM trade_stock_daily_basic WHERE stock_code = %s ORDER BY trade_date DESC LIMIT 1",
            [stock_code],
        )
        total_mv_yi = float(mv_rows[0]["total_mv"]) if mv_rows else 0.0
        total_mv_yuan = total_mv_yi * 1e8  # convert 亿元 to 元

        return FundFlowData(
            net_5d_amount=net_5d,
            net_10d_amount=net_10d,
            net_20d_amount=net_20d,
            total_mv_yuan=total_mv_yuan,
            rps_120=rps_120,
        )

    # ------------------------------------------------------------------
    # RPS
    # ------------------------------------------------------------------

    def fetch_rps(self, stock_code: str) -> float:
        """Fetch latest RPS120 value. Returns 50.0 if unavailable."""
        for table in ["trade_stock_rps", "trade_rps_daily"]:
            rows = self._query(
                f"SELECT rps_120 FROM {table} WHERE stock_code = %s ORDER BY trade_date DESC LIMIT 1",
                [stock_code],
            )
            if rows and rows[0]["rps_120"] is not None:
                return float(rows[0]["rps_120"])
        return 50.0
