#!/bin/bash
# Microcap v3.0 全量回测矩阵
# 时间: 2025-2026
# 因子: peg, pe, pure_mv, pure_mv_mom, peg_ebit_mv
# 持有期: 1, 5, 10, 20 天

set -e

# 日志目录
LOG_DIR="output/microcap/logs"
mkdir -p "$LOG_DIR"

# 时间范围
YEAR_2025_START="2025-01-01"
YEAR_2025_END="2025-12-31"
YEAR_2026_START="2026-01-01"
YEAR_2026_END="2026-04-10"

# 因子列表
FACTORS=("peg" "pe" "pure_mv" "pure_mv_mom" "peg_ebit_mv")

# 持有天数列表
HOLD_DAYS=(1 5 10 20)

# 计数器
TOTAL_TASKS=0
COMPLETED_TASKS=0

echo "=========================================="
echo "Microcap v3.0 全量回测矩阵"
echo "=========================================="
echo "时间范围: 2025 + 2026"
echo "因子组合: ${#FACTORS[@]} 个"
echo "持有天数: ${#HOLD_DAYS[@]} 种"
echo "总任务数: $((${#FACTORS[@]} * ${#HOLD_DAYS[@]} * 2))"
echo "=========================================="
echo ""

# 创建任务列表文件
TASK_LIST="$LOG_DIR/task_list.txt"
> "$TASK_LIST"

# 生成任务列表
for year in 2025 2026; do
    if [ "$year" = "2025" ]; then
        START=$YEAR_2025_START
        END=$YEAR_2025_END
    else
        START=$YEAR_2026_START
        END=$YEAR_2026_END
    fi

    for factor in "${FACTORS[@]}"; do
        for days in "${HOLD_DAYS[@]}"; do
            TOTAL_TASKS=$((TOTAL_TASKS + 1))
            echo "$year|$factor|$days|$START|$END" >> "$TASK_LIST"
        done
    done
done

echo "任务列表已生成: $TASK_LIST"
echo "总任务数: $TOTAL_TASKS"
echo ""

# 执行回测
while IFS='|' read -r year factor days start end; do
    COMPLETED_TASKS=$((COMPLETED_TASKS + 1))
    PROGRESS=$(echo "scale=2; $COMPLETED_TASKS * 100 / $TOTAL_TASKS" | bc)
    LOG_FILE="$LOG_DIR/${year}_${factor}_${days}d.log"

    echo "=========================================="
    echo "任务 [$COMPLETED_TASKS/$TOTAL_TASKS] ($PROGRESS%)"
    echo "=========================================="
    echo "年份: $year"
    echo "因子: $factor"
    echo "持有: ${days}天"
    echo "范围: $start ~ $end"
    echo "日志: $LOG_FILE"
    echo "=========================================="

    # 执行回测
    python -m strategist.microcap.run_backtest \
        --start "$start" \
        --end "$end" \
        --factor "$factor" \
        --top-n 15 \
        --hold-days "$days" \
        --market-cap-percentile 0.20 \
        --min-turnover 5000000 \
        2>&1 | tee "$LOG_FILE"

    # 检查执行结果
    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        echo "[OK] 任务完成"
    else
        echo "[ERROR] 任务失败"
        exit 1
    fi

    echo ""
done < "$TASK_LIST"

echo "=========================================="
echo "全部回测完成！"
echo "=========================================="
echo "总任务数: $TOTAL_TASKS"
echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "日志目录: $LOG_DIR"
echo "=========================================="

# 生成汇总报告
echo ""
echo "生成汇总报告..."
python -c "
import os
import json
import pandas as pd
from pathlib import Path

OUTPUT_DIR = 'output/microcap'
results = []

# 遍历所有 backtest_summary.json 文件
for json_file in Path(OUTPUT_DIR).glob('backtest_summary_*.json'):
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)

        # 从文件名提取参数
        parts = json_file.stem.replace('backtest_summary_', '').split('_')

        results.append({
            'file': json_file.name,
            'start_date': parts[0],
            'end_date': parts[1],
            'total_trades': data.get('total_trades', 0),
            'win_rate': data.get('win_rate', 0),
            'total_return': data.get('total_return', 0),
            'annual_return': data.get('annual_return', 0),
            'sharpe_ratio': data.get('sharpe_ratio', 0),
            'max_drawdown': data.get('max_drawdown', 0),
        })
    except Exception as e:
        print(f'Error reading {json_file}: {e}')

if results:
    df = pd.DataFrame(results)
    df = df.sort_values(['start_date', 'sharpe_ratio'], ascending=[True, False])

    # 保存汇总表
    summary_file = Path(OUTPUT_DIR) / 'all_backtests_summary.csv'
    df.to_csv(summary_file, index=False)
    print(f'汇总报告已保存: {summary_file}')
    print()
    print(df.to_string(index=False))
"

echo ""
echo "全部完成！"
