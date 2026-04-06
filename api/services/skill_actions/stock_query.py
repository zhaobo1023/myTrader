# -*- coding: utf-8 -*-
"""
stock-query skill action: search stocks by ts_code pattern.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def search(params: dict, db: AsyncSession) -> dict:
    query_str = params.get("query", "").strip()
    limit = min(int(params.get("limit", 10)), 50)
    if not query_str:
        return {"stocks": []}
    sql = text("""
        SELECT ts_code, trade_date, open, high, low, close, vol
        FROM trade_stock_daily
        WHERE ts_code LIKE :q
        ORDER BY trade_date DESC
        LIMIT :limit
    """)
    result = await db.execute(sql, {"q": f"%{query_str}%", "limit": limit})
    rows = result.fetchall()
    return {
        "stocks": [
            {
                "code": r.ts_code,
                "date": str(r.trade_date),
                "open": float(r.open or 0),
                "high": float(r.high or 0),
                "low": float(r.low or 0),
                "close": float(r.close or 0),
                "vol": float(r.vol or 0),
            }
            for r in rows
        ]
    }
