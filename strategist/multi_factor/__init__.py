# -*- coding: utf-8 -*-
"""
多因子选股模块

基于横截面百分位打分的多因子选股框架。
支持单因子选股、等权合成选股、IC验证和简单回测。
"""

from .scorer import FactorSelector
from .config import FACTORS, FACTOR_DIRECTIONS

__all__ = ['FactorSelector', 'FACTORS', 'FACTOR_DIRECTIONS']
