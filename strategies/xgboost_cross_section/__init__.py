# -*- coding: utf-8 -*-
"""
XGBoost 截面预测策略模块

基于 MASTER 论文思想，使用 XGBoost 进行股票截面预测
- 52 维技术因子
- MAD 去极值 + Z-Score 标准化
- 滚动窗口训练
- IC/ICIR 评估体系
"""

__version__ = '1.0.0'

from .feature_engine import FeatureEngine, FACTOR_TAXONOMY
from .preprocessor import Preprocessor
from .model_trainer import ModelTrainer
from .predictor import Predictor
from .evaluator import ICEvaluator
from .config import StrategyConfig

__all__ = [
    'FeatureEngine',
    'FACTOR_TAXONOMY',
    'Preprocessor',
    'ModelTrainer',
    'Predictor',
    'ICEvaluator',
    'StrategyConfig',
]
