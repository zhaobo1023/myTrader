# -*- coding: utf-8 -*-
"""
Market schemas - request/response models for market data
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class KlineRequest(BaseModel):
    stock_code: str = Field(..., description="Stock code, e.g. 600519")
    start_date: Optional[str] = Field(None, description="Start date YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="End date YYYY-MM-DD")
    limit: int = Field(default=120, ge=1, le=1000, description="Max rows to return")


class KlineItem(BaseModel):
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    amount: Optional[float] = None
    turnover_rate: Optional[float] = None


class KlineResponse(BaseModel):
    stock_code: str
    count: int
    data: List[KlineItem]


class IndicatorRequest(BaseModel):
    stock_code: str = Field(..., description="Stock code")
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    indicators: Optional[List[str]] = Field(
        default=None,
        description="Specific indicators to return. None = all",
    )


class IndicatorItem(BaseModel):
    trade_date: str
    close: float
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    ma120: Optional[float] = None
    ma250: Optional[float] = None
    macd_dif: Optional[float] = None
    macd_dea: Optional[float] = None
    macd_histogram: Optional[float] = None
    rsi_6: Optional[float] = None
    rsi_12: Optional[float] = None
    rsi_24: Optional[float] = None
    volume_ratio: Optional[float] = None


class IndicatorResponse(BaseModel):
    stock_code: str
    count: int
    data: List[dict]


class FactorRequest(BaseModel):
    calc_date: str = Field(..., description="Factor calculation date YYYY-MM-DD")
    stock_codes: Optional[List[str]] = Field(None, description="Filter by stock codes")


class FactorResponse(BaseModel):
    calc_date: str
    count: int
    data: List[dict]


class RPSRequest(BaseModel):
    trade_date: Optional[str] = Field(None, description="Trade date YYYY-MM-DD")
    window: int = Field(default=250, ge=20, le=500)
    top_n: int = Field(default=50, ge=1, le=500)
    min_rps: Optional[float] = Field(None, description="Minimum RPS filter")


class RPSItem(BaseModel):
    stock_code: str
    rps: float
    rps_slope: Optional[float] = None


class RPSResponse(BaseModel):
    trade_date: str
    window: int
    count: int
    data: List[RPSItem]


class StockSearchRequest(BaseModel):
    keyword: str = Field(..., min_length=1, description="Stock code or name keyword")
    limit: int = Field(default=20, ge=1, le=100)


class StockInfo(BaseModel):
    stock_code: str
    stock_name: Optional[str] = None
    industry: Optional[str] = None


class StockSearchResponse(BaseModel):
    count: int
    data: List[StockInfo]
