#!/usr/bin/env python
"""
Sentiment Data Test Script

测试舆情监控数据抓取和存储
"""

import sys
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_fear_index():
    """测试恐慌指数获取"""
    logger.info("=" * 60)
    logger.info("测试 1: 恐慌指数获取")
    logger.info("=" * 60)
    
    try:
        from data_analyst.sentiment.fear_index import FearIndexService
        
        service = FearIndexService()
        result = service.get_fear_index()
        
        logger.info(f"✅ VIX: {result.vix:.2f}")
        logger.info(f"✅ OVX: {result.ovx:.2f}")
        logger.info(f"✅ GVZ: {result.gvz:.2f}")
        logger.info(f"✅ US10Y: {result.us10y:.2f}")
        logger.info(f"✅ 恐慌/贪婪评分: {result.fear_greed_score}")
        logger.info(f"✅ 市场状态: {result.market_regime}")
        logger.info(f"✅ VIX级别: {result.vix_level}")
        logger.info(f"✅ 利率策略: {result.us10y_strategy}")
        if result.risk_alert:
            logger.warning(f"⚠️  风险警报: {result.risk_alert}")
        
        return True, result
    except Exception as e:
        logger.error(f"❌ 恐慌指数测试失败: {e}")
        return False, None


def test_news_fetch(stock_code='002594', days=1):
    """测试新闻获取"""
    logger.info("=" * 60)
    logger.info(f"测试 2: 新闻获取 (股票: {stock_code})")
    logger.info("=" * 60)
    
    try:
        from data_analyst.sentiment.news_fetcher import NewsFetcher
        
        fetcher = NewsFetcher()
        news_list = fetcher.fetch_stock_news(stock_code, days=days)
        
        logger.info(f"✅ 获取到 {len(news_list)} 条新闻")
        
        for i, news in enumerate(news_list[:3], 1):
            logger.info(f"  {i}. {news.title[:50]}...")
            if news.publish_time:
                logger.info(f"     时间: {news.publish_time}")
        
        return True, news_list
    except Exception as e:
        logger.error(f"❌ 新闻获取测试失败: {e}")
        return False, None


def test_event_detection(news_list):
    """测试事件检测"""
    logger.info("=" * 60)
    logger.info("测试 3: 事件检测")
    logger.info("=" * 60)
    
    if not news_list:
        logger.warning("⚠️  无新闻数据，跳过事件检测")
        return False, None
    
    try:
        from data_analyst.sentiment.event_detector import EventDetector
        
        detector = EventDetector()
        events = detector.detect_events(news_list)
        
        logger.info(f"✅ 检测到 {len(events)} 个事件")
        
        for i, event in enumerate(events[:5], 1):
            logger.info(f"  {i}. {event.event_category} -> {event.signal}")
            logger.info(f"     股票: {event.stock_code or 'N/A'}")
            logger.info(f"     关键词: {', '.join(event.matched_keywords)}")
        
        return True, events
    except Exception as e:
        logger.error(f"❌ 事件检测测试失败: {e}")
        return False, None


def test_storage(fear_result=None, news_list=None, events=None):
    """测试数据存储"""
    logger.info("=" * 60)
    logger.info("测试 4: 数据存储")
    logger.info("=" * 60)
    
    try:
        from data_analyst.sentiment.storage import SentimentStorage
        
        storage = SentimentStorage(env='local')
        
        # 测试保存恐慌指数
        if fear_result:
            success = storage.save_fear_index(fear_result)
            if success:
                logger.info("✅ 恐慌指数保存成功")
            else:
                logger.error("❌ 恐慌指数保存失败")
        
        # 测试保存事件信号
        if events:
            success = storage.save_event_signals(events)
            if success:
                logger.info(f"✅ 事件信号保存成功 ({len(events)} 条)")
            else:
                logger.error("❌ 事件信号保存失败")
        
        # 查询历史数据
        history = storage.get_fear_index_history(days=7)
        logger.info(f"✅ 查询到 {len(history)} 条历史恐慌指数")
        
        recent_events = storage.get_recent_events(days=3)
        logger.info(f"✅ 查询到 {len(recent_events)} 条最近事件")
        
        return True
    except Exception as e:
        logger.error(f"❌ 数据存储测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database_tables():
    """测试数据库表是否存在"""
    logger.info("=" * 60)
    logger.info("测试 0: 数据库表检查")
    logger.info("=" * 60)
    
    try:
        from config.db import execute_query
        
        tables = [
            'trade_fear_index',
            'trade_news_sentiment',
            'trade_event_signal',
            'trade_polymarket_snapshot'
        ]
        
        for table in tables:
            result = execute_query(
                f"SHOW TABLES LIKE '{table}'",
                env='local'
            )
            if result:
                logger.info(f"✅ 表 {table} 存在")
            else:
                logger.error(f"❌ 表 {table} 不存在")
                return False
        
        return True
    except Exception as e:
        logger.error(f"❌ 数据库表检查失败: {e}")
        return False


def main():
    """主测试流程"""
    logger.info("\n" + "=" * 60)
    logger.info("舆情监控数据抓取测试")
    logger.info("=" * 60 + "\n")
    
    # 0. 检查数据库表
    if not test_database_tables():
        logger.error("\n❌ 数据库表不存在，请先执行迁移: make migrate")
        return
    
    # 1. 测试恐慌指数
    fear_success, fear_result = test_fear_index()
    
    # 2. 测试新闻获取
    news_success, news_list = test_news_fetch(stock_code='002594', days=1)
    
    # 3. 测试事件检测
    event_success, events = test_event_detection(news_list if news_success else [])
    
    # 4. 测试数据存储
    storage_success = test_storage(
        fear_result=fear_result if fear_success else None,
        news_list=news_list if news_success else None,
        events=events if event_success else None
    )
    
    # 总结
    logger.info("\n" + "=" * 60)
    logger.info("测试总结")
    logger.info("=" * 60)
    logger.info(f"恐慌指数: {'✅ 通过' if fear_success else '❌ 失败'}")
    logger.info(f"新闻获取: {'✅ 通过' if news_success else '❌ 失败'}")
    logger.info(f"事件检测: {'✅ 通过' if event_success else '❌ 失败'}")
    logger.info(f"数据存储: {'✅ 通过' if storage_success else '❌ 失败'}")
    
    if fear_success and news_success and storage_success:
        logger.info("\n🎉 所有测试通过！数据抓取功能正常。")
    else:
        logger.warning("\n⚠️  部分测试失败，请检查错误信息。")


if __name__ == '__main__':
    main()
