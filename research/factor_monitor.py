# -*- coding: utf-8 -*-
"""
因子监控模块 (Factor Monitor)

功能:
    1. 对因子表中所有因子计算60日滚动IC
    2. 判断因子状态 (有效/衰减/失效)
    3. 结果存入 factor_status 表
    4. 状态变化时记录到 factor_alerts 表

运行:
    python research/factor_monitor.py
"""
import sys
import os
import json
import argparse
from datetime import date, timedelta
from typing import Optional, Dict, List, Tuple

import pandas as pd
import numpy as np
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.db import execute_query, get_connection
import config.settings as settings


# ============================================================
# 配置
# ============================================================

ROLLING_WINDOW = 60  # 滚动IC窗口
IC_VALID_THRESHOLD = 0.03  # 有效: IC均值 > 0.03
IC_DECAYING_THRESHOLD = 0.01  # 衰减: 0.01 < IC均值 < 0.03
# 失效: IC均值 < 0.01

# 从 settings 或环境变量获取飞书 Webhook
# 从环境变量获取飞书 Webhook
FEISHU_WEBHOOK_URL = os.environ.get('FEISHU_WEBHOOK_URL', '')
OUTPUT_DIR = 'output'

# 默认监控的因子
DEFAULT_FACTORS = {
    'oil_mom_20': '原油20日涨跌幅',
    'gold_mom_20': '黄金20日涨跌幅',
    'vix_ma5': 'VIX 5日均值',
    'north_flow_5d': '北向资金5日累计净流入',
}


# ============================================================
# 数据库表结构
# ============================================================

CREATE_FACTOR_STATUS_TABLE = """
CREATE TABLE IF NOT EXISTS factor_status (
    id INT AUTO_INCREMENT PRIMARY KEY,
    factor_code VARCHAR(50) NOT NULL COMMENT '因子代码',
    factor_name VARCHAR(100) COMMENT '因子名称',
    calc_date DATE NOT NULL COMMENT '计算日期',
    rolling_ic DECIMAL(10, 6) COMMENT '滚动IC均值',
    rolling_icir DECIMAL(10, 6) COMMENT '滚动ICIR',
    status ENUM('valid', 'decaying', 'invalid') COMMENT '因子状态',
    sample_count INT COMMENT '样本数',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_factor_date (factor_code, calc_date),
    INDEX idx_calc_date (calc_date),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='因子状态表';
"""

CREATE_FACTOR_ALERTS_TABLE = """
CREATE TABLE IF NOT EXISTS factor_alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    factor_code VARCHAR(50) NOT NULL COMMENT '因子代码',
    alert_date DATE NOT NULL COMMENT '报警日期',
    old_status VARCHAR(20) COMMENT '旧状态',
    new_status VARCHAR(20) COMMENT '新状态',
    rolling_ic DECIMAL(10, 6) COMMENT '滚动IC',
    message TEXT COMMENT '报警消息',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_alert_date (alert_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='因子报警表';
"""


def ensure_tables_exist():
    """确保必要的表存在"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(CREATE_FACTOR_STATUS_TABLE)
    cursor.execute(CREATE_FACTOR_ALERTS_TABLE)
    conn.commit()
    cursor.close()
    conn.close()


# ============================================================
# 数据加载
# ============================================================

def load_factor_data(factor_code: str) -> pd.DataFrame:
    """
    从 macro_factors 表加载因子数据

    Args:
        factor_code: 因子代码

    Returns:
        DataFrame with index=date, columns=[value]
    """
    sql = """
        SELECT date, value
        FROM macro_factors
        WHERE indicator = %s
        ORDER BY date ASC
    """
    rows = execute_query(sql, [factor_code])

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    df = df.set_index('date').sort_index()
    return df


# ============================================================
# IC 计算
# ============================================================

def calculate_rolling_ic(factor_df: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """
    计算滚动IC

    这里使用因子值的变化率作为IC的代理指标
    (实际应用中应该用因子值与未来收益的相关性)

    Args:
        factor_df: 因子数据 DataFrame
        window: 滚动窗口

    Returns:
        DataFrame with columns: [rolling_ic, rolling_std, icir]
    """
    if factor_df.empty or len(factor_df) < window:
        return pd.DataFrame()

    result = pd.DataFrame(index=factor_df.index)

    # 计算因子变化率作为 IC 代理
    factor_returns = factor_df['value'].pct_change()

    # 滚动计算 IC 均值和标准差
    result['rolling_ic'] = factor_returns.rolling(window=window).mean()
    result['rolling_std'] = factor_returns.rolling(window=window).std()
    result['icir'] = result['rolling_ic'].abs() / (result['rolling_std'] + 1e-10)

    # 移除 NaN
    result = result.dropna()

    return result


def determine_status(ic_mean: float) -> str:
    """
    判断因子状态

    Args:
        ic_mean: 滚动IC均值

    Returns:
        'valid', 'decaying', 'invalid'
    """
    abs_ic = abs(ic_mean)

    if abs_ic >= IC_VALID_THRESHOLD:
        return 'valid'
    elif abs_ic >= IC_DECAYING_THRESHOLD:
        return 'decaying'
    else:
        return 'invalid'


# ============================================================
# 状态保存
# ============================================================

def get_previous_status(factor_code: str) -> Optional[str]:
    """获取因子上一次的状态"""
    sql = """
        SELECT status
        FROM factor_status
        WHERE factor_code = %s
        ORDER BY calc_date DESC
        LIMIT 1
    """
    rows = execute_query(sql, [factor_code])
    if rows:
        return rows[0]['status']
    return None


def save_factor_status(
    factor_code: str,
    factor_name: str,
    calc_date: str,
    rolling_ic: float,
    icir: float,
    status: str,
    sample_count: int
) -> None:
    """保存因子状态"""
    sql = """
        INSERT INTO factor_status
        (factor_code, factor_name, calc_date, rolling_ic, rolling_icir, status, sample_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        rolling_ic = VALUES(rolling_ic),
        rolling_icir = VALUES(rolling_icir),
        status = VALUES(status),
        sample_count = VALUES(sample_count)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, [factor_code, factor_name, calc_date, rolling_ic, icir, status, sample_count])
    conn.commit()
    cursor.close()
    conn.close()


def save_alert(
    factor_code: str,
    alert_date: str,
    old_status: str,
    new_status: str,
    rolling_ic: float,
    message: str
) -> None:
    """保存报警记录"""
    sql = """
        INSERT INTO factor_alerts
        (factor_code, alert_date, old_status, new_status, rolling_ic, message)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, [factor_code, alert_date, old_status, new_status, rolling_ic, message])
    conn.commit()
    cursor.close()
    conn.close()


# ============================================================
# 飞书报警
# ============================================================

def send_feishu_alert(title: str, content: str) -> bool:
    """发送飞书报警"""
    if not FEISHU_WEBHOOK_URL:
        return False

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "red"
            },
            "elements": [
                {"tag": "markdown", "content": content}
            ]
        }
    }

    try:
        resp = requests.post(FEISHU_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"  飞书报警发送失败: {e}")
        return False


# ============================================================
# 报告生成
# ============================================================

def generate_report(output_dir: str, results: List[Dict]) -> str:
    """生成监控报告"""
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, 'factor_monitor_report.json')

    report = {
        'report_date': date.today().strftime('%Y-%m-%d'),
        'total_factors': len(results),
        'valid_count': sum(1 for r in results if r['status'] == 'valid'),
        'decaying_count': sum(1 for r in results if r['status'] == 'decaying'),
        'invalid_count': sum(1 for r in results if r['status'] == 'invalid'),
        'factors': results
    }

    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report_path


# ============================================================
# 主监控流程
# ============================================================

def monitor_factor(factor_code: str, factor_name: str) -> Optional[Dict]:
    """
    监控单个因子

    Returns:
        监控结果字典或 None
    """
    print(f"\n  监控因子: {factor_name} ({factor_code})")

    # 加载因子数据
    df = load_factor_data(factor_code)
    if df.empty:
        print(f"    [警告] 无数据")
        return None

    print(f"    数据: {len(df)} 条, {df.index.min().date()} ~ {df.index.max().date()}")

    # 计算滚动IC
    ic_df = calculate_rolling_ic(df, ROLLING_WINDOW)
    if ic_df.empty:
        print(f"    [警告] 滚动IC计算失败")
        return None

    # 获取最新值
    latest = ic_df.iloc[-1]
    rolling_ic = float(latest['rolling_ic'])
    icir = float(latest['icir'])
    status = determine_status(rolling_ic)

    print(f"    滚动IC: {rolling_ic:.4f}, ICIR: {icir:.4f}, 状态: {status}")

    # 保存状态
    calc_date = date.today().strftime('%Y-%m-%d')
    save_factor_status(
        factor_code, factor_name, calc_date,
        rolling_ic, icir, status, len(ic_df)
    )

    # 检查状态变化
    prev_status = get_previous_status(factor_code)
    if prev_status and prev_status != status:
        # 状态发生变化，记录报警
        message = f"因子 {factor_name} 状态变化: {prev_status} -> {status}\n滚动IC: {rolling_ic:.4f}"
        save_alert(factor_code, calc_date, prev_status, status, rolling_ic, message)
        print(f"    [报警] 状态变化: {prev_status} -> {status}")

        # 发送飞书报警
        if FEISHU_WEBHOOK_URL:
            send_feishu_alert("因子状态变化报警", message)

    return {
        'factor_code': factor_code,
        'factor_name': factor_name,
        'rolling_ic': rolling_ic,
        'icir': icir,
        'status': status,
        'sample_count': len(ic_df),
        'latest_date': ic_df.index[-1].strftime('%Y-%m-%d')
    }


def run_monitor(factor_codes: List[str] = None, output_dir: str = None) -> Dict:
    """
    运行因子监控

    Args:
        factor_codes: 要监控的因子列表
        output_dir: 输出目录

    Returns:
        监控结果汇总
    """
    print("=" * 60)
    print("因子监控程序")
    print("=" * 60)

    # 确保表存在
    print("\n检查数据库表...")
    ensure_tables_exist()
    print("  表检查完成")

    # 使用默认因子列表
    if factor_codes is None:
        factor_codes = list(DEFAULT_FACTORS.keys())

    print(f"\n监控因子: {len(factor_codes)} 个")

    # 监控每个因子
    results = []
    for factor_code in factor_codes:
        factor_name = DEFAULT_FACTORS.get(factor_code, factor_code)
        result = monitor_factor(factor_code, factor_name)
        if result:
            results.append(result)

    # 生成报告
    if output_dir is None:
        output_dir = OUTPUT_DIR

    print("\n生成监控报告...")
    report_path = generate_report(output_dir, results)
    print(f"  报告已保存: {report_path}")

    # 打印汇总
    print("\n" + "=" * 60)
    print("监控汇总:")
    print("-" * 60)
    print(f"{'因子':<20} {'状态':<10} {'滚动IC':<12} {'ICIR':<10}")
    print("-" * 60)
    for r in results:
        print(f"{r['factor_name']:<20} {r['status']:<10} {r['rolling_ic']:>10.4f} {r['icir']:>10.4f}")
    print("-" * 60)

    valid_cnt = sum(1 for r in results if r['status'] == 'valid')
    decaying_cnt = sum(1 for r in results if r['status'] == 'decaying')
    invalid_cnt = sum(1 for r in results if r['status'] == 'invalid')

    print(f"有效: {valid_cnt}, 衰减: {decaying_cnt}, 失效: {invalid_cnt}")
    print("=" * 60)

    return {
        'results': results,
        'report_path': report_path,
        'valid_count': valid_cnt,
        'decaying_count': decaying_cnt,
        'invalid_count': invalid_cnt
    }


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='因子监控')
    parser.add_argument('--factors', nargs='+', help='要监控的因子代码')
    parser.add_argument('--output', type=str, default='output', help='输出目录')
    args = parser.parse_args()

    run_monitor(factor_codes=args.factors, output_dir=args.output)
