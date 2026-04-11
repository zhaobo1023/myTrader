"""
Sentiment Monitoring CLI

命令行入口，用于执行各种舆情监控任务
"""

import argparse
import logging
import sys
from datetime import datetime

from data_analyst.sentiment.fear_index import FearIndexService
from data_analyst.sentiment.news_fetcher import NewsFetcher
from data_analyst.sentiment.sentiment_analyzer import SentimentAnalyzer
from data_analyst.sentiment.event_detector import EventDetector
from data_analyst.sentiment.polymarket import PolymarketService
from data_analyst.sentiment.storage import SentimentStorage

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_fear_index(args):
    """执行恐慌指数任务"""
    logger.info("Running fear index task...")
    
    service = FearIndexService()
    result = service.get_fear_index()
    
    logger.info(f"Fear Index Result:")
    logger.info(f"  VIX: {result.vix}")
    logger.info(f"  OVX: {result.ovx}")
    logger.info(f"  GVZ: {result.gvz}")
    logger.info(f"  US10Y: {result.us10y}")
    logger.info(f"  Fear/Greed Score: {result.fear_greed_score}")
    logger.info(f"  Market Regime: {result.market_regime}")
    logger.info(f"  VIX Level: {result.vix_level}")
    logger.info(f"  US10Y Strategy: {result.us10y_strategy}")
    if result.risk_alert:
        logger.warning(f"  Risk Alert: {result.risk_alert}")
    
    if not args.dry_run:
        storage = SentimentStorage(env=args.env)
        storage.save_fear_index(result)
        logger.info("Fear index saved to database")


def run_news_sentiment(args):
    """执行新闻情感分析任务"""
    logger.info(f"Running news sentiment task for stock {args.stock}...")
    
    fetcher = NewsFetcher()
    news_list = fetcher.fetch_stock_news(args.stock, days=args.days)
    
    logger.info(f"Fetched {len(news_list)} news items")
    
    if not news_list:
        logger.warning("No news found")
        return
    
    analyzer = SentimentAnalyzer()
    results = analyzer.analyze_batch(news_list)
    
    logger.info(f"Analyzed {len(results)} news items")
    
    for result in results:
        logger.info(f"  - {result.news_item.title[:50]}... -> {result.sentiment} ({result.sentiment_strength}/5)")
    
    if not args.dry_run:
        storage = SentimentStorage(env=args.env)
        storage.save_news_sentiment(results)
        logger.info("News sentiment saved to database")


def run_event_detection(args):
    """执行事件检测任务"""
    logger.info(f"Running event detection task...")
    
    fetcher = NewsFetcher()
    
    if args.stock:
        news_list = fetcher.fetch_stock_news(args.stock, days=args.days)
    elif args.keywords:
        keywords = args.keywords.split(',')
        news_list = fetcher.fetch_keyword_news(keywords, days=args.days)
    else:
        logger.error("Must specify --stock or --keywords")
        return
    
    logger.info(f"Fetched {len(news_list)} news items")
    
    if not news_list:
        logger.warning("No news found")
        return
    
    detector = EventDetector()
    events = detector.detect_events(news_list)
    
    logger.info(f"Detected {len(events)} events")
    
    for event in events:
        logger.info(
            f"  - {event.event_type}/{event.event_category} -> {event.signal} "
            f"({event.stock_code or 'N/A'})"
        )
    
    if not args.dry_run:
        storage = SentimentStorage(env=args.env)
        storage.save_event_signals(events)
        logger.info("Event signals saved to database")


def run_polymarket(args):
    """执行 Polymarket 监控任务"""
    logger.info(f"Running Polymarket task for keywords: {args.keywords}...")
    
    keywords = args.keywords.split(',')
    service = PolymarketService()
    
    events = service.detect_smart_money_signals(keywords, min_volume=args.min_volume)
    
    logger.info(f"Found {len(events)} smart money signals")
    
    for event in events:
        logger.info(
            f"  - {event.market_question[:50]}... "
            f"Yes: {event.yes_probability:.1f}%, Volume: ${event.volume:,.0f}"
        )
    
    if not args.dry_run:
        storage = SentimentStorage(env=args.env)
        storage.save_polymarket_snapshot(events)
        logger.info("Polymarket snapshots saved to database")


def main():
    parser = argparse.ArgumentParser(description='Sentiment Monitoring CLI')
    parser.add_argument('--task', required=True, 
                       choices=['fear-index', 'news-sentiment', 'event-detection', 'polymarket'],
                       help='Task to run')
    parser.add_argument('--stock', help='Stock code (e.g., 002594)')
    parser.add_argument('--keywords', help='Keywords (comma-separated)')
    parser.add_argument('--days', type=int, default=3, help='Number of days to fetch')
    parser.add_argument('--min-volume', type=float, default=1000000, 
                       help='Minimum volume for Polymarket (USD)')
    parser.add_argument('--env', default='local', 
                       choices=['local', 'dev', 'prod'],
                       help='Database environment')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Dry run (do not save to database)')
    
    args = parser.parse_args()
    
    try:
        if args.task == 'fear-index':
            run_fear_index(args)
        elif args.task == 'news-sentiment':
            if not args.stock:
                logger.error("--stock is required for news-sentiment task")
                sys.exit(1)
            run_news_sentiment(args)
        elif args.task == 'event-detection':
            run_event_detection(args)
        elif args.task == 'polymarket':
            if not args.keywords:
                logger.error("--keywords is required for polymarket task")
                sys.exit(1)
            run_polymarket(args)
        
        logger.info("Task completed successfully")
        
    except Exception as e:
        logger.error(f"Task failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
