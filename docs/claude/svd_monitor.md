# SVD 市场状态监控

新增于 2026-03-29，基于滚动 SVD 分解全 A 股收益率矩阵，监控市场因子结构变化。

## 核心特性

- 多尺度窗口 - 20日/60日/120日三窗口并行监控
- Randomized SVD - 仅提取前 10 成分，极速计算
- 突变检测 - 短窗口偏离 2sigma 自动触发警报 + 3 日冷却期
- 行业中性化 - 可选开关，适配择时/选股不同场景
- 重构误差 - Top5 因子解释不了的部分 = 市场混沌度

## 模块结构

```
data_analyst/
└── market_monitor/
    ├── config.py              # 监控参数配置
    ├── schemas.py             # Pydantic 数据模型 + DDL
    ├── data_builder.py        # 收益率矩阵构建 + 预处理
    ├── svd_engine.py          # Randomized SVD 引擎
    ├── regime_classifier.py   # 市场状态分类 + 突变检测
    ├── storage.py             # 数据库读写层
    ├── visualizer.py          # 多尺度可视化
    ├── reporter.py            # Markdown 报告生成
    └── run_monitor.py         # 主入口 + CLI
```

## 快速开始

```bash
# 仅计算最新状态
python -m data_analyst.market_monitor.run_monitor --latest

# 回填历史数据
python -m data_analyst.market_monitor.run_monitor --start 2025-01-01 --end 2026-03-28

# 开启行业中性化
python -m data_analyst.market_monitor.run_monitor --latest --industry-neutral
```

## 输出结果

- `output/svd_monitor/svd_market_regime.png` - 多尺度监控图
- `output/svd_monitor/svd_report_YYYY-MM-DD.md` - 每日报告
- 数据库表 `trade_svd_market_state` - 历史数据

[返回主文档](../../CLAUDE.md)
