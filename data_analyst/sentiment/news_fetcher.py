"""
News Fetcher Service

新闻获取服务 - 基于 akshare
- 获取个股新闻
- 按关键词获取新闻
- 关键词过滤
"""

import logging
from typing import List, Optional
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd

from data_analyst.sentiment.schemas import NewsItem

logger = logging.getLogger(__name__)


class NewsFetcher:
    """新闻获取服务"""

    def fetch_stock_news(self, stock_code: str, days: int = 3) -> List[NewsItem]:
        """
        获取个股新闻
        
        Args:
            stock_code: 股票代码 (如 '002594')
            days: 获取最近几天的新闻
            
        Returns:
            新闻列表
        """
        try:
            logger.info(f"Fetching news for stock {stock_code}, days={days}")
            
            # 使用 akshare 获取个股新闻
            df = ak.stock_news_em(symbol=stock_code)
            
            if df.empty:
                logger.warning(f"No news found for stock {stock_code}")
                return []
            
            # 过滤最近 N 天的新闻
            cutoff_date = datetime.now() - timedelta(days=days)
            news_list = []
            
            for _, row in df.iterrows():
                try:
                    # akshare 返回的字段: 发布时间, 新闻标题, 新闻内容, 文章来源, 新闻链接
                    publish_time_str = row.get('发布时间', '')
                    if publish_time_str:
                        publish_time = pd.to_datetime(publish_time_str)
                        if publish_time < cutoff_date:
                            continue
                    else:
                        publish_time = None
                    
                    news = NewsItem(
                        title=row.get('新闻标题', ''),
                        content=row.get('新闻内容', ''),
                        source=row.get('文章来源', ''),
                        url=row.get('新闻链接', ''),
                        publish_time=publish_time,
                        stock_code=stock_code,
                    )
                    news_list.append(news)
                except Exception as e:
                    logger.warning(f"Failed to parse news row: {e}")
                    continue
            
            logger.info(f"Fetched {len(news_list)} news items for {stock_code}")
            return news_list
            
        except Exception as e:
            logger.error(f"Failed to fetch stock news for {stock_code}: {e}")
            return []

    def fetch_keyword_news(self, keywords: List[str], days: int = 3) -> List[NewsItem]:
        """
        按关键词获取新闻
        
        Args:
            keywords: 关键词列表
            days: 获取最近几天的新闻
            
        Returns:
            新闻列表
        """
        try:
            logger.info(f"Fetching news for keywords {keywords}, days={days}")
            
            # 使用 akshare 获取财经新闻
            df = ak.news_cctv()
            
            if df.empty:
                logger.warning("No news found")
                return []
            
            # 过滤最近 N 天的新闻
            cutoff_date = datetime.now() - timedelta(days=days)
            news_list = []
            
            for _, row in df.iterrows():
                try:
                    # 检查是否包含关键词
                    title = row.get('title', '')
                    content = row.get('content', '')
                    
                    if not any(kw in title or kw in content for kw in keywords):
                        continue
                    
                    publish_time_str = row.get('time', '')
                    if publish_time_str:
                        publish_time = pd.to_datetime(publish_time_str)
                        if publish_time < cutoff_date:
                            continue
                    else:
                        publish_time = None
                    
                    news = NewsItem(
                        title=title,
                        content=content,
                        source='央视财经',
                        url=row.get('url', ''),
                        publish_time=publish_time,
                    )
                    news_list.append(news)
                except Exception as e:
                    logger.warning(f"Failed to parse news row: {e}")
                    continue
            
            logger.info(f"Fetched {len(news_list)} news items for keywords {keywords}")
            return news_list
            
        except Exception as e:
            logger.error(f"Failed to fetch keyword news: {e}")
            return []

    def filter_by_keywords(self, news_list: List[NewsItem], keywords: List[str]) -> List[NewsItem]:
        """
        按关键词过滤新闻
        
        Args:
            news_list: 新闻列表
            keywords: 关键词列表
            
        Returns:
            过滤后的新闻列表
        """
        filtered = []
        for news in news_list:
            text = f"{news.title} {news.content or ''}"
            if any(kw in text for kw in keywords):
                filtered.append(news)
        
        logger.info(f"Filtered {len(filtered)}/{len(news_list)} news items by keywords")
        return filtered
