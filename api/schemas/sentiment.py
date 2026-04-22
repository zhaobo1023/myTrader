"""
Sentiment API Schemas

API 请求和响应模型定义
"""

from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel, Field


class FearIndexResponse(BaseModel):
    """恐慌指数响应"""
    vix: Optional[float] = Field(None, description="VIX恐慌指数")
    ovx: Optional[float] = Field(None, description="OVX原油波动率")
    gvz: Optional[float] = Field(None, description="GVZ黄金波动率")
    us10y: Optional[float] = Field(None, description="美国10年期国债收益率")
    fear_greed_score: int = Field(..., description="恐慌贪婪评分0-100")
    market_regime: str = Field(..., description="市场状态")
    vix_level: str = Field(..., description="VIX级别描述")
    us10y_strategy: str = Field(..., description="利率策略建议")
    risk_alert: Optional[str] = Field(None, description="风险传导提示")
    timestamp: datetime = Field(..., description="时间戳")


class FearIndexHistoryResponse(BaseModel):
    """恐慌指数历史响应"""
    data: List[FearIndexResponse]
    total: int


class NewsItemResponse(BaseModel):
    """新闻条目响应"""
    title: str
    content: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    publish_time: Optional[datetime] = None
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None


class SentimentResponse(BaseModel):
    """情感分析响应"""
    news_item: NewsItemResponse
    sentiment: str = Field(..., description="情感倾向 positive/negative/neutral")
    sentiment_strength: int = Field(..., description="情感强度1-5")
    entities: List[str] = Field(default_factory=list, description="关键实体")
    keywords: List[str] = Field(default_factory=list, description="关键词")
    summary: str = Field(..., description="摘要")
    market_impact: Optional[str] = Field(None, description="市场影响")


class NewsListResponse(BaseModel):
    """新闻列表响应"""
    data: List[NewsItemResponse]
    total: int


class SentimentListResponse(BaseModel):
    """情感分析列表响应"""
    data: List[SentimentResponse]
    total: int


class EventSignalResponse(BaseModel):
    """事件信号响应"""
    trade_date: str
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None
    event_type: str = Field(..., description="事件类型 bullish/bearish/policy")
    event_category: str = Field(..., description="事件类别")
    signal: str = Field(..., description="交易信号")
    signal_reason: str = Field(..., description="信号原因")
    news_title: str
    matched_keywords: List[str] = Field(default_factory=list)


class EventListResponse(BaseModel):
    """事件列表响应"""
    data: List[EventSignalResponse]
    total: int


class PolymarketEventResponse(BaseModel):
    """Polymarket事件响应"""
    event_id: str
    event_title: str
    market_question: str
    yes_probability: float = Field(..., description="Yes概率0-100")
    volume: float = Field(..., description="交易量USD")
    is_smart_money_signal: bool = Field(..., description="是否聪明钱信号")
    category: Optional[str] = None
    snapshot_time: datetime


class PolymarketListResponse(BaseModel):
    """Polymarket列表响应"""
    data: List[PolymarketEventResponse]
    total: int


class OverviewResponse(BaseModel):
    """概览响应"""
    fear_index: FearIndexResponse
    event_count: int = Field(..., description="事件数量")
    bullish_count: int = Field(..., description="利好事件数量")
    bearish_count: int = Field(..., description="利空事件数量")
    smart_money_count: int = Field(..., description="聪明钱信号数量")


class AnalyzeNewsRequest(BaseModel):
    """分析新闻请求"""
    title: str = Field(..., description="新闻标题")
    content: Optional[str] = Field(None, description="新闻内容")
    stock_code: Optional[str] = Field(None, description="股票代码")
