"""
Sentiment Analyzer Service

情感分析服务 - 基于 LLM (DashScope)
- 单条新闻情感分析
- 批量新闻情感分析
- Prompt 构建
- 响应解析
"""

import logging
import json
from typing import List, Dict, Any, Optional

from dashscope import Generation

from data_analyst.sentiment.schemas import NewsItem, SentimentResult

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """情感分析服务"""

    def __init__(self, model: str = "qwen3.6-plus"):
        self.model = model

    def build_prompt(self, news: NewsItem) -> str:
        """
        构建情感分析 Prompt
        
        Args:
            news: 新闻条目
            
        Returns:
            Prompt 字符串
        """
        prompt = f"""你是一位专业的金融分析师，请对以下新闻进行情感分析。

新闻标题：{news.title}
新闻内容：{news.content or '无'}
股票代码：{news.stock_code or '无'}

请从以下维度分析：
1. 情感倾向 (positive/negative/neutral)
2. 情感强度 (1-5，1最弱，5最强)
3. 关键实体 (公司、人物、产品等)
4. 关键词 (核心概念)
5. 摘要 (一句话总结)
6. 市场影响 (对股价可能的影响)

请以 JSON 格式返回，格式如下：
{{
    "sentiment": "positive/negative/neutral",
    "sentiment_strength": 1-5,
    "entities": ["实体1", "实体2"],
    "keywords": ["关键词1", "关键词2"],
    "summary": "一句话摘要",
    "market_impact": "市场影响分析"
}}
"""
        return prompt

    def parse_response(self, response: str) -> Dict[str, Any]:
        """
        解析 LLM 响应
        
        Args:
            response: LLM 响应文本
            
        Returns:
            解析后的字典
        """
        try:
            # 尝试解析 JSON
            data = json.loads(response)
            
            # 验证必需字段
            required_fields = ['sentiment', 'sentiment_strength', 'entities', 'keywords', 'summary']
            for field in required_fields:
                if field not in data:
                    logger.warning(f"Missing field {field} in response")
                    return self._get_default_result()
            
            # 验证情感值
            if data['sentiment'] not in ['positive', 'negative', 'neutral']:
                logger.warning(f"Invalid sentiment value: {data['sentiment']}")
                data['sentiment'] = 'neutral'
            
            # 验证强度值
            if not isinstance(data['sentiment_strength'], int) or not (1 <= data['sentiment_strength'] <= 5):
                logger.warning(f"Invalid sentiment_strength: {data['sentiment_strength']}")
                data['sentiment_strength'] = 3
            
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return self._get_default_result()
        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            return self._get_default_result()

    def _get_default_result(self) -> Dict[str, Any]:
        """获取默认结果"""
        return {
            'sentiment': 'neutral',
            'sentiment_strength': 3,
            'entities': [],
            'keywords': [],
            'summary': '无法分析',
            'market_impact': None,
        }

    def analyze_single(self, news: NewsItem) -> SentimentResult:
        """
        分析单条新闻
        
        Args:
            news: 新闻条目
            
        Returns:
            情感分析结果
        """
        try:
            logger.info(f"Analyzing news: {news.title[:50]}...")
            
            # 构建 Prompt
            prompt = self.build_prompt(news)
            
            # 调用 LLM
            response = Generation.call(
                model=self.model,
                prompt=prompt,
                result_format='message',
            )
            
            if response.status_code != 200:
                logger.error(f"LLM API error: {response.code} - {response.message}")
                parsed = self._get_default_result()
            else:
                # 解析响应
                content = response.output.choices[0].message.content
                parsed = self.parse_response(content)
            
            # 构建结果
            result = SentimentResult(
                news_item=news,
                sentiment=parsed['sentiment'],
                sentiment_strength=parsed['sentiment_strength'],
                entities=parsed['entities'],
                keywords=parsed['keywords'],
                summary=parsed['summary'],
                market_impact=parsed.get('market_impact'),
            )
            
            logger.info(f"Analysis complete: sentiment={result.sentiment}, strength={result.sentiment_strength}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to analyze news: {e}")
            # 返回默认结果
            parsed = self._get_default_result()
            return SentimentResult(
                news_item=news,
                sentiment=parsed['sentiment'],
                sentiment_strength=parsed['sentiment_strength'],
                entities=parsed['entities'],
                keywords=parsed['keywords'],
                summary=parsed['summary'],
                market_impact=parsed.get('market_impact'),
            )

    def analyze_batch(self, news_list: List[NewsItem]) -> List[SentimentResult]:
        """
        批量分析新闻
        
        Args:
            news_list: 新闻列表
            
        Returns:
            情感分析结果列表
        """
        results = []
        for news in news_list:
            result = self.analyze_single(news)
            results.append(result)
        
        logger.info(f"Batch analysis complete: {len(results)} items")
        return results
