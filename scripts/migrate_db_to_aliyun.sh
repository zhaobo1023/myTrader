#!/bin/bash
# ============================================================
# 一键迁移本地数据库到阿里云服务器
# 源: 192.168.97.1 (wucai_trade)
# 目标: 123.56.3.1 (wucai_trade)
# ============================================================
set -euo pipefail

# ---- PATH (append MySQL 8.0 client, keep system tools) ----
export PATH="/opt/homebrew/opt/mysql-client@8.0/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# ---- 配置 ----
LOCAL_HOST="192.168.97.1"
LOCAL_PORT="3306"
LOCAL_USER="quant_user"
LOCAL_PASS="Quant@2024User"
LOCAL_DB="wucai_trade"

REMOTE_SSH="root@123.56.3.1"
SSH_KEY="/Users/wenwen/Documents/key/trader.pem"
SSH_OPTS="-o ConnectTimeout=10 -o StrictHostKeyChecking=no"

REMOTE_MYSQL_HOST="127.0.0.1"
REMOTE_MYSQL_PORT="3306"
REMOTE_MYSQL_USER="quant_user"
REMOTE_MYSQL_PASS="Quant@2024User"
REMOTE_MYSQL_DB="wucai_trade"

DUMP_DIR="/tmp/db_migration_$(date +%Y%m%d_%H%M%S)"
DUMP_FILE="${DUMP_DIR}/wucai_trade.sql.gz"
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
    for cmd in mysqldump gzip scp ssh mysql; do
        if ! command -v "$cmd" &>/dev/null; then
            log "[ERROR] $cmd not found"
            exit 1
        fi
    done
    log "All dependencies OK"
}

test_local_conn() {
    log "Testing local DB connection..."
    if mysql -h "$LOCAL_HOST" -P "$LOCAL_PORT" -u "$LOCAL_USER" -p"$LOCAL_PASS" -e "SELECT 1" &>/dev/null; then
        log "Local DB connection OK"
    else
        log "[ERROR] Cannot connect to local DB $LOCAL_HOST:$LOCAL_PORT"
        exit 1
    fi
}

test_remote_conn() {
    log "Testing remote SSH connection..."
    if ssh $SSH_OPTS -i "$SSH_KEY" "$REMOTE_SSH" "echo ok" &>/dev/null; then
        log "Remote SSH connection OK"
    else
        log "[ERROR] Cannot SSH to $REMOTE_SSH"
        exit 1
    fi

    log "Testing remote MySQL connection..."
    if ssh $SSH_OPTS -i "$SSH_KEY" "$REMOTE_SSH" \
        "mysql -h $REMOTE_MYSQL_HOST -P $REMOTE_MYSQL_PORT -u $REMOTE_MYSQL_USER -p\"$REMOTE_MYSQL_PASS\" -e 'SELECT 1' 2>/dev/null"; then
        log "Remote MySQL connection OK"
    else
        log "[ERROR] Cannot connect to remote MySQL"
        exit 1
    fi
}

step1_dump() {
    log "===== STEP 1: Dumping local database ====="
    mkdir -p "$DUMP_DIR"

    TABLE_LIST=$(IFS=' '; echo "${TABLES[*]}")
    log "Dumping tables: $TABLE_LIST"

    mysqldump \
        -h "$LOCAL_HOST" -P "$LOCAL_PORT" \
        -u "$LOCAL_USER" -p"$LOCAL_PASS" \
        --databases "$LOCAL_DB" \
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

step2_upload() {
    log "===== STEP 2: Uploading to remote server ====="
    REMOTE_DIR="/tmp/db_migration"
    ssh $SSH_OPTS -i "$SSH_KEY" "$REMOTE_SSH" "mkdir -p $REMOTE_DIR"
    scp $SSH_OPTS -i "$SSH_KEY" "$DUMP_FILE" "${REMOTE_SSH}:${REMOTE_DIR}/wucai_trade.sql.gz"
    log "Upload completed"
}

step3_create_db() {
    log "===== STEP 3: Creating database on remote ====="
    ssh $SSH_OPTS -i "$SSH_KEY" "$REMOTE_SSH" \
        "mysql -h $REMOTE_MYSQL_HOST -P $REMOTE_MYSQL_PORT -u $REMOTE_MYSQL_USER -p\"$REMOTE_MYSQL_PASS\" \
         -e \"CREATE DATABASE IF NOT EXISTS \\\`$REMOTE_MYSQL_DB\\\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci\""
    log "Database $REMOTE_MYSQL_DB ready on remote"
}

step4_import() {
    log "===== STEP 4: Importing data on remote ====="
    ssh $SSH_OPTS -i "$SSH_KEY" "$REMOTE_SSH" \
        "zcat /tmp/db_migration/wucai_trade.sql.gz | mysql -h $REMOTE_MYSQL_HOST -P $REMOTE_MYSQL_PORT -u $REMOTE_MYSQL_USER -p\"$REMOTE_MYSQL_PASS\" $REMOTE_MYSQL_DB"
    log "Import completed"
}

step5_verify() {
    log "===== STEP 5: Verification ====="

    echo ""
    echo "Local vs Remote table row counts:"
    echo "--------------------------------------------------------------"
    printf "%-45s %12s %12s %8s\n" "Table" "Local" "Remote" "Match"
    echo "--------------------------------------------------------------"

    ALL_OK=true
    for TABLE in "${TABLES[@]}"; do
        LOCAL_ROWS=$(mysql -h "$LOCAL_HOST" -P "$LOCAL_PORT" -u "$LOCAL_USER" -p"$LOCAL_PASS" \
            -N -e "SELECT COUNT(*) FROM $LOCAL_DB.$TABLE" 2>/dev/null || echo "0")
        REMOTE_ROWS=$(ssh $SSH_OPTS -i "$SSH_KEY" "$REMOTE_SSH" \
            "mysql -h $REMOTE_MYSQL_HOST -P $REMOTE_MYSQL_PORT -u $REMOTE_MYSQL_USER -p\"$REMOTE_MYSQL_PASS\" \
             -N -e \"SELECT COUNT(*) FROM $REMOTE_MYSQL_DB.$TABLE\"" 2>/dev/null || echo "0")

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

step6_cleanup() {
    log "===== STEP 6: Cleanup ====="
    log "Local dump dir: $DUMP_DIR (not auto-deleted, remove manually if needed)"
    log "Remote dump dir: /tmp/db_migration (not auto-deleted, remove manually if needed)"
}

# ---- Main ----
main() {
    echo "============================================================"
    echo " Database Migration: $LOCAL_HOST -> $REMOTE_SSH"
    echo " Database: $LOCAL_DB -> $REMOTE_MYSQL_DB"
    echo " Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================================"
    echo ""

    mkdir -p "$DUMP_DIR"
    check_deps
    test_local_conn
    test_remote_conn
    echo ""

    step1_dump
    step2_upload
    step3_create_db
    step4_import
    step5_verify
    step6_cleanup

    echo ""
    log "===== Migration completed ====="
}

main "$@"
