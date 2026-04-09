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

FINANCIAL_INCOME_DETAIL_DDL = """
CREATE TABLE IF NOT EXISTS financial_income_detail (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50),
    report_date DATE NOT NULL,
    interest_income DOUBLE COMMENT 'interest income (yi)',
    interest_expense DOUBLE COMMENT 'interest expense (yi)',
    net_interest_income DOUBLE COMMENT 'net interest income (yi)',
    fee_commission_net DOUBLE COMMENT 'net fee & commission income (yi)',
    investment_income DOUBLE COMMENT 'investment income (yi)',
    fair_value_change DOUBLE COMMENT 'fair value change PnL (yi)',
    exchange_gain DOUBLE COMMENT 'exchange gain (yi)',
    other_business_income DOUBLE COMMENT 'other business income (yi)',
    non_interest_income_total DOUBLE COMMENT 'total non-interest income (yi)',
    operating_revenue DOUBLE COMMENT 'total operating revenue (yi)',
    operating_cost DOUBLE COMMENT 'operating cost (yi)',
    selling_expense DOUBLE COMMENT 'selling expense (yi)',
    admin_expense DOUBLE COMMENT 'admin expense (yi)',
    rd_expense DOUBLE COMMENT 'R&D expense (yi)',
    finance_expense DOUBLE COMMENT 'finance expense (yi)',
    asset_impairment DOUBLE COMMENT 'asset impairment loss (yi)',
    credit_impairment DOUBLE COMMENT 'credit impairment loss (yi)',
    non_operating_income DOUBLE COMMENT 'non-operating income (yi)',
    non_operating_expense DOUBLE COMMENT 'non-operating expense (yi)',
    net_profit DOUBLE COMMENT 'net profit attributable to parent (yi)',
    other_comprehensive_income DOUBLE COMMENT 'other comprehensive income (yi)',
    total_comprehensive_income DOUBLE COMMENT 'total comprehensive income (yi)',
    source VARCHAR(20) DEFAULT 'annual_report' COMMENT 'data source',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_date (stock_code, report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='income statement detail from annual report';
"""

FINANCIAL_CASHFLOW_DDL = """
CREATE TABLE IF NOT EXISTS financial_cashflow (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50),
    report_date DATE NOT NULL,
    operating_cashflow DOUBLE COMMENT 'operating activities net cash (yi)',
    investing_cashflow DOUBLE COMMENT 'investing activities net cash (yi)',
    financing_cashflow DOUBLE COMMENT 'financing activities net cash (yi)',
    net_cashflow DOUBLE COMMENT 'net change in cash (yi)',
    source VARCHAR(20) DEFAULT 'annual_report',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_date (stock_code, report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='cash flow summary from annual report';
"""

BANK_OVERDUE_DETAIL_DDL = """
CREATE TABLE IF NOT EXISTS bank_overdue_detail (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50),
    report_date DATE NOT NULL,
    total_loans DOUBLE COMMENT 'total loans (yi)',
    overdue_total DOUBLE COMMENT 'total overdue loans (yi)',
    overdue_1_90 DOUBLE COMMENT 'overdue 1-90 days (yi)',
    overdue_91_360 DOUBLE COMMENT 'overdue 91-360 days (yi)',
    overdue_361_3y DOUBLE COMMENT 'overdue 361d-3y (yi)',
    overdue_3y_plus DOUBLE COMMENT 'overdue 3y+ (yi)',
    overdue_90_plus DOUBLE COMMENT 'overdue 90d+ total (yi)',
    restructured DOUBLE COMMENT 'restructured loans (yi)',
    official_npl DOUBLE COMMENT 'official NPL balance (yi)',
    official_npl_ratio DOUBLE COMMENT 'official NPL ratio (%)',
    npl_ratio2 DOUBLE COMMENT 'NPL ratio2 = (overdue90+ + restructured) / total (%)',
    overdue90_npl_coverage DOUBLE COMMENT 'overdue90+ / NPL ratio (%)',
    source VARCHAR(20) DEFAULT 'annual_report',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_date (stock_code, report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='bank overdue loan detail from annual report';
"""

ALL_DDL = [
    FINANCIAL_INCOME_DDL,
    FINANCIAL_BALANCE_DDL,
    FINANCIAL_DIVIDEND_DDL,
    BANK_ASSET_QUALITY_DDL,
    FINANCIAL_INCOME_DETAIL_DDL,
    FINANCIAL_CASHFLOW_DDL,
    BANK_OVERDUE_DETAIL_DDL,
]
