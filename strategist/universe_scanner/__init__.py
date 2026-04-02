# -*- coding: utf-8 -*-
"""
Universe Scanner - 全量自选股自动化分层过滤系统

三层架构:
  1. 海选池 (Universe)      - 全量 ~650 只，基础数据同步
  2. 动态关注池 (Watchlist)  - ~100 只，RPS > 80 + 趋势对齐
  3. 核心监控池 (HighPriority) - ~30 只，形态契合 + 权重叠加
"""
