"""
Sentiment API Router

舆情监控 API 端点
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import JSONResponse

from api.schemas.sentiment import (
    FearIndexResponse,
    FearIndexHistoryResponse,
    NewsListResponse,
    NewsItemResponse,
    SentimentResponse,
    SentimentListResponse,
    EventListResponse,
    EventSignalResponse,
    PolymarketListResponse,
    PolymarketEventResponse,
    OverviewResponse,
    AnalyzeNewsRequest,
)
from data_analyst.sentiment.fear_index import FearIndexService
from data_analyst.sentiment.news_fetcher import NewsFetcher
from data_analyst.sentiment.sentiment_analyzer import SentimentAnalyzer
from data_analyst.sentiment.event_detector import EventDetector
from data_analyst.sentiment.polymarket import PolymarketService
from data_analyst.sentiment.storage import SentimentStorage
from data_analyst.sentiment.schemas import NewsItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sentiment", tags=["sentiment"])


@router.get("/fear-index", response_model=FearIndexResponse)
async def get_fear_index():
    """获取当前恐慌指数"""
    try:
        service = FearIndexService()
        result = service.get_fear_index()
        
        return FearIndexResponse(
            vix=result.vix,
            ovx=result.ovx,
            gvz=result.gvz,
            us10y=result.us10y,
            fear_greed_score=result.fear_greed_score,
            market_regime=result.market_regime,
            vix_level=result.vix_level,
            us10y_strategy=result.us10y_strategy,
            risk_alert=result.risk_alert,
            timestamp=result.timestamp,
        )
    except Exception as e:
        logger.error(f"Failed to get fear index: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fear-index/history", response_model=FearIndexHistoryResponse)
async def get_fear_index_history(
    days: int = Query(7, ge=1, le=90, description="获取最近几天的数据")
):
    """获取恐慌指数历史"""
    try:
        storage = SentimentStorage()
        data = storage.get_fear_index_history(days=days)
        
        items = []
        for row in data:
            items.append(FearIndexResponse(
                vix=row['vix'],
                ovx=row['ovx'],
                gvz=row['gvz'],
                us10y=row['us10y'],
                fear_greed_score=row['fear_greed_score'],
                market_regime=row['market_regime'],
                vix_level=row['vix_level'],
                us10y_strategy=row['us10y_strategy'],
                risk_alert=row.get('risk_alert'),
                timestamp=row['created_at'],
            ))
        
        return FearIndexHistoryResponse(data=items, total=len(items))
    except Exception as e:
        logger.error(f"Failed to get fear index history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/news", response_model=NewsListResponse)
async def get_news(
    stock_code: Optional[str] = Query(None, description="股票代码"),
    keywords: Optional[str] = Query(None, description="关键词，逗号分隔"),
    days: int = Query(3, ge=1, le=30, description="获取最近几天的新闻")
):
    """获取新闻列表"""
    try:
        fetcher = NewsFetcher()
        
        if stock_code:
            news_list = fetcher.fetch_stock_news(stock_code, days=days)
        elif keywords:
            keyword_list = [k.strip() for k in keywords.split(',')]
            news_list = fetcher.fetch_keyword_news(keyword_list, days=days)
        else:
            raise HTTPException(status_code=400, detail="Must specify stock_code or keywords")
        
        items = []
        for news in news_list:
            items.append(NewsItemResponse(
                title=news.title,
                content=news.content,
                source=news.source,
                url=news.url,
                publish_time=news.publish_time,
                stock_code=news.stock_code,
                stock_name=news.stock_name,
            ))
        
        return NewsListResponse(data=items, total=len(items))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get news: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/news/analyze", response_model=SentimentResponse)
async def analyze_news(request: AnalyzeNewsRequest):
    """分析单条新闻情感"""
    try:
        news = NewsItem(
            title=request.title,
            content=request.content,
            stock_code=request.stock_code,
        )
        
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_single(news)
        
        return SentimentResponse(
            news_item=NewsItemResponse(
                title=result.news_item.title,
                content=result.news_item.content,
                stock_code=result.news_item.stock_code,
            ),
            sentiment=result.sentiment,
            sentiment_strength=result.sentiment_strength,
            entities=result.entities,
            keywords=result.keywords,
            summary=result.summary,
            market_impact=result.market_impact,
        )
    except Exception as e:
        logger.error(f"Failed to analyze news: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events", response_model=EventListResponse)
async def get_events(
    days: int = Query(3, ge=1, le=30, description="获取最近几天的事件"),
    event_type: Optional[str] = Query(None, description="事件类型 bullish/bearish/policy"),
    stock_code: Optional[str] = Query(None, description="股票代码"),
):
    """获取事件信号列表"""
    try:
        storage = SentimentStorage()
        data = storage.get_recent_events(days=days, event_type=event_type)
        
        items = []
        for row in data:
            if stock_code and row.get('stock_code') != stock_code:
                continue
            
            items.append(EventSignalResponse(
                trade_date=row['trade_date'].strftime('%Y-%m-%d') if isinstance(row['trade_date'], datetime) else str(row['trade_date']),
                stock_code=row.get('stock_code'),
                stock_name=row.get('stock_name'),
                event_type=row['event_type'],
                event_category=row['event_category'],
                signal=row['signal'],
                signal_reason=row.get('signal_reason', ''),
                news_title=row.get('news_title', ''),
                matched_keywords=row.get('matched_keywords', '').split(',') if row.get('matched_keywords') else [],
            ))
        
        return EventListResponse(data=items, total=len(items))
    except Exception as e:
        logger.error(f"Failed to get events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/polymarket", response_model=PolymarketListResponse)
async def get_polymarket(
    keyword: str = Query(..., description="搜索关键词"),
    min_volume: float = Query(100000, description="最小交易量USD"),
):
    """搜索 Polymarket 预测市场"""
    try:
        service = PolymarketService()
        events = service.search_markets(keyword, min_volume=min_volume)
        
        items = []
        for event in events:
            items.append(PolymarketEventResponse(
                event_id=event.event_id,
                event_title=event.event_title,
                market_question=event.market_question,
                yes_probability=event.yes_probability,
                volume=event.volume,
                is_smart_money_signal=event.is_smart_money_signal,
                category=event.category,
                snapshot_time=event.snapshot_time,
            ))
        
        return PolymarketListResponse(data=items, total=len(items))
    except Exception as e:
        logger.error(f"Failed to get Polymarket data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/overview", response_model=OverviewResponse)
async def get_overview():
    """获取舆情监控概览"""
    try:
        # 获取恐慌指数
        fear_service = FearIndexService()
        fear_result = fear_service.get_fear_index()
        
        # 获取事件统计
        storage = SentimentStorage()
        all_events = storage.get_recent_events(days=3)
        
        bullish_count = sum(1 for e in all_events if e['event_type'] == 'bullish')
        bearish_count = sum(1 for e in all_events if e['event_type'] == 'bearish')
        
        # 获取聪明钱信号数量（这里简化处理，实际应该从数据库查询）
        smart_money_count = 0
        
        return OverviewResponse(
            fear_index=FearIndexResponse(
                vix=fear_result.vix,
                ovx=fear_result.ovx,
                gvz=fear_result.gvz,
                us10y=fear_result.us10y,
                fear_greed_score=fear_result.fear_greed_score,
                market_regime=fear_result.market_regime,
                vix_level=fear_result.vix_level,
                us10y_strategy=fear_result.us10y_strategy,
                risk_alert=fear_result.risk_alert,
                timestamp=fear_result.timestamp,
            ),
            event_count=len(all_events),
            bullish_count=bullish_count,
            bearish_count=bearish_count,
            smart_money_count=smart_money_count,
        )
    except Exception as e:
        logger.error(f"Failed to get overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))
