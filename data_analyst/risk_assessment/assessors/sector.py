# -*- coding: utf-8 -*-

import logging
from typing import List, Dict

from data_analyst.risk_assessment.assessors.base import BaseAssessor
from data_analyst.risk_assessment.schemas import SectorRiskResult, score_to_level
from data_analyst.risk_assessment.config import (
    SECTOR_CONCENTRATION_THRESHOLDS,
    SECTOR_OVERVALUED_THRESHOLD,
)

logger = logging.getLogger(__name__)

# 大类行业分类（申万一级行业名称关键词）
SECTOR_CATEGORIES = {
    '周期': ['钢铁', '有色金属', '煤炭', '化工'],
    '消费': ['食品饮料', '医药生物', '商贸零售', '纺织服装', '轻工制造'],
    '科技': ['计算机', '电子', '通信', '传媒'],
    '金融': ['银行', '非银金融', '房地产'],
}


def _concentration_score(max_ratio: float) -> float:
    """根据 SECTOR_CONCENTRATION_THRESHOLDS 返回集中度风险分。"""
    for threshold, score in SECTOR_CONCENTRATION_THRESHOLDS:
        if max_ratio >= threshold:
            return float(score)
    return 25.0


def _overvalued_exposure_score(overvalued_ratio: float) -> float:
    """高估行业暴露风险分。"""
    if overvalued_ratio > 0.4:
        return 80.0
    elif overvalued_ratio >= 0.2:
        return 55.0
    return 25.0


def _hedge_score(industry_names: List[str]) -> float:
    """跨行业对冲风险分（覆盖大类越多，风险分越低）。"""
    covered = 0
    for category, keywords in SECTOR_CATEGORIES.items():
        for kw in keywords:
            if any(kw in name for name in industry_names):
                covered += 1
                break
    if covered >= 3:
        return 20.0
    elif covered == 2:
        return 45.0
    return 70.0


class SectorRiskAssessor(BaseAssessor):
    """L3 行业结构与估值风险评估器。"""

    def assess(self, positions: List[Dict]) -> SectorRiskResult:
        """
        参数 positions 格式:
        [{'stock_code': '600519.SH', 'stock_name': '贵州茅台',
          'level': 'L1', 'shares': 100, 'cost_price': 1500.0}, ...]
        """
        if not positions:
            return SectorRiskResult(
                score=0.0,
                level='LOW',
                details={'note': '无持仓'},
                suggestions=[],
                industry_breakdown={},
                overvalued_industries=[],
            )

        # --- 查询各股票行业 ---
        codes = [p['stock_code'] for p in positions]
        placeholders = ', '.join(['%s'] * len(codes))
        industry_map: Dict[str, str] = {}
        try:
            rows = self._query(
                "SELECT stock_code, industry FROM trade_stock_basic WHERE stock_code IN ({})".format(
                    placeholders
                ),
                tuple(codes),
            )
            for r in rows:
                industry_map[r['stock_code']] = r['industry'] or '未知'
        except Exception as e:
            logger.warning("trade_stock_basic 查询失败: %s", e)

        # --- 查询行业估值 ---
        valuation_map: Dict[str, float] = {}
        try:
            rows = self._query(
                """
                SELECT v.industry_name, v.pe_percentile_5y
                FROM sw_industry_valuation v
                INNER JOIN (
                    SELECT industry_name, MAX(trade_date) AS max_date
                    FROM sw_industry_valuation
                    GROUP BY industry_name
                ) latest ON v.industry_name = latest.industry_name
                          AND v.trade_date = latest.max_date
                """
            )
            for r in rows:
                if r['pe_percentile_5y'] is not None:
                    valuation_map[r['industry_name']] = float(r['pe_percentile_5y'])
        except Exception as e:
            logger.warning("sw_industry_valuation 查询失败: %s", e)

        # --- 计算行业市值分布 ---
        industry_value: Dict[str, float] = {}
        total_value = 0.0
        for p in positions:
            code = p['stock_code']
            shares = float(p.get('shares', 0))
            cost = float(p.get('cost_price', 0))
            market_val = shares * cost
            industry = industry_map.get(code, '未知')
            industry_value[industry] = industry_value.get(industry, 0.0) + market_val
            total_value += market_val

        industry_breakdown: Dict[str, float] = {}
        if total_value > 0:
            industry_breakdown = {
                ind: round(val / total_value, 4)
                for ind, val in industry_value.items()
            }

        # --- 行业集中度 (35%) ---
        max_ratio = max(industry_breakdown.values()) if industry_breakdown else 0.0
        concentration_score = _concentration_score(max_ratio)

        # --- 高估暴露 (30%) ---
        overvalued_industries = [
            ind for ind, pct in valuation_map.items()
            if pct > SECTOR_OVERVALUED_THRESHOLD
        ]
        overvalued_exposure = sum(
            industry_breakdown.get(ind, 0.0) for ind in overvalued_industries
        )
        overvalued_score = _overvalued_exposure_score(overvalued_exposure)

        # --- 跨行业对冲 (15%) ---
        held_industries = list(industry_breakdown.keys())
        hedge_score = _hedge_score(held_industries)

        # --- SVD 行业内聚性 (20%) - 暂时跳过，默认50分 ---
        svd_cohesion_score = 50.0

        # --- 加权合并 ---
        final_score = round(
            concentration_score * 0.35
            + overvalued_score * 0.30
            + hedge_score * 0.15
            + svd_cohesion_score * 0.20,
            2,
        )
        level = score_to_level(final_score)

        details = {
            'max_industry_ratio': round(max_ratio, 4),
            'concentration_score': concentration_score,
            'overvalued_exposure_ratio': round(overvalued_exposure, 4),
            'overvalued_score': overvalued_score,
            'hedge_score': hedge_score,
            'svd_cohesion_score': svd_cohesion_score,
        }

        suggestions = []
        if max_ratio > 0.5:
            max_industry = max(industry_breakdown, key=industry_breakdown.get)
            suggestions.append(
                "行业集中度过高: {} 占比 {:.1f}%，建议分散配置".format(
                    max_industry, max_ratio * 100
                )
            )
        if overvalued_industries:
            suggestions.append(
                "以下行业估值偏高(5年分位>70%): {}，注意回调风险".format(
                    "、".join(overvalued_industries)
                )
            )

        return SectorRiskResult(
            score=final_score,
            level=level,
            details=details,
            suggestions=suggestions,
            industry_breakdown=industry_breakdown,
            overvalued_industries=overvalued_industries,
        )
