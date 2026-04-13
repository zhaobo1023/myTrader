# -*- coding: utf-8 -*-
"""
Theme Pool schemas - request/response models
"""
from datetime import datetime, date
from typing import Optional, List

from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# Theme CRUD
# ------------------------------------------------------------------

class ThemeCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None


class ThemeUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


class ThemeStatusRequest(BaseModel):
    status: str = Field(description='draft / active / archived')


class ThemeResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    status: str
    created_by: int
    creator_email: Optional[str] = None
    stock_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ThemeListResponse(BaseModel):
    items: List[ThemeResponse]
    total: int


# ------------------------------------------------------------------
# Stock management
# ------------------------------------------------------------------

class StockAddRequest(BaseModel):
    stock_code: str = Field(min_length=1, max_length=20)
    stock_name: str = Field(default='', max_length=50)
    reason: Optional[str] = None


class StockBatchAddRequest(BaseModel):
    stocks: List[StockAddRequest] = Field(min_length=1)


class HumanStatusRequest(BaseModel):
    human_status: str = Field(description='normal / focused / watching / excluded')


class NoteUpdateRequest(BaseModel):
    note: Optional[str] = None


class ReasonUpdateRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


# ------------------------------------------------------------------
# Score response
# ------------------------------------------------------------------

class StockScoreItem(BaseModel):
    score_date: Optional[date] = None
    rps_20: Optional[float] = None
    rps_60: Optional[float] = None
    rps_120: Optional[float] = None
    rps_250: Optional[float] = None
    tech_score: Optional[float] = None
    tech_signals: Optional[str] = None
    fundamental_score: Optional[float] = None
    fundamental_data: Optional[str] = None
    total_score: Optional[float] = None
    return_5d: Optional[float] = None
    return_10d: Optional[float] = None
    return_20d: Optional[float] = None
    return_60d: Optional[float] = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------------
# Stock response (with latest score + vote counts)
# ------------------------------------------------------------------

class StockResponse(BaseModel):
    id: int
    theme_id: int
    stock_code: str
    stock_name: str
    recommended_by: int
    recommender_email: Optional[str] = None
    reason: Optional[str] = None
    entry_price: Optional[float] = None
    entry_date: date
    human_status: str
    note: Optional[str] = None
    added_at: datetime
    # latest score
    latest_score: Optional[StockScoreItem] = None
    # vote summary
    up_votes: int = 0
    down_votes: int = 0
    my_vote: Optional[int] = None  # current user's vote: 1, -1, or None

    class Config:
        from_attributes = True


class StockListResponse(BaseModel):
    items: List[StockResponse]
    total: int


# ------------------------------------------------------------------
# Vote
# ------------------------------------------------------------------

class VoteRequest(BaseModel):
    vote: int = Field(description='1=up, -1=down')


class VoteResponse(BaseModel):
    up_votes: int
    down_votes: int
    my_vote: Optional[int] = None
