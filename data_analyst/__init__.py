# -*- coding: utf-8 -*-
"""
数据分析师模块

负责：
  - 数据拉取（QMT/Tushare/AKShare）
  - 数据清洗
  - 技术指标计算

注意：子模块按需导入，避免在 Mac 上因缺少 xtquant 等包导致整个模块无法加载。
"""
