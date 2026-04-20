# -*- coding: utf-8 -*-

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime

from data_analyst.risk_assessment.schemas import (
    LayeredRiskResult, MacroRiskResult, RegimeRiskResult,
    SectorRiskResult, StockRiskResult, DataStatus,
)

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(ROOT, 'output', 'risk_assessment')


def dataclass_to_dict(obj):
    """递归将 dataclass / tuple / list / dict 转换为 JSON 可序列化结构。"""
    if hasattr(obj, '__dataclass_fields__'):
        return {k: dataclass_to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: dataclass_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [dataclass_to_dict(i) for i in obj]
    return obj


def save_scan_result(result: LayeredRiskResult, env: str = 'online') -> str:
    """
    将扫描结果持久化到 output/risk_assessment/ 目录。

    文件名格式: risk_scan_YYYYMMDD.json
    若当日已有文件则覆盖。

    返回保存的文件路径。
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    date_str = result.scan_time[:10].replace('-', '')
    filename = 'risk_scan_{}.json'.format(date_str)
    filepath = os.path.join(OUTPUT_DIR, filename)

    try:
        data = {
            'scan_time': result.scan_time,
            'user_id': result.user_id,
            'env': env,
            'overall_score': result.overall_score,
            'overall_suggestions': result.overall_suggestions,
            'data_status': dataclass_to_dict(result.data_status),
            'macro': dataclass_to_dict(result.macro),
            'regime': dataclass_to_dict(result.regime),
            'sector': dataclass_to_dict(result.sector),
            'stocks': dataclass_to_dict(result.stocks),
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("风控扫描结果已保存: %s", filepath)
    except Exception as e:
        logger.error("保存扫描结果失败: %s", e)
        raise

    return filepath


def reconstruct_layered_result(cached: dict) -> LayeredRiskResult:
    """从 JSON 缓存 dict 重建 LayeredRiskResult dataclass。"""
    macro = MacroRiskResult(**cached['macro'])
    regime = RegimeRiskResult(**cached['regime'])
    sector = SectorRiskResult(**cached['sector'])
    stocks = [StockRiskResult(**s) for s in cached.get('stocks', [])]
    data_status = [DataStatus(**d) for d in cached.get('data_status', [])]
    return LayeredRiskResult(
        scan_time=cached['scan_time'],
        user_id=cached['user_id'],
        data_status=data_status,
        macro=macro,
        regime=regime,
        sector=sector,
        stocks=stocks,
        overall_score=cached['overall_score'],
        overall_suggestions=cached.get('overall_suggestions', []),
    )


def load_scan_result(date_str: str = None) -> dict:
    """
    从文件加载扫描结果（用于调试/查看）。

    date_str: 'YYYYMMDD' 格式，默认加载最新文件。
    返回 dict，若文件不存在返回 None。
    """
    if not os.path.isdir(OUTPUT_DIR):
        return None

    if date_str:
        filepath = os.path.join(OUTPUT_DIR, 'risk_scan_{}.json'.format(date_str))
    else:
        # 找最新文件
        files = sorted(
            [f for f in os.listdir(OUTPUT_DIR) if f.startswith('risk_scan_') and f.endswith('.json')],
            reverse=True,
        )
        if not files:
            return None
        filepath = os.path.join(OUTPUT_DIR, files[0])

    if not os.path.isfile(filepath):
        return None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error("加载扫描结果失败 %s: %s", filepath, e)
        return None
