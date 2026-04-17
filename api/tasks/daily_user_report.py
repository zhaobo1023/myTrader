# -*- coding: utf-8 -*-
"""
Celery tasks for per-user daily report generation.

After market close, generates a personalized report for each user
based on their positions and watchlist, then delivers it to their inbox.
"""
import logging
from datetime import date

from api.tasks.celery_app import celery_app
from config.db import execute_query

logger = logging.getLogger('myTrader.api')


@celery_app.task(name='daily_user_report.generate_all', bind=True, max_retries=2, default_retry_delay=60)
def generate_all_user_reports(self, scan_date: str = None):
    """
    Dispatch per-user report generation for all eligible users.

    Triggered after market close (e.g., 17:00 via Celery beat).
    """
    if scan_date is None:
        scan_date = date.today().isoformat()

    # Find all users with daily_report_enabled
    # If notification config doesn't exist, default is enabled
    users = execute_query("""
        SELECT u.id, u.username
        FROM users u
        LEFT JOIN user_notification_configs nc ON nc.user_id = u.id
        WHERE u.is_active = 1
          AND (nc.id IS NULL OR nc.daily_report_enabled = 1)
    """, env='online')

    if not users:
        logger.info('[DAILY_REPORT] No eligible users found')
        return {'dispatched': 0}

    dispatched = 0
    for user in users:
        # Check if user has any positions or watchlist items
        has_data = execute_query("""
            SELECT 1 FROM user_positions WHERE user_id = %s AND is_active = 1
            UNION
            SELECT 1 FROM user_watchlist WHERE user_id = %s
            LIMIT 1
        """, (user['id'], user['id']), env='online')

        if has_data:
            generate_user_report.delay(user['id'], scan_date)
            dispatched += 1

    logger.info('[DAILY_REPORT] Dispatched %s user reports for %s', dispatched, scan_date)
    return {'dispatched': dispatched, 'scan_date': scan_date}


@celery_app.task(name='daily_user_report.generate_one', bind=True, max_retries=3, default_retry_delay=30)
def generate_user_report(self, user_id: int, scan_date: str):
    """
    Generate daily report for a single user and save to inbox.
    """
    from api.services.inbox_service import create_message

    logger.info('[DAILY_REPORT] Generating report for user=%s date=%s', user_id, scan_date)

    # 1. Fetch user's positions
    positions = execute_query("""
        SELECT stock_code, stock_name, level, shares, cost_price
        FROM user_positions
        WHERE user_id = %s AND is_active = 1
        ORDER BY level, stock_code
    """, (user_id,), env='online')

    # 2. Fetch user's watchlist
    watchlist = execute_query("""
        SELECT stock_code, stock_name, note
        FROM user_watchlist
        WHERE user_id = %s
        ORDER BY added_at DESC
    """, (user_id,), env='online')

    # 3. Build report content
    sections = []
    sections.append(f'# {scan_date} 持仓日报\n')

    if positions:
        sections.append('## 持仓概览\n')
        sections.append('| 代码 | 名称 | 层级 | 股数 | 成本 |')
        sections.append('|------|------|------|------|------|')
        for p in positions:
            code = p.get('stock_code', '')
            name = p.get('stock_name', '')
            level = p.get('level', '-')
            shares = p.get('shares', '-')
            cost = p.get('cost_price', '-')
            if cost and cost != '-':
                cost = f'{float(cost):.2f}'
            sections.append(f'| {code} | {name} | {level} | {shares} | {cost} |')
        sections.append('')

        # Try to fetch latest prices for P&L
        codes = [p['stock_code'] for p in positions if p.get('stock_code')]
        if codes:
            placeholders = ','.join(['%s'] * len(codes))
            sql = """
                SELECT stock_code, close, pct_change
                FROM trade_stock_daily
                WHERE stock_code IN ({ph})
                  AND trade_date = (SELECT MAX(trade_date) FROM trade_stock_daily)
            """.format(ph=placeholders)
            latest = execute_query(sql, codes, env='online')

            if latest:
                price_map = {r['stock_code']: r for r in latest}
                sections.append('## 今日行情\n')
                sections.append('| 代码 | 名称 | 收盘价 | 涨跌幅 |')
                sections.append('|------|------|--------|--------|')
                for p in positions:
                    code = p['stock_code']
                    price_info = price_map.get(code)
                    if price_info:
                        close = f"{float(price_info['close']):.2f}"
                        pct = price_info.get('pct_change')
                        pct_str = f"{float(pct):.2f}%" if pct else '-'
                        sections.append(f"| {code} | {p.get('stock_name', '')} | {close} | {pct_str} |")
                sections.append('')
    else:
        sections.append('> 暂无持仓数据\n')

    if watchlist:
        sections.append('## 关注列表\n')
        sections.append('| 代码 | 名称 | 备注 |')
        sections.append('|------|------|------|')
        for w in watchlist:
            note = w.get('note', '') or ''
            sections.append(f"| {w['stock_code']} | {w.get('stock_name', '')} | {note} |")
        sections.append('')

    content = '\n'.join(sections)
    title = f'{scan_date} 持仓日报'

    # 4. Save to inbox
    msg_id = create_message(
        user_id=user_id,
        message_type='daily_report',
        title=title,
        content=content,
        metadata={'scan_date': scan_date, 'positions_count': len(positions), 'watchlist_count': len(watchlist)},
        env='online',
    )

    logger.info('[DAILY_REPORT] Report saved to inbox msg_id=%s for user=%s', msg_id, user_id)
    return {'user_id': user_id, 'message_id': msg_id, 'scan_date': scan_date}
