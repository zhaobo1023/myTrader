# -*- coding: utf-8 -*-
"""
Portfolio Management schemas
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PortfolioStockIn(BaseModel):
    """Request body for POST/PUT portfolio stock."""
    stock_code: str = Field(..., description="Stock code, e.g. 000858 or PDD.O")
    stock_name: str = Field(default='', description="Stock name")
    industry: str = Field(default='', description="Industry classification")
    tier: str = Field(default='', description="Far Ahead | Leading | empty")
    status: str = Field(default='hold', description="hold | watch")
    position_pct: float = Field(default=0.0, description="Current position %")
    profit_26: Optional[float] = Field(default=None, description="2026E profit (100M CNY)")
    profit_27: Optional[float] = Field(default=None, description="2027E profit (100M CNY)")
    pe_26: Optional[float] = Field(default=None, description="2026E fair PE")
    pe_27: Optional[float] = Field(default=None, description="2027E fair PE")
    net_cash_26: float = Field(default=0.0, description="2026E net cash (100M CNY)")
    net_cash_27: float = Field(default=0.0, description="2027E net cash (100M CNY)")
    cash_adj_coef: float = Field(default=0.50, description="Net cash valuation coefficient")
    equity_adj: float = Field(default=0.0, description="Investment equity adjustment (100M CNY)")
    asset_growth_26: float = Field(default=0.0, description="2026 asset appreciation (100M CNY)")
    asset_growth_27: float = Field(default=0.0, description="2027 asset appreciation (100M CNY)")
    payout_ratio: float = Field(default=0.0, description="Dividend + buyback ratio (0-1)")
    research_depth: int = Field(default=80, description="Research depth score 0-100")
    notes: Optional[str] = Field(default=None)


class MarketFactors(BaseModel):
    valuation: float = Field(description="Valuation factor 0-30")
    business: float = Field(description="Business quality factor 0-30")
    liquidity: float = Field(description="Liquidity factor 0-20")
    industry_pref: float = Field(description="Industry preference factor 0-20")
    total: float = Field(description="Sum 0-100")


class PortfolioStockRow(BaseModel):
    """Full row returned in stock list, including computed fields."""
    id: int
    stock_code: str
    stock_name: str
    industry: str
    tier: str
    status: str
    position_pct: float
    profit_26: Optional[float]
    profit_27: Optional[float]
    pe_26: Optional[float]
    pe_27: Optional[float]
    net_cash_26: float
    net_cash_27: float
    cash_adj_coef: float
    equity_adj: float
    asset_growth_26: float
    asset_growth_27: float
    payout_ratio: float
    research_depth: int
    notes: Optional[str]
    updated_at: Optional[str]
    # Computed fields
    market_cap: Optional[float] = Field(default=None, description="Latest market cap (100M CNY)")
    tgt_26: Optional[float] = None
    tgt_27: Optional[float] = None
    return_27: Optional[float] = Field(default=None, description="2027E annualized return")
    growth_27: Optional[float] = Field(default=None, description="2026->2027 profit growth %")
    adj_return: Optional[float] = Field(default=None, description="Adjusted return after market factors")
    market_factors: Optional[MarketFactors] = None
    suggested_pct: Optional[float] = Field(default=None, description="From latest optimizer run")


class TriggerPriceRow(BaseModel):
    """Trigger price row for a stock."""
    stock_code: str
    stock_name: str
    market_cap: Optional[float] = None
    tgt_27: Optional[float] = None
    return_27: Optional[float] = None
    strong_buy: Optional[float] = None
    add: Optional[float] = None
    reduce: Optional[float] = None
    clear: Optional[float] = None
    signal: str = Field(default='', description="STRONG_BUY | ADD | HOLD | REDUCE | CLEAR | NO_DATA")
    signal_label: str = Field(default='')


class OptimizerAllocation(BaseModel):
    stock_code: str
    stock_name: str
    industry: str
    suggested_pct: float
    return_27: Optional[float]
    growth_27: Optional[float]
    div_yield: Optional[float]
    valuation_gap: Optional[float] = Field(description="(tgt27/mktcap - 1) as valuation deviation")


class PortfolioMetrics(BaseModel):
    stock_count: int
    weighted_return_27: Optional[float]
    weighted_pe_27: Optional[float]
    yy_pct: float = Field(description="Far Ahead tier total position %")
    leading_pct: float = Field(description="Leading tier total position %")
    cash_pct: float
    constraints_met: bool
    constraint_violations: List[str] = Field(default_factory=list)


class OptimizerResult(BaseModel):
    run_id: int
    allocations: Dict[str, float] = Field(description="{stock_code: pct}")
    metrics: PortfolioMetrics
    detail: List[OptimizerAllocation]
    constraints_met: bool


class IndustryWeight(BaseModel):
    industry: str
    position_pct: float
    stock_count: int


class BubblePoint(BaseModel):
    stock_code: str
    stock_name: str
    industry: str
    growth_27: Optional[float]
    pe_27: Optional[float]
    position_pct: float
    return_27: Optional[float]


class PortfolioOverview(BaseModel):
    stock_count: int
    weighted_return_27: Optional[float]
    weighted_pe_27: Optional[float]
    yy_pct: float
    leading_pct: float
    industry_weights: List[IndustryWeight]
    bubble_data: List[BubblePoint]
    latest_optimizer_run_id: Optional[int]
