"""
Sentiment API Router

舆情监控 API 端点
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import JSONResponse

from config.db import execute_query
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
    """获取当前恐慌指数（从数据库缓存）"""
    try:
        storage = SentimentStorage()
        # 获取最新一条记录
        data = execute_query(
            """SELECT * FROM trade_fear_index
               ORDER BY trade_date DESC
               LIMIT 1""",
            env='online',
        )

        if not data:
            # 如果数据库无数据，触发一次即时抓取
            from api.tasks.fear_index import fetch_fear_index
            fetch_fear_index.apply_async()
            raise HTTPException(
                status_code=404,
                detail='暂无恐慌指数数据，后台正在抓取中，请稍后再试'
            )

        row = data[0]
        return FearIndexResponse(
            vix=float(row['vix']) if row['vix'] is not None else 0.0,
            ovx=float(row['ovx']) if row['ovx'] is not None else 0.0,
            gvz=float(row['gvz']) if row['gvz'] is not None else 0.0,
            us10y=float(row['us10y']) if row['us10y'] is not None else 0.0,
            fear_greed_score=int(row['fear_greed_score']) if row['fear_greed_score'] is not None else 50,
            market_regime=row['market_regime'] or 'neutral',
            vix_level=row['vix_level'] or '',
            us10y_strategy=row['us10y_strategy'] or '',
            risk_alert=row.get('risk_alert'),
            timestamp=row.get('updated_at') or row.get('created_at'),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get fear index: {e}")
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get("/fear-index/dimensions")
async def get_fear_index_dimensions():
    """
    Real-time multi-dimensional Fear & Greed index.
    Calculates 7 dimensions from macro_data, returns composite score + per-dimension detail.
    """
    try:
        service = FearIndexService()
        result = service.get_fear_index()
        dimensions = getattr(result, '_dimensions', [])
        regime_label = getattr(result, '_regime_label', '')
        return {
            'score': result.fear_greed_score,
            'regime': result.market_regime,
            'regime_label': regime_label,
            'dimensions': dimensions,
            'vix': result.vix,
            'gvz': result.gvz,
            'us10y': result.us10y,
            'vix_level': result.vix_level,
            'us10y_strategy': result.us10y_strategy,
            'timestamp': result.timestamp.isoformat(),
        }
    except Exception as e:
        logger.error("Failed to calculate fear index dimensions: %s", e)
        raise HTTPException(status_code=500, detail='Internal server error')


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
                vix=float(row['vix']) if row.get('vix') is not None else None,
                ovx=float(row['ovx']) if row.get('ovx') is not None else None,
                gvz=float(row['gvz']) if row.get('gvz') is not None else None,
                us10y=float(row['us10y']) if row.get('us10y') is not None else None,
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
        raise HTTPException(status_code=500, detail='Internal server error')


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
        raise HTTPException(status_code=500, detail='Internal server error')


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
        raise HTTPException(status_code=500, detail='Internal server error')


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
        raise HTTPException(status_code=500, detail='Internal server error')


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
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get("/overview", response_model=OverviewResponse)
async def get_overview():
    """获取舆情监控概览"""
    try:
        # 获取恐慌指数（从数据库缓存）
        fear_data = execute_query(
            """SELECT * FROM trade_fear_index
               ORDER BY trade_date DESC
               LIMIT 1""",
            env='online',
        )

        if fear_data:
            row = fear_data[0]
            fear_index = FearIndexResponse(
                vix=float(row['vix']) if row['vix'] is not None else 0.0,
                ovx=float(row['ovx']) if row['ovx'] is not None else 0.0,
                gvz=float(row['gvz']) if row['gvz'] is not None else 0.0,
                us10y=float(row['us10y']) if row['us10y'] is not None else 0.0,
                fear_greed_score=int(row['fear_greed_score']) if row['fear_greed_score'] is not None else 50,
                market_regime=row['market_regime'] or 'neutral',
                vix_level=row['vix_level'] or '',
                us10y_strategy=row['us10y_strategy'] or '',
                risk_alert=row.get('risk_alert'),
                timestamp=row.get('updated_at') or row.get('created_at'),
            )
        else:
            # 如果数据库无数据，返回默认值
            fear_index = FearIndexResponse(
                vix=0.0, ovx=0.0, gvz=0.0, us10y=0.0,
                fear_greed_score=50, market_regime='neutral',
                vix_level='', us10y_strategy='', risk_alert=None,
                timestamp=datetime.now(),
            )

        # 获取事件统计
        storage = SentimentStorage()
        all_events = storage.get_recent_events(days=3)

        bullish_count = sum(1 for e in all_events if e['event_type'] == 'bullish')
        bearish_count = sum(1 for e in all_events if e['event_type'] == 'bearish')

        # 获取聪明钱信号数量（这里简化处理，实际应该从数据库查询）
        smart_money_count = 0

        return OverviewResponse(
            fear_index=fear_index,
            event_count=len(all_events),
            bullish_count=bullish_count,
            bearish_count=bearish_count,
            smart_money_count=smart_money_count,
        )
    except Exception as e:
        logger.error(f"Failed to get overview: {e}")
        raise HTTPException(status_code=500, detail='Internal server error')
