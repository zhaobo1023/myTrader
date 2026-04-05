# -*- coding: utf-8 -*-
"""
RAG schemas
"""
from typing import Literal, Optional, List
from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User question")
    collection: Optional[str] = Field(default=None, description="Collection name")
    top_k: int = Field(default=5, ge=1, le=20)


class RAGSource(BaseModel):
    source: str
    text: str
    score: float
    metadata: dict = {}


class RAGQueryResponse(BaseModel):
    query: str
    intent: str
    answer: str
    sources: List[RAGSource] = []
    sql_results: Optional[list] = None


# --- Report Generation ---

class ReportGenerateRequest(BaseModel):
    stock_code: str = Field(..., description="股票代码，如 000858")
    stock_name: str = Field(..., description="公司名称，如 五粮液")
    report_type: Literal["fundamental", "technical", "comprehensive"] = Field(
        default="comprehensive",
        description=(
            "报告类型: "
            "fundamental=纯基本面五步法, "
            "technical=纯技术面, "
            "comprehensive=综合（默认）"
        ),
    )
    collection: str = Field(default="reports", description="ChromaDB collection 名")


class ReportListItem(BaseModel):
    id: str
    stock_code: str
    stock_name: str
    report_type: str
    created_at: str


class ReportListResponse(BaseModel):
    reports: List[ReportListItem]
    total: int
