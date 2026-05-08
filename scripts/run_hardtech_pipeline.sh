#!/bin/bash
# Hard-tech factor full pipeline on server
# Usage: bash scripts/run_hardtech_pipeline.sh

set -e
cd /root/app

echo "========================================="
echo "Step 0: Create hardtech factor table"
echo "========================================="
DB_ENV=online python -c "
from config.db import get_connection
conn = get_connection()
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS trade_stock_hardtech_factor (
    id INT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL,
    calc_date DATE NOT NULL,
    rd_intensity DOUBLE,
    rd_growth DOUBLE,
    rd_efficiency DOUBLE,
    gross_margin_trend DOUBLE,
    rd_expense DOUBLE,
    report_date_used DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_code_date (calc_date, stock_code),
    KEY idx_calc_date (calc_date),
    KEY idx_stock_code (stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
''')
conn.commit()
print('Table ready')
cursor.close()
conn.close()
"

echo ""
echo "========================================="
echo "Step 1: Fetch rd_expense from Sina (30min)"
echo "========================================="
DB_ENV=online python data_analyst/factors/hardtech_factor_calculator.py --fetch-rd

echo ""
echo "========================================="
echo "Step 2: Calculate rd factors"
echo "========================================="
DB_ENV=online python data_analyst/factors/hardtech_factor_calculator.py --calc-rd

echo ""
echo "========================================="
echo "Step 3: Backfill gross_margin_trend"
echo "========================================="
DB_ENV=online python data_analyst/factors/hardtech_factor_calculator.py --backfill --start 2024-01-01

echo ""
echo "========================================="
echo "Step 4: Run IC analysis"
echo "========================================="
DB_ENV=online python -m strategist.hard_tech.run_selector --mode ic --start 2024-01-01

echo ""
echo "========================================="
echo "Pipeline complete!"
echo "========================================="
