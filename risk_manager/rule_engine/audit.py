# -*- coding: utf-8 -*-
"""
审计日志
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import pandas as pd

from .models import AggregatedDecision, Decision, RiskContext


@dataclass
class AuditEntry:
    """单次风控评估的审计记录"""
    timestamp: datetime
    stock_code: str
    price: float
    final_decision: Decision
    suggested_position_pct: float
    details: str  # summary 文本


class AuditLog:
    """风控审计日志"""

    def __init__(self):
        self._entries: List[AuditEntry] = []

    def record(self, ctx: RiskContext, agg: AggregatedDecision):
        """记录一次评估"""
        entry = AuditEntry(
            timestamp=ctx.date or datetime.now(),
            stock_code=ctx.stock_code,
            price=ctx.price,
            final_decision=agg.final_decision,
            suggested_position_pct=agg.suggested_position_pct,
            details=agg.summary(),
        )
        self._entries.append(entry)

    def to_dataframe(self) -> pd.DataFrame:
        """导出为 DataFrame"""
        if not self._entries:
            return pd.DataFrame()
        return pd.DataFrame([
            {
                'timestamp': e.timestamp,
                'stock_code': e.stock_code,
                'price': e.price,
                'decision': e.final_decision.name,
                'suggested_pct': e.suggested_position_pct,
                'details': e.details,
            }
            for e in self._entries
        ])

    def get_rejections(self) -> List[AuditEntry]:
        """获取所有被拒绝的记录"""
        return [e for e in self._entries if e.final_decision >= Decision.REJECT]

    def get_warnings(self) -> List[AuditEntry]:
        """获取所有警告记录"""
        return [e for e in self._entries if e.final_decision == Decision.WARN]

    def __len__(self) -> int:
        return len(self._entries)
