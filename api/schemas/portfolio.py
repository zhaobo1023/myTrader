# -*- coding: utf-8 -*-
"""
Portfolio schemas
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class HoldingItem(BaseModel):
    stock_code: str
    stock_name: Optional[str] = None
    shares: int
    cost_price: float
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None


class PortfolioSummary(BaseModel):
    total_market_value: float
    total_cost: float
    total_pnl: float
    total_pnl_pct: float
    holdings_count: int
    holdings: List[HoldingItem]


class PortfolioSnapshot(BaseModel):
    date: str
    total_value: float
    pnl: float
    pnl_pct: float


class PortfolioHistoryResponse(BaseModel):
    start_date: str
    end_date: str
    count: int
    data: List[PortfolioSnapshot]
