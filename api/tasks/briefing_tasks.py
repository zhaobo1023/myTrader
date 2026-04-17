# -*- coding: utf-8 -*-
"""
Celery tasks for automated briefing generation, publishing, and data health monitoring.

Schedule:
- 08:30 (Mon-Fri): Generate morning briefing -> publish to Feishu
- 16:30 (Mon-Fri): Pre-check data dependencies for evening briefing
- 17:00 (Mon-Fri): Generate evening briefing -> publish to Feishu
- 21:00 (Mon-Fri): Push daily data health report to Feishu
"""
import logging

from api.tasks.celery_app import celery_app

logger = logging.getLogger('myTrader.briefing_tasks')


@celery_app.task(bind=True, name='generate_briefing_async')
def generate_briefing_async(self, task_id: str, session: str):
    """按需生成 briefing（不发飞书），结果写入 trade_briefing 表。"""
    import asyncio
    from api.services.global_asset_briefing import generate_briefing

    logger.info('[BRIEFING] Async generate start: task_id=%s session=%s', task_id, session)
    try:
        result = asyncio.run(generate_briefing(session))
        logger.info('[BRIEFING] Async generate done: task_id=%s', task_id)
        return {'task_id': task_id, 'status': 'done', 'session': session}
    except Exception as e:
        logger.exception('[BRIEFING] Async generate failed: task_id=%s error=%s', task_id, e)
        raise


@celery_app.task(bind=True, name='publish_morning_briefing')
def publish_morning_briefing(self):
    """Generate and publish morning briefing to Feishu."""
    import asyncio
    from api.services.feishu_doc_publisher import publish_latest_briefing

    logger.info('[BRIEFING] Starting morning briefing publish')
    try:
        result = asyncio.run(publish_latest_briefing('morning', force=True))
        logger.info('[BRIEFING] Morning briefing published: %s', result.get('url'))
        return {'status': 'ok', 'url': result.get('url'), 'date': result.get('date')}
    except Exception as e:
        logger.exception('[BRIEFING] Morning briefing failed: %s', e)
        # Send error notification via bot
        _notify_error('晨报生成失败', str(e))
        raise


@celery_app.task(bind=True, name='publish_evening_briefing')
def publish_evening_briefing(self):
    """Generate and publish evening briefing to Feishu."""
    import asyncio
    from api.services.feishu_doc_publisher import publish_latest_briefing

    logger.info('[BRIEFING] Starting evening briefing publish')
    try:
        result = asyncio.run(publish_latest_briefing('evening', force=True))
        logger.info('[BRIEFING] Evening briefing published: %s', result.get('url'))
        return {'status': 'ok', 'url': result.get('url'), 'date': result.get('date')}
    except Exception as e:
        logger.exception('[BRIEFING] Evening briefing failed: %s', e)
        _notify_error('复盘生成失败', str(e))
        raise


@celery_app.task(bind=True, name='precheck_evening_data')
def precheck_evening_data(self):
    """
    Pre-check data dependencies at 16:30 before evening briefing at 17:00.

    Checks if today's data has landed for:
    - A-share daily prices (trade_stock_daily)
    - ETF daily prices (trade_etf_daily)
    - Limit-up/down details (trade_limit_stock_detail)
    - Dashboard signals

    If any critical data is missing, sends a Feishu alert.
    """
    from datetime import date
    from config.db import execute_query

    logger.info('[PRECHECK] Starting evening data pre-check')
    today = date.today()
    today_str = today.strftime('%Y-%m-%d')

    # Skip weekends
    if today.weekday() >= 5:
        logger.info('[PRECHECK] Weekend, skipping')
        return {'status': 'skipped', 'reason': 'weekend'}

    checks = [
        ('A股日线', "SELECT MAX(trade_date) AS d FROM trade_stock_daily"),
        ('ETF日线', "SELECT MAX(trade_date) AS d FROM trade_etf_daily"),
        ('涨跌停明细', "SELECT MAX(trade_date) AS d FROM trade_limit_stock_detail"),
        ('LogBias', "SELECT MAX(trade_date) AS d FROM trade_log_bias_daily"),
        ('基础因子', "SELECT MAX(calc_date) AS d FROM trade_stock_basic_factor"),
    ]

    missing = []
    ok = []

    for label, sql in checks:
        try:
            rows = execute_query(sql, env='online')
            if rows and rows[0].get('d'):
                latest = rows[0]['d']
                if hasattr(latest, 'isoformat'):
                    latest_str = latest.isoformat()
                else:
                    latest_str = str(latest)[:10]

                if latest_str >= today_str:
                    ok.append(label)
                else:
                    missing.append('{} (最新: {})'.format(label, latest_str))
            else:
                missing.append('{} (无数据)'.format(label))
        except Exception as e:
            missing.append('{} (查询失败: {})'.format(label, str(e)[:40]))

    result = {
        'status': 'ok' if not missing else 'warn',
        'date': today_str,
        'ok': ok,
        'missing': missing,
    }

    if missing:
        logger.warning('[PRECHECK] Missing data: %s', missing)
        # Send alert
        alert_lines = ['**[WARN] 复盘数据预检 (16:30)**', '']
        alert_lines.append('以下数据尚未更新到今日:')
        for m in missing:
            alert_lines.append('- {}'.format(m))
        alert_lines.append('')
        alert_lines.append('已就绪: {}'.format(', '.join(ok) if ok else '无'))
        alert_lines.append('')
        alert_lines.append('17:00 复盘将使用可用数据生成，数据不全可能影响质量')

        _send_card(
            title='复盘数据预检 [{}项未就绪]'.format(len(missing)),
            content='\n'.join(alert_lines),
            color='orange',
        )
    else:
        logger.info('[PRECHECK] All data ready: %s', ok)

    return result


@celery_app.task(bind=True, name='push_daily_health_report')
def push_daily_health_report(self):
    """Push daily data health report to Feishu bot."""
    from api.services.daily_health_report import push_health_report

    logger.info('[HEALTH] Pushing daily health report')
    try:
        result = push_health_report()
        logger.info('[HEALTH] Report pushed: level=%s, status=%s',
                    result.get('level'), result.get('push_status'))
        return {
            'status': result.get('push_status', 'unknown'),
            'level': result.get('level'),
            'summary': result.get('summary'),
        }
    except Exception as e:
        logger.exception('[HEALTH] Health report failed: %s', e)
        raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _notify_error(title: str, error: str):
    """Send error notification via Feishu bot."""
    _send_card(
        title='[ERROR] {}'.format(title),
        content='```\n{}\n```'.format(error[:500]),
        color='red',
    )


def _send_card(title: str, content: str, color: str = 'blue'):
    """Send a simple card message to the owner."""
    import json
    import httpx

    try:
        from api.services.feishu_doc_publisher import _headers, _OWNER_OPEN_ID

        card = {
            'config': {'wide_screen_mode': True},
            'header': {
                'title': {'tag': 'plain_text', 'content': title},
                'template': color,
            },
            'elements': [{
                'tag': 'div',
                'text': {'tag': 'lark_md', 'content': content},
            }],
        }

        msg = {
            'receive_id': _OWNER_OPEN_ID,
            'msg_type': 'interactive',
            'content': json.dumps(card, ensure_ascii=False),
        }

        resp = httpx.post(
            'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id',
            headers=_headers(),
            json=msg,
            timeout=15,
        )
        data = resp.json()
        if data.get('code') != 0:
            logger.warning('Card send failed: %s', data.get('msg'))
    except Exception as e:
        logger.warning('Failed to send card: %s', e)
