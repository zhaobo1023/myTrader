"""
Migrate data from local to online database.
Handles table structure differences by only inserting columns that exist in both.
Uses INSERT ... ON DUPLICATE KEY UPDATE to handle existing rows.
"""
import os
import time
import logging
import pymysql
from pymysql.cursors import DictCursor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

# Source: local
SRC_HOST = "192.168.97.1"
SRC_PORT = 3306
SRC_USER = "quant_user"
SRC_PASS = "Quant@2024User"
SRC_DB = "wucai_trade"

# Target: online
DST_HOST = "123.56.3.1"
DST_PORT = 3306
DST_USER = "mytrader_user"
DST_PASS = "lGgS^uruPhv%AK0ZifeC"
DST_DB = "trade"

# Tables to migrate (all 24)
MIGRATE_TABLES = [
    "trade_stock_daily",
    "trade_stock_rps",
    "trade_hk_daily",
    "trade_stock_extended_factor",
    "trade_stock_basic_factor",
    "trade_stock_valuation_factor",
    "trade_stock_quality_factor",
    "trade_stock_daily_basic",
    "trade_etf_daily",
    "trade_stock_financial",
    "trade_log_bias_daily",
    "macro_data",
    "macro_factors",
    "trade_stock_basic",
    "etf_daily",
    "trade_calendar",
    "trade_factor_validation",
    "factor_status",
    "pt_positions",
    "pt_rounds",
    "financial_income",
    "financial_balance",
    "financial_dividend",
    "bank_asset_quality",
]

BATCH_SIZE = 5000


def get_columns(host, port, user, password, db, table):
    conn = pymysql.connect(host=host, port=port, user=user, password=password,
                           database=db, charset='utf8mb4', connect_timeout=10,
                           cursorclass=DictCursor)
    cursor = conn.cursor()
    cursor.execute(f"SHOW COLUMNS FROM `{table}`")
    cols = [row['Field'] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return cols


def get_online_tables():
    conn = pymysql.connect(host=DST_HOST, port=DST_PORT, user=DST_USER,
                           password=DST_PASS, database=DST_DB, charset='utf8mb4',
                           connect_timeout=10, cursorclass=DictCursor)
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    tables = set(row[list(row.keys())[0]] for row in cursor.fetchall())
    cursor.close()
    conn.close()
    return tables


def migrate_table(table, online_tables):
    # Check if table exists online
    if table not in online_tables:
        log.warning("  SKIP: %s does not exist online (no CREATE permission)", table)
        return False

    # Get columns on both sides
    src_cols = get_columns(SRC_HOST, SRC_PORT, SRC_USER, SRC_PASS, SRC_DB, table)
    dst_cols = get_columns(DST_HOST, DST_PORT, DST_USER, DST_PASS, DST_DB, table)

    # Use only columns that exist in both (preserve order from source)
    common_cols = [c for c in src_cols if c in dst_cols]
    if not common_cols:
        log.warning("  SKIP: %s - no common columns", table)
        return False

    missing_cols = set(src_cols) - set(dst_cols)
    if missing_cols:
        log.info("  %s: skipping columns not in target: %s", table, missing_cols)

    cols_str = ", ".join(f"`{c}`" for c in common_cols)
    placeholders = ", ".join(["%s"] * len(common_cols))
    # Use REPLACE INTO to handle duplicate key conflicts
    sql = f"REPLACE INTO `{table}` ({cols_str}) VALUES ({placeholders})"

    # Count source rows
    src_conn = pymysql.connect(host=SRC_HOST, port=SRC_PORT, user=SRC_USER,
                               password=SRC_PASS, database=SRC_DB, charset='utf8mb4',
                               connect_timeout=10, cursorclass=DictCursor)
    src_cur = src_conn.cursor()
    src_cur.execute(f"SELECT COUNT(*) as cnt FROM `{table}`")
    total_rows = src_cur.fetchone()['cnt']

    # Count dest rows before
    dst_conn = pymysql.connect(host=DST_HOST, port=DST_PORT, user=DST_USER,
                               password=DST_PASS, database=DST_DB, charset='utf8mb4',
                               connect_timeout=10, cursorclass=DictCursor)
    dst_cur = dst_conn.cursor()
    dst_cur.execute(f"SELECT COUNT(*) as cnt FROM `{table}`")
    before_count = dst_cur.fetchone()['cnt']

    # Read and insert in batches (order by first column if 'id' not available)
    order_col = 'id' if 'id' in common_cols else common_cols[0]
    src_cur.execute(f"SELECT {cols_str} FROM `{table}` ORDER BY `{order_col}`")
    inserted = 0
    batch = []
    t0 = time.time()

    while True:
        rows = src_cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        for row in rows:
            batch.append(tuple(row[c] for c in common_cols))

        if len(batch) >= BATCH_SIZE:
            dst_cur.executemany(sql, batch)
            dst_conn.commit()
            inserted += len(batch)
            if inserted % 50000 == 0:
                elapsed = time.time() - t0
                log.info("  %s: %d/%d rows (%d rows/s)", table, inserted, total_rows,
                         int(inserted / elapsed) if elapsed > 0 else 0)
            batch = []

    # Insert remaining
    if batch:
        dst_cur.executemany(sql, batch)
        dst_conn.commit()
        inserted += len(batch)

    elapsed = time.time() - t0

    # Verify
    dst_cur.execute(f"SELECT COUNT(*) as cnt FROM `{table}`")
    after_count = dst_cur.fetchone()['cnt']

    src_cur.close()
    src_conn.close()
    dst_cur.close()
    dst_conn.close()

    log.info("  %s: done - inserted/updated %d rows in %.1fs (before: %d, after: %d)",
             table, inserted, elapsed, before_count, after_count)
    return True


def main():
    log.info("=== Data Migration: %s -> %s ===", SRC_DB, DST_DB)
    log.info("Source: %s:%s/%s", SRC_HOST, SRC_PORT, SRC_DB)
    log.info("Target: %s:%s/%s", DST_HOST, DST_PORT, DST_DB)

    online_tables = get_online_tables()
    log.info("Online has %d tables", len(online_tables))

    t0 = time.time()
    success = 0
    skipped = 0

    for table in MIGRATE_TABLES:
        log.info("Migrating %s...", table)
        try:
            if migrate_table(table, online_tables):
                success += 1
            else:
                skipped += 1
        except Exception as e:
            log.error("  FAILED: %s - %s", table, e)
            skipped += 1

    elapsed = time.time() - t0
    log.info("=== Done: %d success, %d skipped, %.1fs ===", success, skipped, elapsed)


if __name__ == "__main__":
    main()
