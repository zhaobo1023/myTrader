"""
Event Detector Service

事件检测服务
- 基于关键词匹配检测事件
- 生成交易信号
- 事件分类
"""

import logging
from typing import List, Dict, Any
from datetime import datetime

from data_analyst.sentiment.config import EVENT_KEYWORDS, SIGNAL_MAP
from data_analyst.sentiment.schemas import NewsItem, EventSignal

logger = logging.getLogger(__name__)


class EventDetector:
    """事件检测服务"""

    def __init__(self):
        self.event_keywords = EVENT_KEYWORDS
        self.signal_map = SIGNAL_MAP

    def match_keywords(self, text: str, event_type: str) -> List[str]:
        """
        匹配关键词
        
        Args:
            text: 文本内容
            event_type: 事件类型 (bullish/bearish/policy)
            
        Returns:
            匹配到的关键词列表
        """
        matched = []
        
        if event_type not in self.event_keywords:
            return matched
        
        for category, keywords in self.event_keywords[event_type].items():
            for keyword in keywords:
                if keyword in text:
                    matched.append(keyword)
        
        return list(set(matched))  # 去重

    def get_event_category(self, keyword: str, event_type: str) -> str:
        """
        根据关键词获取事件类别
        
        Args:
            keyword: 关键词
            event_type: 事件类型
            
        Returns:
            事件类别
        """
        if event_type not in self.event_keywords:
            return 'unknown'
        
        for category, keywords in self.event_keywords[event_type].items():
            if keyword in keywords:
                return category
        
        return 'unknown'

    def generate_signal(self, event_type: str, category: str) -> Dict[str, str]:
        """
        生成交易信号
        
        Args:
            event_type: 事件类型
            category: 事件类别
            
        Returns:
            信号字典 {'signal': 'buy/sell/hold', 'reason': '原因'}
        """
        if event_type in self.signal_map and category in self.signal_map[event_type]:
            return self.signal_map[event_type][category]
        
        return {'signal': 'hold', 'reason': '未知事件类型'}

    def detect_events(self, news_list: List[NewsItem]) -> List[EventSignal]:
        """
        检测事件
        
        Args:
            news_list: 新闻列表
            
        Returns:
            事件信号列表
        """
        events = []
        
        for news in news_list:
            text = f"{news.title} {news.content or ''}"
            
            # 检测各类事件
            for event_type in ['bullish', 'bearish', 'policy']:
                matched_keywords = self.match_keywords(text, event_type)
                
                if not matched_keywords:
                    continue
                
                # 为每个匹配的关键词生成事件信号
                for keyword in matched_keywords:
                    category = self.get_event_category(keyword, event_type)
                    signal_info = self.generate_signal(event_type, category)
                    
                    event = EventSignal(
                        trade_date=datetime.now().strftime('%Y-%m-%d'),
                        stock_code=news.stock_code,
                        stock_name=news.stock_name,
                        event_type=event_type,
                        event_category=category,
                        signal=signal_info['signal'],
                        signal_reason=signal_info['reason'],
                        news_title=news.title,
                        matched_keywords=[keyword],
                    )
                    events.append(event)
                    
                    logger.info(
                        f"Detected event: {event_type}/{category} -> {signal_info['signal']} "
                        f"for {news.stock_code or 'N/A'}"
                    )
        
        logger.info(f"Detected {len(events)} events from {len(news_list)} news items")
        return events

    def filter_by_signal(self, events: List[EventSignal], signals: List[str]) -> List[EventSignal]:
        """
        按信号类型过滤事件
        
        Args:
            events: 事件列表
            signals: 信号类型列表 (如 ['strong_buy', 'buy'])
            
        Returns:
            过滤后的事件列表
        """
        return [e for e in events if e.signal in signals]

    def filter_by_event_type(self, events: List[EventSignal], event_types: List[str]) -> List[EventSignal]:
        """
        按事件类型过滤
        
        Args:
            events: 事件列表
            event_types: 事件类型列表 (如 ['bullish', 'bearish'])
            
        Returns:
            过滤后的事件列表
        """
        return [e for e in events if e.event_type in event_types]
