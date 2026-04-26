# -*- coding: utf-8 -*-
"""
Agent builtin tools - wrap existing myTrader services.

Each tool is registered via @builtin_tool decorator.
Handler signature: async def handler(params: dict, ctx: AgentContext) -> dict
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from api.services.agent.schemas import AgentContext
from api.services.agent.tool_registry import builtin_tool

logger = logging.getLogger('myTrader.agent.tools')


async def _run_sync(fn, *args, **kwargs):
    """Run a synchronous function in executor to avoid blocking."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


def _safe_float(val: Any) -> Any:
    """Convert Decimal to float for JSON serialization."""
    if val is None:
        return None
    try:
        from decimal import Decimal
        if isinstance(val, Decimal):
            return float(val)
    except Exception:
        pass
    return val


# ============================================================
# T07: query_portfolio
# ============================================================

@builtin_tool(
    name="query_portfolio",
    description=(
        "查询用户当前持仓列表，返回股票代码、名称、仓位占比、盈亏等信息。"
        "当用户询问'我的持仓'、'我买了什么'、'持仓风险'、'持仓情况'等问题时使用。"
    ),
    parameters={"type": "object", "properties": {}, "required": []},
    category="data",
    requires_tier="free",
)
async def query_portfolio(params: dict, ctx: AgentContext) -> dict:
    """Query user's active positions from user_position table."""
    try:
        from sqlalchemy import select
        from api.models.user_position import UserPosition
        stmt = select(UserPosition).where(
            UserPosition.user_id == ctx.user.id,
            UserPosition.is_active == True,
        ).order_by(UserPosition.level, UserPosition.stock_code)
        result = await ctx.db.execute(stmt)
        positions = result.scalars().all()
        if not positions:
            return {"positions": [], "message": "当前没有持仓记录"}

        data = []
        for p in positions:
            data.append({
                "id": p.id,
                "stock_code": p.stock_code or "",
                "stock_name": p.stock_name or "",
                "level": p.level or "",
                "shares": p.shares,
                "cost_price": _safe_float(p.cost_price),
                "account": p.account or "",
                "note": p.note or "",
            })
        return {"positions": data, "total": len(data)}
    except Exception as e:
        logger.error('[query_portfolio] failed: %s', e)
        return {"positions": [], "error": str(e)}


# ============================================================
# T08: get_stock_indicators
# ============================================================

@builtin_tool(
    name="get_stock_indicators",
    description=(
        "获取指定股票的技术指标，包括 MA(5/20/60)、MACD、RSI、成交量比、RPS 等。"
        "当用户询问某只股票的技术面、指标、走势时使用。"
        "参数: stock_code (必填，6位数字股票代码)"
    ),
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {
                "type": "string",
                "description": "股票代码，6位数字，如 '002594'",
            },
        },
        "required": ["stock_code"],
    },
    category="data",
    requires_tier="free",
)
async def get_stock_indicators(params: dict, ctx: AgentContext) -> dict:
    """Get technical indicators for a stock."""
    stock_code = params.get("stock_code", "").strip()
    if not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
        return {"error": "stock_code must be a 6-digit number"}

    try:
        from config.db import execute_query
        sql = """
            SELECT stock_code, stock_name, close_price,
                   ma5, ma20, ma60,
                   macd, macd_signal, macd_hist,
                   rsi_14, volume_ratio,
                   return_5d, return_20d
            FROM trade_stock_indicators
            WHERE stock_code = %s
            ORDER BY trade_date DESC
            LIMIT 1
        """
        rows = await _run_sync(execute_query, sql, (stock_code,), env='online')
        if not rows:
            return {"stock_code": stock_code, "data": None, "message": "未找到该股票指标数据"}

        row = rows[0]
        cols = [
            "stock_code", "stock_name", "close_price",
            "ma5", "ma20", "ma60",
            "macd", "macd_signal", "macd_hist",
            "rsi_14", "volume_ratio",
            "return_5d", "return_20d",
        ]
        data = {cols[i]: _safe_float(row[i]) for i in range(min(len(cols), len(row)))}

        # Try to get RPS
        rps_sql = """
            SELECT rps_20 FROM trade_rps_ranking
            WHERE stock_code = %s
            ORDER BY trade_date DESC LIMIT 1
        """
        try:
            rps_rows = await _run_sync(execute_query, rps_sql, (stock_code,), env='online')
            data["rps_20"] = _safe_float(rps_rows[0][0]) if rps_rows else None
        except Exception:
            data["rps_20"] = None

        return {"stock_code": stock_code, "data": data}
    except Exception as e:
        logger.error('[get_stock_indicators] failed: %s', e)
        return {"stock_code": stock_code, "data": None, "error": str(e)}


# ============================================================
# T09: search_knowledge
# ============================================================

@builtin_tool(
    name="search_knowledge",
    description=(
        "检索投研知识库，包括研报、公告、笔记等文档。"
        "当用户询问某公司的研报、行业分析、公告内容时使用。"
        "参数: query (必填), top_k (可选，默认5)"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "检索关键词或问题",
            },
            "top_k": {
                "type": "integer",
                "description": "返回结果数量，默认5",
                "default": 5,
            },
        },
        "required": ["query"],
    },
    category="data",
    requires_tier="free",
)
async def search_knowledge(params: dict, ctx: AgentContext) -> dict:
    """Search RAG knowledge base."""
    query = params.get("query", "").strip()
    if not query:
        return {"documents": [], "message": "query is empty"}

    top_k = min(params.get("top_k", 5), 10)

    try:
        from investment_rag.retrieval.hybrid_retriever import HybridRetriever
        retriever = HybridRetriever()
        results = await _run_sync(retriever.retrieve, query, "reports", top_k)

        documents = []
        for doc in results[:top_k]:
            content = doc.get("content", "")
            # Truncate to prevent context bloat
            if len(content) > 500:
                content = content[:500] + "..."
            documents.append({
                "source": doc.get("metadata", {}).get("source", "unknown"),
                "text_snippet": content,
                "score": round(doc.get("rrf_score", 0.0), 4),
            })
        return {"documents": documents, "total": len(documents)}
    except Exception as e:
        logger.error('[search_knowledge] failed: %s', e)
        return {"documents": [], "error": str(e)}


# ============================================================
# T10: query_database
# ============================================================

@builtin_tool(
    name="query_database",
    description=(
        "用自然语言查询结构化金融数据，如财报、交易数据、因子数据等。"
        "会将自然语言转换为 SQL 执行查询。"
        "当用户询问具体的财务指标数值、历史交易数据、因子排名等结构化数据时使用。"
        "参数: query (必填，自然语言查询)"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "自然语言查询，如 '000858 最近3年的ROE'",
            },
        },
        "required": ["query"],
    },
    category="data",
    requires_tier="free",
)
async def query_database(params: dict, ctx: AgentContext) -> dict:
    """Natural language to SQL query."""
    query = params.get("query", "").strip()
    if not query:
        return {"error": "query is empty"}

    try:
        from investment_rag.retrieval.text2sql import Text2SQL
        text2sql = Text2SQL()

        # Build query
        query_info = await _run_sync(text2sql.build_query, query)
        if query_info is None:
            return {"error": "Failed to generate SQL from query", "sql": None, "results": []}

        sql = query_info.get("sql", "")

        # Security: only allow SELECT
        sql_upper = sql.strip().upper()
        if not sql_upper.startswith("SELECT"):
            return {"error": "Only SELECT queries are allowed", "sql": sql, "results": []}

        for forbidden in ("DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE"):
            if forbidden in sql_upper:
                return {"error": f"Forbidden SQL keyword: {forbidden}", "sql": sql, "results": []}

        # Execute
        results = await _run_sync(text2sql.execute, query)
        # Limit results
        if len(results) > 50:
            results = results[:50]

        # Convert Decimal values
        clean_results = []
        for row in results:
            clean_row = {k: _safe_float(v) for k, v in row.items()}
            clean_results.append(clean_row)

        return {
            "sql": sql,
            "results": clean_results,
            "total": len(clean_results),
            "description": query_info.get("description", ""),
        }
    except Exception as e:
        logger.error('[query_database] failed: %s', e)
        return {"error": str(e), "sql": None, "results": []}


# ============================================================
# T11: get_fear_index
# ============================================================

@builtin_tool(
    name="get_fear_index",
    description=(
        "获取市场恐慌指数，包括 VIX、OVX、GVZ、美国10年期国债收益率等。"
        "当用户询问市场情绪、恐慌程度、是否适合入场等问题时使用。"
    ),
    parameters={"type": "object", "properties": {}, "required": []},
    category="data",
    requires_tier="free",
)
async def get_fear_index(params: dict, ctx: AgentContext) -> dict:
    """Get market fear & greed index."""
    try:
        from data_analyst.sentiment.fear_index import FearIndexService
        service = FearIndexService()
        result = await _run_sync(service.get_fear_index)

        return {
            "vix": _safe_float(result.vix),
            "ovx": _safe_float(result.ovx),
            "gvz": _safe_float(result.gvz),
            "us10y": _safe_float(result.us10y),
            "fear_greed_score": result.fear_greed_score,
            "market_regime": result.market_regime,
            "vix_level": result.vix_level,
            "risk_alert": result.risk_alert,
            "timestamp": result.timestamp.isoformat() if result.timestamp else None,
        }
    except Exception as e:
        logger.error('[get_fear_index] failed: %s', e)
        return {"error": str(e)}


# ============================================================
# T12: search_news
# ============================================================

@builtin_tool(
    name="search_news",
    description=(
        "搜索新闻和舆情信息。可按股票代码或关键词搜索。"
        "当用户询问某股票的新闻、市场热点、行业动态时使用。"
        "参数: query (关键词), stock_code (可选), days (可选，默认3天)"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词",
            },
            "stock_code": {
                "type": "string",
                "description": "股票代码 (可选)",
            },
            "days": {
                "type": "integer",
                "description": "搜索天数范围，默认3",
                "default": 3,
            },
        },
        "required": ["query"],
    },
    category="data",
    requires_tier="free",
)
async def search_news(params: dict, ctx: AgentContext) -> dict:
    """Search news and sentiment."""
    query = params.get("query", "").strip()
    stock_code = params.get("stock_code", "").strip()
    days = min(params.get("days", 3), 7)

    try:
        from data_analyst.sentiment.news_fetcher import NewsFetcher
        fetcher = NewsFetcher()

        if stock_code:
            news_list = await _run_sync(fetcher.fetch_stock_news, stock_code, days)
        else:
            keywords = [k.strip() for k in query.split() if k.strip()]
            news_list = await _run_sync(fetcher.fetch_keyword_news, keywords, days)

        # Convert to dicts and limit
        results = []
        for item in news_list[:10]:
            results.append({
                "title": getattr(item, 'title', str(item)),
                "source": getattr(item, 'source', ''),
                "publish_time": str(getattr(item, 'publish_time', '')),
                "content": (getattr(item, 'content', '') or '')[:200],
            })
        return {"news": results, "total": len(results)}
    except Exception as e:
        logger.error('[search_news] failed: %s', e)
        return {"news": [], "error": str(e)}


# ============================================================
# T12: get_hot_sectors
# ============================================================

@builtin_tool(
    name="get_hot_sectors",
    description=(
        "获取当前热门板块和行业轮动数据。"
        "当用户询问哪些板块强势、行业轮动、热门概念等问题时使用。"
    ),
    parameters={"type": "object", "properties": {}, "required": []},
    category="data",
    requires_tier="free",
)
async def get_hot_sectors(params: dict, ctx: AgentContext) -> dict:
    """Get hot sector rotation data."""
    try:
        from config.db import execute_query
        sql = """
            SELECT industry_name, pct_change_1d, pct_change_5d,
                   volume_ratio, net_flow_rank
            FROM trade_sw_rotation_daily
            WHERE trade_date = (SELECT MAX(trade_date) FROM trade_sw_rotation_daily)
            ORDER BY pct_change_1d DESC
            LIMIT 20
        """
        rows = await _run_sync(execute_query, sql, env='online')
        if not rows:
            return {"sectors": [], "message": "No sector data available"}

        sectors = []
        for row in rows:
            sectors.append({
                "name": row[0],
                "change_1d": _safe_float(row[1]),
                "change_5d": _safe_float(row[2]),
                "volume_ratio": _safe_float(row[3]),
                "rank": _safe_float(row[4]),
            })
        return {"sectors": sectors, "total": len(sectors)}
    except Exception as e:
        logger.error('[get_hot_sectors] failed: %s', e)
        return {"sectors": [], "error": str(e)}


# ============================================================
# T13: add_watchlist (action)
# ============================================================

@builtin_tool(
    name="add_watchlist",
    description=(
        "添加股票到用户的关注列表。"
        "当用户说'关注这只股票'、'加入关注'、'帮我盯着'时使用。"
        "参数: stock_code (必填), stock_name (必填), note (可选)"
    ),
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {
                "type": "string",
                "description": "股票代码",
            },
            "stock_name": {
                "type": "string",
                "description": "股票名称",
            },
            "note": {
                "type": "string",
                "description": "备注信息",
            },
        },
        "required": ["stock_code", "stock_name"],
    },
    category="action",
    requires_tier="free",
)
async def add_watchlist(params: dict, ctx: AgentContext) -> dict:
    """Add a stock to user's watchlist."""
    stock_code = params.get("stock_code", "").strip()
    stock_name = params.get("stock_name", "").strip()

    if not stock_code or not stock_name:
        return {"success": False, "error": "stock_code and stock_name are required"}

    try:
        from sqlalchemy import select
        from api.models.watchlist import UserWatchlist

        # Check if already exists
        stmt = select(UserWatchlist).where(
            UserWatchlist.user_id == ctx.user.id,
            UserWatchlist.stock_code == stock_code,
        )
        result = await ctx.db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return {"success": True, "message": f"{stock_name}({stock_code}) 已在关注列表中"}

        watchlist_item = UserWatchlist(
            user_id=ctx.user.id,
            stock_code=stock_code,
            stock_name=stock_name,
            note=params.get("note", ""),
        )
        ctx.db.add(watchlist_item)
        await ctx.db.flush()
        return {"success": True, "message": f"已添加 {stock_name}({stock_code}) 到关注列表"}
    except Exception as e:
        logger.error('[add_watchlist] failed: %s', e)
        return {"success": False, "error": str(e)}


# ============================================================
# T14: add_to_candidate_pool (action)
# ============================================================

@builtin_tool(
    name="add_to_candidate_pool",
    description=(
        "批量添加股票到用户的候选池（候选股票池/自选池）。"
        "当用户说'加入候选池'、'添加到候选池'、'放到候选池观察'、'帮我加到候选池'时使用。"
        "支持一次添加多只股票。"
        "参数: stocks (必填，股票列表，每项含 stock_code 和 stock_name), "
        "source_detail (可选，来源说明如'电解铝相关'), memo (可选，备注)"
    ),
    parameters={
        "type": "object",
        "properties": {
            "stocks": {
                "type": "array",
                "description": "要添加的股票列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "stock_code": {
                            "type": "string",
                            "description": "股票代码，6位数字",
                        },
                        "stock_name": {
                            "type": "string",
                            "description": "股票名称",
                        },
                    },
                    "required": ["stock_code", "stock_name"],
                },
            },
            "source_detail": {
                "type": "string",
                "description": "来源说明，如'电解铝行业'、'AI智能搜索'",
            },
            "memo": {
                "type": "string",
                "description": "备注信息",
            },
        },
        "required": ["stocks"],
    },
    category="action",
    requires_tier="free",
)
async def add_to_candidate_pool(params: dict, ctx: AgentContext) -> dict:
    """Add stocks to user's candidate pool."""
    stocks = params.get("stocks", [])
    if not stocks:
        return {"success": False, "error": "stocks list is empty"}

    source_detail = params.get("source_detail", "agent")
    memo = params.get("memo", "")

    try:
        from api.services import candidate_pool_service as svc
        results = []
        added = 0
        updated = 0
        errors = []

        for item in stocks:
            code = item.get("stock_code", "").strip()
            name = item.get("stock_name", "").strip()
            if not code or not name:
                errors.append(f"missing stock_code or stock_name: {item}")
                continue
            try:
                result = await _run_sync(
                    svc.add_stock,
                    user_id=ctx.user.id,
                    stock_code=code,
                    stock_name=name,
                    source_type="manual",
                    source_detail=source_detail,
                    entry_snapshot=None,
                    memo=memo,
                )
                if result.get("action") == "added":
                    added += 1
                else:
                    updated += 1
                results.append({"stock_code": code, "stock_name": name, "action": result.get("action")})
            except Exception as e:
                logger.warning('[add_to_candidate_pool] failed for %s: %s', code, e)
                errors.append(f"{name}({code}): {e}")

        total = added + updated
        parts = []
        if added:
            parts.append(f"新增 {added} 只")
        if updated:
            parts.append(f"更新 {updated} 只")
        msg = f"已{'、'.join(parts)}股票到候选池" if parts else "没有股票被添加"
        if errors:
            msg += f"，{len(errors)} 只失败"

        return {
            "success": total > 0,
            "added": added,
            "updated": updated,
            "total": total,
            "results": results,
            "errors": errors if errors else None,
            "message": msg,
        }
    except Exception as e:
        logger.error('[add_to_candidate_pool] failed: %s', e)
        return {"success": False, "error": str(e)}


# ============================================================
# T13: add_position (action)
# ============================================================

@builtin_tool(
    name="add_position",
    description=(
        "添加股票到用户的模拟持仓。"
        "当用户说'加入持仓'、'模拟买入'等时使用。"
        "参数: stock_code (必填), stock_name (必填)"
    ),
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {
                "type": "string",
                "description": "股票代码",
            },
            "stock_name": {
                "type": "string",
                "description": "股票名称",
            },
        },
        "required": ["stock_code", "stock_name"],
    },
    category="action",
    requires_tier="pro",
)
async def add_position(params: dict, ctx: AgentContext) -> dict:
    """Add a stock to user's simulated positions."""
    stock_code = params.get("stock_code", "").strip()
    stock_name = params.get("stock_name", "").strip()

    if not stock_code or not stock_name:
        return {"success": False, "error": "stock_code and stock_name are required"}

    try:
        from sqlalchemy import select
        from api.models.user_position import UserPosition

        # Check duplicate
        stmt = select(UserPosition).where(
            UserPosition.user_id == ctx.user.id,
            UserPosition.stock_code == stock_code,
        )
        result = await ctx.db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return {"success": True, "message": f"{stock_name}({stock_code}) 已在持仓中"}

        position = UserPosition(
            user_id=ctx.user.id,
            stock_code=stock_code,
            stock_name=stock_name,
        )
        ctx.db.add(position)
        await ctx.db.flush()
        return {"success": True, "message": f"已添加 {stock_name}({stock_code}) 到模拟持仓"}
    except Exception as e:
        logger.error('[add_position] failed: %s', e)
        return {"success": False, "error": str(e)}


# ============================================================
# run_tech_scan (analysis)
# ============================================================

@builtin_tool(
    name="run_tech_scan",
    description=(
        "对指定股票进行技术面扫描，检测信号 (均线回踩/突破、金叉/死叉、超买/超卖等)。"
        "当用户说'技术分析'、'技术面扫描'、'信号检测'时使用。"
        "参数: stock_code (必填)"
    ),
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {
                "type": "string",
                "description": "股票代码，6位数字",
            },
        },
        "required": ["stock_code"],
    },
    category="analysis",
    requires_tier="pro",
)
async def run_tech_scan(params: dict, ctx: AgentContext) -> dict:
    """Run technical scan for a stock."""
    stock_code = params.get("stock_code", "").strip()
    if not stock_code:
        return {"error": "stock_code is required"}

    try:
        from api.services.skill_actions.tech_scan import run as run_scan
        result = await run_scan(
            {"stock_code": stock_code},
            ctx.db,
            ctx.user,
            ctx.redis,
        )
        return result
    except Exception as e:
        logger.error('[run_tech_scan] failed: %s', e)
        return {"error": str(e)}


# ============================================================
# T12: switch_persona
# ============================================================

@builtin_tool(
    name="switch_persona",
    description=(
        "切换交易助手的分析人设/投资风格。当用户说「切换到巴菲特」「用林奇的方式分析」"
        "「换成默认助手」「切换人设」等时使用。"
        "可选人设: default(默认助手), buffett(巴菲特), munger(查理芒格), "
        "graham(格雷厄姆), lynch(彼得林奇), livermore(利弗莫尔), dalio(达利欧), custom(自定义)。"
        "参数: persona_id (必填)"
    ),
    parameters={
        "type": "object",
        "properties": {
            "persona_id": {
                "type": "string",
                "description": "人设ID，可选: default, buffett, munger, graham, lynch, livermore, dalio, custom",
                "enum": ["default", "buffett", "munger", "graham", "lynch", "livermore", "dalio", "custom"],
            },
        },
        "required": ["persona_id"],
    },
    category="system",
)
async def switch_persona(params: dict, ctx: AgentContext) -> dict:
    """Return a switch_persona action for the frontend to handle."""
    from api.services.agent.prompts import PERSONAS
    persona_id = params.get("persona_id", "default")
    persona = PERSONAS.get(persona_id, PERSONAS["default"])
    return {
        "action": "switch_persona",
        "persona_id": persona_id,
        "persona_name": persona["name"],
        "message": f"已切换到「{persona['name']}」分析模式。",
    }


# ============================================================
# T15: trade_position (action) - 加仓/减仓/清仓
# ============================================================

@builtin_tool(
    name="trade_position",
    description=(
        "对用户持仓执行加仓、减仓或清仓操作，自动记录操作日志。"
        "加仓会重算加权平均成本；减仓保留原成本；清仓关闭持仓并计算总盈亏。"
        "使用场景：用户说'加仓XX'、'减仓XX'、'清仓XX'、'卖出XX'等。"
        "必须先通过 query_portfolio 确认持仓存在后再调用。"
        "参数: stock_code(必填), action(必填: add/reduce/close), price(必填), shares(减仓/加仓时必填)"
    ),
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {
                "type": "string",
                "description": "股票代码，6位数字，如 '002594'",
            },
            "action": {
                "type": "string",
                "enum": ["add", "reduce", "close"],
                "description": "操作类型：add=加仓，reduce=减仓，close=清仓",
            },
            "price": {
                "type": "number",
                "description": "成交价，必须大于0",
            },
            "shares": {
                "type": "integer",
                "description": "股数，加仓/减仓时必填；清仓时可不填",
                "minimum": 1,
            },
        },
        "required": ["stock_code", "action", "price"],
    },
    category="action",
    requires_tier="free",
)
async def trade_position(params: dict, ctx: AgentContext) -> dict:
    """Execute add/reduce/close trade on a position."""
    from sqlalchemy import select
    from api.models.user_position import UserPosition
    from api.models.trade_operation_log import TradeOperationLog
    import json as _json

    stock_code = params.get("stock_code", "").strip()
    action = params.get("action", "").lower()
    price = params.get("price")
    shares = params.get("shares")

    if not stock_code:
        return {"success": False, "error": "stock_code 不能为空"}
    if action not in ("add", "reduce", "close"):
        return {"success": False, "error": "action 必须是 add/reduce/close"}
    if not price or price <= 0:
        return {"success": False, "error": "price 必须大于 0"}
    if action in ("add", "reduce") and not shares:
        return {"success": False, "error": f"{action} 操作需要填写 shares 股数"}

    # 查找持仓（允许带 .SH/.SZ 后缀的 stock_code）
    base_code = stock_code.split(".")[0]
    result = await ctx.db.execute(
        select(UserPosition).where(
            UserPosition.user_id == ctx.user.id,
            UserPosition.is_active == True,
        )
    )
    all_positions = result.scalars().all()
    position = next(
        (p for p in all_positions if (p.stock_code or "").split(".")[0] == base_code),
        None,
    )

    if not position:
        return {"success": False, "error": f"未找到持仓 {stock_code}，请先确认持仓存在"}

    shares_before = position.shares or 0
    cost_before = position.cost_price
    name = position.stock_name or position.stock_code
    pnl_pct = None

    if action == "add":
        new_shares = shares_before + shares
        if cost_before and shares_before > 0:
            new_cost = round(
                (cost_before * shares_before + price * shares) / new_shares, 4
            )
        else:
            new_cost = price
        position.shares = new_shares
        position.cost_price = new_cost
        op_type = "add_reduce"
        detail = f"加仓 {name} @{price} +{shares}股 新股数={new_shares}股 新成本={new_cost}"
        before_val = _json.dumps({"shares": shares_before, "cost_price": cost_before})
        after_val = _json.dumps({"shares": new_shares, "cost_price": new_cost})
        summary = (
            f"加仓成功：{name}({stock_code})\n"
            f"- 操作：@{price} +{shares}股\n"
            f"- 股数：{shares_before} -> {new_shares} 股\n"
            f"- 持仓成本：{cost_before} -> {new_cost}"
        )

    elif action == "reduce":
        if shares >= shares_before:
            return {"success": False, "error": f"减仓股数({shares})不能大于等于持仓股数({shares_before})，如需清仓请用 close"}
        new_shares = shares_before - shares
        pnl_pct = round((price - cost_before) / cost_before * 100, 2) if cost_before else None
        position.shares = new_shares
        op_type = "add_reduce"
        pnl_str = f"{pnl_pct:+.2f}%" if pnl_pct is not None else "暂缺"
        detail = f"减仓 {name} @{price} -{shares}股 剩余={new_shares}股 本次盈亏={pnl_str}"
        before_val = _json.dumps({"shares": shares_before})
        after_val = _json.dumps({"shares": new_shares})
        summary = (
            f"减仓成功：{name}({stock_code})\n"
            f"- 操作：@{price} -{shares}股\n"
            f"- 股数：{shares_before} -> {new_shares} 股\n"
            f"- 本次盈亏：{pnl_str}"
        )

    else:  # close
        pnl_pct = round((price - cost_before) / cost_before * 100, 2) if cost_before else None
        position.is_active = False
        op_type = "close_position"
        pnl_str = f"{pnl_pct:+.2f}%" if pnl_pct is not None else "暂缺"
        detail = f"清仓 {name} @{price} {shares_before}股 盈亏={pnl_str}"
        before_val = _json.dumps({"shares": shares_before, "cost_price": cost_before})
        after_val = _json.dumps({"shares": 0, "pnl_pct": pnl_pct})
        summary = (
            f"清仓完成：{name}({stock_code})\n"
            f"- 成交价：{price}，持仓成本：{cost_before}\n"
            f"- 总盈亏：{pnl_str}"
        )

    ctx.db.add(TradeOperationLog(
        user_id=ctx.user.id,
        operation_type=op_type,
        stock_code=position.stock_code,
        stock_name=position.stock_name,
        detail=detail,
        before_value=before_val,
        after_value=after_val,
        source="agent",
    ))

    logger.info('[trade_position] user=%s action=%s stock=%s price=%s shares=%s',
                ctx.user.id, action, stock_code, price, shares)

    return {
        "success": True,
        "action": action,
        "stock_code": stock_code,
        "stock_name": name,
        "shares_before": shares_before,
        "shares_after": position.shares if action != "close" else 0,
        "cost_before": cost_before,
        "cost_after": position.cost_price if action != "close" else None,
        "pnl_pct": pnl_pct,
        "closed": action == "close",
        "message": summary,
    }


# ============================================================
# T16: get_trade_logs - 查询操作日志
# ============================================================

@builtin_tool(
    name="get_trade_logs",
    description=(
        "查询用户的持仓操作日志（加仓、减仓、清仓、建仓记录）。"
        "当用户询问'操作记录'、'交易日志'、'最近买卖了什么'、'XX股票的操作历史'等时使用。"
        "参数: stock_code(可选，筛选特定股票), limit(可选，条数，默认20)"
    ),
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {
                "type": "string",
                "description": "股票代码，6位数字，可选，不填则返回所有操作记录",
            },
            "limit": {
                "type": "integer",
                "description": "返回条数，默认20，最多50",
                "default": 20,
                "minimum": 1,
                "maximum": 50,
            },
        },
        "required": [],
    },
    category="data",
    requires_tier="free",
)
async def get_trade_logs(params: dict, ctx: AgentContext) -> dict:
    """Query user's trade operation logs."""
    from config.db import execute_query

    stock_code = params.get("stock_code", "").strip()
    limit = min(int(params.get("limit", 20)), 50)

    base_code = stock_code.split(".")[0] if stock_code else ""

    try:
        if base_code:
            rows = await _run_sync(
                execute_query,
                """SELECT operation_type, stock_code, stock_name, detail, created_at
                   FROM trade_operation_logs
                   WHERE user_id=%s AND stock_code LIKE %s
                   ORDER BY created_at DESC LIMIT %s""",
                (ctx.user.id, f"{base_code}%", limit),
                env="online",
            )
        else:
            rows = await _run_sync(
                execute_query,
                """SELECT operation_type, stock_code, stock_name, detail, created_at
                   FROM trade_operation_logs
                   WHERE user_id=%s
                   ORDER BY created_at DESC LIMIT %s""",
                (ctx.user.id, limit),
                env="online",
            )

        OP_LABEL = {
            "open_position": "建仓",
            "close_position": "清仓",
            "add_reduce": "加减仓",
            "modify_info": "修改",
        }

        logs = []
        for r in rows:
            logs.append({
                "type": OP_LABEL.get(r["operation_type"], r["operation_type"]),
                "stock_code": r["stock_code"],
                "stock_name": r["stock_name"],
                "detail": r["detail"],
                "date": str(r["created_at"])[:10],
            })

        return {"logs": logs, "total": len(logs)}
    except Exception as e:
        logger.error('[get_trade_logs] failed: %s', e)
        return {"logs": [], "error": str(e)}


# ============================================================
# T17: smart_stock_search (data) - AI智能选股
# ============================================================

@builtin_tool(
    name="smart_stock_search",
    description=(
        "AI智能选股：用自然语言描述选股条件，通过AI解析意图后搜索数据库，"
        "返回符合条件的股票列表（含股票代码、名称、行业、主营业务、RPS等）。"
        "当用户说'帮我找/筛选/搜索XX相关的股票'、'XX行业有哪些上市公司'、"
        "'主营XX的公司'、'XX概念股有哪些'等选股需求时使用。"
        "返回结果后，可配合 add_to_candidate_pool 或 create_theme_pool 将股票加入候选池或创建主题。"
        "参数: query (必填，自然语言选股条件), max_results (可选，最大返回数，默认30)"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "自然语言选股条件，如'铜矿营收占比高的公司'、'电解铝行业'、'江苏省的半导体公司'",
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回股票数量，默认30",
                "default": 30,
            },
        },
        "required": ["query"],
    },
    category="data",
    requires_tier="free",
)
async def smart_stock_search(params: dict, ctx: AgentContext) -> dict:
    """AI-powered smart stock search using SmartSearchSkill."""
    query = params.get("query", "").strip()
    if not query:
        return {"error": "query is empty", "stocks": []}

    max_results = min(params.get("max_results", 30), 50)

    try:
        from api.services.theme_smart_search import SmartSearchSkill
        skill = SmartSearchSkill()

        # Collect all SSE events from the stream
        stocks = []
        intent = None
        raw_total = 0

        async for event in skill.stream(query, max_results):
            etype = event.get("type")
            if etype == "intent_parsed":
                intent = event.get("intent")
            elif etype == "raw_results":
                raw_total = event.get("total", 0)
            elif etype == "candidate_list":
                stocks = event.get("stocks", [])
            elif etype == "error":
                return {"error": event.get("message", "search failed"), "stocks": []}

        # Simplify stock data for LLM context
        result_stocks = []
        for s in stocks:
            result_stocks.append({
                "stock_code": s.get("stock_code", ""),
                "stock_name": s.get("stock_name", ""),
                "industry": s.get("industry", ""),
                "relevance": s.get("relevance", ""),
                "reason": s.get("reason", ""),
                "close": s.get("close"),
                "rps_20": s.get("rps_20"),
                "rps_120": s.get("rps_120"),
                "main_business_short": s.get("main_business_short", ""),
            })

        return {
            "stocks": result_stocks,
            "total": len(result_stocks),
            "db_candidates": raw_total,
            "intent": intent,
            "message": f"AI搜索完成：数据库匹配 {raw_total} 只，AI审核后保留 {len(result_stocks)} 只",
        }
    except Exception as e:
        logger.error('[smart_stock_search] failed: %s', e)
        return {"error": str(e), "stocks": []}


# ============================================================
# T18: create_theme_pool (action) - 创建主题票池
# ============================================================

@builtin_tool(
    name="create_theme_pool",
    description=(
        "创建一个新的主题票池，并可选地批量添加股票到该主题中。"
        "当用户说'创建一个XX主题'、'把这些股票建成一个主题'、'新建XX概念的票池'时使用。"
        "注意：调用此工具前，应先用 smart_stock_search 搜索到股票列表，"
        "然后将搜索结果中用户选择的股票传入此工具。"
        "参数: theme_name (必填), description (可选), "
        "stocks (可选，股票列表，每项含 stock_code, stock_name, reason)"
    ),
    parameters={
        "type": "object",
        "properties": {
            "theme_name": {
                "type": "string",
                "description": "主题名称，如'电解铝产业链'、'铜矿概念'",
            },
            "description": {
                "type": "string",
                "description": "主题描述",
            },
            "stocks": {
                "type": "array",
                "description": "要添加到主题的股票列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "stock_code": {
                            "type": "string",
                            "description": "股票代码",
                        },
                        "stock_name": {
                            "type": "string",
                            "description": "股票名称",
                        },
                        "reason": {
                            "type": "string",
                            "description": "推荐理由",
                        },
                    },
                    "required": ["stock_code", "stock_name"],
                },
            },
        },
        "required": ["theme_name"],
    },
    category="action",
    requires_tier="free",
)
async def create_theme_pool(params: dict, ctx: AgentContext) -> dict:
    """Create a theme pool and optionally add stocks to it."""
    # This is an action tool - the orchestrator will send it to frontend for confirmation.
    # The actual execution happens in the frontend ActionConfirm component.
    # This function is defined for tool schema only.
    return {"status": "pending_confirmation"}


# ============================================================
# T19: query_sector_strength (data/free) - 申万板块强度查询
# ============================================================

@builtin_tool(
    name="query_sector_strength",
    description=(
        "查询申万行业板块强度排名，返回综合强度分、动量、量比、相位等指标。"
        "当用户问'哪些板块最强'、'板块轮动情况'、'拐点预警'、"
        "'今天哪个行业最活跃'、'强势行业有哪些'时使用。"
        "参数: sw_level(1或2，默认2), top_n(返回条数，默认10), "
        "trade_date(YYYY-MM-DD，默认最新), phase_filter(可选：accel_up/decel_up/accel_down/decel_down)"
    ),
    parameters={
        "type": "object",
        "properties": {
            "sw_level": {
                "type": "integer",
                "description": "申万级别：1=一级行业, 2=二级行业（默认）",
            },
            "top_n": {
                "type": "integer",
                "description": "返回强度排名前N个板块（默认10）",
            },
            "trade_date": {
                "type": "string",
                "description": "交易日期 YYYY-MM-DD（默认最新可用日期）",
            },
            "phase_filter": {
                "type": "string",
                "description": "相位过滤：accel_up/decel_up/accel_down/decel_down/neutral",
            },
        },
        "required": [],
    },
    category="data",
    requires_tier="free",
)
async def query_sector_strength(params: dict, ctx: AgentContext) -> dict:
    """Query sector strength rankings from trade_sector_strength_daily."""
    try:
        from api.services.sector_strength_service import get_latest_strength

        sw_level = int(params.get('sw_level', 2))
        top_n = int(params.get('top_n', 10))
        trade_date = params.get('trade_date') or None
        phase_filter = params.get('phase_filter') or None

        data = await _run_sync(
            get_latest_strength,
            sw_level=sw_level,
            top_n=top_n,
            trade_date=trade_date,
            phase_filter=phase_filter,
        )
        return {
            'success': True,
            'trade_date': data.get('trade_date'),
            'sectors': data.get('sectors', []),
            'inflections': data.get('inflections', []),
            'count': len(data.get('sectors', [])),
        }
    except Exception as e:
        logger.error('[query_sector_strength] failed: %s', e)
        return {'success': False, 'error': str(e), 'sectors': []}


# ============================================================
# T20: query_morning_picks (data/free) - 多因子盘前推荐
# ============================================================

@builtin_tool(
    name="query_morning_picks",
    description=(
        "查询今日多因子选股盘前推荐结果，基于强势板块成分股筛选。"
        "当用户问'盘前推荐'、'今天看哪些股'、'AI推荐什么股票'、"
        "'今天有什么机会'、'推荐选股'时使用。"
        "参数: top_n(返回条数，默认15), pick_date(YYYY-MM-DD，默认最新), "
        "sector_filter(可选：按申万二级行业名称过滤)"
    ),
    parameters={
        "type": "object",
        "properties": {
            "top_n": {
                "type": "integer",
                "description": "返回推荐股票数量（默认15）",
            },
            "pick_date": {
                "type": "string",
                "description": "选股日期 YYYY-MM-DD（默认最新可用日期）",
            },
            "sector_filter": {
                "type": "string",
                "description": "按申万二级行业名称过滤，如'半导体'、'白酒'",
            },
        },
        "required": [],
    },
    category="data",
    requires_tier="free",
)
async def query_morning_picks(params: dict, ctx: AgentContext) -> dict:
    """Query morning stock picks from trade_morning_picks."""
    try:
        from api.services.sector_strength_service import get_latest_picks

        top_n = int(params.get('top_n', 15))
        pick_date = params.get('pick_date') or None
        sector_filter = params.get('sector_filter') or None

        data = await _run_sync(
            get_latest_picks,
            top_n=top_n,
            pick_date=pick_date,
            sector_filter=sector_filter,
        )
        return {
            'success': True,
            'pick_date': data.get('pick_date'),
            'picks': data.get('picks', []),
            'count': len(data.get('picks', [])),
        }
    except Exception as e:
        logger.error('[query_morning_picks] failed: %s', e)
        return {'success': False, 'error': str(e), 'picks': []}
