"""
Test News Fetcher Service
"""

import pytest
from data_analyst.sentiment.news_fetcher import NewsFetcher
from data_analyst.sentiment.schemas import NewsItem


def test_filter_by_keywords():
    """关键词过滤正确"""
    fetcher = NewsFetcher()
    news = [
        NewsItem(title='比亚迪资产重组公告', content=''),
        NewsItem(title='今日大盘走势', content=''),
        NewsItem(title='某公司回购股份', content=''),
    ]
    filtered = fetcher.filter_by_keywords(news, ['资产重组'])
    assert len(filtered) == 1
    assert '资产重组' in filtered[0].title


def test_filter_by_keywords_multiple():
    """多关键词过滤"""
    fetcher = NewsFetcher()
    news = [
        NewsItem(title='比亚迪资产重组公告', content=''),
        NewsItem(title='某公司回购股份', content=''),
        NewsItem(title='今日大盘走势', content=''),
    ]
    filtered = fetcher.filter_by_keywords(news, ['资产重组', '回购'])
    assert len(filtered) == 2


def test_filter_by_keywords_empty():
    """空关键词列表"""
    fetcher = NewsFetcher()
    news = [NewsItem(title='测试新闻', content='')]
    filtered = fetcher.filter_by_keywords(news, [])
    assert len(filtered) == 0


@pytest.mark.integration
def test_fetch_stock_news_real():
    """实际获取个股新闻（需网络）"""
    fetcher = NewsFetcher()
    news = fetcher.fetch_stock_news('002594', days=3)
    assert isinstance(news, list)
