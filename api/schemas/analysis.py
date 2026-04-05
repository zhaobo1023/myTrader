# -*- coding: utf-8 -*-
"""
Analysis schemas
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class TechnicalAnalysisRequest(BaseModel):
    stock_code: str = Field(..., description="Stock code")
    indicators: Optional[List[str]] = Field(None, description="Specific indicators to analyze")


class SignalItem(BaseModel):
    name: str
    signal: str  # bullish, bearish, neutral
    description: str


class TechnicalAnalysisResponse(BaseModel):
    stock_code: str
    trade_date: str
    signals: List[SignalItem]
    score: float  # -100 to 100
    summary: str
    indicators: Dict[str, Any]


class FundamentalAnalysisRequest(BaseModel):
    stock_code: str = Field(..., description="Stock code")


class FundamentalItem(BaseModel):
    metric: str
    value: float
    description: str


class FundamentalAnalysisResponse(BaseModel):
    stock_code: str
    valuation: List[FundamentalItem]
    profitability: List[FundamentalItem]
    growth: List[FundamentalItem]
    score: float
    summary: str
