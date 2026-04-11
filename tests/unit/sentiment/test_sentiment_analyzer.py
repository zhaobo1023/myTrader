"""
Test Sentiment Analyzer Service
"""

import pytest
from data_analyst.sentiment.sentiment_analyzer import SentimentAnalyzer
from data_analyst.sentiment.schemas import NewsItem


def test_build_prompt():
    """Prompt 构建正确"""
    analyzer = SentimentAnalyzer()
    news = NewsItem(title='比亚迪业绩大增', content='比亚迪发布年报...', stock_code='002594')
    prompt = analyzer.build_prompt(news)
    assert '情感分析' in prompt or 'sentiment' in prompt.lower()
    assert '比亚迪业绩大增' in prompt
    assert '002594' in prompt


def test_parse_response_positive():
    """解析正面情感响应"""
    analyzer = SentimentAnalyzer()
    mock_response = '{"sentiment": "positive", "sentiment_strength": 4, "entities": ["比亚迪"], "keywords": ["业绩", "增长"], "summary": "业绩利好"}'
    result = analyzer.parse_response(mock_response)
    assert result['sentiment'] == 'positive'
    assert result['sentiment_strength'] == 4
    assert '比亚迪' in result['entities']


def test_parse_response_invalid():
    """解析无效响应应返回中性"""
    analyzer = SentimentAnalyzer()
    result = analyzer.parse_response('invalid json')
    assert result['sentiment'] == 'neutral'
    assert result['sentiment_strength'] == 3


def test_parse_response_missing_fields():
    """解析缺少字段的响应"""
    analyzer = SentimentAnalyzer()
    mock_response = '{"sentiment": "positive"}'
    result = analyzer.parse_response(mock_response)
    assert result['sentiment'] == 'neutral'


@pytest.mark.integration
def test_analyze_single_real():
    """实际调用 LLM 分析（需 API Key）"""
    analyzer = SentimentAnalyzer()
    news = NewsItem(
        title='比亚迪2025年报亮眼，营收突破8000亿',
        content='比亚迪发布年报，营收同比增长30%...',
        stock_code='002594'
    )
    result = analyzer.analyze_single(news)
    assert result.sentiment in ['positive', 'negative', 'neutral']
    assert 1 <= result.sentiment_strength <= 5
