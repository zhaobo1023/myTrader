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


class TechReportCard(BaseModel):
    id: int
    stock_code: str
    stock_name: str
    trade_date: str
    score: float
    score_label: str
    ma_pattern: Optional[str] = None
    max_severity: str
    summary: str
    signal_count: int
    created_at: str
    has_html: Optional[bool] = None


class TechReportDetail(TechReportCard):
    signals: List[dict]
    indicators: dict


class TechReportListResponse(BaseModel):
    total: int
    items: List[TechReportCard]


class TechReportGenerateRequest(BaseModel):
    stock_code: str
    stock_name: Optional[str] = ''


class TechReportGenerateResponse(BaseModel):
    generated: bool
    quota_used: int
    quota_limit: int = 50
    report: TechReportDetail
