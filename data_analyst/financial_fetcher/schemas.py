# -*- coding: utf-8 -*-
"""DDL for financial tables"""

FINANCIAL_INCOME_DDL = """
CREATE TABLE IF NOT EXISTS financial_income (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50),
    report_date DATE NOT NULL,
    report_type VARCHAR(20),
    revenue DOUBLE COMMENT 'revenue (yi)',
    net_profit DOUBLE COMMENT 'net profit (yi)',
    net_profit_yoy DOUBLE COMMENT 'yoy%',
    roe DOUBLE COMMENT 'ROE%',
    gross_margin DOUBLE COMMENT 'gross margin%',
    eps DOUBLE COMMENT 'EPS',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_date (stock_code, report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='income statement';
"""

FINANCIAL_BALANCE_DDL = """
CREATE TABLE IF NOT EXISTS financial_balance (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50),
    report_date DATE NOT NULL,
    total_assets DOUBLE COMMENT 'total assets (yi)',
    total_equity DOUBLE COMMENT 'equity (yi)',
    loan_total DOUBLE COMMENT 'loans (yi)',
    npl_ratio DOUBLE COMMENT 'NPL%',
    provision_coverage DOUBLE COMMENT 'provision coverage%',
    provision_ratio DOUBLE COMMENT 'loan provision ratio%',
    cap_adequacy_ratio DOUBLE COMMENT 'capital adequacy%',
    tier1_ratio DOUBLE COMMENT 'tier1 ratio%',
    nim DOUBLE COMMENT 'NIM%',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_date (stock_code, report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='balance sheet + bank indicators';
"""

FINANCIAL_DIVIDEND_DDL = """
CREATE TABLE IF NOT EXISTS financial_dividend (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50),
    ex_date DATE,
    record_date DATE,
    cash_div DOUBLE COMMENT 'div per share (pre-tax)',
    div_total DOUBLE COMMENT 'total div (yi)',
    div_ratio DOUBLE COMMENT 'payout ratio%',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='dividend history';
"""

BANK_ASSET_QUALITY_DDL = """
CREATE TABLE IF NOT EXISTS bank_asset_quality (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50),
    report_date DATE NOT NULL,
    overdue_91 DOUBLE COMMENT 'overdue 91d+ loans (yi)',
    restructured DOUBLE COMMENT 'restructured loans (yi)',
    npl_ratio2 DOUBLE COMMENT 'custom NPL ratio 2%',
    provision_adj DOUBLE COMMENT 'provision adjustment (yi)',
    profit_adj_est DOUBLE COMMENT 'profit impact est (yi)',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_date (stock_code, report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='bank asset quality (flitter method)';
"""

ALL_DDL = [
    FINANCIAL_INCOME_DDL,
    FINANCIAL_BALANCE_DDL,
    FINANCIAL_DIVIDEND_DDL,
    BANK_ASSET_QUALITY_DDL,
]
