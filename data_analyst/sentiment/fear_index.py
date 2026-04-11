"""
Fear Index Service

恐慌指数服务 - 基于课程代码 market_fear_index.py
- 获取 VIX/OVX/GVZ/US10Y 数据
- 计算综合恐慌/贪婪评分
- 判断市场状态
- 检测风险传导
"""

import logging
from typing import Optional
from datetime import datetime

import yfinance as yf

from data_analyst.sentiment.config import VIX_THRESHOLDS, US10Y_THRESHOLDS, DATA_SOURCE_CONFIG
from data_analyst.sentiment.schemas import FearIndexResult

logger = logging.getLogger(__name__)


class FearIndexService:
    """恐慌指数服务"""

    def __init__(self):
        self.config = DATA_SOURCE_CONFIG['yfinance']

    def fetch_vix(self) -> float:
        """获取 VIX 恐慌指数"""
        try:
            ticker = yf.Ticker(self.config['vix_ticker'])
            data = ticker.history(period='1d')
            if not data.empty:
                vix_value = float(data['Close'].iloc[-1])
                if vix_value < 0:
                    logger.warning(f"Invalid VIX value: {vix_value}, using 0.0")
                    return 0.0
                return vix_value
            logger.warning("VIX data is empty")
            return 0.0
        except Exception as e:
            logger.error(f"Failed to fetch VIX: {e}")
            return 0.0

    def fetch_ovx(self) -> float:
        """获取 OVX 原油波动率指数"""
        try:
            ticker = yf.Ticker(self.config['ovx_ticker'])
            data = ticker.history(period='1d')
            if not data.empty:
                return float(data['Close'].iloc[-1])
            logger.warning("OVX data is empty")
            return 0.0
        except Exception as e:
            logger.error(f"Failed to fetch OVX: {e}")
            return 0.0

    def fetch_gvz(self) -> float:
        """获取 GVZ 黄金波动率指数"""
        try:
            ticker = yf.Ticker(self.config['gvz_ticker'])
            data = ticker.history(period='1d')
            if not data.empty:
                return float(data['Close'].iloc[-1])
            logger.warning("GVZ data is empty")
            return 0.0
        except Exception as e:
            logger.error(f"Failed to fetch GVZ: {e}")
            return 0.0

    def fetch_us10y(self) -> float:
        """获取美国10年期国债收益率"""
        try:
            ticker = yf.Ticker(self.config['us10y_ticker'])
            data = ticker.history(period='1d')
            if not data.empty:
                return float(data['Close'].iloc[-1])
            logger.warning("US10Y data is empty")
            return 0.0
        except Exception as e:
            logger.error(f"Failed to fetch US10Y: {e}")
            return 0.0

    def calculate_fear_greed_score(self, vix: float, us10y: float) -> int:
        """
        计算综合恐慌/贪婪评分 (0-100)
        0 = 极度恐慌, 100 = 极度贪婪
        """
        score = 50  # 基准分

        # VIX 维度
        if vix < VIX_THRESHOLDS['extreme_calm']:
            score += 30      # 极度贪婪
        elif vix < VIX_THRESHOLDS['normal']:
            score += 15      # 偏贪婪
        elif vix < VIX_THRESHOLDS['anxiety']:
            score += 0       # 中性
        elif vix < VIX_THRESHOLDS['fear']:
            score -= 15      # 恐慌
        else:
            score -= 30      # 极度恐慌

        # 10年期国债维度
        if us10y < US10Y_THRESHOLDS['low']:
            score += 10      # 宽松利好
        elif us10y > US10Y_THRESHOLDS['high'] + 0.4:  # > 4.8
            score -= 10      # 紧缩利空

        return max(0, min(100, score))

    def get_market_regime(self, score: int) -> str:
        """根据评分判断市场状态"""
        if score <= 20:
            return 'extreme_fear'
        elif score <= 40:
            return 'fear'
        elif score <= 60:
            return 'neutral'
        elif score <= 80:
            return 'greed'
        else:
            return 'extreme_greed'

    def get_vix_level(self, vix: float) -> str:
        """获取 VIX 级别描述"""
        if vix < VIX_THRESHOLDS['extreme_calm']:
            return '极度平静(警惕自满)'
        elif vix < VIX_THRESHOLDS['normal']:
            return '正常'
        elif vix < VIX_THRESHOLDS['anxiety']:
            return '焦虑'
        elif vix < VIX_THRESHOLDS['fear']:
            return '恐慌'
        else:
            return '极度恐慌'

    def get_us10y_strategy(self, us10y: float) -> str:
        """获取 US10Y 策略建议"""
        if us10y > US10Y_THRESHOLDS['high']:
            return '利率偏高，看好价值股和防御板块'
        elif us10y > US10Y_THRESHOLDS['watershed']:
            return '利率处于分水岭，密切关注方向选择'
        else:
            return '宽松预期，资金回流成长股'

    def check_risk_contagion(self, vix: float, ovx: float) -> Optional[str]:
        """
        风险传导检测
        - OVX飙升但VIX滞后 -> 风险集中在能源端
        - OVX与VIX同步共振向上 -> 地缘风险已触发流动性危机
        """
        if ovx > 50 and vix > 25:
            return 'OVX与VIX同步共振向上: 地缘风险已触发流动性危机或全球经济衰退预期，需立即风控'
        elif ovx > 50 and vix < 20:
            return 'OVX飙升但VIX滞后: 风险仍集中在能源端，尚未传导至全球宏观信用风险'
        return None

    def get_fear_index(self) -> FearIndexResult:
        """获取完整恐慌指数"""
        logger.info("Fetching fear index data...")

        # 获取各项指标
        vix = self.fetch_vix()
        ovx = self.fetch_ovx()
        gvz = self.fetch_gvz()
        us10y = self.fetch_us10y()

        logger.info(f"VIX: {vix}, OVX: {ovx}, GVZ: {gvz}, US10Y: {us10y}")

        # 计算评分和状态
        score = self.calculate_fear_greed_score(vix, us10y)
        regime = self.get_market_regime(score)
        vix_level = self.get_vix_level(vix)
        us10y_strategy = self.get_us10y_strategy(us10y)
        risk_alert = self.check_risk_contagion(vix, ovx)

        result = FearIndexResult(
            vix=vix,
            ovx=ovx,
            gvz=gvz,
            us10y=us10y,
            fear_greed_score=score,
            market_regime=regime,
            vix_level=vix_level,
            us10y_strategy=us10y_strategy,
            risk_alert=risk_alert,
            timestamp=datetime.now(),
        )

        logger.info(f"Fear index calculated: score={score}, regime={regime}")
        return result
