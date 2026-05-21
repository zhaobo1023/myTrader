# -*- coding: utf-8 -*-
"""
Celery task for batch financial statement fetching (income + balance + cashflow + dividend).

Runs weekly on Saturday 02:00 via Celery Beat, and can be triggered manually.
Uses progress file for resume support. Reports progress via self.update_state.
"""
import logging
import os
import sys
import types

from api.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_LOCK_KEY = 'celery:lock:fetch_financial_statements_batch'
_LOCK_EXPIRE = 15000  # match time_limit


def _ensure_data_analyst_package():
    """Register dummy data_analyst package to avoid xtquant import on Linux."""
    if 'data_analyst' not in sys.modules:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dummy = types.ModuleType('data_analyst')
        dummy.__path__ = [os.path.join(project_root, 'data_analyst')]
        dummy.__package__ = 'data_analyst'
        sys.modules['data_analyst'] = dummy


@celery_app.task(
    bind=True,
    name='fetch_financial_statements_batch',
    soft_time_limit=14400,
    time_limit=15000,
)
def fetch_financial_statements_batch(self):
    """
    Incremental fetch of financial_income + financial_balance for all A-shares.

    Resume support: reads progress file to skip already-fetched stocks.
    Progress: updates Celery state every 50 stocks.
    """
    logger.info('[FINANCIAL_FETCH] Starting batch financial statement fetch')

    # --- Redis lock ---
    redis = None
    try:
        import redis as sync_redis
        from api.config import get_settings
        _s = get_settings()
        redis = sync_redis.Redis(
            host=_s.redis_host, port=_s.redis_port,
            password=_s.redis_password or None, db=_s.redis_db,
            socket_connect_timeout=2,
        )
        acquired = redis.set(_LOCK_KEY, '1', nx=True, ex=_LOCK_EXPIRE)
        if not acquired:
            logger.warning('[FINANCIAL_FETCH] Another run is in progress, skipping')
            return {'status': 'skipped', 'reason': 'lock held'}
    except Exception as lock_err:
        logger.warning('[FINANCIAL_FETCH] Could not acquire Redis lock (%s), proceeding anyway', lock_err)
        redis = None

    try:
        _ensure_data_analyst_package()

        from data_analyst.financial_fetcher.config import FinancialFetcherConfig
        from data_analyst.financial_fetcher.storage import FinancialStorage

        # Import run_fetcher functions via importlib to avoid __main__ guard issues
        import importlib.util
        run_fetcher_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'data_analyst', 'financial_fetcher', 'run_fetcher.py'
        )
        spec = importlib.util.spec_from_file_location(
            'data_analyst.financial_fetcher.run_fetcher', run_fetcher_path
        )
        run_fetcher_mod = importlib.util.module_from_spec(spec)
        run_fetcher_mod.__package__ = 'data_analyst.financial_fetcher'
        sys.modules['data_analyst.financial_fetcher.run_fetcher'] = run_fetcher_mod
        spec.loader.exec_module(run_fetcher_mod)

        from data_analyst.financial_fetcher.fetcher import run_fetch

        config = FinancialFetcherConfig()
        config.db_env = 'online'

        # Init tables
        FinancialStorage(env='online').init_tables()

        # Load stock lists
        all_stocks = run_fetcher_mod._load_all_stocks('online')
        progress_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'output', 'financial_fetcher', 'progress.txt'
        )
        done_codes = run_fetcher_mod._load_done_codes(progress_file)
        pending = {k: v for k, v in all_stocks.items() if k not in done_codes}

        total = len(all_stocks)
        already_done = len(done_codes)
        to_fetch = len(pending)

        logger.info(
            '[FINANCIAL_FETCH] Total: %d, Done: %d, Pending: %d',
            total, already_done, to_fetch,
        )

        if not pending:
            logger.info('[FINANCIAL_FETCH] All stocks already fetched')
            return {'status': 'ok', 'total': total, 'done': already_done, 'failed': 0, 'fetched': 0}

        # Ensure output directory exists
        os.makedirs(os.path.dirname(progress_file), exist_ok=True)

        # Failed file
        failed_file = progress_file.replace('progress.txt', 'failed.txt')

        counter = {'done': already_done, 'failed': 0, 'fetched': 0}
        report_interval = 50

        for i, (code, name) in enumerate(pending.items(), 1):
            try:
                stats = run_fetch(config, stock_codes={code: name}, skip_init=True)
                run_fetcher_mod._mark_done(progress_file, code)
                counter['done'] += 1
                counter['fetched'] += sum(stats.values())
                logger.info(
                    '[FINANCIAL_FETCH] [%d/%d] %s(%s) done: %d rows',
                    counter['done'], total, name, code, sum(stats.values()),
                )
            except Exception as e:
                counter['failed'] += 1
                logger.error('[FINANCIAL_FETCH] [FAIL] %s(%s): %s', name, code, e)
                with open(failed_file, 'a') as f:
                    f.write(f'{code}\t{name}\t{e}\n')

            # Report progress every N stocks
            if i % report_interval == 0:
                self.update_state(
                    state='RUNNING',
                    meta={
                        'total': total,
                        'done': counter['done'],
                        'failed': counter['failed'],
                        'pending_remaining': to_fetch - i,
                        'progress_pct': round(counter['done'] / total * 100, 1),
                    },
                )

        result = {
            'status': 'ok',
            'total': total,
            'done': counter['done'],
            'failed': counter['failed'],
            'fetched': counter['fetched'],
        }
        logger.info(
            '[FINANCIAL_FETCH] All done: total=%d, done=%d, failed=%d, rows=%d',
            total, counter['done'], counter['failed'], counter['fetched'],
        )
        return result

    except Exception as e:
        logger.error('[FINANCIAL_FETCH] Fatal error: %s', e)
        return {'status': 'failed', 'error': str(e)}

    finally:
        try:
            if redis is not None:
                redis.delete(_LOCK_KEY)
        except Exception:
            pass
