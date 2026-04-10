#!/bin/bash
# ============================================================
# 一键迁移本地数据库到阿里云服务器（网络直连版，无需 SSH）
# 源: 192.168.97.1 (wucai_trade)
# 目标: 123.56.3.1 (trade)
# 方式: mysqldump 本地导出 -> mysql 管道直连线上导入
# ============================================================
set -euo pipefail

# ---- PATH (append MySQL 8.0 client, keep system tools) ----
export PATH="/opt/homebrew/opt/mysql-client@8.0/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# ---- 源端配置（本地） ----
LOCAL_HOST="192.168.97.1"
LOCAL_PORT="3306"
LOCAL_USER="quant_user"
LOCAL_PASS="Quant@2024User"
LOCAL_DB="wucai_trade"

# ---- 目标端配置（线上，公网直连） ----
REMOTE_HOST="123.56.3.1"
REMOTE_PORT="3306"
REMOTE_USER="mytrader_user"
REMOTE_PASS='lGgS^uruPhv%AK0ZifeC'
REMOTE_DB="trade"

DUMP_DIR="/tmp/db_migration_$(date +%Y%m%d_%H%M%S)"
DUMP_FILE="${DUMP_DIR}/dump.sql.gz"
LOG_FILE="${DUMP_DIR}/migration.log"

# 只导出有数据的表（跳过空表，减少无用数据）
TABLES=(
    trade_stock_daily
    trade_stock_rps
    trade_hk_daily
    trade_stock_extended_factor
    trade_stock_basic_factor
    trade_stock_valuation_factor
    trade_stock_quality_factor
    trade_stock_daily_basic
    trade_etf_daily
    trade_stock_financial
    trade_log_bias_daily
    macro_data
    macro_factors
    trade_stock_basic
    etf_daily
    trade_calendar
    trade_factor_validation
    factor_status
    pt_positions
    pt_rounds
    financial_income
    financial_balance
    financial_dividend
    bank_asset_quality
)

# ---- 函数 ----
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

check_deps() {
    log "Checking dependencies..."
    for cmd in mysqldump gzip mysql; do
        if ! command -v "$cmd" &>/dev/null; then
            log "[ERROR] $cmd not found"
            exit 1
        fi
    done
    log "All dependencies OK"
}

test_local_conn() {
    log "Testing local DB connection ($LOCAL_HOST:$LOCAL_PORT)..."
    if mysql -h "$LOCAL_HOST" -P "$LOCAL_PORT" -u "$LOCAL_USER" -p"$LOCAL_PASS" -e "SELECT 1" &>/dev/null; then
        log "Local DB connection OK"
    else
        log "[ERROR] Cannot connect to local DB $LOCAL_HOST:$LOCAL_PORT"
        exit 1
    fi
}

test_remote_conn() {
    log "Testing remote DB connection ($REMOTE_HOST:$REMOTE_PORT)..."
    if mysql -h "$REMOTE_HOST" -P "$REMOTE_PORT" -u "$REMOTE_USER" -p"$REMOTE_PASS" -e "SELECT 1" &>/dev/null; then
        log "Remote DB connection OK"
    else
        log "[ERROR] Cannot connect to remote DB $REMOTE_HOST:$REMOTE_PORT"
        exit 1
    fi
}

step1_dump() {
    log "===== STEP 1: Dumping local database ====="
    mkdir -p "$DUMP_DIR"

    TABLE_LIST=$(IFS=' '; echo "${TABLES[*]}")
    log "Dumping ${#TABLES[@]} tables: $TABLE_LIST"

    mysqldump \
        -h "$LOCAL_HOST" -P "$LOCAL_PORT" \
        -u "$LOCAL_USER" -p"$LOCAL_PASS" \
        "$LOCAL_DB" \
        --tables $TABLE_LIST \
        --single-transaction \
        --no-tablespaces \
        --routines \
        --triggers \
        --events=false \
        --set-gtid-purged=OFF \
        --max-allowed-packet=256M \
    | gzip > "$DUMP_FILE"

    SIZE=$(du -sh "$DUMP_FILE" | cut -f1)
    log "Dump completed: $DUMP_FILE ($SIZE)"
}

step2_import() {
    log "===== STEP 2: Importing to remote database ====="
    log "Streaming dump -> $REMOTE_HOST:$REMOTE_PORT/$REMOTE_DB"

    gunzip -c "$DUMP_FILE" | mysql \
        -h "$REMOTE_HOST" -P "$REMOTE_PORT" \
        -u "$REMOTE_USER" -p"$REMOTE_PASS" \
        --max-allowed-packet=256M \
        "$REMOTE_DB"

    log "Import completed"
}

step3_verify() {
    log "===== STEP 3: Verification ====="

    echo ""
    echo "Local vs Remote table row counts:"
    echo "--------------------------------------------------------------"
    printf "%-45s %12s %12s %8s\n" "Table" "Local" "Remote" "Match"
    echo "--------------------------------------------------------------"

    ALL_OK=true
    for TABLE in "${TABLES[@]}"; do
        LOCAL_ROWS=$(mysql -h "$LOCAL_HOST" -P "$LOCAL_PORT" -u "$LOCAL_USER" -p"$LOCAL_PASS" \
            -N -e "SELECT COUNT(*) FROM $LOCAL_DB.$TABLE" 2>/dev/null || echo "0")
        REMOTE_ROWS=$(mysql -h "$REMOTE_HOST" -P "$REMOTE_PORT" -u "$REMOTE_USER" -p"$REMOTE_PASS" \
            -N -e "SELECT COUNT(*) FROM $REMOTE_DB.$TABLE" 2>/dev/null || echo "0")

        if [ "$LOCAL_ROWS" = "$REMOTE_ROWS" ]; then
            STATUS="OK"
        else
            STATUS="DIFF"
            ALL_OK=false
        fi
        printf "%-45s %12s %12s %8s\n" "$TABLE" "$LOCAL_ROWS" "$REMOTE_ROWS" "$STATUS"
    done
    echo "--------------------------------------------------------------"

    if $ALL_OK; then
        log "[OK] All tables match!"
    else
        log "[WARN] Some tables have row count differences, check above"
    fi
}

# ---- Main ----
main() {
    echo "============================================================"
    echo " Database Migration (Direct Connect)"
    echo " Source: $LOCAL_HOST:$LOCAL_PORT/$LOCAL_DB"
    echo " Target: $REMOTE_HOST:$REMOTE_PORT/$REMOTE_DB"
    echo " Tables: ${#TABLES[@]}"
    echo " Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================================"
    echo ""

    mkdir -p "$DUMP_DIR"
    check_deps
    test_local_conn
    test_remote_conn
    echo ""

    step1_dump
    step2_import
    step3_verify

    echo ""
    log "===== Migration completed ====="
    log "Dump file: $DUMP_FILE (remove manually if needed)"
}

main "$@"
