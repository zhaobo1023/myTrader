# -*- coding: utf-8 -*-
"""
Strategy & Backtest schemas
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class BacktestSubmitRequest(BaseModel):
    strategy_type: str = Field(default='xgboost', description="Strategy type")
    name: str = Field(..., description="Strategy name")
    description: Optional[str] = None
    stock_pool: Optional[List[str]] = Field(default=None, description="Stock codes")
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    initial_cash: float = Field(default=1000000)
    commission: float = Field(default=0.0002)
    position_pct: int = Field(default=95)


class BacktestSubmitResponse(BaseModel):
    job_id: int
    task_id: str
    status: str


class BacktestStatusResponse(BaseModel):
    job_id: int
    status: str
    progress: int = 0
    stage: Optional[str] = None
    total_return: Optional[float] = None
    annual_return: Optional[float] = None
    max_drawdown: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    ic: Optional[float] = None
    icir: Optional[float] = None
    error_msg: Optional[str] = None
    created_at: Optional[str] = None
    finished_at: Optional[str] = None


class StrategyResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    params: Optional[Dict[str, Any]]
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


class StrategyCreateRequest(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Preset strategy schemas
# ---------------------------------------------------------------------------

class StrategyWarning(BaseModel):
    type: str   # 'danger' | 'warning' | 'info'
    title: str
    body: str


class PresetStrategyMeta(BaseModel):
    key: str
    name: str
    description: str
    params_desc: str
    warnings: List[StrategyWarning] = []


class PresetRunSummary(BaseModel):
    id: int
    run_date: str
    status: str
    signal_count: int
    momentum_count: int
    reversal_count: int
    market_status: str
    market_message: str
    triggered_at: str
    finished_at: Optional[str]
    error_msg: Optional[str]


class PresetRunDetail(PresetRunSummary):
    signals: List[Dict[str, Any]]


class PresetStrategyCard(BaseModel):
    meta: PresetStrategyMeta
    today_run: Optional[PresetRunSummary]
    recent_runs: List[PresetRunSummary]
