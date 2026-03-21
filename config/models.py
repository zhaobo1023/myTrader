# -*- coding: utf-8 -*-
"""
数据库模型定义

对应 wucai_trade 数据库的表结构
"""

# ============================================================
# 行情数据表
# ============================================================

TRADE_STOCK_DAILY_SQL = """
CREATE TABLE IF NOT EXISTS trade_stock_daily (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    trade_date DATE NOT NULL COMMENT '交易日期',
    open_price DECIMAL(12,4) COMMENT '开盘价',
    high_price DECIMAL(12,4) COMMENT '最高价',
    low_price DECIMAL(12,4) COMMENT '最低价',
    close_price DECIMAL(12,4) COMMENT '收盘价',
    volume BIGINT COMMENT '成交量(手)',
    amount DECIMAL(18,2) COMMENT '成交额(元)',
    turnover_rate DECIMAL(8,4) COMMENT '换手率(%)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_date (stock_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

TRADE_STOCK_DAILY_BASIC_SQL = """
CREATE TABLE IF NOT EXISTS trade_stock_daily_basic (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    trade_date DATE NOT NULL COMMENT '交易日期',
    total_mv DECIMAL(18,4) COMMENT '总市值(万元)',
    circ_mv DECIMAL(18,4) COMMENT '流通市值(万元)',
    pe_ttm DECIMAL(10,4) COMMENT '市盈率TTM',
    pb DECIMAL(10,4) COMMENT '市净率',
    ps_ttm DECIMAL(10,4) COMMENT '市销率TTM',
    total_share DECIMAL(18,4) COMMENT '总股本(万股)',
    circ_share DECIMAL(18,4) COMMENT '流通股本(万股)',
    turnover_rate DECIMAL(8,4) COMMENT '换手率(%)',
    free_share DECIMAL(18,4) COMMENT '自由流通股本(万股)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_daily_basic (stock_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

TRADE_STOCK_MONEYFLOW_SQL = """
CREATE TABLE IF NOT EXISTS trade_stock_moneyflow (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    trade_date DATE NOT NULL COMMENT '交易日期',
    buy_sm_vol DECIMAL(18,2) COMMENT '小单买入量(手)',
    buy_elg_vol DECIMAL(18,2) COMMENT '中单买入量(手)',
    buy_lg_vol DECIMAL(18,2) COMMENT '大单买入量(手)',
    sell_sm_vol DECIMAL(18,2) COMMENT '小单卖出量(手)',
    sell_elg_vol DECIMAL(18,2) COMMENT '中单卖出量(手)',
    sell_lg_vol DECIMAL(18,2) COMMENT '大单卖出量(手)',
    net_mf_vol DECIMAL(18,2) COMMENT '净流入量(手)',
    buy_md_vol DECIMAL(18,2) COMMENT '主力买入量(手)',
    sell_md_vol DECIMAL(18,2) COMMENT '主力卖出量(手)',
    net_md_vol DECIMAL(18,2) COMMENT '主力净流入(手)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_moneyflow (stock_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# ============================================================
# 财务数据表
# ============================================================

TRADE_STOCK_FINANCIAL_SQL = """
CREATE TABLE IF NOT EXISTS trade_stock_financial (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    report_date DATE NOT NULL COMMENT '报告日期',
    roe DECIMAL(10,4) COMMENT 'ROE(%)',
    net_profit_margin DECIMAL(10,4) COMMENT '销售净利率(%)',
    gross_profit_margin DECIMAL(10,4) COMMENT '销售毛利率(%)',
    debt_to_asset DECIMAL(10,4) COMMENT '资产负债率(%)',
    current_ratio DECIMAL(10,4) COMMENT '流动比率',
    quick_ratio DECIMAL(10,4) COMMENT '速动比率',
    eps DECIMAL(10,4) COMMENT '每股收益(元)',
    bvps DECIMAL(10,4) COMMENT '每股净资产(元)',
    cfps DECIMAL(10,4) COMMENT '每股现金流(元)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_financial (stock_code, report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

TRADE_STOCK_INDUSTRY_SQL = """
CREATE TABLE IF NOT EXISTS trade_stock_industry (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    stock_name VARCHAR(50) COMMENT '股票名称',
    industry VARCHAR(50) COMMENT '行业',
    sector VARCHAR(50) COMMENT '板块',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_industry (stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# ============================================================
# 技术指标表
# ============================================================

TRADE_TECHNICAL_INDICATOR_SQL = """
CREATE TABLE IF NOT EXISTS trade_technical_indicator (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    trade_date DATE NOT NULL COMMENT '交易日期',
    ma5 DECIMAL(12,4) COMMENT '5日均线',
    ma10 DECIMAL(12,4) COMMENT '10日均线',
    ma20 DECIMAL(12,4) COMMENT '20日均线',
    ma60 DECIMAL(12,4) COMMENT '60日均线',
    ma120 DECIMAL(12,4) COMMENT '120日均线',
    ma250 DECIMAL(12,4) COMMENT '250日均线',
    macd_dif DECIMAL(12,4) COMMENT 'MACD DIF',
    macd_dea DECIMAL(12,4) COMMENT 'MACD DEA',
    macd_histogram DECIMAL(12,4) COMMENT 'MACD柱状图',
    rsi_6 DECIMAL(10,4) COMMENT 'RSI(6)',
    rsi_12 DECIMAL(10,4) COMMENT 'RSI(12)',
    rsi_24 DECIMAL(10,4) COMMENT 'RSI(24)',
    kdj_k DECIMAL(10,4) COMMENT 'KDJ K值',
    kdj_d DECIMAL(10,4) COMMENT 'KDJ D值',
    kdj_j DECIMAL(10,4) COMMENT 'KDJ J值',
    bollinger_upper DECIMAL(12,4) COMMENT '布林上轨',
    bollinger_middle DECIMAL(12,4) COMMENT '布林中轨',
    bollinger_lower DECIMAL(12,4) COMMENT '布林下轨',
    atr DECIMAL(12,4) COMMENT 'ATR',
    volume_ratio DECIMAL(10,4) COMMENT '量比',
    turnover_rate DECIMAL(8,4) COMMENT '换手率(%)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_technical_indicator (stock_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# ============================================================
# 因子数据表
# ============================================================

TRADE_STOCK_FACTOR_SQL = """
CREATE TABLE IF NOT EXISTS trade_stock_factor (
    id INT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    calc_date DATE NOT NULL COMMENT '计算日期',
    momentum_20d DOUBLE COMMENT '20日动量',
    momentum_60d DOUBLE COMMENT '60日动量',
    volatility DOUBLE COMMENT '波动率',
    rsi_14 DOUBLE COMMENT '14日RSI',
    adx_14 DOUBLE COMMENT '14日ADX',
    turnover_ratio DOUBLE COMMENT '换手率比',
    price_position DOUBLE COMMENT '价格位置(52周)',
    macd_signal DOUBLE COMMENT 'MACD信号',
    close DOUBLE COMMENT '收盘价',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# ============================================================
# 新闻数据表
# ============================================================

TRADE_STOCK_NEWS_SQL = """
CREATE TABLE IF NOT EXISTS trade_stock_news (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    news_type VARCHAR(20) COMMENT '新闻类型',
    title VARCHAR(500) NOT NULL COMMENT '标题',
    content TEXT COMMENT '内容',
    source VARCHAR(50) COMMENT '来源',
    source_url VARCHAR(500) COMMENT '来源URL',
    sentiment VARCHAR(20) COMMENT '情感倾向',
    is_important TINYINT COMMENT '是否重要',
    published_at VARCHAR(50) COMMENT '发布时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_stock_news_code (stock_code),
    INDEX idx_stock_news_date (published_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# ============================================================
# 分钟线数据表
# ============================================================

TRADE_STOCK_MIN_SQL = """
CREATE TABLE IF NOT EXISTS trade_stock_min{period} (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    trade_time DATETIME NOT NULL COMMENT '交易时间',
    open_price DECIMAL(12,4) COMMENT '开盘价',
    high_price DECIMAL(12,4) COMMENT '最高价',
    low_price DECIMAL(12,4) COMMENT '最低价',
    close_price DECIMAL(12,4) COMMENT '收盘价',
    volume BIGINT COMMENT '成交量(手)',
    amount DECIMAL(18,2) COMMENT '成交额(元)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_min{period} (stock_code, trade_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# ============================================================
# 其他数据表
# ============================================================

TRADE_MARGIN_TRADE_SQL = """
CREATE TABLE IF NOT EXISTS trade_margin_trade (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    trade_date DATE NOT NULL COMMENT '交易日期',
    rzye DECIMAL(18,2) COMMENT '融资余额(元)',
    rqye DECIMAL(18,2) COMMENT '融券余额(元)',
    rzmre DECIMAL(18,2) COMMENT '融资买入额(元)',
    rqmcl DECIMAL(18,2) COMMENT '融券卖出量(股)',
    rzche DECIMAL(18,2) COMMENT '融资偿还额(元)',
    rqchl DECIMAL(18,2) COMMENT '融券偿还量(股)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_margin_trade (stock_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

TRADE_NORTH_HOLDING_SQL = """
CREATE TABLE IF NOT EXISTS trade_north_holding (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    hold_date DATE NOT NULL COMMENT '持仓日期',
    hold_amount DECIMAL(18,4) COMMENT '持仓数量(股)',
    hold_ratio DECIMAL(10,4) COMMENT '持仓占比(%)',
    hold_change DECIMAL(18,4) COMMENT '持仓变化(股)',
    hold_value DECIMAL(18,2) COMMENT '持仓市值(元)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_north_holding (stock_code, hold_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

TRADE_CALENDAR_SQL = """
CREATE TABLE IF NOT EXISTS trade_calendar (
    trade_date DATE NOT NULL COMMENT '交易日期',
    is_trading TINYINT(1) NOT NULL COMMENT '是否交易日',
    market VARCHAR(20) NOT NULL COMMENT '市场',
    PRIMARY KEY (trade_date, market)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

TRADE_CALENDAR_EVENT_SQL = """
CREATE TABLE IF NOT EXISTS trade_calendar_event (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_date DATE NOT NULL COMMENT '事件日期',
    event_time VARCHAR(20) COMMENT '事件时间',
    title VARCHAR(500) NOT NULL COMMENT '标题',
    country VARCHAR(50) COMMENT '国家',
    category VARCHAR(50) COMMENT '分类',
    importance TINYINT COMMENT '重要性(1-3)',
    forecast_value VARCHAR(50) COMMENT '预测值',
    actual_value VARCHAR(50) COMMENT '实际值',
    previous_value VARCHAR(50) COMMENT '前值',
    source VARCHAR(50) COMMENT '来源',
    ai_prompt TEXT COMMENT 'AI提示',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

TRADE_RATE_DAILY_SQL = """
CREATE TABLE IF NOT EXISTS trade_rate_daily (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    rate_date DATE NOT NULL COMMENT '日期',
    cn_bond_10y DECIMAL(10,4) COMMENT '中国10年期国债收益率(%)',
    us_bond_10y DECIMAL(10,4) COMMENT '美国10年期国债收益率(%)',
    data_source VARCHAR(20) COMMENT '数据来源',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_rate_daily (rate_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# ============================================================
# 分析报告表
# ============================================================

TRADE_ANALYSIS_REPORT_SQL = """
CREATE TABLE IF NOT EXISTS trade_analysis_report (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    report_date DATE NOT NULL COMMENT '报告日期',
    report_type VARCHAR(20) COMMENT '报告类型',
    signal_type VARCHAR(20) COMMENT '信号类型',
    signal_strength DECIMAL(10,4) COMMENT '信号强度',
    current_price DECIMAL(12,4) COMMENT '当前价格',
    support_price DECIMAL(12,4) COMMENT '支撑位',
    resistance_price DECIMAL(12,4) COMMENT '阻力位',
    trend_direction VARCHAR(20) COMMENT '趋势方向',
    trend_strength DECIMAL(10,4) COMMENT '趋势强度',
    risk_level VARCHAR(20) COMMENT '风险等级',
    recommendation VARCHAR(500) COMMENT '建议',
    analysis_data JSON COMMENT '分析数据',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_analysis_report (stock_code, report_date, report_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

TRADE_REPORT_CONSENSUS_SQL = """
CREATE TABLE IF NOT EXISTS trade_report_consensus (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    broker VARCHAR(100) COMMENT '券商',
    report_date DATE NOT NULL COMMENT '报告日期',
    rating VARCHAR(50) COMMENT '评级',
    target_price DECIMAL(12,4) COMMENT '目标价',
    eps_forecast_current DECIMAL(10,4) COMMENT '当年EPS预测',
    eps_forecast_next DECIMAL(10,4) COMMENT '明年EPS预测',
    revenue_forecast DECIMAL(18,2) COMMENT '营收预测',
    source_file VARCHAR(50) COMMENT '来源文件',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# ============================================================
# 持仓管理表
# ============================================================

MODEL_TRADE_POSITION_SQL = """
CREATE TABLE IF NOT EXISTS model_trade_position (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    stock_name VARCHAR(50) COMMENT '股票名称',
    shares INT NOT NULL COMMENT '持仓股数',
    cost_price DECIMAL(12,4) COMMENT '成本价',
    is_margin TINYINT COMMENT '是否融资',
    account_tag VARCHAR(50) COMMENT '账户标签',
    notes VARCHAR(500) COMMENT '备注',
    status TINYINT DEFAULT 1 COMMENT '状态(1持仓中,0已清仓)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# ============================================================
# ETF数据表
# ============================================================

TRADE_ETF_DAILY_SQL = """
CREATE TABLE IF NOT EXISTS trade_etf_daily (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT 'ETF代码',
    trade_date DATE NOT NULL COMMENT '交易日期',
    open_price DECIMAL(12,4) COMMENT '开盘价',
    high_price DECIMAL(12,4) COMMENT '最高价',
    low_price DECIMAL(12,4) COMMENT '最低价',
    close_price DECIMAL(12,4) COMMENT '收盘价',
    volume BIGINT COMMENT '成交量(手)',
    amount DECIMAL(18,2) COMMENT '成交额(元)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_etf_daily (stock_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# ============================================================
# OCR记录表
# ============================================================

TRADE_OCR_RECORD_SQL = """
CREATE TABLE IF NOT EXISTS trade_ocr_record (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT COMMENT '用户ID',
    image_path VARCHAR(500) NOT NULL COMMENT '图片路径',
    ocr_type VARCHAR(20) COMMENT 'OCR类型',
    ocr_result TEXT COMMENT 'OCR结果',
    parsed_data JSON COMMENT '解析数据',
    confidence DECIMAL(10,4) COMMENT '置信度',
    status TINYINT COMMENT '状态',
    error_message VARCHAR(500) COMMENT '错误信息',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


# ============================================================
# 宏观数据表
# ============================================================

TRADE_MACRO_INDICATOR_SQL = """
CREATE TABLE IF NOT EXISTS trade_macro_indicator (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    indicator_name VARCHAR(50) NOT NULL COMMENT '指标名称',
    indicator_date DATE NOT NULL COMMENT '指标日期',
    indicator_value DECIMAL(18,4) COMMENT '指标值',
    unit VARCHAR(20) COMMENT '单位',
    data_source VARCHAR(50) COMMENT '数据来源',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_macro_indicator (indicator_name, indicator_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


# ============================================================
# 建表SQL字典
# ============================================================

CREATE_TABLE_SQLS = {
    'trade_stock_daily': TRADE_STOCK_DAILY_SQL,
    'trade_stock_daily_basic': TRADE_STOCK_DAILY_BASIC_SQL,
    'trade_stock_moneyflow': TRADE_STOCK_MONEYFLOW_SQL,
    'trade_stock_financial': TRADE_STOCK_FINANCIAL_SQL,
    'trade_stock_industry': TRADE_STOCK_INDUSTRY_SQL,
    'trade_technical_indicator': TRADE_TECHNICAL_INDICATOR_SQL,
    'trade_stock_factor': TRADE_STOCK_FACTOR_SQL,
    'trade_stock_news': TRADE_STOCK_NEWS_SQL,
    'trade_stock_min1': TRADE_STOCK_MIN_SQL.replace('{period}', '1'),
    'trade_stock_min5': TRADE_STOCK_MIN_SQL.replace('{period}', '5'),
    'trade_stock_min15': TRADE_STOCK_MIN_SQL.replace('{period}', '15'),
    'trade_stock_min30': TRADE_STOCK_MIN_SQL.replace('{period}', '30'),
    'trade_stock_min60': TRADE_STOCK_MIN_SQL.replace('{period}', '60'),
    'trade_margin_trade': TRADE_MARGIN_TRADE_SQL,
    'trade_north_holding': TRADE_NORTH_HOLDING_SQL,
    'trade_calendar': TRADE_CALENDAR_SQL,
    'trade_calendar_event': TRADE_CALENDAR_EVENT_SQL,
    'trade_rate_daily': TRADE_RATE_DAILY_SQL,
    'trade_analysis_report': TRADE_ANALYSIS_REPORT_SQL,
    'trade_report_consensus': TRADE_REPORT_CONSENSUS_SQL,
    'model_trade_position': MODEL_TRADE_POSITION_SQL,
    'trade_etf_daily': TRADE_ETF_DAILY_SQL,
    'trade_ocr_record': TRADE_OCR_RECORD_SQL,
    'trade_macro_indicator': TRADE_MACRO_INDICATOR_SQL,
}


def init_database(env='local'):
    """
    初始化数据库表结构

    Args:
        env: 环境名称 'local' 或 'online'
    """
    from config.db import get_connection

    conn = get_connection(env)
    cursor = conn.cursor()

    for table_name, sql in CREATE_TABLE_SQLS.items():
        try:
            cursor.execute(sql)
            print(f"✓ {table_name} 表创建成功")
        except Exception as e:
            if 'already exists' in str(e).lower() or '已存在' in str(e):
                print(f"- {table_name} 表已存在")
            else:
                print(f"✗ {table_name} 表创建失败: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print("\n数据库初始化完成!")


if __name__ == "__main__":
    import sys
    env = sys.argv[1] if len(sys.argv) > 1 else 'local'
    init_database(env)
