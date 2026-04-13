# -*- coding: utf-8 -*-
"""
Adapter functions for modules that don't have a simple zero-argument entry point.

Each adapter provides a `dry_run` parameter. When dry_run=True, only prints
what would happen without actually executing.
"""
import logging

logger = logging.getLogger(__name__)


def run_log_bias(dry_run: bool = False):
    """Adapter for strategist.log_bias.run_daily.run_daily."""
    if dry_run:
        logger.info("[DRY-RUN] run_log_bias: would run LogBias daily signal detection")
        return

    from strategist.log_bias.config import LogBiasConfig
    from strategist.log_bias.run_daily import run_daily

    config = LogBiasConfig()
    run_daily(config)


def run_technical_indicator_scan(dry_run: bool = False):
    """Adapter for data_analyst.indicators.technical.TechnicalIndicatorCalculator."""
    if dry_run:
        logger.info("[DRY-RUN] run_technical_indicator_scan: would calculate technical indicators for all stocks")
        return

    from data_analyst.indicators.technical import TechnicalIndicatorCalculator

    calculator = TechnicalIndicatorCalculator()
    calculator.calculate_for_all_stocks()


def run_paper_trading_settle(dry_run: bool = False):
    """Adapter for paper trading settlement."""
    if dry_run:
        logger.info("[DRY-RUN] run_paper_trading_settle: would settle paper trading positions")
        return

    # PaperTradingScheduler is not yet implemented; placeholder
    logger.info("[WARN] Paper trading settlement not yet implemented")


def run_industry_update(dry_run: bool = False):
    """Adapter for strategist.multi_factor.industry_fetcher."""
    if dry_run:
        logger.info("[DRY-RUN] run_industry_update: would fetch and update industry classifications")
        return

    from strategist.multi_factor.industry_fetcher import fetch_all_industries, update_db

    industry_map = fetch_all_industries()
    update_db(industry_map, dry_run=False)
    logger.info("Updated industry classifications for %d stocks", len(industry_map))


# ---------------------------------------------------------------------------
# Data supplement adapters (daily incremental, dual-write local+online)
# ---------------------------------------------------------------------------

def _clear_proxy():
    """Remove proxy env vars so AKShare can reach external APIs directly."""
    import os
    for _var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                 "ALL_PROXY", "all_proxy"):
        os.environ.pop(_var, None)
    os.environ["NO_PROXY"] = "*"


def fetch_moneyflow_incremental(dry_run: bool = False, envs: str = "local,online"):
    """
    Daily incremental fetch of trade_stock_moneyflow.
    Writes to all envs in comma-separated envs string.
    """
    if dry_run:
        logger.info("[DRY-RUN] fetch_moneyflow_incremental: would fetch yesterday's moneyflow")
        return

    _clear_proxy()

    import sys
    import os
    import importlib.util
    sys.argv = ["fetch_moneyflow", "--incremental", "--no-proxy", "--envs", envs]

    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "fetch_moneyflow.py")
    spec = importlib.util.spec_from_file_location("fetch_moneyflow", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


def fetch_sw_industry_sync(dry_run: bool = False, envs: str = "local,online"):
    """
    Sync SW industry classification from trade_stock_basic (fast, no API).
    Run weekly or after bulk stock list update.
    """
    if dry_run:
        logger.info("[DRY-RUN] fetch_sw_industry_sync: would sync industry classification")
        return

    from config.db import execute_query, execute_many

    env_list = [e.strip() for e in envs.split(",") if e.strip()]
    source_env = env_list[0]

    rows = execute_query(
        "SELECT stock_code, stock_name, industry FROM trade_stock_basic "
        "WHERE industry IS NOT NULL AND industry != ''",
        env=source_env,
    )
    if not rows:
        logger.warning("trade_stock_basic has no industry data")
        return

    data = [
        (r["stock_code"], r["stock_name"] or "", "", r["industry"], "1", "SW")
        for r in rows if r.get("industry")
    ]

    sql = """
        INSERT INTO trade_stock_industry
            (stock_code, stock_name, industry_code, industry_name, industry_level, classify_type)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE industry_name = VALUES(industry_name)
    """
    for env in env_list:
        try:
            execute_many(sql, data, env=env)
            logger.info(f"[env={env}] SW industry sync: {len(data)} rows")
        except Exception as e:
            logger.error(f"[env={env}] SW industry sync failed: {e}")


def fetch_margin_incremental(dry_run: bool = False, envs: str = "local,online"):
    """Daily incremental fetch of trade_margin_trade (by-date mode)."""
    if dry_run:
        logger.info("[DRY-RUN] fetch_margin_incremental: would fetch yesterday's margin data")
        return

    _clear_proxy()
    from datetime import datetime, timedelta

    import sys
    import os
    import importlib.util
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    sys.argv = ["fetch_margin", "--by-date", "--start", yesterday, "--no-proxy", "--envs", envs]

    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "fetch_margin.py")
    spec = importlib.util.spec_from_file_location("fetch_margin", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


def fetch_north_holding_incremental(dry_run: bool = False, envs: str = "local,online"):
    """Daily incremental fetch of trade_north_holding."""
    if dry_run:
        logger.info("[DRY-RUN] fetch_north_holding_incremental: would fetch yesterday's north holding")
        return

    _clear_proxy()
    from datetime import datetime, timedelta

    import sys
    import os
    import importlib.util
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    sys.argv = ["fetch_north_holding", "--start", yesterday, "--no-proxy", "--envs", envs]

    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "fetch_north_holding.py")
    spec = importlib.util.spec_from_file_location("fetch_north_holding", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


# ---------------------------------------------------------------------------
# Sentiment monitoring adapters
# ---------------------------------------------------------------------------

def run_sentiment_fear_index(dry_run: bool = False, env: str = "online"):
    """Fetch VIX/OVX/GVZ/US10Y and persist to trade_fear_index."""
    if dry_run:
        logger.info("[DRY-RUN] run_sentiment_fear_index: would fetch VIX/OVX/GVZ/US10Y -> trade_fear_index (env=%s)", env)
        return
    from data_analyst.sentiment.fear_index import FearIndexService
    from data_analyst.sentiment.storage import SentimentStorage
    result = FearIndexService().get_fear_index()
    logger.info("Fear index: VIX=%.2f score=%d regime=%s", result.vix, result.fear_greed_score, result.market_regime)
    if result.risk_alert:
        logger.warning("[WARN] %s", result.risk_alert)
    ok = SentimentStorage(env=env).save_fear_index(result)
    if not ok:
        raise RuntimeError("save_fear_index returned False")
    logger.info("[OK] fear index saved (env=%s)", env)


def run_sentiment_news(dry_run: bool = False, env: str = "online", stock_codes: str = "", days: int = 1):
    """Fetch news for stocks, run LLM sentiment, persist to trade_news_sentiment."""
    if dry_run:
        logger.info("[DRY-RUN] run_sentiment_news: stocks=%s days=%d -> trade_news_sentiment (env=%s)", stock_codes, days, env)
        return
    if not stock_codes:
        logger.warning("[WARN] run_sentiment_news: stock_codes empty, skip")
        return
    from data_analyst.sentiment.news_fetcher import NewsFetcher
    from data_analyst.sentiment.sentiment_analyzer import SentimentAnalyzer
    from data_analyst.sentiment.storage import SentimentStorage
    fetcher = NewsFetcher()
    analyzer = SentimentAnalyzer()
    storage = SentimentStorage(env=env)
    total = 0
    for code in [c.strip() for c in stock_codes.split(",") if c.strip()]:
        try:
            news_list = fetcher.fetch_stock_news(code, days=days)
            if not news_list:
                continue
            results = analyzer.analyze_batch(news_list)
            if storage.save_news_sentiment(results):
                total += len(results)
                logger.info("[OK] saved %d records for %s", len(results), code)
        except Exception as e:
            logger.error("[RED] news sentiment failed for %s: %s", code, e)
    logger.info("[OK] run_sentiment_news done: %d total saved (env=%s)", total, env)


def run_sentiment_events(dry_run: bool = False, env: str = "online",
                         keywords: str = "资产重组,回购,业绩预增,业绩预减,减持,违规,退市", days: int = 1):
    """Detect keyword-based events from CCTV news and persist to trade_event_signal."""
    if dry_run:
        logger.info("[DRY-RUN] run_sentiment_events: keywords=%s days=%d -> trade_event_signal (env=%s)", keywords, days, env)
        return
    from data_analyst.sentiment.news_fetcher import NewsFetcher
    from data_analyst.sentiment.event_detector import EventDetector
    from data_analyst.sentiment.storage import SentimentStorage
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    news_list = NewsFetcher().fetch_keyword_news(kw_list, days=days)
    if not news_list:
        logger.info("[OK] no news found for keywords, nothing saved")
        return
    events = EventDetector().detect_events(news_list)
    logger.info("detected %d event signals from %d news items", len(events), len(news_list))
    if events:
        ok = SentimentStorage(env=env).save_event_signals(events)
        if not ok:
            raise RuntimeError("save_event_signals returned False")
    logger.info("[OK] run_sentiment_events done (env=%s)", env)


def run_sentiment_polymarket(dry_run: bool = False, env: str = "online",
                              keywords: str = "tariff,fed,election,china,oil", min_volume: float = 1000000.0):
    """Fetch Polymarket smart-money signals and persist to trade_polymarket_snapshot."""
    if dry_run:
        logger.info("[DRY-RUN] run_sentiment_polymarket: keywords=%s min_volume=%.0f -> trade_polymarket_snapshot (env=%s)", keywords, min_volume, env)
        return
    from data_analyst.sentiment.polymarket import PolymarketService
    from data_analyst.sentiment.storage import SentimentStorage
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    events = PolymarketService().detect_smart_money_signals(kw_list, min_volume=min_volume)
    logger.info("found %d Polymarket smart money signals", len(events))
    if events:
        ok = SentimentStorage(env=env).save_polymarket_snapshot(events)
        if not ok:
            raise RuntimeError("save_polymarket_snapshot returned False")
    logger.info("[OK] run_sentiment_polymarket done (env=%s)", env)


# ---------------------------------------------------------------------------
# Theme Pool scoring adapter
# ---------------------------------------------------------------------------

def run_theme_pool_score(dry_run: bool = False, env: str = "online"):
    """Daily scoring for all stocks in active theme pools."""
    if dry_run:
        logger.info("[DRY-RUN] run_theme_pool_score: would score all active theme pool stocks (env=%s)", env)
        return

    from api.tasks.theme_pool_score import run_theme_pool_score as _score
    _score(dry_run=False, env=env)
