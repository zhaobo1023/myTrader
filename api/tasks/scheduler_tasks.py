# -*- coding: utf-8 -*-
"""
Celery task wrappers for scheduler adapter functions.

These tasks bridge Celery Beat scheduling and the scheduler/adapters.py
functions. Named to match the beat_schedule task names.
"""
import logging

from api.tasks.celery_app import celery_app

logger = logging.getLogger('myTrader.tasks')


@celery_app.task(name='scheduler.adapters.run_data_gate', bind=True, max_retries=0)
def run_data_gate(self):
    from scheduler.adapters import run_data_gate as _fn
    logger.info('[CELERY] run_data_gate start')
    return _fn()


@celery_app.task(name='scheduler.adapters.run_factor_calculation', bind=True, max_retries=0)
def run_factor_calculation(self):
    from scheduler.adapters import run_factor_calculation as _fn
    logger.info('[CELERY] run_factor_calculation start')
    return _fn()


@celery_app.task(name='scheduler.adapters.run_indicator_calculation', bind=True, max_retries=0)
def run_indicator_calculation(self):
    from scheduler.adapters import run_indicator_calculation as _fn
    logger.info('[CELERY] run_indicator_calculation start')
    return _fn()


@celery_app.task(name='scheduler.adapters.run_theme_pool_score', bind=True, max_retries=0)
def run_theme_pool_score(self):
    from api.tasks.theme_pool_score import run_theme_pool_score as _fn
    logger.info('[CELERY] run_theme_pool_score start')
    return _fn()


@celery_app.task(name='scheduler.adapters.run_data_integrity_check', bind=True, max_retries=0)
def run_data_integrity_check(self):
    from scheduler.adapters import run_data_integrity_check as _fn
    logger.info('[CELERY] run_data_integrity_check start')
    return _fn()


@celery_app.task(name='scheduler.adapters.run_tech_scan', bind=True, max_retries=0)
def run_tech_scan(self):
    from scheduler.adapters import run_tech_scan as _fn
    logger.info('[CELERY] run_tech_scan start')
    return _fn()


@celery_app.task(name='scheduler.adapters.run_log_bias_strategy', bind=True, max_retries=0)
def run_log_bias_strategy(self):
    from scheduler.adapters import run_log_bias_strategy as _fn
    logger.info('[CELERY] run_log_bias_strategy start')
    return _fn()
