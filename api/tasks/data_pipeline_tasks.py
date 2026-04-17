# -*- coding: utf-8 -*-
"""
Celery tasks for the full data pipeline: data supplement, sentiment,
indicators, and maintenance tasks.

These wrap scheduler/adapters.py functions and are referenced by
the beat_schedule in celery_app.py.
"""
import logging

from api.tasks.celery_app import celery_app

logger = logging.getLogger('myTrader.data_pipeline')


# ---------------------------------------------------------------------------
# Data supplement tasks (moneyflow, margin, north holding)
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name='fetch_moneyflow_daily')
def fetch_moneyflow_daily(self):
    """Daily incremental fetch of trade_stock_moneyflow."""
    logger.info('[PIPELINE] fetch_moneyflow_daily start')
    from scheduler.adapters import fetch_moneyflow_incremental
    fetch_moneyflow_incremental(envs='online')
    return {'status': 'ok'}


@celery_app.task(bind=True, name='fetch_margin_daily')
def fetch_margin_daily(self):
    """Daily incremental fetch of trade_margin_trade."""
    logger.info('[PIPELINE] fetch_margin_daily start')
    from scheduler.adapters import fetch_margin_incremental
    fetch_margin_incremental(envs='online')
    return {'status': 'ok'}


@celery_app.task(bind=True, name='fetch_north_holding_daily')
def fetch_north_holding_daily(self):
    """Daily incremental fetch of trade_north_holding."""
    logger.info('[PIPELINE] fetch_north_holding_daily start')
    from scheduler.adapters import fetch_north_holding_incremental
    fetch_north_holding_incremental(envs='online')
    return {'status': 'ok'}


# ---------------------------------------------------------------------------
# Sentiment tasks
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name='fetch_news_sentiment')
def fetch_news_sentiment(self):
    """Fetch news + LLM sentiment analysis for watched stocks."""
    logger.info('[PIPELINE] fetch_news_sentiment start')
    from scheduler.adapters import run_sentiment_news
    run_sentiment_news(stock_codes='002594,600519,000858,601318')
    return {'status': 'ok'}


@celery_app.task(bind=True, name='fetch_event_signals')
def fetch_event_signals(self):
    """Detect keyword-based events from news."""
    logger.info('[PIPELINE] fetch_event_signals start')
    from scheduler.adapters import run_sentiment_events
    run_sentiment_events()
    return {'status': 'ok'}


@celery_app.task(bind=True, name='fetch_polymarket')
def fetch_polymarket(self):
    """Fetch Polymarket smart-money signals."""
    logger.info('[PIPELINE] fetch_polymarket start')
    from scheduler.adapters import run_sentiment_polymarket
    run_sentiment_polymarket()
    return {'status': 'ok'}


# ---------------------------------------------------------------------------
# Indicator & strategy tasks
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name='sync_concept_board')
def sync_concept_board(self):
    """Sync Eastmoney concept board memberships into stock_concept_map."""
    logger.info('[PIPELINE] sync_concept_board start')
    from scheduler.adapters import sync_concept_board as _fn
    _fn()
    return {'status': 'ok'}


@celery_app.task(bind=True, name='monitor_candidate_pool')
def monitor_candidate_pool(self):
    """Daily candidate pool monitor + Feishu push."""
    logger.info('[PIPELINE] monitor_candidate_pool start')
    from scheduler.adapters import monitor_candidate_pool as _fn
    _fn()
    return {'status': 'ok'}


@celery_app.task(bind=True, name='fetch_dashboard_data')
def fetch_dashboard_data(self):
    """Fetch market dashboard indicators."""
    logger.info('[PIPELINE] fetch_dashboard_data start')
    from scheduler.adapters import run_dashboard_fetch
    run_dashboard_fetch()
    return {'status': 'ok'}


@celery_app.task(bind=True, name='compute_dashboard')
def compute_dashboard(self):
    """Compute 6-section dashboard and warm Redis cache."""
    logger.info('[PIPELINE] compute_dashboard start')
    from scheduler.adapters import run_dashboard_compute
    run_dashboard_compute()
    return {'status': 'ok'}


@celery_app.task(bind=True, name='calc_sw_valuation')
def calc_sw_valuation(self):
    """Calculate SW industry valuation percentile."""
    logger.info('[PIPELINE] calc_sw_valuation start')
    from data_analyst.fetchers.sw_industry_valuation_fetcher import run_daily
    run_daily()
    return {'status': 'ok'}


@celery_app.task(bind=True, name='check_data_completeness')
def check_data_completeness(self):
    """Morning data completeness check."""
    logger.info('[PIPELINE] check_data_completeness start')
    from scheduler.check_data_completeness import run_check
    result = run_check(env='online')
    return {'status': 'ok', 'summary': result}


# ---------------------------------------------------------------------------
# Nightly curated opinion report (23:00)
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name='run_nightly_digest')
def run_nightly_digest(self):
    """Export wechat2rss articles, two-stage LLM digest, curated report -> Feishu."""
    import asyncio
    import subprocess

    logger.info('[PIPELINE] run_nightly_digest start')

    # Step 0: Run export script on server (reads res.db -> JSON)
    try:
        from api.config import settings
        export_script = (
            getattr(settings, 'ARTICLE_EXPORT_SCRIPT', '') or
            '/app/scripts/export_wechat_articles.py'
        )
        proc = subprocess.run(
            ['python3', export_script], check=True, timeout=60,
            capture_output=True, text=True,
        )
        logger.info('[PIPELINE] Export script completed: %s', proc.stdout[:200] if proc.stdout else '')
    except Exception as e:
        logger.error('[PIPELINE] Export script failed: %s', e)
        return {'status': 'error', 'reason': 'export_failed', 'error': str(e)}

    # Step 1+2+3: Two-stage digest + categorized reports
    from api.services.article_digest_service import run_nightly_digest_pipeline
    result = asyncio.run(run_nightly_digest_pipeline())
    reports = result.get('reports', [])
    logger.info('[PIPELINE] run_nightly_digest done: status=%s, reports=%d (%s)',
                result.get('status'), len(reports),
                ', '.join('{}: {}articles'.format(r['category'], r['article_count']) for r in reports))
    return result
