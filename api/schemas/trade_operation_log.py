# -*- coding: utf-8 -*-
"""
Trade operation log schemas (调仓操作日志)
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class TradeLogCreate(BaseModel):
    """手动添加日志"""
    operation_type: str = Field(default='manual_note', max_length=20)
    stock_code: Optional[str] = Field(default='', max_length=20)
    stock_name: Optional[str] = Field(default=None, max_length=50)
    detail: Optional[str] = Field(default=None, max_length=500)
    before_value: Optional[str] = Field(default=None, max_length=200)
    after_value: Optional[str] = Field(default=None, max_length=200)


class TradeLogResponse(BaseModel):
    id: int
    operation_type: str
    stock_code: str
    stock_name: Optional[str] = None
    detail: Optional[str] = None
    before_value: Optional[str] = None
    after_value: Optional[str] = None
    source: str
    created_at: str

    class Config:
        from_attributes = True


class TradeLogListResponse(BaseModel):
    items: List[TradeLogResponse]
    total: int
