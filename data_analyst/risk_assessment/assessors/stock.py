# -*- coding: utf-8 -*-

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

from data_analyst.risk_assessment.assessors.base import BaseAssessor
from data_analyst.risk_assessment.schemas import StockRiskResult, score_to_level
from data_analyst.risk_assessment.config import STOP_LOSS_PCTS

logger = logging.getLogger(__name__)


def _financial_score(net_profit_yoy: Optional[float], roe: Optional[float]) -> float:
    """财务健康评分 (0-100, 越高风险越大)。"""
    if net_profit_yoy is None and roe is None:
        return 50.0

    scores = []

    if net_profit_yoy is not None:
        if net_profit_yoy > 20:
            scores.append(20.0)
        elif net_profit_yoy >= 0:
            scores.append(45.0)
        elif net_profit_yoy >= -20:
            scores.append(65.0)
        else:
            scores.append(85.0)

    if roe is not None:
        if roe > 15:
            scores.append(20.0)
        elif roe >= 10:
            scores.append(40.0)
        elif roe >= 5:
            scores.append(60.0)
        else:
            scores.append(80.0)

    return round(sum(scores) / len(scores), 2)


def _valuation_score(pe_ttm: Optional[float]) -> float:
    """估值风险评分 (0-100, 越高风险越大)。"""
    if pe_ttm is None:
        return 50.0
    if pe_ttm < 0:
        return 70.0
    if pe_ttm < 15:
        return 20.0
    elif pe_ttm < 25:
        return 40.0
    elif pe_ttm < 40:
        return 60.0
    elif pe_ttm < 60:
        return 75.0
    else:
        return 85.0


def _news_score(neg_ratio: Optional[float]) -> float:
    """新闻情绪风险评分 (0-100)。"""
    if neg_ratio is None:
        return 40.0
    if neg_ratio > 0.5:
        return 80.0
    elif neg_ratio >= 0.3:
        return 60.0
    elif neg_ratio >= 0.1:
        return 40.0
    else:
        return 20.0


def _technical_score(
    close: Optional[float],
    cost_price: float,
    level: str,
    ma60: Optional[float],
    macd_dif: Optional[float],
    macd_dea: Optional[float],
) -> tuple:
    """
    技术止损评分，返回 (score, stop_loss_hit, loss_pct, distance_to_stop)。
    """
    stop_pct = STOP_LOSS_PCTS.get(level, 0.08)
    stop_loss_hit = False
    loss_pct = None
    distance_to_stop = None

    if close is not None and cost_price > 0:
        loss_pct = close / cost_price - 1  # 负值表示亏损
        distance_to_stop = loss_pct - (-stop_pct)  # 正值表示距止损线还有空间

        if loss_pct <= -stop_pct:
            stop_loss_hit = True
            stop_score = 95.0
        elif distance_to_stop < 0.05:
            stop_score = 70.0
        elif distance_to_stop < 0.10:
            stop_score = 45.0
        else:
            stop_score = 20.0
    else:
        stop_score = 50.0

    if ma60 is not None and close is not None:
        ma60_score = 30.0 if close > ma60 else 70.0
    else:
        ma60_score = 50.0

    if macd_dif is not None and macd_dea is not None:
        macd_score = 25.0 if macd_dif > macd_dea else 65.0
    else:
        macd_score = 45.0

    final = round(stop_score * 0.50 + ma60_score * 0.30 + macd_score * 0.20, 2)
    return final, stop_loss_hit, loss_pct, distance_to_stop


def _momentum_score(rps_250: Optional[float]) -> float:
    """动量衰减评分 (0-100)。"""
    if rps_250 is None:
        return 50.0
    if rps_250 > 80:
        return 20.0
    elif rps_250 >= 60:
        return 40.0
    elif rps_250 >= 40:
        return 60.0
    else:
        return 80.0


class StockFundamentalAssessor(BaseAssessor):
    """L4 个股基本面与技术面风险评估器。"""

    def assess_stock(self, position: Dict) -> StockRiskResult:
        """评估单只股票风险。"""
        return self.assess_batch([position])[0]

    def assess_batch(self, positions: List[Dict]) -> List[StockRiskResult]:
        """批量评估，合并查询减少 DB 请求。"""
        if not positions:
            return []

        codes = [p['stock_code'] for p in positions]
        placeholders = ', '.join(['%s'] * len(codes))
        today = date.today()
        seven_days_ago = (today - timedelta(days=7)).strftime('%Y-%m-%d')

        # --- 批量查询财务数据（取每只最新报告）---
        financial_map: Dict[str, Dict] = {}
        try:
            rows = self._query(
                """
                SELECT f.stock_code, f.net_profit_yoy, f.roe
                FROM trade_stock_financial f
                INNER JOIN (
                    SELECT stock_code, MAX(report_date) AS max_date
                    FROM trade_stock_financial
                    WHERE stock_code IN ({})
                    GROUP BY stock_code
                ) latest ON f.stock_code = latest.stock_code
                          AND f.report_date = latest.max_date
                """.format(placeholders),
                tuple(codes),
            )
            for r in rows:
                financial_map[r['stock_code']] = {
                    'net_profit_yoy': float(r['net_profit_yoy']) if r['net_profit_yoy'] is not None else None,
                    'roe': float(r['roe']) if r['roe'] is not None else None,
                }
        except Exception as e:
            logger.warning("trade_stock_financial 批量查询失败: %s", e)

        # --- 批量查询估值数据（取每只最近1条）---
        valuation_map: Dict[str, Dict] = {}
        try:
            rows = self._query(
                """
                SELECT b.stock_code, b.pe_ttm
                FROM trade_stock_daily_basic b
                INNER JOIN (
                    SELECT stock_code, MAX(trade_date) AS max_date
                    FROM trade_stock_daily_basic
                    WHERE stock_code IN ({})
                    GROUP BY stock_code
                ) latest ON b.stock_code = latest.stock_code
                          AND b.trade_date = latest.max_date
                """.format(placeholders),
                tuple(codes),
            )
            for r in rows:
                valuation_map[r['stock_code']] = {
                    'pe_ttm': float(r['pe_ttm']) if r['pe_ttm'] is not None else None,
                }
        except Exception as e:
            logger.warning("trade_stock_daily_basic 批量查询失败: %s", e)

        # --- 批量查询技术指标（取每只最近1条）---
        technical_map: Dict[str, Dict] = {}
        try:
            rows = self._query(
                """
                SELECT t.stock_code, t.close, t.ma20, t.ma60, t.macd_dif, t.macd_dea, t.rsi_14
                FROM trade_technical_indicator t
                INNER JOIN (
                    SELECT stock_code, MAX(trade_date) AS max_date
                    FROM trade_technical_indicator
                    WHERE stock_code IN ({})
                    GROUP BY stock_code
                ) latest ON t.stock_code = latest.stock_code
                          AND t.trade_date = latest.max_date
                """.format(placeholders),
                tuple(codes),
            )
            for r in rows:
                technical_map[r['stock_code']] = {
                    'close': float(r['close']) if r['close'] is not None else None,
                    'ma20': float(r['ma20']) if r['ma20'] is not None else None,
                    'ma60': float(r['ma60']) if r['ma60'] is not None else None,
                    'macd_dif': float(r['macd_dif']) if r['macd_dif'] is not None else None,
                    'macd_dea': float(r['macd_dea']) if r['macd_dea'] is not None else None,
                    'rsi_14': float(r['rsi_14']) if r['rsi_14'] is not None else None,
                }
        except Exception as e:
            logger.warning("trade_technical_indicator 批量查询失败: %s", e)

        # --- 批量查询 RPS（取每只最近1条）---
        rps_map: Dict[str, Dict] = {}
        try:
            rows = self._query(
                """
                SELECT r.stock_code, r.rps_20, r.rps_60, r.rps_120, r.rps_250
                FROM trade_stock_rps r
                INNER JOIN (
                    SELECT stock_code, MAX(trade_date) AS max_date
                    FROM trade_stock_rps
                    WHERE stock_code IN ({})
                    GROUP BY stock_code
                ) latest ON r.stock_code = latest.stock_code
                          AND r.trade_date = latest.max_date
                """.format(placeholders),
                tuple(codes),
            )
            for r in rows:
                rps_map[r['stock_code']] = {
                    'rps_250': float(r['rps_250']) if r['rps_250'] is not None else None,
                    'rps_120': float(r['rps_120']) if r['rps_120'] is not None else None,
                    'rps_60': float(r['rps_60']) if r['rps_60'] is not None else None,
                    'rps_20': float(r['rps_20']) if r['rps_20'] is not None else None,
                }
        except Exception as e:
            logger.warning("trade_stock_rps 批量查询失败: %s", e)

        # --- 批量查询新闻情绪（最近7天）---
        news_map: Dict[str, List] = {c: [] for c in codes}
        try:
            rows = self._query(
                """
                SELECT stock_code, sentiment, sentiment_strength
                FROM trade_news_sentiment
                WHERE stock_code IN ({})
                  AND publish_time >= '{}'
                """.format(placeholders, seven_days_ago),
                tuple(codes),
            )
            for r in rows:
                news_map.setdefault(r['stock_code'], []).append(r['sentiment'])
        except Exception as e:
            logger.warning("trade_news_sentiment 批量查询失败: %s", e)

        # --- 批量查询事件信号（最近7天）---
        event_map: Dict[str, List] = {c: [] for c in codes}
        try:
            rows = self._query(
                """
                SELECT stock_code, signal, event_category
                FROM trade_event_signal
                WHERE stock_code IN ({})
                  AND trade_date >= '{}'
                """.format(placeholders, seven_days_ago),
                tuple(codes),
            )
            for r in rows:
                event_map.setdefault(r['stock_code'], []).append(r['signal'])
        except Exception as e:
            logger.warning("trade_event_signal 批量查询失败: %s", e)

        # --- 批量查询5日前收盘价 ---
        close_5d_map: Dict[str, float] = {}
        try:
            rows = self._query(
                """
                SELECT sub.stock_code, sub.close_price
                FROM (
                    SELECT stock_code, close_price,
                           ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY trade_date DESC) AS rn
                    FROM trade_stock_daily
                    WHERE stock_code IN ({})
                ) sub
                WHERE sub.rn = 6
                """.format(placeholders),
                tuple(codes),
            )
            for r in rows:
                if r['close_price'] is not None:
                    close_5d_map[r['stock_code']] = float(r['close_price'])
        except Exception as e:
            logger.warning("trade_stock_daily 5日前收盘价查询失败: %s", e)

        # --- 逐只股票计算评分 ---
        results = []
        for p in positions:
            code = p['stock_code']
            name = p.get('stock_name', code)
            level = p.get('level', 'L2')
            cost_price = float(p.get('cost_price', 0) or 0)

            # 财务健康 (25%)
            fin = financial_map.get(code, {})
            net_profit_yoy = fin.get('net_profit_yoy')
            roe = fin.get('roe')
            fin_score = _financial_score(net_profit_yoy, roe)

            # 估值水平 (20%)
            val = valuation_map.get(code, {})
            pe_ttm = val.get('pe_ttm')
            val_score = _valuation_score(pe_ttm)

            # 新闻情绪 (15%)
            sentiments = news_map.get(code, [])
            if sentiments:
                neg_count = sum(1 for s in sentiments if s == 'negative')
                neg_ratio = neg_count / len(sentiments)
            else:
                neg_ratio = None
            news_s = _news_score(neg_ratio)

            # 技术止损 (25%)
            tech = technical_map.get(code, {})
            close = tech.get('close')
            ma60 = tech.get('ma60')
            macd_dif = tech.get('macd_dif')
            macd_dea = tech.get('macd_dea')
            tech_score, stop_loss_hit, loss_pct, distance_to_stop = _technical_score(
                close, cost_price, level, ma60, macd_dif, macd_dea
            )

            # 动量衰减 (15%)
            rps = rps_map.get(code, {})
            rps_250 = rps.get('rps_250')
            mom_score = _momentum_score(rps_250)

            # 综合评分
            final_score = round(
                fin_score * 0.25
                + val_score * 0.20
                + news_s * 0.15
                + tech_score * 0.25
                + mom_score * 0.15,
                2,
            )

            sub_scores = {
                'financial': fin_score,
                'valuation': val_score,
                'news': news_s,
                'technical': tech_score,
                'momentum': mom_score,
            }

            # 生成预警列表
            alerts = []
            if net_profit_yoy is not None and net_profit_yoy < 0:
                alerts.append("净利润同比下滑{:.1f}%".format(abs(net_profit_yoy)))
            if pe_ttm is not None and pe_ttm > 0 and pe_ttm > 60:
                alerts.append("PE偏高({:.0f}倍)".format(pe_ttm))
            if neg_ratio is not None and neg_ratio > 0.3:
                alerts.append("近期负面新闻较多(占比{:.0f}%)".format(neg_ratio * 100))
            if close is not None and ma60 is not None and close < ma60:
                alerts.append("跌破MA60")
            if macd_dif is not None and macd_dea is not None and macd_dif < macd_dea:
                alerts.append("MACD死叉")
            if stop_loss_hit:
                alerts.append("触及止损线")
            elif distance_to_stop is not None and 0 <= distance_to_stop < 0.05:
                alerts.append("接近止损线(距止损还有{:.1f}%)".format(distance_to_stop * 100))

            # 止损价计算
            stop_pct = STOP_LOSS_PCTS.get(level, 0.08)
            stop_loss_price = round(cost_price * (1 - stop_pct), 2) if cost_price > 0 else None

            # 成本距离
            cost_dist = round(loss_pct * 100, 2) if loss_pct is not None else None

            # 5日涨跌幅
            close_5d = close_5d_map.get(code)
            change_5d = round((close - close_5d) / close_5d * 100, 2) if close is not None and close_5d is not None and close_5d > 0 else None

            # 5日急涨急跌预警
            if change_5d is not None:
                if change_5d <= -10:
                    alerts.append("5日急跌{:.1f}%".format(change_5d))
                elif change_5d >= 15:
                    alerts.append("5日急涨{:.1f}%".format(change_5d))

            results.append(StockRiskResult(
                stock_code=code,
                stock_name=name,
                score=final_score,
                sub_scores=sub_scores,
                alerts=alerts,
                stop_loss_hit=stop_loss_hit,
                stop_loss_price=stop_loss_price,
                cost_distance_pct=cost_dist,
                change_5d_pct=change_5d,
                latest_close=close,
            ))

        return results
