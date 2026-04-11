"""
Sentiment Analysis Data Models

数据模型定义：
- FearIndexResult: 恐慌指数结果
- NewsItem: 新闻条目
- SentimentResult: 情感分析结果
- EventSignal: 事件信号
- PolymarketEvent: Polymarket 预测市场事件
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class FearIndexResult:
    """恐慌指数结果"""
    vix: float
    ovx: float
    gvz: float
    us10y: float
    fear_greed_score: int  # 0-100
    market_regime: str     # extreme_fear/fear/neutral/greed/extreme_greed
    vix_level: str         # 极度平静/正常/焦虑/恐慌/极度恐慌
    us10y_strategy: str    # 利率策略建议
    risk_alert: Optional[str]  # 风险传导提示
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = asdict(self)
        result['timestamp'] = self.timestamp.isoformat()
        return result


@dataclass
class NewsItem:
    """新闻条目"""
    title: str
    content: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    publish_time: Optional[datetime] = None
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = asdict(self)
        if self.publish_time:
            result['publish_time'] = self.publish_time.isoformat()
        return result


@dataclass
class SentimentResult:
    """情感分析结果"""
    news_item: NewsItem
    sentiment: str  # positive/negative/neutral
    sentiment_strength: int  # 1-5
    entities: List[str]
    keywords: List[str]
    summary: str
    market_impact: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'news_item': self.news_item.to_dict(),
            'sentiment': self.sentiment,
            'sentiment_strength': self.sentiment_strength,
            'entities': self.entities,
            'keywords': self.keywords,
            'summary': self.summary,
            'market_impact': self.market_impact,
        }


@dataclass
class EventSignal:
    """事件信号"""
    trade_date: str  # YYYY-MM-DD
    stock_code: Optional[str]
    stock_name: Optional[str]
    event_type: str  # bullish/bearish/policy
    event_category: str  # 资产重组/回购增持等
    signal: str  # strong_buy/buy/hold/sell/strong_sell
    signal_reason: str
    news_title: str
    matched_keywords: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class PolymarketEvent:
    """Polymarket 预测市场事件"""
    event_id: str
    event_title: str
    market_question: str
    yes_probability: float  # 0-100
    volume: float  # USD
    is_smart_money_signal: bool
    category: Optional[str] = None
    snapshot_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = asdict(self)
        if self.snapshot_time:
            result['snapshot_time'] = self.snapshot_time.isoformat()
        return result
