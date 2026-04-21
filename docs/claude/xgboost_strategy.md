# XGBoost 截面预测策略

新增于 2026-03-27，基于 MASTER 论文 (AAAI 2024) 思想，使用 XGBoost 进行股票截面预测的量化策略。

## 核心特性

- 52 维技术因子 - 6 大类因子（价量、动量、波动率、技术指标、均线形态、交互）
- 截面预处理 - MAD 去极值 + Z-Score 标准化
- 滚动窗口训练 - XGBoost 模型滚动训练
- IC 评估体系 - IC/ICIR/RankIC/RankICIR
- 完整回测框架 - 基于预测排名的选股回测

## 模块结构

```
strategist/xgboost_strategy/
├── config.py              # 策略配置
├── feature_engine.py      # 52维因子计算引擎
├── preprocessor.py        # 截面预处理（MAD/Z-Score）
├── data_loader.py         # 数据加载与因子计算
├── model_trainer.py       # XGBoost滚动窗口训练
├── predictor.py           # 截面预测器
├── evaluator.py           # IC评估器
├── backtest.py            # 回测框架
├── visualizer.py          # 可视化工具
├── run_strategy.py        # 主入口脚本
├── test_strategy.py       # 测试脚本
└── README.md              # 详细文档
```

## 快速开始

```bash
# 安装依赖（必需）
pip install xgboost scipy scikit-learn
brew install ta-lib && pip install TA-Lib  # macOS

# 测试模块
python -m strategist.xgboost_strategy.test_strategy

# 运行策略
python -m strategist.xgboost_strategy.run_strategy
```

## 输出结果

- `output/xgboost/signals.csv` - 每日预测信号
- `output/xgboost/portfolio_returns.csv` - 组合收益
- `output/xgboost/factor_ic.csv` - 因子 IC 统计
- `output/xgboost/ic_analysis.png` - IC 时序图和分布
- `output/xgboost/portfolio_performance.png` - 组合表现
- `output/xgboost/factor_ic.png` - 因子 IC 排名
- `output/xgboost/strategy_report.md` - 策略报告

## 预期效果

- IC: 0.03~0.05
- ICIR: 0.3~0.5
- RankIC: 0.04~0.06

详见 `strategist/xgboost_strategy/README.md`

[返回主文档](../../CLAUDE.md)
