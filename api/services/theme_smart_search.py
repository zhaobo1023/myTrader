# -*- coding: utf-8 -*-
"""
Smart search service for theme creation.

Three-phase pipeline:
  1. LLM parses natural language -> structured intent
  2. DB query using parsed keywords (trade_stock_info)
  3. LLM reviews DB results for relevance

Usage (from router):
    skill = SmartSearchSkill()
    async for event in skill.stream(query="PCB业务增速高的"):
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
"""
import asyncio
import json
import logging
import re

from config.db import execute_query
from api.services.llm_client_factory import get_llm_client, llm_call_with_retry
from api.services.theme_smart_search_prompts import (
    INTENT_PARSE_SYSTEM, INTENT_PARSE_USER,
    REVIEW_SYSTEM, REVIEW_USER,
)

logger = logging.getLogger('myTrader.smart_search')

_DB_ENV = 'online'


class SmartSearchSkill:
    """
    Smart search skill: given a natural language query, produce a
    filtered stock list via LLM intent parsing + DB search + LLM review.
    """

    def __init__(self, model_alias: str | None = None):
        self._llm_factory = get_llm_client(model_alias)

    async def stream(self, query: str, max_results: int = 50):
        """Async generator: yields SSE event dicts."""
        try:
            async for event in self._run(query, max_results):
                yield event
        except Exception as e:
            logger.exception('[SmartSearchSkill] unexpected error for query=%s', query)
            yield {'type': 'error', 'message': str(e)}

    async def _run(self, query: str, max_results: int):
        yield {'type': 'start', 'message': f'正在解析查询意图...'}

        # --- Phase 1: LLM parse intent ---
        yield {'type': 'phase', 'phase': 'intent_parsing', 'message': '正在让 AI 解析搜索条件...'}
        intent = await self._parse_intent(query)
        yield {'type': 'intent_parsed', 'intent': intent}

        # --- Phase 2: DB query (with fallback retry) ---
        yield {'type': 'phase', 'phase': 'db_query', 'message': '正在从数据库搜索匹配股票...'}
        raw_results = await self._query_db(intent)

        # Fallback: if 0 results, try with fallback keywords from query text
        if not raw_results:
            fallback_kws = self._fallback_keywords(query)
            if fallback_kws != intent.get('keywords'):
                logger.info('[SmartSearch] 0 results, retrying with fallback keywords: %s', fallback_kws)
                fallback_intent = {**intent, 'keywords': fallback_kws}
                raw_results = await self._query_db(fallback_intent)
                if raw_results:
                    intent = fallback_intent

        yield {
            'type': 'raw_results',
            'total': len(raw_results),
            'message': f'数据库找到 {len(raw_results)} 只匹配股票',
        }

        if not raw_results:
            yield {
                'type': 'candidate_list',
                'stocks': [],
                'total': 0,
            }
            yield {'type': 'done', 'summary': '未找到匹配股票'}
            return

        # --- Phase 3: LLM review ---
        yield {'type': 'phase', 'phase': 'llm_review', 'message': f'正在让 AI 审核 {len(raw_results)} 只候选股票...'}
        reviewed = await self._review_stocks(query, raw_results, max_results)

        yield {
            'type': 'candidate_list',
            'stocks': reviewed,
            'total': len(reviewed),
        }
        yield {
            'type': 'done',
            'summary': f'共找到 {len(reviewed)} 只相关股票（数据库 {len(raw_results)} 只，AI 审核后保留 {len(reviewed)} 只）',
        }

    # ------------------------------------------------------------------
    # Phase 1: LLM intent parsing
    # ------------------------------------------------------------------

    async def _parse_intent(self, query: str) -> dict:
        """Parse natural language query into structured intent."""
        try:
            raw = await llm_call_with_retry(
                self._llm_factory.call,
                prompt=INTENT_PARSE_USER.format(query=query),
                system_prompt=INTENT_PARSE_SYSTEM,
                validate_json=False,
                timeout_sec=30.0,
                temperature=0.1,
                max_tokens=512,
            )
            intent = json.loads(self._extract_json(raw))
            # Validate structure
            if not isinstance(intent.get('keywords'), list) or not intent['keywords']:
                intent = {'keywords': [query], 'financial_hint': '', 'industry': None, 'province': None}
            # Safety: split any keyword longer than 8 chars into shorter parts
            intent['keywords'] = self._sanitize_keywords(intent['keywords'])
            return intent
        except Exception as e:
            logger.warning('[SmartSearch] intent parse failed: %s, using fallback', e)
            return {'keywords': self._fallback_keywords(query), 'financial_hint': '', 'industry': None, 'province': None}

    @staticmethod
    def _sanitize_keywords(keywords: list[str]) -> list[str]:
        """Ensure no keyword is too long; split long ones."""
        result = []
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            if len(kw) <= 6:
                result.append(kw)
            else:
                # Long keyword: keep it but also add 2-char sub-segments
                result.append(kw)
                # Extract meaningful sub-keywords (every 2-4 chars)
                for i in range(0, len(kw) - 1, 2):
                    sub = kw[i:i + 2]
                    if sub not in result:
                        result.append(sub)
        return result[:10]  # cap at 10

    @staticmethod
    def _fallback_keywords(query: str) -> list[str]:
        """Extract short keywords from query when LLM parsing fails."""
        import jieba
        try:
            words = [w for w in jieba.cut(query) if len(w) >= 2]
            return words[:8] if words else [query[:4]]
        except Exception:
            # If jieba not available, simple 2-gram extraction
            keywords = []
            clean = re.sub(r'[的了吗呢吧啊哪些有哪公司企业上市]', '', query)
            if len(clean) >= 2:
                keywords.append(clean[:4] if len(clean) > 4 else clean)
                if len(clean) > 2:
                    keywords.append(clean[:2])
            return keywords if keywords else [query[:4]]

    # ------------------------------------------------------------------
    # Phase 2: DB query
    # ------------------------------------------------------------------

    async def _query_db(self, intent: dict) -> list[dict]:
        """Query trade_stock_info using parsed keywords."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_query_db, intent)

    def _sync_query_db(self, intent: dict) -> list[dict]:
        """Synchronous DB query using intent keywords."""
        keywords = list(intent.get('keywords', []))
        province = intent.get('province')
        industry = intent.get('industry')

        # Merge industry into keywords for OR matching (DB industry names
        # are long official names like "石油、煤炭及其他燃料加工业",
        # so exact match rarely works -- use LIKE instead).
        if industry and industry not in keywords:
            keywords.append(industry)

        if not keywords and not province:
            return []

        where = ['1=1']
        params = []

        if province:
            where.append('i.province LIKE %s')
            params.append(f'%{province}%')

        # Multi-keyword OR match on text fields + industry column
        if keywords:
            kw_clauses = []
            for kw in keywords:
                like_val = f'%{kw}%'
                kw_clauses.append(
                    '(i.main_business LIKE %s OR i.business_scope LIKE %s'
                    ' OR i.company_intro LIKE %s OR i.industry LIKE %s)'
                )
                params.extend([like_val, like_val, like_val, like_val])
            where.append(f'({" OR ".join(kw_clauses)})')

        where_sql = ' AND '.join(where)

        # Query stock info with full main_business for LLM review
        rows = execute_query(
            f'''SELECT i.stock_code, i.stock_name, i.province, i.city,
                       i.industry, i.listed_date, i.main_business
                FROM trade_stock_info i
                WHERE {where_sql}
                ORDER BY i.stock_code
                LIMIT 300''',
            tuple(params) if params else None,
            env=_DB_ENV,
        )

        if not rows:
            return []

        codes_list = [r['stock_code'] for r in rows]

        # Fetch latest RPS
        latest_date = self._latest_trade_date()
        rps_map = self._batch_fetch_rps(codes_list, latest_date)

        # Fetch latest close price
        price_map = self._batch_fetch_price(codes_list, latest_date)

        # Assemble results
        result = []
        for r in rows:
            code = r['stock_code']
            rps = rps_map.get(code, {})
            result.append({
                'stock_code': code,
                'stock_name': r['stock_name'],
                'province': r['province'],
                'industry': r['industry'],
                'listed_date': str(r['listed_date']) if r['listed_date'] else None,
                'main_business': r['main_business'] or '',
                'close': float(price_map[code]) if price_map.get(code) is not None else None,
                'rps_250': float(rps['rps_250']) if rps.get('rps_250') is not None else None,
                'rps_120': float(rps['rps_120']) if rps.get('rps_120') is not None else None,
                'rps_20': float(rps['rps_20']) if rps.get('rps_20') is not None else None,
            })

        return result

    def _latest_trade_date(self) -> str:
        from datetime import date
        rows = execute_query(
            'SELECT MAX(trade_date) AS d FROM trade_stock_rps', env=_DB_ENV
        )
        if rows and rows[0]['d']:
            return str(rows[0]['d'])
        return date.today().strftime('%Y-%m-%d')

    def _batch_fetch_rps(self, codes: list[str], trade_date: str) -> dict:
        CHUNK = 200
        rps_map = {}
        for i in range(0, len(codes), CHUNK):
            chunk = codes[i:i + CHUNK]
            ph = ','.join(['%s'] * len(chunk))
            rows = execute_query(
                f'SELECT stock_code, rps_20, rps_120, rps_250 '
                f'FROM trade_stock_rps WHERE stock_code IN ({ph}) AND trade_date = %s',
                tuple(chunk) + (trade_date,), env=_DB_ENV,
            )
            for r in rows:
                rps_map[r['stock_code']] = r
        return rps_map

    def _batch_fetch_price(self, codes: list[str], trade_date: str) -> dict:
        CHUNK = 200
        price_map = {}
        for i in range(0, len(codes), CHUNK):
            chunk = codes[i:i + CHUNK]
            ph = ','.join(['%s'] * len(chunk))
            rows = execute_query(
                f'SELECT stock_code, close_price '
                f'FROM trade_stock_daily WHERE stock_code IN ({ph}) AND trade_date = %s',
                tuple(chunk) + (trade_date,), env=_DB_ENV,
            )
            for r in rows:
                price_map[r['stock_code']] = r.get('close_price')
        return price_map

    # ------------------------------------------------------------------
    # Phase 3: LLM review
    # ------------------------------------------------------------------

    async def _review_stocks(self, query: str, candidates: list[dict], max_results: int) -> list[dict]:
        """LLM reviews DB results for relevance. Processes in batches."""
        BATCH_SIZE = 50
        all_selected = []

        for i in range(0, len(candidates), BATCH_SIZE):
            batch = candidates[i:i + BATCH_SIZE]
            selected = await self._review_batch(query, batch)
            all_selected.extend(selected)
            if len(all_selected) >= max_results:
                break

        return all_selected[:max_results]

    async def _review_batch(self, query: str, batch: list[dict]) -> list[dict]:
        """Review a single batch of candidates."""
        # Build stock list text for LLM - give more main_business context
        stock_lines = []
        for s in batch:
            mb = (s.get('main_business') or '')[:300]
            stock_lines.append(
                f"- {s['stock_code']} {s['stock_name']} [{s.get('industry', '')}] 主营: {mb}"
            )
        stock_list_text = '\n'.join(stock_lines)

        try:
            raw = await llm_call_with_retry(
                self._llm_factory.call,
                prompt=REVIEW_USER.format(
                    query=query,
                    total=len(batch),
                    stock_list=stock_list_text,
                ),
                system_prompt=REVIEW_SYSTEM,
                validate_json=False,
                timeout_sec=60.0,
                temperature=0.1,
                max_tokens=4096,
            )
            result = json.loads(self._extract_json(raw))
            selected = result.get('selected', [])
        except Exception as e:
            logger.warning('[SmartSearch] review batch failed: %s, returning all', e)
            # Fallback: return all with medium relevance
            selected = [
                {'stock_code': s['stock_code'], 'stock_name': s['stock_name'],
                 'relevance': 'medium', 'reason': ''}
                for s in batch
            ]

        # Enrich selected stocks with DB data (price, RPS, industry)
        batch_map = {s['stock_code']: s for s in batch}
        enriched = []
        for s in selected:
            code = s.get('stock_code', '')
            db_data = batch_map.get(code, {})
            enriched.append({
                'stock_code': code,
                'stock_name': s.get('stock_name', db_data.get('stock_name', '')),
                'relevance': s.get('relevance', 'medium'),
                'reason': s.get('reason', ''),
                'industry': db_data.get('industry', ''),
                'province': db_data.get('province', ''),
                'close': db_data.get('close'),
                'rps_250': db_data.get('rps_250'),
                'rps_120': db_data.get('rps_120'),
                'rps_20': db_data.get('rps_20'),
                'main_business_short': (db_data.get('main_business') or '')[:80],
            })

        return enriched

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from LLM response (handles markdown fences)."""
        # Try to find JSON in markdown code blocks
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # Try to find raw JSON object or array
        m = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if m:
            return m.group(1).strip()
        return text.strip()
