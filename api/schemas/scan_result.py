# api/schemas/scan_result.py
# -*- coding: utf-8 -*-
import json
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, field_validator


class ScanResultItem(BaseModel):
    id: int
    stock_code: str
    stock_name: str
    scan_date: date
    score: Optional[float]
    score_label: Optional[str]
    dimension_scores: Optional[Dict[str, Any]]
    signals: Optional[List[Dict[str, Any]]]
    max_severity: str
    notified: bool
    created_at: datetime

    model_config = {'from_attributes': True}

    @field_validator('dimension_scores', mode='before')
    @classmethod
    def parse_dimension_scores(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator('signals', mode='before')
    @classmethod
    def parse_signals(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v
