# -*- coding: utf-8 -*-
"""Collect regime and crowding signals from DB"""
import logging
from typing import Optional, Tuple
from config.db import execute_query

logger = logging.getLogger(__name__)


class SignalCollector:
    """Collect latest regime and crowding signals"""
    
    def __init__(self, env: str = 'online'):
        self.env = env
    
    def get_latest_regime(self) -> Optional[str]:
        """Get latest bull/bear regime from trade_bull_bear_signal"""
        rows = execute_query(
            "SELECT regime FROM trade_bull_bear_signal ORDER BY calc_date DESC LIMIT 1",
            env=self.env,
        )
        if rows:
            return rows[0]['regime']
        logger.warning("No bull/bear signal found, defaulting to NEUTRAL")
        return 'NEUTRAL'
    
    def get_latest_crowding(self) -> Optional[str]:
        """Get latest crowding level from trade_crowding_score"""
        rows = execute_query(
            "SELECT crowding_level FROM trade_crowding_score WHERE dimension = 'overall' ORDER BY calc_date DESC LIMIT 1",
            env=self.env,
        )
        if rows:
            return rows[0]['crowding_level']
        logger.warning("No crowding score found, defaulting to LOW")
        return 'LOW'
    
    def collect(self) -> Tuple[str, str]:
        """Collect both signals. Returns (regime, crowding_level)"""
        regime = self.get_latest_regime() or 'NEUTRAL'
        crowding = self.get_latest_crowding() or 'LOW'
        logger.info(f"Collected signals: regime={regime}, crowding={crowding}")
        return regime, crowding
