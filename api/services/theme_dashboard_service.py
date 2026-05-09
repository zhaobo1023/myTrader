# -*- coding: utf-8 -*-
"""
Theme Dashboard Service - aggregated data for theme dashboard view
"""
import json
import logging
import asyncio
from datetime import datetime, date, timedelta

logger = logging.getLogger('myTrader.api')

# ---------------------------------------------------------------------------
# Mapping config: theme_id -> list of {cn_stock, us_peers}
# ---------------------------------------------------------------------------
THEME_STOCK_MAPPINGS = {
    16: [
        {
            'cn_code': '603039.SH', 'cn_name': '泛微网络', 'cn_market': 'A',
            'us_peers': [
                {'code': 'NOW', 'name': 'ServiceNow'},
                {'code': 'CRM', 'name': 'Salesforce'},
            ],
        },
        {
            'cn_code': '688111.SH', 'cn_name': '金山办公', 'cn_market': 'A',
            'us_peers': [
                {'code': 'MSFT', 'name': 'Microsoft'},
            ],
        },
        {
            'cn_code': '688615.SH', 'cn_name': '合合信息', 'cn_market': 'A',
            'us_peers': [
                {'code': 'PATH', 'name': 'UiPath'},
                {'code': 'ADBE', 'name': 'Adobe'},
            ],
        },
        {
            'cn_code': '688083.SH', 'cn_name': '中望软件', 'cn_market': 'A',
            'us_peers': [
                {'code': 'ADSK', 'name': 'Autodesk'},
            ],
        },
        {
            'cn_code': '301269.SZ', 'cn_name': '华大九天', 'cn_market': 'A',
            'us_peers': [
                {'code': 'SNPS', 'name': 'Synopsys'},
                {'code': 'CDNS', 'name': 'Cadence'},
            ],
        },
        {
            'cn_code': '603383.SH', 'cn_name': '顶点软件', 'cn_market': 'A',
            'us_peers': [
                {'code': 'FIS', 'name': 'FIS Global'},
            ],
        },
        {
            'cn_code': '688692.SH', 'cn_name': '达梦数据', 'cn_market': 'A',
            'us_peers': [
                {'code': 'ORCL', 'name': 'Oracle'},
                {'code': 'SNOW', 'name': 'Snowflake'},
            ],
        },
        {
            'cn_code': '600588.SH', 'cn_name': '用友网络', 'cn_market': 'A',
            'us_peers': [
                {'code': 'SAP', 'name': 'SAP'},
            ],
        },
        {
            'cn_code': '00268.HK', 'cn_name': '金蝶国际', 'cn_market': 'HK',
            'us_peers': [
                {'code': 'WDAY', 'name': 'Workday'},
                {'code': 'SAP', 'name': 'SAP'},
            ],
        },
        {
            'cn_code': '03888.HK', 'cn_name': '金山软件', 'cn_market': 'HK',
            'us_peers': [
                {'code': 'MSFT', 'name': 'Microsoft'},
            ],
        },
    ],
}


def _get_market(stock_code: str) -> str:
    """Determine market from stock code."""
    if stock_code.endswith('.HK'):
        return 'HK'
    # Pure ticker without suffix = US stock
    if '.' not in stock_code:
        return 'US'
    return 'A'


def _get_cn_close_map(price_history: list) -> dict:
    """Build a map of stock_code -> {latest_close, prices_list} from price history."""
    result = {}
    for item in price_history:
        code = item['stock_code']
        prices = item.get('prices', [])
        if prices:
            latest = prices[-1]['close']
            # Calculate returns
            ret_5d = _calc_return(prices, 5)
            ret_20d = _calc_return(prices, 20)
            result[code] = {
                'latest_close': latest,
                'prices': prices,
                'return_5d': ret_5d,
                'return_20d': ret_20d,
            }
    return result


def _calc_return(prices: list, n_days: int):
    """Calculate return from n_days ago to latest."""
    if len(prices) < n_days + 1:
        return None
    latest = prices[-1]['close']
    past = prices[-(n_days + 1)]['close']
    if past and latest and past != 0:
        return round((latest - past) / past * 100, 1)
    return None


def _normalize_prices(prices: list, key: str = 'close') -> list:
    """Normalize price series to base 100."""
    if not prices:
        return []
    base = prices[0].get(key)
    if not base or base == 0:
        return []
    return [
        {'date': p['date'], 'value': round(p.get(key, 0) / base * 100, 2) if p.get(key) else None}
        for p in prices
    ]


def fetch_us_stock_snapshots_from_db(tickers: list) -> dict:
    """
    Fetch US stock snapshots from trade_us_daily table.
    Returns: {"MSFT": {"price": 420.5, "return_5d": 2.1, "return_20d": -1.3, "history": [...]}}
    """
    from config.db import execute_query

    results = {}
    for ticker in tickers:
        try:
            rows = list(execute_query(
                "SELECT trade_date, open_price, high_price, low_price, close_price, volume "
                "FROM trade_us_daily WHERE stock_code = %s "
                "ORDER BY trade_date DESC LIMIT 130",
                (ticker,),
                env='online',
            ))
            if not rows:
                continue

            rows.reverse()  # chronological order
            history = [
                {'date': str(r['trade_date']), 'close': float(r['close_price'])}
                for r in rows if r.get('close_price')
            ]
            if not history:
                continue

            latest = history[-1]['close']
            ret_5d = None
            ret_20d = None
            if len(history) >= 6:
                ret_5d = round((latest - history[-6]['close']) / history[-6]['close'] * 100, 1)
            if len(history) >= 21:
                ret_20d = round((latest - history[-21]['close']) / history[-21]['close'] * 100, 1)

            results[ticker] = {
                'price': round(latest, 2),
                'return_5d': ret_5d,
                'return_20d': ret_20d,
                'history': history,
            }
        except Exception as e:
            logger.warning('[DASHBOARD] US stock DB fetch failed for %s: %s', ticker, e)

    return results

                close_col = 'Close' if 'Close' in df.columns else 'close'
                closes = df[close_col].dropna()
                if closes.empty:
                    continue

                latest = float(closes.iloc[-1])
                ret_5d = None
                ret_20d = None
                if len(closes) >= 6:
                    ret_5d = round((latest - float(closes.iloc[-6])) / float(closes.iloc[-6]) * 100, 1)
                if len(closes) >= 21:
                    ret_20d = round((latest - float(closes.iloc[0])) / float(closes.iloc[0]) * 100, 1)

                history = []
                for idx, row in df.iterrows():
                    c = row.get(close_col)
                    if c is not None and not pd.isna(c):
                        history.append({
                            'date': idx.strftime('%Y-%m-%d'),
                            'close': round(float(c), 2),
                        })

                results[ticker] = {
                    'price': round(latest, 2),
                    'return_5d': ret_5d,
                    'return_20d': ret_20d,
                    'history': history,
                }
            except Exception as e:
                logger.warning('[DASHBOARD] yfinance parse failed for %s: %s', ticker, e)

    except Exception as e:
        logger.error('[DASHBOARD] yfinance download failed: %s', e)

    return results


async def get_theme_dashboard(db, theme_id: int, redis_client=None) -> dict:
    """Build the complete dashboard data for a theme pool."""

    from config.db import execute_query
    from api.models.theme_pool import ThemePool
    from api.services.theme_pool_service import list_stocks
    from sqlalchemy import select

    # 1. Get theme metadata
    result = await db.execute(
        select(ThemePool).where(ThemePool.id == theme_id)
    )
    theme = result.scalar_one_or_none()
    if not theme:
        return None

    # 2. Get all stocks with scores
    stocks_data = await list_stocks(db, theme_id, user_id=None)

    # 3. Classify stocks by market
    a_stocks = []
    hk_stocks = []
    us_stocks = []
    for s in stocks_data:
        market = _get_market(s['stock_code'])
        s['market'] = market
        if market == 'A':
            a_stocks.append(s)
        elif market == 'HK':
            hk_stocks.append(s)
        else:
            us_stocks.append(s)

    # 4. Get price history for A-share + HK stocks
    price_history = []
    cn_codes = [s['stock_code'] for s in a_stocks + hk_stocks]
    for code in cn_codes:
        try:
            if code.endswith('.HK'):
                table, col = 'trade_hk_daily', 'stock_code'
            else:
                table, col = 'trade_stock_daily', 'stock_code'
            rows = list(execute_query(
                f"SELECT trade_date, open_price, high_price, low_price, close_price, volume "
                f"FROM {table} WHERE {col} = %s ORDER BY trade_date DESC LIMIT 60",
                (code,),
                env='online',
            ))
            if rows:
                rows.reverse()
                prices = [
                    {
                        'date': str(r['trade_date']),
                        'close': float(r['close_price']) if r.get('close_price') else None,
                    }
                    for r in rows
                ]
                price_history.append({
                    'stock_code': code,
                    'prices': prices,
                })
        except Exception as e:
            logger.warning('[DASHBOARD] price history failed for %s: %s', code, e)

    cn_close_map = _get_cn_close_map(price_history)

    # 5. Fetch US stock snapshots
    mapping_config = THEME_STOCK_MAPPINGS.get(theme_id, [])
    all_us_tickers = list(set(
        peer['code']
        for m in mapping_config
        for peer in m.get('us_peers', [])
    ))
    # Also add standalone US stocks in the pool
    for s in us_stocks:
        if s['stock_code'] not in all_us_tickers:
            all_us_tickers.append(s['stock_code'])

    us_snapshots = {}
    if all_us_tickers:
        us_snapshots = fetch_us_stock_snapshots_from_db(all_us_tickers)

    # 6. Build mappings with comparison data
    mappings = []
    for m in mapping_config:
        cn_data = cn_close_map.get(m['cn_code'], {})
        mapping_item = {
            'cn_stock': {
                'code': m['cn_code'],
                'name': m['cn_name'],
                'market': m['cn_market'],
                'latest_close': cn_data.get('latest_close'),
                'return_5d': cn_data.get('return_5d'),
                'return_20d': cn_data.get('return_20d'),
                'normalized': _normalize_prices(cn_data.get('prices', [])),
            },
            'us_peers': [],
        }
        for peer in m.get('us_peers', []):
            us_data = us_snapshots.get(peer['code'], {})
            mapping_item['us_peers'].append({
                'code': peer['code'],
                'name': peer.get('name', peer['code']),
                'latest_close': us_data.get('price'),
                'return_5d': us_data.get('return_5d'),
                'return_20d': us_data.get('return_20d'),
                'normalized': _normalize_prices(
                    [{'date': h['date'], 'close': h['close']} for h in us_data.get('history', [])]
                ),
            })
        mappings.append(mapping_item)

    # 7. Compute summary
    a_returns_5d = [((s.get('latest_score') or {}).get('return_5d')) for s in a_stocks
                    if (s.get('latest_score') or {}).get('return_5d') is not None]
    a_returns_20d = [((s.get('latest_score') or {}).get('return_20d')) for s in a_stocks
                     if (s.get('latest_score') or {}).get('return_20d') is not None]
    us_returns_5d = [v.get('return_5d') for v in us_snapshots.values()
                     if v.get('return_5d') is not None]
    us_returns_20d = [v.get('return_20d') for v in us_snapshots.values()
                      if v.get('return_20d') is not None]

    summary = {
        'total_stocks': len(stocks_data),
        'a_share_count': len(a_stocks),
        'hk_count': len(hk_stocks),
        'us_count': len(us_stocks),
        'avg_return_5d': round(sum(a_returns_5d + us_returns_5d) / max(len(a_returns_5d + us_returns_5d), 1), 1),
        'avg_return_20d': round(sum(a_returns_20d + us_returns_20d) / max(len(a_returns_20d + us_returns_20d), 1), 1),
        'a_share_avg_return_5d': round(sum(a_returns_5d) / max(len(a_returns_5d), 1), 1) if a_returns_5d else None,
        'a_share_avg_return_20d': round(sum(a_returns_20d) / max(len(a_returns_20d), 1), 1) if a_returns_20d else None,
        'us_avg_return_5d': round(sum(us_returns_5d) / max(len(us_returns_5d), 1), 1) if us_returns_5d else None,
        'us_avg_return_20d': round(sum(us_returns_20d) / max(len(us_returns_20d), 1), 1) if us_returns_20d else None,
    }

    return {
        'theme': {
            'id': theme.id,
            'name': theme.name,
            'description': theme.description,
        },
        'summary': summary,
        'mappings': mappings,
        'stocks': stocks_data,
    }


