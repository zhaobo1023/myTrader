# -*- coding: utf-8 -*-
"""
Theme Pool Router - thematic stock selection endpoints

Prefix: /api/theme-pool
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.middleware.auth import get_current_user, get_optional_user
from api.models.user import User
from api.models.theme_pool import ThemePool, ThemePoolStock
from api.schemas.theme_pool import (
    ThemeCreateRequest, ThemeUpdateRequest, ThemeStatusRequest,
    ThemeResponse, ThemeListResponse,
    StockAddRequest, StockBatchAddRequest, StockResponse, StockListResponse,
    HumanStatusRequest, NoteUpdateRequest, ReasonUpdateRequest,
    VoteRequest, VoteResponse,
)
from api.services import theme_pool_service as svc

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/theme-pool', tags=['theme-pool'])


async def _get_user_or_dev(
    user: User = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Return authenticated user, or find/create a dev user when no token."""
    if user is not None:
        return user
    from sqlalchemy import select as sa_select
    result = await db.execute(sa_select(User).order_by(User.id).limit(1))
    dev_user = result.scalar_one_or_none()
    if dev_user:
        return dev_user
    # create a minimal dev user
    dev_user = User(email='dev@local', hashed_password='none', is_active=True)
    db.add(dev_user)
    await db.flush()
    await db.refresh(dev_user)
    return dev_user


# ==================================================================
# Theme CRUD
# ==================================================================

@router.post('/themes', response_model=ThemeResponse, status_code=status.HTTP_201_CREATED)
async def create_theme(
    req: ThemeCreateRequest,
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """Create a new theme pool."""
    theme = await svc.create_theme(db, current_user.id, req.name, req.description)
    return ThemeResponse(
        id=theme.id,
        name=theme.name,
        description=theme.description,
        status=theme.status.value if hasattr(theme.status, 'value') else theme.status,
        created_by=theme.created_by,
        creator_email=current_user.email,
        stock_count=0,
        created_at=theme.created_at,
        updated_at=theme.updated_at,
    )


@router.get('/themes', response_model=ThemeListResponse)
async def list_themes(
    status_filter: str = Query(None, alias='status', description='draft/active/archived'),
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """List all theme pools."""
    themes = await svc.list_themes(db, status_filter)
    return ThemeListResponse(
        items=[ThemeResponse(**t) for t in themes],
        total=len(themes),
    )


@router.get('/themes/{theme_id}', response_model=ThemeResponse)
async def get_theme(
    theme_id: int,
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """Get theme pool detail."""
    theme = await svc.get_theme(db, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail='Theme not found')
    creator = await db.get(User, theme.created_by)
    # count stocks
    from sqlalchemy import select, func
    from api.models.theme_pool import ThemePoolStock
    result = await db.execute(
        select(func.count(ThemePoolStock.id)).where(ThemePoolStock.theme_id == theme_id)
    )
    stock_count = result.scalar() or 0
    return ThemeResponse(
        id=theme.id,
        name=theme.name,
        description=theme.description,
        status=theme.status.value if hasattr(theme.status, 'value') else theme.status,
        created_by=theme.created_by,
        creator_email=creator.email if creator else None,
        stock_count=stock_count,
        created_at=theme.created_at,
        updated_at=theme.updated_at,
    )


@router.put('/themes/{theme_id}', response_model=ThemeResponse)
async def update_theme(
    theme_id: int,
    req: ThemeUpdateRequest,
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """Update theme name/description. Only creator can update."""
    theme = await svc.get_theme(db, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail='Theme not found')
    if theme.created_by != current_user.id:
        raise HTTPException(status_code=403, detail='Only the creator can update this theme')
    theme = await svc.update_theme(db, theme, req.name, req.description)
    return ThemeResponse(
        id=theme.id,
        name=theme.name,
        description=theme.description,
        status=theme.status.value if hasattr(theme.status, 'value') else theme.status,
        created_by=theme.created_by,
        creator_email=current_user.email,
        stock_count=0,
        created_at=theme.created_at,
        updated_at=theme.updated_at,
    )


@router.patch('/themes/{theme_id}/status', response_model=ThemeResponse)
async def change_theme_status(
    theme_id: int,
    req: ThemeStatusRequest,
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """Change theme status. Only creator can change status."""
    theme = await svc.get_theme(db, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail='Theme not found')
    if theme.created_by != current_user.id:
        raise HTTPException(status_code=403, detail='Only the creator can change status')
    try:
        theme = await svc.transition_status(db, theme, req.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ThemeResponse(
        id=theme.id,
        name=theme.name,
        description=theme.description,
        status=theme.status.value if hasattr(theme.status, 'value') else theme.status,
        created_by=theme.created_by,
        creator_email=current_user.email,
        stock_count=0,
        created_at=theme.created_at,
        updated_at=theme.updated_at,
    )


@router.delete('/themes/{theme_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_theme(
    theme_id: int,
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """Delete a draft theme. Only creator can delete."""
    theme = await svc.get_theme(db, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail='Theme not found')
    if theme.created_by != current_user.id:
        raise HTTPException(status_code=403, detail='Only the creator can delete this theme')
    try:
        await svc.delete_theme(db, theme)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================================================================
# Stock management
# ==================================================================

@router.post('/themes/{theme_id}/stocks', response_model=StockResponse, status_code=status.HTTP_201_CREATED)
async def add_stock(
    theme_id: int,
    req: StockAddRequest,
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """Add a stock to the theme pool. Any authenticated user can add."""
    theme = await svc.get_theme(db, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail='Theme not found')
    try:
        stock = await svc.add_stock(
            db, theme_id, current_user.id,
            req.stock_code, req.stock_name, req.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return StockResponse(
        id=stock.id,
        theme_id=stock.theme_id,
        stock_code=stock.stock_code,
        stock_name=stock.stock_name,
        recommended_by=stock.recommended_by,
        recommender_email=current_user.email,
        reason=stock.reason,
        entry_price=stock.entry_price,
        entry_date=stock.entry_date,
        human_status=stock.human_status if isinstance(stock.human_status, str) else stock.human_status.value,
        note=stock.note,
        added_at=stock.added_at,
    )


@router.post('/themes/{theme_id}/stocks/batch', response_model=StockListResponse, status_code=status.HTTP_201_CREATED)
async def batch_add_stocks(
    theme_id: int,
    req: StockBatchAddRequest,
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """Batch add stocks to the theme pool."""
    theme = await svc.get_theme(db, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail='Theme not found')
    added = []
    for s in req.stocks:
        try:
            stock = await svc.add_stock(
                db, theme_id, current_user.id,
                s.stock_code, s.stock_name, s.reason,
            )
            added.append(StockResponse(
                id=stock.id,
                theme_id=stock.theme_id,
                stock_code=stock.stock_code,
                stock_name=stock.stock_name,
                recommended_by=stock.recommended_by,
                recommender_email=current_user.email,
                reason=stock.reason,
                entry_price=stock.entry_price,
                entry_date=stock.entry_date,
                human_status=stock.human_status if isinstance(stock.human_status, str) else stock.human_status.value,
                note=stock.note,
                added_at=stock.added_at,
            ))
        except ValueError:
            # skip duplicates
            continue
    return StockListResponse(items=added, total=len(added))


@router.get('/themes/{theme_id}/stocks', response_model=StockListResponse)
async def list_stocks(
    theme_id: int,
    human_status: str = Query(None, description='normal/focused/watching/excluded'),
    sort_by: str = Query('total_score', description='total_score/added_at/return_5d/return_20d/rps_20'),
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """List all stocks in a theme pool with latest scores and vote counts."""
    theme = await svc.get_theme(db, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail='Theme not found')
    items = await svc.list_stocks(db, theme_id, current_user.id, human_status, sort_by)
    return StockListResponse(
        items=[StockResponse(**item) for item in items],
        total=len(items),
    )


@router.get('/themes/{theme_id}/price-history')
async def get_price_history(
    theme_id: int,
    days: int = Query(60, ge=5, le=250, description='Number of trading days'),
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """Get daily OHLCV prices for all stocks in a theme."""
    theme = await svc.get_theme(db, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail='Theme not found')
    history = await svc.get_price_history(db, theme_id, days)
    return {'stocks': history}


@router.delete('/themes/{theme_id}/stocks/{stock_code}', status_code=status.HTTP_204_NO_CONTENT)
async def remove_stock(
    theme_id: int,
    stock_code: str,
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """Remove a stock from the theme pool."""
    removed = await svc.remove_stock(db, theme_id, stock_code)
    if not removed:
        raise HTTPException(status_code=404, detail=f'{stock_code} not in this theme')


# ==================================================================
# Human status & notes
# ==================================================================

@router.patch('/stocks/{stock_id}/status')
async def update_human_status(
    stock_id: int,
    req: HumanStatusRequest,
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """Update human-assigned status for a stock."""
    try:
        stock = await svc.update_human_status(db, stock_id, req.human_status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not stock:
        raise HTTPException(status_code=404, detail='Stock not found')
    return {'id': stock_id, 'human_status': req.human_status}


@router.patch('/stocks/{stock_id}/note')
async def update_note(
    stock_id: int,
    req: NoteUpdateRequest,
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """Update note for a stock."""
    stock = await svc.update_note(db, stock_id, req.note)
    if not stock:
        raise HTTPException(status_code=404, detail='Stock not found')
    return {'id': stock_id, 'note': req.note}


@router.patch('/stocks/{stock_id}/reason')
async def update_reason(
    stock_id: int,
    req: ReasonUpdateRequest,
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """Update recommendation reason for a stock."""
    stock = await svc.update_reason(db, stock_id, req.reason)
    if not stock:
        raise HTTPException(status_code=404, detail='Stock not found')
    return {'id': stock_id, 'reason': req.reason}


# ==================================================================
# Voting
# ==================================================================

@router.post('/stocks/{stock_id}/vote', response_model=VoteResponse)
async def vote_stock(
    stock_id: int,
    req: VoteRequest,
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """Vote on a stock (1=up, -1=down). Re-voting changes existing vote. One vote per user."""
    stock = await db.get(ThemePoolStock, stock_id)
    if not stock:
        raise HTTPException(status_code=404, detail='Stock not found')
    try:
        result = await svc.vote_stock(db, stock_id, current_user.id, req.vote)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return VoteResponse(**result)


@router.post('/themes/{theme_id}/score')
async def trigger_score(
    theme_id: int,
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger scoring for all stocks in a theme."""
    theme = await svc.get_theme(db, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail='Theme not found')

    import threading
    from api.tasks.theme_pool_score import run_theme_pool_score_for_theme

    def _run():
        try:
            run_theme_pool_score_for_theme(theme_id, env='online')
        except Exception as e:
            logger.error('[THEME_POOL] manual score failed theme=%d: %s', theme_id, str(e))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {'message': f'Scoring started for theme {theme_id}', 'theme_id': theme_id}


@router.delete('/stocks/{stock_id}/vote', response_model=VoteResponse)
async def remove_vote(
    stock_id: int,
    current_user: User = Depends(_get_user_or_dev),
    db: AsyncSession = Depends(get_db),
):
    """Remove current user's vote on a stock."""
    stock = await db.get(ThemePoolStock, stock_id)
    if not stock:
        raise HTTPException(status_code=404, detail='Stock not found')
    result = await svc.remove_vote(db, stock_id, current_user.id)
    return VoteResponse(**result)


# ---------------------------------------------------------------------------
# LLM-driven theme creation (SSE streaming)
# ---------------------------------------------------------------------------

class LLMThemeCreateRequest(BaseModel):
    theme_name: str
    description: str = ''
    max_candidates: int = 40


@router.post('/llm/create')
async def llm_create_theme(req: LLMThemeCreateRequest):
    """
    SSE streaming endpoint: LLM-driven theme stock selection.

    The client should read this as a Server-Sent Events stream using fetch +
    ReadableStream (not EventSource, since we use POST).

    Event types (in order):
      start            - processing started
      phase            - phase transition message
      concept_mapping  - LLM-generated concept keywords
      boards_matched   - concept boards found in Eastmoney
      fetching         - per-board fetch progress (status: fetching | done)
      raw_pool         - summary after code validation
      filtering_start  - LLM filtering begins
      filter_done      - LLM filtering complete
      candidate_list   - final candidate stock list (main payload)
      done             - stream complete
      error            - fatal error

    candidate_list.stocks item:
      stock_code   str          "000001.SZ"
      stock_name   str          "平安银行"
      source       str          "akshare" | "llm"
      boards       list[str]    concept boards (akshare only)
      relevance    str          "high" | "medium"
      reason       str          LLM-generated one-line rationale
    """
    from api.services.theme_llm_service import ThemeCreateSkill
    from api.dependencies import get_redis

    redis = await get_redis()
    skill = ThemeCreateSkill(redis=redis)

    async def event_gen():
        async for event in skill.stream(
            theme_name=req.theme_name,
            description=req.description,
            max_candidates=req.max_candidates,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


# ---------------------------------------------------------------------------
# Unified LLM skill stream endpoint (M2-T6)
# ---------------------------------------------------------------------------

class LLMStreamRequest(BaseModel):
    skill_id: str
    params: dict = {}


@router.post('/llm/stream')
async def llm_skill_stream(req: LLMStreamRequest):
    """
    Unified SSE streaming endpoint that routes to any registered LLM skill.

    Request body:
      skill_id  str   e.g. "theme-review"
      params    dict  skill-specific parameters, e.g. {"theme_id": 1, "theme_name": "电网设备"}

    Returns Server-Sent Events stream. Each event is a JSON object with a "type" field.
    Last event has type "done" (success) or "error" (failure).
    """
    from api.services.llm_skills.registry import get_skill
    # ensure skills are registered
    import api.services.llm_skills.theme_review  # noqa: F401

    skill = get_skill(req.skill_id)
    if skill is None:
        async def _error_gen():
            yield f"data: {json.dumps({'type': 'error', 'message': f'Unknown skill: {req.skill_id}'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(
            _error_gen(),
            media_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
        )

    async def event_gen():
        async for event in skill.stream(**req.params):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


@router.get('/llm/skills')
async def list_llm_skills():
    """List all registered LLM skills."""
    from api.services.llm_skills.registry import list_skills
    import api.services.llm_skills.theme_review  # noqa: F401
    return {'skills': list_skills()}
