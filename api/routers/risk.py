# -*- coding: utf-8 -*-
"""
风控 V2 API 路由

GET /api/risk/scan           - 触发完整分层扫描，返回 LayeredRiskResult 序列化为 dict
GET /api/risk/macro          - 仅宏观层评估
GET /api/risk/report         - 返回最新 Markdown 报告字符串
POST /api/risk/trigger-deps  - 手动触发数据依赖检查
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from api.middleware.auth import get_current_user
from api.models.user import User
from data_analyst.risk_assessment.storage import dataclass_to_dict, reconstruct_layered_result

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/risk', tags=['risk'])


@router.get('/scan')
async def risk_scan_v2(
    current_user: User = Depends(get_current_user),
):
    """
    触发完整分层风控扫描（L1-L5），返回 LayeredRiskResult 序列化后的 dict。
    计算密集，耗时约 10-30 秒。
    """
    import asyncio

    def _do_scan(user_id: int):
        from data_analyst.risk_assessment.scanner import scan_portfolio_v2
        return scan_portfolio_v2(user_id=user_id, env='online')

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _do_scan, current_user.id)
        return dataclass_to_dict(result)
    except Exception as exc:
        logger.error('[RISK] scan failed for user=%s: %s', current_user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get('/macro')
async def risk_macro(
    current_user: User = Depends(get_current_user),
):
    """仅宏观层评估（L1），响应较快。"""
    import asyncio

    def _do_macro():
        from data_analyst.risk_assessment.assessors.macro import MacroRiskAssessor
        result = MacroRiskAssessor(env='online').assess()
        return dataclass_to_dict(result)

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _do_macro)
    except Exception as exc:
        logger.error('[RISK] macro failed for user=%s: %s', current_user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get('/report')
async def risk_report(
    current_user: User = Depends(get_current_user),
):
    """
    返回最新风控扫描的 Markdown 报告字符串。
    优先从 output/risk_assessment/ 加载缓存，否则实时计算。
    """
    import asyncio

    def _do_report(user_id: int):
        from data_analyst.risk_assessment.storage import load_scan_result, reconstruct_layered_result
        from data_analyst.risk_assessment.report import generate_report_v2

        cached = load_scan_result()
        if cached is not None:
            try:
                return generate_report_v2(reconstruct_layered_result(cached))
            except Exception:
                pass

        from data_analyst.risk_assessment.scanner import scan_portfolio_v2
        return generate_report_v2(scan_portfolio_v2(user_id=user_id, env='online'))

    try:
        loop = asyncio.get_running_loop()
        report_md = await loop.run_in_executor(None, _do_report, current_user.id)
        return {'report': report_md}
    except Exception as exc:
        logger.error('[RISK] report failed for user=%s: %s', current_user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get('/stock/{code}')
async def risk_stock(
    code: str,
    current_user: User = Depends(get_current_user),
):
    """
    个股风控分析：通用维度（技术指标、估值）+ 个性化维度（成本距离、仓位占比、盈亏比、相关性）。
    code 为带后缀的股票代码，如 000858.SZ。
    """
    import asyncio

    def _do_stock_risk(user_id: int, stock_code: str):
        from config.db import execute_query

        result: dict = {
            'stock_code': stock_code,
            'common': {},
            'personalized': None,
        }

        # --- 通用：技术指标 ---
        try:
            rows = execute_query(
                """
                SELECT t.trade_date, t.close_price,
                       t.ma5, t.ma10, t.ma20, t.ma60, t.ma250,
                       t.macd_dif, t.macd_dea, t.rsi_14,
                       t.upper_band, t.lower_band, t.atr_14
                FROM trade_technical_indicator t
                WHERE t.stock_code = %s
                ORDER BY t.trade_date DESC
                LIMIT 1
                """,
                (stock_code,),
                env='online',
            )
            if rows:
                r = rows[0]
                close = float(r['close_price']) if r['close_price'] else None
                ma20 = float(r['ma20']) if r['ma20'] else None
                ma60 = float(r['ma60']) if r['ma60'] else None
                ma250 = float(r['ma250']) if r['ma250'] else None
                rsi = float(r['rsi_14']) if r['rsi_14'] else None
                macd_dif = float(r['macd_dif']) if r['macd_dif'] else None
                macd_dea = float(r['macd_dea']) if r['macd_dea'] else None
                upper = float(r['upper_band']) if r['upper_band'] else None
                lower = float(r['lower_band']) if r['lower_band'] else None

                ma_status = []
                if close and ma20:
                    ma_status.append('MA20以上' if close > ma20 else 'MA20以下')
                if close and ma60:
                    ma_status.append('MA60以上' if close > ma60 else 'MA60以下')
                if close and ma250:
                    ma_status.append('MA250以上' if close > ma250 else 'MA250以下')

                macd_signal = None
                if macd_dif is not None and macd_dea is not None:
                    if macd_dif > macd_dea:
                        macd_signal = '金叉区间' if macd_dif > 0 else '底部金叉'
                    else:
                        macd_signal = '死叉区间' if macd_dif < 0 else '顶部死叉'

                boll_position = None
                if close and upper and lower and upper > lower:
                    pct = (close - lower) / (upper - lower)
                    if pct > 0.8:
                        boll_position = '布林上轨附近'
                    elif pct < 0.2:
                        boll_position = '布林下轨附近'
                    else:
                        boll_position = '布林中轨区间'

                result['common']['technical'] = {
                    'trade_date': str(r['trade_date']) if r['trade_date'] else None,
                    'close': close,
                    'ma20': ma20,
                    'ma60': ma60,
                    'ma250': ma250,
                    'rsi_14': rsi,
                    'macd_dif': macd_dif,
                    'macd_dea': macd_dea,
                    'ma_status': ma_status,
                    'macd_signal': macd_signal,
                    'boll_position': boll_position,
                }
        except Exception as e:
            logger.warning('[RISK/stock] technical query failed for %s: %s', stock_code, e)

        # --- 通用：估值 ---
        try:
            val_rows = execute_query(
                """
                SELECT pe_ttm, pb, ps_ttm, total_mv, circ_mv, trade_date
                FROM trade_stock_daily_basic
                WHERE stock_code = %s
                ORDER BY trade_date DESC
                LIMIT 1
                """,
                (stock_code,),
                env='online',
            )
            if val_rows:
                v = val_rows[0]
                pe = float(v['pe_ttm']) if v['pe_ttm'] else None
                pb = float(v['pb']) if v['pb'] else None
                result['common']['valuation'] = {
                    'trade_date': str(v['trade_date']) if v['trade_date'] else None,
                    'pe_ttm': pe,
                    'pb': pb,
                    'ps_ttm': float(v['ps_ttm']) if v['ps_ttm'] else None,
                    'total_mv': float(v['total_mv']) if v['total_mv'] else None,
                    'circ_mv': float(v['circ_mv']) if v['circ_mv'] else None,
                }
        except Exception as e:
            logger.warning('[RISK/stock] valuation query failed for %s: %s', stock_code, e)

        # --- 个性化：查找用户持仓 ---
        try:
            pos_rows = execute_query(
                "SELECT stock_code, shares, cost_price FROM user_positions WHERE user_id = %s AND is_active = 1",
                (user_id,),
                env='local',
            )
            positions = [
                {'stock_code': r['stock_code'], 'shares': int(r['shares'] or 0), 'cost_price': float(r['cost_price'] or 0)}
                for r in pos_rows
            ]
        except Exception as e:
            logger.warning('[RISK/stock] user positions query failed: %s', e)
            positions = []

        target_pos = next((p for p in positions if p['stock_code'] == stock_code), None)

        if target_pos and target_pos['shares'] > 0 and target_pos['cost_price'] > 0:
            personalized: dict = {}

            # 获取当前收盘价
            close_price = None
            try:
                price_rows = execute_query(
                    """
                    SELECT close_price FROM trade_stock_daily
                    WHERE stock_code = %s
                    ORDER BY trade_date DESC LIMIT 1
                    """,
                    (stock_code,),
                    env='online',
                )
                if price_rows and price_rows[0]['close_price']:
                    close_price = float(price_rows[0]['close_price'])
            except Exception as e:
                logger.warning('[RISK/stock] price query failed: %s', e)

            cost = target_pos['cost_price']
            shares = target_pos['shares']

            if close_price:
                personalized['cost_distance_pct'] = round((close_price - cost) / cost * 100, 2)
                personalized['pnl_ratio'] = round((close_price - cost) / cost * 100, 2)
                curr_val = close_price * shares
            else:
                personalized['cost_distance_pct'] = None
                personalized['pnl_ratio'] = None
                curr_val = cost * shares

            personalized['cost_price'] = cost
            personalized['shares'] = shares
            personalized['current_price'] = close_price

            # 仓位占比
            total_val = sum(
                (close_price if p['stock_code'] == stock_code else p['cost_price']) * p['shares']
                for p in positions if p['shares'] > 0
            )
            if total_val > 0:
                personalized['position_weight_pct'] = round(curr_val / total_val * 100, 2)
            else:
                personalized['position_weight_pct'] = None

            # 与其他持仓相关性（复用 regime assessor 的相关性结果）
            other_codes = [p['stock_code'] for p in positions if p['stock_code'] != stock_code and p['shares'] > 0]
            if len(other_codes) >= 1:
                try:
                    import pandas as pd
                    all_codes = [stock_code] + other_codes
                    placeholders = ', '.join(['%s'] * len(all_codes))
                    corr_rows = execute_query(
                        """
                        SELECT stock_code, trade_date, close_price AS close
                        FROM trade_stock_daily
                        WHERE stock_code IN ({})
                          AND trade_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
                        ORDER BY stock_code, trade_date
                        """.format(placeholders),
                        tuple(all_codes),
                        env='online',
                    )
                    if corr_rows:
                        df = pd.DataFrame(corr_rows)
                        df['close'] = df['close'].astype(float)
                        pivot = df.pivot(index='trade_date', columns='stock_code', values='close')
                        returns = pivot.pct_change().dropna(how='all')
                        valid_cols = [c for c in returns.columns if returns[c].count() >= 30]
                        if stock_code in valid_cols and len(valid_cols) >= 2:
                            corr_matrix = returns[valid_cols].corr()
                            if stock_code in corr_matrix.columns:
                                row = corr_matrix[stock_code].drop(stock_code)
                                top_corr = row.abs().nlargest(3)
                                personalized['correlations'] = [
                                    {'stock_code': c, 'correlation': round(float(row[c]), 3)}
                                    for c in top_corr.index
                                ]
                                avg = float(row.mean())
                                personalized['avg_portfolio_correlation'] = round(avg, 3)
                except Exception as e:
                    logger.warning('[RISK/stock] correlation calc failed: %s', e)

            result['personalized'] = personalized

        return result

    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, _do_stock_risk, current_user.id, code)
        return data
    except Exception as exc:
        logger.error('[RISK] stock risk failed for code=%s user=%s: %s', code, current_user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post('/trigger-deps')
async def trigger_deps(
    current_user: User = Depends(get_current_user),
):
    """
    手动触发数据依赖检查，返回各数据源状态列表。
    """
    import asyncio

    def _do_check():
        from data_analyst.risk_assessment.data_deps import DataDependencyChecker
        results = DataDependencyChecker(env='online').check_and_trigger()
        return dataclass_to_dict(results)

    try:
        loop = asyncio.get_running_loop()
        statuses = await loop.run_in_executor(None, _do_check)
        return {'data_status': statuses}
    except Exception as exc:
        logger.error('[RISK] trigger-deps failed for user=%s: %s', current_user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
