#!/usr/bin/env bash
# -*- coding: utf-8 -*-
#
# 微盘股策略服务器端一键启动脚本
#
# 用法：
#   bash strategist/microcap/run_server.sh
#
# 功能：
#   1. 数据完整性检查（关键表行数 + 日期覆盖）
#   2. 缺失数据补充提示
#   3. 并行启动所有回测任务
#
# 环境要求：
#   DB_ENV=online（默认）或通过 export DB_ENV=online 提前设置

set -e

export DB_ENV=${DB_ENV:-online}

# 项目根目录（脚本位于 strategist/microcap/，回溯两层）
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

LOG_DIR="/tmp/microcap_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"

echo "================================================"
echo " 微盘股策略回测启动脚本"
echo " DB_ENV=$DB_ENV"
echo " ROOT=$ROOT"
echo " LOG_DIR=$LOG_DIR"
echo "================================================"

# ─────────────────────────────────────────────────────────
# Step 1: 数据完整性检查
# ─────────────────────────────────────────────────────────
echo ""
echo "[Step 1] 检查数据完整性..."

python3 - <<'PYEOF'
import sys, os
sys.path.insert(0, os.environ.get('ROOT', '.'))
from config.db import get_connection
import pandas as pd

conn = get_connection()
checks = [
    ("trade_stock_daily",       "SELECT COUNT(*) as cnt, MIN(trade_date) as min_d, MAX(trade_date) as max_d FROM trade_stock_daily"),
    ("trade_stock_daily_basic", "SELECT COUNT(*) as cnt, MIN(trade_date) as min_d, MAX(trade_date) as max_d FROM trade_stock_daily_basic"),
    ("trade_stock_financial",   "SELECT COUNT(*) as cnt, MIN(report_date) as min_d, MAX(report_date) as max_d FROM trade_stock_financial"),
    ("trade_stock_basic",       "SELECT COUNT(*) as cnt FROM trade_stock_basic"),
    ("trade_stock_ebit",        "SELECT COUNT(*) as cnt, MIN(report_date) as min_d, MAX(report_date) as max_d FROM trade_stock_ebit"),
]

ok = True
for name, sql in checks:
    try:
        df = pd.read_sql(sql, conn)
        row = df.iloc[0]
        cnt = int(row['cnt'])
        min_d = str(row.get('min_d', 'N/A'))
        max_d = str(row.get('max_d', 'N/A'))
        status = "[OK]" if cnt > 0 else "[WARN] EMPTY"
        print("  {:<8} {:<35} rows={:>10}  {} ~ {}".format(status, name, cnt, min_d, max_d))
        if cnt == 0:
            ok = False
    except Exception as e:
        print("  [ERROR]  {:<35} {}".format(name, e))
        ok = False

conn.close()

conn2 = get_connection()
try:
    df = pd.read_sql("SELECT MIN(trade_date) as min_d FROM trade_stock_daily_basic", conn2)
    min_date = str(df.iloc[0]['min_d'])
    if min_date > '2022-06-01':
        print("\n  [WARN] trade_stock_daily_basic 最早数据 {}，2022-01-01 前数据缺失".format(min_date))
        print("         建议先运行: python3 -m data_analyst.financial_fetcher.daily_basic_history_fetcher")
    else:
        print("\n  [OK]   trade_stock_daily_basic 覆盖 2022 年以前，数据充足")
finally:
    conn2.close()

sys.exit(0 if ok else 1)
PYEOF

if [ $? -ne 0 ]; then
    echo ""
    echo "[WARN] 部分数据检查失败，建议先补充数据后再回测。"
    echo "       补充 trade_stock_daily_basic 历史数据："
    echo "         DB_ENV=online python -m data_analyst.financial_fetcher.daily_basic_history_fetcher"
    echo ""
    read -p "是否仍然继续启动回测？[y/N] " confirm
    [ "$confirm" != "y" ] && echo "已取消。" && exit 0
fi

# ─────────────────────────────────────────────────────────
# Step 2: 并行启动所有回测
# ─────────────────────────────────────────────────────────
echo ""
echo "[Step 2] 启动并行回测..."

START=${START:-2022-01-01}
END=${END:-2026-03-24}

echo "  回测区间: $START ~ $END"
echo ""

# 任务1：grid (peg/pe/roe × h1/3/5/10)，4 并行
GRID_LOG="$LOG_DIR/grid.log"
DB_ENV=$DB_ENV python3 -m strategist.microcap.run_grid \
    --start "$START" --end "$END" \
    --factors peg pe roe \
    --hold-days 1 3 5 10 \
    --top-n 15 --workers 4 \
    > "$GRID_LOG" 2>&1 &
GRID_PID=$!
echo "  [START] grid       PID=$GRID_PID  log=$GRID_LOG"

# 任务2：pure_mv h1
PURE_LOG="$LOG_DIR/pure_mv_h1.log"
DB_ENV=$DB_ENV python3 -m strategist.microcap.run_backtest \
    --start "$START" --end "$END" \
    --factor pure_mv --top-n 15 --hold-days 1 \
    > "$PURE_LOG" 2>&1 &
PURE_PID=$!
echo "  [START] pure_mv_h1 PID=$PURE_PID  log=$PURE_LOG"

# 任务3：peg_ebit_mv h1
EBIT_LOG="$LOG_DIR/peg_ebit_mv_h1.log"
DB_ENV=$DB_ENV python3 -m strategist.microcap.run_backtest \
    --start "$START" --end "$END" \
    --factor peg_ebit_mv --top-n 10 --hold-days 1 \
    > "$EBIT_LOG" 2>&1 &
EBIT_PID=$!
echo "  [START] peg_ebit_mv_h1 PID=$EBIT_PID  log=$EBIT_LOG"

echo ""
echo "================================================"
echo " 全部任务已在后台启动"
echo ""
echo " 查看进度："
echo "   tail -f $GRID_LOG"
echo "   tail -f $PURE_LOG"
echo "   tail -f $EBIT_LOG"
echo ""
echo " 查看所有进程："
echo "   ps aux | grep run_backtest"
echo ""
echo " 停止所有任务："
echo "   kill $GRID_PID $PURE_PID $EBIT_PID"
echo "================================================"

# 写入 PID 文件，方便后续停止
echo "$GRID_PID $PURE_PID $EBIT_PID" > "$LOG_DIR/pids.txt"
