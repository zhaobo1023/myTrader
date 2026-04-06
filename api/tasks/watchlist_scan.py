# api/tasks/watchlist_scan.py
# -*- coding: utf-8 -*-
"""
Celery tasks for daily watchlist scan.
Uses sync pymysql (Celery worker context - no async).
Reuses strategist/tech_scan/ modules for 5-dimension scoring.
"""
import json
import logging
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from api.tasks.celery_app import celery_app

logger = logging.getLogger('myTrader.tasks.scan')


def _get_sync_db():
    """Get sync pymysql connection (Celery worker environment, no async)."""
    import pymysql
    from api.config import get_settings
    settings = get_settings()
    if settings.db_env == 'online':
        return pymysql.connect(
            host=settings.online_db_host,
            port=settings.online_db_port,
            user=settings.online_db_user,
            password=settings.online_db_password,
            database=settings.online_db_name,
            charset='utf8',
            cursorclass=pymysql.cursors.DictCursor,
        )
    return pymysql.connect(
        host=settings.local_db_host,
        port=settings.local_db_port,
        user=settings.local_db_user,
        password=settings.local_db_password,
        database=settings.local_db_name,
        charset='utf8',
        cursorclass=pymysql.cursors.DictCursor,
    )


def _run_scan_for_stock(stock_code: str, scan_date: date) -> dict | None:
    """
    Run 5-dimension scan for one stock.
    Returns dict with score/signals or None if data unavailable.
    Gracefully handles missing strategist/tech_scan modules.
    """
    try:
        from strategist.tech_scan.data_fetcher import TechScanDataFetcher
        from strategist.tech_scan.indicator_calculator import IndicatorCalculator
        from strategist.tech_scan.signal_detector import SignalDetector
        from strategist.tech_scan.report_engine import ReportEngine
    except ImportError as e:
        logger.warning('[SCAN] tech_scan module not available: %s', e)
        return None

    try:
        fetcher = TechScanDataFetcher()
        calc = IndicatorCalculator()
        detector = SignalDetector()
        engine = ReportEngine()

        df = fetcher.fetch_stock_data(stock_code, end_date=scan_date.strftime('%Y-%m-%d'))
        if df is None or df.empty:
            logger.warning('[SCAN] no data for %s on %s', stock_code, scan_date)
            return None

        df = calc.calc_indicators(df)
        latest = df.iloc[-1]
        signals = detector.detect_all(df)
        score_result = engine.calc_score(latest)

        severity_order = {'RED': 3, 'YELLOW': 2, 'GREEN': 1, 'INFO': 0, 'NONE': -1}
        max_severity = 'NONE'
        for sig in signals:
            sev = sig.get('severity', 'NONE')
            if severity_order.get(sev, -1) > severity_order.get(max_severity, -1):
                max_severity = sev

        return {
            'score': score_result.get('total', 0.0),
            'score_label': score_result.get('label', ''),
            'dimension_scores': json.dumps(score_result.get('dimensions', {}), ensure_ascii=True),
            'signals': json.dumps(signals, ensure_ascii=True),
            'max_severity': max_severity,
        }
    except Exception as e:
        logger.error('[SCAN] error scanning stock %s: %s', stock_code, e)
        return None


@celery_app.task(name='watchlist_scan.scan_all_users', bind=True)
def scan_all_users_watchlist(self):
    """Trigger per-user scan tasks for all users with watchlists."""
    today = date.today()
    conn = _get_sync_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT DISTINCT user_id FROM user_watchlist')
            user_ids = [r['user_id'] for r in cur.fetchall()]
        logger.info('[SCAN] starting daily scan for %d users', len(user_ids))
        for user_id in user_ids:
            scan_user_watchlist.delay(user_id, today.isoformat())
    finally:
        conn.close()


@celery_app.task(name='watchlist_scan.scan_user', bind=True, max_retries=2)
def scan_user_watchlist(self, user_id: int, scan_date_str: str):
    """Scan all watchlist stocks for one user, write results, send notifications."""
    scan_date = date.fromisoformat(scan_date_str)
    conn = _get_sync_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT stock_code, stock_name FROM user_watchlist WHERE user_id = %s',
                (user_id,)
            )
            stocks = cur.fetchall()
            cur.execute(
                'SELECT * FROM user_notification_configs WHERE user_id = %s AND enabled = 1',
                (user_id,)
            )
            notify_config = cur.fetchone()

        if not stocks:
            logger.info('[SCAN] user=%d has no watchlist stocks', user_id)
            return

        logger.info('[SCAN] user=%d scanning %d stocks for %s', user_id, len(stocks), scan_date)

        for stock in stocks:
            code = stock['stock_code']
            name = stock['stock_name']
            try:
                result = _run_scan_for_stock(code, scan_date)
                if result is None:
                    continue

                with conn.cursor() as cur:
                    cur.execute('''
                        INSERT INTO user_scan_results
                            (user_id, stock_code, stock_name, scan_date, score, score_label,
                             dimension_scores, signals, max_severity, notified)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
                        ON DUPLICATE KEY UPDATE
                            score=VALUES(score), score_label=VALUES(score_label),
                            dimension_scores=VALUES(dimension_scores),
                            signals=VALUES(signals), max_severity=VALUES(max_severity),
                            notified=0
                    ''', (
                        user_id, code, name, scan_date,
                        result['score'], result['score_label'],
                        result['dimension_scores'], result['signals'],
                        result['max_severity'],
                    ))
                    conn.commit()

                if notify_config:
                    _maybe_send_notification(notify_config, code, name, scan_date, result)

            except Exception as e:
                logger.error('[SCAN] error processing stock=%s user=%d: %s', code, user_id, e)
                continue

    finally:
        conn.close()


def _maybe_send_notification(notify_config: dict, stock_code: str, stock_name: str,
                              scan_date: date, result: dict):
    """Evaluate config and send Feishu card if conditions are met."""
    from api.services.notification_sender import should_notify, build_feishu_card, send_webhook_notification

    class _Config:
        def __init__(self, d):
            self.enabled = bool(d.get('enabled', 1))
            self.webhook_url = d.get('webhook_url')
            self.notify_on_red = bool(d.get('notify_on_red', 1))
            self.notify_on_yellow = bool(d.get('notify_on_yellow', 0))
            self.notify_on_green = bool(d.get('notify_on_green', 0))
            self.score_threshold = d.get('score_threshold')

    config_obj = _Config(notify_config)
    if not should_notify(config_obj, result['max_severity'], result['score']):
        return

    signals = json.loads(result['signals'])
    card = build_feishu_card(
        stock_code=stock_code,
        stock_name=stock_name,
        scan_date=scan_date,
        score=result['score'],
        score_label=result['score_label'],
        signals=signals,
        max_severity=result['max_severity'],
    )
    sent = send_webhook_notification(config_obj.webhook_url, card)
    if sent:
        logger.info('[NOTIFY] sent webhook: stock=%s severity=%s', stock_code, result['max_severity'])
