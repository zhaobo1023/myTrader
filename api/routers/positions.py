# -*- coding: utf-8 -*-
"""
Positions router - user portfolio positions CRUD
"""
import csv
import io
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import get_db
from api.models.user import User
from api.models.user_position import UserPosition
from api.models.trade_operation_log import TradeOperationLog
from api.middleware.auth import get_current_user
from api.schemas.positions import (
    PositionCreate,
    PositionUpdate,
    PositionResponse,
    PositionListResponse,
    PositionImportRequest,
    TradeActionRequest,
    TradeActionResponse,
)

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/positions', tags=['positions'])


def _to_response(p: UserPosition) -> PositionResponse:
    return PositionResponse(
        id=p.id,
        stock_code=p.stock_code,
        stock_name=p.stock_name,
        level=p.level,
        shares=p.shares,
        cost_price=p.cost_price,
        account=p.account,
        note=p.note,
        is_active=p.is_active,
        created_at=p.created_at.isoformat() if p.created_at else '',
        updated_at=p.updated_at.isoformat() if p.updated_at else '',
    )


def _build_detail(action: str, stock_name: str, stock_code: str, **kwargs) -> str:
    """Build Chinese detail string for trade log."""
    name = stock_name or stock_code
    parts = [f'{action} {name}']
    for k, v in kwargs.items():
        parts.append(f'{k}={v}')
    return ' '.join(parts)


@router.get('', response_model=PositionListResponse)
async def list_positions(
    level: Optional[str] = Query(default=None, description='Filter by level: L1/L2/L3'),
    active_only: bool = Query(default=True, description='Only active positions'),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's positions, optionally filtered by level."""
    query = select(UserPosition).where(UserPosition.user_id == current_user.id)
    if active_only:
        query = query.where(UserPosition.is_active == True)
    if level:
        query = query.where(UserPosition.level == level)
    query = query.order_by(UserPosition.level, UserPosition.stock_code)

    result = await db.execute(query)
    items = result.scalars().all()
    return PositionListResponse(
        items=[_to_response(p) for p in items],
        total=len(items),
    )


@router.get('/export')
async def export_positions(
    level: Optional[str] = Query(default=None),
    active_only: bool = Query(default=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出持仓为 CSV 文件，含最新收盘价、5日涨跌幅、持仓盈亏。"""
    query = select(UserPosition).where(UserPosition.user_id == current_user.id)
    if active_only:
        query = query.where(UserPosition.is_active == True)
    if level:
        query = query.where(UserPosition.level == level)
    query = query.order_by(UserPosition.level, UserPosition.stock_code)

    result = await db.execute(query)
    items = result.scalars().all()

    # Fetch market data for all positions
    market: dict = {}
    if items:
        codes = [p.stock_code for p in items]
        cost_map = {p.stock_code: float(p.cost_price) if p.cost_price else None for p in items}

        def _fetch(stock_codes):
            from config.db import execute_query
            placeholders = ', '.join(['%s'] * len(stock_codes))
            data: dict = {}
            try:
                rows = execute_query(
                    """
                    SELECT sub.stock_code, sub.close_price, sub.trade_date
                    FROM (
                        SELECT stock_code, close_price, trade_date,
                               ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY trade_date DESC) AS rn
                        FROM trade_stock_daily
                        WHERE stock_code IN ({})
                    ) sub
                    WHERE sub.rn = 1
                    """.format(placeholders),
                    tuple(stock_codes),
                    env='online',
                )
                for r in rows:
                    code = r['stock_code']
                    close = float(r['close_price']) if r['close_price'] else None
                    data[code] = {
                        'close': close,
                        'trade_date': str(r['trade_date']) if r['trade_date'] else None,
                    }
            except Exception as e:
                logger.warning('[POSITIONS] export market-data latest close failed: %s', e)
                return data

            # ETF latest close (codes missing from trade_stock_daily)
            etf_codes = [c for c in stock_codes if c not in data]
            if etf_codes:
                etf_ph = ', '.join(['%s'] * len(etf_codes))
                try:
                    rows = execute_query(
                        """
                        SELECT sub.fund_code, sub.close_price, sub.trade_date
                        FROM (
                            SELECT fund_code, close_price, trade_date,
                                   ROW_NUMBER() OVER (PARTITION BY fund_code ORDER BY trade_date DESC) AS rn
                            FROM trade_etf_daily
                            WHERE fund_code IN ({})
                        ) sub
                        WHERE sub.rn = 1
                        """.format(etf_ph),
                        tuple(etf_codes),
                        env='online',
                    )
                    for r in rows:
                        code = r['fund_code']
                        close = float(r['close_price']) if r['close_price'] else None
                        data[code] = {
                            'close': close,
                            'trade_date': str(r['trade_date']) if r['trade_date'] else None,
                        }
                except Exception as e:
                    logger.warning('[POSITIONS] export market-data ETF latest close failed: %s', e)

            try:
                rows = execute_query(
                    """
                    SELECT sub.stock_code, sub.close_price
                    FROM (
                        SELECT stock_code, close_price,
                               ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY trade_date DESC) AS rn
                        FROM trade_stock_daily
                        WHERE stock_code IN ({})
                    ) sub
                    WHERE sub.rn = 6
                    """.format(placeholders),
                    tuple(stock_codes),
                    env='online',
                )
                for r in rows:
                    code = r['stock_code']
                    if code in data and r['close_price'] is not None:
                        close_5d = float(r['close_price'])
                        data[code]['close_5d'] = close_5d
                        close = data[code].get('close')
                        if close is not None and close_5d > 0:
                            data[code]['change_5d_pct'] = round((close - close_5d) / close_5d * 100, 2)
            except Exception as e:
                logger.warning('[POSITIONS] export market-data 5d close failed: %s', e)

            # ETF 5-day close
            etf_codes_in_data = [c for c in etf_codes if c in data and 'change_5d_pct' not in data[c]]
            if etf_codes_in_data:
                etf_ph2 = ', '.join(['%s'] * len(etf_codes_in_data))
                try:
                    rows = execute_query(
                        """
                        SELECT sub.fund_code, sub.close_price
                        FROM (
                            SELECT fund_code, close_price,
                                   ROW_NUMBER() OVER (PARTITION BY fund_code ORDER BY trade_date DESC) AS rn
                            FROM trade_etf_daily
                            WHERE fund_code IN ({})
                        ) sub
                        WHERE sub.rn = 6
                        """.format(etf_ph2),
                        tuple(etf_codes_in_data),
                        env='online',
                    )
                    for r in rows:
                        code = r['fund_code']
                        if code in data and r['close_price'] is not None:
                            close_5d = float(r['close_price'])
                            data[code]['close_5d'] = close_5d
                            close = data[code].get('close')
                            if close is not None and close_5d > 0:
                                data[code]['change_5d_pct'] = round((close - close_5d) / close_5d * 100, 2)
                except Exception as e:
                    logger.warning('[POSITIONS] export market-data ETF 5d close failed: %s', e)

            for code, info in data.items():
                cost = cost_map.get(code)
                close = info.get('close')
                if cost and cost > 0 and close is not None:
                    info['cost_pct'] = round((close - cost) / cost * 100, 2)

            return data

        import asyncio
        loop = asyncio.get_running_loop()
        market = await loop.run_in_executor(None, _fetch, codes)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        '股票代码', '股票名称', '仓位级别', '持股数量', '成本价',
        '最新收盘价', '数据日期', '5日涨跌幅(%)', '持仓盈亏(%)',
        '账户', '备注', '状态', '创建时间',
    ])
    for p in items:
        mkt = market.get(p.stock_code, {})
        close = mkt.get('close')
        writer.writerow([
            p.stock_code,
            p.stock_name or '',
            p.level or '',
            p.shares if p.shares is not None else '',
            p.cost_price if p.cost_price is not None else '',
            close if close is not None else '',
            mkt.get('trade_date') or '',
            mkt.get('change_5d_pct', ''),
            mkt.get('cost_pct', ''),
            p.account or '',
            p.note or '',
            '持仓中' if p.is_active else '已清仓',
            p.created_at.strftime('%Y-%m-%d %H:%M:%S') if p.created_at else '',
        ])

    buf.seek(0)
    filename = 'positions.csv'
    return StreamingResponse(
        iter(['\ufeff' + buf.getvalue()]),
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@router.post('', response_model=PositionResponse, status_code=status.HTTP_201_CREATED)
async def create_position(
    req: PositionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new position."""
    # Check for duplicate (same user + stock_code + account)
    existing = await db.execute(
        select(UserPosition).where(
            UserPosition.user_id == current_user.id,
            UserPosition.stock_code == req.stock_code,
            UserPosition.account == req.account,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'{req.stock_code} already exists in positions',
        )

    position = UserPosition(
        user_id=current_user.id,
        stock_code=req.stock_code,
        stock_name=req.stock_name,
        level=req.level,
        shares=req.shares,
        cost_price=req.cost_price,
        account=req.account,
        note=req.note,
    )
    db.add(position)
    await db.flush()
    await db.refresh(position)

    # Auto-log: open position
    after = {}
    if req.shares is not None:
        after['shares'] = req.shares
    if req.cost_price is not None:
        after['cost_price'] = req.cost_price
    if req.level:
        after['level'] = req.level
    db.add(TradeOperationLog(
        user_id=current_user.id,
        operation_type='open_position',
        stock_code=req.stock_code,
        stock_name=req.stock_name,
        detail=_build_detail('建仓', req.stock_name, req.stock_code,
                             shares=f'{req.shares}股' if req.shares else '',
                             cost=f'@{req.cost_price}' if req.cost_price else '',
                             level=req.level or ''),
        after_value=json.dumps(after) if after else None,
        source='auto',
    ))

    logger.info('[POSITIONS] user=%s added stock=%s', current_user.id, req.stock_code)
    return _to_response(position)


@router.put('/{position_id}', response_model=PositionResponse)
async def update_position(
    position_id: int,
    req: PositionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a position."""
    result = await db.execute(
        select(UserPosition).where(
            UserPosition.id == position_id,
            UserPosition.user_id == current_user.id,
        )
    )
    position = result.scalar_one_or_none()
    if not position:
        raise HTTPException(status_code=404, detail='Position not found')

    update_data = req.model_dump(exclude_unset=True)
    if not update_data:
        return _to_response(position)

    # Snapshot old values before applying changes
    old_values = {k: getattr(position, k) for k in update_data}

    # Apply changes
    for key, value in update_data.items():
        setattr(position, key, value)

    # Determine operation type and build log
    name = position.stock_name or position.stock_code
    shares_changed = 'shares' in update_data

    if shares_changed:
        old_s = old_values.get('shares') or 0
        new_s = update_data.get('shares') or 0
        direction = '加仓' if new_s > old_s else ('减仓' if new_s < old_s else '调整')
        db.add(TradeOperationLog(
            user_id=current_user.id,
            operation_type='add_reduce',
            stock_code=position.stock_code,
            stock_name=position.stock_name,
            detail=_build_detail(direction, name, position.stock_code,
                                 shares=f'{old_s}->{new_s}股'),
            before_value=json.dumps({'shares': old_s}),
            after_value=json.dumps({'shares': new_s}),
            source='auto',
        ))
    else:
        changed_list = ', '.join(update_data.keys())
        db.add(TradeOperationLog(
            user_id=current_user.id,
            operation_type='modify_info',
            stock_code=position.stock_code,
            stock_name=position.stock_name,
            detail=_build_detail('修改', name, position.stock_code,
                                 fields=changed_list),
            before_value=json.dumps(old_values),
            after_value=json.dumps(update_data),
            source='auto',
        ))

    return _to_response(position)


@router.delete('/{position_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_position(
    position_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a position (set is_active=False)."""
    result = await db.execute(
        select(UserPosition).where(
            UserPosition.id == position_id,
            UserPosition.user_id == current_user.id,
        )
    )
    position = result.scalar_one_or_none()
    if not position:
        raise HTTPException(status_code=404, detail='Position not found')

    # Snapshot before deactivation
    before = {}
    if position.shares is not None:
        before['shares'] = position.shares
    if position.cost_price is not None:
        before['cost_price'] = position.cost_price

    position.is_active = False

    # Auto-log: close position
    name = position.stock_name or position.stock_code
    db.add(TradeOperationLog(
        user_id=current_user.id,
        operation_type='close_position',
        stock_code=position.stock_code,
        stock_name=position.stock_name,
        detail=_build_detail('清仓', name, position.stock_code,
                             shares=f'{position.shares}股' if position.shares else '',
                             cost=f'@{position.cost_price}' if position.cost_price else ''),
        before_value=json.dumps(before) if before else None,
        source='auto',
    ))

    logger.info('[POSITIONS] user=%s deactivated position=%s', current_user.id, position_id)


@router.post('/{position_id}/trade', response_model=TradeActionResponse)
async def trade_position(
    position_id: int,
    req: TradeActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    加仓/减仓/清仓操作：
    - add：加仓，重算加权平均成本
    - reduce：减仓，保留原成本不变
    - close：清仓，is_active=False，计算盈亏%
    """
    result = await db.execute(
        select(UserPosition).where(
            UserPosition.id == position_id,
            UserPosition.user_id == current_user.id,
            UserPosition.is_active == True,
        )
    )
    position = result.scalar_one_or_none()
    if not position:
        raise HTTPException(status_code=404, detail='Position not found')

    action = req.action.lower()
    if action not in ('add', 'reduce', 'close'):
        raise HTTPException(status_code=400, detail='action must be add/reduce/close')

    shares_before = position.shares or 0
    cost_before = position.cost_price
    name = position.stock_name or position.stock_code
    pnl_pct = None
    closed = False

    if action == 'add':
        if req.shares is None:
            raise HTTPException(status_code=400, detail='shares required for add')
        trade_shares = req.shares
        new_shares = shares_before + trade_shares
        # Weighted average cost
        if cost_before and shares_before > 0:
            new_cost = round(
                (cost_before * shares_before + req.price * trade_shares) / new_shares, 4
            )
        else:
            new_cost = req.price
        position.shares = new_shares
        position.cost_price = new_cost
        op_type = 'add_reduce'
        detail = _build_detail(
            '加仓', name, position.stock_code,
            price=f'@{req.price}', shares=f'+{trade_shares}股',
            new_shares=f'{new_shares}股', new_cost=f'{new_cost}',
        )
        before_val = json.dumps({'shares': shares_before, 'cost_price': cost_before})
        after_val = json.dumps({'shares': new_shares, 'cost_price': new_cost})

    elif action == 'reduce':
        if req.shares is None:
            raise HTTPException(status_code=400, detail='shares required for reduce')
        trade_shares = req.shares
        if trade_shares >= shares_before:
            raise HTTPException(status_code=400, detail='reduce shares must be less than current shares; use close to exit fully')
        new_shares = shares_before - trade_shares
        # Cost stays unchanged on reduce
        new_cost = cost_before
        pnl_pct = round((req.price - cost_before) / cost_before * 100, 2) if cost_before else None
        position.shares = new_shares
        op_type = 'add_reduce'
        pnl_str = f' 本次盈亏={pnl_pct:+.2f}%' if pnl_pct is not None else ''
        detail = _build_detail(
            '减仓', name, position.stock_code,
            price=f'@{req.price}', shares=f'-{trade_shares}股',
            remaining=f'{new_shares}股',
        ) + pnl_str
        before_val = json.dumps({'shares': shares_before})
        after_val = json.dumps({'shares': new_shares})

    else:  # close
        # Calculate P&L
        if cost_before and cost_before > 0:
            pnl_pct = round((req.price - cost_before) / cost_before * 100, 2)
        position.is_active = False
        closed = True
        new_shares = 0
        new_cost = cost_before
        op_type = 'close_position'
        pnl_str = f' 盈亏={pnl_pct:+.2f}%' if pnl_pct is not None else ''
        detail = _build_detail(
            '清仓', name, position.stock_code,
            price=f'@{req.price}', shares=f'{shares_before}股',
        ) + pnl_str
        before_val = json.dumps({'shares': shares_before, 'cost_price': cost_before})
        after_val = json.dumps({'shares': 0, 'pnl_pct': pnl_pct})

    db.add(TradeOperationLog(
        user_id=current_user.id,
        operation_type=op_type,
        stock_code=position.stock_code,
        stock_name=position.stock_name,
        detail=detail,
        before_value=before_val,
        after_value=after_val,
        source='manual',
    ))

    logger.info('[POSITIONS] user=%s trade=%s position=%s price=%s shares=%s',
                current_user.id, action, position_id, req.price, req.shares)

    return TradeActionResponse(
        position_id=position_id,
        action=action,
        shares_before=shares_before,
        shares_after=new_shares,
        cost_before=cost_before,
        cost_after=new_cost,
        pnl_pct=pnl_pct,
        closed=closed,
    )


@router.post('/risk-scan')
async def risk_scan(
    current_user: User = Depends(get_current_user),
):
    """Trigger a risk scan for the current user's portfolio."""
    import asyncio

    def _do_scan(user_id: int):
        import sys
        import os
        # Add trader project to path for risk_manager.scanner
        trader_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'trader')
        trader_path = os.path.normpath(trader_path)
        if trader_path not in sys.path:
            sys.path.insert(0, trader_path)

        from risk_manager.scanner import scan_portfolio
        return scan_portfolio(user_id=user_id, env='online')

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _do_scan, current_user.id)
        return result
    except Exception as exc:
        logger.error('[POSITIONS] risk_scan failed for user=%s: %s', current_user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post('/batch-analyze')
async def batch_analyze(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    一键分析：对当前用户所有活跃持仓执行技术面快照 + 当日公告检查。
    公告当日未抓取时自动触发全市场抓取（去重，每日只触发一次）。
    返回每支股票的分析摘要。
    """
    import asyncio
    from datetime import date

    result = await db.execute(
        select(UserPosition).where(
            UserPosition.user_id == current_user.id,
            UserPosition.is_active == True,
        )
    )
    positions = result.scalars().all()
    if not positions:
        return {'stocks': [], 'announcement_fetched': False}

    codes = [p.stock_code for p in positions if p.stock_code]
    code_name = {p.stock_code: p.stock_name or p.stock_code for p in positions if p.stock_code}
    if not codes:
        return {'stocks': [], 'announcement_fetched': False}

    def _analyze(stock_codes, user_id):
        from config.db import execute_query, execute_update
        from data_analyst.fetchers.announcement_fetcher import (
            fetch_announcements_for_date,
            get_announcements_for_codes,
        )

        today = date.today()
        today_str = today.isoformat()
        placeholders = ', '.join(['%s'] * len(stock_codes))

        # --- 技术面快照：最近2日 OHLCV + 量比 ---
        tech_map = {}
        try:
            rows = execute_query(
                """
                SELECT sub.stock_code, sub.close_price, sub.open_price,
                       sub.high_price, sub.low_price, sub.volume, sub.trade_date,
                       sub.rn
                FROM (
                    SELECT stock_code, close_price, open_price, high_price, low_price,
                           volume, trade_date,
                           ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY trade_date DESC) AS rn
                    FROM trade_stock_daily
                    WHERE stock_code IN ({})
                ) sub
                WHERE sub.rn <= 6
                """.format(placeholders),
                tuple(stock_codes),
                env='online',
            )
            # 按 code 分组
            raw: dict = {}
            for r in rows:
                code = r['stock_code']
                raw.setdefault(code, []).append(r)

            for code, recs in raw.items():
                recs_sorted = sorted(recs, key=lambda x: x['rn'])
                latest = recs_sorted[0]
                prev = recs_sorted[1] if len(recs_sorted) > 1 else None
                day5 = recs_sorted[5] if len(recs_sorted) > 5 else None

                close = float(latest['close_price']) if latest['close_price'] else None
                prev_close = float(prev['close_price']) if prev and prev['close_price'] else None
                open_p = float(latest['open_price']) if latest['open_price'] else None
                high = float(latest['high_price']) if latest['high_price'] else None
                low = float(latest['low_price']) if latest['low_price'] else None
                vol = int(latest['volume']) if latest['volume'] else None
                prev_vol = int(prev['volume']) if prev and prev['volume'] else None
                close_5d = float(day5['close_price']) if day5 and day5['close_price'] else None

                chg_pct = round((close - prev_close) / prev_close * 100, 2) if close and prev_close else None
                chg_5d_pct = round((close - close_5d) / close_5d * 100, 2) if close and close_5d else None
                vol_ratio = round(vol / prev_vol, 2) if vol and prev_vol and prev_vol > 0 else None

                tech_map[code] = {
                    'trade_date': str(latest['trade_date']) if latest['trade_date'] else '',
                    'close': close,
                    'open': open_p,
                    'high': high,
                    'low': low,
                    'chg_pct': chg_pct,
                    'chg_5d_pct': chg_5d_pct,
                    'vol_ratio': vol_ratio,
                }
        except Exception as e:
            logger.warning('[POSITIONS] batch-analyze tech query failed: %s', e)

        # --- 当日公告检查：DB 层乐观锁防止并发重复抓取 ---
        announcement_fetched = False
        try:
            execute_update(
                """CREATE TABLE IF NOT EXISTS announcement_fetch_lock (
                    fetch_date DATE NOT NULL,
                    status VARCHAR(10) NOT NULL DEFAULT 'fetching',
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (fetch_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
                env='online',
            )
            # 尝试插入占位行，ON DUPLICATE KEY 保证只有第一个请求真正触发抓取
            inserted = execute_update(
                """INSERT IGNORE INTO announcement_fetch_lock (fetch_date, status, created_at)
                   VALUES (%s, 'fetching', NOW())""",
                (today_str,),
                env='online',
            )
            if inserted:
                # 本请求抢到锁，执行抓取
                try:
                    fetch_announcements_for_date(today)
                    execute_update(
                        "UPDATE announcement_fetch_lock SET status='done' WHERE fetch_date=%s",
                        (today_str,),
                        env='online',
                    )
                    announcement_fetched = True
                except Exception as e:
                    execute_update(
                        "UPDATE announcement_fetch_lock SET status='error' WHERE fetch_date=%s",
                        (today_str,),
                        env='online',
                    )
                    logger.warning('[POSITIONS] batch-analyze announcement fetch failed: %s', e)
            # else: 另一个请求已在处理或已完成，跳过
        except Exception as e:
            logger.warning('[POSITIONS] batch-analyze lock check failed: %s', e)

        # --- 读公告（当日 + 近7日） ---
        ann_map = get_announcements_for_codes(stock_codes, days=7)

        return tech_map, ann_map, announcement_fetched

    try:
        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(None, _analyze, codes, current_user.id)
        tech_map, ann_map, ann_fetched = await asyncio.wait_for(task, timeout=120)
    except asyncio.TimeoutError:
        logger.warning('[POSITIONS] batch-analyze timeout for user=%s', current_user.id)
        raise HTTPException(status_code=504, detail='分析超时，请稍后重试')
    except Exception as exc:
        logger.error('[POSITIONS] batch-analyze failed for user=%s: %s', current_user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    today_str = date.today().isoformat()
    stocks = []
    for code in codes:
        tech = tech_map.get(code, {})
        anns = ann_map.get(code, [])
        today_anns = [a for a in anns if a['date'] == today_str]
        recent_anns = [a for a in anns if a['date'] != today_str]

        stocks.append({
            'stock_code': code,
            'stock_name': code_name.get(code, ''),
            'tech': tech,
            'today_announcements': today_anns,
            'recent_announcements': recent_anns[:5],
        })

    logger.info('[POSITIONS] batch-analyze done for user=%s, stocks=%d', current_user.id, len(stocks))
    return {'stocks': stocks, 'announcement_fetched': ann_fetched}


@router.get('/market-data/freshness')
async def check_market_data_freshness(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if position market data is up-to-date.

    Returns the expected latest trading day, whether the data is ready,
    and whether markets are currently open -- so the frontend can decide
    whether to show a stale-data banner and avoid repeated checks.
    """
    import asyncio
    from datetime import date, datetime, time, timedelta

    now = datetime.now()
    today = now.date()
    current_time = now.time()

    # Market hours: 09:30 - 15:00, Monday-Friday
    is_weekday = today.weekday() < 5
    market_open = time(9, 30)
    market_close = time(15, 0)
    # Data pipeline starts 16:15, typically ready by ~17:30
    data_ready_time = time(17, 30)

    is_market_hours = is_weekday and market_open <= current_time <= market_close
    is_after_close = is_weekday and current_time > market_close

    # Determine the expected latest trading day with data
    # After 17:30 on a weekday -> expect today's data
    # Before 17:30 on a weekday -> expect previous trading day data
    # Weekend -> expect last Friday's data
    def _get_expected_date():
        if is_weekday and current_time >= data_ready_time:
            return today
        # Walk backwards to find the previous weekday
        d = today if not is_weekday else today - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d

    expected_date = _get_expected_date()

    # Get active positions
    result = await db.execute(
        select(UserPosition.stock_code).where(
            UserPosition.user_id == current_user.id,
            UserPosition.is_active == True,
        )
    )
    codes = [r[0] for r in result.all()]
    if not codes:
        return {
            'expected_date': str(expected_date),
            'is_market_hours': is_market_hours,
            'is_after_close': is_after_close,
            'data_ready': True,
            'stale_count': 0,
            'total_count': 0,
        }

    def _check(stock_codes):
        from config.db import execute_query
        placeholders = ', '.join(['%s'] * len(stock_codes))
        try:
            rows = execute_query(
                """
                SELECT stock_code, MAX(trade_date) AS latest_date
                FROM trade_stock_daily
                WHERE stock_code IN ({})
                GROUP BY stock_code
                """.format(placeholders),
                tuple(stock_codes),
                env='online',
            )
            found = {r['stock_code']: str(r['latest_date']) for r in rows}
        except Exception:
            found = {}

        # Also check ETF table for codes not found
        missing = [c for c in stock_codes if c not in found]
        if missing:
            etf_ph = ', '.join(['%s'] * len(missing))
            try:
                rows = execute_query(
                    """
                    SELECT fund_code, MAX(trade_date) AS latest_date
                    FROM trade_etf_daily
                    WHERE fund_code IN ({})
                    GROUP BY fund_code
                    """.format(etf_ph),
                    tuple(missing),
                    env='online',
                )
                for r in rows:
                    found[r['fund_code']] = str(r['latest_date'])
            except Exception:
                pass

        expected_str = str(expected_date)
        stale = [c for c in stock_codes if found.get(c, '') < expected_str]
        return len(stale), found

    loop = asyncio.get_running_loop()
    stale_count, _detail = await loop.run_in_executor(None, _check, codes)

    return {
        'expected_date': str(expected_date),
        'is_market_hours': is_market_hours,
        'is_after_close': is_after_close,
        'data_ready': stale_count == 0,
        'stale_count': stale_count,
        'total_count': len(codes),
    }


@router.get('/market-data')
async def get_positions_market_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch latest close price and 5-day change for all active positions."""
    import asyncio

    # Get active positions
    result = await db.execute(
        select(UserPosition).where(
            UserPosition.user_id == current_user.id,
            UserPosition.is_active == True,
        )
    )
    positions = result.scalars().all()
    if not positions:
        return {}

    codes = [p.stock_code for p in positions]
    cost_map = {p.stock_code: float(p.cost_price) if p.cost_price else None for p in positions}

    def _fetch_market_data(stock_codes):
        from config.db import execute_query

        placeholders = ', '.join(['%s'] * len(stock_codes))
        data = {}

        # Latest close price
        try:
            rows = execute_query(
                """
                SELECT sub.stock_code, sub.close_price, sub.trade_date
                FROM (
                    SELECT stock_code, close_price, trade_date,
                           ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY trade_date DESC) AS rn
                    FROM trade_stock_daily
                    WHERE stock_code IN ({})
                ) sub
                WHERE sub.rn = 1
                """.format(placeholders),
                tuple(stock_codes),
                env='online',
            )
            for r in rows:
                code = r['stock_code']
                close = float(r['close_price']) if r['close_price'] else None
                data[code] = {
                    'close': close,
                    'trade_date': str(r['trade_date']) if r['trade_date'] else None,
                }
        except Exception as e:
            logger.warning('[POSITIONS] market-data latest close query failed: %s', e)
            return data

        # ETF latest close (codes missing from trade_stock_daily)
        etf_codes = [c for c in stock_codes if c not in data]
        if etf_codes:
            etf_ph = ', '.join(['%s'] * len(etf_codes))
            try:
                rows = execute_query(
                    """
                    SELECT sub.fund_code, sub.close_price, sub.trade_date
                    FROM (
                        SELECT fund_code, close_price, trade_date,
                               ROW_NUMBER() OVER (PARTITION BY fund_code ORDER BY trade_date DESC) AS rn
                        FROM trade_etf_daily
                        WHERE fund_code IN ({})
                    ) sub
                    WHERE sub.rn = 1
                    """.format(etf_ph),
                    tuple(etf_codes),
                    env='online',
                )
                for r in rows:
                    code = r['fund_code']
                    close = float(r['close_price']) if r['close_price'] else None
                    data[code] = {
                        'close': close,
                        'trade_date': str(r['trade_date']) if r['trade_date'] else None,
                    }
            except Exception as e:
                logger.warning('[POSITIONS] market-data ETF latest close query failed: %s', e)

        # 5 trading days ago close
        try:
            rows = execute_query(
                """
                SELECT sub.stock_code, sub.close_price
                FROM (
                    SELECT stock_code, close_price,
                           ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY trade_date DESC) AS rn
                    FROM trade_stock_daily
                    WHERE stock_code IN ({})
                ) sub
                WHERE sub.rn = 6
                """.format(placeholders),
                tuple(stock_codes),
                env='online',
            )
            for r in rows:
                code = r['stock_code']
                if code in data and r['close_price'] is not None:
                    close_5d = float(r['close_price'])
                    data[code]['close_5d'] = close_5d
                    close = data[code].get('close')
                    if close is not None and close_5d > 0:
                        data[code]['change_5d_pct'] = round((close - close_5d) / close_5d * 100, 2)
        except Exception as e:
            logger.warning('[POSITIONS] market-data 5d close query failed: %s', e)

        # ETF 5-day close
        etf_codes_in_data = [c for c in etf_codes if c in data and 'change_5d_pct' not in data[c]]
        if etf_codes_in_data:
            etf_ph2 = ', '.join(['%s'] * len(etf_codes_in_data))
            try:
                rows = execute_query(
                    """
                    SELECT sub.fund_code, sub.close_price
                    FROM (
                        SELECT fund_code, close_price,
                               ROW_NUMBER() OVER (PARTITION BY fund_code ORDER BY trade_date DESC) AS rn
                        FROM trade_etf_daily
                        WHERE fund_code IN ({})
                    ) sub
                    WHERE sub.rn = 6
                    """.format(etf_ph2),
                    tuple(etf_codes_in_data),
                    env='online',
                )
                for r in rows:
                    code = r['fund_code']
                    if code in data and r['close_price'] is not None:
                        close_5d = float(r['close_price'])
                        data[code]['close_5d'] = close_5d
                        close = data[code].get('close')
                        if close is not None and close_5d > 0:
                            data[code]['change_5d_pct'] = round((close - close_5d) / close_5d * 100, 2)
            except Exception as e:
                logger.warning('[POSITIONS] market-data ETF 5d close query failed: %s', e)

        # Calculate cost gain/loss %
        for code, info in data.items():
            cost = cost_map.get(code)
            close = info.get('close')
            if cost and cost > 0 and close is not None:
                info['cost_pct'] = round((close - cost) / cost * 100, 2)

        return data

    try:
        loop = asyncio.get_running_loop()
        market_data = await loop.run_in_executor(None, _fetch_market_data, codes)
        return market_data
    except Exception as exc:
        logger.error('[POSITIONS] market-data failed for user=%s: %s', current_user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post('/import', status_code=status.HTTP_201_CREATED)
async def import_positions(
    req: PositionImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk import positions from JSON."""
    created = 0
    skipped = 0
    for item in req.items:
        existing = await db.execute(
            select(UserPosition).where(
                UserPosition.user_id == current_user.id,
                UserPosition.stock_code == item.stock_code,
                UserPosition.account == item.account,
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        position = UserPosition(
            user_id=current_user.id,
            stock_code=item.stock_code,
            stock_name=item.stock_name,
            level=item.level,
            shares=item.shares,
            cost_price=item.cost_price,
            account=item.account,
            note=item.note,
        )
        db.add(position)

        # Auto-log each imported position
        after = {}
        if item.shares is not None:
            after['shares'] = item.shares
        if item.cost_price is not None:
            after['cost_price'] = item.cost_price
        db.add(TradeOperationLog(
            user_id=current_user.id,
            operation_type='open_position',
            stock_code=item.stock_code,
            stock_name=item.stock_name,
            detail=_build_detail('批量建仓', item.stock_name, item.stock_code,
                                 shares=f'{item.shares}股' if item.shares else ''),
            after_value=json.dumps(after) if after else None,
            source='auto',
        ))

        created += 1

    await db.flush()
    logger.info('[POSITIONS] user=%s imported %s positions (%s skipped)', current_user.id, created, skipped)
    return {'created': created, 'skipped': skipped}
