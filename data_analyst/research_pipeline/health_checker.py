# -*- coding: utf-8 -*-
"""
data_analyst/research_pipeline/health_checker.py

在生成报告前检测所有数据源的完整性和时效性，输出数据健康度报告。

健康度评估维度：
- 技术面数据：有无行情数据，最新日期是否在近 5 个交易日内
- 资金流数据：moneyflow 表是否有数据，是否全为 0
- 财务数据：是否有年报，距今是否超过 18 个月（过时阈值）
- 估值数据：PE/PB 是否有效
- RPS 数据：是否使用默认值 50

当数据缺失或过时时，对应截面评分降权，避免无效数据参与综合得分。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from dataclasses import field
from typing import Optional

logger = logging.getLogger(__name__)

# 财务数据过时阈值（月）
FINANCIAL_STALE_MONTHS = 18


@dataclass
class DataHealthReport:
    """各数据源的健康状态汇总。"""
    stock_code: str = ""
    check_date: str = ""

    # 技术面
    technical_ok: bool = True
    technical_date: str = ""

    # 资金流
    fund_flow_ok: bool = False
    fund_flow_missing: bool = True
    fund_flow_warning: str = ""

    # 财务数据
    financial_ok: bool = False
    financial_stale: bool = False
    financial_stale_months: int = 0
    financial_report_date: str = ""
    financial_warning: str = ""

    # 估值
    valuation_ok: bool = False
    valuation_date: str = ""

    # RPS
    rps_ok: bool = False
    rps_value: float = 50.0

    @property
    def completeness_pct(self) -> int:
        """数据完整度 0-100%，5 项等权。"""
        checks = [
            self.technical_ok,
            self.fund_flow_ok and not self.fund_flow_missing,
            self.financial_ok and not self.financial_stale,
            self.valuation_ok,
            self.rps_ok,
        ]
        return int(sum(checks) / len(checks) * 100)

    @property
    def confidence(self) -> str:
        pct = self.completeness_pct
        if pct >= 80:
            return "HIGH"
        if pct >= 60:
            return "MEDIUM"
        return "LOW"

    @property
    def warnings(self) -> list[str]:
        """收集所有警告信息列表。"""
        warns = []
        if self.fund_flow_missing:
            warns.append(self.fund_flow_warning or "[MISSING] 主力资金流向数据缺失，资金面评分不可用")
        if self.financial_stale:
            warns.append(
                self.financial_warning
                or f"[STALE] 财务数据距今 {self.financial_stale_months} 个月"
                   f"（最新年报: {self.financial_report_date}），基本面/周期评分可信度低"
            )
        if not self.rps_ok:
            warns.append("[DEFAULT] RPS120 使用默认值 50，板块强度无法评估")
        return warns

    def get_weight_adjustments(self) -> dict[str, float]:
        """
        根据数据健康度返回各截面的权重调整系数（乘数）。
        正常 = 1.0，缺失/过时降为 0 ~ 0.5。
        调用方需自行归一化权重。
        """
        adj = {
            "technical": 1.0,
            "fund_flow": 1.0,
            "fundamental": 1.0,
            "sentiment": 1.0,
            "capital_cycle": 1.0,
        }

        if self.fund_flow_missing:
            adj["fund_flow"] = 0.0

        if self.financial_stale:
            adj["fundamental"] = 0.4
            adj["capital_cycle"] = 0.4

        return adj


class HealthChecker:
    """检测数据健康度，返回 DataHealthReport。"""

    def check(
        self,
        stock_code: str,
        tech_data: dict,
        fund_flow_data: "FundFlowData",    # noqa: F821
        financial_data: "FinancialSeries", # noqa: F821
        valuation_data: "ValuationData",   # noqa: F821
        rps_value: float,
        check_date: str = "",
    ) -> DataHealthReport:
        report = DataHealthReport(stock_code=stock_code, check_date=check_date)

        # --- 技术面 ---
        report.technical_ok = bool(tech_data and tech_data.get("price", 0) > 0)
        report.technical_date = tech_data.get("data_date", "") if tech_data else ""

        # --- 资金流 ---
        report.fund_flow_missing = getattr(fund_flow_data, "is_missing", True)
        report.fund_flow_warning = getattr(fund_flow_data, "data_warning", "")
        report.fund_flow_ok = not report.fund_flow_missing

        # --- 财务数据 ---
        has_rows = bool(getattr(financial_data, "roe_series", []))
        report.financial_ok = has_rows
        report.financial_stale = getattr(financial_data, "is_stale", False)
        report.financial_stale_months = getattr(financial_data, "stale_months", 0)
        report.financial_report_date = getattr(financial_data, "report_date", "")
        report.financial_warning = getattr(financial_data, "data_warning", "")

        # --- 估值 ---
        report.valuation_ok = (
            getattr(valuation_data, "pe_ttm", 0) > 0
            and getattr(valuation_data, "pb", 0) > 0
        )
        report.valuation_date = getattr(valuation_data, "trade_date", "")

        # --- RPS ---
        # RPS 默认值 50.0 意味着无有效数据
        report.rps_ok = abs(rps_value - 50.0) > 0.1
        report.rps_value = rps_value

        return report
