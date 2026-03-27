# -*- coding: utf-8 -*-
"""
Paper Trading 数据库表结构

提供建表 SQL 和初始化方法。
"""
import logging

logger = logging.getLogger(__name__)

# ============================================================
# 建表 SQL
# ============================================================

CREATE_PT_ROUNDS = """
CREATE TABLE IF NOT EXISTS pt_rounds (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    round_id      VARCHAR(32) NOT NULL UNIQUE COMMENT '轮次ID，如 20260328_沪深300',
    signal_date   DATE NOT NULL COMMENT '信号生成日（周五）',
    buy_date      DATE NOT NULL COMMENT '买入日（signal_date + 1 交易日）',
    sell_date     DATE NOT NULL COMMENT '卖出日（buy_date + hold_days 交易日）',
    index_name    VARCHAR(32) NOT NULL COMMENT '指数池名称',
    hold_days     INT DEFAULT 5 COMMENT '持仓天数（交易日）',
    top_n         INT DEFAULT 10 COMMENT '选股数量',
    status        ENUM('pending','active','settled','cancelled') DEFAULT 'pending' COMMENT '轮次状态',
    portfolio_ret DECIMAL(10,6) NULL COMMENT '策略收益（扣费后，%）',
    benchmark_ret DECIMAL(10,6) NULL COMMENT '基准收益（%）',
    excess_ret    DECIMAL(10,6) NULL COMMENT '超额收益（%）',
    ic            DECIMAL(10,6) NULL COMMENT 'Spearman IC',
    rank_ic       DECIMAL(10,6) NULL COMMENT 'RankIC',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    settled_at    DATETIME NULL,
    INDEX idx_signal_date (signal_date),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Paper Trading 轮次表';
"""

CREATE_PT_POSITIONS = """
CREATE TABLE IF NOT EXISTS pt_positions (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    round_id      VARCHAR(32) NOT NULL COMMENT '轮次ID',
    stock_code    VARCHAR(16) NOT NULL COMMENT '股票代码',
    pred_score    DECIMAL(10,6) NOT NULL COMMENT '模型预测分值',
    pred_rank     INT NOT NULL COMMENT '截面内预测排名（1=最高）',
    buy_price     DECIMAL(12,4) NULL COMMENT '实际买入价（T+1 收盘价）',
    sell_price    DECIMAL(12,4) NULL COMMENT '实际卖出价（T+N 收盘价）',
    gross_ret     DECIMAL(10,6) NULL COMMENT '毛收益（%）',
    net_ret       DECIMAL(10,6) NULL COMMENT '净收益（扣费后，%）',
    actual_rank   INT NULL COMMENT '实际收益在截面内的排名',
    status        ENUM('pending','active','settled') DEFAULT 'pending' COMMENT '持仓状态',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    settled_at    DATETIME NULL,
    INDEX idx_round_id (round_id),
    INDEX idx_stock_code (stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Paper Trading 持仓明细表';
"""

CREATE_PT_BENCHMARK = """
CREATE TABLE IF NOT EXISTS pt_benchmark (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    trade_date   DATE NOT NULL COMMENT '交易日期',
    index_name   VARCHAR(32) NOT NULL COMMENT '指数名称',
    index_code   VARCHAR(16) NOT NULL COMMENT '指数代码',
    close_price  DECIMAL(12,4) NOT NULL COMMENT '收盘点位',
    daily_ret    DECIMAL(10,6) NULL COMMENT '日收益率（%）',
    UNIQUE KEY uk_date_idx (trade_date, index_name),
    INDEX idx_trade_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基准指数日收益表';
"""


def _execute_ddl(sql, env=None):
    """
    执行 DDL 语句。

    直接使用连接执行，避免 pymysql 将 SQL 中的 % 号（如 COMMENT 中的 %）
    误解析为参数占位符。
    """
    from config.db import get_connection

    conn = get_connection(env)
    cursor = conn.cursor()
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()


def init_tables(env=None):
    """
    初始化 Paper Trading 所需的数据库表。

    Args:
        env: 数据库环境 ('local' / 'online' / None)
    """
    tables = [
        ('pt_rounds', CREATE_PT_ROUNDS),
        ('pt_positions', CREATE_PT_POSITIONS),
        ('pt_benchmark', CREATE_PT_BENCHMARK),
    ]

    for table_name, sql in tables:
        try:
            _execute_ddl(sql, env=env)
            logger.info(f"表 {table_name} 检查/创建完成")
        except Exception as e:
            logger.error(f"创建表 {table_name} 失败: {e}")
            raise

    logger.info("Paper Trading 数据库初始化完成")


def drop_tables(env=None):
    """删除 Paper Trading 表（仅用于测试清理）"""
    for table in ['pt_positions', 'pt_rounds', 'pt_benchmark']:
        try:
            _execute_ddl(f"DROP TABLE IF EXISTS {table}", env=env)
            logger.info(f"表 {table} 已删除")
        except Exception as e:
            logger.warning(f"删除表 {table} 失败: {e}")
