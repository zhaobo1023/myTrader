# -*- coding: utf-8 -*-

import logging
from typing import List, Tuple

from data_analyst.risk_assessment.assessors.base import BaseAssessor
from data_analyst.risk_assessment.schemas import RegimeRiskResult, score_to_level
from data_analyst.risk_assessment.config import SVD_STATE_SCORES, CORR_RISK_SCORES

logger = logging.getLogger(__name__)


def _corr_score(avg_corr: float) -> float:
    """根据 CORR_RISK_SCORES 将平均相关性映射到风险分。"""
    for (low, high), score in CORR_RISK_SCORES.items():
        if low <= avg_corr < high:
            return float(score)
    return 25.0


class RegimeRiskAssessor(BaseAssessor):
    """L2 市场状态与持仓相关性风险评估器。"""

    def assess(self, position_codes: List[str]) -> RegimeRiskResult:
        sub_scores = {}
        details = {}
        market_state = ''

        # --- SVD 市场状态 (40%) ---
        svd_score = 50.0
        is_mutation = False
        try:
            rows = self._query(
                """
                SELECT market_state, is_mutation
                FROM trade_svd_market_state
                WHERE window_size = 20 AND universe_type = '全A'
                ORDER BY calc_date DESC
                LIMIT 1
                """
            )
            if rows:
                market_state = rows[0]['market_state'] or ''
                svd_score = float(SVD_STATE_SCORES.get(market_state, 50))
                is_mutation = bool(rows[0]['is_mutation'])
                details['svd_market_state'] = market_state
                details['svd_score'] = svd_score
        except Exception as e:
            logger.warning("trade_svd_market_state 查询失败: %s", e)

        sub_scores['svd_state'] = svd_score

        # --- 突变检测 (15%) ---
        mutation_score = 80.0 if is_mutation else 20.0
        sub_scores['mutation'] = mutation_score
        details['is_mutation'] = is_mutation

        # --- 持仓相关性 (45%) ---
        avg_corr = 0.0
        corr_score = 25.0
        high_corr_pairs: List[Tuple[str, str, float]] = []

        if len(position_codes) < 2:
            corr_score = 25.0
            details['correlation_note'] = "持仓股票不足2只，相关性默认低风险"
        else:
            try:
                placeholders = ', '.join(['%s'] * len(position_codes))
                rows = self._query(
                    """
                    SELECT stock_code, trade_date, close_price AS close
                    FROM trade_stock_daily
                    WHERE stock_code IN ({})
                      AND trade_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
                    ORDER BY stock_code, trade_date
                    """.format(placeholders),
                    tuple(position_codes),
                )
                if rows:
                    import pandas as pd
                    df = pd.DataFrame(rows)
                    df['close'] = df['close'].astype(float)
                    pivot = df.pivot(index='trade_date', columns='stock_code', values='close')
                    returns = pivot.pct_change().dropna(how='all')
                    # 只保留有足够数据的列（至少30个交易日）
                    valid_cols = [c for c in returns.columns if returns[c].count() >= 30]
                    if len(valid_cols) >= 2:
                        corr_matrix = returns[valid_cols].corr()
                        corr_vals = []
                        codes = list(corr_matrix.columns)
                        for i in range(len(codes)):
                            for j in range(i + 1, len(codes)):
                                val = float(corr_matrix.iloc[i, j])
                                corr_vals.append(val)
                                if val > 0.6:
                                    high_corr_pairs.append((codes[i], codes[j], round(val, 3)))
                        avg_corr = round(sum(corr_vals) / len(corr_vals), 4) if corr_vals else 0.0
                        corr_score = _corr_score(avg_corr)
                    else:
                        details['correlation_note'] = "有效数据不足，相关性默认低风险"
            except Exception as e:
                logger.warning("持仓相关性计算失败: %s", e)

        sub_scores['correlation'] = corr_score
        details['avg_correlation'] = avg_corr
        details['high_corr_pairs_count'] = len(high_corr_pairs)

        # --- 加权合并 ---
        final_score = round(
            svd_score * 0.40 + mutation_score * 0.15 + corr_score * 0.45,
            2,
        )
        level = score_to_level(final_score)

        suggestions = []
        if high_corr_pairs:
            # 统计高相关涉及的股票（去重），不在建议里放原始 code 对
            involved = set()
            for a, b, _ in high_corr_pairs:
                involved.add(a)
                involved.add(b)
            suggestions.append(
                "{}只持仓之间存在{}对高度相关（相关系数>0.6），注意分散风险".format(
                    len(involved), len(high_corr_pairs)
                )
            )
        if is_mutation:
            suggestions.append("市场结构发生突变，建议谨慎操作")

        details['sub_scores'] = sub_scores

        return RegimeRiskResult(
            score=final_score,
            level=level,
            details=details,
            suggestions=suggestions,
            market_state=market_state,
            avg_correlation=avg_corr,
            high_corr_pairs=high_corr_pairs,
        )
