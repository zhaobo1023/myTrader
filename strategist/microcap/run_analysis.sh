#!/usr/bin/env bash
# -*- coding: utf-8 -*-
#
# 微盘股策略增强分析一键脚本
#
# 用法：
#   bash strategist/microcap/run_analysis.sh
#   START=2022-01-01 END=2026-03-24 bash strategist/microcap/run_analysis.sh
#
# 包含阶段：
#   Step 1: 数据完整性检查（含 high/low 字段 + 退市建议）
#   Step 2: 修复后基线回测（peg_h5 + 国证2000 基准）
#   Step 3: 滑点敏感性测试（0.1% / 0.2% / 0.3% / 0.5%）
#   Step 4: 持有期鲁棒性测试（h2/h4/h6/h7/h8 补全参数曲线）
#   Step 5: 完整网格（peg/pe/roe × h1/3/5/10）
#   Step 6: 输出汇总报告
#
# 环境变量：
#   DB_ENV=online（默认）
#   START=2022-01-01（默认）
#   END=2026-03-24（默认）
#   MIN_TURNOVER=0（默认，实盘建议 5000000）
#   WORKERS=1（默认，可设 4 加速 grid）

set -uo pipefail

export DB_ENV=${DB_ENV:-online}
START=${START:-2022-01-01}
END=${END:-2026-03-24}
MIN_TURNOVER=${MIN_TURNOVER:-0}
WORKERS=${WORKERS:-1}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="/tmp/microcap_analysis_${TIMESTAMP}"
mkdir -p "$LOG_DIR"

OUTPUT_DIR="$ROOT/output/microcap"
mkdir -p "$OUTPUT_DIR"

echo "=================================================="
echo " 微盘股策略增强分析"
echo " DB_ENV=$DB_ENV"
echo " 回测区间: $START ~ $END"
echo " MIN_TURNOVER: $MIN_TURNOVER"
echo " LOG_DIR: $LOG_DIR"
echo "=================================================="

# ──────────────────────────────────────────────────────────
# Step 1: 数据完整性检查
# ──────────────────────────────────────────────────────────
echo ""
echo "[Step 1] 数据完整性检查..."

python3 - <<PYEOF
import sys, os
sys.path.insert(0, "$ROOT")
os.environ['DB_ENV'] = '$DB_ENV'
from config.db import get_connection
import pandas as pd

conn = get_connection()
ok = True
warnings = []

checks = [
    ("trade_stock_daily",
     "SELECT COUNT(*) cnt, MIN(trade_date) min_d, MAX(trade_date) max_d FROM trade_stock_daily"),
    ("trade_stock_daily_basic",
     "SELECT COUNT(*) cnt, MIN(trade_date) min_d, MAX(trade_date) max_d FROM trade_stock_daily_basic"),
    ("trade_stock_financial",
     "SELECT COUNT(*) cnt, MIN(report_date) min_d, MAX(report_date) max_d FROM trade_stock_financial"),
    ("trade_stock_basic",
     "SELECT COUNT(*) cnt FROM trade_stock_basic"),
]
optional_checks = [
    ("trade_stock_ebit",
     "SELECT COUNT(*) cnt, MIN(report_date) min_d, MAX(report_date) max_d FROM trade_stock_ebit"),
]

for name, sql in checks:
    try:
        df = pd.read_sql(sql, conn)
        row = df.iloc[0]
        cnt = int(row['cnt'])
        min_d = str(row.get('min_d', 'N/A'))
        max_d = str(row.get('max_d', 'N/A'))
        tag = "[OK]  " if cnt > 0 else "[WARN]"
        print(f"  {tag} {name:<35} rows={cnt:>10}  {min_d} ~ {max_d}")
        if cnt == 0:
            ok = False
    except Exception as e:
        print(f"  [ERROR] {name:<35} {e}")
        ok = False

for name, sql in optional_checks:
    try:
        df = pd.read_sql(sql, conn)
        row = df.iloc[0]
        cnt = int(row['cnt'])
        min_d = str(row.get('min_d', 'N/A'))
        max_d = str(row.get('max_d', 'N/A'))
        print(f"  [OPT]  {name:<35} rows={cnt:>10}  {min_d} ~ {max_d}")
    except Exception:
        print(f"  [OPT]  {'trade_stock_ebit':<35} not available (peg_ebit_mv will skip)")

# 检查 high_price / low_price 字段是否有数据（涨跌停检测需要）
try:
    df2 = pd.read_sql(
        "SELECT COUNT(*) cnt FROM trade_stock_daily WHERE high_price IS NOT NULL AND high_price > 0",
        conn
    )
    cnt_hl = int(df2.iloc[0]['cnt'])
    if cnt_hl > 0:
        print(f"  [OK]   high_price/low_price 字段有数据（{cnt_hl:,} 行），涨跌停检测可用")
    else:
        print("  [WARN] high_price/low_price 字段全为空，涨跌停检测将不起效")
        warnings.append("high/low 字段缺失")
except Exception as e:
    print(f"  [WARN] 检查 high/low 字段失败: {e}")

# 检查 daily_basic 数据范围
try:
    df3 = pd.read_sql(
        "SELECT MIN(trade_date) min_d FROM trade_stock_daily_basic", conn
    )
    min_date = str(df3.iloc[0]['min_d'])
    if min_date > '2022-06-01':
        print(f"\n  [WARN] daily_basic 最早 {min_date}，2022 数据可能不完整")
        print("         可先运行: DB_ENV=online python3 -m data_analyst.financial_fetcher.daily_basic_history_fetcher")
        warnings.append("daily_basic 历史数据不足")
    else:
        print(f"  [OK]   daily_basic 覆盖至 {min_date}，历史数据充足")
except Exception:
    pass

conn.close()

print()
if warnings:
    print("  注意以下警告:")
    for w in warnings:
        print(f"    - {w}")

sys.exit(0 if ok else 1)
PYEOF

DATA_CHECK_EXIT=$?
if [ $DATA_CHECK_EXIT -ne 0 ]; then
    echo ""
    echo "[WARN] 基础数据表检查未通过，建议先补数据。"
    read -p "仍然继续？[y/N] " confirm
    [ "${confirm:-N}" != "y" ] && echo "已取消。" && exit 0
fi

echo "[Step 1] 数据检查完成"

# ──────────────────────────────────────────────────────────
# Step 2: 修复后基线回测（peg_h5 + 国证2000 基准）
# ──────────────────────────────────────────────────────────
echo ""
echo "[Step 2] 基线回测: peg_h5 + 国证2000 基准..."
BASELINE_LOG="$LOG_DIR/baseline_peg_h5.log"

DB_ENV=$DB_ENV python3 -m strategist.microcap.run_backtest \
    --start "$START" --end "$END" \
    --factor peg --top-n 15 --hold-days 5 \
    --min-turnover "$MIN_TURNOVER" \
    2>&1 | tee "$BASELINE_LOG" || true

echo "[Step 2] 基线回测完成，详细日志: $BASELINE_LOG"

# ──────────────────────────────────────────────────────────
# Step 3: 滑点敏感性测试（peg_h5 × 4 档滑点）
# ──────────────────────────────────────────────────────────
echo ""
echo "[Step 3] 滑点敏感性测试: peg_h5 × 0.1%/0.2%/0.3%/0.5%..."
SLIPPAGE_LOG="$LOG_DIR/slippage_sensitivity.log"

DB_ENV=$DB_ENV python3 -m strategist.microcap.run_grid \
    --start "$START" --end "$END" \
    --factors peg --hold-days 5 \
    --slippage 0.001 0.002 0.003 0.005 \
    --top-n 15 --workers "$WORKERS" \
    2>&1 | tee "$SLIPPAGE_LOG" || true

echo "[Step 3] 滑点测试完成，结果: $OUTPUT_DIR/slippage_sensitivity_*.csv"

# ──────────────────────────────────────────────────────────
# Step 4: 持有期鲁棒性测试（peg × h2/h4/h6/h7/h8）
# ──────────────────────────────────────────────────────────
echo ""
echo "[Step 4] 持有期鲁棒性测试: peg × h2/h4/h6/h7/h8..."
ROBUSTNESS_LOG="$LOG_DIR/hold_days_robustness.log"

DB_ENV=$DB_ENV python3 -m strategist.microcap.run_grid \
    --start "$START" --end "$END" \
    --factors peg --hold-days 2 4 6 7 8 \
    --top-n 15 --workers "$WORKERS" \
    2>&1 | tee "$ROBUSTNESS_LOG" || true

echo "[Step 4] 鲁棒性测试完成"

# ──────────────────────────────────────────────────────────
# Step 5: 完整网格（peg/pe/roe × h1/3/5/10）
# ──────────────────────────────────────────────────────────
echo ""
echo "[Step 5] 完整网格回测: peg/pe/roe × h1/3/5/10..."
GRID_LOG="$LOG_DIR/full_grid.log"

DB_ENV=$DB_ENV python3 -m strategist.microcap.run_grid \
    --start "$START" --end "$END" \
    --factors peg pe roe \
    --hold-days 1 3 5 10 \
    --top-n 15 --workers "$WORKERS" \
    2>&1 | tee "$GRID_LOG" || true

echo "[Step 5] 完整网格完成"

# ──────────────────────────────────────────────────────────
# Step 6: 汇总报告
# ──────────────────────────────────────────────────────────
echo ""
echo "[Step 6] 生成汇总报告..."

python3 - <<PYEOF
import sys, os, json, glob
sys.path.insert(0, "$ROOT")

output_dir = "$OUTPUT_DIR"
date_str = "${START}".replace("-","") + "_" + "${END}".replace("-","")

lines = []
lines.append("=" * 70)
lines.append("微盘股策略增强分析汇总报告")
lines.append(f"回测区间: ${START} ~ ${END}")
lines.append("=" * 70)

# 基线结果
summary_file = os.path.join(output_dir, "backtest_summary.json")
if os.path.exists(summary_file):
    with open(summary_file) as f:
        s = json.load(f)
    lines.append("\n[基线] peg_h5")
    lines.append(f"  年化收益:  {s.get('annual_return', 0):+.2%}")
    lines.append(f"  Sharpe:    {s.get('sharpe_ratio', 0):.3f}")
    lines.append(f"  最大回撤:  {s.get('max_drawdown', 0):.2%}")
    lines.append(f"  涨停跳过:  {s.get('limit_up_skipped', 0)}")
    lines.append(f"  跌停顺延:  {s.get('limit_down_delayed', 0)}")
    lines.append(f"  退市归零:  {s.get('delist_writeoffs', 0)}")
    if s.get('benchmark_annual_return') is not None:
        lines.append(f"  --- 对比基准 ({s.get('benchmark_code','')}) ---")
        lines.append(f"  基准年化:  {s.get('benchmark_annual_return', 0):+.2%}")
        lines.append(f"  超额年化:  {s.get('excess_annual_return', 0):+.2%}")
        lines.append(f"  信息比率:  {s.get('information_ratio', 0):.3f}")
        lines.append(f"  Beta:      {s.get('beta', 0):.3f}")
        lines.append(f"  Alpha:     {s.get('alpha', 0):+.2%}")

# 滑点敏感性
slip_files = glob.glob(os.path.join(output_dir, f"slippage_sensitivity_{date_str}.csv"))
if slip_files:
    import pandas as pd
    df = pd.read_csv(slip_files[0])
    lines.append("\n[滑点敏感性] peg_h5")
    lines.append(f"  {'滑点':>6}  {'年化':>8}  {'Sharpe':>7}  {'最大回撤':>9}")
    lines.append("  " + "-" * 38)
    for _, row in df.iterrows():
        sign = "+" if row['annual_return'] >= 0 else ""
        lines.append(f"  {row['slippage_rate']:.1%}   {sign}{row['annual_return']:.2%}   "
                     f"{row['sharpe']:>7.3f}   {row['max_drawdown']:.2%}")

# 持有期鲁棒性（合并 h1~h10 全量数据）
grid_files = glob.glob(os.path.join(output_dir, f"grid_summary_{date_str}.json"))
if grid_files:
    import pandas as pd
    with open(grid_files[-1]) as f:
        rows = json.load(f)
    peg_rows = [r for r in rows if r.get('factor') == 'peg' and r.get('status') == 'ok'
                and r.get('slippage_rate', 0.001) == 0.001]
    if peg_rows:
        peg_rows.sort(key=lambda r: r.get('hold_days', 0))
        lines.append("\n[持有期鲁棒性] peg @ slippage=0.1%")
        lines.append(f"  {'持有天':>6}  {'年化':>8}  {'Sharpe':>7}  {'最大回撤':>9}  {'胜率':>6}")
        lines.append("  " + "-" * 50)
        for r in peg_rows:
            sign = "+" if r['annual_return'] >= 0 else ""
            lines.append(f"  h{r['hold_days']:<5}  {sign}{r['annual_return']:.2%}   "
                         f"{r['sharpe']:>7.3f}   {r['max_drawdown']:.2%}   "
                         f"{r['win_rate']:.1%}")

lines.append("\n" + "=" * 70)
report_text = "\n".join(lines)
print(report_text)

report_file = os.path.join(output_dir, "analysis_report_${TIMESTAMP}.txt")
with open(report_file, "w") as f:
    f.write(report_text)
print(f"\n报告已保存: {report_file}")
PYEOF

echo ""
echo "=================================================="
echo " 全部分析完成"
echo " 输出目录: $OUTPUT_DIR"
echo " 日志目录: $LOG_DIR"
echo "=================================================="
