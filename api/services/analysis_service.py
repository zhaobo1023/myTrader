# -*- coding: utf-8 -*-
"""
Analysis service - technical and fundamental analysis
"""
import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

import pandas as pd
from fastapi import HTTPException

from config.db import execute_query, execute_update
from api.services.market_service import _normalize_stock_code, _format_date

logger = logging.getLogger('myTrader.api')


async def get_technical_analysis(stock_code: str) -> dict:
    """Generate technical analysis report for a stock."""
    code = _normalize_stock_code(stock_code)

    # Fetch latest K-line data
    kline_sql = """
        SELECT trade_date, open_price as open, high_price as high,
               low_price as low, close_price as close, volume, turnover_rate
        FROM trade_stock_daily
        WHERE stock_code = %s
        ORDER BY trade_date DESC LIMIT 60
    """
    kline_data = list(execute_query(kline_sql, (code,)))
    if not kline_data:
        return {'stock_code': code, 'trade_date': '', 'signals': [], 'score': 0,
                'summary': 'No data found', 'indicators': {}}

    latest = kline_data[0]
    close = float(latest['close'])
    trade_date = _format_date(latest.get('trade_date', ''))

    # Fetch technical indicators
    ind_sql = """
        SELECT ma5, ma10, ma20, ma60, ma120, ma250,
               macd_dif, macd_dea, macd_histogram,
               rsi_6, rsi_12, rsi_24,
               bollinger_upper, bollinger_middle, bollinger_lower,
               volume_ratio, atr
        FROM trade_technical_indicator
        WHERE stock_code = %s
        ORDER BY trade_date DESC LIMIT 2
    """
    ind_data = list(execute_query(ind_sql, (code,)))

    signals = []
    indicators = {}
    score = 0

    if ind_data:
        curr = ind_data[0]
        prev = ind_data[1] if len(ind_data) > 1 else None
        indicators = {k: float(v) if v is not None else None for k, v in curr.items()}

        # MA analysis
        for period_name in ['ma5', 'ma10', 'ma20', 'ma60']:
            ma_val = curr.get(period_name)
            if ma_val is not None:
                ma_float = float(ma_val)
                if close > ma_float:
                    signals.append({
                        'name': f'{period_name.upper()}',
                        'signal': 'bullish',
                        'description': f'Price above {period_name.upper()} ({ma_float:.2f})',
                    })
                    score += 5
                else:
                    signals.append({
                        'name': f'{period_name.upper()}',
                        'signal': 'bearish',
                        'description': f'Price below {period_name.upper()} ({ma_float:.2f})',
                    })
                    score -= 5

        # MACD analysis
        dif = curr.get('macd_dif')
        dea = curr.get('macd_dea')
        hist = curr.get('macd_histogram')
        if dif is not None and dea is not None:
            if float(dif) > float(dea):
                signals.append({'name': 'MACD', 'signal': 'bullish',
                               'description': 'DIF above DEA'})
                score += 10
            else:
                signals.append({'name': 'MACD', 'signal': 'bearish',
                               'description': 'DIF below DEA'})
                score -= 10

        if prev and hist is not None and prev.get('macd_histogram') is not None:
            if float(hist) > float(prev['macd_histogram']):
                signals.append({'name': 'MACD_MOM', 'signal': 'bullish',
                               'description': 'MACD histogram increasing'})
                score += 5
            else:
                signals.append({'name': 'MACD_MOM', 'signal': 'bearish',
                               'description': 'MACD histogram decreasing'})
                score -= 5

        # RSI analysis
        rsi_6 = curr.get('rsi_6')
        if rsi_6 is not None:
            rsi_val = float(rsi_6)
            if rsi_val > 80:
                signals.append({'name': 'RSI_6', 'signal': 'bearish',
                               'description': f'RSI(6) overbought ({rsi_val:.1f})'})
                score -= 10
            elif rsi_val < 20:
                signals.append({'name': 'RSI_6', 'signal': 'bullish',
                               'description': f'RSI(6) oversold ({rsi_val:.1f})'})
                score += 10
            elif rsi_val > 70:
                signals.append({'name': 'RSI_6', 'signal': 'neutral',
                               'description': f'RSI(6) approaching overbought ({rsi_val:.1f})'})
                score -= 3
            elif rsi_val < 30:
                signals.append({'name': 'RSI_6', 'signal': 'neutral',
                               'description': f'RSI(6) approaching oversold ({rsi_val:.1f})'})
                score += 3

        # Volume ratio
        vol_ratio = curr.get('volume_ratio')
        if vol_ratio is not None:
            indicators['volume_ratio'] = float(vol_ratio)

    # Clamp score
    score = max(-100, min(100, score))

    # Generate summary
    bull_count = sum(1 for s in signals if s['signal'] == 'bullish')
    bear_count = sum(1 for s in signals if s['signal'] == 'bearish')
    if bull_count > bear_count * 1.5:
        summary = 'Overall bullish bias with multiple positive signals'
    elif bear_count > bull_count * 1.5:
        summary = 'Overall bearish bias with multiple negative signals'
    else:
        summary = 'Mixed signals, no clear directional bias'

    return {
        'stock_code': code,
        'trade_date': trade_date,
        'signals': signals,
        'score': score,
        'summary': summary,
        'indicators': indicators,
    }


async def get_fundamental_analysis(stock_code: str) -> dict:
    """Generate fundamental analysis report for a stock.

    [DEPRECATED] This endpoint uses simple rule-based scoring from factor tables.
    The frontend (FundamentalTab) now uses the FiveStepAnalyzer via
    POST /api/analysis/comprehensive/generate (report_type=fundamental) for
    industry-aware LLM-powered analysis. This function is kept for backward
    compatibility with any external API consumers only.
    """
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "[DEPRECATED] get_fundamental_analysis called for %s. "
        "Use FiveStepAnalyzer via /api/analysis/comprehensive/generate instead.",
        stock_code,
    )
    code = _normalize_stock_code(stock_code)

    valuation = []
    profitability = []
    growth = []
    score = 0

    # Fetch valuation factors
    val_sql = """
        SELECT pe_ttm, pb, ps_ttm, market_cap, circ_market_cap
        FROM trade_stock_valuation_factor
        WHERE stock_code = %s
        ORDER BY calc_date DESC LIMIT 1
    """
    val_data = list(execute_query(val_sql, (code,)))
    if val_data:
        v = val_data[0]
        if v.get('pe_ttm') is not None:
            pe = float(v['pe_ttm'])
            valuation.append({'metric': 'PE_TTM', 'value': pe,
                             'description': f'PE ratio: {"Low" if pe < 15 else "Medium" if pe < 30 else "High"}'})
            if pe < 15:
                score += 10
            elif pe > 50:
                score -= 5
        if v.get('pb') is not None:
            pb = float(v['pb'])
            valuation.append({'metric': 'PB', 'value': pb, 'description': f'PB ratio'})
            if pb < 1.5:
                score += 5
        if v.get('market_cap') is not None:
            market_cap = float(v['market_cap'])
            valuation.append({'metric': 'MARKET_CAP', 'value': market_cap,
                             'description': f'Market cap: {market_cap/1e8:.1f}B'})

    # Fetch quality factors
    qual_sql = """
        SELECT roa, current_ratio, debt_ratio, cash_flow_ratio
        FROM trade_stock_quality_factor
        WHERE stock_code = %s
        ORDER BY calc_date DESC LIMIT 1
    """
    qual_data = list(execute_query(qual_sql, (code,)))
    if qual_data:
        q = qual_data[0]
        if q.get('roa') is not None:
            roa = float(q['roa'])
            profitability.append({'metric': 'ROA', 'value': roa,
                                'description': f'Return on assets: {"Good" if roa > 0.05 else "Low"}'})
            if roa > 0.05:
                score += 10
        if q.get('current_ratio') is not None:
            cr = float(q['current_ratio'])
            profitability.append({'metric': 'CURRENT_RATIO', 'value': cr,
                                'description': f'Current ratio: {"Healthy" if cr > 1.5 else "Low"}'})
        if q.get('debt_ratio') is not None:
            dr = float(q['debt_ratio'])
            profitability.append({'metric': 'DEBT_RATIO', 'value': dr,
                                'description': f'Debt ratio: {dr:.1%}'})

    # Fetch extended factors for growth
    ext_sql = """
        SELECT net_profit_growth, revenue_growth
        FROM trade_stock_extended_factor
        WHERE stock_code = %s
        ORDER BY calc_date DESC LIMIT 1
    """
    ext_data = list(execute_query(ext_sql, (code,)))
    if ext_data:
        e = ext_data[0]
        if e.get('net_profit_growth') is not None:
            npg = float(e['net_profit_growth'])
            growth.append({'metric': 'NET_PROFIT_GROWTH', 'value': npg,
                          'description': f'Net profit growth: {npg:.1%}'})
            if npg > 0.2:
                score += 15
            elif npg > 0:
                score += 5
            elif npg < -0.2:
                score -= 10
        if e.get('revenue_growth') is not None:
            rg = float(e['revenue_growth'])
            growth.append({'metric': 'REVENUE_GROWTH', 'value': rg,
                          'description': f'Revenue growth: {rg:.1%}'})

    score = max(-100, min(100, score))

    has_data = valuation or profitability or growth
    if not has_data:
        summary = 'No fundamental data available for this stock'
    elif score > 20:
        summary = 'Fundamentally strong with good valuation and growth metrics'
    elif score < -20:
        summary = 'Fundamental concerns with weak profitability or high valuation'
    else:
        summary = 'Mixed fundamental profile, further analysis recommended'

    return {
        'stock_code': code,
        'valuation': valuation,
        'profitability': profitability,
        'growth': growth,
        'score': score,
        'summary': summary,
    }


# ---------------------------------------------------------------------------
# Tech report functions
# ---------------------------------------------------------------------------

QUOTA_LIMIT = 50


def _get_target_trade_date(stock_code: str) -> str:
    """
    Determine the target trade date for a report.
    After 15:30 (China time) use today; otherwise use the latest trade date in DB.
    """
    now = datetime.now()
    cutoff = now.replace(hour=15, minute=30, second=0, microsecond=0)
    today_str = now.strftime('%Y-%m-%d')

    if now >= cutoff:
        # Check if today has data
        sql = """
            SELECT COUNT(*) as cnt
            FROM trade_stock_daily
            WHERE stock_code = %s AND trade_date = %s
        """
        rows = list(execute_query(sql, (stock_code, today_str), env='online'))
        if rows and rows[0]['cnt'] > 0:
            return today_str

    # Fall back to latest available trade date
    sql = """
        SELECT MAX(trade_date) as latest_date
        FROM trade_stock_daily
        WHERE stock_code = %s
    """
    rows = list(execute_query(sql, (stock_code,), env='online'))
    if rows and rows[0]['latest_date']:
        d = rows[0]['latest_date']
        if isinstance(d, (date, datetime)):
            return d.strftime('%Y-%m-%d')
        return str(d)
    return today_str


def _score_label(score: float) -> str:
    if score >= 40:
        return '强势多头'
    if score >= 20:
        return '多头'
    if score >= -20:
        return '震荡整理'
    if score >= -40:
        return '空头'
    return '强势空头'


def _generate_tech_report(stock_code: str, trade_date: str, stock_name: str = '') -> dict:
    """
    Generate tech report using SingleStockScanner (full pipeline).
    Returns a dict ready for INSERT into trade_tech_report.
    """
    import sys
    import os
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    from strategist.tech_scan.single_scanner import SingleStockScanner
    from strategist.tech_scan.report_engine import ReportEngine
    from strategist.tech_scan.signal_detector import SignalDetector

    scanner = SingleStockScanner(env='online', lookback_days=300, generate_chart=True)
    if stock_name:
        scanner._stock_name_override = stock_name

    # Fetch data and compute indicators (mirrors scanner.scan internals)
    fetcher = scanner.fetcher
    calculator = scanner.calculator
    detector = scanner.detector

    if fetcher._is_etf(stock_code):
        df = fetcher.fetch_etf_data([stock_code], lookback_days=300)
    else:
        df = fetcher.fetch_daily_data([stock_code], lookback_days=300)

    if df.empty:
        raise ValueError(f'No data for {stock_code}')

    df = calculator.calculate_all(df)

    # Merge RPS
    try:
        rps_df = fetcher.fetch_rps_data([stock_code])
        if not rps_df.empty:
            rps_cols = ['stock_code', 'trade_date']
            for col in ['rps_120', 'rps_250', 'rps_slope']:
                if col in rps_df.columns:
                    rps_cols.append(col)
            df = df.merge(rps_df[rps_cols], on=['stock_code', 'trade_date'], how='left')
    except Exception:
        pass

    df = df.sort_values('trade_date')
    latest = df.iloc[-1]

    name = stock_name or scanner._fetch_stock_name(stock_code)

    # Full ReportEngine analysis
    engine = ReportEngine()
    score_result = engine.calc_score(latest)
    ma_pattern = engine.classify_ma_pattern(latest)
    macd_interp = engine.interpret_macd(latest)
    rsi_val = latest.get('rsi')
    rsi_interp = engine.interpret_rsi(rsi_val) if rsi_val is not None and not pd.isna(rsi_val) else None
    kdj_interp = engine.interpret_kdj(latest)
    boll_interp = engine.interpret_boll(latest)
    vp_quadrant = engine.analyze_volume_price(latest)
    divergence = detector.detect_macd_divergence(df) if len(df) >= 20 else {'type': '无背驰', 'confidence': '低', 'description': '数据不足'}
    kdj_signals = detector.detect_kdj_signals(latest)
    alerts = engine.detect_alerts(latest, divergence, kdj_signals)
    supports, resistances = engine.calc_key_levels(latest, df)
    recent_features = engine.analyze_recent_pattern(df)

    # Extract RPS
    rps_120 = rps_250 = rps_slope = None
    for col in ['rps_120', 'rps_250', 'rps_slope']:
        if col in df.columns:
            valid = df[col].dropna()
            if not valid.empty:
                val = valid.iloc[-1]
                if col == 'rps_120':
                    rps_120 = val
                elif col == 'rps_250':
                    rps_250 = val
                else:
                    rps_slope = val

    # Generate HTML report
    html_content = scanner._generate_html_report(
        stock_code, name, df, latest,
        latest['trade_date'].strftime('%Y-%m-%d') if hasattr(latest['trade_date'], 'strftime') else str(latest['trade_date']),
        chart_path=None,
        score_result=score_result, ma_pattern=ma_pattern,
        macd_interp=macd_interp, rsi_interp=rsi_interp,
        kdj_interp=kdj_interp, boll_interp=boll_interp,
        vp_quadrant=vp_quadrant, divergence=divergence,
        kdj_signals=kdj_signals, alerts=alerts,
        supports=supports, resistances=resistances,
        recent_features=recent_features,
        rps_120=rps_120, rps_250=rps_250, rps_slope=rps_slope,
    )

    # Serialize signals from alerts + detector
    signals_raw = detector.detect_all(latest)
    signals_list = []
    max_severity = 'NONE'
    score = int(round(score_result.score * 10))  # convert 0-10 to 0-100 scale
    score = max(-100, min(100, score))

    for sig in signals_raw:
        level_name = sig.level.name
        if level_name == 'RED' and max_severity != 'RED':
            max_severity = 'RED'
        elif level_name == 'YELLOW' and max_severity == 'NONE':
            max_severity = 'YELLOW'
        elif level_name == 'GREEN' and max_severity == 'NONE':
            max_severity = 'GREEN'
        signals_list.append({
            'name': sig.name,
            'level': level_name,
            'description': sig.description,
            'severity': sig.severity.name if sig.severity else '',
            'tag': sig.tag or '',
        })

    label = score_result.trend_label

    # Build indicator snapshot
    indicator_fields = [
        'ma5', 'ma20', 'ma60', 'ma250',
        'macd_dif', 'macd_dea', 'macd_hist',
        'rsi', 'atr_14',
        'boll_upper', 'boll_middle', 'boll_lower',
        'volume_ratio', 'vol_ma5', 'vol_ma20',
        'kdj_k', 'kdj_d', 'kdj_j',
        'close', 'open', 'high', 'low',
    ]
    indicators = {}
    for field in indicator_fields:
        val = latest.get(field)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            try:
                indicators[field] = round(float(val), 4)
            except (TypeError, ValueError):
                pass

    red_cnt = sum(1 for s in signals_list if s['level'] == 'RED')
    green_cnt = sum(1 for s in signals_list if s['level'] == 'GREEN')
    yellow_cnt = sum(1 for s in signals_list if s['level'] == 'YELLOW')
    summary = (
        f'评分 {score_result.score:.1f}/10，{label}，{score_result.action_advice}。'
        f'共 {len(signals_list)} 个信号'
        f'（红灯 {red_cnt}，黄灯 {yellow_cnt}，绿灯 {green_cnt}）。'
        f'均线形态：{ma_pattern.name}。'
    )

    return {
        'stock_code': stock_code,
        'trade_date': trade_date,
        'score': score_result.score * 10,
        'score_label': label,
        'ma_pattern': ma_pattern.name,
        'max_severity': max_severity,
        'summary': summary,
        'signals': json.dumps(signals_list, ensure_ascii=False),
        'indicators': json.dumps(indicators, ensure_ascii=False),
        'html_content': html_content,
        'signal_count': len(signals_list),
    }


async def get_or_generate_tech_report(stock_code: str, stock_name: str = '') -> dict:
    """
    Get cached or generate a new tech report. Returns a dict with extra fields:
    generated (bool), quota_used (int), quota_limit (int).
    """
    code = _normalize_stock_code(stock_code)
    trade_date = _get_target_trade_date(code)
    today_str = datetime.now().strftime('%Y-%m-%d')

    # 1. Check cache
    cache_sql = """
        SELECT id, stock_code, stock_name, trade_date, score, score_label,
               ma_pattern, max_severity, summary, signals, indicators, html_content, created_at
        FROM trade_tech_report
        WHERE stock_code = %s AND trade_date = %s
    """
    rows = list(execute_query(cache_sql, (code, trade_date)))
    quota_sql = "SELECT COUNT(*) as cnt FROM trade_tech_report WHERE trade_date = %s"
    quota_rows = list(execute_query(quota_sql, (today_str,)))
    quota_used = int(quota_rows[0]['cnt']) if quota_rows else 0

    if rows:
        row = rows[0]
        report = _row_to_detail(row)
        return {
            'generated': False,
            'quota_used': quota_used,
            'quota_limit': QUOTA_LIMIT,
            'report': report,
        }

    # 2. Check quota
    if quota_used >= QUOTA_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f'Daily quota exceeded ({QUOTA_LIMIT} reports/day). Try again tomorrow.',
        )

    # 3. Generate
    name = stock_name or ''
    data = _generate_tech_report(code, trade_date, stock_name=name)
    name = name or ''

    insert_sql = """
        INSERT INTO trade_tech_report
            (stock_code, stock_name, trade_date, score, score_label, ma_pattern, max_severity,
             summary, signals, indicators, html_content)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            stock_name   = VALUES(stock_name),
            score        = VALUES(score),
            score_label  = VALUES(score_label),
            ma_pattern   = VALUES(ma_pattern),
            max_severity = VALUES(max_severity),
            summary      = VALUES(summary),
            signals      = VALUES(signals),
            indicators   = VALUES(indicators),
            html_content = VALUES(html_content)
    """
    execute_update(insert_sql, (
        code, name, data['trade_date'],
        data['score'], data['score_label'], data.get('ma_pattern', ''),
        data['max_severity'],
        data['summary'], data['signals'], data['indicators'],
        data.get('html_content', ''),
    ))

    # Re-fetch to get id and created_at
    rows = list(execute_query(cache_sql, (code, data['trade_date'])))
    quota_used += 1
    report = _row_to_detail(rows[0]) if rows else _build_detail_from_data(data, name)

    return {
        'generated': True,
        'quota_used': quota_used,
        'quota_limit': QUOTA_LIMIT,
        'report': report,
    }


def _row_to_detail(row: dict) -> dict:
    """Convert a DB row to TechReportDetail dict."""
    signals = json.loads(row['signals']) if isinstance(row['signals'], str) else (row['signals'] or [])
    indicators = json.loads(row['indicators']) if isinstance(row['indicators'], str) else (row['indicators'] or {})
    trade_date = row['trade_date']
    if isinstance(trade_date, (date, datetime)):
        trade_date = trade_date.strftime('%Y-%m-%d')
    created_at = row.get('created_at', '')
    if isinstance(created_at, datetime):
        created_at = created_at.strftime('%Y-%m-%d %H:%M:%S')

    return {
        'id': row.get('id', 0),
        'stock_code': row['stock_code'],
        'stock_name': row.get('stock_name', ''),
        'trade_date': str(trade_date),
        'score': float(row['score']),
        'score_label': row.get('score_label', ''),
        'ma_pattern': row.get('ma_pattern', ''),
        'max_severity': row.get('max_severity', 'NONE'),
        'summary': row.get('summary', ''),
        'signal_count': len(signals),
        'created_at': str(created_at),
        'signals': signals,
        'indicators': indicators,
        'has_html': bool(row.get('html_content')),
    }


def _build_detail_from_data(data: dict, stock_name: str) -> dict:
    """Build a TechReportDetail dict from generated data (fallback when re-fetch fails)."""
    signals = json.loads(data['signals']) if isinstance(data['signals'], str) else []
    indicators = json.loads(data['indicators']) if isinstance(data['indicators'], str) else {}
    return {
        'id': 0,
        'stock_code': data['stock_code'],
        'stock_name': stock_name,
        'trade_date': data['trade_date'],
        'score': float(data['score']),
        'score_label': data['score_label'],
        'max_severity': data['max_severity'],
        'summary': data['summary'],
        'signal_count': len(signals),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'signals': signals,
        'indicators': indicators,
    }


async def list_tech_reports(limit: int = 20, offset: int = 0) -> dict:
    """List tech reports, ordered by trade_date desc then created_at desc."""
    count_sql = "SELECT COUNT(*) as total FROM trade_tech_report"
    count_rows = list(execute_query(count_sql, ()))
    total = int(count_rows[0]['total']) if count_rows else 0

    list_sql = """
        SELECT id, stock_code, stock_name, trade_date, score, score_label,
               max_severity, summary, signals, created_at
        FROM trade_tech_report
        ORDER BY trade_date DESC, created_at DESC
        LIMIT %s OFFSET %s
    """
    rows = list(execute_query(list_sql, (limit, offset)))

    items = []
    for row in rows:
        signals = json.loads(row['signals']) if isinstance(row['signals'], str) else (row['signals'] or [])
        trade_date = row['trade_date']
        if isinstance(trade_date, (date, datetime)):
            trade_date = trade_date.strftime('%Y-%m-%d')
        created_at = row.get('created_at', '')
        if isinstance(created_at, datetime):
            created_at = created_at.strftime('%Y-%m-%d %H:%M:%S')
        items.append({
            'id': row['id'],
            'stock_code': row['stock_code'],
            'stock_name': row.get('stock_name', ''),
            'trade_date': str(trade_date),
            'score': float(row['score']),
            'score_label': row.get('score_label', ''),
            'max_severity': row.get('max_severity', 'NONE'),
            'summary': row.get('summary', ''),
            'signal_count': len(signals),
            'created_at': str(created_at),
        })

    return {'total': total, 'items': items}


async def get_stock_recent_reports(stock_code: str, days: int = 3) -> list:
    """Return all tech reports for a stock within the last `days` calendar days."""
    code = _normalize_stock_code(stock_code)
    sql = """
        SELECT id, stock_code, stock_name, trade_date, score, score_label,
               ma_pattern, max_severity, summary, signals, indicators, html_content, created_at
        FROM trade_tech_report
        WHERE stock_code = %s
          AND trade_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        ORDER BY trade_date DESC, created_at DESC
    """
    rows = list(execute_query(sql, (code, days)))
    return [_row_to_detail(dict(r)) for r in rows]


async def list_analyzed_stocks() -> dict:
    """
    Return the latest tech report for each distinct stock, PLUS all stocks
    in user_watchlist that have no tech report yet.  Joined with market cap
    and industry info.
    Used for the stock card grid.
    """
    # Latest report per stock
    sql = """
        SELECT t.stock_code, t.stock_name, t.trade_date AS latest_date,
               t.score, t.score_label, t.max_severity, t.summary
        FROM trade_tech_report t
        INNER JOIN (
            SELECT stock_code, MAX(trade_date) AS max_date
            FROM trade_tech_report
            GROUP BY stock_code
        ) latest ON t.stock_code = latest.stock_code AND t.trade_date = latest.max_date
        ORDER BY t.trade_date DESC, t.stock_code
    """
    rows = list(execute_query(sql))

    report_codes = {r['stock_code'] for r in rows}

    # Add watchlist stocks that have no tech report
    wl_sql = """
        SELECT DISTINCT stock_code, stock_name
        FROM user_watchlist
    """
    wl_rows = list(execute_query(wl_sql))
    for wl in wl_rows:
        if wl['stock_code'] not in report_codes:
            rows.append({
                'stock_code': wl['stock_code'],
                'stock_name': wl['stock_name'],
                'latest_date': None,
                'score': None,
                'score_label': '',
                'max_severity': 'NONE',
                'summary': '',
            })

    if not rows:
        return {'data': []}

    codes = [r['stock_code'] for r in rows]
    placeholders = ','.join(['%s'] * len(codes))

    # Latest market cap + PE/PB per stock from trade_stock_daily_basic
    cap_sql = f"""
        SELECT b.stock_code, b.total_mv, b.circ_mv, b.pe_ttm, b.pb
        FROM trade_stock_daily_basic b
        INNER JOIN (
            SELECT stock_code, MAX(trade_date) AS max_date
            FROM trade_stock_daily_basic
            WHERE stock_code IN ({placeholders})
            GROUP BY stock_code
        ) latest ON b.stock_code = latest.stock_code AND b.trade_date = latest.max_date
    """
    cap_rows = list(execute_query(cap_sql, tuple(codes), env='online'))
    cap_map = {r['stock_code']: r for r in cap_rows}

    # Industry from trade_stock_basic — stock_code may or may not have suffix
    # Try with original codes first; fallback to bare codes for compatibility
    ind_placeholders = ','.join(['%s'] * len(codes))
    ind_sql = f"""
        SELECT stock_code, industry, sw_level1, sw_level2
        FROM trade_stock_basic
        WHERE stock_code IN ({ind_placeholders})
    """
    ind_rows = list(execute_query(ind_sql, tuple(codes), env='online'))
    ind_map: dict = {r['stock_code']: r for r in ind_rows}

    # If nothing found, try bare codes (strip .SH/.SZ) for older DB schemas
    if not ind_map:
        bare_codes = [c.split('.')[0] if '.' in c else c for c in codes]
        bare_placeholders = ','.join(['%s'] * len(bare_codes))
        ind_sql2 = f"""
            SELECT stock_code, industry, sw_level1, sw_level2
            FROM trade_stock_basic
            WHERE stock_code IN ({bare_placeholders})
        """
        ind_rows = list(execute_query(ind_sql2, tuple(bare_codes), env='online'))
        ind_map = {r['stock_code']: r for r in ind_rows}

    def _fmt_date(v):
        if v is None:
            return ''
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        return str(v)

    data = []
    for r in rows:
        cap = cap_map.get(r['stock_code'], {})
        # total_mv / circ_mv are already in 亿
        mc_raw  = cap.get('total_mv')
        cmc_raw = cap.get('circ_mv')
        mc  = round(float(mc_raw),  1) if mc_raw  is not None else None
        cmc = round(float(cmc_raw), 1) if cmc_raw is not None else None
        pe_raw = cap.get('pe_ttm')
        pb_raw = cap.get('pb')
        pe = round(float(pe_raw), 2) if pe_raw is not None else None
        pb = round(float(pb_raw), 2) if pb_raw is not None else None
        # ind_map may be keyed by full code or bare code depending on DB schema
        bare = r['stock_code'].split('.')[0] if '.' in r['stock_code'] else r['stock_code']
        ind_row = ind_map.get(r['stock_code']) or ind_map.get(bare) or {}
        data.append({
            'stock_code':      r['stock_code'],
            'stock_name':      r['stock_name'],
            'latest_date':     _fmt_date(r['latest_date']),
            'score':           int(r['score']) if r['score'] is not None else 0,
            'score_label':     r['score_label'] or '',
            'max_severity':    r['max_severity'] or 'NONE',
            'summary':         r['summary'] or '',
            'market_cap':      mc,
            'circ_market_cap': cmc,
            'pe_ttm':          pe,
            'pb':              pb,
            'industry':        ind_row.get('industry', ''),
            'sw_level1':       ind_row.get('sw_level1', '') or ind_row.get('industry', ''),
            'sw_level2':       ind_row.get('sw_level2', ''),
        })

    return {'data': data}


async def list_industry_tree() -> dict:
    """
    Return the SW industry hierarchy (level1 -> level2) with stock counts.
    Structure:
    {
      "tree": [
        {
          "name": "电子",
          "count": 477,
          "children": [
            {"name": "半导体", "count": 171},
            ...
          ]
        },
        ...
      ]
    }
    Falls back to level1-only when sw_level2 data is sparse.
    """
    sql = """
        SELECT industry, sw_level1, sw_level2, COUNT(*) as cnt
        FROM trade_stock_basic
        WHERE (sw_level1 IS NOT NULL AND sw_level1 != '')
           OR (industry IS NOT NULL AND industry != '')
        GROUP BY industry, sw_level1, sw_level2
    """
    rows = list(execute_query(sql, env='online'))

    # Aggregate: level1 -> {level2 -> count}
    l1_totals: dict = {}
    l1_children: dict = {}

    for r in rows:
        l1 = r['sw_level1'] or r['industry']
        l2 = r['sw_level2'] or ''
        cnt = int(r['cnt'])

        l1_totals[l1] = l1_totals.get(l1, 0) + cnt
        if l2:
            if l1 not in l1_children:
                l1_children[l1] = {}
            l1_children[l1][l2] = l1_children[l1].get(l2, 0) + cnt

    tree = []
    for l1, total in sorted(l1_totals.items(), key=lambda x: -x[1]):
        children = []
        if l1 in l1_children:
            for l2, cnt in sorted(l1_children[l1].items(), key=lambda x: -x[1]):
                children.append({'name': l2, 'count': cnt})
        tree.append({'name': l1, 'count': total, 'children': children})

    return {'tree': tree}


async def get_tech_report_html(report_id: int) -> Optional[str]:
    """Return the raw HTML content for a report by id."""
    sql = "SELECT html_content FROM trade_tech_report WHERE id = %s"
    rows = list(execute_query(sql, (report_id,)))
    if not rows:
        return None
    return rows[0].get('html_content') or ''


async def get_tech_report_detail(stock_code: str, trade_date_str: str) -> dict:
    """Get full report detail including signals and indicators JSON."""
    code = _normalize_stock_code(stock_code)
    sql = """
        SELECT id, stock_code, stock_name, trade_date, score, score_label,
               ma_pattern, max_severity, summary, signals, indicators, html_content, created_at
        FROM trade_tech_report
        WHERE stock_code = %s AND trade_date = %s
    """
    rows = list(execute_query(sql, (code, trade_date_str)))
    if not rows:
        raise HTTPException(status_code=404, detail=f'Report not found for {code} on {trade_date_str}')
    return _row_to_detail(rows[0])


# ---------------------------------------------------------------------------
# 估值分位服务
# ---------------------------------------------------------------------------

async def get_industry_valuation_temperature(trade_date: str = None) -> dict:
    """
    获取申万一级行业估值温度（最新日或指定日）。
    """
    if trade_date:
        date_filter = 'trade_date = %s'
        params = (trade_date,)
    else:
        date_filter = 'trade_date = (SELECT MAX(trade_date) FROM sw_industry_valuation)'
        params = ()

    sql = f"""
        SELECT trade_date, sw_name, pe_ttm, pe_ttm_eq, pe_ttm_med,
               pb, pb_med, pe_pct_5y, pb_pct_5y, pe_pct_10y, pb_pct_10y,
               valuation_score, valuation_label
        FROM sw_industry_valuation
        WHERE {date_filter}
        ORDER BY valuation_score ASC
    """
    rows = list(execute_query(sql, params, env='online'))
    if not rows:
        return {'date': trade_date or '', 'items': []}

    actual_date = str(rows[0]['trade_date']) if rows else ''
    items = []
    for r in rows:
        items.append({
            'name': r['sw_name'],
            'pe_ttm': float(r['pe_ttm']) if r['pe_ttm'] is not None else None,
            'pe_ttm_eq': float(r['pe_ttm_eq']) if r['pe_ttm_eq'] is not None else None,
            'pe_ttm_med': float(r['pe_ttm_med']) if r['pe_ttm_med'] is not None else None,
            'pb': float(r['pb']) if r['pb'] is not None else None,
            'pb_med': float(r['pb_med']) if r['pb_med'] is not None else None,
            'pe_pct_5y': float(r['pe_pct_5y']) if r['pe_pct_5y'] is not None else None,
            'pb_pct_5y': float(r['pb_pct_5y']) if r['pb_pct_5y'] is not None else None,
            'pe_pct_10y': float(r['pe_pct_10y']) if r['pe_pct_10y'] is not None else None,
            'pb_pct_10y': float(r['pb_pct_10y']) if r['pb_pct_10y'] is not None else None,
            'valuation_score': float(r['valuation_score']) if r['valuation_score'] is not None else None,
            'valuation_label': r['valuation_label'] or '',
        })

    return {'date': actual_date, 'items': items}


async def get_industry_valuation_history(industry_name: str, metric: str = 'pe_ttm', years: int = 5) -> dict:
    """
    获取某行业估值历史走势 + 分位带。

    metric: pe_ttm | pe_ttm_med | pb | pb_med
    years: 5 | 10
    """
    allowed_metrics = {'pe_ttm', 'pe_ttm_eq', 'pe_ttm_med', 'pb', 'pb_med'}
    if metric not in allowed_metrics:
        raise HTTPException(status_code=400, detail=f'metric must be one of {allowed_metrics}')

    from datetime import date, timedelta
    start = (date.today() - timedelta(days=int(years) * 365)).strftime('%Y-%m-%d')

    sql = f"""
        SELECT trade_date, {metric} as value, pe_pct_5y, pb_pct_5y,
               valuation_score, valuation_label
        FROM sw_industry_valuation
        WHERE sw_name = %s AND trade_date >= %s
        ORDER BY trade_date ASC
    """
    rows = list(execute_query(sql, (industry_name, start), env='online'))
    if not rows:
        return {'industry': industry_name, 'metric': metric, 'history': [], 'percentile_bands': {}}

    history = [
        {
            'date': str(r['trade_date']),
            'value': float(r['value']) if r['value'] is not None else None,
        }
        for r in rows
    ]

    # 计算分位带（基于同期历史数据）
    values = [h['value'] for h in history if h['value'] is not None]
    if values:
        arr = sorted(values)
        n = len(arr)
        p20 = arr[int(n * 0.2)]
        p50 = arr[int(n * 0.5)]
        p80 = arr[int(n * 0.8)]
        percentile_bands = {'p20': p20, 'p50': p50, 'p80': p80}
    else:
        percentile_bands = {}

    # 最新估值状态
    latest_row = rows[-1]
    current = {
        'date': str(latest_row['trade_date']),
        'value': float(latest_row['value']) if latest_row['value'] is not None else None,
        'valuation_score': float(latest_row['valuation_score']) if latest_row['valuation_score'] is not None else None,
        'valuation_label': latest_row['valuation_label'] or '',
    }

    return {
        'industry': industry_name,
        'metric': metric,
        'current': current,
        'history': history,
        'percentile_bands': percentile_bands,
    }


async def get_stock_valuation_history(stock_code: str, years: int = 5) -> dict:
    """
    获取个股历史 PE/PB 走势 + 历史分位带。
    """
    code = _normalize_stock_code(stock_code)
    from datetime import date, timedelta
    start = (date.today() - timedelta(days=int(years) * 365)).strftime('%Y-%m-%d')

    # 基本信息
    info = list(execute_query(
        'SELECT stock_name FROM trade_stock_basic WHERE stock_code = %s',
        (code,), env='online'
    ))
    stock_name = info[0]['stock_name'] if info else code

    # 历史 PE/PB
    sql = """
        SELECT trade_date, pe_ttm, pb
        FROM trade_stock_daily_basic
        WHERE stock_code = %s AND trade_date >= %s
          AND pe_ttm > 0 AND pe_ttm < 300
          AND pb > 0
        ORDER BY trade_date ASC
    """
    rows = list(execute_query(sql, (code, start), env='online'))
    if not rows:
        return {'code': code, 'name': stock_name, 'history': [], 'percentile_bands': {}}

    history = [
        {
            'date': str(r['trade_date']),
            'pe_ttm': float(r['pe_ttm']) if r['pe_ttm'] is not None else None,
            'pb': float(r['pb']) if r['pb'] is not None else None,
        }
        for r in rows
    ]

    # 分位带
    pe_vals = sorted([h['pe_ttm'] for h in history if h['pe_ttm'] is not None])
    pb_vals = sorted([h['pb'] for h in history if h['pb'] is not None])
    n_pe, n_pb = len(pe_vals), len(pb_vals)

    percentile_bands = {}
    if n_pe >= 10:
        percentile_bands['pe_ttm'] = {
            'p20': pe_vals[int(n_pe * 0.2)],
            'p50': pe_vals[int(n_pe * 0.5)],
            'p80': pe_vals[int(n_pe * 0.8)],
        }
    if n_pb >= 10:
        percentile_bands['pb'] = {
            'p20': pb_vals[int(n_pb * 0.2)],
            'p50': pb_vals[int(n_pb * 0.5)],
            'p80': pb_vals[int(n_pb * 0.8)],
        }

    latest = rows[-1]
    current = {
        'date': str(latest['trade_date']),
        'pe_ttm': float(latest['pe_ttm']) if latest['pe_ttm'] is not None else None,
        'pb': float(latest['pb']) if latest['pb'] is not None else None,
    }
    # 当前 PE 在历史中的分位
    if pe_vals and current['pe_ttm']:
        current['pe_pct'] = round(sum(1 for v in pe_vals if v < current['pe_ttm']) / n_pe, 3)
    if pb_vals and current['pb']:
        current['pb_pct'] = round(sum(1 for v in pb_vals if v < current['pb']) / n_pb, 3)

    return {
        'code': code,
        'name': stock_name,
        'current': current,
        'history': history,
        'percentile_bands': percentile_bands,
    }
