"""
Sentiment Storage Service

舆情数据存储服务
- 保存恐慌指数
- 保存新闻情感
- 保存事件信号
- 保存 Polymarket 快照
"""

import logging
from typing import List, Optional
from datetime import datetime, timedelta

from config.db import execute_query, execute_update, execute_many

from data_analyst.sentiment.schemas import (
    FearIndexResult,
    SentimentResult,
    EventSignal,
    PolymarketEvent,
)

logger = logging.getLogger(__name__)


class SentimentStorage:
    """舆情数据存储服务"""

    def __init__(self, env: str = 'local'):
        self.env = env

    def save_fear_index(self, result: FearIndexResult) -> bool:
        """
        保存恐慌指数
        
        Args:
            result: 恐慌指数结果
            
        Returns:
            是否成功
        """
        try:
            sql = """
            INSERT INTO trade_fear_index (
                trade_date, vix, ovx, gvz, us10y,
                fear_greed_score, market_regime, vix_level,
                us10y_strategy, risk_alert, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                vix = VALUES(vix),
                ovx = VALUES(ovx),
                gvz = VALUES(gvz),
                us10y = VALUES(us10y),
                fear_greed_score = VALUES(fear_greed_score),
                market_regime = VALUES(market_regime),
                vix_level = VALUES(vix_level),
                us10y_strategy = VALUES(us10y_strategy),
                risk_alert = VALUES(risk_alert),
                updated_at = NOW()
            """
            
            params = (
                result.timestamp.strftime('%Y-%m-%d'),
                result.vix,
                result.ovx,
                result.gvz,
                result.us10y,
                result.fear_greed_score,
                result.market_regime,
                result.vix_level,
                result.us10y_strategy,
                result.risk_alert,
                result.timestamp,
            )
            
            execute_update(sql, params, env=self.env)
            logger.info(f"Saved fear index for {result.timestamp.strftime('%Y-%m-%d')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save fear index: {e}")
            return False

    def get_fear_index_history(self, days: int = 7) -> List[dict]:
        """
        获取恐慌指数历史
        
        Args:
            days: 获取最近几天的数据
            
        Returns:
            历史数据列表
        """
        try:
            sql = """
            SELECT * FROM trade_fear_index
            WHERE trade_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            ORDER BY trade_date DESC
            """
            
            result = execute_query(sql, (days,), env=self.env)
            logger.info(f"Fetched {len(result)} fear index records")
            return result
            
        except Exception as e:
            logger.error(f"Failed to get fear index history: {e}")
            return []

    def save_news_sentiment(self, items: List[SentimentResult]) -> bool:
        """
        保存新闻情感
        
        Args:
            items: 情感分析结果列表
            
        Returns:
            是否成功
        """
        try:
            if not items:
                return True
            
            sql = """
            INSERT INTO trade_news_sentiment (
                stock_code, stock_name, news_title, news_content,
                news_source, news_url, publish_time,
                sentiment, sentiment_strength, entities, keywords,
                summary, market_impact, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """
            
            params_list = []
            for item in items:
                news = item.news_item
                params = (
                    news.stock_code,
                    news.stock_name,
                    news.title,
                    news.content,
                    news.source,
                    news.url,
                    news.publish_time,
                    item.sentiment,
                    item.sentiment_strength,
                    ','.join(item.entities),
                    ','.join(item.keywords),
                    item.summary,
                    item.market_impact,
                    datetime.now(),
                )
                params_list.append(params)
            
            execute_many(sql, params_list, env=self.env)
            logger.info(f"Saved {len(items)} news sentiment records")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save news sentiment: {e}")
            return False

    def save_event_signals(self, signals: List[EventSignal]) -> bool:
        """
        保存事件信号
        
        Args:
            signals: 事件信号列表
            
        Returns:
            是否成功
        """
        try:
            if not signals:
                return True
            
            sql = """
            INSERT INTO trade_event_signal (
                trade_date, stock_code, stock_name,
                event_type, event_category, signal, signal_reason,
                news_title, matched_keywords, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """
            
            params_list = []
            for sig in signals:
                params = (
                    sig.trade_date,
                    sig.stock_code,
                    sig.stock_name,
                    sig.event_type,
                    sig.event_category,
                    sig.signal,
                    sig.signal_reason,
                    sig.news_title,
                    ','.join(sig.matched_keywords),
                    datetime.now(),
                )
                params_list.append(params)
            
            execute_many(sql, params_list, env=self.env)
            logger.info(f"Saved {len(signals)} event signals")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save event signals: {e}")
            return False

    def save_polymarket_snapshot(self, events: List[PolymarketEvent]) -> bool:
        """
        保存 Polymarket 快照
        
        Args:
            events: Polymarket 事件列表
            
        Returns:
            是否成功
        """
        try:
            if not events:
                return True
            
            sql = """
            INSERT INTO trade_polymarket_snapshot (
                event_id, event_title, market_question,
                yes_probability, volume, is_smart_money_signal,
                category, snapshot_time, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """
            
            params_list = []
            for event in events:
                params = (
                    event.event_id,
                    event.event_title,
                    event.market_question,
                    event.yes_probability,
                    event.volume,
                    event.is_smart_money_signal,
                    event.category,
                    event.snapshot_time,
                    datetime.now(),
                )
                params_list.append(params)
            
            execute_many(sql, params_list, env=self.env)
            logger.info(f"Saved {len(events)} Polymarket snapshots")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save Polymarket snapshot: {e}")
            return False

    def get_recent_events(self, days: int = 3, event_type: Optional[str] = None) -> List[dict]:
        """
        获取最近的事件信号
        
        Args:
            days: 获取最近几天的数据
            event_type: 事件类型过滤 (bullish/bearish/policy)
            
        Returns:
            事件列表
        """
        try:
            sql = """
            SELECT * FROM trade_event_signal
            WHERE trade_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            """
            params = [days]
            
            if event_type:
                sql += " AND event_type = %s"
                params.append(event_type)
            
            sql += " ORDER BY created_at DESC"
            
            result = execute_query(sql, tuple(params), env=self.env)
            logger.info(f"Fetched {len(result)} event signals")
            return result
            
        except Exception as e:
            logger.error(f"Failed to get recent events: {e}")
            return []
