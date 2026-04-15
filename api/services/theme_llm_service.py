# -*- coding: utf-8 -*-
"""
LLM-driven theme creation service.

Components:
  - AKShareConceptFetcher  : wraps AKShare concept board APIs as async
  - StockCodeValidator     : normalizes raw codes and validates against DB
  - ThemeCreateSkill       : async generator skill, yields SSE event dicts

Usage (from router):
    skill = ThemeCreateSkill()
    async for event in skill.stream(theme_name="电网设备"):
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
"""
import asyncio
import json
import logging
import re

from config.db import execute_query
from api.services.llm_client_factory import get_llm_client, llm_call_with_retry
from api.services.theme_llm_prompts import (
    CONCEPT_MAPPING_SYSTEM, CONCEPT_MAPPING_USER,
    STOCK_FILTER_SYSTEM, STOCK_FILTER_USER,
    LLM_SUPPLEMENT_SYSTEM, LLM_SUPPLEMENT_USER,
)

logger = logging.getLogger('myTrader.theme_llm')


# ---------------------------------------------------------------------------
# AKShare concept board fetcher
# ---------------------------------------------------------------------------

class AKShareConceptFetcher:
    """Fetches Eastmoney concept board data via AKShare (sync wrapped as async)."""

    async def get_all_boards(self) -> list[str]:
        """Return all concept board names from Eastmoney."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_get_all_boards)

    def _sync_get_all_boards(self) -> list[str]:
        try:
            import akshare as ak
            df = ak.stock_board_concept_name_em()
            return df['板块名称'].tolist()
        except Exception as e:
            logger.warning('[AKShare] get_all_boards failed: %s', e)
            return []

    async def get_board_stocks(self, board_name: str) -> list[dict]:
        """Return stocks in a given concept board."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_get_board_stocks, board_name)

    def _sync_get_board_stocks(self, board_name: str) -> list[dict]:
        import time
        time.sleep(0.3)  # rate limit
        try:
            import akshare as ak
            df = ak.stock_board_concept_cons_em(symbol=board_name)
            return [
                {'code': str(row['代码']).zfill(6), 'name': str(row['名称'])}
                for _, row in df.iterrows()
            ]
        except Exception as e:
            logger.warning('[AKShare] get_board_stocks(%s) failed: %s', board_name, e)
            return []


# ---------------------------------------------------------------------------
# Stock code validator
# ---------------------------------------------------------------------------

class StockCodeValidator:
    """Normalizes raw stock codes and validates existence in trade_stock_basic."""

    def validate_batch(self, raw_codes: list[str]) -> dict[str, str]:
        """
        Normalize codes and query DB.
        Returns {normalized_code: stock_name} for valid codes only.
        """
        if not raw_codes:
            return {}
        normalized = list({self._normalize(c) for c in raw_codes})
        placeholders = ','.join(['%s'] * len(normalized))
        try:
            rows = execute_query(
                f"SELECT stock_code, stock_name FROM trade_stock_basic "
                f"WHERE stock_code IN ({placeholders})",
                tuple(normalized),
                env='online',
            )
            return {r['stock_code']: r['stock_name'] for r in rows}
        except Exception as e:
            logger.error('[Validator] DB query failed: %s', e)
            return {}

    @staticmethod
    def _normalize(code: str) -> str:
        """Convert "000001" -> "000001.SZ", "600519" -> "600519.SH", etc."""
        code = re.sub(r'[^0-9]', '', code).zfill(6)
        if code.startswith(('0', '3')):
            return f"{code}.SZ"
        elif code.startswith(('6', '9')):
            return f"{code}.SH"
        elif code.startswith(('4', '8')):
            return f"{code}.BJ"
        return f"{code}.SZ"


# ---------------------------------------------------------------------------
# Theme create skill
# ---------------------------------------------------------------------------

class ThemeCreateSkill:
    """
    P0 LLM skill: given a theme name, produce a candidate stock list via:
      1. LLM -> Eastmoney concept keywords + SW industry keywords
      2. DB query -> stock_concept_map (primary) + trade_stock_basic SW industry (fallback)
         If DB is empty, fall back to live AKShare fetch
      3. DB code validation
      4. LLM filter + score
      5. LLM supplement (subcategory-aware, finds unlisted niche leaders)
    """

    def __init__(self, model_alias: str | None = None, redis=None):
        from api.services.akshare_cache import CachedAKShareFetcher
        inner = AKShareConceptFetcher()
        self._fetcher = CachedAKShareFetcher(inner=inner, redis=redis) if redis else inner
        self._validator = StockCodeValidator()
        self._llm_factory = get_llm_client(model_alias)

    async def stream(self, theme_name: str, description: str = '', max_candidates: int = 40):
        """Async generator: yields SSE event dicts."""
        try:
            async for event in self._run(theme_name, description, max_candidates):
                yield event
        except Exception as e:
            logger.exception('[ThemeCreateSkill] unexpected error for theme=%s', theme_name)
            yield {'type': 'error', 'message': str(e)}

    async def _run(self, theme_name: str, description: str, max_candidates: int):
        yield {'type': 'start', 'message': f'正在分析主题「{theme_name}」...'}

        # --- Phase 1: LLM concept mapping ---
        yield {'type': 'phase', 'phase': 'concept_mapping', 'message': '正在让 AI 扩展相关概念板块...'}
        concepts = await self._map_concepts(theme_name)
        yield {'type': 'concept_mapping', 'concepts': concepts}

        # --- Phase 2: Query DB concept map (primary) + SW industry (fallback) ---
        yield {'type': 'phase', 'phase': 'fetching', 'message': '正在从数据库拉取概念成分股...'}
        db_stocks, matched_boards, used_akshare = await self._fetch_candidates_from_db(
            theme_name, concepts
        )

        if used_akshare:
            yield {
                'type': 'boards_matched',
                'boards': matched_boards,
                'total': len(matched_boards),
                'source': 'akshare_live',
                'note': 'DB concept map empty, fell back to live AKShare fetch',
            }
        else:
            yield {
                'type': 'boards_matched',
                'boards': matched_boards,
                'total': len(matched_boards),
                'source': 'db',
            }

        valid_stocks = db_stocks
        yield {
            'type': 'raw_pool',
            'total': len(valid_stocks),
            'valid': len(valid_stocks),
            'boards_hit': len(matched_boards),
        }

        # --- Phase 3: LLM filter ---
        yield {'type': 'filtering_start', 'total_candidates': len(valid_stocks)}
        filtered = await self._filter_stocks(theme_name, valid_stocks)
        yield {'type': 'filter_done', 'selected': len(filtered)}

        # --- Phase 4: LLM supplement (subcategory-aware) ---
        existing_codes = [s['stock_code'] for s in filtered]
        supplements_raw = await self._supplement_stocks(theme_name, existing_codes)
        supp_valid_map = self._validator.validate_batch(
            [re.sub(r'[^0-9]', '', s['stock_code']) for s in supplements_raw]
        )
        supplements = []
        for s in supplements_raw:
            norm = StockCodeValidator._normalize(s['stock_code'])
            if norm in supp_valid_map and norm not in existing_codes:
                supplements.append({
                    'stock_code': norm,
                    'stock_name': supp_valid_map[norm],
                    'source': 'llm',
                    'boards': [],
                    'subcategory': s.get('subcategory', ''),
                    'relevance': 'medium',
                    'reason': s.get('reason', ''),
                })

        # --- Phase 5: Final candidate list ---
        final_stocks = (filtered + supplements)[:max_candidates]
        yield {
            'type': 'candidate_list',
            'stocks': final_stocks,
            'total': len(final_stocks),
            'akshare_count': len(filtered),
            'llm_supplement_count': len(supplements),
        }
        yield {
            'type': 'done',
            'summary': f'共找到 {len(final_stocks)} 只候选股票（概念库 {len(filtered)} 只，AI 补充 {len(supplements)} 只）',
        }

    async def _fetch_candidates_from_db(
        self, theme_name: str, concepts: list[str]
    ) -> tuple[list[dict], list[str], bool]:
        """
        Primary: query stock_concept_map by concept keywords.
        Fallback A: query trade_stock_basic by SW industry keywords if DB has too few results.
        Fallback B: live AKShare if DB concept map is completely empty.

        Returns (valid_stocks, matched_boards, used_akshare_flag).
        """
        loop = asyncio.get_event_loop()

        # Try DB concept map
        db_result = await loop.run_in_executor(
            None, self._sync_query_concept_db, concepts
        )
        raw_stocks, matched_boards = db_result

        if raw_stocks:
            # Also supplement with SW industry match from trade_stock_basic
            industry_stocks = await loop.run_in_executor(
                None, self._sync_query_sw_industry, concepts
            )
            # Merge: add industry stocks not already in raw_stocks
            existing_codes = {s['stock_code'] for s in raw_stocks}
            for s in industry_stocks:
                if s['stock_code'] not in existing_codes:
                    raw_stocks.append(s)
                    existing_codes.add(s['stock_code'])

            return raw_stocks, matched_boards, False

        # DB concept map is empty -> fall back to live AKShare
        logger.warning(
            '[ThemeCreateSkill] stock_concept_map has no data for theme=%s, falling back to AKShare',
            theme_name,
        )
        all_boards = await self._fetcher.get_all_boards()
        matched_boards = self._fuzzy_match_boards(concepts, all_boards)
        raw_stocks_dict: dict[str, dict] = {}
        for board in matched_boards:
            stocks = await self._fetcher.get_board_stocks(board)
            for s in stocks:
                code = s['code']
                if code not in raw_stocks_dict:
                    raw_stocks_dict[code] = {'name': s['name'], 'boards': []}
                if board not in raw_stocks_dict[code]['boards']:
                    raw_stocks_dict[code]['boards'].append(board)

        valid_map = self._validator.validate_batch(list(raw_stocks_dict.keys()))
        valid_stocks = []
        for raw_code, info in raw_stocks_dict.items():
            norm = StockCodeValidator._normalize(raw_code)
            if norm in valid_map:
                valid_stocks.append({
                    'stock_code': norm,
                    'stock_name': valid_map[norm],
                    'boards': info['boards'],
                    'source': 'akshare',
                })
        return valid_stocks, matched_boards, True

    def _sync_query_concept_db(self, concepts: list[str]) -> tuple[list[dict], list[str]]:
        """
        Query stock_concept_map by concept keywords.
        Uses bidirectional matching: both "concept_name LIKE %keyword%"
        and "keyword LIKE %concept_name%" to handle naming differences
        between LLM-generated concepts and actual DB concept names.
        Returns (stock_list, matched_board_names).
        """
        if not concepts:
            return [], []
        try:
            # First try direct substring match: concept_name LIKE %keyword%
            placeholders = ' OR '.join(['concept_name LIKE %s'] * len(concepts))
            params = tuple(f'%{c}%' for c in concepts)
            rows = execute_query(
                f"""
                SELECT DISTINCT m.stock_code, m.stock_name, m.concept_name
                FROM stock_concept_map m
                WHERE {placeholders}
                ORDER BY m.stock_code
                """,
                params,
                env='online',
            )

            # If no results, try reverse match: fetch all distinct concept names
            # and match by checking if any keyword is a substring of the concept name
            if not rows:
                all_concepts = execute_query(
                    "SELECT DISTINCT concept_name FROM stock_concept_map",
                    env='online',
                )
                matched_names = []
                for ac in all_concepts:
                    db_name = ac['concept_name']
                    for kw in concepts:
                        # keyword contains concept_name OR concept_name contains keyword
                        if kw in db_name or db_name in kw:
                            matched_names.append(db_name)
                            break
                if matched_names:
                    ph2 = ' OR '.join(['concept_name = %s'] * len(matched_names))
                    rows = execute_query(
                        f"""
                        SELECT DISTINCT m.stock_code, m.stock_name, m.concept_name
                        FROM stock_concept_map m
                        WHERE {ph2}
                        ORDER BY m.stock_code
                        """,
                        tuple(matched_names),
                        env='online',
                    )
            if not rows:
                return [], []

            # Group by stock_code
            stock_map: dict[str, dict] = {}
            board_set: set[str] = set()
            for r in rows:
                code = r['stock_code']
                board = r['concept_name']
                board_set.add(board)
                if code not in stock_map:
                    stock_map[code] = {
                        'stock_code': code,
                        'stock_name': r['stock_name'],
                        'boards': [],
                        'source': 'db',
                    }
                if board not in stock_map[code]['boards']:
                    stock_map[code]['boards'].append(board)

            return list(stock_map.values()), sorted(board_set)
        except Exception as e:
            logger.warning('[ThemeCreateSkill] concept DB query failed: %s', e)
            return [], []

    def _sync_query_sw_industry(self, concepts: list[str]) -> list[dict]:
        """
        Supplement from trade_stock_basic by SW industry name keyword match.
        Returns list of {stock_code, stock_name, boards, source}.
        """
        if not concepts:
            return []
        try:
            placeholders = ' OR '.join(['industry LIKE %s'] * len(concepts))
            params = tuple(f'%{c}%' for c in concepts)
            rows = execute_query(
                f"""
                SELECT stock_code, stock_name, industry
                FROM trade_stock_basic
                WHERE {placeholders}
                  AND stock_code IS NOT NULL
                LIMIT 500
                """,
                params,
                env='online',
            )
            return [
                {
                    'stock_code': r['stock_code'],
                    'stock_name': r['stock_name'],
                    'boards': [r['industry']],
                    'source': 'sw_industry',
                }
                for r in rows
                if r.get('stock_code')
            ]
        except Exception as e:
            logger.warning('[ThemeCreateSkill] SW industry query failed: %s', e)
            return []

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    async def _llm_call(self, prompt: str, system_prompt: str, temperature: float = 0.3,
                        max_tokens: int = 2048) -> str:
        """Async LLM call via factory, with 30s timeout (no JSON validation at this layer)."""
        return await llm_call_with_retry(
            self._llm_factory.call,
            validate_json=False,
            timeout_sec=30.0,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract first JSON object or array from LLM output text."""
        # strip markdown code fences
        text = re.sub(r'```(?:json)?\s*', '', text).strip()
        # find the first [ or { by position (whichever appears first)
        idx_bracket = text.find('[')
        idx_brace = text.find('{')
        candidates = [(idx, '[', ']') for idx in [idx_bracket] if idx != -1] + \
                     [(idx, '{', '}') for idx in [idx_brace] if idx != -1]
        if not candidates:
            return text
        start_idx, start_char, end_char = min(candidates, key=lambda x: x[0])
        # find matching end using depth tracking
        depth = 0
        for i, ch in enumerate(text[start_idx:], start=start_idx):
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
            if depth == 0:
                return text[start_idx:i + 1]
        return text

    async def _map_concepts(self, theme_name: str) -> list[str]:
        """Phase 1: LLM call -> concept board keyword list."""
        try:
            resp = await self._llm_call(
                prompt=CONCEPT_MAPPING_USER.format(theme_name=theme_name),
                system_prompt=CONCEPT_MAPPING_SYSTEM,
                temperature=0.3,
                max_tokens=256,
            )
            data = json.loads(self._extract_json(resp))
            if isinstance(data, list):
                return [str(x) for x in data if x]
        except Exception as e:
            logger.warning('[ThemeCreateSkill] concept mapping failed: %s | resp=%s', e, resp if 'resp' in dir() else '')
        return [theme_name]  # fallback: use theme name directly

    @staticmethod
    def _fuzzy_match_boards(concepts: list[str], all_boards: list[str]) -> list[str]:
        """Match concept keywords against all board names (substring match)."""
        matched = []
        for board in all_boards:
            for concept in concepts:
                if concept in board or board in concept:
                    if board not in matched:
                        matched.append(board)
                    break
        return matched[:8]  # cap at 8 boards to avoid excessive requests

    async def _filter_stocks(self, theme_name: str, stocks: list[dict]) -> list[dict]:
        """Phase 4: LLM call -> filter and score candidate stocks."""
        if not stocks:
            return []

        stock_list_text = '\n'.join(
            f"{s['stock_code']} {s['stock_name']} (板块: {', '.join(s['boards'])})"
            for s in stocks[:150]  # token limit
        )
        try:
            resp = await self._llm_call(
                prompt=STOCK_FILTER_USER.format(
                    theme_name=theme_name,
                    total=len(stocks[:150]),
                    stock_list=stock_list_text,
                ),
                system_prompt=STOCK_FILTER_SYSTEM.format(theme_name=theme_name),
                temperature=0.2,
                max_tokens=4096,
            )
            data = json.loads(self._extract_json(resp))
            selected = data.get('selected', [])
            result = []
            for item in selected:
                code = item.get('stock_code', '')
                if not code:
                    continue
                # find original boards info
                orig = next((s for s in stocks if s['stock_code'] == code), None)
                result.append({
                    'stock_code': code,
                    'stock_name': item.get('stock_name', orig['stock_name'] if orig else ''),
                    'source': 'akshare',
                    'boards': orig['boards'] if orig else [],
                    'relevance': item.get('relevance', 'medium'),
                    'reason': item.get('reason', ''),
                })
            return result
        except Exception as e:
            logger.warning('[ThemeCreateSkill] filter failed: %s', e)
            # fallback: return top-50 unfiltered
            return [
                {**s, 'relevance': 'medium', 'reason': '来自东财概念板块'}
                for s in stocks[:50]
            ]

    async def _supplement_stocks(self, theme_name: str, existing_codes: list[str]) -> list[dict]:
        """Phase 5: LLM call -> supplement stocks not in AKShare."""
        existing_str = ', '.join(existing_codes[:30])
        try:
            resp = await self._llm_call(
                prompt=LLM_SUPPLEMENT_USER.format(
                    theme_name=theme_name,
                    existing_codes=existing_str,
                ),
                system_prompt=LLM_SUPPLEMENT_SYSTEM.format(theme_name=theme_name),
                temperature=0.4,
                max_tokens=1024,
            )
            data = json.loads(self._extract_json(resp))
            return data.get('supplements', [])
        except Exception as e:
            logger.warning('[ThemeCreateSkill] supplement failed: %s', e)
            return []
