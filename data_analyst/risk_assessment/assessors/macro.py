# -*- coding: utf-8 -*-

import logging
from data_analyst.risk_assessment.assessors.base import BaseAssessor
from data_analyst.risk_assessment.schemas import MacroRiskResult, score_to_level
from data_analyst.risk_assessment.config import MACRO_WEIGHTS, MACRO_POSITION_LIMITS

logger = logging.getLogger(__name__)


def _suggested_exposure(score: float) -> float:
    """根据 MACRO_POSITION_LIMITS 映射宏观风险分到建议最大仓位。"""
    for (low, high), limit in MACRO_POSITION_LIMITS.items():
        if low <= score < high:
            return limit
    return 0.3


class MacroRiskAssessor(BaseAssessor):
    """L1 宏观环境风险评估器。"""

    def assess(self) -> MacroRiskResult:
        scores = {}
        raw_values = {}

        # --- fear_index ---
        try:
            rows = self._query(
                "SELECT fear_greed_score FROM trade_fear_index ORDER BY trade_date DESC LIMIT 1"
            )
            if rows:
                fgs = float(rows[0]['fear_greed_score'])
                raw_values['fear_index'] = fgs
                # fear_greed_score: 0=extreme_fear(高风险), 100=extreme_greed(低风险)
                # 反转：恐慌=高风险，贪婪=低风险
                scores['fear_index'] = round(100 - fgs, 2)
        except Exception as e:
            logger.warning("fear_index 查询失败: %s", e)

        # --- vix / northflow / yield_spread / commodity: 一次查询批量获取 ---
        # northflow 需要最近5条，其余取最近1条；用子查询各自 LIMIT
        try:
            macro_rows = self._query(
                """
                SELECT indicator, value FROM macro_data
                WHERE (indicator IN ('qvix', 'vix', 'us_10y_2y_spread', 'dxy')
                       AND (indicator, date) IN (
                           SELECT indicator, MAX(date) FROM macro_data
                           WHERE indicator IN ('qvix', 'vix', 'us_10y_2y_spread', 'dxy')
                           GROUP BY indicator
                       ))
                   OR (indicator = 'north_flow' AND date >= (
                           SELECT DATE_SUB(MAX(date), INTERVAL 10 DAY) FROM macro_data
                           WHERE indicator = 'north_flow'
                       ))
                """
            )
            by_indicator: dict = {}
            for r in macro_rows:
                ind = r['indicator']
                val = float(r['value'])
                by_indicator.setdefault(ind, []).append(val)

            # vix: prefer qvix over vix
            vix_vals = by_indicator.get('qvix') or by_indicator.get('vix')
            if vix_vals:
                vix_val = vix_vals[0]
                raw_values['vix'] = vix_val
                if vix_val < 13:
                    scores['vix'] = 10
                elif vix_val < 17:
                    scores['vix'] = 30
                elif vix_val < 22:
                    scores['vix'] = 50
                elif vix_val < 30:
                    scores['vix'] = 75
                else:
                    scores['vix'] = 90

            # northflow: average of recent values
            nf_vals = by_indicator.get('north_flow', [])
            if nf_vals:
                avg_flow = sum(nf_vals[:5]) / min(len(nf_vals), 5)
                raw_values['northflow'] = round(avg_flow, 2)
                if avg_flow > 0:
                    scores['northflow'] = 20
                elif avg_flow == 0:
                    scores['northflow'] = 50
                elif avg_flow >= -50:
                    scores['northflow'] = 70
                else:
                    scores['northflow'] = 85

            # yield_spread
            spread_vals = by_indicator.get('us_10y_2y_spread')
            if spread_vals:
                spread = spread_vals[0]
                raw_values['yield_spread'] = spread
                if spread > 1:
                    scores['yield_spread'] = 20
                elif spread >= 0.5:
                    scores['yield_spread'] = 40
                elif spread >= 0:
                    scores['yield_spread'] = 55
                else:
                    scores['yield_spread'] = 75

            # commodity (DXY)
            dxy_vals = by_indicator.get('dxy')
            if dxy_vals:
                dxy = dxy_vals[0]
                raw_values['commodity'] = dxy
                if dxy > 105:
                    scores['commodity'] = 70
                elif dxy >= 100:
                    scores['commodity'] = 50
                else:
                    scores['commodity'] = 25

        except Exception as e:
            logger.warning("macro_data 批量查询失败: %s", e)

        # --- fx (north_flow_5d from macro_factors) ---
        try:
            rows = self._query(
                "SELECT value FROM macro_factors WHERE factor_name='north_flow_5d' ORDER BY trade_date DESC LIMIT 1"
            )
            if rows:
                nf5d = float(rows[0]['value'])
                raw_values['fx'] = nf5d
                scores['fx'] = 20 if nf5d > 0 else 60
        except Exception as e:
            logger.warning("fx/north_flow_5d 查询失败: %s", e)

        # --- 加权合并（缺失维度重新归一化权重）---
        available_keys = [k for k in MACRO_WEIGHTS if k in scores]
        if not available_keys:
            logger.error("所有宏观指标均缺失，返回默认中等风险分 50")
            final_score = 50.0
        else:
            total_weight = sum(MACRO_WEIGHTS[k] for k in available_keys)
            final_score = sum(scores[k] * MACRO_WEIGHTS[k] / total_weight for k in available_keys)
            final_score = round(final_score, 2)

        level = score_to_level(final_score)
        exposure = _suggested_exposure(final_score)

        details = {
            'dimension_scores': scores,
            'raw_values': raw_values,
            'available_dimensions': available_keys,
        }

        suggestions = []
        if final_score > 70:
            suggestions.append(
                "宏观风险偏高，建议降低仓位至 {:.0f}%".format(exposure * 100)
            )

        return MacroRiskResult(
            score=final_score,
            level=level,
            details=details,
            suggestions=suggestions,
            suggested_max_exposure=exposure,
        )
