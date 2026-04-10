"""Check which migrate tables exist online."""
import pymysql
from pymysql.cursors import DictCursor

conn = pymysql.connect(host='123.56.3.1', port=3306, user='mytrader_user',
    password='lGgS^uruPhv%AK0ZifeC', database='trade', charset='utf8mb4',
    connect_timeout=10, cursorclass=DictCursor)
cursor = conn.cursor()
cursor.execute("SHOW TABLES FROM trade")
online_tables = set(row[list(row.keys())[0]] for row in cursor.fetchall())
cursor.close()
conn.close()

migrate_tables = [
    "trade_stock_daily", "trade_stock_rps", "trade_hk_daily",
    "trade_stock_extended_factor", "trade_stock_basic_factor",
    "trade_stock_valuation_factor", "trade_stock_quality_factor",
    "trade_stock_daily_basic", "trade_etf_daily", "trade_stock_financial",
    "trade_log_bias_daily", "macro_data", "macro_factors", "trade_stock_basic",
    "etf_daily", "trade_calendar", "trade_factor_validation", "factor_status",
    "pt_positions", "pt_rounds", "financial_income", "financial_balance",
    "financial_dividend", "bank_asset_quality"
]

print("=== Can import (table exists online) ===")
can_import = [t for t in migrate_tables if t in online_tables]
for t in can_import:
    print("  " + t)

print("\n=== Cannot import (table missing online, no CREATE perm) ===")
cannot_import = [t for t in migrate_tables if t not in online_tables]
for t in cannot_import:
    print("  " + t)

print("\nOnline tables: {} | Migrate tables: {} | Can import: {} | Need CREATE: {}".format(
    len(online_tables), len(migrate_tables), len(can_import), len(cannot_import)))
