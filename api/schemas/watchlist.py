# api/schemas/watchlist.py
# -*- coding: utf-8 -*-
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class WatchlistAddRequest(BaseModel):
    stock_code: str       # e.g. "600519"
    stock_name: str       # e.g. "Guizhou Maotai"
    note: Optional[str] = None


class WatchlistItem(BaseModel):
    id: int
    stock_code: str
    stock_name: str
    note: Optional[str]
    added_at: datetime

    model_config = {'from_attributes': True}


class WatchlistResponse(BaseModel):
    items: List[WatchlistItem]
    total: int
