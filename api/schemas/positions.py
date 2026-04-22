# -*- coding: utf-8 -*-
"""
Position schemas - request/response models
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class PositionCreate(BaseModel):
    stock_code: str = Field(min_length=1, max_length=20)
    stock_name: Optional[str] = Field(default=None, max_length=50)
    level: Optional[str] = Field(default=None, max_length=10)
    shares: Optional[int] = None
    cost_price: Optional[float] = None
    account: Optional[str] = Field(default=None, max_length=50)
    note: Optional[str] = None


class PositionUpdate(BaseModel):
    stock_name: Optional[str] = Field(default=None, max_length=50)
    level: Optional[str] = Field(default=None, max_length=10)
    shares: Optional[int] = None
    cost_price: Optional[float] = None
    account: Optional[str] = Field(default=None, max_length=50)
    note: Optional[str] = None


class PositionResponse(BaseModel):
    id: int
    stock_code: str
    stock_name: Optional[str] = None
    level: Optional[str] = None
    shares: Optional[int] = None
    cost_price: Optional[float] = None
    account: Optional[str] = None
    note: Optional[str] = None
    is_active: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class PositionListResponse(BaseModel):
    items: List[PositionResponse]
    total: int


class TradeActionRequest(BaseModel):
    action: str = Field(description="add=加仓, reduce=减仓, close=清仓")
    price: float = Field(gt=0, description="成交价")
    shares: Optional[int] = Field(default=None, ge=1, description="股数（清仓时可不填）")


class TradeActionResponse(BaseModel):
    position_id: int
    action: str
    shares_before: Optional[int]
    shares_after: Optional[int]
    cost_before: Optional[float]
    cost_after: Optional[float]
    pnl_pct: Optional[float] = None   # 清仓时返回盈亏%
    closed: bool = False


class PositionImportItem(BaseModel):
    stock_code: str = Field(min_length=1, max_length=20)
    stock_name: Optional[str] = None
    level: Optional[str] = None
    shares: Optional[int] = None
    cost_price: Optional[float] = None
    account: Optional[str] = None
    note: Optional[str] = None


class PositionImportRequest(BaseModel):
    items: List[PositionImportItem]
