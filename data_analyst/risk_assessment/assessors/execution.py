# -*- coding: utf-8 -*-

import logging
from typing import Dict, List

from data_analyst.risk_assessment.assessors.base import BaseAssessor

logger = logging.getLogger(__name__)

DEFAULT_MAX_POSITIONS = 10
SINGLE_POSITION_LIMIT = 0.30  # 单只持仓市值上限比例


class ExecutionRiskAssessor(BaseAssessor):
    """L5 交易执行规则风险评估器。"""

    def assess(
        self,
        positions: List[Dict],
        macro_result=None,
    ) -> Dict:
        """
        检查执行层风险：ST、涨跌停、仓位数量、日内亏损等。

        返回:
        {
            'score': float,
            'level': str,
            'position_count': int,
            'max_positions': int,
            'single_position_limit': float,
            'daily_loss_pct': float,
            'st_stocks': list,
            'price_limit_stocks': list,
            'alerts': list,
            'suggestions': list,
        }
        """
        alerts = []
        suggestions = []
        score_penalties = 0.0

        position_count = len(positions)

        # --- 动态调整最大持仓数 ---
        max_positions = DEFAULT_MAX_POSITIONS
        if macro_result is not None and macro_result.score > 70:
            max_positions = 8
            logger.info("宏观风险偏高(%.1f)，最大持仓数调整为 %d", macro_result.score, max_positions)

        # --- ST 股票检查 ---
        st_stocks = []
        if positions:
            codes = [p['stock_code'] for p in positions]
            placeholders = ', '.join(['%s'] * len(codes))
            try:
                rows = self._query(
                    """
                    SELECT stock_code, stock_name
                    FROM trade_stock_basic
                    WHERE stock_code IN ({})
                      AND stock_name LIKE '%ST%'
                    """.format(placeholders),
                    tuple(codes),
                )
                st_stocks = [r['stock_code'] for r in rows]
            except Exception as e:
                logger.warning("ST 检查查询失败: %s", e)

        if st_stocks:
            score_penalties += 20.0
            alerts.append("持有ST股票: {}".format(', '.join(st_stocks)))
            suggestions.append("建议尽快清仓ST股票: {}".format(', '.join(st_stocks)))

        # --- 获取最新及前一日收盘价（涨跌停检测 + 日内亏损共用）---
        close_map: Dict[str, float] = {}
        prev_close_map: Dict[str, float] = {}
        if positions:
            codes = [p['stock_code'] for p in positions]
            placeholders = ', '.join(['%s'] * len(codes))
            try:
                rows = self._query(
                    """
                    SELECT d.stock_code, d.close_price AS close, prev.close_price AS prev_close
                    FROM trade_stock_daily d
                    INNER JOIN (
                        SELECT stock_code, MAX(trade_date) AS max_date
                        FROM trade_stock_daily
                        WHERE stock_code IN ({})
                        GROUP BY stock_code
                    ) latest ON d.stock_code = latest.stock_code
                              AND d.trade_date = latest.max_date
                    LEFT JOIN trade_stock_daily prev ON prev.stock_code = d.stock_code
                        AND prev.trade_date = (
                            SELECT MAX(trade_date)
                            FROM trade_stock_daily
                            WHERE stock_code = d.stock_code
                              AND trade_date < latest.max_date
                        )
                    """.format(placeholders),
                    tuple(codes),
                )
                for r in rows:
                    if r['close'] is not None:
                        close_map[r['stock_code']] = float(r['close'])
                    if r['prev_close'] is not None:
                        prev_close_map[r['stock_code']] = float(r['prev_close'])
            except Exception as e:
                logger.warning("行情查询失败: %s", e)

        # --- 涨跌停检测 ---
        price_limit_stocks = []
        for code, curr_close in close_map.items():
            prev_close = prev_close_map.get(code)
            if prev_close and prev_close > 0:
                if abs((curr_close - prev_close) / prev_close) >= 0.095:
                    price_limit_stocks.append(code)

        if price_limit_stocks:
            score_penalties += 10.0
            alerts.append("涨跌停股票: {}".format(', '.join(price_limit_stocks)))
            suggestions.append("涨跌停股票流动性受限，注意操作风险: {}".format(', '.join(price_limit_stocks)))

        # --- 仓位数量检查 ---
        if position_count > max_positions:
            score_penalties += 15.0
            alerts.append("持仓数量({})超过上限({})".format(position_count, max_positions))
            suggestions.append("建议减少持仓数量至 {} 只以内".format(max_positions))

        # --- 当日亏损估算 ---
        daily_loss_pct = 0.0
        total_market_value = 0.0
        total_daily_pnl = 0.0

        if positions:
            try:
                position_map = {p['stock_code']: p for p in positions}
                for code, pos in position_map.items():
                    shares = float(pos.get('shares', 0) or 0)
                    curr_close = close_map.get(code)
                    prev_close = prev_close_map.get(code)
                    if curr_close is not None and shares > 0:
                        market_val = curr_close * shares
                        total_market_value += market_val
                        if prev_close is not None and prev_close > 0:
                            total_daily_pnl += (curr_close - prev_close) * shares

                if total_market_value > 0:
                    daily_loss_pct = round(total_daily_pnl / total_market_value, 4)
            except Exception as e:
                logger.warning("日内亏损计算失败: %s", e)

        if daily_loss_pct < -0.02:
            score_penalties += 10.0
            alerts.append("今日持仓整体亏损{:.1f}%".format(abs(daily_loss_pct) * 100))

        # --- 单仓位集中度检查 ---
        if positions and total_market_value > 0:
            try:
                for p in positions:
                    code = p['stock_code']
                    shares = float(p.get('shares', 0) or 0)
                    c = close_map.get(code) or float(p.get('cost_price', 0) or 0)
                    if c > 0:
                        ratio = c * shares / total_market_value
                        if ratio > SINGLE_POSITION_LIMIT:
                            score_penalties += 8.0
                            alerts.append(
                                "{} 单仓占比{:.1f}%，超过上限{:.0f}%".format(
                                    code, ratio * 100, SINGLE_POSITION_LIMIT * 100
                                )
                            )
                            suggestions.append(
                                "建议适当减持 {}，控制单仓占比在 {:.0f}% 以内".format(
                                    code, SINGLE_POSITION_LIMIT * 100
                                )
                            )
                            break  # 只提示一次集中度警告
            except Exception as e:
                logger.warning("单仓集中度检查失败: %s", e)

        # --- 综合评分 ---
        base_score = 20.0
        final_score = min(100.0, round(base_score + score_penalties, 2))

        # 映射到风险等级
        from data_analyst.risk_assessment.schemas import score_to_level
        level = score_to_level(final_score)

        if not alerts:
            suggestions.append("交易规则检查通过，无明显违规风险")

        return {
            'score': final_score,
            'level': level,
            'position_count': position_count,
            'max_positions': max_positions,
            'single_position_limit': SINGLE_POSITION_LIMIT,
            'daily_loss_pct': daily_loss_pct,
            'st_stocks': st_stocks,
            'price_limit_stocks': price_limit_stocks,
            'alerts': alerts,
            'suggestions': suggestions,
        }
