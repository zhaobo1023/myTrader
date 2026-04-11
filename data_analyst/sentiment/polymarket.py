"""
Polymarket Service

Polymarket 预测市场服务
- 搜索市场
- 获取市场详情
- 检测聪明钱信号
"""

import logging
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime

from data_analyst.sentiment.config import DATA_SOURCE_CONFIG
from data_analyst.sentiment.schemas import PolymarketEvent

logger = logging.getLogger(__name__)


class PolymarketService:
    """Polymarket 预测市场服务"""

    def __init__(self):
        self.config = DATA_SOURCE_CONFIG['polymarket']
        self.base_url = self.config['base_url']
        self.timeout = self.config['timeout']

    def search_markets(
        self,
        keyword: str,
        min_volume: float = 100000,
        limit: int = 20
    ) -> List[PolymarketEvent]:
        """
        搜索市场
        
        Args:
            keyword: 搜索关键词
            min_volume: 最小交易量 (USD)
            limit: 返回数量限制
            
        Returns:
            市场事件列表
        """
        try:
            logger.info(f"Searching Polymarket for keyword: {keyword}")
            
            # Polymarket Gamma API endpoint
            url = f"{self.base_url}/markets"
            params = {
                'limit': limit,
                'offset': 0,
            }
            
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            markets = []
            
            for item in data:
                # 过滤关键词
                question = item.get('question', '')
                if keyword.lower() not in question.lower():
                    continue
                
                # 解析市场数据
                market = self.parse_market(item)
                
                # 过滤交易量
                if market and market.volume >= min_volume:
                    markets.append(market)
            
            logger.info(f"Found {len(markets)} markets for keyword {keyword}")
            return markets
            
        except Exception as e:
            logger.error(f"Failed to search Polymarket: {e}")
            return []

    def parse_market(self, data: Dict[str, Any]) -> Optional[PolymarketEvent]:
        """
        解析市场数据
        
        Args:
            data: API 返回的市场数据
            
        Returns:
            PolymarketEvent 对象
        """
        try:
            # 解析概率
            outcome_prices = data.get('outcomePrices', '[]')
            if isinstance(outcome_prices, str):
                import json
                prices = json.loads(outcome_prices)
            else:
                prices = outcome_prices
            
            yes_probability = float(prices[0]) * 100 if prices else 0.0
            
            # 解析交易量
            volume = float(data.get('volume', 0))
            
            # 检测聪明钱信号
            is_smart_money = self._detect_smart_money(yes_probability, volume)
            
            event = PolymarketEvent(
                event_id=data.get('id', ''),
                event_title=data.get('title', ''),
                market_question=data.get('question', ''),
                yes_probability=yes_probability,
                volume=volume,
                is_smart_money_signal=is_smart_money,
                category=data.get('category', None),
                snapshot_time=datetime.now(),
            )
            
            return event
            
        except Exception as e:
            logger.error(f"Failed to parse market data: {e}")
            return None

    def _detect_smart_money(self, yes_probability: float, volume: float) -> bool:
        """
        检测聪明钱信号
        
        规则：
        - 交易量 > 100万美元
        - 概率极端 (>70% 或 <30%)
        
        Args:
            yes_probability: Yes 概率 (0-100)
            volume: 交易量 (USD)
            
        Returns:
            是否为聪明钱信号
        """
        if volume < 1000000:
            return False
        
        if yes_probability > 70 or yes_probability < 30:
            return True
        
        return False

    def get_market_details(self, market_id: str) -> Optional[PolymarketEvent]:
        """
        获取市场详情
        
        Args:
            market_id: 市场 ID
            
        Returns:
            市场事件
        """
        try:
            logger.info(f"Fetching market details for {market_id}")
            
            url = f"{self.base_url}/markets/{market_id}"
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            return self.parse_market(data)
            
        except Exception as e:
            logger.error(f"Failed to get market details: {e}")
            return None

    def detect_smart_money_signals(
        self,
        keywords: List[str],
        min_volume: float = 1000000
    ) -> List[PolymarketEvent]:
        """
        检测聪明钱信号
        
        Args:
            keywords: 关键词列表
            min_volume: 最小交易量
            
        Returns:
            聪明钱信号列表
        """
        all_signals = []
        
        for keyword in keywords:
            markets = self.search_markets(keyword, min_volume=min_volume)
            smart_money = [m for m in markets if m.is_smart_money_signal]
            all_signals.extend(smart_money)
        
        logger.info(f"Detected {len(all_signals)} smart money signals")
        return all_signals
