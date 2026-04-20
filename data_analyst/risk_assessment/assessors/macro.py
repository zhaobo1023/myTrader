# -*- coding: utf-8 -*-

import logging
from data_analyst.risk_assessment.assessors.base import BaseAssessor
from data_analyst.risk_assessment.schemas import MacroRiskResult, score_to_level
from data_analyst.risk_assessment.config import MACRO_WEIGHTS, MACRO_POSITION_LIMITS, BULL_BEAR_REGIME_SCORES

logger = logging.getLogger(__name__)


def _suggested_exposure(score: float) -> float:
    for (low, high), limit in MACRO_POSITION_LIMITS.items():
        if low <= score < high:
            return limit
    return 0.3


class MacroRiskAssessor(BaseAssessor):
    """L1 宏观环境风险评估器 (9维)。"""

    def assess(self) -> MacroRiskResult:
        scores = {}
        raw_values = {}
        interpretations = {}

        # 批量取 macro_data 最新值
        latest_macro = {}
        try:
            rows = self._query("""
                SELECT m.indicator, m.value
                FROM macro_data m
                INNER JOIN (
                    SELECT indicator, MAX(date) AS max_date
                    FROM macro_data
                    WHERE indicator IN (
                        'qvix', 'vix', 'north_flow', 'us_10y_2y_spread',
                        'dxy', 'usdcny', 'wti_oil', 'gold',
                        'margin_balance', 'margin_net_buy',
                        'advance_count', 'decline_count',
                        'limit_up_count', 'limit_down_count',
                        'pe_csi300', 'cn_10y_bond', 'div_yield_csi300',
                        'market_volume'
                    )
                    GROUP BY indicator
                ) t ON m.indicator = t.indicator AND m.date = t.max_date
            """)
            for r in rows:
                if r['value'] is not None:
                    latest_macro[r['indicator']] = float(r['value'])
        except Exception as e:
            logger.warning("macro_data 批量查询失败: %s", e)

        # 取北向资金近5日
        northflow_5d = []
        try:
            rows = self._query("""
                SELECT value FROM macro_data
                WHERE indicator = 'north_flow'
                ORDER BY date DESC LIMIT 5
            """)
            northflow_5d = [float(r['value']) for r in rows if r['value'] is not None]
        except Exception as e:
            logger.warning("north_flow 查询失败: %s", e)

        # 取融资余额近5日 (计算趋势)
        margin_recent = []
        try:
            rows = self._query("""
                SELECT value FROM macro_data
                WHERE indicator = 'margin_balance'
                ORDER BY date DESC LIMIT 5
            """)
            margin_recent = [float(r['value']) for r in rows if r['value'] is not None]
        except Exception as e:
            logger.warning("margin_balance 查询失败: %s", e)

        # 取成交额近5日 (计算趋势)
        volume_recent = []
        try:
            rows = self._query("""
                SELECT value FROM macro_data
                WHERE indicator = 'market_volume'
                ORDER BY date DESC LIMIT 10
            """)
            volume_recent = [float(r['value']) for r in rows if r['value'] is not None]
        except Exception as e:
            logger.warning("market_volume 查询失败: %s", e)

        # 取恐惧指数
        try:
            rows = self._query(
                "SELECT fear_greed_score, market_regime FROM trade_fear_index ORDER BY trade_date DESC LIMIT 1"
            )
            if rows and rows[0]['fear_greed_score'] is not None:
                fgs = float(rows[0]['fear_greed_score'])
                regime = rows[0]['market_regime'] or ''
                raw_values['fear_index'] = fgs
                raw_values['fear_regime'] = regime
                # 0=extreme_fear(高风险), 100=extreme_greed(低风险) -> 反转
                scores['fear_index'] = round(100 - fgs, 2)
                interpretations['fear_index'] = self._interpret_fear(fgs, regime)
        except Exception as e:
            logger.warning("fear_index 查询失败: %s", e)

        # --- 1. VIX ---
        vix_val = latest_macro.get('qvix') or latest_macro.get('vix')
        if vix_val is not None:
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
            interpretations['vix'] = self._interpret_vix(vix_val)

        # --- 2. 北向资金 ---
        if northflow_5d:
            avg_flow = sum(northflow_5d) / len(northflow_5d)
            avg_flow_yi = avg_flow / 1e8  # 转为亿
            raw_values['northflow'] = round(avg_flow_yi, 2)
            if avg_flow > 0:
                scores['northflow'] = 20
            elif avg_flow > -50e8:
                scores['northflow'] = 50
            elif avg_flow > -100e8:
                scores['northflow'] = 70
            else:
                scores['northflow'] = 85
            interpretations['northflow'] = self._interpret_northflow(avg_flow_yi)

        # --- 3. 美债利差 ---
        spread = latest_macro.get('us_10y_2y_spread')
        if spread is not None:
            raw_values['yield_spread'] = spread
            if spread > 1:
                scores['yield_spread'] = 20
            elif spread >= 0.5:
                scores['yield_spread'] = 40
            elif spread >= 0:
                scores['yield_spread'] = 55
            else:
                scores['yield_spread'] = 75
            interpretations['yield_spread'] = self._interpret_spread(spread)

        # --- 4. 大宗商品 + 汇率 (合并) ---
        dxy = latest_macro.get('dxy')
        usdcny = latest_macro.get('usdcny')
        if dxy is not None or usdcny is not None:
            sub = []
            if dxy is not None:
                raw_values['dxy'] = dxy
                sub.append(70 if dxy > 105 else (50 if dxy >= 100 else 25))
            if usdcny is not None:
                raw_values['usdcny'] = usdcny
                sub.append(70 if usdcny > 7.3 else (50 if usdcny >= 7.1 else 25))
            scores['commodity_fx'] = round(sum(sub) / len(sub), 2)
            interpretations['commodity_fx'] = self._interpret_commodity_fx(dxy, usdcny)

        # --- 5. 融资融券趋势 ---
        mb = latest_macro.get('margin_balance')
        mnb = latest_macro.get('margin_net_buy')
        if mb is not None:
            mb_wan_yi = mb / 1e12  # 转为万亿
            raw_values['margin_balance'] = round(mb_wan_yi, 2)
            raw_values['margin_net_buy'] = round((mnb or 0) / 1e8, 2)

            # 融资余额趋势: 比较最新和5日前
            if len(margin_recent) >= 2:
                trend = (margin_recent[0] - margin_recent[-1]) / margin_recent[-1] * 100
                raw_values['margin_trend_5d'] = round(trend, 2)
                if trend > 1:
                    scores['margin'] = 25  # 加杠杆 -> 乐观 -> 低风险(但注意过热)
                elif trend >= -0.5:
                    scores['margin'] = 45
                elif trend >= -2:
                    scores['margin'] = 65
                else:
                    scores['margin'] = 85  # 大幅去杠杆 -> 高风险
            else:
                scores['margin'] = 50
            interpretations['margin'] = self._interpret_margin(mb_wan_yi, mnb, margin_recent)

        # --- 6. 涨跌家数 (市场广度) ---
        adv = latest_macro.get('advance_count')
        dec = latest_macro.get('decline_count')
        lu = latest_macro.get('limit_up_count')
        ld = latest_macro.get('limit_down_count')
        if adv is not None and dec is not None and (adv + dec) > 0:
            adv_ratio = adv / (adv + dec)
            raw_values['advance_count'] = int(adv)
            raw_values['decline_count'] = int(dec)
            raw_values['limit_up_count'] = int(lu or 0)
            raw_values['limit_down_count'] = int(ld or 0)
            raw_values['advance_ratio'] = round(adv_ratio, 4)

            if adv_ratio > 0.7:
                scores['breadth'] = 15  # 普涨 -> 低风险
            elif adv_ratio > 0.55:
                scores['breadth'] = 35
            elif adv_ratio > 0.45:
                scores['breadth'] = 55
            elif adv_ratio > 0.3:
                scores['breadth'] = 75
            else:
                scores['breadth'] = 90  # 普跌 -> 高风险
            interpretations['breadth'] = self._interpret_breadth(
                int(adv), int(dec), int(lu or 0), int(ld or 0)
            )

        # --- 7. 股债性价比 ---
        pe = latest_macro.get('pe_csi300')
        bond_10y = latest_macro.get('cn_10y_bond')
        if pe is not None and pe > 0 and bond_10y is not None:
            equity_yield = (1 / pe) * 100  # 股票收益率%
            bond_yield = bond_10y  # 已经是百分比
            spread_eb = equity_yield - bond_yield
            raw_values['pe_csi300'] = pe
            raw_values['cn_10y_bond'] = bond_10y
            raw_values['equity_bond_spread'] = round(spread_eb, 2)

            if spread_eb > 3:
                scores['equity_bond'] = 15
            elif spread_eb > 2:
                scores['equity_bond'] = 30
            elif spread_eb > 1:
                scores['equity_bond'] = 50
            elif spread_eb > 0:
                scores['equity_bond'] = 70
            else:
                scores['equity_bond'] = 85
            interpretations['equity_bond'] = self._interpret_equity_bond(
                pe, bond_10y, spread_eb
            )

        # --- 8. 成交额趋势 ---
        if volume_recent and len(volume_recent) >= 2:
            vol_today = volume_recent[0] / 1e8  # 亿
            vol_avg5 = sum(volume_recent[:5]) / min(len(volume_recent), 5) / 1e8
            vol_avg10 = sum(volume_recent) / len(volume_recent) / 1e8
            raw_values['volume_today'] = round(vol_today, 0)
            raw_values['volume_avg5'] = round(vol_avg5, 0)

            vol_ratio = vol_today / vol_avg10 if vol_avg10 > 0 else 1.0
            if vol_ratio > 1.5:
                scores['volume'] = 30  # 放量 -> 活跃(偏乐观，但也可能恐慌放量)
            elif vol_ratio > 1.0:
                scores['volume'] = 40
            elif vol_ratio > 0.7:
                scores['volume'] = 55
            else:
                scores['volume'] = 70  # 缩量 -> 观望/萎靡
            interpretations['volume'] = self._interpret_volume(vol_today, vol_avg5)

        # --- 9. 牛熊三指标状态 ---
        try:
            rows = self._query(
                "SELECT regime, composite_score FROM trade_bull_bear_signal "
                "ORDER BY calc_date DESC LIMIT 1"
            )
            if rows and rows[0]['regime']:
                regime = rows[0]['regime']
                composite = int(rows[0]['composite_score'] or 0)
                raw_values['bull_bear_regime'] = regime
                raw_values['bull_bear_composite'] = composite
                scores['bull_bear_regime'] = float(BULL_BEAR_REGIME_SCORES.get(regime, 50))
                interpretations['bull_bear_regime'] = self._interpret_bull_bear(regime, composite)
        except Exception as e:
            logger.warning("trade_bull_bear_signal 查询失败: %s", e)

        # --- 加权合并 ---
        available_keys = [k for k in MACRO_WEIGHTS if k in scores]
        if not available_keys:
            logger.error("所有宏观指标均缺失，返回默认中等风险分 50")
            final_score = 50.0
        else:
            total_weight = sum(MACRO_WEIGHTS[k] for k in available_keys)
            final_score = sum(
                scores[k] * MACRO_WEIGHTS[k] / total_weight for k in available_keys
            )
            final_score = round(final_score, 2)

        level = score_to_level(final_score)
        exposure = _suggested_exposure(final_score)

        details = {
            'dimension_scores': scores,
            'raw_values': raw_values,
            'interpretations': interpretations,
            'available_dimensions': available_keys,
        }

        suggestions = []
        if final_score > 70:
            suggestions.append(
                "宏观风险偏高，建议降低仓位至 {:.0f}%".format(exposure * 100)
            )
        elif final_score > 50:
            suggestions.append(
                "宏观环境风险中等，建议保持仓位在 {:.0f}% 以内".format(exposure * 100)
            )

        return MacroRiskResult(
            score=final_score,
            level=level,
            details=details,
            suggestions=suggestions,
            suggested_max_exposure=exposure,
        )

    # ---- 解读模板 ----

    @staticmethod
    def _interpret_fear(fgs: float, regime: str) -> str:
        regime_cn = {
            'extreme_fear': '极度恐慌', 'fear': '恐慌',
            'neutral': '中性', 'greed': '贪婪', 'extreme_greed': '极度贪婪',
        }
        return "恐慌贪婪指数 {:.0f} ({})".format(fgs, regime_cn.get(regime, regime))

    @staticmethod
    def _interpret_vix(val: float) -> str:
        if val < 17:
            return "波动率 {:.1f}，市场波动处于低位，情绪平稳".format(val)
        elif val < 25:
            return "波动率 {:.1f}，市场波动正常".format(val)
        else:
            return "波动率 {:.1f}，市场恐慌情绪升温".format(val)

    @staticmethod
    def _interpret_northflow(avg_yi: float) -> str:
        if avg_yi > 0:
            return "北向资金近5日均净流入 {:.1f}亿，外资看好A股".format(avg_yi)
        else:
            return "北向资金近5日均净流出 {:.1f}亿，外资谨慎".format(abs(avg_yi))

    @staticmethod
    def _interpret_spread(spread: float) -> str:
        if spread < 0:
            return "美债利差 {:.2f}%，收益率曲线倒挂，衰退风险上升".format(spread)
        elif spread < 0.5:
            return "美债利差 {:.2f}%，利差收窄，需关注经济前景".format(spread)
        else:
            return "美债利差 {:.2f}%，正常水平".format(spread)

    @staticmethod
    def _interpret_commodity_fx(dxy, usdcny) -> str:
        parts = []
        if dxy is not None:
            parts.append("美元指数 {:.1f}".format(dxy))
        if usdcny is not None:
            parts.append("美元/人民币 {:.4f}".format(usdcny))
        return "，".join(parts)

    @staticmethod
    def _interpret_margin(mb_wan_yi: float, mnb, margin_recent) -> str:
        parts = ["融资余额 {:.2f}万亿".format(mb_wan_yi)]
        if mnb is not None:
            parts.append("净买入 {:.1f}亿".format(mnb / 1e8))
        if len(margin_recent) >= 2:
            trend = (margin_recent[0] - margin_recent[-1]) / margin_recent[-1] * 100
            if trend > 0:
                parts.append("杠杆资金温和增加，情绪偏乐观")
            else:
                parts.append("杠杆资金有所减少，情绪趋于谨慎")
        return "，".join(parts)

    @staticmethod
    def _interpret_breadth(adv, dec, lu, ld) -> str:
        return "上涨{}家/下跌{}家，涨停{}家/跌停{}家".format(adv, dec, lu, ld)

    @staticmethod
    def _interpret_equity_bond(pe, bond_10y, spread) -> str:
        if spread > 2:
            judge = "股票配置价值较高"
        elif spread > 0:
            judge = "股票配置价值适中"
        else:
            judge = "债券相对更有吸引力"
        return "沪深300 PE {:.1f}，10Y国债 {:.2f}%，股债利差 {:.2f}%，{}".format(
            pe, bond_10y, spread, judge
        )

    @staticmethod
    def _interpret_volume(vol_today, vol_avg5) -> str:
        return "今日成交 {:.0f}亿，5日均量 {:.0f}亿".format(vol_today, vol_avg5)

    @staticmethod
    def _interpret_bull_bear(regime: str, composite: int) -> str:
        regime_cn = {'BULL': '牛市', 'BEAR': '熊市', 'NEUTRAL': '震荡'}
        return "牛熊三指标判断: {} (综合分 {:+d})".format(
            regime_cn.get(regime, regime), composite
        )
