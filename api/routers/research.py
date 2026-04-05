# -*- coding: utf-8 -*-
"""
Research router - five-section investment research endpoints.

All research module imports are lazy (inside endpoint functions) to avoid
circular imports and missing-dependency errors at startup.

DB reads use config.db.execute_query (sync) because research modules
already depend on it directly.
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from api.middleware.auth import get_current_user
from api.models.user import User

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/research', tags=['research'])


# ============================================================
# Request models
# ============================================================

class CreateEventRequest(BaseModel):
    code: str
    event_date: str
    event_text: str
    direction: str
    magnitude: str
    category: str
    source: Optional[str] = None


class AddWatchlistRequest(BaseModel):
    code: str
    name: Optional[str] = None
    tier: str = 'watch'
    industry: Optional[str] = None
    thesis: Optional[str] = None


class UpdateThesisRequest(BaseModel):
    thesis: str


class VerifyEventRequest(BaseModel):
    result: str


# ============================================================
# Fundamental endpoints
# ============================================================

@router.get('/fundamental/{code}')
async def get_fundamental_snapshot(
    code: str,
    current_user: User = Depends(get_current_user),
):
    """Return the latest fundamental snapshot for a stock."""
    try:
        from config.db import execute_query
        sql = """
            SELECT code, snap_date, fundamental_score, pe_ttm, pe_quantile_5yr,
                   pb, pb_quantile_5yr, roe, revenue_yoy, profit_yoy,
                   fcf, net_cash, expected_return_2yr, valuation_json
            FROM fundamental_snapshots
            WHERE code = %s
            ORDER BY snap_date DESC
            LIMIT 1
        """
        rows = execute_query(sql, (code,))
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'No snapshot found for {code}',
            )
        row = rows[0]
        # Parse valuation_json if it came back as a string
        valuation_json = row.get('valuation_json') if isinstance(row, dict) else row[-1]
        if isinstance(valuation_json, str):
            try:
                valuation_json = json.loads(valuation_json)
            except Exception:
                pass

        if isinstance(row, dict):
            result = dict(row)
            result['valuation_json'] = valuation_json
        else:
            keys = ['code', 'snap_date', 'fundamental_score', 'pe_ttm', 'pe_quantile_5yr',
                    'pb', 'pb_quantile_5yr', 'roe', 'revenue_yoy', 'profit_yoy',
                    'fcf', 'net_cash', 'expected_return_2yr', 'valuation_json']
            result = dict(zip(keys, row))
            result['valuation_json'] = valuation_json

        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error('[research] get_fundamental_snapshot %s: %s', code, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post('/fundamental/{code}/refresh')
async def refresh_fundamental_snapshot(
    code: str,
    current_user: User = Depends(get_current_user),
):
    """Recompute and persist a fresh fundamental snapshot for a stock."""
    try:
        from research.fundamental.snapshot import FundamentalSnapshot
        snap = FundamentalSnapshot()
        row = snap.save(code)
        return {
            'message': f'Snapshot refreshed for {code}',
            'snap_date': row.get('snap_date'),
            'fundamental_score': row.get('fundamental_score'),
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error('[research] refresh_fundamental_snapshot %s: %s', code, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# ============================================================
# Valuation endpoint
# ============================================================

@router.get('/valuation/{code}')
async def get_valuation(
    code: str,
    dcf_growth1: float = Query(default=0.15),
    dcf_growth2: float = Query(default=0.08),
    current_user: User = Depends(get_current_user),
):
    """Run 8-method valuation for a stock."""
    try:
        from research.fundamental.valuation import FundamentalValuator
        v = FundamentalValuator()
        result = v.compute(code)
        return {
            'code': result.code,
            'current_market_cap_yi': result.current_market_cap_yi,
            'methods': result.methods,
            'notes': result.notes,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error('[research] get_valuation %s: %s', code, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# ============================================================
# Sentiment endpoints
# ============================================================

@router.get('/sentiment/{code}/events')
async def list_sentiment_events(
    code: str,
    days: int = Query(default=30),
    current_user: User = Depends(get_current_user),
):
    """List recent sentiment events for a stock."""
    try:
        from research.sentiment.event_tracker import SentimentEventTracker
        tracker = SentimentEventTracker()
        events = tracker.list_recent(code, days=days)
        return {'code': code, 'events': events}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error('[research] list_sentiment_events %s: %s', code, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post('/sentiment/events')
async def create_sentiment_event(
    body: CreateEventRequest,
    current_user: User = Depends(get_current_user),
):
    """Create a new sentiment event record."""
    try:
        from research.sentiment.event_tracker import SentimentEventTracker
        tracker = SentimentEventTracker()
        event_id = tracker.create(
            code=body.code,
            event_date=body.event_date,
            event_text=body.event_text,
            direction=body.direction,
            magnitude=body.magnitude,
            category=body.category,
            source=body.source,
        )
        return {'id': event_id, 'message': 'Event created'}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error('[research] create_sentiment_event: %s', exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.put('/sentiment/events/{event_id}/verify')
async def verify_sentiment_event(
    event_id: int,
    body: VerifyEventRequest,
    current_user: User = Depends(get_current_user),
):
    """Mark a sentiment event as verified."""
    try:
        from research.sentiment.event_tracker import SentimentEventTracker
        tracker = SentimentEventTracker()
        tracker.verify(event_id, body.result)
        return {'message': f'Event {event_id} verified'}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error('[research] verify_sentiment_event %s: %s', event_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# ============================================================
# Composite endpoints
# ============================================================

@router.get('/composite/{code}')
async def get_composite_score(
    code: str,
    current_user: User = Depends(get_current_user),
):
    """Return the latest composite score for a stock."""
    try:
        from config.db import execute_query
        sql = """
            SELECT code, score_date, composite_score, direction, signal_note,
                   score_technical, score_fund_flow, score_fundamental,
                   score_sentiment, score_capital_cycle
            FROM composite_scores
            WHERE code = %s
            ORDER BY score_date DESC
            LIMIT 1
        """
        rows = execute_query(sql, (code,))
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'No composite score found for {code}',
            )
        row = rows[0]
        if isinstance(row, dict):
            return dict(row)
        keys = ['code', 'score_date', 'composite_score', 'direction', 'signal_note',
                'score_technical', 'score_fund_flow', 'score_fundamental',
                'score_sentiment', 'score_capital_cycle']
        return dict(zip(keys, row))
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error('[research] get_composite_score %s: %s', code, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post('/composite/{code}/compute')
async def compute_composite_score(
    code: str,
    score_technical: int = Query(default=50, ge=0, le=100),
    score_fund_flow: int = Query(default=50, ge=0, le=100),
    score_sentiment: int = Query(default=50, ge=0, le=100),
    score_capital_cycle: int = Query(default=50, ge=0, le=100),
    capital_cycle_phase: int = Query(default=0, ge=0, le=5),
    current_user: User = Depends(get_current_user),
):
    """Compute and persist a composite five-section score for a stock."""
    try:
        from config.db import execute_query
        from research.composite.aggregator import CompositeAggregator, FiveSectionScores

        # Read latest fundamental_score and pe_quantile_5yr from fundamental_snapshots
        snap_sql = """
            SELECT fundamental_score, pe_quantile_5yr
            FROM fundamental_snapshots
            WHERE code = %s
            ORDER BY snap_date DESC
            LIMIT 1
        """
        snap_rows = execute_query(snap_sql, (code,))
        if snap_rows:
            snap_row = snap_rows[0]
            if isinstance(snap_row, dict):
                score_fundamental = int(snap_row.get('fundamental_score') or 50)
                pe_quantile = float(snap_row.get('pe_quantile_5yr') or 0.5)
            else:
                score_fundamental = int(snap_row[0] or 50)
                pe_quantile = float(snap_row[1] or 0.5)
        else:
            score_fundamental = 50
            pe_quantile = 0.5

        scores = FiveSectionScores(
            score_technical=score_technical,
            score_fund_flow=score_fund_flow,
            score_fundamental=score_fundamental,
            score_sentiment=score_sentiment,
            score_capital_cycle=score_capital_cycle,
            pe_quantile=pe_quantile,
            capital_cycle_phase=capital_cycle_phase,
        )

        agg_result = CompositeAggregator().aggregate(scores)

        # Persist to composite_scores
        from datetime import date
        today = date.today().strftime('%Y-%m-%d')
        insert_sql = """
            INSERT INTO composite_scores
                (code, score_date, composite_score, direction, signal_note,
                 score_technical, score_fund_flow, score_fundamental,
                 score_sentiment, score_capital_cycle)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                composite_score     = VALUES(composite_score),
                direction           = VALUES(direction),
                signal_note         = VALUES(signal_note),
                score_technical     = VALUES(score_technical),
                score_fund_flow     = VALUES(score_fund_flow),
                score_fundamental   = VALUES(score_fundamental),
                score_sentiment     = VALUES(score_sentiment),
                score_capital_cycle = VALUES(score_capital_cycle)
        """
        execute_query(insert_sql, (
            code,
            today,
            agg_result.composite_score,
            agg_result.direction,
            agg_result.signal_note,
            score_technical,
            score_fund_flow,
            score_fundamental,
            score_sentiment,
            score_capital_cycle,
        ))

        return {
            'code': code,
            'composite_score': agg_result.composite_score,
            'direction': agg_result.direction,
            'signal_note': agg_result.signal_note,
            'section_scores': {
                'technical': score_technical,
                'fund_flow': score_fund_flow,
                'fundamental': score_fundamental,
                'sentiment': score_sentiment,
                'capital_cycle': score_capital_cycle,
            },
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error('[research] compute_composite_score %s: %s', code, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# ============================================================
# Watchlist endpoints
# ============================================================

@router.get('/watchlist')
async def list_watchlist(
    tier: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
):
    """List active watchlist entries, optionally filtered by tier."""
    try:
        from research.watchlist.manager import WatchlistManager
        mgr = WatchlistManager()
        items = mgr.list_active(tier=tier)
        return {'watchlist': items}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error('[research] list_watchlist: %s', exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post('/watchlist')
async def add_to_watchlist(
    body: AddWatchlistRequest,
    current_user: User = Depends(get_current_user),
):
    """Add a stock to the watchlist."""
    try:
        from research.watchlist.manager import WatchlistManager
        mgr = WatchlistManager()
        mgr.add(
            code=body.code,
            name=body.name,
            tier=body.tier,
            industry=body.industry,
            thesis=body.thesis,
        )
        return {'message': f'{body.code} added to watchlist', 'code': body.code}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error('[research] add_to_watchlist: %s', exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.put('/watchlist/{code}/tier')
async def set_watchlist_tier(
    code: str,
    tier: str = Query(..., pattern='^(deep|standard|watch)$'),
    current_user: User = Depends(get_current_user),
):
    """Update the tier of a watchlist entry."""
    try:
        from research.watchlist.manager import WatchlistManager
        mgr = WatchlistManager()
        mgr.set_tier(code, tier)
        return {'message': f'{code} tier updated to {tier}'}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error('[research] set_watchlist_tier %s: %s', code, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.put('/watchlist/{code}/thesis')
async def update_watchlist_thesis(
    code: str,
    body: UpdateThesisRequest,
    current_user: User = Depends(get_current_user),
):
    """Update the investment thesis for a watchlist entry."""
    try:
        from research.watchlist.manager import WatchlistManager
        mgr = WatchlistManager()
        mgr.update_thesis(code, body.thesis)
        return {'message': f'{code} thesis updated'}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error('[research] update_watchlist_thesis %s: %s', code, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.delete('/watchlist/{code}')
async def remove_from_watchlist(
    code: str,
    current_user: User = Depends(get_current_user),
):
    """Remove a stock from the watchlist (soft delete)."""
    try:
        from research.watchlist.manager import WatchlistManager
        mgr = WatchlistManager()
        mgr.remove(code)
        return {'message': f'{code} removed from watchlist'}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error('[research] remove_from_watchlist %s: %s', code, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
